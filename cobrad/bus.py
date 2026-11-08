"""Unix-socket server: one JSON message per line.

Client → cobrad:
  {"type": "ask", "id", "text"}            ask something (one at a time; others queue)
  {"type": "confirm_reply", "confirm_id", "allow"}
  {"type": "subscribe"}                    receive every event (overlay, waybar)
  {"type": "status"} / {"type": "reset"}

cobrad → client:
  state {state: idle|thinking|speaking} · heard {text} · delta {text}
  tool {name, args, status, result?} · confirm {confirm_id, tool, args}
  error {message} · done {text} · status {state}
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path

from .brain.agent import Agent

log = logging.getLogger(__name__)


class Server:
    def __init__(self, agent: Agent, path: Path):
        self.agent = agent
        self.path = path
        self.state = "idle"
        self.subscribers: set[asyncio.StreamWriter] = set()
        self.pending: dict[str, asyncio.Future] = {}
        self.lock = asyncio.Lock()
        self.server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.unlink(missing_ok=True)
        self.server = await asyncio.start_unix_server(self._handle, path=str(self.path))
        os.chmod(self.path, 0o600)
        log.info("listening on %s", self.path)

    async def close(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        self.path.unlink(missing_ok=True)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        tasks: set[asyncio.Task] = set()
        try:
            async for line in reader:
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = msg.get("type")
                if kind == "ask" and msg.get("text"):
                    task = asyncio.create_task(self._ask(msg, writer))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
                elif kind == "confirm_reply":
                    fut = self.pending.get(msg.get("confirm_id"))
                    if fut and not fut.done():
                        fut.set_result(bool(msg.get("allow")))
                elif kind == "subscribe":
                    self.subscribers.add(writer)
                    await self._send(writer, {"type": "state", "state": self.state})
                elif kind == "status":
                    await self._send(writer, {"type": "status", "state": self.state})
                elif kind == "reset":
                    self.agent.reset()
                    await self._send(writer, {"type": "status", "state": self.state})
        finally:
            self.subscribers.discard(writer)
            for task in tasks:
                task.cancel()
            writer.close()

    async def _ask(self, msg: dict, writer: asyncio.StreamWriter) -> None:
        ask_id = msg.get("id") or uuid.uuid4().hex

        async def emit(ev: dict) -> None:
            ev["id"] = ask_id
            if ev["type"] == "state":
                self.state = ev["state"]
            await self._send(writer, ev)
            for sub in list(self.subscribers):
                if sub is not writer:
                    await self._send(sub, ev)

        async def confirm(tool: str, args: dict) -> bool:
            cid = uuid.uuid4().hex
            fut = asyncio.get_running_loop().create_future()
            self.pending[cid] = fut
            try:
                await emit({"type": "confirm", "confirm_id": cid, "tool": tool, "args": args})
                return await fut
            finally:
                self.pending.pop(cid, None)

        async with self.lock:
            try:
                await emit({"type": "heard", "text": msg["text"]})
                reply = await self.agent.ask(msg["text"], emit, confirm)
                await emit({"type": "done", "text": reply})
            except Exception as e:
                log.exception("ask failed")
                await emit({"type": "error", "message": f"internal error: {e}"})
                await emit({"type": "done", "text": ""})
            finally:
                await emit({"type": "state", "state": "idle"})

    async def _send(self, writer: asyncio.StreamWriter, ev: dict) -> None:
        if writer.is_closing():
            return
        try:
            writer.write(json.dumps(ev, ensure_ascii=False).encode() + b"\n")
            await writer.drain()
        except (ConnectionError, RuntimeError):
            self.subscribers.discard(writer)
