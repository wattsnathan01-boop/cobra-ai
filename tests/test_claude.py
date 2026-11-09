import unittest
from types import SimpleNamespace as NS

from cobrad.brain.claude import ClaudeBrain, to_messages, to_tools
from cobrad.brain.router import Router, choose, strip_choice

from test_core import run

THINK = {"type": "thinking", "thinking": "", "signature": "sig"}


class TranslateTests(unittest.TestCase):
    def test_instructions_stay_frozen_and_context_follows_the_question(self):
        system, msgs = to_messages([{"role": "system", "content": "persona"},
                                    {"role": "user", "content": "hi"}], "time: 10:00")
        self.assertEqual(system, "persona")
        self.assertEqual(msgs, [{"role": "user", "content": "hi"},
                                {"role": "system", "content": "time: 10:00"}])

    def test_thinking_is_kept_only_within_the_current_question(self):
        old = {"role": "assistant", "content": "Old answer",
               "claude_blocks": [THINK, {"type": "text", "text": "Old answer"}]}
        step = {"role": "assistant", "content": "",
                "claude_blocks": [THINK, {"type": "tool_use", "id": "t1", "name": "x", "input": {}}],
                "tool_calls": [{"id": "t1", "function": {"name": "x", "arguments": {}}}]}
        _, msgs = to_messages([{"role": "system", "content": "p"},
                               {"role": "user", "content": "first"}, old,
                               {"role": "user", "content": "second"}, step,
                               {"role": "tool", "tool_name": "x", "content": "ok",
                                "tool_call_id": "t1"}], "ctx")
        roles = [m["role"] for m in msgs]
        self.assertEqual(roles, ["user", "assistant", "user", "system", "assistant", "user"])
        self.assertEqual([b["type"] for b in msgs[1]["content"]], ["text"])  # old: no thinking
        self.assertEqual([b["type"] for b in msgs[4]["content"]], ["thinking", "tool_use"])
        self.assertEqual(msgs[5]["content"][0], {"type": "tool_result", "tool_use_id": "t1",
                                                 "content": "ok"})

    def test_turns_the_local_brain_answered_get_matching_ids(self):
        _, msgs = to_messages([
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "",
             "tool_calls": [{"function": {"name": "a", "arguments": {}}},
                            {"function": {"name": "b", "arguments": {"x": 1}}}]},
            {"role": "tool", "tool_name": "a", "content": "A"},
            {"role": "tool", "tool_name": "b", "content": "B"},
        ], "")
        uses = [b["id"] for b in msgs[1]["content"]]
        results = [b["tool_use_id"] for b in msgs[2]["content"]]
        self.assertEqual(uses, results)
        self.assertEqual(len(msgs), 3)  # both results in one user message

    def test_a_note_after_her_reply_goes_in_as_a_user_note(self):
        _, msgs = to_messages([{"role": "user", "content": "q"},
                               {"role": "assistant", "content": "I've done it"},
                               {"role": "system", "content": "you didn't"}], "")
        self.assertEqual(msgs[-1]["role"], "user")
        self.assertIn("you didn't", str(msgs[-1]["content"]))

    def test_two_notes_in_a_row_are_merged(self):
        _, msgs = to_messages([{"role": "user", "content": "q"},
                               {"role": "system", "content": "check your tools"}], "ctx")
        self.assertEqual([m["role"] for m in msgs], ["user", "system"])
        self.assertIn("ctx", msgs[1]["content"])
        self.assertIn("check your tools", msgs[1]["content"])

    def test_tools(self):
        t = to_tools([{"type": "function", "function": {"name": "n", "description": "d",
                                                        "parameters": {"type": "object"}}}])
        self.assertEqual(t, [{"name": "n", "description": "d", "input_schema": {"type": "object"}}])


class Block(NS):
    def to_dict(self, exclude_none=False):
        return {k: v for k, v in vars(self).items() if not (exclude_none and v is None)}


class FakeStream:
    def __init__(self, events, final):
        self.events, self.final = events, final

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        async def gen():
            for e in self.events:
                yield e
        return gen()

    async def get_final_message(self):
        return self.final


class FakeClient:
    def __init__(self, final, events):
        self.sent = None
        outer = self

        def stream(**kwargs):
            outer.sent = kwargs
            return FakeStream(events, final)
        self.beta = NS(messages=NS(stream=stream))


class PausingClient:
    """Answers with each final message in turn (for pause_turn)."""
    def __init__(self, finals):
        self.sent = []
        outer = self

        def stream(**kwargs):
            outer.sent.append(kwargs)
            return FakeStream([], finals[len(outer.sent) - 1])
        self.beta = NS(messages=NS(stream=stream))


def usage(searches=0):
    return NS(input_tokens=0, output_tokens=0, cache_read_input_tokens=0,
              cache_creation_input_tokens=0, server_tool_use=NS(web_search_requests=searches))


class ClaudeBrainTests(unittest.TestCase):
    def test_web_search_pauses_and_costs(self):
        import asyncio
        search = [Block(type="server_tool_use", id="s1", name="web_search", input={"query": "q"}),
                  Block(type="web_search_tool_result", tool_use_id="s1", content=[])]
        client = PausingClient([
            NS(model="claude-opus-5-5", stop_reason="pause_turn", usage=usage(2), content=search),
            NS(model="claude-opus-5-5", stop_reason="end_turn", usage=usage(1),
               content=[Block(type="text", text="Sunny.")]),
        ])
        spent = []
        brain = ClaudeBrain("k", client=client, on_usage=lambda m, c: spent.append(c))

        async def go():
            return [ev async for ev in brain.chat([{"role": "user", "content": "weather?"}], [])]
        self.assertEqual(asyncio.run(go()), [])  # (the text arrives as stream events)
        tools = [t["type"] for t in client.sent[0]["tools"] if "type" in t]
        self.assertEqual(tools, ["web_search_20260209", "web_fetch_20260209"])
        self.assertEqual(client.sent[1]["messages"][-1]["role"], "assistant")  # carried on
        self.assertEqual([round(c, 4) for c in spent], [0.02, 0.01])
        blocks = brain.assistant_message("Sunny.", [])["claude_blocks"]
        self.assertEqual([b["type"] for b in blocks],
                         ["server_tool_use", "web_search_tool_result", "text"])
        # a later question doesn't resend the search results
        _, msgs = to_messages([{"role": "user", "content": "weather?"},
                               {"role": "assistant", "content": "Sunny.", "claude_blocks": blocks},
                               {"role": "user", "content": "thanks"}], "")
        self.assertEqual([b["type"] for b in msgs[1]["content"]], ["text", "text"])
        self.assertIn('searched "q" on the web', msgs[1]["content"][0]["text"])

    def test_web_can_be_turned_off(self):
        import asyncio
        client = PausingClient([NS(model="claude-opus-5-5", stop_reason="end_turn",
                                   usage=usage(), content=[])])
        brain = ClaudeBrain("k", client=client, web=False)

        async def go():
            return [ev async for ev in brain.chat([{"role": "user", "content": "x"}], [])]
        asyncio.run(go())
        self.assertEqual(client.sent[0]["tools"], [])

    def test_request_and_reply(self):
        import asyncio
        final = NS(model="claude-opus-5-5", stop_reason="tool_use",
                   usage=NS(input_tokens=1000, output_tokens=100, cache_read_input_tokens=0,
                            cache_creation_input_tokens=0),
                   content=[Block(type="thinking", thinking="", signature="s"),
                            Block(type="text", text="Checking."),
                            Block(type="tool_use", id="t9", name="system_stats", input={})])
        client = FakeClient(final, [NS(type="text", text="Checking.")])
        spent = []
        brain = ClaudeBrain("k", "claude-opus-5-5", "low", on_usage=lambda m, c: spent.append(c),
                            client=client)

        async def go():
            return [ev async for ev in brain.chat([{"role": "system", "content": "persona"},
                                                   {"role": "user", "content": "how hot?"}],
                                                  [], "time")]
        events = asyncio.run(go())
        self.assertEqual(events[0], {"type": "text", "text": "Checking."})
        self.assertEqual(events[1]["calls"], [{"name": "system_stats", "arguments": {}, "id": "t9"}])
        sent = client.sent
        self.assertEqual(sent["fallbacks"], "default")
        self.assertIn("server-side-fallback-2026-07-01", sent["betas"])
        self.assertEqual(sent["thinking"]["block_binding"]["prefix_mismatch_behavior"], "drop_block")
        self.assertEqual(sent["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(sent["output_config"], {"effort": "low"})
        self.assertNotIn("temperature", sent)
        self.assertAlmostEqual(spent[0], (1000 * 4 + 100 * 20) / 1e6)
        msg = brain.assistant_message("Checking.", events[1]["calls"])
        self.assertEqual([b["type"] for b in msg["claude_blocks"]], ["thinking", "text", "tool_use"])
        self.assertEqual(brain.tool_message("system_stats", "{}", "t9")["tool_call_id"], "t9")

    def test_a_refusal_is_said_plainly(self):
        import asyncio
        final = NS(model="claude-opus-5-5", stop_reason="refusal", content=[],
                   usage=NS(input_tokens=1, output_tokens=0, cache_read_input_tokens=0,
                            cache_creation_input_tokens=0))
        brain = ClaudeBrain("k", client=FakeClient(final, []))

        async def go():
            return [ev async for ev in brain.chat([{"role": "user", "content": "x"}], [])]
        self.assertIn("can't help", asyncio.run(go())[0]["text"])


class RoutingTests(unittest.TestCase):
    def test_auto(self):
        cases = {
            "what's my battery at?": "local",
            "turn the volume down": "local",
            "open the browser": "local",
            "remember that my cat is called Miso": "local",
            "install cowsay": "local",
            "write a python script that renames my photos by date": "claude",
            "why does my waybar config not load?": "claude",
            "explain how hyprland window rules work": "claude",
            "ask Claude what the best budget mechanical keyboard is": "claude",
            "use local, what's the capital of France?": "local",
            "what's the capital of France?": "local",
            "tell me a story about a dragon who lived on a mountain and guarded a library": "claude",
            "remind me to sign Sky up at the vets": "claude",
            "add to my diary that today was good": "claude",
            "open my notebook": "local",
            "what's the weather in Leeds tomorrow?": "claude",
            "search for cheap flights to Spain": "claude",
            "what's the latest news?": "claude",
            "go to the vets website in your browser and find their phone number": "claude",
        }
        for text, want in cases.items():
            self.assertEqual(choose(text, "auto", True), want, text)

    def test_short_answers_stay_with_the_brain_that_asked(self):
        router = Router(object(), object(), "auto")
        claude = router.claude
        run(router.select("remind me to sign Sky up at the vets"))
        self.assertIs(router.current, claude)
        run(router.select("today at 6 o'clock", previous="What time should I remind you?"))
        self.assertIs(router.current, claude)
        run(router.select("today at 6 o'clock", previous="Done, it's set."))
        self.assertIs(router.current, router.local)

    def test_switching_brains_by_voice(self):
        from unittest import mock
        from cobrad import hands
        from cobrad.hands import ToolError, brain
        hands.load_all()
        fake = NS(agent=NS(brain=Router(object(), object(), "auto")), info={})
        async def hello():
            pass
        fake.announce_hello = hello
        with mock.patch.object(brain, "server", fake), \
                mock.patch("cobrad.settings.set_toml") as saved:
            self.assertIn("thinking with Claude", run(hands.run("brain_mode", {"mode": "claude"})))
            self.assertEqual(fake.agent.brain.mode, "claude")
            saved.assert_called_once()
            fake.agent.brain.claude = None
            with self.assertRaises(ToolError):
                run(hands.run("brain_mode", {"mode": "claude"}))

    def test_the_routing_phrase_is_removed(self):
        self.assertEqual(strip_choice("ask Claude: why do snakes flick their tongues"),
                         "Why do snakes flick their tongues")
        self.assertEqual(strip_choice("use local, what's the time?"), "What's the time?")
        self.assertEqual(strip_choice("ask claude to write a poem"), "Write a poem")
        self.assertEqual(strip_choice("what's the weather"), "what's the weather")
        self.assertEqual(strip_choice("ask Claude"), "ask Claude")  # nothing else: keep it

    def test_modes_and_no_key(self):
        self.assertEqual(choose("write a script", "local", True), "local")
        self.assertEqual(choose("what's my battery?", "claude", True), "claude")
        self.assertEqual(choose("write a script", "auto", False), "local")
        self.assertEqual(choose("write a script", "claude", False), "local")


if __name__ == "__main__":
    unittest.main()
