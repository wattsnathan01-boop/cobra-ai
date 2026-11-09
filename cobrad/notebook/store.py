"""Reading and writing the notebook folder (see __init__.py for the layout).

Cobra's daemon and the MCP server (a separate process, for Claude Code) both write here, so
every change happens under a file lock and files are replaced atomically.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import secrets
import shutil
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

AUTHORS = ("you", "cobra", "claude")
KINDS = ("note", "diary")
MOODS = ("", "good", "meh", "rough")

IMAGE = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif", ".heic", ".svg"}
VIDEO = {".mp4", ".webm", ".mkv", ".mov", ".avi", ".m4v"}
AUDIO = {".mp3", ".ogg", ".opus", ".wav", ".m4a", ".flac", ".oga"}
MAX_ATTACH_BYTES = 2 * 1024 ** 3
MAX_TEXT_CHARS = 100_000

_BY = re.compile(r"^<!--\s*by:\s*(\w+)\s*-->\s*$")
_LINK = re.compile(r"^(!?)\[(.*)\]\((media/[^)\s]+)\)\s*$")
_CHECK = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s?(.*)$")
_ID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")


class NotebookError(Exception):
    """Something the caller asked for can't be done (unknown note, bad time, …)."""


_current: "Notebook | None" = None


def current() -> "Notebook":
    if _current is None:
        raise RuntimeError("the notebook isn't set up")
    return _current


def media_kind(name: str) -> str:
    ext = Path(name).suffix.lower()
    return "image" if ext in IMAGE else "video" if ext in VIDEO else \
        "audio" if ext in AUDIO else "file"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _who(who: str) -> str:
    who = (who or "you").lower()
    if who not in AUTHORS:
        raise NotebookError(f"unknown author {who!r}")
    return who


def parse_when(text: str, now: datetime | None = None) -> datetime:
    """A reminder time: ISO ("2026-11-14T10:00", "2026-11-14 10:00"), "HH:MM" (the next one),
    or "in 20 minutes" / "in 2 hours" / "in 3 days"."""
    now = now or datetime.now()
    s = (text or "").strip().lower()
    m = re.fullmatch(r"in\s+(\d+(?:\.\d+)?)\s*(m|min|mins|minutes?|h|hrs?|hours?|d|days?)", s)
    if m:
        n, unit = float(m.group(1)), m.group(2)[0]
        return now + timedelta(**{"m": {"minutes": n}, "h": {"hours": n}, "d": {"days": n}}[unit])
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
    if m:
        at = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        return at if at > now else at + timedelta(days=1)
    try:
        return datetime.fromisoformat(s.upper().replace(" ", "T")).replace(tzinfo=None)
    except ValueError:
        raise NotebookError(f"can't read the time {text!r}; use e.g. 2026-11-14T10:00, "
                            "18:30 or 'in 20 minutes'")


# ── the note file format ────────────────────────────────────────────────────

def parse_note(text: str) -> tuple[dict, list[dict]]:
    """A note file → (fields, blocks)."""
    fields: dict = {}
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            for line in text[4:end].splitlines():
                key, sep, value = line.partition(":")
                if not sep:
                    continue
                value = value.strip()
                try:
                    fields[key.strip()] = json.loads(value)
                except json.JSONDecodeError:
                    if value.startswith("[") and value.endswith("]"):  # [a, b] by hand
                        fields[key.strip()] = [v.strip().strip("'\"")
                                               for v in value[1:-1].split(",") if v.strip()]
                    else:
                        fields[key.strip()] = value
            body = text[end + 4:].lstrip("\n")
    return fields, parse_body(body)


def parse_body(body: str) -> list[dict]:
    blocks: list[dict] = []
    author = "you"
    text: list[str] = []

    def flush_text():
        joined = "\n".join(text).strip("\n")
        if joined.strip():
            blocks.append({"type": "text", "author": author, "text": joined})
        text.clear()

    for line in body.splitlines():
        if m := _BY.match(line):
            flush_text()
            author = m.group(1).lower() if m.group(1).lower() in AUTHORS else "you"
        elif m := _LINK.match(line):
            flush_text()
            src = m.group(3)
            kind = media_kind(src)
            blocks.append({"type": kind, "author": author, "src": src, "caption": m.group(2)})
        elif m := _CHECK.match(line):
            flush_text()
            item = {"text": m.group(2), "done": m.group(1) != " "}
            last = blocks[-1] if blocks else None
            if last and last["type"] == "checklist" and last["author"] == author \
                    and last.get("_open"):
                last["items"].append(item)
            else:
                blocks.append({"type": "checklist", "author": author, "items": [item],
                               "_open": True})
        else:
            if blocks and blocks[-1].get("_open"):
                blocks[-1]["_open"] = False  # anything else ends a checklist
                if not line.strip():
                    continue
            text.append(line)
    flush_text()
    for b in blocks:
        b.pop("_open", None)
    return blocks


def render_note(fields: dict, blocks: list[dict]) -> str:
    head = "".join(f"{k}: {json.dumps(v, ensure_ascii=False)}\n" for k, v in fields.items())
    parts, author = [], "you"
    for b in blocks:
        lines = []
        if b.get("author", "you") != author:
            author = b.get("author", "you")
            lines.append(f"<!-- by: {author} -->")
        if b["type"] == "text":
            lines.append(b["text"].strip("\n"))
        elif b["type"] == "checklist":
            lines += [f"- [{'x' if i.get('done') else ' '}] {i.get('text', '')}"
                      for i in b.get("items", [])]
        else:
            bang = "!" if b["type"] == "image" else ""
            caption = (b.get("caption") or "").replace("]", ")").replace("\n", " ")
            lines.append(f"{bang}[{caption}]({b['src']})")
        parts.append("\n".join(lines))
    return f"---\n{head}---\n\n" + "\n\n".join(parts) + "\n"


def _clean_blocks(blocks: list[dict], default_author: str) -> list[dict]:
    out = []
    for b in blocks or []:
        kind = b.get("type")
        author = b.get("author") if b.get("author") in AUTHORS else default_author
        if kind == "text":
            if str(b.get("text", "")).strip():
                out.append({"type": "text", "author": author, "text": str(b["text"])})
        elif kind == "checklist":
            items = [{"text": str(i.get("text", "")).replace("\n", " "), "done": bool(i.get("done"))}
                     for i in b.get("items", []) if str(i.get("text", "")).strip()]
            if items:
                out.append({"type": "checklist", "author": author, "items": items})
        elif kind in ("image", "video", "audio", "file"):
            src = str(b.get("src", ""))
            if src.startswith("media/") and ".." not in src:
                out.append({"type": media_kind(src), "author": author, "src": src,
                            "caption": str(b.get("caption", ""))})
    return out


def _unmerge_blocks(before: str, after: str, now: str) -> str:
    """Take back blocks that were added (after vs before) from a note changed since."""
    _, b_blocks = parse_note(before)
    _, a_blocks = parse_note(after)
    fields, n_blocks = parse_note(now)
    added = list(a_blocks)
    for b in b_blocks:
        if b in added:
            added.remove(b)
    for b in added:
        if b in n_blocks:
            n_blocks.remove(b)
    return render_note(fields, n_blocks)


def _unmerge_reminders(before: str, after: str, now: str) -> str:
    """Reverse one change to reminders.json, keeping everything changed since."""
    by_id = lambda text: {r.get("id"): r for r in json.loads(text or "[]")}  # noqa: E731
    b, a, n = by_id(before), by_id(after), json.loads(now or "[]")
    out = []
    for r in n:
        rid = r.get("id")
        if rid in a and rid not in b:
            continue                    # it was added: take it out
        out.append(b[rid] if rid in a and rid in b and a[rid] != b[rid] and r == a[rid] else r)
    have = {r.get("id") for r in out}
    out += [r for rid, r in b.items() if rid not in a and rid not in have]  # it was removed
    return json.dumps(out, indent=1, ensure_ascii=False) + "\n"


# ── the notebook ────────────────────────────────────────────────────────────

class Notebook:
    def __init__(self, root: Path):
        global _current
        self.root = Path(os.path.expanduser(str(root)))
        self.notes_dir = self.root / "notes"
        self.media_dir = self.root / "media"
        self.meta = self.root / ".cobra"
        self.reminders_path = self.root / "reminders.json"
        self.activity_path = self.meta / "activity.jsonl"
        for d in (self.notes_dir, self.media_dir, self.meta / "undo", self.meta / "trash"):
            d.mkdir(parents=True, exist_ok=True)
        _current = self

    # ── plumbing ──

    @contextlib.contextmanager
    def _locked(self):
        with open(self.meta / "lock", "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    @staticmethod
    def _write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)

    def _path(self, note_id: str) -> Path:
        if not _ID.match(note_id or ""):
            raise NotebookError(f"no note {note_id!r}")
        return self.notes_dir / f"{note_id}.md"

    def version(self) -> tuple:
        """Changes whenever anything in the notebook does (cheap: a few stats)."""
        out = []
        for p in (self.notes_dir, self.reminders_path, self.activity_path):
            try:
                st = p.stat()
                out.append((st.st_mtime_ns, st.st_size))
            except FileNotFoundError:
                out.append(None)
        return tuple(out)

    def _log(self, who: str, action: str, summary: str, note_id: str = "",
             title: str = "", file: Path | None = None, before: str | None = None,
             added: list[str] | None = None) -> None:
        """Record what Cobra or Claude did, keeping the file as it was so it can be undone."""
        if who == "you":
            return
        entry_id = f"{int(time.time() * 1000):x}{secrets.token_hex(2)}"
        undo = None
        if file is not None:
            undo = {"file": str(file.relative_to(self.root)), "added": added or []}
            if before is not None:
                self._write(self.meta / "undo" / f"{entry_id}.bak", before)
                undo["before"] = f"{entry_id}.bak"
            if file.exists():  # as it was right after, to see what changed since
                self._write(self.meta / "undo" / f"{entry_id}.after", file.read_text(encoding="utf-8"))
                undo["after"] = f"{entry_id}.after"
        rec = {"id": entry_id, "ts": _now(), "who": who, "action": action, "summary": summary,
               "note_id": note_id, "title": title, "undo": undo}
        with open(self.activity_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ── notes ──

    def _load(self, note_id: str) -> tuple[dict, list[dict], str]:
        path = self._path(note_id)
        if not path.exists():
            raise NotebookError(f"no note {note_id!r}")
        text = path.read_text(encoding="utf-8")
        fields, blocks = parse_note(text)
        return fields, blocks, text

    def _fields(self, f: dict, note_id: str) -> dict:
        tags = f.get("tags") or []
        return {
            "id": note_id,
            "title": str(f.get("title") or "Untitled"),
            "kind": f.get("kind") if f.get("kind") in KINDS else "note",
            "tags": [str(t).lstrip("#") for t in (tags if isinstance(tags, list) else [tags])],
            "mood": f.get("mood") if f.get("mood") in MOODS else "",
            "pinned": bool(f.get("pinned")),
            "author": f.get("author") if f.get("author") in AUTHORS else "you",
            "created": str(f.get("created") or ""),
            "updated": str(f.get("updated") or f.get("created") or ""),
            "date": str(f.get("date") or str(f.get("created") or "")[:10]),
        }

    def _note(self, fields: dict, blocks: list[dict], note_id: str) -> dict:
        note = self._fields(fields, note_id)
        for b in blocks:
            if "src" in b:
                b["path"] = str(self.root / b["src"])
        note["blocks"] = blocks
        return note

    def _save(self, note_id: str, fields: dict, blocks: list[dict]) -> None:
        keep = {k: fields[k] for k in ("title", "kind", "date", "tags", "mood", "pinned",
                                       "author", "created", "updated") if k in fields}
        text = render_note(keep, blocks)
        if len(text) > MAX_TEXT_CHARS:
            raise NotebookError("that note is too long")
        self._write(self._path(note_id), text)

    def get(self, note_id: str) -> dict:
        fields, blocks, _ = self._load(note_id)
        return self._note(fields, blocks, note_id)

    def create(self, title: str, text: str = "", who: str = "you", kind: str = "note",
               tags: list[str] | None = None, mood: str = "", date: str = "",
               checklist: list[str] | None = None) -> dict:
        who = _who(who)
        if kind not in KINDS:
            raise NotebookError("kind must be note or diary")
        now = datetime.now()
        note_id = now.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)
        fields = {"title": (title or "Untitled").strip()[:200], "kind": kind,
                  "tags": [t.strip().lstrip("#") for t in tags or [] if t.strip()],
                  "mood": mood if mood in MOODS else "", "pinned": False, "author": who,
                  "created": _now(), "updated": _now()}
        if kind == "diary":
            fields["date"] = date or now.strftime("%Y-%m-%d")
        blocks = []
        if text.strip():
            blocks.append({"type": "text", "author": who, "text": text.strip()})
        if checklist:
            blocks.append({"type": "checklist", "author": who,
                           "items": [{"text": c, "done": False} for c in checklist if c.strip()]})
        with self._locked():
            self._save(note_id, fields, blocks)
            self._log(who, "created", f"created {kind}", note_id, fields["title"],
                      self._path(note_id), None)
        return self.get(note_id)

    def append(self, note_id: str, text: str = "", who: str = "you",
               checklist: list[str] | None = None) -> dict:
        who = _who(who)
        if not text.strip() and not checklist:
            raise NotebookError("nothing to add")
        with self._locked():
            fields, blocks, before = self._load(note_id)
            if text.strip():
                blocks.append({"type": "text", "author": who, "text": text.strip()})
            if checklist:
                blocks.append({"type": "checklist", "author": who,
                               "items": [{"text": c, "done": False}
                                         for c in checklist if c.strip()]})
            fields["updated"] = _now()
            self._save(note_id, fields, blocks)
            what = "added a checklist to" if checklist and not text.strip() else "added to"
            self._log(who, "appended", what, note_id, fields.get("title", ""),
                      self._path(note_id), before)
        return self.get(note_id)

    def update(self, note_id: str, who: str = "you", blocks: list[dict] | None = None,
               **changes) -> dict:
        """Change fields (title, tags, mood, pinned, kind) and/or replace all the blocks."""
        who = _who(who)
        with self._locked():
            fields, old_blocks, before = self._load(note_id)
            for key in ("title", "tags", "mood", "pinned", "kind"):
                if key in changes and changes[key] is not None:
                    fields[key] = changes[key]
            if fields.get("mood") not in MOODS:
                raise NotebookError("mood must be good, meh or rough")
            if fields.get("kind") not in KINDS:
                raise NotebookError("kind must be note or diary")
            if isinstance(fields.get("tags"), list):
                fields["tags"] = [str(t).strip().lstrip("#") for t in fields["tags"]
                                  if str(t).strip()]
            new_blocks = old_blocks if blocks is None else _clean_blocks(blocks, who)
            fields["updated"] = _now()
            self._save(note_id, fields, new_blocks)
            self._log(who, "edited", "edited", note_id, str(fields.get("title", "")),
                      self._path(note_id), before)
        return self.get(note_id)

    def attach(self, note_id: str, source: str | Path, who: str = "you", caption: str = "",
               move: bool = False) -> dict:
        """Copy (or move) a file into the note's media folder and add it as a block."""
        who = _who(who)
        src = Path(os.path.expanduser(str(source)))
        if not src.is_file():
            raise NotebookError(f"{source} isn't a file")
        if src.stat().st_size > MAX_ATTACH_BYTES:
            raise NotebookError("that file is too big (over 2 GB)")
        name = re.sub(r"[^\w.\-]+", "-", src.name).strip("-") or "file"
        with self._locked():
            fields, blocks, before = self._load(note_id)
            folder = self.media_dir / note_id
            folder.mkdir(parents=True, exist_ok=True)
            dest = folder / name
            n = 1
            while dest.exists():
                dest = folder / f"{Path(name).stem}-{n}{Path(name).suffix}"
                n += 1
            (shutil.move if move else shutil.copy2)(str(src), dest)
            rel = str(dest.relative_to(self.root))
            kind = media_kind(rel)
            blocks.append({"type": kind, "author": who, "src": rel, "caption": caption})
            fields["updated"] = _now()
            self._save(note_id, fields, blocks)
            self._log(who, "attached", f"attached a {kind if kind != 'file' else 'file'} to",
                      note_id, fields.get("title", ""), self._path(note_id), before, [rel])
        return self.get(note_id)

    def delete(self, note_id: str, who: str = "you") -> None:
        who = _who(who)
        with self._locked():
            fields, _, before = self._load(note_id)
            path = self._path(note_id)
            shutil.move(str(path), self.meta / "trash" / path.name)
            self._log(who, "deleted", "deleted", note_id, fields.get("title", ""), path, before)

    def diary_today(self, who: str = "you", day: str = "") -> dict:
        """Today's diary entry (or `day`'s, YYYY-MM-DD), made if there isn't one."""
        day = day or datetime.now().strftime("%Y-%m-%d")
        for n in self.list(kind="diary"):
            if n["date"] == day:
                return self.get(n["id"])
        title = datetime.strptime(day, "%Y-%m-%d").strftime("%A %-d %B")
        return self.create(title, who=who, kind="diary", date=day)

    def _summary(self, path: Path) -> dict | None:
        try:
            fields, blocks = parse_note(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            return None
        s = self._fields(fields, path.stem)
        texts = [b["text"] for b in blocks if b["type"] == "text"]
        texts += [i["text"] for b in blocks if b["type"] == "checklist" for i in b["items"]]
        s["preview"] = " ".join(" ".join(texts).split())[:240]
        s["media"] = sorted({b["type"] for b in blocks if b["type"] not in ("text",)})
        s["authors"] = sorted({b["author"] for b in blocks} | {s["author"]},
                              key=AUTHORS.index)
        s["thumb"] = next((str(self.root / b["src"]) for b in blocks if b["type"] == "image"), "")
        s["_all"] = " ".join([s["title"], " ".join(s["tags"])] + texts +
                             [b.get("caption", "") for b in blocks]).lower()
        return s

    def list(self, query: str = "", kind: str = "", tag: str = "", has: str = "",
             limit: int = 0) -> list[dict]:
        """Notes, pinned first then newest. query matches title, text, tags and captions."""
        words = query.lower().split()
        out = []
        for path in self.notes_dir.glob("*.md"):
            s = self._summary(path)
            if s is None or (kind and s["kind"] != kind) or (tag and tag.lstrip("#") not in s["tags"]):
                continue
            if has and has not in s["media"]:
                continue
            if words and not all(w in s["_all"] for w in words):
                continue
            out.append(s)
        out.sort(key=lambda s: (s["pinned"], s["updated"]), reverse=True)
        for s in out:
            s.pop("_all")
        return out[:limit] if limit else out

    def media(self, limit: int = 0) -> list[dict]:
        """Every attachment, newest first."""
        out = []
        for path in self.notes_dir.glob("*.md"):
            try:
                fields, blocks = parse_note(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            f = self._fields(fields, path.stem)
            for b in blocks:
                if "src" in b:
                    out.append({"note_id": f["id"], "title": f["title"], "updated": f["updated"],
                                "type": b["type"], "caption": b.get("caption", ""),
                                "src": b["src"], "path": str(self.root / b["src"])})
        out.sort(key=lambda m: m["src"], reverse=True)
        return out[:limit] if limit else out

    # ── reminders ──

    def _reminders(self) -> list[dict]:
        try:
            data = json.loads(self.reminders_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_reminders(self, items: list[dict]) -> None:
        self._write(self.reminders_path, json.dumps(items, indent=1, ensure_ascii=False) + "\n")

    def _reminders_text(self) -> str | None:
        try:
            return self.reminders_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def reminders(self, include_done: bool = False) -> list[dict]:
        items = [r for r in self._reminders() if include_done or not r.get("done")]
        return sorted(items, key=lambda r: (bool(r.get("done")), r.get("due", "")))

    def add_reminder(self, text: str, when: str, who: str = "you", speak: bool = True,
                     note_id: str = "") -> dict:
        who = _who(who)
        if not text.strip():
            raise NotebookError("what should the reminder say?")
        due = parse_when(when)
        if note_id:
            self._load(note_id)  # must exist
        rem = {"id": secrets.token_hex(4), "text": text.strip()[:300],
               "due": due.strftime("%Y-%m-%dT%H:%M:%S"), "speak": bool(speak),
               "note_id": note_id, "author": who, "created": _now(), "done": False,
               "fired": False}
        with self._locked():
            before = self._reminders_text()
            items = self._reminders()
            items.append(rem)
            self._save_reminders(items)
            self._log(who, "reminder", f"set a reminder for {due:%a %-d %b %H:%M}:",
                      note_id, rem["text"], self.reminders_path, before or "[]\n")
        return rem

    def _change_reminder(self, rid: str, who: str, action: str, fn) -> dict:
        who = _who(who)
        with self._locked():
            before = self._reminders_text()
            items = self._reminders()
            for r in items:
                if r.get("id") == rid:
                    fn(r)
                    self._save_reminders(items)
                    self._log(who, "reminder", action, r.get("note_id", ""), r["text"],
                              self.reminders_path, before or "[]\n")
                    return r
        raise NotebookError(f"no reminder {rid!r}")

    def complete_reminder(self, rid: str, who: str = "you", done: bool = True) -> dict:
        return self._change_reminder(rid, who, "ticked off" if done else "reopened",
                                     lambda r: r.update(done=done))

    def snooze_reminder(self, rid: str, minutes: float = 10, who: str = "you") -> dict:
        due = (datetime.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")
        return self._change_reminder(rid, who, f"snoozed {int(minutes)} min",
                                     lambda r: r.update(due=due, fired=False, done=False))

    def delete_reminder(self, rid: str, who: str = "you") -> None:
        who = _who(who)
        with self._locked():
            before = self._reminders_text()
            items = self._reminders()
            keep = [r for r in items if r.get("id") != rid]
            if len(keep) == len(items):
                raise NotebookError(f"no reminder {rid!r}")
            gone = next(r for r in items if r.get("id") == rid)
            self._save_reminders(keep)
            self._log(who, "reminder", "removed reminder", gone.get("note_id", ""),
                      gone["text"], self.reminders_path, before)

    def due_reminders(self, now: datetime | None = None) -> list[dict]:
        """Reminders that are due and haven't gone off yet; marks them as gone off."""
        stamp = (now or datetime.now()).strftime("%Y-%m-%dT%H:%M:%S")
        with self._locked():
            items = self._reminders()
            due = [r for r in items if not r.get("done") and not r.get("fired")
                   and r.get("due", "9") <= stamp]
            if due:
                for r in due:
                    r["fired"] = True
                self._save_reminders(items)
        return due

    # ── activity and undo ──

    def activity(self, limit: int = 50) -> list[dict]:
        try:
            lines = self.activity_path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        out, undone = [], set()
        for line in reversed(lines):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("action") == "undo":
                undone.add(rec.get("target"))
                continue
            rec["undone"] = rec["id"] in undone
            rec["can_undo"] = bool(rec.get("undo")) and not rec["undone"]
            rec.pop("undo", None)
            out.append(rec)
            if len(out) >= limit:
                break
        return out

    def undo(self, entry_id: str) -> str:
        """Put back the file as it was before an AI change. Returns what was undone."""
        with self._locked():
            recs = {}
            undone = set()
            try:
                for line in self.activity_path.read_text(encoding="utf-8").splitlines():
                    rec = json.loads(line)
                    recs[rec["id"]] = rec
                    if rec.get("action") == "undo":
                        undone.add(rec.get("target"))
            except (FileNotFoundError, json.JSONDecodeError):
                pass
            rec = recs.get(entry_id)
            if rec is None or not rec.get("undo"):
                raise NotebookError("nothing to undo there")
            if entry_id in undone:
                raise NotebookError("already undone")
            u = rec["undo"]
            target = (self.root / u["file"]).resolve()
            if not target.is_relative_to(self.root.resolve()):
                raise NotebookError("nothing to undo there")
            snap = lambda key: (self.meta / "undo" / u[key]).read_text(encoding="utf-8") \
                if u.get(key) else None  # noqa: E731
            before, after = snap("before"), snap("after")
            now = target.read_text(encoding="utf-8") if target.exists() else None
            if before is None:  # it was created: move it to the trash
                if target.exists():
                    shutil.move(str(target), self.meta / "trash" / target.name)
            elif now == after:  # nothing changed since: put it back exactly
                self._write(target, before)
            elif now is not None and target == self.reminders_path.resolve():
                self._write(target, _unmerge_reminders(before, after or "[]", now))
            elif now is not None and rec["action"] in ("appended", "attached"):
                self._write(target, _unmerge_blocks(before, after or "", now))
            else:
                raise NotebookError("that note has changed since; undo the later changes first")
            for rel in u.get("added", []):
                p = (self.root / rel).resolve()
                if p.is_relative_to(self.media_dir.resolve()) and p.exists():
                    shutil.move(str(p), self.meta / "trash" / p.name)
            with open(self.activity_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"id": entry_id + "u", "ts": _now(), "who": "you",
                                    "action": "undo", "target": entry_id}) + "\n")
        return f"undid: {rec['who']} {rec['summary']} {rec['title']}".strip()

    # ── the Today page ──

    def overview(self) -> dict:
        """Everything the window's pages need, in one go."""
        notes = self.list()
        tags: dict[str, int] = {}
        for n in notes:
            for t in n["tags"]:
                tags[t] = tags.get(t, 0) + 1
        calendar: dict[str, dict] = {}
        for n in notes:
            if n["kind"] == "diary":
                day = calendar.setdefault(n["date"], {})
                day.update(mood=n["mood"] or day.get("mood", ""), diary=n["id"])
                if n["media"]:
                    day["media"] = n["media"][0]
        reminders = self.reminders(include_done=True)
        for r in reminders:
            if not r.get("done"):
                calendar.setdefault(r["due"][:10], {})["reminder"] = True
        media = self.media()
        return {
            "root": str(self.root),
            "notes": notes,
            "tags": sorted(tags.items(), key=lambda kv: (-kv[1], kv[0])),
            "counts": {"notes": len(notes),
                       "diary": sum(n["kind"] == "diary" for n in notes),
                       "reminders": sum(not r.get("done") for r in reminders),
                       "media": len(media)},
            "calendar": calendar,
            "reminders": reminders[:200],
            "activity": self.activity(60),
            "media": media[:200],
        }
