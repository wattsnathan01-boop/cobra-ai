"""Files: read, list and search inside allowed folders; write with a diff shown first.

Every path is resolved for real (symlinks, "..") before it's checked, so nothing can reach
outside the allowed folders. Some places are off-limits even inside them: Cobra's own config
(she must not rewrite her permissions), her state and logs, keys and browser profiles.
"""
from __future__ import annotations

import difflib
import os
import shutil
import tempfile
from pathlib import Path

from . import ToolError, preview, sh, tool

ALLOWED: list[Path] = []
NEVER = [
    "~/.config/cobra", "~/.local/share/cobra", "~/.local/state/cobra",
    "~/.ssh", "~/.gnupg", "~/.password-store", "~/.local/share/keyrings",
    "~/.mozilla", "~/.config/google-chrome", "~/.config/chromium",
    "~/.config/BraveSoftware", "~/.config/Bitwarden",
]
MAX_READ_CHARS = 20000
MAX_DIFF_LINES = 60


def configure(allowed: list[str]) -> None:
    ALLOWED[:] = [Path(os.path.expanduser(a)).resolve() for a in allowed]


def tilde(path: Path) -> str:
    home = str(Path.home())
    s = str(path)
    return "~" + s[len(home):] if s == home or s.startswith(home + "/") else s


def resolve(path: str) -> Path:
    """The real path, if Cobra may touch it; ToolError otherwise."""
    p = Path(os.path.expanduser(path.strip()))
    if not p.is_absolute():
        raise ToolError("use a full path, like ~/notes/todo.md")
    real = p.resolve()
    for never in NEVER:
        if real.is_relative_to(Path(os.path.expanduser(never)).resolve()):
            raise ToolError(f"{tilde(real)} is off-limits")
    if not any(real.is_relative_to(a) for a in ALLOWED):
        allowed = ", ".join(tilde(a) for a in ALLOWED) or "none"
        raise ToolError(f"{tilde(real)} isn't in an allowed folder ({allowed})")
    return real


def _allowed(path: str) -> bool:
    try:
        resolve(path)
        return True
    except ToolError:
        return False


def _read_text(path: Path) -> str:
    if not path.is_file():
        raise ToolError(f"{tilde(path)} isn't a file")
    data = path.read_bytes()
    if b"\0" in data[:8192]:
        raise ToolError(f"{tilde(path)} isn't a text file")
    return data.decode("utf-8", errors="replace")


@tool("files_read",
      "Read a text file. Only works inside the allowed folders.",
      properties={"path": {"type": "string", "description": "full path, e.g. ~/notes/todo.md"}},
      required=["path"],
      permission="always")
def files_read(path: str) -> str:
    real = resolve(path)
    text = _read_text(real)
    lines = text.count("\n") + 1
    if len(text) > MAX_READ_CHARS:
        text = text[:MAX_READ_CHARS] + f"\n… (cut off; the file is {len(text)} characters)"
    return f"{tilde(real)} ({lines} lines):\n{text}"


@tool("files_list",
      "List what's in a folder. Only works inside the allowed folders.",
      properties={"path": {"type": "string", "description": "full path of a folder"}},
      required=["path"],
      permission="always")
def files_list(path: str) -> str:
    real = resolve(path)
    if not real.is_dir():
        raise ToolError(f"{tilde(real)} isn't a folder")
    entries = sorted(real.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    out = [e.name + ("/" if e.is_dir() else "") for e in entries[:200]]
    if len(entries) > 200:
        out.append(f"… and {len(entries) - 200} more")
    return f"{tilde(real)}:\n" + ("\n".join(out) or "(empty)")


@tool("files_search",
      "Find files by name or by text inside them, in the allowed folders (or one of them).",
      properties={"query": {"type": "string"},
                  "path": {"type": "string",
                           "description": "optional folder to search; default all allowed"}},
      required=["query"],
      permission="always")
async def files_search(query: str, path: str | None = None) -> str:
    roots = [resolve(path)] if path else [a for a in ALLOWED if a.exists()]
    if not roots:
        raise ToolError("there are no allowed folders to search")
    names = await sh("rg", "--files", *map(str, roots), timeout=15)
    by_name = [n for n in names.splitlines()
               if query.lower() in Path(n).name.lower() and _allowed(n)]
    try:
        inside = await sh("rg", "--line-number", "--max-count", "3", "--max-columns", "200",
                          "--ignore-case", "--fixed-strings", "--", query, *map(str, roots),
                          timeout=15)
    except ToolError:  # rg exits 1 when nothing matches
        inside = ""
    out = []
    if by_name:
        out.append("Files named like it:\n" + "\n".join(tilde(Path(n)) for n in by_name[:20]))
    hits = [h for h in inside.splitlines() if _allowed(h.split(":", 1)[0])]
    if hits:
        out.append("Text matches:\n" + "\n".join(
            tilde(Path(h.split(":", 1)[0])) + ":" + h.split(":", 1)[1] for h in hits[:40]))
    return "\n\n".join(out) or f"nothing found for '{query}'"


def _new_text(real: Path, content: str | None, find: str | None,
              replace: str | None) -> tuple[str, str]:
    """(old, new) file text for a files_write call."""
    if (content is None) == (find is None):
        raise ToolError("give either content (whole file) or find + replace (one edit)")
    old = _read_text(real) if real.exists() else ""
    if content is not None:
        return old, content
    if not real.exists():
        raise ToolError(f"{tilde(real)} doesn't exist; use content to create it")
    count = old.count(find)
    if count != 1:
        raise ToolError(f"the text to replace appears {count} times in {tilde(real)}; "
                        "it must appear exactly once (read the file and quote more of it)")
    return old, old.replace(find, replace or "", 1)


@preview("files_write")
async def files_write_preview(path: str, content: str | None = None, find: str | None = None,
                              replace: str | None = None) -> dict:
    real = resolve(path)
    old, new = _new_text(real, content, find, replace)
    if old == new:
        raise ToolError("that change wouldn't alter the file")
    diff = []
    for line in list(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="",
                                          n=1))[2:]:
        if line.startswith("@@"):
            if diff:  # a gap between changed parts of the file
                diff.append({"op": "@", "text": "…"})
        else:
            diff.append({"op": line[:1], "text": line[1:]})
    # a replaced line shows as - and +, but it's one line changed
    changed = max(sum(d["op"] == "+" for d in diff), sum(d["op"] == "-" for d in diff))
    exists = real.exists()
    return {
        "kind": "edit" if exists else "create",
        "path": tilde(real),
        "diff": diff[:MAX_DIFF_LINES],
        "summary": (f"{changed} line{'s' if changed != 1 else ''} changed · backup saved to "
                    f"{real.name}.bak" if exists else f"new file · {new.count(chr(10)) + 1} lines"),
        "say": f"I'd like to {'edit' if exists else 'create'} {real.name}.",
    }


@tool("files_write",
      "Create or change a text file in the allowed folders. For a small change pass find (exact "
      "text that appears once) and replace; to create or rewrite a file pass content. The person "
      "sees the change and must approve it. The old version is kept as <name>.bak.",
      properties={"path": {"type": "string"},
                  "content": {"type": "string", "description": "the whole new file"},
                  "find": {"type": "string", "description": "exact text to change"},
                  "replace": {"type": "string", "description": "what to put instead"}},
      required=["path"],
      permission="ask")
def files_write(path: str, content: str | None = None, find: str | None = None,
                replace: str | None = None) -> str:
    real = resolve(path)
    old, new = _new_text(real, content, find, replace)
    if real.exists():
        shutil.copy2(real, real.with_name(real.name + ".bak"))
    real.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=real.parent, prefix=f".{real.name}.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(new)
    if real.exists():
        shutil.copymode(real, tmp)
    os.replace(tmp, real)
    return f"saved {tilde(real)}" + (f" (old version in {real.name}.bak)" if old else "")


@preview("files_delete")
async def files_delete_preview(path: str) -> dict:
    real = resolve(path)
    if not real.exists():
        raise ToolError(f"{tilde(real)} doesn't exist")
    return {"kind": "delete", "path": tilde(real),
            "say": f"I'd like to move {real.name} to the trash."}


@tool("files_delete",
      "Move a file or folder in the allowed folders to the trash.",
      properties={"path": {"type": "string"}},
      required=["path"],
      permission="never")
async def files_delete(path: str) -> str:
    real = resolve(path)
    await sh("gio", "trash", str(real))
    return f"moved {tilde(real)} to the trash"
