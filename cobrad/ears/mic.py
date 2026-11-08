"""Push-to-talk recording: the mic is only open between start() and stop()."""
from __future__ import annotations

import logging
import threading
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)

RATE = 16000  # what Whisper wants
LEVELS_PER_SECOND = 30


class Recorder:
    def __init__(self, max_seconds: float = 30, on_level: Callable[[float], None] | None = None,
                 input=None):
        """on_level: called from the audio thread with 0..1 loudness, ~30×/s.
        input: factory(rate, blocksize, callback) → stream with start/stop/close (tests swap it)."""
        self.max_frames = int(max_seconds * RATE)
        self.on_level = on_level
        self._input = input or _sounddevice_input
        self._stream = None
        self._chunks: list[np.ndarray] = []
        self._frames = 0
        self._lock = threading.Lock()

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        if self._stream is not None:
            return
        self._chunks, self._frames = [], 0
        stream = self._input(RATE, RATE // LEVELS_PER_SECOND, self._callback)
        stream.start()
        self._stream = stream

    def stop(self) -> np.ndarray:
        """Close the mic and return what was heard: mono float32 at 16 kHz."""
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                log.exception("closing the mic failed")
        if self.on_level:
            self.on_level(0.0)
        with self._lock:
            audio = np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)
            self._chunks, self._frames = [], 0
        return audio

    def _callback(self, indata, frames, time, status) -> None:
        mono = np.asarray(indata, dtype=np.float32).reshape(len(indata), -1)[:, 0]
        with self._lock:
            if self._frames < self.max_frames:
                self._chunks.append(mono.copy())
                self._frames += len(mono)
        if self.on_level:
            self.on_level(min(1.0, float(np.sqrt(np.mean(mono ** 2))) * 4))


def _sounddevice_input(rate: int, blocksize: int, callback):
    import sounddevice as sd
    return sd.InputStream(samplerate=rate, channels=1, dtype="float32", blocksize=blocksize,
                          callback=callback)
