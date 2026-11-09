"""Finding and installing software: pacman for the Arch repos, yay for the AUR.

Installing always asks first: the card lists every package with its version, source and size,
then your normal password prompt appears (pkexec). AUR packages are flagged, because their
build scripts are written by other users and run on this machine.
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
from pathlib import Path

from . import ToolError, preview, tool
from .shell import _run

_NAME = re.compile(r"^[a-z0-9@._+-]+$")
_ENV = {**os.environ, "LC_ALL": "C"}


async def _c(*cmd: str, timeout: float = 30) -> str:
    """A command with English output (so it can be parsed)."""
    proc = await asyncio.create_subprocess_exec(*cmd, env=_ENV, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.PIPE)
    out, err = await asyncio.wait_for(proc.communicate(), timeout)
    if proc.returncode != 0:
        raise ToolError(err.decode(errors="replace").strip() or f"{cmd[0]} failed")
    return out.decode(errors="replace")


def _fields(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() and not key.startswith(" "):
            out.setdefault(key.strip(), value.strip())
    return out


async def _info(name: str) -> dict | None:
    """Repo info for a package, else AUR info, else None."""
    try:
        f = _fields(await _c("pacman", "-Si", "--", name))
        return {"name": f.get("Name", name), "version": f.get("Version", "?"),
                "source": f.get("Repository", "repo"), "size": f.get("Download Size", "")}
    except ToolError:
        pass
    if shutil.which("yay"):
        try:
            f = _fields(await _c("yay", "-Si", "--aur", "--", name))
            if f.get("Name"):
                return {"name": f["Name"], "version": f.get("Version", "?"), "source": "aur",
                        "size": ""}
        except ToolError:
            pass
    return None


async def _installed(name: str) -> str | None:
    try:
        return (await _c("pacman", "-Q", "--", name)).split()[1]
    except (ToolError, IndexError):
        return None


@tool("packages_search",
      "Search for software to install, in the Arch repositories (and the AUR if nothing "
      "matches). Use it to find the right package name before installing.",
      properties={"query": {"type": "string"}},
      required=["query"],
      permission="always")
async def packages_search(query: str) -> str:
    try:
        out = await _c("pacman", "-Ss", "--", query)
    except ToolError:
        out = ""
    results = []
    lines = out.splitlines()
    for i, line in enumerate(lines):
        if line and not line.startswith(" "):
            m = re.match(r"(\S+)/(\S+) (\S+)(.*)", line)
            if m:
                desc = lines[i + 1].strip() if i + 1 < len(lines) else ""
                installed = " [installed]" if "[installed" in m.group(4) else ""
                results.append(f"{m.group(2)} {m.group(3)} ({m.group(1)}){installed}: {desc}")
    if not results and shutil.which("yay"):
        try:
            aur = (await _c("yay", "-Ss", "--aur", "--", query, timeout=40)).splitlines()
            for i, line in enumerate(aur):
                m = re.match(r"aur/(\S+) (\S+)", line)
                if m:
                    desc = aur[i + 1].strip() if i + 1 < len(aur) else ""
                    results.append(f"{m.group(1)} {m.group(2)} (AUR): {desc}")
        except ToolError:
            pass
    if not results:
        return f"no packages found for '{query}'"
    more = f"\n… and {len(results) - 12} more" if len(results) > 12 else ""
    return "\n".join(results[:12]) + more


async def _plan(packages: list[str]) -> list[dict]:
    if isinstance(packages, str):
        packages = packages.replace(",", " ").split()
    names = list(dict.fromkeys(p.strip().lower() for p in packages if p.strip()))
    if not names:
        raise ToolError("which packages?")
    plan = []
    for name in names:
        if not _NAME.match(name):
            raise ToolError(f"'{name}' isn't a valid package name")
        info = await _info(name)
        if info is None:
            raise ToolError(f"there's no package called '{name}'; search with packages_search")
        info["installed"] = await _installed(info["name"])
        plan.append(info)
    if all(p["installed"] for p in plan):
        raise ToolError("already installed: " + ", ".join(f"{p['name']} {p['installed']}"
                                                            for p in plan))
    return plan


@preview("packages_install")
async def packages_install_preview(packages: list[str]) -> dict:
    plan = await _plan(packages)
    new = [p for p in plan if not p["installed"]]
    aur = [p for p in new if p["source"] == "aur"]
    tags = ["sudo", "packages"] + (["AUR"] if aur else [])
    names = " ".join(p["name"] for p in new)
    return {
        "kind": "packages",
        "packages": plan,
        "command": f"{'yay' if aur else 'pacman'} -S --needed {names}",
        "tags": tags,
        "root": True,
        "warning": ("AUR packages are built from scripts written by other users, and those "
                    "scripts run on this machine." if aur else ""),
        "say": f"I'd like to install {', '.join(p['name'] for p in new)}. It's on screen, and "
               f"then you'll be asked for your password.",
    }


@tool("packages_install",
      "Install software (Arch packages, or AUR packages if they're not in the repositories). "
      "The person sees the list, approves it and types their password. Find exact names with "
      "packages_search first if you're not sure.",
      properties={"packages": {"type": "array", "items": {"type": "string"},
                               "description": "exact package names"}},
      required=["packages"],
      permission="ask")
async def packages_install(packages: list[str]) -> str:
    plan = await _plan(packages)
    new = [p["name"] for p in plan if not p["installed"]]
    if any(p["source"] == "aur" for p in plan if not p["installed"]):
        argv = ["yay", "-S", "--needed", "--noconfirm", "--sudo", "pkexec",
                "--answerclean", "None", "--answerdiff", "None", "--answeredit", "None", "--", *new]
        cwd = Path.home()
    else:
        argv = ["pkexec", "pacman", "-S", "--needed", "--noconfirm", "--", *new]
        cwd = Path("/")
    output = await _run(argv, cwd, timeout=1200)
    done = {n: await _installed(n) for n in new}
    if not all(done.values()):
        missing = ", ".join(n for n, v in done.items() if not v)
        if output.startswith(("exit code 126", "exit code 127")):
            raise ToolError("the password prompt was cancelled, so nothing was installed")
        raise ToolError(f"{missing} didn't install:\n{output[-1500:]}")
    return "installed " + ", ".join(f"{n} {v}" for n, v in done.items())
