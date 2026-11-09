"""Switching her brain by voice: local, Claude or Auto (same as Settings → Brains)."""
from __future__ import annotations

from . import ToolError, tool

# set by the daemon: the bus Server, whose settings code saves and applies the change
server = None


@tool("brain_mode",
      "Switch which brain you think with, when the person asks: \"local\" (free, on their "
      "GPU), \"claude\" (cloud, smarter, costs a little) or \"auto\" (you pick per question). "
      "It's saved and applies from their next question.",
      properties={"mode": {"type": "string", "enum": ["local", "claude", "auto"]}},
      required=["mode"],
      permission="always")
async def brain_mode(mode: str) -> str:
    from .. import settings
    if server is None:
        raise ToolError("can't switch brains right now")
    try:
        note = await settings.apply(server, "brain.mode", mode)
    except settings.SettingError as e:
        raise ToolError(str(e))
    return f"Done: {note} from the next question. Tell them briefly."
