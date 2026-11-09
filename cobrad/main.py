"""cobrad: the Cobra daemon."""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from . import hands
from .brain.agent import Agent
from .brain.memory import Memory
from .brain.ollama import OllamaBrain
from .brain.router import Router
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


def claude_key() -> str | None:
    """The Anthropic API key: an encrypted systemd credential (see README), or the
    ANTHROPIC_API_KEY environment variable when running by hand."""
    creds = os.environ.get("CREDENTIALS_DIRECTORY")
    if creds and (Path(creds) / "anthropic").exists():
        return (Path(creds) / "anthropic").read_text().strip() or None
    return os.environ.get("ANTHROPIC_API_KEY") or None


async def amain() -> None:
    cfg = load_config()

    hands.load_all()
    from . import screen
    from .hands import files
    files.configure(load_allowed_folders())
    from .hands import mcp
    await mcp.start_all(config_dir() / "mcp.json")  # tools from other apps (Pencil, …)
    screen.SETTINGS.update(host=cfg["local"]["host"], model=cfg["local"]["vision_model"],
                           hide=cfg["screen"]["hide"], max_side=cfg["screen"]["max_side"])
    local = cfg["local"]
    local_brain = OllamaBrain(local["host"], local["model"], local["think"], local["keep_alive"])
    if await local_brain.ping():
        log.info("Ollama is up, using %s", local["model"])
    else:
        log.warning("can't reach Ollama at %s yet; will keep trying per request", local["host"])

    gate = Gate(load_permissions(), state_dir() / "audit.jsonl", cfg["agent"]["confirm_timeout"],
                user_file=config_dir() / "permissions.toml")
    memory = Memory(data_dir() / "cobra.db", config_dir() / "memory.md",
                    cfg["memory"]["resume_hours"])
    claude = None
    if key := claude_key():
        from .brain.claude import ClaudeBrain
        claude = ClaudeBrain(key, cfg["claude"]["model"], cfg["claude"]["effort"],
                             on_usage=memory.record_usage, web=cfg["claude"].get("web", True))
        log.info("Claude is set up (%s); brain mode %s", cfg["claude"]["model"],
                 cfg["brain"]["mode"])
    else:
        log.info("no Claude API key; thinking locally")
    brain = Router(local_brain, claude, cfg["brain"]["mode"])
    agent = Agent(brain, gate, load_persona(), cfg["agent"]["max_steps"],
                  cfg["agent"]["history_turns"], memory)
    if agent.history:
        log.info("carrying on the conversation (%d messages)", len(agent.history))
    server = Server(agent, socket_path(), info={
        "brain": brain.mode, "model": local["model"], "claude": bool(claude),
        "claude_model": cfg["claude"]["model"], "voice": cfg["voice"]["piper_voice"],
        "stt": cfg["ears"]["whisper_model"]}, follow_up_seconds=cfg["wake"]["follow_up_seconds"])
    server.voice = setup_voice(cfg, server)
    screen.notify = server.screen_event
    agent.context = lambda: (
        "\nWatching mode is on: the person has asked you to keep an eye on their screen. "
        "When a question could be about what they're looking at, use screen_look."
        if screen.watching else "")
    from .hands import brain as brain_tools
    brain_tools.server = server
    from .hands import notebook as notebook_tools
    from .notebook import Notebook
    from .notebook.service import Service
    server.notebook = Service(Notebook(Path(cfg["notebook"]["dir"])), server)
    notebook_tools.open_window = lambda note_id="", page="": server._broadcast(
        {"type": "notebook_open", "id": note_id, "page": page})
    notebook_task = asyncio.create_task(server.notebook.run())
    await server.start()
    if server.voice:
        setup_wake(cfg, server)
    ears = asyncio.create_task(load_ears(cfg, server.voice)) if server.voice else None

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    notebook_task.cancel()
    if ears:
        ears.cancel()
    await mcp.stop_all()
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
