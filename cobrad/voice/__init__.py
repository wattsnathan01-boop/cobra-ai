"""Voice: Piper text-to-speech and playback."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Voice:
    """What the daemon hears and speaks with."""
    recorder: Any            # ears.mic.Recorder
    speaker: Any = None      # voice.speaker.Speaker; None if Piper couldn't start
    transcriber: Any = None  # ears.stt.Transcriber; None until Whisper has loaded
