# 🐍 Cobra

A JARVIS-style voice assistant for the [Cobra Queen](https://github.com/wattsnathan01-boop/cobra-queen-dots)
Hyprland setup. She runs locally on your GPU through Ollama, can use your system through
tools, and asks before doing anything risky.

![Full HUD](design/previews/1-full-hud.png)

> **Status: milestone 1 of 7.** Text chat with the local brain and system tools works.
> Voice, the overlay and screen sharing are next. See [PLAN.md](PLAN.md).

## Install (Arch)

```sh
git clone https://github.com/wattsnathan01-boop/cobra-ai.git ~/cobra-ai
cd ~/cobra-ai
bash install.sh
```

It installs Ollama (CUDA build), downloads `qwen3:8b` (~5 GB), sets up the `cobrad` service
and puts `cobractl` on your path.

## Use

```sh
cobractl ask "how hot is my GPU?"
cobractl ask "put youtube on workspace 3"
cobractl chat          # back-and-forth; /reset to start fresh
cobractl status
```

## What she can do so far

| Tool | Does | Permission |
|---|---|---|
| `system_stats` | CPU, RAM, temps, battery, GPU | always |
| `hypr_windows` | List open windows | always |
| `hypr_action` | Focus, move to workspace, switch workspace, fullscreen, float | always |
| `hypr_close` | Close a window | **ask** |
| `media` | Play/pause, next, previous, what's playing | always |
| `volume` / `brightness` | Get, set, up, down, mute | always |
| `apps_launch` | Open an installed app | always |

Change any of these in `~/.config/cobra/permissions.toml` (`always` / `ask` / `never`).
Every tool call is logged to `~/.local/state/cobra/audit.jsonl`.

## Config

| File | What |
|---|---|
| `~/.config/cobra/config.toml` | Model, Ollama address, voice, limits |
| `~/.config/cobra/permissions.toml` | What she may do without asking |
| `~/.config/cobra/persona.md` | Her personality |

Logs: `journalctl --user -u cobra -f`

## Tests

```sh
python -m unittest discover -s tests -v
```
