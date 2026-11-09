"""Tools from other apps over MCP (Model Context Protocol), e.g. Pencil's design canvas.

Servers are listed in ~/.config/cobra/mcp.json, in the usual format:

    {"mcpServers": {"pencil": {"command": "/path/to/server", "args": ["--app", "x"], "env": {}}}}

(a single {"name": ..., "command": ...} object, or a list of them, works too). Each server's
tools become Cobra tools named "<server>__<tool>". They go through the permission gate like any
other: tools the server marks read-only run straight away, the rest ask first. Change that per
tool in permissions.toml. What comes back from a server is information, not instructions.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from contextlib import AsyncExitStack
from pathlib import Path

from . import TOOLS, Tool, ToolError

log = logging.getLogger(__name__)

MAX_RESULT_CHARS = 30000
RETRY_SECONDS = 60

servers: dict[str, "Server"] = {}


def load_config(path: Path) -> dict[str, dict]:
    """{name: {"command", "args", "env"}} from mcp.json (missing file: nothing)."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "mcpServers" in data:
        entries = data["mcpServers"]
    elif isinstance(data, dict) and "name" in data:
        entries = {data["name"]: data}
    elif isinstance(data, list):
        entries = {d["name"]: d for d in data}
    else:
        entries = data
    out = {}
    for name, cfg in entries.items():
        if cfg.get("transport", "stdio") != "stdio" or not cfg.get("command"):
            log.warning("MCP server %s: only local (stdio) servers are supported", name)
            continue
        out[name] = {"command": cfg["command"], "args": list(cfg.get("args") or []),
                     "env": dict(cfg.get("env") or {})}
    return out


def tool_name(server: str, tool: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", f"{server}__{tool}")[:64]


def as_text(result) -> str:
    parts = []
    for c in result.content or []:
        if getattr(c, "type", "") == "text":
            parts.append(c.text)
        else:
            parts.append(f"[{getattr(c, 'type', 'content')}]")
    text = "\n".join(parts).strip() or "(no output)"
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + f"\n… (cut off; {len(text)} characters in all)"
    return text


class Server:
    """One MCP server, kept running by its own task (the SDK's context managers must be
    entered and left in the same task)."""

    def __init__(self, name: str, cfg: dict):
        self.name = name
        self.cfg = cfg
        self.session = None
        self.ready = asyncio.Event()
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self.error = ""

    def start(self) -> None:
        if self._task is None or self._task.done():
            self.ready.clear()
            self._stop.clear()
            self._task = asyncio.create_task(self._run(), name=f"mcp-{self.name}")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, 5)
            except (asyncio.TimeoutError, Exception):
                self._task.cancel()

    async def _run(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        while not self._stop.is_set():
            try:
                async with AsyncExitStack() as stack:
                    params = StdioServerParameters(command=self.cfg["command"],
                                                   args=self.cfg["args"],
                                                   env=self.cfg["env"] or None)
                    read, write = await stack.enter_async_context(stdio_client(params))
                    session = await stack.enter_async_context(ClientSession(read, write))
                    await session.initialize()
                    self._register((await session.list_tools()).tools)
                    self.session, self.error = session, ""
                    self.ready.set()
                    log.info("MCP server %s connected", self.name)
                    await self._stop.wait()
            except Exception as e:  # can't start, or it died (e.g. the app was closed)
                self.error = str(e) or type(e).__name__
                log.warning("MCP server %s unavailable: %s", self.name, self.error)
            finally:
                self.session = None
                self.ready.clear()
            if not self._stop.is_set():
                try:
                    await asyncio.wait_for(self._stop.wait(), RETRY_SECONDS)
                except asyncio.TimeoutError:
                    pass

    def _register(self, tools) -> None:
        for t in tools:
            name = tool_name(self.name, t.name)
            read_only = bool(t.annotations and t.annotations.read_only_hint)
            TOOLS[name] = Tool(
                name=name,
                description=f"[{self.name}] {t.description or t.name}",
                parameters=t.input_schema or {"type": "object", "properties": {}},
                func=self._caller(t.name),
                permission="always" if read_only else "ask",
            )

    def _caller(self, tool: str):
        async def call(**args):
            if self.session is None:
                self.start()
                try:
                    await asyncio.wait_for(self.ready.wait(), 15)
                except asyncio.TimeoutError:
                    raise ToolError(f"{self.name} isn't running (is the app open?)"
                                    + (f": {self.error}" if self.error else ""))
            try:
                result = await asyncio.wait_for(self.session.call_tool(tool, args), 180)
            except asyncio.TimeoutError:
                raise ToolError(f"{self.name} took too long to answer")
            except Exception as e:
                raise ToolError(f"{self.name}: {e}")
            text = as_text(result)
            if result.is_error:
                raise ToolError(text)
            return text
        return call


async def start_all(path: Path) -> None:
    """Start every server in mcp.json; their tools appear as each one connects."""
    try:
        config = load_config(path)
    except (OSError, ValueError, KeyError) as e:
        log.warning("can't read %s: %s", path, e)
        return
    for name, cfg in config.items():
        servers[name] = Server(name, cfg)
        servers[name].start()


async def stop_all() -> None:
    for server in servers.values():
        await server.stop()
