import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

import httpx

from cobrad import hands
from cobrad.brain.agent import Agent
from cobrad.brain.ollama import BrainError, OllamaBrain
from cobrad.gate import Gate
from cobrad.hands.apps import match_app
from cobrad.hands.hypr import find_window

RAN: list[dict] = []


@hands.tool("echo_test", "test tool", {"word": {"type": "string"}}, ["word"], permission="always")
def echo_test(word: str) -> str:
    RAN.append({"word": word})
    return f"echo {word}"


@hands.tool("risky_test", "test tool needing confirmation", permission="ask")
def risky_test() -> str:
    RAN.append({"risky": True})
    return "did the risky thing"


class FakeBrain:
    """Plays back scripted turns; each turn is (text, calls)."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.seen: list[list[dict]] = []

    async def chat(self, messages, tools):
        self.seen.append(messages)
        text, calls = self.turns.pop(0)
        for word in text.split(" "):
            if word:
                yield {"type": "text", "text": word + " "}
        if calls:
            yield {"type": "tool_calls", "calls": calls}

    assistant_message = staticmethod(OllamaBrain.assistant_message)
    tool_message = staticmethod(OllamaBrain.tool_message)


def make_agent(turns, policy=None, history_turns=12):
    tmp = Path(tempfile.mkdtemp())
    gate = Gate(policy or {}, tmp / "audit.jsonl", confirm_timeout=0.5)
    return Agent(FakeBrain(turns), gate, "persona", history_turns=history_turns), tmp


def run(coro):
    return asyncio.run(coro)


class AgentTests(unittest.TestCase):
    def setUp(self):
        RAN.clear()
        self.events = []

    async def emit(self, ev):
        self.events.append(ev)

    def test_plain_reply_streams_and_is_returned(self):
        agent, _ = make_agent([("Hello there", None)])
        reply = run(agent.ask("hi", self.emit, None))
        self.assertEqual(reply.strip(), "Hello there")
        self.assertIn({"type": "state", "state": "speaking"}, self.events)
        self.assertEqual(len(agent.history), 2)

    def test_allowed_tool_runs_and_result_goes_back(self):
        agent, tmp = make_agent([("", [{"name": "echo_test", "arguments": {"word": "hiss"}}]),
                                 ("Done", None)])
        reply = run(agent.ask("say hiss", self.emit, None))
        done = next(e for e in self.events if e["type"] == "tool" and e["status"] == "done")
        self.assertIsInstance(done["ms"], int)
        self.assertEqual(RAN, [{"word": "hiss"}])
        self.assertEqual(reply.strip(), "Done")
        last_call = agent.brain.seen[1][-1]
        self.assertEqual(last_call, {"role": "tool", "tool_name": "echo_test",
                                     "content": "echo hiss"})
        audit = [json.loads(l) for l in (tmp / "audit.jsonl").read_text().splitlines()]
        self.assertEqual([a["event"] for a in audit], ["decision", "result"])

    def test_ask_tool_denied_does_not_run(self):
        async def say_no(tool, args, preview=None):
            return False
        agent, _ = make_agent([("", [{"name": "risky_test", "arguments": {}}]), ("Okay", None)])
        run(agent.ask("do it", self.emit, say_no))
        self.assertEqual(RAN, [])
        self.assertIn("you denied it", agent.brain.seen[1][-1]["content"])

    def test_ask_tool_allowed_runs(self):
        async def say_yes(tool, args, preview=None):
            return True
        agent, _ = make_agent([("", [{"name": "risky_test", "arguments": {}}]), ("Done", None)])
        run(agent.ask("do it", self.emit, say_yes))
        self.assertEqual(RAN, [{"risky": True}])

    def test_ask_with_nobody_to_answer_is_denied(self):
        agent, _ = make_agent([("", [{"name": "risky_test", "arguments": {}}]), ("Okay", None)])
        run(agent.ask("do it", self.emit, None))
        self.assertEqual(RAN, [])

    def test_confirm_timeout_denies(self):
        async def never_answers(tool, args, preview=None):
            await asyncio.sleep(10)
        agent, _ = make_agent([("", [{"name": "risky_test", "arguments": {}}]), ("Okay", None)])
        run(agent.ask("do it", self.emit, never_answers))
        self.assertEqual(RAN, [])
        self.assertIn("no answer in time", agent.brain.seen[1][-1]["content"])

    def test_policy_never_overrides_tool_default(self):
        agent, _ = make_agent([("", [{"name": "echo_test", "arguments": {"word": "x"}}]),
                               ("No", None)], policy={"echo_test": "never"})
        run(agent.ask("echo", self.emit, None))
        self.assertEqual(RAN, [])

    def test_unknown_tool_is_blocked(self):
        agent, _ = make_agent([("", [{"name": "rm_rf", "arguments": {}}]), ("Hm", None)])
        run(agent.ask("x", self.emit, None))
        self.assertIn("never", agent.brain.seen[1][-1]["content"])

    def test_bad_arguments_reported_not_crashed(self):
        agent, _ = make_agent([("", [{"name": "echo_test", "arguments": {"nope": 1}}]),
                               ("Oops", None)])
        run(agent.ask("x", self.emit, None))
        self.assertIn("bad arguments", agent.brain.seen[1][-1]["content"])

    def test_claiming_an_action_without_a_tool_gets_corrected(self):
        agent, _ = make_agent([("I've saved that for you", None),           # empty claim
                               ("", [{"name": "echo_test", "arguments": {"word": "x"}}]),
                               ("Saved", None)])
        reply = run(agent.ask("save it", self.emit, None))
        self.assertEqual(RAN, [{"word": "x"}])
        self.assertEqual(reply.strip(), "Saved")
        # the empty claim isn't kept, so she can't copy it later
        self.assertNotIn("I've saved that", " ".join(m["content"] for m in agent.history))

    def test_a_copied_refusal_gets_a_second_look_without_the_old_refusals(self):
        agent, _ = make_agent([("I cannot do that", None),                       # copied refusal
                               ("", [{"name": "echo_test", "arguments": {"word": "y"}}]),
                               ("Done", None)])
        agent.history = [{"role": "user", "content": "do it"},
                         {"role": "assistant", "content": "I cannot do that"}]
        run(agent.ask("do it", self.emit, None))
        self.assertEqual(RAN, [{"word": "y"}])
        retry = agent.brain.seen[1]
        self.assertFalse(any("I cannot" in (m.get("content") or "") for m in retry))
        # only the system prompt, this request and the note: nothing earlier to copy
        self.assertEqual([m["role"] for m in retry], ["system", "user", "system"])

    def test_a_real_refusal_still_comes_through(self):
        agent, _ = make_agent([("I can't set timers", None), ("I can't set timers, sorry", None)])
        reply = run(agent.ask("set a timer", self.emit, None))
        self.assertIn("can't", reply)
        self.assertEqual(RAN, [])

    def test_honest_replies_are_left_alone(self):
        agent, _ = make_agent([("Paris is the capital", None)])
        run(agent.ask("capital of France?", self.emit, None))
        self.assertEqual(len(agent.brain.seen), 1)

    def test_history_is_trimmed_to_recent_turns(self):
        agent, _ = make_agent([(f"r{i}", None) for i in range(5)], history_turns=2)
        for i in range(5):
            run(agent.ask(f"q{i}", self.emit, None))
        users = [m["content"] for m in agent.history if m["role"] == "user"]
        self.assertEqual(users, ["q3", "q4"])


def ndjson(*chunks):
    return "\n".join(json.dumps(c) for c in chunks) + "\n"


class OllamaTests(unittest.TestCase):
    def brain(self, handler):
        return OllamaBrain("http://ollama", "qwen3:8b", transport=httpx.MockTransport(handler))

    def collect(self, brain):
        async def go():
            return [ev async for ev in brain.chat([{"role": "user", "content": "hi"}], [])]
        return run(go())

    def test_streams_text_and_tool_calls(self):
        body = ndjson(
            {"message": {"role": "assistant", "content": "Checking"}, "done": False},
            {"message": {"role": "assistant", "content": "",
                         "tool_calls": [{"function": {"name": "system_stats", "arguments": {}}}]},
             "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": True})
        seen = {}

        def handler(req):
            seen.update(json.loads(req.content))
            return httpx.Response(200, text=body)

        events = self.collect(self.brain(handler))
        self.assertEqual(events[0], {"type": "text", "text": "Checking"})
        self.assertEqual(events[-1], {"type": "tool_calls",
                                      "calls": [{"name": "system_stats", "arguments": {}}]})
        self.assertEqual(seen["model"], "qwen3:8b")
        self.assertFalse(seen["think"])
        self.assertTrue(seen["stream"])

    def test_error_chunk_raises(self):
        b = self.brain(lambda req: httpx.Response(200, text=ndjson({"error": "model not found"})))
        with self.assertRaises(BrainError):
            self.collect(b)

    def test_http_error_raises(self):
        b = self.brain(lambda req: httpx.Response(404, text="nope"))
        with self.assertRaises(BrainError):
            self.collect(b)


class MatchingTests(unittest.TestCase):
    clients = [
        {"address": "0x1", "class": "kitty", "title": "~/dots"},
        {"address": "0x2", "class": "google-chrome", "title": "YouTube - Google Chrome"},
        {"address": "0x3", "class": "kitty-scratch", "title": "notes"},
    ]

    def test_exact_class_beats_partial(self):
        self.assertEqual(find_window(self.clients, "Kitty")["address"], "0x1")

    def test_title_match(self):
        self.assertEqual(find_window(self.clients, "youtube")["address"], "0x2")

    def test_no_match_raises(self):
        with self.assertRaises(hands.ToolError):
            find_window(self.clients, "steam")

    def test_app_matching(self):
        apps = {"google chrome": "google-chrome", "thunar file manager": "thunar"}
        self.assertEqual(match_app(apps, "chrome"), ("google chrome", "google-chrome"))
        self.assertEqual(match_app(apps, "thunar")[1], "thunar")
        with self.assertRaises(hands.ToolError):
            match_app(apps, "photoshop")


class RegistryTests(unittest.TestCase):
    def test_real_tools_register_with_valid_schemas(self):
        hands.load_all()
        names = {s["function"]["name"] for s in hands.schemas()}
        for expected in ["system_stats", "hypr_windows", "hypr_action", "hypr_close",
                         "media", "volume", "brightness", "apps_launch"]:
            self.assertIn(expected, names)
        for s in hands.schemas():
            params = s["function"]["parameters"]
            self.assertEqual(params["type"], "object")
            for r in params["required"]:
                self.assertIn(r, params["properties"])


@unittest.skipIf(sys.platform == "win32", "Unix sockets: run on Linux")
class BusTests(unittest.TestCase):
    def test_ask_round_trip_with_confirm(self):
        from cobrad.bus import Server

        async def go():
            tmp = Path(tempfile.mkdtemp())
            agent, _ = make_agent([("", [{"name": "risky_test", "arguments": {}}]),
                                   ("All done", None)])
            server = Server(agent, tmp / "cobra.sock")
            await server.start()
            reader, writer = await asyncio.open_unix_connection(str(tmp / "cobra.sock"))
            writer.write(json.dumps({"type": "ask", "text": "go"}).encode() + b"\n")
            events = []
            async for line in reader:
                ev = json.loads(line)
                events.append(ev)
                if ev["type"] == "confirm":
                    writer.write(json.dumps({"type": "confirm_reply",
                                             "confirm_id": ev["confirm_id"],
                                             "allow": True}).encode() + b"\n")
                if ev["type"] == "state" and ev["state"] == "idle":
                    break
            writer.close()
            await server.close()
            return events

        RAN.clear()
        events = run(go())
        kinds = [e["type"] for e in events]
        self.assertIn("confirm", kinds)
        self.assertEqual(RAN, [{"risky": True}])
        done = next(e for e in events if e["type"] == "done")
        self.assertEqual(done["text"].strip(), "All done")


if __name__ == "__main__":
    unittest.main()
