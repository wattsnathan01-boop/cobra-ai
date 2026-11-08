"""Tool registry. Each tool module registers itself with @tool on import."""
from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from typing import Any, Callable


class ToolError(Exception):
    """A tool failed in a way worth telling the model about."""


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    func: Callable[..., Any]
    permission: str  # default when permissions.toml doesn't list it


TOOLS: dict[str, Tool] = {}


def tool(name: str, description: str, properties: dict | None = None,
         required: list[str] | None = None, permission: str = "ask"):
    def register(func):
        TOOLS[name] = Tool(
            name=name,
            description=description,
            parameters={
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
            func=func,
            permission=permission,
        )
        return func
    return register


def schemas() -> list[dict]:
    """Tool definitions in the function-calling format Ollama expects."""
    return [
        {"type": "function",
         "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
        for t in TOOLS.values()
    ]


async def run(name: str, args: dict) -> str:
    """Run a tool and return its result as text for the model."""
    t = TOOLS.get(name)
    if t is None:
        raise ToolError(f"unknown tool: {name}")
    if inspect.iscoroutinefunction(t.func):
        result = await t.func(**args)
    else:
        result = await asyncio.to_thread(t.func, **args)
    return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)


async def sh(*cmd: str, timeout: float = 10) -> str:
    """Run a command (no shell) and return stdout; raise ToolError on failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except FileNotFoundError:
        raise ToolError(f"{cmd[0]} is not installed")
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise ToolError(f"{cmd[0]} timed out")
    if proc.returncode != 0:
        raise ToolError(err.decode(errors="replace").strip() or f"{cmd[0]} failed")
    return out.decode(errors="replace").strip()


def load_all() -> None:
    from . import apps, hypr, media, system  # noqa: F401  (registers tools)
