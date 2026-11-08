"""cobrad: the Cobra daemon."""
from __future__ import annotations

import asyncio
import logging
import signal

from . import hands
from .brain.agent import Agent
from .brain.ollama import OllamaBrain
from .bus import Server
from .config import load_config, load_permissions, load_persona, socket_path, state_dir
from .gate import Gate

log = logging.getLogger("cobrad")


async def amain() -> None:
    cfg = load_config()
    if cfg["brain"]["mode"] != "local":
        log.warning("brain mode '%s' isn't built yet; using local", cfg["brain"]["mode"])

    hands.load_all()
    local = cfg["local"]
    brain = OllamaBrain(local["host"], local["model"], local["think"], local["keep_alive"])
    if await brain.ping():
        log.info("Ollama is up, using %s", local["model"])
    else:
        log.warning("can't reach Ollama at %s yet; will keep trying per request", local["host"])

    gate = Gate(load_permissions(), state_dir() / "audit.jsonl", cfg["agent"]["confirm_timeout"])
    agent = Agent(brain, gate, load_persona(), cfg["agent"]["max_steps"],
                  cfg["agent"]["history_turns"])
    server = Server(agent, socket_path())
    await server.start()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    await server.close()
    log.info("bye")


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    asyncio.run(amain())


if __name__ == "__main__":
    run()
