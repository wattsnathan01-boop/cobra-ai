"""The think → use tools → answer loop, with conversation history."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Awaitable, Callable

from .. import hands
from ..gate import Confirm, Gate
from .memory import SUMMARY_PROMPT, Memory, as_text
from .ollama import BrainError

Emit = Callable[[dict], Awaitable[None]]
log = logging.getLogger(__name__)

# Saying she did (or is about to do) something, in a reply where no tool ran: nothing happened.
_CLAIM = re.compile(
    r"\b(i(?:'ll| will| shall) (?:remember|check|look|set|open|send|save|note|get|do that)"
    r"|i(?:'ve| have) (?:remembered|saved|set|opened|sent|launched|closed|turned|changed|"
    r"checked|noted|started|stopped|increased|decreased|muted|paused)"
    r"|one moment|just a moment|let me (?:check|look|see|find))\b", re.IGNORECASE)
NUDGE = ("You just said you'd do, or did, something, but you didn't call a tool, so nothing "
         "happened. If one of your tools can do it, call it now. If not, tell the person plainly "
         "that you can't do it.")


class Agent:
    def __init__(self, brain, gate: Gate, persona: str, max_steps: int = 8,
                 history_turns: int = 12, memory: Memory | None = None):
        self.brain = brain
        self.gate = gate
        self.persona = persona
        self.max_steps = max_steps
        self.history_turns = history_turns
        self.memory = memory
        # pick up where we left off (if it wasn't long ago)
        self.history: list[dict] = memory.recent(history_turns) if memory else []
        self._summarising: asyncio.Task | None = None
        # extra lines for the system prompt that change with state (e.g. watching the screen)
        self.context: Callable[[], str] | None = None

    def reset(self) -> None:
        self.history.clear()
        if self.memory:
            self.memory.new_conversation()

    def _system(self) -> dict:
        now = time.strftime("%A %d %B %Y, %H:%M")
        extra = self.context() if self.context else ""
        remembered = self.memory.prompt() if self.memory else ""
        return {"role": "system",
                "content": f"{self.persona}\n\nCurrent local time: {now}.{extra}{remembered}"}

    async def ask(self, text: str, emit: Emit, confirm: Confirm | None) -> str:
        turn = [{"role": "user", "content": text}]
        tools = hands.schemas()
        reply = ""
        used_tools = False
        nudged_at: int | None = None  # where in `turn` an empty claim was caught

        for _ in range(self.max_steps):
            reply, calls = "", []
            await emit({"type": "state", "state": "thinking"})
            try:
                async for ev in self.brain.chat([self._system(), *self.history, *turn], tools):
                    if ev["type"] == "text":
                        if not reply:
                            await emit({"type": "state", "state": "speaking"})
                        reply += ev["text"]
                        await emit({"type": "delta", "text": ev["text"]})
                    elif ev["type"] == "tool_calls":
                        calls = ev["calls"]
            except BrainError as e:
                await emit({"type": "error", "message": str(e)})
                return ""

            turn.append(self.brain.assistant_message(reply, calls))
            if not calls and not used_tools and nudged_at is None and _CLAIM.search(reply):
                log.info("caught a claim with no tool behind it: %r", reply[:120])
                nudged_at = len(turn) - 1
                turn.append({"role": "system", "content": NUDGE})
                await emit({"type": "delta", "text": " "})
                continue
            if not calls:
                break
            used_tools = True

            for call in calls:
                name, args = call["name"], call["arguments"]
                await emit({"type": "tool", "name": name, "args": args, "status": "checking"})
                started = time.monotonic()
                try:
                    # what the call would do (a diff, a command); a bad call fails right here
                    preview = await hands.make_preview(name, args)
                    allowed, reason = await self.gate.check(name, args, confirm, preview)
                except hands.ToolError as e:
                    allowed, reason, preview = False, str(e), None
                if not allowed and self.gate.level(name) == "never":
                    await emit({"type": "blocked", "tool": name, "args": args, "preview": preview})
                if not allowed:
                    result, ok = f"Not done: {reason}.", False
                else:
                    await emit({"type": "tool", "name": name, "args": args, "status": "running"})
                    try:
                        result, ok = await hands.run(name, args), True
                    except hands.ToolError as e:
                        result, ok = f"Error: {e}", False
                    except TypeError as e:
                        result, ok = f"Error: bad arguments ({e})", False
                    self.gate.log_result(name, ok, result)
                await emit({"type": "tool", "name": name, "args": args,
                            "status": "done" if ok else "failed", "result": result,
                            "ms": round((time.monotonic() - started) * 1000)})
                turn.append(self.brain.tool_message(name, result))
        else:
            await emit({"type": "error", "message": "stopped after too many tool steps"})

        if nudged_at is not None:
            # don't keep the empty claim: she copies her own earlier replies
            del turn[nudged_at:nudged_at + 2]
        self.history.extend(turn)
        if self.memory:
            self.memory.record(turn)
        dropped = self._trim()
        if dropped and self.memory:
            self._summarising = asyncio.create_task(self._summarise(dropped, self._summarising))
        return reply

    def _trim(self) -> list[dict]:
        """Keep the last history_turns exchanges; return what fell off the front."""
        users = [i for i, m in enumerate(self.history) if m["role"] == "user"]
        if len(users) <= self.history_turns:
            return []
        cut = users[-self.history_turns]
        dropped, self.history = self.history[:cut], self.history[cut:]
        return dropped

    async def _summarise(self, dropped: list[dict], previous: asyncio.Task | None) -> None:
        """Fold turns that no longer fit into the conversation's running summary."""
        if previous and not previous.done():  # one at a time, in order
            await asyncio.wait([previous])
        prompt = SUMMARY_PROMPT.format(summary=self.memory.summary() or "(none yet)",
                                       text=as_text(dropped))
        text = ""
        try:
            async for ev in self.brain.chat([{"role": "user", "content": prompt}], []):
                if ev["type"] == "text":
                    text += ev["text"]
        except Exception:
            log.exception("summarising failed; keeping the old summary")
            return
        if text.strip():
            self.memory.set_summary(text.strip()[:1200])
