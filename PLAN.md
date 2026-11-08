# Cobra — build plan

A JARVIS-style voice assistant for the Cobra Queen Hyprland setup. You talk to her with your
mic, she answers out loud, she can see your screen and use your system, and she thinks with
either **Claude** (cloud) or a **local model** (Ollama on the RTX 5060).

Designs: [design/previews](design/previews) (1 Full HUD · 2 Mini pop-up · 3 Brains settings ·
4 Screen share · 5 Permissions · 6 Confirm pop-ups).

---

## 1. How it fits together

```
           mic ──► ┌──────────────────────── cobrad (Python daemon) ────────────────────────┐
                   │                                                                         │
                   │  Ears                Brain                     Hands                    │
                   │  ─────               ─────                     ─────                    │
                   │  wake word  ──►      Router ──► Claude API      Tools ──► Permission     │
                   │  push-to-talk        │     └──► Ollama (local)  (system, hypr,   gate    │
                   │  VAD + Whisper  ──►  │  conversation memory     files, shell,   │        │
                   │                      │                          screen, media)  ▼        │
                   │  Voice               ▼                                       audit log   │
 speakers ◄──────  │  Piper TTS  ◄── reply text (streamed sentence by sentence)               │
                   └────────────────────────────▲────────────────────────────────────────────┘
                                                │ JSON over a Unix socket
                     ┌──────────────────────────┴─────────────────────────┐
                     │  Quickshell overlay (QML)          waybar module    │
                     │  HUD · mini pop-up · confirm cards  · eye badge     │
                     └─────────────────────────────────────────────────────┘
```

Two programs:

- **`cobrad`**, a Python daemon (systemd user service) that does everything: audio, models, tools,
  permissions. It knows nothing about drawing.
- **The overlay**, built with **Quickshell**: a QML toolkit for Hyprland that draws
  see-through layers over the desktop (same QML family as the SDDM theme). It only draws what
  `cobrad` tells it and sends back button presses.

They talk over a Unix socket (`$XDG_RUNTIME_DIR/cobra.sock`) using one JSON message per line.
A tiny CLI, **`cobractl`**, uses the same socket, so Hyprland keybinds and waybar can drive Cobra too.

---

## 2. The pieces

### Ears: hearing you

| Part | Choice | Why |
|---|---|---|
| Mic capture | `sounddevice` (PipeWire via PortAudio) | Simple, low latency |
| Push-to-talk | `SUPER+C` hold → `cobractl listen start/stop` | Works from day one, no false triggers |
| Wake word | **openWakeWord** with a custom "Cobra" model | Runs on CPU, trainable from synthetic speech (no recordings needed) |
| End of speech | **Silero VAD** | Knows when you've stopped talking |
| Speech → text | **faster-whisper**, `large-v3-turbo` int8 on the GPU | Fast and accurate; ~1.5 GB VRAM |

### Voice: talking back

| Part | Choice | Why |
|---|---|---|
| Text → speech | **Piper**, British voice (e.g. `en_GB-cori-high`) | Runs on CPU in real time, sounds natural, fully local |
| Streaming | Speak each sentence as soon as it arrives | She starts talking ~1 s after you stop |
| Barge-in | Talking over her stops her speech | Feels like a conversation, not a voicemail |
| Lip-sync for the HUD | Send the output volume level to the overlay ~30×/s | Drives the hood bars in the design |
| Later upgrade | Kokoro TTS | Richer voice, still local, costs some GPU |

### Brain: thinking

**Claude** (via the official `anthropic` Python SDK):

| Model | ID | Price (input / output per 1M tokens) | Use for |
|---|---|---|---|
| Claude Opus 5.5 | `claude-opus-5-5` | $4 / $20 | Default: coding, files, screen questions, anything tricky |
| Claude Haiku 5.5 | `claude-haiku-5-5` | $0.10 / $0.50 | Quick chat when you choose speed over depth |

Notes for building it:
- Stream every reply, so speech starts on the first sentence.
- Opus 5.5 always thinks. Control how much with `effort` (`low` for quick voice replies,
  `high` for real work); its default is `medium`.
- Use **prompt caching** on the system prompt and tool list, which never change between turns.
  Repeat turns are then much cheaper and faster.
- Turn on the server-side **fallback** for refusals, so a blocked reply retries on another
  model instead of going silent.
- Tool loop: the SDK's **tool runner** with a per-turn hook. The hook is where the permission
  gate sits (every tool call stops there before it runs).

**Local** (Ollama on `localhost:11434`):

| Model | Size | Use for |
|---|---|---|
| `qwen3:8b` | ~5.2 GB | Default local brain; good at tool calling |
| `gemma3:4b` | ~3.3 GB | Local **vision** (reading your screen privately), and the fastest replies |

The RTX 5060 has **8 GB VRAM**. Whisper (~1.5 GB) + `qwen3:8b` (~5.2 GB) fits; swapping to a
vision model unloads the other (Ollama handles this automatically, with a ~2 s delay the first time).

**Router (Auto mode)**, rules first, simple to reason about:
1. You said "ask Claude" / "use local" → obey.
2. No internet → local.
3. Screen capture and "Screenshots stay local" is on → local vision.
4. Timers, media, system info, small talk → local.
5. Coding, files, long reasoning, anything local got wrong → Claude.

### Hands: tools

One set of tool definitions, shared by both brains:

| Tool | Does | Default permission |
|---|---|---|
| `system_stats` | CPU/GPU/RAM/temps/battery (`psutil`, `nvidia-smi`) | Always |
| `hypr` | Focus/move/open/close windows, switch workspace (`hyprctl -j`) | Always |
| `media` | Play/pause/skip, volume, brightness (`playerctl`, `wpctl`, `brightnessctl`) | Always |
| `apps_launch` | Start apps by name | Always |
| `screen_capture` | Screenshot whole screen or active window (`grim`) | Always (while open) |
| `screen_point` | Draw a highlight + note on screen (the "Line 13" callout) | Always |
| `files_read` / `files_search` | Read/search inside allowed folders | Always |
| `files_write` | Edit or create files, shown as a diff first | Ask first |
| `shell_run` | Run a shell command as you | Ask first |
| `sudo` actions | Go through **pkexec**, so your normal password prompt appears | Ask first |
| `files_delete` | — | Never |
| Passwords / keyring | — | Never (no tool exists) |

Claude can also use Anthropic's built-in **web search** tool for questions about the outside world.

### Screen sharing

- **Capture:** `grim` grabs the screen; `hyprctl activewindow -j` gives window positions.
- **Privacy:** before anything leaves the laptop, windows matching a blocklist (Bitwarden, banking
  tab titles) are painted black using their coordinates.
- **Cost control:** one screenshot to Claude is ~1,500–2,000 input tokens (≈ $0.007 on Opus 5.5).
  So "watching" **doesn't** stream frames to Claude every 2 s. It takes a frame when you ask,
  or when the screen changes a lot (a cheap local image diff), and continuous watching uses the
  **local** vision model.
- **Pointing:** the model returns a box in screenshot pixels; the overlay draws the highlight
  and callout there. Expect it to be roughly right, not pixel-perfect.
- **Always visible:** crimson screen edge, the waybar eye badge, and the "Cobra can see your
  screen" pill whenever capture is on. `ESC` stops it.

### Safety layer

- **Permission gate** in `cobrad`. Every tool call is checked against
  `~/.config/cobra/permissions.toml` before it runs. Always → run. Ask first → confirm
  pop-up (Y/N, or say "yes" / "no"), auto-deny after 20 s. Never → blocked card.
- **Allowed folders**: file tools resolve real paths and refuse anything outside the list
  (no `../` or symlink tricks).
- **Audit log**: every tool call, its arguments, the decision and the result go to
  `~/.local/state/cobra/audit.jsonl`.
- **Prompt injection**: text on your screen, in files or on web pages is treated as *data*.
  If a web page says "run this command", that still goes through the Ask-first pop-up.
- **Secrets**: the Claude API key is stored in the system keyring (`secret-tool`),
  never in a config file or the git repo.

### Memory & personality

- Conversation history in SQLite (`~/.local/share/cobra/cobra.db`). Recent turns go to the model,
  older ones get summarised.
- A small "things to remember" file she can add to when you say "remember that…".
- A personality prompt in `~/.config/cobra/persona.md` (calm, dry, a bit regal, short spoken
  answers, never reads out code; she puts it on screen instead).

---

## 3. Repo layout

```
cobra-ai/
├── cobrad/                 Python daemon (package)
│   ├── main.py             start-up, event loop
│   ├── bus.py              Unix-socket server, message types
│   ├── ears/               mic, wake word, VAD, whisper
│   ├── voice/              piper, playback, level meter
│   ├── brain/              claude.py, ollama.py, router.py, memory.py, persona
│   ├── hands/              one file per tool group
│   ├── gate.py             permissions + audit log
│   └── screen.py           capture, privacy masking, change detection
├── cobractl                CLI (keybinds, waybar, debugging)
├── ui/                     Quickshell QML
│   ├── shell.qml
│   ├── Hud.qml  Popup.qml  Confirm.qml  Watching.qml
│   ├── Character.qml       face, hood, voice bars
│   └── Theme.qml           Cobra Queen palette
├── config/                 default config.toml, permissions.toml, persona.md
├── systemd/cobra.service
├── install.sh
└── design/                 images + previews (already here)
```

It hooks into the dotfiles repo with a few lines: Hyprland keybinds, a layer rule for blur,
autostarting the overlay, and the waybar eye module.

---

## 4. Build order

Each step gives something usable on its own.

| # | Milestone | You can… |
|---|---|---|
| 0 | **Setup**: repo, Python env, Ollama + models, API key in keyring | — |
| 1 | **Text brain**: `cobractl ask "…"` → router → Claude/Ollama, streamed; tools: stats, media, hypr | Type questions in a terminal and have her control windows/music |
| 2 | **Voice**: push-to-talk, Whisper, Piper, barge-in | Hold SUPER+C and talk to her |
| 3 | **Mini pop-up**: Quickshell overlay, 4 states, live transcript, voice bars | See her react in the corner |
| 4 | **Full HUD**: character, hood animation, context + actions panels | The full JARVIS screen |
| 5 | **Permissions**: gate, confirm pop-ups, audit log, file + shell tools | Let her edit files and run commands safely |
| 6 | **Screen sharing**: capture, privacy masking, watching mode, eye badge, pointing | "Cobra, what's this error?" |
| 7 | **Wake word + polish**: train "Cobra", memory, persona, settings screens | Just say "Cobra" |

Rough effort: steps 1–3 are the core (a few sessions); 4–6 are the bulk; 7 is polish.

---

## 5. Costs

- **Local**: free once set up (electricity and some fan noise).
- **Claude** on Opus 5.5 at $4 / $20 per million tokens: a typical spoken exchange is
  ~3–5k tokens in (cached after the first turn) and ~200 out. Expect **roughly 1–3p per question**,
  a bit more with a screenshot. Using Auto routing so quick stuff goes local keeps a heavy
  day of use in the tens of pence. The settings screen shows the month's spend.

---

## 6. Risks & open questions

- **VRAM squeeze**: 8 GB is enough, but Whisper + an 8B model + a game won't all fit. Cobra
  should unload models when a game is running (`nvidia-smi` shows it) and fall back to Claude.
- **Wake-word false triggers**: start with push-to-talk; tune the wake word sensitivity later.
- **Quickshell is young**: its API changes between releases, so pin a version.
- **Screen pointing accuracy**: good enough for "this line / this button", not for tiny targets.
- **Your call**: Claude API account (needs a key and a few pounds of credit) or local-only
  to start? Which British voice? Male, female, or something more synthetic?
