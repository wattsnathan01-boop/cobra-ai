"""Unix-socket server: one JSON message per line.

Client → cobrad:
  {"type": "ask", "id", "text", "speak"?}  ask something (one at a time; others queue);
                                           speak: also say the reply out loud
  {"type": "listen", "action"}             push-to-talk: start | stop | toggle | cancel
  {"type": "hush"}                         stop talking (and stop the spoken question)
  {"type": "hud", "action"}                open the full HUD: toggle | show | hide
  {"type": "wake", "action"}               the "Cobra" wake word: on | off | toggle
  {"type": "stats"}                        system stats + what's playing, for the HUD
  {"type": "settings"}                     every setting (answered with a settings snapshot)
  {"type": "set", "key", "value"}          change one setting: saved and applied now
  {"type": "preview_voice", "voice"}       say a line in another voice without switching
  {"type": "open_settings", "page"?}       ask the overlay to open the settings window
  {"type": "confirm_reply", "confirm_id", "allow", "remember"?}   remember: "Always"
  {"type": "subscribe"}                    receive every event (overlay, waybar); answered
                                           with hello {model, voice, stt} and the state
  {"type": "status"} / {"type": "reset"}

cobrad → client:
  state {state: idle|listening|thinking|speaking} · heard {text} · delta {text}
  partial {text}  (live transcript while listening; subscribers only)
  tool {name, args, status, result?, ms?}
  confirm {confirm_id, tool, args, preview?, reason, timeout, always, card}  (asks to decide)
  confirmed {confirm_id, allow}  (it was answered or timed out: close the card)
  blocked {tool, args, preview?}  (a tool set to Never was tried)
  hud {action}  (subscribers only) · stats {cpu_percent, gpu, ..., playing}
  wake {on}  (to everyone, when it changes; also in hello)
  settings {...} · saved {key, note} · setting_error {key, message} · open_settings {page}
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

from . import settings
from .brain.agent import Agent
from .gate import NO_ALWAYS
from .voice import Voice
from .voice.sentences import SentenceSplitter

log = logging.getLogger(__name__)

MIN_SPEECH_SECONDS = 0.3
# a "stop" this soon before a "start" was a quick tap whose messages arrived out of order
TAP_SECONDS = 0.5
# Whisper turns mic hum into "." or "..."; only text with letters or digits counts as speech
_WORDS = re.compile(r"\w")
# how often the live transcript is refreshed while you talk
PARTIAL_SECONDS = 0.7

# "Cobra, …" / "Hey Cobra …" / "Okay Cobra" at the start of a phrase (and Whisper's near misses)
_WAKE = re.compile(r"^\W*(?:(?:hey|hi|ok|okay|oi)\W+)?(?:cobra|kobra|copra)s?\b\W*(.*)$",
                   re.IGNORECASE | re.DOTALL)

# for phrases from the always-on mic: hinting her name (with a wider beam search) turns
# mumbled starts like "bro what is the time" into "Cobra, what is the time?"
WAKE_PROMPT = "Cobra, what's my GPU temperature? Cobra."

_YES = re.compile(r"\b(yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|allow|affirmative)\b")
_NO = re.compile(r"\b(no|nope|nah|don't|do not|stop|cancel|deny)\b")


def match_wake(text: str) -> str | None:
    """What was asked after "Cobra" ("" if just her name), or None if it wasn't for her."""
    m = _WAKE.match(text)
    return m.group(1).strip() if m else None


def parse_yes_no(text: str) -> bool:
    """A spoken answer to a confirm card. Anything that isn't a clear yes is a no."""
    text = text.lower()
    return not _NO.search(text) and bool(_YES.search(text))


async def _stats() -> dict:
    from .hands import ToolError
    from .hands.media import media
    from .hands.system import system_stats
    try:
        stats = await system_stats()
    except Exception:
        log.exception("stats failed")
        stats = {}
    try:
        playing = await media("status")
        stats["playing"] = "" if playing == "nothing is playing" else playing
    except ToolError:
        stats["playing"] = ""
    return stats


class Server:
    def __init__(self, agent: Agent, path: Path, voice: Voice | None = None,
                 info: dict | None = None, follow_up_seconds: float = 8):
        self.agent = agent
        self.path = path
        self.voice = voice
        self.info = info or {}  # model / voice names, sent to subscribers in "hello"
        self.state = "idle"
        self.subscribers: set[asyncio.StreamWriter] = set()
        self.clients: set[asyncio.StreamWriter] = set()
        self.pending: dict[str, asyncio.Future] = {}
        self.lock = asyncio.Lock()
        self.server: asyncio.AbstractServer | None = None
        self.spoken_task: asyncio.Task | None = None  # the voice question being answered
        self._listen_session = 0
        self._early_stop = 0.0
        self.wake = None                 # ears.wake.WakeListener, if hands-free is set up
        self.follow_up_seconds = follow_up_seconds
        self.awake_until = 0.0           # after "Cobra" on its own: listening without the name
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
        if self.wake:
            self.wake.stop()
        if self.voice and self.voice.recorder.recording:
            self.voice.recorder.stop()
        if self.voice and self.voice.speaker:
            self.voice.speaker.stop()
        if self.server:
            self.server.close()
            # wait_closed() waits for every client, and the overlay never hangs up by itself
            for writer in list(self.clients):
                writer.close()
            await self.server.wait_closed()
        self.path.unlink(missing_ok=True)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        tasks: set[asyncio.Task] = set()
        self.clients.add(writer)
        try:
            await self._serve(reader, writer, tasks)
        except ConnectionError:
            pass  # the client went away mid-read
        finally:
            self.clients.discard(writer)
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
            elif kind == "hud":
                await self._broadcast({"type": "hud", "action": msg.get("action", "toggle")})
            elif kind == "settings":
                await self._send(writer, await settings.snapshot(self))
            elif kind == "set":
                self._spawn(self._set(msg.get("key", ""), msg.get("value"), writer))
            elif kind == "preview_voice":
                self._spawn(self._preview_voice(msg.get("voice", ""), writer))
            elif kind == "open_settings":
                await self._broadcast({"type": "open_settings", "page": msg.get("page", "")})
            elif kind == "wake":
                await self.set_wake(msg.get("action", "toggle"))
                if writer not in self.subscribers:
                    await self._send(writer, {"type": "wake",
                                              "on": bool(self.wake and self.wake.running)})
            elif kind == "stats":
                await self._send(writer, {"type": "stats", **await _stats()})
            elif kind == "confirm_reply":
                fut = self.pending.get(msg.get("confirm_id"))
                if fut and not fut.done():
                    if msg.get("allow") and msg.get("remember"):
                        self.agent.gate.remember(fut.tool)
                    fut.set_result(bool(msg.get("allow")))
            elif kind == "subscribe":
                self.subscribers.add(writer)
                await self._send(writer, {"type": "hello", **self.info,
                                          "wake": bool(self.wake and self.wake.running)})
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

        async def confirm(tool: str, args: dict, preview: dict | None = None) -> bool:
            cid = uuid.uuid4().hex
            fut = asyncio.get_running_loop().create_future()
            fut.tool = tool
            self.pending[cid] = fut
            allowed = False
            try:
                if speaker:
                    how = ("Say yes or no." if self.wake and self.wake.running
                           else "Hold the talk key and say yes or no.")
                    ask = (preview or {}).get("say") or \
                        f"I need your okay to use {tool.replace('_', ' ')}."
                    speaker.say(f"{ask} {how}")
                await emit({"type": "confirm", "confirm_id": cid, "tool": tool, "args": args,
                            "preview": preview, "reason": text,
                            "timeout": self.agent.gate.confirm_timeout,
                            "always": tool not in NO_ALWAYS,
                            # an overlay will show a card, so a terminal shouldn't also prompt
                            "card": any(s is not reply_to for s in self.subscribers)})
                allowed = await fut
                return allowed
            finally:
                self.pending.pop(cid, None)
                await emit({"type": "confirmed", "confirm_id": cid, "allow": allowed})

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
        self._spawn(self._live_transcript(self._listen_session))

    async def _listen_timeout(self, session: int) -> None:
        """Never leave the mic open: stop at the recording limit even if the key-up never came."""
        await asyncio.sleep(self.voice.recorder.max_frames / 16000)
        if session == self._listen_session and self.voice.recorder.recording:
            log.info("push-to-talk held too long (or key-up lost); stopping")
            await self._listen_stop()

    async def _live_transcript(self, session: int) -> None:
        """While the key is held, keep transcribing what's been said so far for the overlay."""
        recorder, last = self.voice.recorder, ""
        while True:
            await asyncio.sleep(PARTIAL_SECONDS)
            if session != self._listen_session or not recorder.recording:
                return
            if not self.subscribers or self.voice.transcriber is None:
                continue
            audio = recorder.snapshot()
            if len(audio) < MIN_SPEECH_SECONDS * 16000:
                continue
            try:
                text = await asyncio.to_thread(self.voice.transcriber.transcribe, audio)
            except Exception:
                log.exception("live transcript failed")
                return
            if (_WORDS.search(text) and text != last and session == self._listen_session
                    and recorder.recording):
                last = text
                await self._broadcast({"type": "partial", "text": text})

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
        if not _WORDS.search(text):
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

    # ── hands-free ("Cobra, …") ─────────────────────────────────────────

    async def announce_hello(self) -> None:
        """Model or voice changed: tell the overlay."""
        await self._broadcast({"type": "hello", **self.info,
                               "wake": bool(self.wake and self.wake.running)})

    async def _set(self, key: str, value, writer: asyncio.StreamWriter) -> None:
        try:
            note = await settings.apply(self, key, value)
        except (settings.SettingError, ValueError, TypeError, OSError) as e:
            await self._send(writer, {"type": "setting_error", "key": key, "message": str(e)})
            return
        except Exception as e:
            log.exception("setting %s failed", key)
            await self._send(writer, {"type": "setting_error", "key": key, "message": str(e)})
            return
        log.info("setting %s: %s", key, note)
        await self._send(writer, {"type": "saved", "key": key, "note": note})
        await self._send(writer, await settings.snapshot(self))

    async def _preview_voice(self, voice: str, writer: asyncio.StreamWriter) -> None:
        try:
            await settings.preview_voice(voice)
            await self._send(writer, {"type": "saved", "key": "preview_voice", "note": ""})
        except Exception as e:
            await self._send(writer, {"type": "setting_error", "key": "preview_voice",
                                      "message": str(e)})

    async def set_wake(self, action: str) -> None:
        if self.wake is None:
            await self._broadcast({"type": "error", "message": "the wake word isn't set up"})
            return
        on = not self.wake.running if action == "toggle" else action == "on"
        try:
            self.wake.start() if on else self.wake.stop()
        except Exception as e:
            log.exception("couldn't switch the wake word")
            await self._broadcast({"type": "error", "message": f"wake word: {e}"})
        await self._broadcast({"type": "wake", "on": self.wake.running})

    def heard_phrase(self, audio) -> None:
        """A phrase from the always-on mic. Called from the wake listener's thread."""
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._spawn, self._on_phrase(audio))

    async def _on_phrase(self, audio) -> None:
        voice = self.voice
        if voice is None or voice.transcriber is None or voice.recorder.recording:
            return
        if self.spoken_task and not self.spoken_task.done() and not self.pending:
            return  # she's busy with a question; push-to-talk can still interrupt
        awake = time.monotonic() < self.awake_until
        hint = not awake and not self.pending
        text = await asyncio.to_thread(voice.transcriber.transcribe, audio,
                                       WAKE_PROMPT if hint else None, 5 if hint else 1)
        if not _WORDS.search(text):
            return
        if self.pending:  # waiting on yes/no: only a clear answer counts, not room chatter
            lowered = text.lower()
            if _YES.search(lowered) or _NO.search(lowered):
                await self._broadcast({"type": "heard", "text": text})
                fut = list(self.pending.values())[-1]
                if not fut.done():
                    fut.set_result(parse_yes_no(text))
            return
        question = text if awake else match_wake(text)
        if question is None:
            return  # not for her; deliberately not logged
        log.info("wake: %r", text)
        self.awake_until = 0.0
        if not _WORDS.search(question):
            self._spawn(self._wake_up())
            return
        self.spoken_task = asyncio.create_task(self._ask(question, None, speak=True))
        self._bg.add(self.spoken_task)
        self.spoken_task.add_done_callback(self._bg.discard)

    async def _wake_up(self) -> None:
        """Just "Cobra": answer, then listen for the question without needing her name."""
        speaker = self.voice.speaker
        if speaker:
            speaker.say("Yes?")
            await speaker.wait()
        self.awake_until = time.monotonic() + self.follow_up_seconds
        await self._set_state("listening")
        await asyncio.sleep(self.follow_up_seconds)
        if self.awake_until and time.monotonic() >= self.awake_until:
            self.awake_until = 0.0
            if self.state == "listening" and not self.voice.recorder.recording:
                await self._set_state(self._resting_state())

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
