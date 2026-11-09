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
# She copies her own earlier replies, including refusals from before she gained a tool.
ABILITIES_NOTE = ("Your tools are listed with this message and they're what you can do right "
                  "now. Earlier replies in this conversation may be out of date about what you "
                  "can and can't do: if a tool fits the request, use it.")
# Refusing without having tried a tool: often a copy of an old reply from before she could.
_REFUSAL = re.compile(r"\b(i (?:cannot|can't|can not|am unable to|am not able to)|i'm (?:unable|"
                      r"not able) to|i don't have (?:the ability|a way|access))\b", re.IGNORECASE)
REFUSAL_NUDGE = ("You said you can't, but you haven't tried any tool, and earlier replies may be "
                 "out of date. Check your tools: if one fits (packages_install for installing "
                 "software, shell_run for commands, files_* for files), call it now. If none "
                 "fits, tell the person plainly that you can't.")
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
        """Her standing instructions: the same on every request (so Claude can cache them)."""
        return {"role": "system", "content": f"{self.persona}\n\n{ABILITIES_NOTE}"}

    def _context(self) -> str:
        """What changes per question: the time, what she remembers, watching mode."""
        now = time.strftime("%A %d %B %Y, %H:%M")
        extra = self.context() if self.context else ""
        remembered = self.memory.prompt() if self.memory else ""
        return f"Current local time: {now}.{extra}{remembered}".strip()

    async def ask(self, text: str, emit: Emit, confirm: Confirm | None) -> str:
        if hasattr(self.brain, "select"):
            # Auto mode: local or Claude for this question ("ask Claude:" is removed)
            text = await self.brain.select(text, emit) or text
        turn = [{"role": "user", "content": text}]
        tools = hands.schemas()
        context = self._context()  # once per question, so every step sees the same
        # the honesty checks below are for the local model's habit of copying old replies
        checks = getattr(self.brain, "name", "local") != "claude"
        reply = ""
        used_tools = False
        nudged_at: int | None = None  # where in `turn` an empty claim or refusal was caught
        nudge_len = 0                 # how many entries the catch added there
        history = self.history

        for _ in range(self.max_steps):
            reply, calls = "", []
            await emit({"type": "state", "state": "thinking"})
            try:
                async for ev in self.brain.chat([self._system(), *history, *turn], tools,
                                                context):
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
            if checks and not calls and not used_tools and nudged_at is None:
                nudge = NUDGE if _CLAIM.search(reply) else \
                    REFUSAL_NUDGE if _REFUSAL.search(reply) else None
                if nudge:
                    log.info("checking a reply with no tool behind it: %r", reply[:120])
                    nudged_at = len(turn) - 1
                    if nudge is REFUSAL_NUDGE:
                        # she copies earlier replies (old refusals, or whatever answer came
                        # last), so the retry sees only this request and the note
                        history = []
                        turn[-1] = {"role": "system", "content": nudge}
                        nudge_len = 1
                    else:
                        turn.append({"role": "system", "content": nudge})
                        nudge_len = 2
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
                turn.append(self.brain.tool_message(name, result, call.get("id")))
        else:
            await emit({"type": "error", "message": "stopped after too many tool steps"})

        if nudged_at is not None:
            # don't keep the empty claim: she copies her own earlier replies
            del turn[nudged_at:nudged_at + nudge_len]
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
            # background work stays on the free local model, whichever brain is answering
            brain = getattr(self.brain, "background", self.brain)
            async for ev in brain.chat([{"role": "user", "content": prompt}], []):
                if ev["type"] == "text":
                    text += ev["text"]
        except Exception:
            log.exception("summarising failed; keeping the old summary")
            return
        if text.strip():
            self.memory.set_summary(text.strip()[:1200])
