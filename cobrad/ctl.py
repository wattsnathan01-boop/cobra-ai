"""cobractl: talk to cobrad from a terminal, keybind or script."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid

from .config import socket_path

MINT, VIOLET, CRIMSON, MUTED, RESET = (
    "\033[38;2;59;240;182m", "\033[38;2;138;123;255m", "\033[38;2;255;45;99m",
    "\033[38;2;134;160;154m", "\033[0m")


async def _connect():
    try:
        return await asyncio.open_unix_connection(str(socket_path()))
    except (FileNotFoundError, ConnectionRefusedError):
        sys.exit(f"{CRIMSON}cobrad isn't running.{RESET} Start it with: systemctl --user start cobra")


async def _send(writer: asyncio.StreamWriter, msg: dict) -> None:
    writer.write(json.dumps(msg).encode() + b"\n")
    await writer.drain()


async def _ask(reader, writer, text: str, speak: bool = False) -> None:
    await _send(writer, {"type": "ask", "id": uuid.uuid4().hex, "text": text, "speak": speak})
    print(f"{MINT}cobra ›{RESET} ", end="", flush=True)
    mid_line = False
    async for line in reader:
        ev = json.loads(line)
        kind = ev.get("type")
        if kind == "delta":
            print(ev["text"], end="", flush=True)
            mid_line = True
        elif kind == "tool" and ev["status"] in ("running", "done", "failed"):
            if ev["status"] == "running":
                continue
            colour = MUTED if ev["status"] == "done" else CRIMSON
            mark = "✓" if ev["status"] == "done" else "✗"
            print(f"{chr(10) if mid_line else ''}{colour}  {mark} {ev['name']} "
                  f"{json.dumps(ev['args'])}{RESET}")
            print(f"{MINT}cobra ›{RESET} ", end="", flush=True)
            mid_line = False
        elif kind == "confirm":
            answer = await _confirm(ev, mid_line)
            if answer is not None:
                await _send(writer, {"type": "confirm_reply", "confirm_id": ev["confirm_id"],
                                     "allow": answer[0], "remember": answer[1]})
            mid_line = False
        elif kind == "confirmed":
            print(f"{MUTED}    {'allowed' if ev['allow'] else 'denied'}{RESET}")
            print(f"{MINT}cobra \u203a{RESET} ", end="", flush=True)
        elif kind == "blocked":
            print(f"{chr(10) if mid_line else ''}{CRIMSON}  \u2298 blocked: {ev['tool']} is set "
                  f"to never{RESET}")
            mid_line = False
        elif kind == "error":
            print(f"\n{CRIMSON}  ! {ev['message']}{RESET}")
        elif kind == "done":
            print()
            if not speak:
                return
        elif kind == "state" and ev["state"] == "idle" and speak:
            return  # stay connected until she's finished talking, or she'd be cut short


def _show_preview(ev: dict) -> None:
    p = ev.get("preview") or {}
    if p.get("kind") == "command":
        print(f"{MUTED}    {'#' if p.get('root') else '$'} {RESET}{p['command']}"
              f"{MUTED}   (in {p['cwd']}){RESET}")
    elif p.get("kind") in ("edit", "create"):
        print(f"{MUTED}    {p['path']} \u00b7 {p['summary']}{RESET}")
        for d in p.get("diff", []):
            colour = {"+": MINT, "-": CRIMSON}.get(d["op"], MUTED)
            print(f"{colour}    {d['op'] if d['op'] in '+-' else ' '} {d['text']}{RESET}")
    elif p.get("kind") == "packages":
        for pkg in p["packages"]:
            note = "already installed" if pkg["installed"] else \
                f"{'AUR' if pkg['source'] == 'aur' else pkg['source']} {pkg['size']}".strip()
            print(f"{MUTED}    {pkg['name']} {pkg['version']}  ({note}){RESET}")
        if p.get("warning"):
            print(f"{CRIMSON}    {p['warning']}{RESET}")
    else:
        print(f"{MUTED}    {json.dumps(ev['args'])}{RESET}")


async def _confirm(ev: dict, mid_line: bool) -> tuple[bool, bool] | None:
    """(allow, remember), or None when an on-screen card is asking instead."""
    print(f"{chr(10) if mid_line else ''}{VIOLET}  ? Cobra wants to use {ev['tool']}{RESET}")
    _show_preview(ev)
    if ev.get("card"):
        print(f"{VIOLET}    answer on screen (Y / N) or say yes / no{RESET}")
        return None
    always = ev.get("always")
    print(f"{VIOLET}    Allow? [y/N{'/a = always' if always else ''}] {RESET}", end="", flush=True)
    if not sys.stdin.isatty():
        print("n (no terminal to ask)")
        return False, False
    answer = (await asyncio.to_thread(sys.stdin.readline)).strip().lower()
    if always and answer in ("a", "always"):
        return True, True
    return answer in ("y", "yes"), False


async def _watch(reader, writer) -> None:
    """Show what Cobra hears, thinks and says, live (until the overlay exists)."""
    await _send(writer, {"type": "subscribe"})
    print(f"{MUTED}Watching Cobra. Ctrl+C to stop.{RESET}")
    mid_line = False
    async for line in reader:
        ev = json.loads(line)
        kind = ev.get("type")
        if kind == "state" and ev["state"] in ("listening", "thinking"):
            print(f"{chr(10) if mid_line else ''}{MUTED}  … {ev['state']}{RESET}")
            mid_line = False
        elif kind == "heard":
            print(f"{chr(10) if mid_line else ''}{VIOLET}you ›{RESET} {ev['text']}")
            mid_line = False
        elif kind == "delta":
            if not mid_line:
                print(f"{MINT}cobra ›{RESET} ", end="")
            print(ev["text"], end="", flush=True)
            mid_line = True
        elif kind == "tool" and ev["status"] in ("done", "failed"):
            colour = MUTED if ev["status"] == "done" else CRIMSON
            print(f"{chr(10) if mid_line else ''}{colour}  {'✓' if ev['status'] == 'done' else '✗'} "
                  f"{ev['name']} {json.dumps(ev['args'])}{RESET}")
            mid_line = False
        elif kind == "confirm":
            print(f"{chr(10) if mid_line else ''}{VIOLET}  ? wants to use {ev['tool']} "
                  f"{json.dumps(ev['args'])}; say yes or no{RESET}")
            mid_line = False
        elif kind == "error":
            print(f"{chr(10) if mid_line else ''}{CRIMSON}  ! {ev['message']}{RESET}")
            mid_line = False
        elif kind == "done" and mid_line:
            print()
            mid_line = False


def _eye_line(ev: dict) -> str:
    state = ev.get("state", "off")
    windows = ", ".join(ev.get("windows") or [])
    if state == "off":
        return json.dumps({"text": "", "class": "off"})
    return json.dumps({
        "text": "\U000f0208  COBRA",  # eye
        "class": state,
        "tooltip": ("Cobra is looking at your screen" if state == "looking"
                    else "Cobra is watching your screen (click to stop)")
                   + (f"\n{windows}" if windows else ""),
    })


async def eye() -> None:
    """For a waybar custom module: one JSON line whenever the screen indicator changes.
    Keeps going (and reconnects) if cobrad restarts."""
    while True:
        try:
            reader, writer = await asyncio.open_unix_connection(str(socket_path()))
        except (FileNotFoundError, ConnectionRefusedError):
            print(_eye_line({}), flush=True)
            await asyncio.sleep(3)
            continue
        await _send(writer, {"type": "subscribe"})
        try:
            async for line in reader:
                ev = json.loads(line)
                if ev.get("type") == "screen":
                    print(_eye_line(ev), flush=True)
        except (ConnectionError, json.JSONDecodeError):
            pass
        writer.close()
        print(_eye_line({}), flush=True)
        await asyncio.sleep(1)


async def _simple(reader, writer, msg: dict) -> None:
    await _send(writer, msg)
    print(json.loads(await reader.readline()).get("state", "?"))


async def amain(args: argparse.Namespace) -> None:
    reader, writer = await _connect()
    try:
        if args.cmd == "ask":
            await _ask(reader, writer, " ".join(args.text), args.say)
        elif args.cmd == "chat":
            print(f"{MUTED}Talking to Cobra. Ctrl+D to leave, /reset to start fresh.{RESET}")
            while True:
                try:
                    text = await asyncio.to_thread(input, f"{VIOLET}you ›{RESET} ")
                except EOFError:
                    print()
                    break
                if text.strip() == "/reset":
                    await _simple(reader, writer, {"type": "reset"})
                elif text.strip():
                    await _ask(reader, writer, text)
        elif args.cmd == "listen":
            await _send(writer, {"type": "listen", "action": args.action})
        elif args.cmd == "wake":
            await _send(writer, {"type": "wake", "action": args.action})
            ev = json.loads(await reader.readline())
            print("on" if ev.get("on") else ev.get("message", "off"))
        elif args.cmd == "screen":
            await _send(writer, {"type": "screen", "action": args.action})
            print(json.loads(await reader.readline()).get("state", "?"))
        elif args.cmd == "settings":
            await _send(writer, {"type": "open_settings", "page": args.page or ""})
        elif args.cmd == "hud":
            await _send(writer, {"type": "hud", "action": args.action})
        elif args.cmd == "hush":
            await _send(writer, {"type": "hush"})
        elif args.cmd == "watch":
            await _watch(reader, writer)
        elif args.cmd == "status":
            await _simple(reader, writer, {"type": "status"})
        elif args.cmd == "reset":
            await _simple(reader, writer, {"type": "reset"})
    finally:
        writer.close()


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="cobractl", description="Talk to Cobra.")
    sub = p.add_subparsers(dest="cmd", required=True)
    ask = sub.add_parser("ask", help="ask one question")
    ask.add_argument("--say", action="store_true", help="speak the reply out loud too")
    ask.add_argument("text", nargs="+")
    sub.add_parser("chat", help="back-and-forth conversation")
    listen = sub.add_parser("listen", help="push-to-talk (bind start to key press, stop to release)")
    listen.add_argument("action", choices=["start", "stop", "toggle", "cancel"])
    sub.add_parser("hush", help="stop talking")
    wake = sub.add_parser("wake", help='turn the "Cobra" wake word on or off')
    wake.add_argument("action", nargs="?", default="toggle", choices=["toggle", "on", "off"])
    sc = sub.add_parser("screen", help="watching mode: Cobra keeps an eye on your screen")
    sc.add_argument("action", choices=["watch", "stop"])
    sub.add_parser("eye", help="waybar module: prints the screen indicator as JSON lines")
    st = sub.add_parser("settings", help="open the settings window")
    st.add_argument("page", nargs="?", choices=["brains", "voice", "wake", "personality",
                                                "memory", "permissions", "shortcuts"])
    hud = sub.add_parser("hud", help="open or close the full HUD")
    hud.add_argument("action", nargs="?", default="toggle", choices=["toggle", "show", "hide"])
    sub.add_parser("watch", help="show what she hears and says, live")
    sub.add_parser("status", help="idle / listening / thinking / speaking")
    sub.add_parser("reset", help="forget the conversation so far")
    args = p.parse_args(argv)
    try:
        asyncio.run(eye() if args.cmd == "eye" else amain(args))
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
