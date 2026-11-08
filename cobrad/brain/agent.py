"""The think → use tools → answer loop, with conversation history."""
from __future__ import annotations

import time
from typing import Awaitable, Callable

from .. import hands
from ..gate import Confirm, Gate
from .ollama import BrainError

Emit = Callable[[dict], Awaitable[None]]


class Agent:
    def __init__(self, brain, gate: Gate, persona: str, max_steps: int = 8,
                 history_turns: int = 12):
        self.brain = brain
        self.gate = gate
        self.persona = persona
        self.max_steps = max_steps
        self.history_turns = history_turns
        self.history: list[dict] = []

    def reset(self) -> None:
        self.history.clear()

    def _system(self) -> dict:
        now = time.strftime("%A %d %B %Y, %H:%M")
        return {"role": "system", "content": f"{self.persona}\n\nCurrent local time: {now}."}

    async def ask(self, text: str, emit: Emit, confirm: Confirm | None) -> str:
        turn = [{"role": "user", "content": text}]
        tools = hands.schemas()
        reply = ""

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
            if not calls:
                break

            for call in calls:
                name, args = call["name"], call["arguments"]
                await emit({"type": "tool", "name": name, "args": args, "status": "checking"})
                allowed, reason = await self.gate.check(name, args, confirm)
                started = time.monotonic()
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

        self.history.extend(turn)
        self._trim()
        return reply

    def _trim(self) -> None:
        users = [i for i, m in enumerate(self.history) if m["role"] == "user"]
        if len(users) > self.history_turns:
            self.history = self.history[users[-self.history_turns]:]
