"""Cloud brain: Claude through the official Anthropic SDK, streamed, with tool calling.

The agent keeps one conversation format (Ollama's: tool_calls / role "tool"); this module
translates it for the Messages API. Things that matter here:

- Her instructions (persona + tools) are frozen and cached, so repeat questions are cheap.
  What changes per question (time, remembered facts, watching state) goes in a system
  message right after the question instead.
- Claude Opus 5.5 always thinks, and its thinking blocks are bound to the exact conversation
  they came from. Cobra trims and retries conversations, so thinking is kept only within the
  current question's tool steps; earlier turns go back without it. `drop_block` is a safety
  net: anything that still doesn't match is dropped instead of failing the request.
- A request Claude's safety classifiers decline is retried server-side on another Claude
  model (`fallbacks: "default"`).
- Web search and web fetch are Anthropic's server tools: Claude runs them itself and the
  results come back in the same reply. A long search can pause the turn (`pause_turn`); the
  paused reply is sent back unchanged to carry on. Search results are kept only for the current
  question, so later questions don't pay to resend them.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator, Callable

from .ollama import BrainError

log = logging.getLogger(__name__)

BETAS = ["server-side-fallback-2026-07-01", "thinking-binding-controls-2026-08-01"]
# $ per million tokens: input, output, cache read, cache write (5-minute)
PRICES = {"claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
          "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125)}


SEARCH_PRICE = 0.01  # $ per web search ($10 per 1,000); fetching pages costs only tokens
# Anthropic's server tools: the web, searched and read by Claude itself
WEB_TOOLS = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5},
             {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 5}]
MAX_PAUSES = 4
# blocks of earlier questions that are worth resending (thinking and search results aren't)
OLD_TURN_BLOCKS = ("text", "tool_use")


def cost(model: str, usage) -> float:
    p_in, p_out, p_read, p_write = PRICES.get(model, PRICES["claude-opus-5-5"])
    server = getattr(usage, "server_tool_use", None)
    searches = (getattr(server, "web_search_requests", 0) or 0) if server else 0
    return ((usage.input_tokens or 0) * p_in + (usage.output_tokens or 0) * p_out
            + (getattr(usage, "cache_read_input_tokens", 0) or 0) * p_read
            + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * p_write) / 1e6 \
        + searches * SEARCH_PRICE


def to_tools(schemas: list[dict]) -> list[dict]:
    return [{"name": s["function"]["name"], "description": s["function"]["description"],
             "input_schema": s["function"]["parameters"]} for s in schemas]


def _old_turn(blocks: list[dict]) -> list[dict]:
    """An earlier question's reply, slimmed down: text and tool calls, plus a note of what she
    searched for (without it she later thinks she made those answers up)."""
    used = [f"searched \"{b['input']['query']}\"" if b.get("name") == "web_search"
            else f"read {b['input']['url']}"
            for b in blocks if b.get("type") == "server_tool_use"
            and b.get("name") in ("web_search", "web_fetch")
            and isinstance(b.get("input"), dict) and (b["input"].get("query") or b["input"].get("url"))]
    out = [{"type": "text", "text": "[" + "; ".join(dict.fromkeys(used)) + " on the web]"}] \
        if used else []
    for b in blocks:
        if b.get("type") == "text":
            out.append({"type": "text", "text": b.get("text", "")})  # (citations dropped)
        elif b.get("type") in OLD_TURN_BLOCKS:
            out.append(b)
    return out


def to_messages(messages: list[dict], context: str) -> tuple[str, list[dict]]:
    """(system prompt, Messages API messages) from the agent's conversation."""
    system = messages[0]["content"] if messages and messages[0]["role"] == "system" else ""
    rest = messages[1:] if system else list(messages)
    # the current question: the last plain user message (tool results are role "tool")
    current = max((i for i, m in enumerate(rest) if m["role"] == "user"), default=0)
    out: list[dict] = []
    pending: list[str] = []  # tool_use ids still waiting for their results, in order

    def add(role: str, content) -> None:
        if role == "user" and out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list) \
                and isinstance(content, list):
            out[-1]["content"].extend(content)  # tool results for one turn go together
        else:
            out.append({"role": role, "content": content})

    for i, m in enumerate(rest):
        role = m["role"]
        if role == "user":
            add("user", m["content"])
            if i == current and context:
                out.append({"role": "system", "content": context})
        elif role == "assistant":
            blocks = m.get("claude_blocks")
            if blocks:
                keep = i > current  # thinking and searches only within the current question
                content = blocks if keep else _old_turn(blocks)
                pending = [b["id"] for b in blocks if b.get("type") == "tool_use"]
            else:  # a turn the local brain answered
                content = [{"type": "text", "text": m["content"]}] if m.get("content") else []
                pending = []
                for k, call in enumerate(m.get("tool_calls") or []):
                    fn = call.get("function", call)
                    cid = call.get("id") or f"toolu_local_{i}_{k}"
                    content.append({"type": "tool_use", "id": cid, "name": fn["name"],
                                    "input": fn.get("arguments") or {}})
                    pending.append(cid)
            if content:
                add("assistant", content)
        elif role == "tool":
            cid = m.get("tool_call_id") or (pending.pop(0) if pending else None)
            if cid in pending:
                pending.remove(cid)
            if cid:
                add("user", [{"type": "tool_result", "tool_use_id": cid,
                              "content": str(m.get("content", ""))}])
        elif role == "system":
            # a note to her mid-question (from the agent's honesty checks). A system message
            # has to follow a user turn, so after one of her replies it goes in as a user note.
            if out and out[-1]["role"] == "system":
                out[-1]["content"] += "\n\n" + m["content"]
            elif out and out[-1]["role"] == "user":
                out.append({"role": "system", "content": m["content"]})
            else:
                add("user", f"[Note from Cobra's system] {m['content']}")
    return system, out


class ClaudeBrain:
    name = "claude"

    def __init__(self, api_key: str, model: str = "claude-opus-5-5", effort: str = "low",
                 on_usage: Callable[[str, float], None] | None = None, client=None,
                 web: bool = True):
        if client is None:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=api_key, timeout=90, max_retries=2)
        self.client = client
        self.model = model
        self.effort = effort
        self.on_usage = on_usage
        self.web = web  # web search + fetch
        self._blocks: list[dict] = []

    async def ping(self) -> bool:
        try:
            await self.client.models.retrieve(self.model)
            return True
        except Exception as e:
            log.warning("Claude isn't reachable: %s", e)
            return False

    async def chat(self, messages: list[dict], tools: list[dict],
                   context: str = "") -> AsyncIterator[dict]:
        import anthropic
        system, msgs = to_messages(messages, context)
        self._blocks = []
        blocks: list = []  # this reply's content, across pauses
        for _ in range(MAX_PAUSES + 1):
            final = None
            async for ev in self._stream(anthropic, system, msgs, tools):
                if ev["type"] == "final":
                    final = ev["message"]
                else:
                    yield ev
            if self.on_usage:
                try:
                    model = final.model or self.model
                    self.on_usage(model, cost(model, final.usage))
                except Exception:
                    log.exception("recording Claude usage failed")
            if final.stop_reason == "refusal":
                yield {"type": "text", "text": "Sorry, I can't help with that one."}
                return
            blocks += final.content
            if final.stop_reason != "pause_turn":
                break
            # a long search paused the turn: send what she has so far back to carry on
            msgs = msgs + [{"role": "assistant",
                            "content": [b.to_dict(exclude_none=True) for b in final.content]}]
        self._blocks = [b.to_dict(exclude_none=True) for b in blocks]
        calls = [{"name": b.name, "arguments": dict(b.input or {}), "id": b.id}
                 for b in blocks if b.type == "tool_use"]
        if calls:
            yield {"type": "tool_calls", "calls": calls}

    async def _stream(self, anthropic, system: str, msgs: list[dict], tools: list[dict]):
        """One streamed request: text events, then {"type": "final", "message"}."""
        try:
            async with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=16000,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                tools=to_tools(tools) + (WEB_TOOLS if self.web else []),
                messages=msgs,
                thinking={"type": "adaptive",
                          "block_binding": {"prefix_mismatch_behavior": "drop_block"}},
                output_config={"effort": self.effort},
                cache_control={"type": "ephemeral"},
                fallbacks="default",
                betas=BETAS,
            ) as stream:
                async for event in stream:
                    if event.type == "text" and event.text:
                        yield {"type": "text", "text": event.text}
                yield {"type": "final", "message": await stream.get_final_message()}
        except anthropic.AuthenticationError:
            raise BrainError("Claude rejected the API key; check it in Settings → Brains")
        except anthropic.PermissionDeniedError as e:
            raise BrainError(f"Claude refused access: {e.message}")
        except anthropic.RateLimitError:
            raise BrainError("Claude is rate-limiting us; try again in a minute")
        except anthropic.APIStatusError as e:
            if "credit" in str(e.message).lower() or e.status_code == 402:
                raise BrainError("the Claude account is out of credit")
            raise BrainError(f"Claude error {e.status_code}: {e.message}")
        except anthropic.APIConnectionError:
            raise BrainError("can't reach Claude (no internet?)")

    def assistant_message(self, text: str, calls: list[dict]) -> dict:
        msg: dict = {"role": "assistant", "content": text, "claude_blocks": self._blocks}
        if calls:
            msg["tool_calls"] = [{"id": c.get("id"), "function": {"name": c["name"],
                                                                  "arguments": c["arguments"]}}
                                 for c in calls]
        return msg

    @staticmethod
    def tool_message(name: str, result: str, call_id: str | None = None) -> dict:
        return {"role": "tool", "tool_name": name, "content": result, "tool_call_id": call_id}
