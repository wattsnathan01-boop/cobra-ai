"""Speech → text with faster-whisper, on the GPU when it can be."""
from __future__ import annotations

import ctypes
import glob
import logging
import os
import threading
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)


# strict mode drops a segment when Whisper thinks it wasn't speech AND wasn't sure of the
# words (its own silence rule), or when it's all but certain it wasn't speech. Stricter than
# this and quiet speech gets dropped too, so you have to raise your voice for her.
NO_SPEECH = 0.6
MIN_LOGPROB = -1.0
SURELY_NOT_SPEECH = 0.9


def _is_speech(s) -> bool:
    if s.no_speech_prob > SURELY_NOT_SPEECH:
        return False
    return not (s.no_speech_prob > NO_SPEECH and s.avg_logprob < MIN_LOGPROB)


def _preload_cuda12() -> None:
    """CTranslate2 (under faster-whisper) is built for CUDA 12, but Arch ships CUDA 13. The CUDA 12
    cuBLAS and cuDNN come from NVIDIA's pip wheels instead; load them up front so CTranslate2
    finds them without LD_LIBRARY_PATH."""
    for name in ("nvidia.cublas", "nvidia.cudnn"):
        try:
            mod = __import__(name, fromlist=["_"])
        except ImportError:
            continue
        libs = sorted(glob.glob(os.path.join(list(mod.__path__)[0], "lib", "*.so.*")))
        # some libraries need others loaded first; keep retrying until nothing more loads
        while libs:
            failed = []
            for lib in libs:
                try:
                    ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
                except OSError:
                    failed.append(lib)
            if len(failed) == len(libs):
                log.warning("couldn't load %s", ", ".join(os.path.basename(f) for f in failed))
                break
            libs = failed


class Transcriber:
    def __init__(self, model: str, device: str, models_dir: Path):
        """device: "cuda", "cpu" or "auto" (GPU if it works, else CPU)."""
        from faster_whisper import WhisperModel

        self._lock = threading.Lock()  # live transcripts and the final one take turns
        attempts = [("cuda", "int8_float16"), ("cpu", "int8")]
        if device != "auto":
            attempts = [a for a in attempts if a[0] == device]
        error = None
        for dev, compute in attempts:
            try:
                if dev == "cuda":
                    _preload_cuda12()
                self.model = WhisperModel(model, device=dev, compute_type=compute,
                                          download_root=str(models_dir))
                self._run(np.zeros(16000, np.float32), vad=False)  # warm up / prove it works
                self.device = dev
                log.info("Whisper %s ready on %s", model, dev)
                return
            except Exception as e:
                log.warning("Whisper on %s failed: %s", dev, e)
                error = e
        raise RuntimeError(f"couldn't start Whisper: {error}")

    def transcribe(self, audio: np.ndarray, prompt: str | None = None, beam: int = 1,
                   strict: bool = False) -> str:
        """audio: mono float32 at 16 kHz. Returns "" if nobody spoke.
        prompt: text Whisper treats as what came before, to make words like "Cobra" likelier.
        strict: drop what Whisper isn't sure was speech (for the always-on mic, where music
        and noise otherwise come out as made-up words, often the prompt repeated back)."""
        return self._run(audio, vad=True, prompt=prompt, beam=beam, strict=strict)

    def _run(self, audio: np.ndarray, vad: bool, prompt: str | None = None, beam: int = 1,
             strict: bool = False) -> str:
        with self._lock:
            segments, _ = self.model.transcribe(audio, language="en", beam_size=beam,
                                                vad_filter=vad, condition_on_previous_text=False,
                                                initial_prompt=prompt)
            kept = []
            for seg in segments:
                if not strict or _is_speech(seg):
                    kept.append(seg.text.strip())
                else:  # scores only: what was (maybe) said isn't logged
                    log.info("dropped unsure speech (no_speech %.2f, logprob %.2f)",
                             seg.no_speech_prob, seg.avg_logprob)
            return " ".join(kept).strip()
