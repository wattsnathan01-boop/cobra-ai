"""Local brain: Ollama's /api/chat, streamed, with tool calling."""
from __future__ import annotations

import json
from typing import AsyncIterator

import httpx


class BrainError(Exception):
    pass


class OllamaBrain:
    name = "local"

    def __init__(self, host: str, model: str, think: bool = False, keep_alive: str = "10m",
                 transport: httpx.AsyncBaseTransport | None = None):
        self.model = model
        self.think = think
        self.keep_alive = keep_alive
        self.client = httpx.AsyncClient(base_url=host, transport=transport,
                                        timeout=httpx.Timeout(300, connect=5))

    async def ping(self) -> bool:
        try:
            r = await self.client.get("/api/tags")
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def chat(self, messages: list[dict], tools: list[dict],
                   context: str = "") -> AsyncIterator[dict]:
        """Yield {"type": "text", "text"} chunks, then one {"type": "tool_calls", "calls"}
        if the model wants tools. Each call is {"name": str, "arguments": dict}.
        context: what changes per question (time, remembered facts), added to the system prompt."""
        body = {"model": self.model, "messages": self._clean(messages, context), "tools": tools,
                "stream": True,
                "think": self.think, "keep_alive": self.keep_alive}
        calls: list[dict] = []
        try:
            async with self.client.stream("POST", "/api/chat", json=body) as r:
                if r.status_code != 200:
                    detail = (await r.aread()).decode(errors="replace")
                    raise BrainError(f"Ollama returned {r.status_code}: {detail[:200]}")
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if "error" in chunk:
                        raise BrainError(chunk["error"])
                    msg = chunk.get("message", {})
                    if msg.get("content"):
                        yield {"type": "text", "text": msg["content"]}
                    for c in msg.get("tool_calls") or []:
                        fn = c.get("function", {})
                        args = fn.get("arguments") or {}
                        if isinstance(args, str):
                            args = json.loads(args or "{}")
                        calls.append({"name": fn.get("name", ""), "arguments": args})
        except httpx.ConnectError:
            raise BrainError("can't reach Ollama. Is it running? (systemctl status ollama)")
        if calls:
            yield {"type": "tool_calls", "calls": calls}

    @staticmethod
    def _clean(messages: list[dict], context: str) -> list[dict]:
        """Just what Ollama understands (turns Claude answered carry extra fields)."""
        out = []
        for m in messages:
            msg = {"role": m["role"], "content": m.get("content") or ""}
            if m.get("tool_calls"):
                msg["tool_calls"] = [{"function": c.get("function", c)} for c in m["tool_calls"]]
            if m["role"] == "tool":
                msg["tool_name"] = m.get("tool_name", "")
            out.append(msg)
        if context and out and out[0]["role"] == "system":
            out[0]["content"] += "\n\n" + context
        return out

    @staticmethod
    def assistant_message(text: str, calls: list[dict]) -> dict:
        msg: dict = {"role": "assistant", "content": text}
        if calls:
            msg["tool_calls"] = [{"function": {"name": c["name"], "arguments": c["arguments"]}}
                                 for c in calls]
        return msg

    @staticmethod
    def tool_message(name: str, result: str, call_id: str | None = None) -> dict:
        return {"role": "tool", "tool_name": name, "content": result}
