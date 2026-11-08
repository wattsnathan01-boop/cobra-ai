"""The settings window's back end: a snapshot of every setting, and changing one at a time.

A change is written to the person's file in ~/.config/cobra (only that line, so their comments
survive) and applied to the running daemon straight away.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import tomllib
from pathlib import Path

from . import hands
from .config import DEFAULTS, config_dir, data_dir, load_allowed_folders, load_config
from .gate import LEVELS, NO_ALWAYS
from .hands import ToolError, files, sh

log = logging.getLogger(__name__)

# English single-speaker Piper voices worth offering, with what Piper doesn't record: who
# they sound like. (No Australian voice exists in Piper yet.)
VOICES = [
    ("en_GB-cori-high", "female", "British"),
    ("en_GB-cori-medium", "female", "British"),
    ("en_GB-jenny_dioco-medium", "female", "British"),
    ("en_GB-southern_english_female-low", "female", "Southern English"),
    ("en_GB-alba-medium", "female", "Scottish"),
    ("en_US-amy-medium", "female", "American"),
    ("en_US-kristin-medium", "female", "American"),
    ("en_US-lessac-high", "female", "American"),
    ("en_US-hfc_female-medium", "female", "American"),
    ("en_GB-alan-medium", "male", "British"),
    ("en_GB-northern_english_male-medium", "male", "Northern English"),
    ("en_US-ryan-high", "male", "American"),
    ("en_US-joe-medium", "male", "American"),
]
VOICE_MB = {"low": 63, "medium": 63, "high": 114}
PREVIEW_TEXT = "Hello. This is how I'd sound. Shall we get started?"


# ── writing the person's config files ─────────────────────────────────────

def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)  # a JSON string is a valid TOML basic string
    if isinstance(value, list):
        if not value:
            return "[]"
        return "[\n" + "".join(f"    {_toml_value(v)},\n" for v in value) + "]"
    raise ValueError(f"can't write {value!r} to TOML")


def set_toml(path: Path, section: str, key: str, value) -> None:
    """Set [section] key = value in a TOML file, keeping everything else (comments too)."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    line = f"{key} = {_toml_value(value)}"
    header = re.search(rf"(?m)^\[{re.escape(section)}\][ \t]*$", text)
    if header is None:
        text = text.rstrip() + ("\n\n" if text.strip() else "") + f"[{section}]\n{line}\n"
    else:
        start = header.end()
        nxt = re.search(r"(?m)^\[", text[start:])
        end = start + nxt.start() if nxt else len(text)
        body = text[start:end]
        # the key's value: one line, or a list opened with "[" and closed by "]" on its own line
        existing = re.search(
            rf"(?ms)^{re.escape(key)}[ \t]*=[ \t]*(\[[ \t]*\n.*?^\][ \t]*$|[^\n]*)", body)
        if existing:
            body = body[:existing.start()] + line + body[existing.end():]
        else:
            body = "\n" + line + body
        text = text[:start] + body + text[end:]
    tomllib.loads(text)  # never save a file that won't load
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ── reading ───────────────────────────────────────────────────────────────

async def _ollama(server) -> tuple[bool, list[dict]]:
    brain = server.agent.brain
    try:
        r = await brain.client.get("/api/tags")
        models = r.json().get("models", [])
    except Exception:
        return False, []
    return True, [{"name": m["name"], "size_gb": round(m.get("size", 0) / 1e9, 1)}
                  for m in sorted(models, key=lambda m: m["name"])]


async def _vram() -> dict:
    try:
        out = await sh("nvidia-smi", "--query-gpu=memory.used,memory.total",
                       "--format=csv,noheader,nounits")
        used, total = (int(x) for x in out.splitlines()[0].split(","))
        return {"used_mb": used, "total_mb": total}
    except (ToolError, ValueError):
        return {}


def _voices(current: str) -> list[dict]:
    piper_dir = data_dir() / "models" / "piper"
    out = []
    for name, gender, accent in VOICES:
        quality = name.rsplit("-", 1)[1]
        out.append({"name": name, "label": name.split("-")[1].replace("_", " "),
                    "gender": gender, "accent": accent, "quality": quality,
                    "installed": (piper_dir / f"{name}.onnx").exists(),
                    "size_mb": VOICE_MB.get(quality, 63), "current": name == current})
    if current not in {v[0] for v in VOICES}:
        out.insert(0, {"name": current, "label": current, "gender": "", "accent": "",
                       "quality": "", "installed": True, "size_mb": 0, "current": True})
    return out


def _memory(server, cfg) -> dict:
    mem = server.agent.memory
    if mem is None:
        return {"available": False, "facts": []}
    return {"available": True, "facts": mem.facts(), "resume_hours": mem.resume_hours,
            "file": str(mem.facts_path).replace(str(Path.home()), "~"), **mem.stats()}


def _tools(server) -> list[dict]:
    gate = server.agent.gate
    return [{"name": t.name, "level": gate.level(t.name), "default": t.permission}
            for t in hands.TOOLS.values()]


async def snapshot(server) -> dict:
    cfg = load_config()
    brain = server.agent.brain
    up, models = await _ollama(server)
    persona_file = config_dir() / "persona.md"
    default_persona = (DEFAULTS / "persona.md").read_text(encoding="utf-8")
    wake = server.wake
    return {
        "type": "settings",
        "brain": {"mode": cfg["brain"]["mode"], "host": cfg["local"]["host"],
                  "model": brain.model, "think": brain.think, "ollama_up": up,
                  "models": models, "vram": await _vram()},
        "claude": {"configured": False, "model": cfg["claude"]["model"],
                   "fast_model": cfg["claude"]["fast_model"]},
        "voice": {"current": server.info.get("voice", ""),
                  "voices": _voices(server.info.get("voice", ""))},
        "wake": {"enabled": bool(wake and wake.running),
                 "available": wake is not None,
                 "threshold": wake.start_threshold if wake else cfg["wake"]["threshold"],
                 "follow_up_seconds": server.follow_up_seconds},
        "persona": {"text": server.agent.persona,
                    "is_default": server.agent.persona.strip() == default_persona.strip(),
                    "customised": persona_file.exists()},
        "screen": {"hide": cfg["screen"]["hide"], "vision_model": cfg["local"]["vision_model"]},
        "memory": _memory(server, cfg),
        "permissions": {"tools": _tools(server),
                        "allowed": load_allowed_folders(),
                        "exists": {a: Path(a).expanduser().is_dir()
                                   for a in load_allowed_folders()}},
    }


# ── changing ──────────────────────────────────────────────────────────────

class SettingError(Exception):
    pass


async def apply(server, key: str, value) -> str:
    """Save one setting and apply it now. Returns a short note for the window."""
    user_cfg = config_dir() / "config.toml"

    if key == "local.model":
        up, models = await _ollama(server)
        if value not in {m["name"] for m in models}:
            raise SettingError(f"{value} isn't installed (ollama pull {value})")
        set_toml(user_cfg, "local", "model", value)
        server.agent.brain.model = value
        server.info["model"] = value
        await server.announce_hello()
        return f"now thinking with {value}"

    if key == "local.think":
        set_toml(user_cfg, "local", "think", bool(value))
        server.agent.brain.think = bool(value)
        return "thinking before answering " + ("on" if value else "off")

    if key == "voice.piper_voice":
        if value not in {v[0] for v in VOICES} and value != server.info.get("voice"):
            raise SettingError(f"unknown voice {value}")
        if server.voice is None or server.voice.speaker is None:
            raise SettingError("speech isn't running")
        from .voice.tts import PiperTTS
        tts = await asyncio.to_thread(PiperTTS, value, data_dir() / "models" / "piper")
        set_toml(user_cfg, "voice", "piper_voice", value)
        server.voice.speaker.tts = tts
        server.info["voice"] = value
        await server.announce_hello()
        return f"voice changed to {value}"

    if key == "wake.enabled":
        set_toml(user_cfg, "wake", "enabled", bool(value))
        await server.set_wake("on" if value else "off")
        return "wake word " + ("on" if value else "off")

    if key == "wake.threshold":
        value = round(min(0.9, max(0.2, float(value))), 2)
        set_toml(user_cfg, "wake", "threshold", value)
        if server.wake:
            server.wake.start_threshold = value
            server.wake.keep_threshold = value * 0.6
        return f"sensitivity set ({value})"

    if key == "wake.follow_up_seconds":
        value = int(min(20, max(3, int(value))))
        set_toml(user_cfg, "wake", "follow_up_seconds", value)
        server.follow_up_seconds = value
        return f"waits {value} s after “Cobra”"

    if key == "persona":
        text = str(value).strip() + "\n"
        if len(text) < 20:
            raise SettingError("that's too short to be a personality")
        (config_dir() / "persona.md").write_text(text, encoding="utf-8")
        server.agent.persona = text
        return "personality saved"

    if key == "persona.reset":
        text = (DEFAULTS / "persona.md").read_text(encoding="utf-8")
        (config_dir() / "persona.md").write_text(text, encoding="utf-8")
        server.agent.persona = text
        return "personality reset to the default"

    if key.startswith("permission."):
        tool = key.split(".", 1)[1]
        if tool not in hands.TOOLS:
            raise SettingError(f"unknown tool {tool}")
        if value not in LEVELS:
            raise SettingError(f"level must be one of {', '.join(LEVELS)}")
        if value == "always" and tool in NO_ALWAYS:
            raise SettingError("commands always ask first")
        set_toml(config_dir() / "permissions.toml", "tools", tool, value)
        server.agent.gate.policy[tool] = value
        return f"{tool}: {value}"

    if key == "screen.hide":
        words = sorted({str(w).strip().lower() for w in value if str(w).strip()})
        set_toml(user_cfg, "screen", "hide", words)
        from . import screen
        screen.SETTINGS["hide"] = words
        return "private windows list saved"

    if key.startswith("memory."):
        mem = server.agent.memory
        if mem is None:
            raise SettingError("memory isn't set up")
        if key == "memory.add":
            return mem.remember(str(value))
        if key == "memory.remove":
            gone = mem.forget(str(value))
            return "forgotten" if gone else "that wasn't remembered"
        if key == "memory.clear_conversation":
            server.agent.reset()
            return "started a fresh conversation"
        if key == "memory.clear_history":
            mem.clear_history()
            server.agent.history.clear()
            return "all saved conversations deleted"
        if key == "memory.resume_hours":
            value = float(min(72, max(0, float(value))))
            set_toml(user_cfg, "memory", "resume_hours", value)
            mem.resume_hours = value
            return f"carries on after a restart within {value:g} h" if value else "always starts fresh"

    if key == "files.allowed":
        folders = [str(f).strip() for f in value if str(f).strip()]
        for f in folders:
            if not f.startswith(("~/", "/")):
                raise SettingError(f"{f}: use a full path, like ~/notes")
        set_toml(config_dir() / "permissions.toml", "files", "allowed", folders)
        files.configure(folders)
        return "allowed folders saved"

    raise SettingError(f"unknown setting {key}")


async def preview_voice(name: str) -> None:
    """Say a short line in a voice (downloading it if needed), without switching to it."""
    if name not in {v[0] for v in VOICES}:
        raise SettingError(f"unknown voice {name}")
    from .voice.tts import PiperTTS

    def play():
        import numpy as np
        import sounddevice as sd
        tts = PiperTTS(name, data_dir() / "models" / "piper")
        audio = np.concatenate(list(tts.synthesize(PREVIEW_TEXT)))
        sd.play(audio, tts.sample_rate)
        sd.wait()
    await asyncio.to_thread(play)
