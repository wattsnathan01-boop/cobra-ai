"""Speaks sentences in order while the next ones are still being written, and stops instantly
when interrupted (barge-in).

Two threads: one turns text into audio, the other plays it. Each sentence carries the
"generation" it was queued in; stop() bumps the generation, so anything older is skipped and
the sentence playing right now is cut off within one block (~1/30 s).
"""
from __future__ import annotations

import asyncio
import logging
import queue
import threading
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)

LEVELS_PER_SECOND = 30


class Speaker:
    def __init__(self, tts, on_level: Callable[[float], None] | None = None, output=None):
        """tts: has .sample_rate and .synthesize(text) → int16 chunks.
        on_level: called from the audio thread with 0..1 loudness, ~30×/s (drives the HUD).
        output: factory(sample_rate) → stream with start/write/abort/close (tests swap this)."""
        self.tts = tts
        self.on_level = on_level
        self._output = output or _sounddevice_output
        self._texts: queue.Queue = queue.Queue()
        self._audio: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._gen = 0
        self._busy = 0  # sentences queued but not yet finished or skipped
        threading.Thread(target=self._synth_loop, name="cobra-tts", daemon=True).start()
        threading.Thread(target=self._play_loop, name="cobra-play", daemon=True).start()

    @property
    def speaking(self) -> bool:
        return self._busy > 0

    def say(self, text: str) -> None:
        if not text.strip():
            return
        with self._lock:
            self._busy += 1
            self._texts.put((self._gen, text))

    def stop(self) -> None:
        """Stop talking now and forget everything queued."""
        with self._lock:
            self._gen += 1

    async def wait(self) -> None:
        """Until everything queued has been spoken (or skipped by stop())."""
        while self._busy > 0:
            await asyncio.sleep(0.05)

    def _synth_loop(self) -> None:
        while True:
            gen, text = self._texts.get()
            try:
                if gen == self._gen:
                    for chunk in self.tts.synthesize(text):
                        if gen != self._gen:
                            break
                        self._audio.put((gen, chunk))
            except Exception:
                log.exception("speech synthesis failed for %r", text)
            self._audio.put((gen, None))  # end of this sentence, always sent exactly once

    def _play_loop(self) -> None:
        stream = None
        block = max(1, self.tts.sample_rate // LEVELS_PER_SECOND)
        while True:
            try:
                gen, chunk = self._audio.get(timeout=0.5)
            except queue.Empty:
                if stream is not None:  # quiet for a moment: release the sound device
                    stream = _close(stream)
                continue
            if chunk is None:
                with self._lock:
                    self._busy -= 1
                    done = self._busy == 0
                if done:
                    self._level(0.0)
                continue
            if gen != self._gen:
                continue
            try:
                if stream is None:
                    stream = self._output(self.tts.sample_rate)
                    stream.start()
                for i in range(0, len(chunk), block):
                    if gen != self._gen:  # barge-in: drop what's buffered and stop
                        stream = _close(stream, abort=True)
                        self._level(0.0)
                        break
                    part = chunk[i:i + block]
                    stream.write(part)
                    rms = float(np.sqrt(np.mean((part.astype(np.float32) / 32768) ** 2)))
                    self._level(min(1.0, rms * 4))
            except Exception:
                log.exception("audio playback failed")
                stream = _close(stream, abort=True) if stream is not None else None

    def _level(self, value: float) -> None:
        if self.on_level:
            try:
                self.on_level(value)
            except Exception:
                log.exception("level callback failed")


def _close(stream, abort: bool = False) -> None:
    try:
        stream.abort() if abort else stream.stop()
        stream.close()
    except Exception:
        log.exception("closing audio stream failed")
    return None


def _sounddevice_output(sample_rate: int):
    import sounddevice as sd
    return sd.OutputStream(samplerate=sample_rate, channels=1, dtype="int16")
