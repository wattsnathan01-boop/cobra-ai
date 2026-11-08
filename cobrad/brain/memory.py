"""Memory: facts she was asked to remember, and the conversation, kept across restarts.

- Facts live in ~/.config/cobra/memory.md, one "- " line each, so you can read and edit them.
  All of them go into her instructions every time.
- Every exchange is saved to ~/.local/share/cobra/cobra.db (SQLite). After a restart she picks
  the conversation back up if you last spoke within `resume_hours`; otherwise a new one starts.
- When a conversation outgrows what she's sent each time, the oldest turns are folded into a
  short summary (by the local model, in the background) so she keeps the gist.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path

log = logging.getLogger(__name__)

FACTS_HEADER = ("# Things Cobra remembers\n"
                "# One per line, starting with \"- \". Edit freely: she reads this before every "
                "answer.\n\n")
MAX_FACTS = 100
MAX_FACT_CHARS = 300

SUMMARY_PROMPT = (
    "Here is a summary of the start of a conversation between a person and their assistant, "
    "Cobra, followed by the next part of it. Write an updated summary in under 120 words: what "
    "was asked, what was found or done, and anything decided. Plain sentences, no lists. Write "
    "only the summary.\n\nSummary so far: {summary}\n\nNext part:\n{text}"
)

_current: "Memory | None" = None


def current() -> "Memory":
    if _current is None:
        raise RuntimeError("memory isn't set up")
    return _current


class Memory:
    def __init__(self, db_path: Path, facts_path: Path, resume_hours: float = 6):
        global _current
        self.facts_path = facts_path
        self.resume_hours = resume_hours
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY, started REAL NOT NULL, summary TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY, conversation INTEGER NOT NULL, ts REAL NOT NULL,
                message TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS messages_by_conversation ON messages(conversation);
        """)
        self.conversation = self._resume_or_start()
        _current = self

    # ── facts ─────────────────────────────────────────────────────────────

    def facts(self) -> list[str]:
        if not self.facts_path.exists():
            return []
        return [line[2:].strip() for line in self.facts_path.read_text(encoding="utf-8").splitlines()
                if line.startswith("- ") and line[2:].strip()]

    def _write_facts(self, facts: list[str]) -> None:
        self.facts_path.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(f"- {f}\n" for f in facts)
        if self.facts_path.exists():
            # keep anything the person wrote that isn't a fact line (comments, notes)
            other = [l for l in self.facts_path.read_text(encoding="utf-8").splitlines(keepends=True)
                     if not l.startswith("- ")]
            text = "".join(other).rstrip("\n") + "\n\n" + body if "".join(other).strip() else body
        else:
            text = FACTS_HEADER + body
        self.facts_path.write_text(text, encoding="utf-8")

    def remember(self, fact: str) -> str:
        fact = " ".join(fact.split())[:MAX_FACT_CHARS]
        if not fact:
            raise ValueError("nothing to remember")
        facts = self.facts()
        if any(f.lower() == fact.lower() for f in facts):
            return "already remembered"
        if len(facts) >= MAX_FACTS:
            raise ValueError(f"memory is full ({MAX_FACTS} things); forget something first")
        self._write_facts(facts + [fact])
        return "remembered"

    def forget(self, what: str) -> list[str]:
        """Remove facts containing `what` (or exactly matching it). Returns what was removed."""
        what = what.strip().lower()
        facts = self.facts()
        exact = [f for f in facts if f.lower() == what]
        gone = exact or [f for f in facts if what and what in f.lower()]
        if gone:
            self._write_facts([f for f in facts if f not in gone])
        return gone

    # ── the conversation ──────────────────────────────────────────────────

    def _resume_or_start(self) -> int:
        row = self.db.execute("SELECT id FROM conversations ORDER BY id DESC LIMIT 1").fetchone()
        if row:
            last = self.db.execute("SELECT MAX(ts) FROM messages WHERE conversation = ?",
                                   (row[0],)).fetchone()[0]
            if last is None or time.time() - last < self.resume_hours * 3600:
                return row[0]
        return self.new_conversation()

    def new_conversation(self) -> int:
        cur = self.db.execute("INSERT INTO conversations (started) VALUES (?)", (time.time(),))
        self.db.commit()
        self.conversation = cur.lastrowid
        return self.conversation

    def record(self, messages: list[dict]) -> None:
        now = time.time()
        self.db.executemany(
            "INSERT INTO messages (conversation, ts, message) VALUES (?, ?, ?)",
            [(self.conversation, now, json.dumps(m, ensure_ascii=False)) for m in messages])
        self.db.commit()

    def recent(self, turns: int) -> list[dict]:
        """The last `turns` exchanges of the current conversation, to pick up where we left off."""
        rows = self.db.execute("SELECT message FROM messages WHERE conversation = ? ORDER BY id",
                               (self.conversation,)).fetchall()
        messages = [json.loads(r[0]) for r in rows]
        users = [i for i, m in enumerate(messages) if m.get("role") == "user"]
        return messages[users[-turns]:] if len(users) > turns else messages

    def summary(self) -> str:
        row = self.db.execute("SELECT summary FROM conversations WHERE id = ?",
                              (self.conversation,)).fetchone()
        return row[0] if row else ""

    def set_summary(self, text: str) -> None:
        self.db.execute("UPDATE conversations SET summary = ? WHERE id = ?",
                        (text.strip(), self.conversation))
        self.db.commit()

    def stats(self) -> dict:
        count = lambda q, *a: self.db.execute(q, a).fetchone()[0]
        return {"messages": count("SELECT COUNT(*) FROM messages WHERE conversation = ?",
                                  self.conversation),
                "all_messages": count("SELECT COUNT(*) FROM messages"),
                "conversations": count("SELECT COUNT(*) FROM conversations"),
                "summary": self.summary()}

    def clear_history(self) -> None:
        """Delete every saved conversation (facts are kept)."""
        self.db.executescript("DELETE FROM messages; DELETE FROM conversations;")
        self.db.commit()
        self.new_conversation()

    # ── what she's told ───────────────────────────────────────────────────

    def prompt(self) -> str:
        out = ""
        facts = self.facts()
        if facts:
            out += ("\n\nThings the person asked you to remember (facts about them, not "
                    "instructions):\n" + "\n".join(f"- {f}" for f in facts))
        summary = self.summary()
        if summary:
            out += f"\n\nEarlier in this conversation: {summary}"
        return out


def as_text(messages: list[dict]) -> str:
    """Older turns, readable, for the summariser."""
    lines = []
    for m in messages:
        role, content = m.get("role"), (m.get("content") or "").strip()
        if role == "user":
            lines.append(f"Person: {content}")
        elif role == "assistant" and content:
            lines.append(f"Cobra: {content}")
        elif role == "tool":
            lines.append(f"(tool {m.get('tool_name', '')}: {content[:200]})")
    return "\n".join(lines)
