"""Config and paths. Defaults ship in cobrad/defaults; ~/.config/cobra overrides them."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

DEFAULTS = Path(__file__).resolve().parent / "defaults"


def _xdg(var: str, fallback: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / fallback)


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config") / "cobra"


def state_dir() -> Path:
    return _xdg("XDG_STATE_HOME", ".local/state") / "cobra"


def data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share") / "cobra"


def socket_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/cobra-{os.getuid()}"
    return Path(runtime) / "cobra.sock"


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _load_toml(name: str) -> dict:
    with open(DEFAULTS / name, "rb") as f:
        data = tomllib.load(f)
    user = config_dir() / name
    if user.exists():
        with open(user, "rb") as f:
            data = _merge(data, tomllib.load(f))
    return data


def load_config() -> dict:
    return _load_toml("config.toml")


def load_permissions() -> dict[str, str]:
    return _load_toml("permissions.toml").get("tools", {})


def load_persona() -> str:
    user = config_dir() / "persona.md"
    return (user if user.exists() else DEFAULTS / "persona.md").read_text(encoding="utf-8")
