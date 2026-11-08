"""Unix-socket server: one JSON message per line.

Client → cobrad:
  {"type": "ask", "id", "text", "speak"?}  ask something (one at a time; others queue);
                                           speak: also say the reply out loud
  {"type": "listen", "action"}             push-to-talk: start | stop | toggle | cancel
  {"type": "hush"}                         stop talking (and stop the spoken question)
  {"type": "confirm_reply", "confirm_id", "allow"}
  {"type": "subscribe"}                    receive every event (overlay, waybar)
  {"type": "status"} / {"type": "reset"}

cobrad → client:
  state {state: idle|listening|thinking|speaking} · heard {text} · delta {text}
  tool {name, args, status, result?} · confirm {confirm_id, tool, args}
  level {source: mic|voice, value 0..1}  (subscribers only, ~30×/s)
  error {message} · done {text} · status {state}
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path

from .brain.agent import Agent
from .voice import Voice
from .voice.sentences import SentenceSplitter

log = logging.getLogger(__name__)

MIN_SPEECH_SECONDS = 0.3
# a "stop" this soon before a "start" was a quick tap whose messages arrived out of order
TAP_SECONDS = 0.5

_YES = re.compile(r"\b(yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|allow|affirmative)\b")
_NO = re.compile(r"\b(no|nope|nah|don't|do not|stop|cancel|deny)\b")


def parse_yes_no(text: str) -> bool:
    """A spoken answer to a confirm card. Anything that isn't a clear yes is a no."""
    text = text.lower()
    return not _NO.search(text) and bool(_YES.search(text))


class Server:
    def __init__(self, agent: Agent, path: Path, voice: Voice | None = None):
        self.agent = agent
        self.path = path
        self.voice = voice
        self.state = "idle"
        self.subscribers: set[asyncio.StreamWriter] = set()
        self.pending: dict[str, asyncio.Future] = {}
        self.lock = asyncio.Lock()
        self.server: asyncio.AbstractServer | None = None
        self.spoken_task: asyncio.Task | None = None  # the voice question being answered
        self._listen_session = 0
        self._early_stop = 0.0
        self._bg: set[asyncio.Task] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.unlink(missing_ok=True)
        self.server = await asyncio.start_unix_server(self._handle, path=str(self.path))
        os.chmod(self.path, 0o600)
        log.info("listening on %s", self.path)

    async def close(self) -> None:
        if self.voice and self.voice.recorder.recording:
            self.voice.recorder.stop()
        if self.voice and self.voice.speaker:
            self.voice.speaker.stop()
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        self.path.unlink(missing_ok=True)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        tasks: set[asyncio.Task] = set()
        try:
            await self._serve(reader, writer, tasks)
        except ConnectionError:
            pass  # the client went away mid-read
        finally:
            self.subscribers.discard(writer)
            for task in tasks:
                task.cancel()
            writer.close()

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                     tasks: set[asyncio.Task]) -> None:
        async for line in reader:
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = msg.get("type")
            if kind == "ask" and msg.get("text"):
                task = asyncio.create_task(
                    self._ask(msg["text"], writer, msg.get("id"), bool(msg.get("speak"))))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
            elif kind == "listen":
                await self._listen(msg.get("action", "toggle"))
            elif kind == "hush":
                await self._hush()
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

    # ── asking ──────────────────────────────────────────────────────────

    async def _ask(self, text: str, reply_to: asyncio.StreamWriter | None,
                   ask_id: str | None = None, speak: bool = False) -> None:
        ask_id = ask_id or uuid.uuid4().hex
        speaker = self.voice.speaker if speak and self.voice else None
        splitter = SentenceSplitter()

        async def emit(ev: dict) -> None:
            ev["id"] = ask_id
            if ev["type"] == "state":
                self.state = ev["state"]
            await self._broadcast(ev, reply_to)
            if speaker is None:
                return
            if ev["type"] == "delta":
                for sentence in splitter.feed(ev["text"]):
                    speaker.say(sentence)
            elif ev["type"] == "tool" and ev["status"] == "checking":
                for sentence in splitter.flush():  # "Let me check." before a tool runs
                    speaker.say(sentence)
            elif ev["type"] == "error":
                speaker.say(ev["message"])

        async def confirm(tool: str, args: dict) -> bool:
            cid = uuid.uuid4().hex
            fut = asyncio.get_running_loop().create_future()
            self.pending[cid] = fut
            try:
                if speaker:
                    speaker.say(f"I need your okay to use {tool.replace('_', ' ')}. "
                                "Hold the talk key and say yes or no.")
                await emit({"type": "confirm", "confirm_id": cid, "tool": tool, "args": args})
                return await fut
            finally:
                self.pending.pop(cid, None)

        async with self.lock:
            try:
                await emit({"type": "heard", "text": text})
                reply = await self.agent.ask(text, emit, confirm)
                await emit({"type": "done", "text": reply})
                if speaker:
                    for sentence in splitter.flush():
                        speaker.say(sentence)
                    if speaker.speaking:
                        await emit({"type": "state", "state": "speaking"})
                        await speaker.wait()
            except Exception as e:
                log.exception("ask failed")
                await emit({"type": "error", "message": f"internal error: {e}"})
                await emit({"type": "done", "text": ""})
            finally:
                listening = self.voice is not None and self.voice.recorder.recording
                await emit({"type": "state", "state": "listening" if listening else "idle"})

    # ── push-to-talk ────────────────────────────────────────────────────

    async def _listen(self, action: str) -> None:
        if self.voice is None:
            await self._broadcast({"type": "error", "message": "voice isn't available"})
            return
        recorder = self.voice.recorder
        if action == "toggle":
            action = "stop" if recorder.recording else "start"
        if action == "start":
            await self._listen_start()
        elif action == "stop":
            await self._listen_stop()
        elif action == "cancel" and recorder.recording:
            recorder.stop()
            await self._set_state(self._resting_state())

    async def _listen_start(self) -> None:
        recorder = self.voice.recorder
        if recorder.recording:
            # the key-up got lost (e.g. SUPER let go before C): a second press ends it
            await self._listen_stop()
            return
        if time.monotonic() - self._early_stop < TAP_SECONDS:
            return
        if self.voice.speaker:
            self.voice.speaker.stop()  # barge-in: she stops talking as soon as you press
        try:
            recorder.start()
        except Exception as e:
            log.exception("couldn't open the mic")
            await self._broadcast({"type": "error", "message": f"couldn't open the mic: {e}"})
            return
        if not self.pending:  # a new question replaces the one being answered
            await self._cancel_spoken()
        await self._set_state("listening")
        self._listen_session += 1
        self._spawn(self._listen_timeout(self._listen_session))

    async def _listen_timeout(self, session: int) -> None:
        """Never leave the mic open: stop at the recording limit even if the key-up never came."""
        await asyncio.sleep(self.voice.recorder.max_frames / 16000)
        if session == self._listen_session and self.voice.recorder.recording:
            log.info("push-to-talk held too long (or key-up lost); stopping")
            await self._listen_stop()

    async def _listen_stop(self) -> None:
        recorder = self.voice.recorder
        if not recorder.recording:
            self._early_stop = time.monotonic()
            return
        audio = recorder.stop()
        if len(audio) < MIN_SPEECH_SECONDS * 16000:
            await self._set_state(self._resting_state())
            return
        if self.voice.transcriber is None:
            await self._say_error("My ears are still warming up. Try again in a moment.")
            return
        await self._set_state("thinking")
        try:
            text = await asyncio.to_thread(self.voice.transcriber.transcribe, audio)
        except Exception as e:
            log.exception("transcription failed")
            await self._say_error(f"I couldn't make that out: {e}")
            return
        log.info("heard: %r", text)
        if not text:
            await self._set_state(self._resting_state())
            return
        if self.pending:  # she asked "yes or no?": this is the answer
            await self._broadcast({"type": "heard", "text": text})
            fut = list(self.pending.values())[-1]
            if not fut.done():
                fut.set_result(parse_yes_no(text))
            await self._set_state(self._resting_state())
            return
        self.spoken_task = asyncio.create_task(self._ask(text, None, speak=True))
        self._bg.add(self.spoken_task)
        self.spoken_task.add_done_callback(self._bg.discard)

    async def _hush(self) -> None:
        if self.voice and self.voice.speaker:
            self.voice.speaker.stop()
        await self._cancel_spoken()

    async def _cancel_spoken(self) -> None:
        task, self.spoken_task = self.spoken_task, None
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    def _resting_state(self) -> str:
        return "thinking" if self.spoken_task and not self.spoken_task.done() else "idle"

    async def _say_error(self, message: str) -> None:
        await self._broadcast({"type": "error", "message": message})
        if self.voice and self.voice.speaker:
            self.voice.speaker.say(message)
        await self._set_state(self._resting_state())

    # ── events ──────────────────────────────────────────────────────────

    def level(self, source: str, value: float) -> None:
        """Loudness for the HUD's voice bars. Safe to call from audio threads."""
        if self.subscribers and self._loop is not None:
            ev = {"type": "level", "source": source, "value": round(value, 3)}
            self._loop.call_soon_threadsafe(self._spawn, self._broadcast(ev))

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._bg.add(task)
        task.add_done_callback(self._bg.discard)

    async def _set_state(self, state: str) -> None:
        self.state = state
        await self._broadcast({"type": "state", "state": state})

    async def _broadcast(self, ev: dict, reply_to: asyncio.StreamWriter | None = None) -> None:
        if reply_to is not None:
            await self._send(reply_to, ev)
        for sub in list(self.subscribers):
            if sub is not reply_to:
                await self._send(sub, ev)

    async def _send(self, writer: asyncio.StreamWriter, ev: dict) -> None:
        if writer.is_closing():
            return
        try:
            writer.write(json.dumps(ev, ensure_ascii=False).encode() + b"\n")
            await writer.drain()
        except (ConnectionError, RuntimeError):
            self.subscribers.discard(writer)
