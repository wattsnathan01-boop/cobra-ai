"""Hands-free: keep the mic open, cut it into phrases with Silero VAD (CPU, ~0.1 ms per 32 ms
frame), and hand each phrase to the daemon, which checks whether it starts with "Cobra".

No phrase is kept or logged unless it's for Cobra. While she is talking (or push-to-talk is
recording) phrases are dropped, so she doesn't wake herself up through the speakers.
"""
from __future__ import annotations

import logging
import os
import queue
import threading
import time
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)

RATE = 16000
FRAME = 512             # 32 ms, what Silero expects at 16 kHz
CONTEXT = 64
PREROLL_FRAMES = 19     # keep ~0.6 s from before speech was detected, so "Cobra" isn't clipped
END_FRAMES = 28         # ~0.9 s of quiet ends a phrase (people pause after "Cobra,")
MIN_FRAMES = 8          # ignore blips shorter than ~0.25 s
MAX_FRAMES = 15 * RATE // FRAME
COOLDOWN = 0.6          # after she stops talking, her echo is still in the room
# Silero's memory of a long quiet stretch makes it slow to notice the next word, so a short
# "Cobra" would be half over before a phrase starts. Forget the quiet every ~2 s.
RESET_QUIET_FRAMES = 60


class VAD:
    """Silero VAD, one frame at a time (the model ships with faster-whisper)."""

    def __init__(self) -> None:
        import faster_whisper
        import onnxruntime
        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.log_severity_level = 4
        path = os.path.join(os.path.dirname(faster_whisper.__file__), "assets",
                            "silero_vad_v6.onnx")
        self.session = onnxruntime.InferenceSession(path, providers=["CPUExecutionProvider"],
                                                    sess_options=opts)
        self.reset()

    def reset(self) -> None:
        self.h = np.zeros((1, 1, 128), np.float32)
        self.c = np.zeros((1, 1, 128), np.float32)
        self.context = np.zeros(CONTEXT, np.float32)

    def __call__(self, frame: np.ndarray) -> float:
        x = np.concatenate([self.context, frame])[None]
        prob, self.h, self.c = self.session.run(None, {"input": x, "h": self.h, "c": self.c})
        self.context = frame[-CONTEXT:]
        return float(prob.reshape(-1)[0])


class WakeListener:
    def __init__(self, on_phrase: Callable[[np.ndarray], None], busy: Callable[[], bool],
                 threshold: float = 0.6, on_level: Callable[[float], None] | None = None,
                 vad=None, input=None):
        """on_phrase: called (from a worker thread) with each phrase, float32 16 kHz.
        busy: True while phrases should be ignored (she's talking, push-to-talk is on)."""
        self.on_phrase = on_phrase
        self.busy = busy
        self.start_threshold = threshold
        self.keep_threshold = threshold * 0.6
        self.on_level = on_level
        self.vad = vad
        self._input = input or _sounddevice_input
        self._stream = None
        self._blocks: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        if self._stream is not None:
            return
        if self.vad is None:
            self.vad = VAD()
        if self._worker is None:
            self._worker = threading.Thread(target=self._loop, name="cobra-wake", daemon=True)
            self._worker.start()
        stream = self._input(RATE, FRAME, self._callback)
        stream.start()
        self._stream = stream
        log.info("wake word listening")

    def stop(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                log.exception("closing the wake mic failed")
            self._blocks.put(None)  # tell the worker to forget any half-heard phrase
            log.info("wake word off")

    def _callback(self, indata, frames, time_info, status) -> None:
        self._blocks.put(np.asarray(indata, dtype=np.float32).reshape(len(indata), -1)[:, 0].copy())

    def _loop(self) -> None:
        pending = np.zeros(0, np.float32)
        preroll: list[np.ndarray] = []
        phrase: list[np.ndarray] = []
        quiet = 0
        voiced = 0  # frames that actually sounded like speech (not the lead-in or pauses)
        idle = 0    # quiet frames in a row while waiting for speech
        quiet_until = 0.0
        while True:
            block = self._blocks.get()
            if block is None:
                pending, preroll, phrase, quiet = np.zeros(0, np.float32), [], [], 0
                self.vad.reset()
                continue
            pending = np.concatenate([pending, block])
            while len(pending) >= FRAME:
                frame, pending = pending[:FRAME], pending[FRAME:]
                if self.busy():
                    quiet_until = time.monotonic() + COOLDOWN
                if time.monotonic() < quiet_until:
                    preroll, phrase, quiet = [], [], 0
                    continue
                prob = self.vad(frame)
                if not phrase:
                    preroll = (preroll + [frame])[-PREROLL_FRAMES:]
                    if prob >= self.start_threshold:
                        phrase, preroll, quiet, voiced, idle = preroll, [], 0, 1, 0
                        continue
                    idle = idle + 1 if prob < self.keep_threshold else 0
                    if idle >= RESET_QUIET_FRAMES:
                        self.vad.reset()
                        idle = 0
                    continue
                phrase.append(frame)
                if prob >= self.keep_threshold:
                    quiet, voiced = 0, voiced + 1
                else:
                    quiet += 1
                if self.on_level:
                    self.on_level(min(1.0, float(np.sqrt(np.mean(frame ** 2))) * 4))
                if quiet >= END_FRAMES or len(phrase) >= MAX_FRAMES:
                    audio, enough = np.concatenate(phrase), voiced >= MIN_FRAMES
                    phrase, quiet, voiced = [], 0, 0
                    if self.on_level:
                        self.on_level(0.0)
                    if enough:
                        try:
                            self.on_phrase(audio)
                        except Exception:
                            log.exception("phrase handler failed")


def _sounddevice_input(rate: int, blocksize: int, callback):
    import sounddevice as sd
    return sd.InputStream(samplerate=rate, channels=1, dtype="float32", blocksize=blocksize,
                          callback=callback)
