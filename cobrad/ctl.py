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


async def _ask(reader, writer, text: str) -> None:
    await _send(writer, {"type": "ask", "id": uuid.uuid4().hex, "text": text})
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
            allow = await _confirm(ev, mid_line)
            await _send(writer, {"type": "confirm_reply", "confirm_id": ev["confirm_id"],
                                 "allow": allow})
            mid_line = False
        elif kind == "error":
            print(f"\n{CRIMSON}  ! {ev['message']}{RESET}")
        elif kind == "done":
            print()
            return


async def _confirm(ev: dict, mid_line: bool) -> bool:
    print(f"{chr(10) if mid_line else ''}{VIOLET}  ? Cobra wants to use {ev['tool']} "
          f"{json.dumps(ev['args'])}. Allow? [y/N] {RESET}", end="", flush=True)
    if not sys.stdin.isatty():
        print("n (no terminal to ask)")
        return False
    answer = await asyncio.to_thread(sys.stdin.readline)
    return answer.strip().lower() in ("y", "yes")


async def _simple(reader, writer, msg: dict) -> None:
    await _send(writer, msg)
    print(json.loads(await reader.readline()).get("state", "?"))


async def amain(args: argparse.Namespace) -> None:
    reader, writer = await _connect()
    try:
        if args.cmd == "ask":
            await _ask(reader, writer, " ".join(args.text))
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
    ask.add_argument("text", nargs="+")
    sub.add_parser("chat", help="back-and-forth conversation")
    sub.add_parser("status", help="idle / thinking / speaking")
    sub.add_parser("reset", help="forget the conversation so far")
    try:
        asyncio.run(amain(p.parse_args(argv)))
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
