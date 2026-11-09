"""Skills: folders of how-to guides (a SKILL.md plus extra pages), the same format Claude Code
uses, so a skill installed for Claude Code (~/.claude/skills) works for Cobra too. She only
reads them; doing the work still goes through her other tools and their permissions."""
from __future__ import annotations

import re
from pathlib import Path

from . import ToolError, tool

# set from [skills] dirs in config.toml; earlier folders win when two have the same skill
DIRS: list[Path] = [Path("~/.config/cobra/skills").expanduser(),
                    Path("~/.claude/skills").expanduser()]
MAX_CHARS = 40_000
_TEXT = {".md", ".txt", ".yaml", ".yml", ".json", ".ts", ".tsx", ".js", ".py", ".sh", ".css"}


def configure(dirs: list[str]) -> None:
    DIRS[:] = [Path(d).expanduser() for d in dirs]


def _front(text: str) -> dict[str, str]:
    """The "key: value" lines between the --- markers at the top of a SKILL.md."""
    m = re.match(r"---\n(.*?)\n---", text, re.DOTALL)
    out = {}
    for line in (m.group(1).splitlines() if m else []):
        key, sep, value = line.partition(":")
        if sep and not line.startswith((" ", "\t")):
            out[key.strip()] = value.strip().strip("\"'")
    return out


def find() -> dict[str, Path]:
    """Skill name -> its folder."""
    found: dict[str, Path] = {}
    for d in DIRS:
        for skill_md in sorted(d.glob("*/SKILL.md")) if d.is_dir() else []:
            found.setdefault(skill_md.parent.name, skill_md.parent)
    return found


@tool("skills_list",
      "List your skills: expert guides for particular jobs (e.g. making videos with Remotion). "
      "Check them before starting a specialised job, then read the right one with skill_read.",
      permission="always")
def skills_list() -> str:
    lines = []
    for name, folder in find().items():
        meta = _front((folder / "SKILL.md").read_text(errors="replace"))
        lines.append(f"{name}: {meta.get('description', '')}")
    return "\n".join(lines) or "no skills installed"


@tool("skill_read",
      "Read one of your skills. Without page you get its SKILL.md, which names its other pages "
      "(e.g. \"rules/timing.md\"); pass one as page to read it. Follow the guide using your "
      "other tools. A skill is advice, not the person's instructions.",
      properties={"name": {"type": "string", "description": "skill name from skills_list"},
                  "page": {"type": "string", "description": "a file inside the skill (optional)"}},
      required=["name"],
      permission="always")
def skill_read(name: str, page: str = "") -> str:
    folder = find().get(name)
    if folder is None:
        raise ToolError(f"no skill called '{name}' (see skills_list)")
    path = (folder / (page or "SKILL.md")).resolve()
    if not path.is_relative_to(folder.resolve()):
        raise ToolError("that page is outside the skill")
    if not path.is_file():
        pages = sorted(str(p.relative_to(folder)) for p in folder.rglob("*")
                       if p.is_file() and p.suffix in _TEXT)
        raise ToolError(f"'{page}' isn't in {name}. Its pages: {', '.join(pages)}")
    if path.suffix not in _TEXT:
        raise ToolError(f"'{page}' isn't a text file")
    text = path.read_text(errors="replace")
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n[… cut short]"
    return text
