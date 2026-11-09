"""Permission gate: every tool call is checked here before it runs, and logged."""
from __future__ import annotations

import asyncio
import json
import re
import time
import tomllib
from pathlib import Path
from typing import Awaitable, Callable

from .hands import TOOLS

# Asks the person, showing the preview (what the call would do); resolves True to allow.
# Raising or timing out counts as "no".
Confirm = Callable[[str, dict, dict | None], Awaitable[bool]]

LEVELS = ("always", "ask", "never")
# never offered "Always": a standing yes to any command is too broad
NO_ALWAYS = {"shell_run", "sudo_run", "packages_install"}


class Gate:
    def __init__(self, policy: dict[str, str], audit_path: Path, confirm_timeout: float = 20,
                 user_file: Path | None = None):
        """user_file: the person's permissions.toml, where "Always" answers are saved."""
        self.policy = policy
        self.audit_path = audit_path
        self.confirm_timeout = confirm_timeout
        self.user_file = user_file

    def level(self, name: str) -> str:
        level = self.policy.get(name)
        if level not in LEVELS:
            tool = TOOLS.get(name)
            level = tool.permission if tool else "never"
        return level

    async def check(self, name: str, args: dict, confirm: Confirm | None,
                    preview: dict | None = None) -> tuple[bool, str]:
        level = self.level(name)
        if level == "always":
            return self._decide(name, args, True, "always")
        if level == "never":
            return self._decide(name, args, False, "blocked by permissions (never)")
        if confirm is None:
            return self._decide(name, args, False, "needs confirmation, but nobody can answer")
        try:
            ok = await asyncio.wait_for(confirm(name, args, preview), self.confirm_timeout)
        except asyncio.TimeoutError:
            return self._decide(name, args, False, "no answer in time, denied")
        except Exception:
            return self._decide(name, args, False, "confirmation failed, denied")
        return self._decide(name, args, ok, "you allowed it" if ok else "you denied it")

    def remember(self, name: str) -> bool:
        """Answered "Always": allow this tool from now on, and save that. False if not allowed."""
        if name in NO_ALWAYS or self.level(name) == "never":
            return False
        self.policy[name] = "always"
        self._write({"event": "remember", "tool": name, "level": "always"})
        if self.user_file is None:
            return True
        text = self.user_file.read_text(encoding="utf-8") if self.user_file.exists() else ""
        line = f'{name} = "always"'
        pattern = re.compile(rf"(?m)^\s*{re.escape(name)}\s*=.*$")
        if pattern.search(text):
            text = pattern.sub(line, text, count=1)
        elif re.search(r"(?m)^\[tools\]\s*$", text):
            text = re.sub(r"(?m)^\[tools\]\s*$", "[tools]\n" + line, text, count=1)
        else:
            text = text.rstrip() + ("\n\n" if text else "") + "[tools]\n" + line + "\n"
        tomllib.loads(text)  # never save a file that won't load
        self.user_file.parent.mkdir(parents=True, exist_ok=True)
        self.user_file.write_text(text, encoding="utf-8")
        return True

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
