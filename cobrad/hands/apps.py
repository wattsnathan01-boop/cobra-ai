"""Launch installed apps by name, using their .desktop entries."""
from __future__ import annotations

import os
from pathlib import Path

import difflib

from . import ToolError, sh, tool
from .hypr import dispatch, lua_str

# what people call their browser; mapped to the default web browser
BROWSER_WORDS = {"browser", "web browser", "internet", "web", "google", "the internet"}


def _app_dirs() -> list[Path]:
    data_home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
    data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return [Path(d) / "applications" for d in [data_home, *data_dirs.split(":")]]


def _parse_desktop(path: Path) -> dict[str, str]:
    entry, in_main = {}, False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("["):
            in_main = line == "[Desktop Entry]"
        elif in_main and "=" in line:
            key, _, value = line.partition("=")
            entry.setdefault(key.strip(), value.strip())
    return entry


def installed_apps() -> dict[str, str]:
    """Map lowercase app name -> desktop id. Earlier dirs (user) win over system ones."""
    apps: dict[str, str] = {}
    for d in _app_dirs():
        if not d.is_dir():
            continue
        for f in d.glob("*.desktop"):
            e = _parse_desktop(f)
            if e.get("Type") != "Application" or e.get("NoDisplay") == "true" \
                    or e.get("Hidden") == "true" or "Name" not in e:
                continue
            apps.setdefault(e["Name"].lower(), f.stem)
    return apps


def match_app(apps: dict[str, str], name: str) -> tuple[str, str]:
    n = name.lower().strip()
    if n in apps:
        return n, apps[n]
    for app_name, desktop_id in apps.items():
        if n in app_name or n == desktop_id.lower():
            return app_name, desktop_id
    close = difflib.get_close_matches(n, list(apps), n=3, cutoff=0.5)
    hint = f" Close matches: {', '.join(close)}." if close else ""
    raise ToolError(f"no installed app called '{name}'.{hint} Use 'browser' for the web browser.")


async def default_browser(apps: dict[str, str]) -> tuple[str, str] | None:
    try:
        desktop = (await sh("xdg-settings", "get", "default-web-browser")).removesuffix(".desktop")
    except ToolError:
        return None
    for app_name, desktop_id in apps.items():
        if desktop_id == desktop:
            return app_name, desktop_id
    return None


@tool("apps_launch",
      "Open an installed application by name, e.g. 'files', 'steam', 'kitty'. Use 'browser' "
      "for the web browser (also when they say 'Google' or 'the internet').",
      properties={"name": {"type": "string"}},
      required=["name"],
      permission="always")
async def apps_launch(name: str) -> str:
    apps = installed_apps()
    found = await default_browser(apps) if name.lower().strip() in BROWSER_WORDS else None
    app_name, desktop_id = found or match_app(apps, name)
    # launched by Hyprland, not as a child of cobrad, so restarting Cobra doesn't close it
    await dispatch(f"hl.dsp.exec_cmd({lua_str('gtk-launch ' + desktop_id)})",
                   "exec", f"gtk-launch {desktop_id}")
    return f"launched {app_name}"
