"""Shell commands, as you or (through pkexec and your password) as root. Both ask first."""
from __future__ import annotations

import asyncio
import os
import re
import signal
from pathlib import Path

from . import ToolError, preview, tool
from .files import tilde

MAX_OUTPUT = 4000
_SUDO = re.compile(r"(^|[;&|]\s*)(sudo|doas|su|pkexec)\b")


async def _run(argv: list[str], cwd: Path, timeout: float) -> str:
    proc = await asyncio.create_subprocess_exec(
        *argv, cwd=cwd, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT, start_new_session=True)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        os.killpg(proc.pid, signal.SIGKILL)
        await proc.wait()
        raise ToolError(f"still running after {timeout:.0f} s, so it was stopped")
    text = out.decode(errors="replace").strip()
    if len(text) > MAX_OUTPUT:
        text = "…" + text[-MAX_OUTPUT:]
    return f"exit code {proc.returncode}\n{text or '(no output)'}"


def _cwd(cwd: str | None) -> Path:
    path = Path(os.path.expanduser(cwd or "~"))
    if not path.is_dir():
        raise ToolError(f"{cwd} isn't a folder")
    return path


@preview("shell_run")
async def shell_run_preview(command: str, cwd: str | None = None) -> dict:
    if _SUDO.search(command):
        raise ToolError("that needs root; use sudo_run for it instead")
    return {"kind": "command", "command": command, "cwd": tilde(_cwd(cwd)), "tags": [],
            "say": "I'd like to run a command. It's on screen."}


@tool("shell_run",
      "Run a shell command as the person (bash). They see the exact command and must approve it. "
      "Returns the exit code and output. Not for anything needing root: use sudo_run.",
      properties={"command": {"type": "string"},
                  "cwd": {"type": "string", "description": "folder to run in; default ~"}},
      required=["command"],
      permission="ask")
async def shell_run(command: str, cwd: str | None = None) -> str:
    await shell_run_preview(command, cwd)
    return await _run(["bash", "-c", command], _cwd(cwd), timeout=60)


@preview("sudo_run")
async def sudo_run_preview(command: str) -> dict:
    tags = ["sudo", "system change"]
    if re.search(r"\b(pacman|yay|paru)\b.*\s-S", command):
        tags.append("packages")
    return {"kind": "command", "command": command, "cwd": "/", "tags": tags, "root": True,
            "say": "I'd like to run a command as root. It's on screen, and you'll be asked "
                   "for your password."}


@tool("sudo_run",
      "Run a command as root, for system changes (services, files in /etc, updates). To install "
      "software use packages_install instead. The person sees the command, must approve it, and "
      "then types their password.",
      properties={"command": {"type": "string",
                              "description": "the command without sudo in front"}},
      required=["command"],
      permission="ask")
async def sudo_run(command: str) -> str:
    command = re.sub(r"^\s*sudo\s+", "", command)
    result = await _run(["pkexec", "bash", "-c", command], Path("/"), timeout=300)
    if result.startswith(("exit code 126", "exit code 127")) and "\n(no output)" in result:
        raise ToolError("the password prompt was cancelled or failed")
    return result
