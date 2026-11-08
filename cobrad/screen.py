"""Seeing the screen: capture with grim, black out private windows, ask the local vision model.

Nothing leaves the laptop. Before the vision model sees a frame, windows matching the hide list
(password managers, banking) are painted over. While Cobra looks, the overlay shows a crimson
edge and waybar shows the eye badge (see the "screen" events).
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

import httpx

from .hands import ToolError, sh, tool

log = logging.getLogger(__name__)

# set up by the daemon (main.py)
SETTINGS: dict = {"host": "http://localhost:11434", "model": "qwen3-vl:4b-instruct",
                  "hide": [], "max_side": 1280}
# the daemon's hook for indicator / pointing events
notify: Callable[[dict], Awaitable[None]] | None = None
watching = False

_POINT = re.compile(r"^\s*POINT:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_BBOX = re.compile(r'"bbox_2d"\s*:\s*\[\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*\]')

PROMPT = (
    "This is a screenshot of the user's screen{where}. Answer their question about it "
    "briefly and concretely: quote exact text (error messages, names) where it helps. Black "
    "rectangles are private windows hidden on purpose; ignore them.\n"
    "If the answer is about one specific thing on screen (a line, an error, a button), add a "
    "last line exactly like\nPOINT: <that thing, quoting its visible text>\n"
    "Otherwise don't add a POINT line.\n\nQuestion: {question}"
)
# Qwen-VL's own grounding prompt; it answers with JSON bbox_2d in 0-1000 coordinates
LOCATE = "Locate {thing} in the image, output its bbox coordinates using JSON format."


@dataclass
class Shot:
    png: bytes                  # what the vision model sees (masked, scaled)
    width: int                  # its size in pixels
    height: int
    monitor: str
    origin: tuple[float, float]  # top-left of the captured area, in layout coordinates
    size: tuple[float, float]    # its size in layout coordinates
    windows: list[str] = field(default_factory=list)  # what's visible, for "I can see …"
    hidden: int = 0


async def _json(*cmd: str):
    return json.loads(await sh(*cmd))


def _private(client: dict) -> bool:
    text = f"{client.get('class', '')} {client.get('title', '')}".lower()
    return any(h.lower() in text for h in SETTINGS["hide"])


async def capture(target: str = "screen") -> Shot:
    """The focused monitor (or just the active window), private windows blacked out."""
    from PIL import Image, ImageDraw

    monitors = await _json("hyprctl", "monitors", "-j")
    mon = next((m for m in monitors if m.get("focused")), monitors[0])
    scale = float(mon.get("scale", 1)) or 1
    mx, my = mon["x"], mon["y"]
    mw, mh = mon["width"] / scale, mon["height"] / scale  # layout size
    if mon.get("transform", 0) % 2:
        mw, mh = mh, mw

    region = (mx, my, mw, mh)
    if target == "window":
        win = await _json("hyprctl", "activewindow", "-j")
        if not win:
            raise ToolError("no window is focused")
        if _private(win):
            raise ToolError("the focused window is on the private list, so I won't look at it")
        region = (*win["at"], *win["size"])

    x, y, w, h = region
    raw = await sh_bytes("grim", "-g", f"{x},{y} {w}x{h}", "-t", "png", "-")
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    px = img.width / w  # image pixels per layout pixel

    # what's on this monitor's visible workspaces
    ws = {mon["activeWorkspace"]["id"], (mon.get("specialWorkspace") or {}).get("id")}
    clients = [c for c in await _json("hyprctl", "clients", "-j")
               if c.get("monitor") == mon["id"] and c.get("workspace", {}).get("id") in ws
               and c.get("mapped", True) and not c.get("hidden", False)]
    draw, hidden, names = ImageDraw.Draw(img), 0, []
    for c in clients:
        cx, cy = c["at"]
        cw, ch = c["size"]
        if cx + cw <= x or cy + ch <= y or cx >= x + w or cy >= y + h:
            continue  # not in the captured area
        if _private(c):
            draw.rectangle([(cx - x) * px, (cy - y) * px, (cx - x + cw) * px, (cy - y + ch) * px],
                           fill="black")
            hidden += 1
        elif c.get("class"):
            names.append(c["class"])

    side = SETTINGS["max_side"]
    if max(img.size) > side:
        img.thumbnail((side, side))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return Shot(buf.getvalue(), img.width, img.height, mon["name"], (x, y), (w, h),
                sorted(set(names)), hidden)


async def sh_bytes(*cmd: str, timeout: float = 10) -> bytes:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except FileNotFoundError:
        raise ToolError(f"{cmd[0]} is not installed")
    out, err = await asyncio.wait_for(proc.communicate(), timeout)
    if proc.returncode != 0:
        raise ToolError(err.decode(errors="replace").strip() or f"{cmd[0]} failed")
    return out


async def ask_vision(shot: Shot, question: str, target: str = "screen") -> str:
    where = " (only the focused window)" if target == "window" else ""
    return await _vision(shot, PROMPT.format(where=where, question=question))


async def _vision(shot: Shot, prompt: str) -> str:
    body = {
        "model": SETTINGS["model"],
        "messages": [{"role": "user", "content": prompt,
                      "images": [base64.b64encode(shot.png).decode()]}],
        "stream": False,
        "keep_alive": "2m",  # free the VRAM soon; the main brain needs it back
        "options": {"temperature": 0.2, "num_ctx": 8192},
    }
    try:
        async with httpx.AsyncClient(base_url=SETTINGS["host"], timeout=180) as client:
            r = await client.post("/api/chat", json=body)
    except httpx.ConnectError:
        raise ToolError("can't reach Ollama for the vision model")
    if r.status_code == 404:
        raise ToolError(f"the vision model isn't installed: ollama pull {SETTINGS['model']}")
    if r.status_code != 200:
        raise ToolError(f"vision model failed: {r.text[:200]}")
    return r.json().get("message", {}).get("content", "").strip()


def split_point(answer: str) -> tuple[str, str | None]:
    """The answer without its POINT line, and what to point at (if anything)."""
    m = _POINT.search(answer)
    if not m:
        return answer.strip(), None
    return (answer[:m.start()] + answer[m.end():]).strip(), m.group(1).strip().rstrip(".")


async def locate(shot: Shot, thing: str) -> dict | None:
    """Where `thing` is, in screen layout coordinates (roughly), or None."""
    try:
        out = await _vision(shot, LOCATE.format(thing=thing))
    except ToolError:
        return None
    return find_box(out, shot)


def find_box(out: str, shot: Shot) -> dict | None:
    """Map a bbox_2d (0-1000, or image pixels) onto the screen."""
    m = _BBOX.search(out)
    if not m:
        return None
    x1, y1, x2, y2 = (float(v) for v in m.groups())
    if max(x1, y1, x2, y2) > 1000:  # it answered in image pixels instead
        x1, x2 = x1 / shot.width * 1000, x2 / shot.width * 1000
        y1, y2 = y1 / shot.height * 1000, y2 / shot.height * 1000
    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))
    if x2 - x1 < 2 or y2 - y1 < 2:
        return None
    ox, oy = shot.origin
    w, h = shot.size
    return {"x": ox + x1 / 1000 * w, "y": oy + y1 / 1000 * h,
            "w": (x2 - x1) / 1000 * w, "h": (y2 - y1) / 1000 * h}


async def _emit(ev: dict) -> None:
    if notify:
        try:
            await notify(ev)
        except Exception:
            log.exception("screen event failed")


@tool("screen_look",
      "Look at the person's screen (or just the focused window) and answer a question about "
      "what's on it: errors, code, settings, what something is. Use it whenever they say "
      "\"this\", \"here\", \"on my screen\" or ask about something they're looking at. If the "
      "answer is about one place on screen it gets highlighted for them.",
      properties={"question": {"type": "string", "description": "what to find out"},
                  "target": {"type": "string", "enum": ["screen", "window"],
                             "description": "the whole focused monitor (default) or just the "
                                            "focused window"}},
      required=["question"],
      permission="always")
async def screen_look(question: str, target: str = "screen") -> str:
    started = time.monotonic()
    # the full HUD covers the whole screen: get it out of the way so she sees what's behind it
    await _emit({"type": "hud", "action": "hide"})
    await asyncio.sleep(0.35)  # its fade-out
    shot = await capture(target)
    await _emit({"type": "screen", "state": "looking", "monitor": shot.monitor,
                 "windows": shot.windows})
    try:
        text, thing = split_point(await ask_vision(shot, question, target))
        box = await locate(shot, thing) if thing else None
    finally:
        await _emit({"type": "screen", "state": "watching" if watching else "off",
                     "monitor": shot.monitor, "windows": shot.windows})
    if box:
        await _emit({"type": "point", "monitor": shot.monitor, **box,
                     "note": text[:300]})
    log.info("looked at %s in %.1f s (%d hidden)", shot.monitor, time.monotonic() - started,
             shot.hidden)
    seen = f"Visible windows: {', '.join(shot.windows) or 'none'}."
    if shot.hidden:
        seen += f" {shot.hidden} private window(s) were blacked out."
    return f"{text}\n({seen}{' The spot is highlighted on screen.' if box else ''})"


@tool("screen_watch",
      "Start or stop watching mode: the screen indicator stays on and you look at the screen "
      "whenever the question might be about it. Use when they say \"watch my screen\" or "
      "\"stop watching\".",
      properties={"on": {"type": "boolean"}},
      required=["on"],
      permission="always")
async def screen_watch(on: bool) -> str:
    global watching
    watching = bool(on)
    await _emit({"type": "screen", "state": "watching" if watching else "off"})
    return "watching the screen" if watching else "stopped watching the screen"
