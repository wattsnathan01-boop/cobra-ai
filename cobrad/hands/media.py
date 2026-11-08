"""Music, volume and screen brightness."""
from __future__ import annotations

from . import ToolError, sh, tool

SINK = "@DEFAULT_AUDIO_SINK@"


@tool("media",
      "Control music/video players. Actions: play_pause, next, previous, status "
      "(what's playing).",
      properties={"action": {"type": "string",
                             "enum": ["play_pause", "next", "previous", "status"]}},
      required=["action"],
      permission="always")
async def media(action: str) -> str:
    if action == "status":
        try:
            return await sh("playerctl", "metadata", "--format",
                            "{{status}}: {{artist}} - {{title}}")
        except ToolError:
            return "nothing is playing"
    cmd = {"play_pause": "play-pause", "next": "next", "previous": "previous"}.get(action)
    if not cmd:
        raise ToolError(f"unknown action '{action}'")
    await sh("playerctl", cmd)
    return "done"


@tool("volume",
      "Speaker volume. Actions: get, set (to level 0-100), up, down (by level, default 10), "
      "mute (toggle).",
      properties={"action": {"type": "string", "enum": ["get", "set", "up", "down", "mute"]},
                  "level": {"type": "integer", "minimum": 0, "maximum": 100}},
      required=["action"],
      permission="always")
async def volume(action: str, level: int | None = None) -> str:
    if action == "set":
        if level is None:
            raise ToolError("'set' needs a level")
        await sh("wpctl", "set-volume", SINK, f"{level}%")
    elif action in ("up", "down"):
        step = level or 10
        await sh("wpctl", "set-volume", "-l", "1", SINK, f"{step}%{'+' if action == 'up' else '-'}")
    elif action == "mute":
        await sh("wpctl", "set-mute", SINK, "toggle")
    elif action != "get":
        raise ToolError(f"unknown action '{action}'")
    # "Volume: 0.45 [MUTED]"
    out = await sh("wpctl", "get-volume", SINK)
    pct = round(float(out.split()[1]) * 100)
    return f"volume {pct}%" + (" (muted)" if "MUTED" in out else "")


@tool("brightness",
      "Screen brightness. Actions: get, set (to level 1-100), up, down (by level, default 10).",
      properties={"action": {"type": "string", "enum": ["get", "set", "up", "down"]},
                  "level": {"type": "integer", "minimum": 1, "maximum": 100}},
      required=["action"],
      permission="always")
async def brightness(action: str, level: int | None = None) -> str:
    if action == "set":
        if level is None:
            raise ToolError("'set' needs a level")
        await sh("brightnessctl", "set", f"{level}%")
    elif action in ("up", "down"):
        step = level or 10
        await sh("brightnessctl", "set", f"{step}%{'+' if action == 'up' else '-'}")
    elif action != "get":
        raise ToolError(f"unknown action '{action}'")
    # "intel_backlight,backlight,9600,50%,19200"
    out = await sh("brightnessctl", "-m")
    return f"brightness {out.split(',')[3]}"
