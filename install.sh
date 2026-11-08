#!/usr/bin/env bash
# ── Cobra · installer (Arch Linux) ───────────────
# Milestones 0–1: local brain (Ollama on the RTX 5060), cobrad daemon, cobractl CLI.
# Run as your normal user from the repo folder:  bash install.sh
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/.local/share/cobra"
CONF="$HOME/.config/cobra"
MODEL="qwen3:8b"

say() { printf '\n\033[38;2;59;240;182m==>\033[0m %s\n' "$*"; }

if [ "$EUID" -eq 0 ]; then
    echo "Run this as your normal user, not root." >&2
    exit 1
fi

find "$DIR" -path "$DIR/.git" -prune -o -type f \
    \( -name '*.sh' -o -name '*.py' -o -name '*.toml' -o -name '*.service' -o -name '*.md' \) \
    -exec sed -i 's/\r$//' {} +

say "Installing packages"
sudo pacman -S --needed python ollama-cuda gtk3 playerctl brightnessctl wireplumber

say "Starting Ollama (runs on the RTX 5060)"
sudo systemctl enable --now ollama
for _ in $(seq 1 20); do
    curl -fs http://localhost:11434/api/tags >/dev/null && break
    sleep 1
done

say "Downloading the local brain: $MODEL (~5 GB, one time)"
ollama pull "$MODEL"

say "Setting up Python environment"
python -m venv "$APP/venv"
"$APP/venv/bin/pip" install --quiet --upgrade pip
"$APP/venv/bin/pip" install --quiet -e "$DIR"
mkdir -p "$HOME/.local/bin"
ln -sf "$APP/venv/bin/cobractl" "$HOME/.local/bin/cobractl"

say "Config (existing files are kept)"
mkdir -p "$CONF"
for f in config.toml permissions.toml persona.md; do
    [ -e "$CONF/$f" ] || cp "$DIR/cobrad/defaults/$f" "$CONF/$f"
done

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

Then try:
    cobractl ask "how hot is my GPU?"
    cobractl chat

Logs:         journalctl --user -u cobra -f
Audit trail:  ~/.local/state/cobra/audit.jsonl
EOF
