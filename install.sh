#!/usr/bin/env bash
# ── Cobra · installer (Arch Linux) ───────────────
# Milestones 0–4: local brain (Ollama on the RTX 5060), voice (Whisper + Piper),
# cobrad daemon, cobractl CLI, Quickshell overlay (mini pop-up and full HUD).
# Run as your normal user from the repo folder:  bash install.sh
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/.local/share/cobra"
CONF="$HOME/.config/cobra"
MODEL="qwen3:8b"
VISION="qwen3-vl:4b-instruct"

say() { printf '\n\033[38;2;59;240;182m==>\033[0m %s\n' "$*"; }

if [ "$EUID" -eq 0 ]; then
    echo "Run this as your normal user, not root." >&2
    exit 1
fi

find "$DIR" -path "$DIR/.git" -prune -o -type f \
    \( -name '*.sh' -o -name '*.py' -o -name '*.toml' -o -name '*.service' -o -name '*.md' \) \
    -exec sed -i 's/\r$//' {} +

say "Installing packages"
sudo pacman -S --needed python ollama-cuda gtk3 playerctl brightnessctl wireplumber portaudio quickshell

say "Starting Ollama (runs on the RTX 5060)"
sudo systemctl enable --now ollama
for _ in $(seq 1 20); do
    curl -fs http://localhost:11434/api/tags >/dev/null && break
    sleep 1
done

say "Downloading the local brain: $MODEL (~5 GB, one time)"
ollama pull "$MODEL"

say "Downloading the eyes: $VISION (~3.3 GB, one time; reads your screen, locally)"
ollama pull "$VISION"

say "Setting up Python environment"
python -m venv "$APP/venv"
"$APP/venv/bin/pip" install --quiet --upgrade pip
"$APP/venv/bin/pip" install --quiet -e "$DIR[gpu]"
mkdir -p "$HOME/.local/bin"
ln -sf "$APP/venv/bin/cobractl" "$HOME/.local/bin/cobractl"

say "Downloading the voice and Whisper (~1.7 GB, one time)"
"$APP/venv/bin/cobrad" fetch-models

say "Config (existing files are kept)"
mkdir -p "$CONF"
for f in config.toml permissions.toml persona.md; do
    [ -e "$CONF/$f" ] || cp "$DIR/cobrad/defaults/$f" "$CONF/$f"
done

say "Overlay (Quickshell)"
mkdir -p "$HOME/.config/quickshell"
ln -sfn "$DIR/ui" "$HOME/.config/quickshell/cobra"

say "Installing the service"
mkdir -p "$HOME/.config/systemd/user"
cp "$DIR/systemd/cobra.service" "$HOME/.config/systemd/user/cobra.service"
systemctl --user daemon-reload

# Hyprland's variables let cobrad talk to hyprctl; starting it now if we're inside Hyprland
if [ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]; then
    systemctl --user import-environment WAYLAND_DISPLAY HYPRLAND_INSTANCE_SIGNATURE XDG_CURRENT_DESKTOP
    systemctl --user restart cobra
fi

say "Done!"
cat <<'EOF'
Cobra starts with Hyprland once your dotfiles have this inside the
hl.on("hyprland.start", ...) block of ~/.config/hypr/hyprland.lua
(already there if you `git pull` cobra-queen-dots):

    hl.exec_cmd("systemctl --user import-environment WAYLAND_DISPLAY HYPRLAND_INSTANCE_SIGNATURE XDG_CURRENT_DESKTOP && systemctl --user start cobra")
    hl.exec_cmd("qs -n -c cobra")

and these with the other layer rules, to blur behind the pop-up and the HUD:

    hl.layer_rule({ name = "blur-cobra", match = { namespace = "cobra" }, blur = true, ignore_alpha = 0.2 })
    hl.layer_rule({ name = "blur-cobra-hud", match = { namespace = "cobra-hud" }, blur = true })

and this with the window rules, so the settings window floats:

    hl.window_rule({ name = "cobra-settings", match = { title = "^(Cobra settings)$" }, float = true, size = "1400 880", center = true })

For push-to-talk (hold SUPER+C) and the full HUD (SUPER+SHIFT+C), add to the keybinds in
~/.config/hypr/hyprland.lua:

    hl.bind(mod .. " + C", hl.dsp.exec_cmd("~/.local/bin/cobractl listen start"))
    hl.bind(mod .. " + C", hl.dsp.exec_cmd("~/.local/bin/cobractl listen stop"), { release = true })
    hl.bind(mod .. " + SHIFT + C", hl.dsp.exec_cmd("~/.local/bin/cobractl hud"))

For the eye badge (shown only while Cobra can see your screen), add "custom/cobra-eye" to
waybar's modules-right and this module:

    "custom/cobra-eye": {
        "exec": "~/.local/bin/cobractl eye",
        "return-type": "json",
        "on-click": "~/.local/bin/cobractl screen stop"
    }

Then try:
    cobractl ask "how hot is my GPU?"
    cobractl ask --say "say hello"
    cobractl chat
    cobractl watch     (shows what she hears and says while you use SUPER+C)
    cobractl settings  (brains, voice, wake word, personality, permissions)

Logs:         journalctl --user -u cobra -f
Audit trail:  ~/.local/state/cobra/audit.jsonl
EOF
