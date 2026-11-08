"""Permission gate: every tool call is checked here before it runs, and logged."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Awaitable, Callable

from .hands import TOOLS

# Asks the person; resolves True to allow. Raising or timing out counts as "no".
Confirm = Callable[[str, dict], Awaitable[bool]]

LEVELS = ("always", "ask", "never")


class Gate:
    def __init__(self, policy: dict[str, str], audit_path: Path, confirm_timeout: float = 20):
        self.policy = policy
        self.audit_path = audit_path
        self.confirm_timeout = confirm_timeout

    def level(self, name: str) -> str:
        level = self.policy.get(name)
        if level not in LEVELS:
            tool = TOOLS.get(name)
            level = tool.permission if tool else "never"
        return level

    async def check(self, name: str, args: dict, confirm: Confirm | None) -> tuple[bool, str]:
        level = self.level(name)
        if level == "always":
            return self._decide(name, args, True, "always")
        if level == "never":
            return self._decide(name, args, False, "blocked by permissions (never)")
        if confirm is None:
            return self._decide(name, args, False, "needs confirmation, but nobody can answer")
        try:
            ok = await asyncio.wait_for(confirm(name, args), self.confirm_timeout)
        except asyncio.TimeoutError:
            return self._decide(name, args, False, "no answer in time, denied")
        except Exception:
            return self._decide(name, args, False, "confirmation failed, denied")
        return self._decide(name, args, ok, "you allowed it" if ok else "you denied it")

    def log_result(self, name: str, ok: bool, result: str) -> None:
        self._write({"event": "result", "tool": name, "ok": ok, "result": result[:500]})

    def _decide(self, name: str, args: dict, allowed: bool, reason: str) -> tuple[bool, str]:
        self._write({"event": "decision", "tool": name, "args": args,
                     "allowed": allowed, "reason": reason})
        return allowed, reason

    def _write(self, record: dict) -> None:
        record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
