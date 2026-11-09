"""The notebook inside cobrad: requests from the window, reminders going off, voice memos.

Window → cobrad:  {"type": "notebook", "action", "req"?, ...}   (actions in Service.handle)
                  {"type": "notebook_open"}                      ask the window to open
cobrad → window:  notebook {action, req, ok, data | error}       the answer to a request
                  notebook_changed                               re-read (anyone changed it)
                  notebook_open {id?}                            open the window (at a note)
                  reminder {id, text, due, note_id}              a reminder went off
                  recording {on, note_id, seconds?}              a voice memo is being recorded
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import subprocess
import tempfile
import time
import wave
from pathlib import Path

from .store import Notebook, NotebookError

log = logging.getLogger(__name__)

POLL_SECONDS = 2
MAX_MEMO_SECONDS = 15 * 60


class Service:
    def __init__(self, notebook: Notebook, server):
        self.nb = notebook
        self.server = server
        self._version = notebook.version()
        self._recording: dict | None = None  # {proc, path, note_id, started}

    # ── requests from the window ──

    async def handle(self, msg: dict, writer) -> None:
        action = msg.get("action", "")
        reply = {"type": "notebook", "action": action, "req": msg.get("req")}
        try:
            data = await self._do(action, msg)
            reply.update(ok=True, data=data)
        except NotebookError as e:
            reply.update(ok=False, error=str(e))
        except Exception as e:
            log.exception("notebook %s failed", action)
            reply.update(ok=False, error=f"internal error: {e}")
        await self.server._send(writer, reply)
        await self.poke()

    async def _do(self, action: str, m: dict):
        nb = self.nb
        call = lambda fn, *a, **k: asyncio.to_thread(fn, *a, **k)  # noqa: E731
        if action == "overview":
            data = await call(nb.overview)
            data["recording"] = self.recording_state()
            return data
        if action == "get":
            return await call(nb.get, m["id"])
        if action == "create":
            return await call(nb.create, m.get("title") or "Untitled", m.get("text", ""),
                              "you", m.get("kind", "note"), m.get("tags"))
        if action == "diary_today":
            return await call(nb.diary_today, "you", m.get("day", ""))
        if action == "update":
            changes = {k: m[k] for k in ("title", "tags", "mood", "pinned", "kind") if k in m}
            return await call(nb.update, m["id"], "you", m.get("blocks"), **changes)
        if action == "append":
            return await call(nb.append, m["id"], m.get("text", ""), "you")
        if action == "attach":
            path = str(m.get("path", "")).removeprefix("file://")
            return await call(nb.attach, m["id"], path, "you", m.get("caption", ""))
        if action == "delete":
            return await call(nb.delete, m["id"], "you")
        if action == "reminder_add":
            return await call(nb.add_reminder, m.get("text", ""), m.get("when", ""), "you",
                              m.get("speak", True), m.get("note_id", ""))
        if action == "reminder_done":
            return await call(nb.complete_reminder, m["rid"], "you", m.get("done", True))
        if action == "reminder_snooze":
            return await call(nb.snooze_reminder, m["rid"], float(m.get("minutes", 10)), "you")
        if action == "reminder_delete":
            return await call(nb.delete_reminder, m["rid"], "you")
        if action == "undo":
            return await call(nb.undo, m["entry"])
        if action == "open_path":
            return await self._open_path(m.get("path", ""))
        if action == "record_start":
            return await self.record_start(m["id"])
        if action == "record_stop":
            return await self.record_stop()
        if action == "ask":
            return await self._ask(m)
        raise NotebookError(f"unknown notebook action {action!r}")

    async def _open_path(self, path: str) -> str:
        """Open an attachment in its usual app (only files inside the notebook)."""
        p = Path(path).resolve()
        if not p.is_relative_to(self.nb.root.resolve()) or not p.exists():
            raise NotebookError("that file isn't in the notebook")
        subprocess.Popen(["xdg-open", str(p)], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return "opened"

    async def _ask(self, m: dict) -> str:
        """The composer's ✨: ask Cobra about (or to change) the open note."""
        text = str(m.get("text", "")).strip()
        if not text:
            raise NotebookError("ask what?")
        if m.get("id"):
            note = await asyncio.to_thread(self.nb.get, m["id"])
            text = (f"(The person is in the notebook, looking at the note \"{note['title']}\", "
                    f"id {note['id']}. Use the notebook tools on it if they ask you to add or "
                    f"change something.)\n{text}")
        self.server._spawn(self.server._ask(text, None, speak=bool(m.get("speak"))))
        return "asked"

    # ── voice memos ──

    def recording_state(self) -> dict:
        r = self._recording
        if not r:
            return {"on": False}
        return {"on": True, "note_id": r["note_id"],
                "seconds": round(time.monotonic() - r["started"])}

    async def record_start(self, note_id: str) -> dict:
        if self._recording:
            raise NotebookError("already recording a voice memo")
        await asyncio.to_thread(self.nb.get, note_id)
        path = Path(tempfile.mkdtemp(prefix="cobra-memo-")) / \
            time.strftime("voice-memo-%Y%m%d-%H%M%S.wav")
        try:
            proc = await asyncio.create_subprocess_exec(
                "pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", str(path),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        except FileNotFoundError:
            raise NotebookError("pw-record isn't installed (it comes with pipewire)")
        self._recording = {"proc": proc, "path": path, "note_id": note_id,
                           "started": time.monotonic()}
        self.server._spawn(self._record_limit(proc))
        await self.server._broadcast({"type": "recording", **self.recording_state()})
        return self.recording_state()

    async def _record_limit(self, proc) -> None:
        await asyncio.sleep(MAX_MEMO_SECONDS)
        if self._recording and self._recording["proc"] is proc:
            await self.record_stop()

    async def record_stop(self) -> dict:
        r, self._recording = self._recording, None
        if not r:
            raise NotebookError("not recording")
        proc = r["proc"]
        with contextlib.suppress(ProcessLookupError):
            proc.send_signal(signal.SIGINT)  # pw-record finishes the file on SIGINT
        try:
            await asyncio.wait_for(proc.wait(), 5)
        except asyncio.TimeoutError:
            proc.kill()
        await self.server._broadcast({"type": "recording", "on": False})
        path: Path = r["path"]
        if not path.exists() or path.stat().st_size < 16000:  # under ~0.5 s
            raise NotebookError("the voice memo was empty")
        seconds = round(time.monotonic() - r["started"])
        caption = f"voice memo · {seconds // 60}:{seconds % 60:02d}"
        note = await asyncio.to_thread(self.nb.attach, r["note_id"], path, "you", caption, True)
        path.parent.rmdir()
        self.server._spawn(self._transcribe(r["note_id"], note["blocks"][-1]["path"]))
        return note

    async def _transcribe(self, note_id: str, wav_path: str) -> None:
        voice = self.server.voice
        if voice is None or voice.transcriber is None:
            return
        try:
            import numpy as np
            with wave.open(wav_path, "rb") as w:
                frames = w.readframes(w.getnframes())
            audio = np.frombuffer(frames, np.int16).astype(np.float32) / 32768
            text = await asyncio.to_thread(voice.transcriber.transcribe, audio)
        except Exception:
            log.exception("couldn't transcribe the voice memo")
            return
        if len(text.split()) >= 2:  # one word is usually Whisper hearing room noise
            await asyncio.to_thread(self.nb.append, note_id, f"🎙 “{text.strip()}”", "cobra")
            await self.poke()

    # ── watching: reminders and outside changes ──

    async def poke(self) -> None:
        """Tell the window to re-read if anything changed (here, or from Claude's MCP server)."""
        version = await asyncio.to_thread(self.nb.version)
        if version != self._version:
            self._version = version
            await self.server._broadcast({"type": "notebook_changed"})

    async def run(self) -> None:
        while True:
            try:
                for r in await asyncio.to_thread(self.nb.due_reminders):
                    await self._remind(r)
                await self.poke()
            except Exception:
                log.exception("notebook watch failed")
            await asyncio.sleep(POLL_SECONDS)

    async def _remind(self, r: dict) -> None:
        log.info("reminder: %s", r["text"])
        await self.server._broadcast({"type": "reminder", **r})
        with contextlib.suppress(OSError):
            subprocess.Popen(["notify-send", "-a", "Cobra", "-u", "critical", "-i", "appointment-soon",
                              "Reminder", r["text"]],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        voice = self.server.voice
        if r.get("speak", True) and voice and voice.speaker:
            voice.speaker.say(f"Reminder: {r['text']}")
