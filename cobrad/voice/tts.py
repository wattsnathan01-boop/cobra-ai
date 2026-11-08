"""Text → speech with Piper (local, CPU, real time)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator

import numpy as np

log = logging.getLogger(__name__)


def fetch_voice(name: str, voices_dir: Path) -> Path:
    """Download a Piper voice (once) and return its .onnx path."""
    path = voices_dir / f"{name}.onnx"
    if not (path.exists() and path.with_suffix(".onnx.json").exists()):
        from piper.download_voices import download_voice
        log.info("downloading Piper voice %s", name)
        voices_dir.mkdir(parents=True, exist_ok=True)
        download_voice(name, voices_dir)
    return path


class PiperTTS:
    def __init__(self, name: str, voices_dir: Path):
        from piper import PiperVoice
        self.name = name
        self.voice = PiperVoice.load(str(fetch_voice(name, voices_dir)))
        self.sample_rate: int = self.voice.config.sample_rate

    def synthesize(self, text: str) -> Iterator[np.ndarray]:
        """Yield mono int16 audio, a chunk at a time."""
        for chunk in self.voice.synthesize(text):
            yield chunk.audio_int16_array.reshape(-1)
