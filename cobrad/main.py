"""cobrad: the Cobra daemon."""
from __future__ import annotations

import asyncio
import logging
import signal
import sys

from . import hands
from .brain.agent import Agent
from .brain.ollama import OllamaBrain
from .bus import Server
from .config import (config_dir, data_dir, load_allowed_folders, load_config, load_permissions,
                     load_persona, socket_path, state_dir)
from .gate import Gate
from .voice import Voice

log = logging.getLogger("cobrad")


def _models_dir(kind: str):
    return data_dir() / "models" / kind


def setup_voice(cfg: dict, server: Server) -> Voice | None:
    """Mic and speech output. Whisper loads later, in the background (see load_ears)."""
    try:
        from .ears.mic import Recorder
        from .voice.speaker import Speaker
        from .voice.tts import PiperTTS
    except ImportError as e:
        log.warning("voice disabled, a package is missing (%s); re-run install.sh", e)
        return None
    voice = Voice(Recorder(cfg["ears"]["max_seconds"],
                           on_level=lambda v: server.level("mic", v)))
    try:
        tts = PiperTTS(cfg["voice"]["piper_voice"], _models_dir("piper"))
        voice.speaker = Speaker(tts, on_level=lambda v: server.level("voice", v))
        log.info("Piper voice %s ready", tts.name)
    except Exception:
        log.exception("Piper couldn't start; replies won't be spoken")
    return voice


def setup_wake(cfg: dict, server: Server) -> None:
    """Hands-free listening for "Cobra"."""
    from .ears.wake import WakeListener
    voice = server.voice
    server.wake = WakeListener(
        server.heard_phrase,
        busy=lambda: voice.recorder.recording or bool(voice.speaker and voice.speaker.speaking),
        threshold=cfg["wake"]["threshold"])
    if cfg["wake"]["enabled"]:
        try:
            server.wake.start()
        except Exception:
            log.exception("couldn't start the wake word; push-to-talk still works")


async def load_ears(cfg: dict, voice: Voice) -> None:
    from .ears.stt import Transcriber
    ears = cfg["ears"]
    try:
        voice.transcriber = await asyncio.to_thread(
            Transcriber, ears["whisper_model"], ears["device"], _models_dir("whisper"))
    except Exception:
        log.exception("Whisper couldn't start; push-to-talk won't work")


def fetch_models() -> None:
    """Download the voice and Whisper model up front (install.sh runs this)."""
    from faster_whisper.utils import download_model
    from .voice.tts import fetch_voice
    cfg = load_config()
    fetch_voice(cfg["voice"]["piper_voice"], _models_dir("piper"))
    log.info("fetching Whisper %s (downloads once)", cfg["ears"]["whisper_model"])
    download_model(cfg["ears"]["whisper_model"], cache_dir=str(_models_dir("whisper")))


async def amain() -> None:
    cfg = load_config()
    if cfg["brain"]["mode"] != "local":
        log.warning("brain mode '%s' isn't built yet; using local", cfg["brain"]["mode"])

    hands.load_all()
    from .hands import files
    files.configure(load_allowed_folders())
    local = cfg["local"]
    brain = OllamaBrain(local["host"], local["model"], local["think"], local["keep_alive"])
    if await brain.ping():
        log.info("Ollama is up, using %s", local["model"])
    else:
        log.warning("can't reach Ollama at %s yet; will keep trying per request", local["host"])

    gate = Gate(load_permissions(), state_dir() / "audit.jsonl", cfg["agent"]["confirm_timeout"],
                user_file=config_dir() / "permissions.toml")
    agent = Agent(brain, gate, load_persona(), cfg["agent"]["max_steps"],
                  cfg["agent"]["history_turns"])
    server = Server(agent, socket_path(), info={
        "brain": "local", "model": local["model"], "voice": cfg["voice"]["piper_voice"],
        "stt": cfg["ears"]["whisper_model"]}, follow_up_seconds=cfg["wake"]["follow_up_seconds"])
    server.voice = setup_voice(cfg, server)
    await server.start()
    if server.voice:
        setup_wake(cfg, server)
    ears = asyncio.create_task(load_ears(cfg, server.voice)) if server.voice else None

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    if ears:
        ears.cancel()
    await server.close()
    log.info("bye")


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    if sys.argv[1:] == ["fetch-models"]:
        fetch_models()
    else:
        asyncio.run(amain())


if __name__ == "__main__":
    run()
