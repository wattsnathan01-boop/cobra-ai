"""Window and workspace control through hyprctl."""
from __future__ import annotations

import json

from . import ToolError, sh, tool


async def _clients() -> list[dict]:
    return json.loads(await sh("hyprctl", "clients", "-j"))


async def _dispatch(*args: str) -> None:
    out = await sh("hyprctl", "dispatch", *args)
    if out and out.lower() != "ok":
        raise ToolError(out)


def find_window(clients: list[dict], target: str) -> dict:
    """Match a window by class or title, case-insensitive. Exact class wins over partials."""
    t = target.lower()
    for c in clients:
        if c.get("class", "").lower() == t:
            return c
    for c in clients:
        if t in c.get("class", "").lower() or t in c.get("title", "").lower():
            return c
    raise ToolError(f"no open window matches '{target}'")


@tool("hypr_windows",
      "List open windows (app class, title, workspace) and which one is focused.",
      permission="always")
async def hypr_windows() -> list[dict]:
    active = json.loads(await sh("hyprctl", "activewindow", "-j") or "{}")
    return [
        {"class": c.get("class"), "title": c.get("title"),
         "workspace": c.get("workspace", {}).get("id"),
         "focused": c.get("address") == active.get("address")}
        for c in await _clients()
    ]


@tool("hypr_action",
      "Control windows and workspaces. Actions: focus (a window), move (a window to a "
      "workspace), workspace (switch to a workspace), fullscreen, float (toggle floating). "
      "fullscreen and float apply to the focused window.",
      properties={
          "action": {"type": "string",
                     "enum": ["focus", "move", "workspace", "fullscreen", "float"]},
          "window": {"type": "string", "description": "App class or part of the title"},
          "workspace": {"type": "integer", "minimum": 1, "maximum": 10},
      },
      required=["action"],
      permission="always")
async def hypr_action(action: str, window: str | None = None,
                      workspace: int | None = None) -> str:
    if action in ("focus", "move") and not window:
        raise ToolError(f"'{action}' needs a window")
    if action in ("move", "workspace") and not workspace:
        raise ToolError(f"'{action}' needs a workspace number")

    if action == "focus":
        w = find_window(await _clients(), window)
        await _dispatch("focuswindow", f"address:{w['address']}")
        return f"focused {w['class']}"
    if action == "move":
        w = find_window(await _clients(), window)
        await _dispatch("movetoworkspacesilent", f"{workspace},address:{w['address']}")
        return f"moved {w['class']} to workspace {workspace}"
    if action == "workspace":
        await _dispatch("workspace", str(workspace))
        return f"switched to workspace {workspace}"
    if action == "fullscreen":
        await _dispatch("fullscreen", "0")
        return "toggled fullscreen"
    if action == "float":
        await _dispatch("togglefloating")
        return "toggled floating"
    raise ToolError(f"unknown action '{action}'")


@tool("hypr_close",
      "Close a window. Unsaved work in it may be lost.",
      properties={"window": {"type": "string", "description": "App class or part of the title"}},
      required=["window"],
      permission="ask")
async def hypr_close(window: str) -> str:
    w = find_window(await _clients(), window)
    await _dispatch("closewindow", f"address:{w['address']}")
    return f"closed {w['class']}"
