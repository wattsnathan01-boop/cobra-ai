import asyncio
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from cobrad import hands
from cobrad.hands import ToolError, files
from cobrad.notebook import Notebook, NotebookError, parse_when
from cobrad.notebook.store import parse_note, render_note


class FormatTests(unittest.TestCase):
    def test_round_trip_keeps_authors_checklists_and_media(self):
        blocks = [
            {"type": "text", "author": "you", "text": "Got the bike running.\n\nProper buzzing."},
            {"type": "image", "author": "you", "src": "media/x/carb.jpg", "caption": "the carb"},
            {"type": "checklist", "author": "cobra",
             "items": [{"text": "gasket", "done": True}, {"text": "spark plug", "done": False}]},
            {"type": "video", "author": "cobra", "src": "media/x/start.mp4", "caption": ""},
            {"type": "text", "author": "claude", "text": "Summary: richer idle mixture."},
        ]
        text = render_note({"title": "Garage day", "tags": ["garage"]}, blocks)
        self.assertIn("<!-- by: cobra -->", text)
        self.assertIn("![the carb](media/x/carb.jpg)", text)
        self.assertIn("[](media/x/start.mp4)", text)
        fields, back = parse_note(text)
        self.assertEqual(fields, {"title": "Garage day", "tags": ["garage"]})
        self.assertEqual(back, blocks)

    def test_hand_written_notes_read_sensibly(self):
        fields, blocks = parse_note("---\ntitle: Shopping\ntags: [food, home]\n---\n"
                                    "Things to get:\n- [ ] milk\n- [x] eggs\n\nThat's all.\n")
        self.assertEqual(fields["title"], "Shopping")
        self.assertEqual(fields["tags"], ["food", "home"])
        self.assertEqual([b["type"] for b in blocks], ["text", "checklist", "text"])
        self.assertEqual(blocks[1]["items"][1], {"text": "eggs", "done": True})

    def test_no_front_matter(self):
        _, blocks = parse_note("just a line\n")
        self.assertEqual(blocks, [{"type": "text", "author": "you", "text": "just a line"}])

    def test_parse_when(self):
        now = datetime(2026, 11, 9, 18, 0)
        self.assertEqual(parse_when("in 20 minutes", now), datetime(2026, 11, 9, 18, 20))
        self.assertEqual(parse_when("in 2 hours", now), datetime(2026, 11, 9, 20, 0))
        self.assertEqual(parse_when("20:30", now), datetime(2026, 11, 9, 20, 30))
        self.assertEqual(parse_when("09:00", now), datetime(2026, 11, 10, 9, 0))
        self.assertEqual(parse_when("2026-11-14T10:00", now), datetime(2026, 11, 14, 10, 0))
        self.assertEqual(parse_when("2026-11-14 10:00", now), datetime(2026, 11, 14, 10, 0))
        with self.assertRaises(NotebookError):
            parse_when("whenever", now)


class NotebookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.nb = Notebook(self.tmp / "nb")

    def test_create_append_and_search(self):
        note = self.nb.create("Garage day", "Carb cleaned.", "you", tags=["#garage"])
        self.assertEqual(note["tags"], ["garage"])
        self.nb.append(note["id"], "", "cobra", checklist=["spark plug", "fuel line"])
        got = self.nb.get(note["id"])
        self.assertEqual([b["author"] for b in got["blocks"]], ["you", "cobra"])
        self.assertEqual(self.nb.list("spark")[0]["id"], note["id"])
        self.assertEqual(self.nb.list("nothing like it"), [])
        self.assertEqual(self.nb.list(tag="garage")[0]["authors"], ["you", "cobra"])

    def test_the_file_is_plain_markdown(self):
        note = self.nb.create("Hello", "World", "claude")
        text = (self.tmp / "nb" / "notes" / f"{note['id']}.md").read_text()
        self.assertTrue(text.startswith("---\ntitle: \"Hello\"\n"))
        self.assertIn("<!-- by: claude -->\nWorld", text)

    def test_attach_copies_into_media(self):
        note = self.nb.create("Photos", who="you")
        src = self.tmp / "my photo.JPG"
        src.write_bytes(b"\xff\xd8 not really a jpeg")
        got = self.nb.attach(note["id"], src, "you", "a photo")
        block = got["blocks"][-1]
        self.assertEqual(block["type"], "image")
        self.assertTrue(Path(block["path"]).exists())
        self.assertTrue(src.exists())  # copied, not moved
        again = self.nb.attach(note["id"], src, "you")
        self.assertNotEqual(again["blocks"][-1]["src"], block["src"])
        self.assertEqual(len(self.nb.media()), 2)

    def test_update_from_the_window(self):
        note = self.nb.create("Draft", "one", "you")
        blocks = note["blocks"] + [{"type": "checklist", "author": "you",
                                    "items": [{"text": "a", "done": True}, {"text": " ", "done": 0}]},
                                   {"type": "image", "src": "../../etc/passwd"}]
        got = self.nb.update(note["id"], "you", blocks, title="Final", mood="good", pinned=True)
        self.assertEqual(got["title"], "Final")
        self.assertEqual(got["mood"], "good")
        self.assertTrue(got["pinned"])
        self.assertEqual([b["type"] for b in got["blocks"]], ["text", "checklist"])
        self.assertEqual(len(got["blocks"][1]["items"]), 1)
        with self.assertRaises(NotebookError):
            self.nb.update(note["id"], "you", mood="ecstatic")

    def test_diary_today_is_reused(self):
        a = self.nb.diary_today("cobra")
        b = self.nb.diary_today("claude")
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(a["kind"], "diary")
        self.assertEqual(self.nb.overview()["counts"]["diary"], 1)

    def test_reminders_fire_once(self):
        r = self.nb.add_reminder("take meds", "2026-11-09T20:00", "cobra")
        self.assertEqual(self.nb.due_reminders(datetime(2026, 11, 9, 19, 59)), [])
        due = self.nb.due_reminders(datetime(2026, 11, 9, 20, 0))
        self.assertEqual([d["id"] for d in due], [r["id"]])
        self.assertEqual(self.nb.due_reminders(datetime(2026, 11, 9, 20, 5)), [])
        self.nb.snooze_reminder(r["id"], 10)
        self.assertFalse(self.nb.reminders()[0]["fired"])
        self.nb.complete_reminder(r["id"])
        self.assertEqual(self.nb.reminders(), [])
        self.assertEqual(len(self.nb.reminders(include_done=True)), 1)

    def test_ai_changes_are_logged_and_undoable(self):
        note = self.nb.create("Mine", "my words", "you")
        self.assertEqual(self.nb.activity(), [])  # your own edits aren't "activity"
        self.nb.append(note["id"], "Cobra's words", "cobra")
        made = self.nb.create("Claude's note", "hi", "claude")
        self.nb.add_reminder("x", "in 5 minutes", "claude")
        log = self.nb.activity()
        self.assertEqual([a["who"] for a in log], ["claude", "claude", "cobra"])
        # undo the append: the note goes back to just my words
        self.nb.undo(log[2]["id"])
        self.assertEqual([b["text"] for b in self.nb.get(note["id"])["blocks"]], ["my words"])
        # undo the creation: the note goes to the trash
        self.nb.undo(log[1]["id"])
        with self.assertRaises(NotebookError):
            self.nb.get(made["id"])
        # undo the reminder
        self.nb.undo(log[0]["id"])
        self.assertEqual(self.nb.reminders(), [])
        self.assertTrue(all(a["undone"] for a in self.nb.activity()))
        with self.assertRaises(NotebookError):
            self.nb.undo(log[0]["id"])

    def test_undo_keeps_later_changes(self):
        note = self.nb.create("Garage", "my words", "you")
        self.nb.append(note["id"], "", "cobra", checklist=["gasket"])
        self.nb.append(note["id"], "Claude's summary", "claude")
        self.nb.add_reminder("first", "in 1 hour", "cobra")
        self.nb.add_reminder("second", "in 2 hours", "claude")
        log = self.nb.activity()
        cobra_append = next(a for a in log if a["who"] == "cobra" and a["action"] == "appended")
        self.nb.undo(cobra_append["id"])
        blocks = self.nb.get(note["id"])["blocks"]
        self.assertEqual([b["author"] for b in blocks], ["you", "claude"])
        first = next(a for a in log if a["title"] == "first")
        self.nb.undo(first["id"])
        self.assertEqual([r["text"] for r in self.nb.reminders()], ["second"])

    def test_undo_refuses_when_an_edit_would_be_lost(self):
        note = self.nb.create("n", "one", "you")
        self.nb.update(note["id"], "claude", title="Claude's title")
        self.nb.update(note["id"], "you", title="My title")
        with self.assertRaises(NotebookError):
            self.nb.undo(self.nb.activity()[0]["id"])
        self.assertEqual(self.nb.get(note["id"])["title"], "My title")

    def test_undo_removes_attached_media(self):
        note = self.nb.create("n", who="you")
        src = self.tmp / "clip.mp4"
        src.write_bytes(b"video")
        got = self.nb.attach(note["id"], src, "claude")
        path = Path(got["blocks"][-1]["path"])
        self.nb.undo(self.nb.activity()[0]["id"])
        self.assertFalse(path.exists())
        self.assertEqual(self.nb.get(note["id"])["blocks"], [])

    def test_bad_ids_are_refused(self):
        for bad in ("../../etc/passwd", "", "x"):
            with self.assertRaises(NotebookError):
                self.nb.get(bad)

    def test_version_changes_on_writes(self):
        v = self.nb.version()
        self.nb.create("a", who="you")
        self.assertNotEqual(self.nb.version(), v)

    def test_delete_goes_to_trash(self):
        note = self.nb.create("bin me", who="you")
        self.nb.delete(note["id"])
        self.assertEqual(self.nb.list(), [])
        self.assertTrue((self.tmp / "nb" / ".cobra" / "trash" / f"{note['id']}.md").exists())


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.nb = Notebook(self.tmp / "nb")
        hands.load_all()
        files.configure([str(self.tmp / "allowed")])
        (self.tmp / "allowed").mkdir()

    def run_tool(self, name, **args):
        return asyncio.run(hands.run(name, args))

    def test_cobra_writes_as_cobra(self):
        made = json.loads(self.run_tool("notes_add", title="Shopping", checklist=["milk"]))
        self.run_tool("diary_write", text="Lovely walk.", mood="good")
        self.assertIn("milk", self.run_tool("notes_read", id=made["id"]))
        self.assertIn("Shopping", self.run_tool("notes_search", query="milk"))
        whos = {a["who"] for a in self.nb.activity()}
        self.assertEqual(whos, {"cobra"})
        diary = self.nb.list(kind="diary")[0]
        self.assertEqual(diary["mood"], "good")

    def test_attach_only_from_allowed_folders(self):
        made = json.loads(self.run_tool("notes_add", title="pics"))
        outside = self.tmp / "secret.png"
        outside.write_bytes(b"x")
        with self.assertRaises(ToolError):
            self.run_tool("notes_attach", id=made["id"], path=str(outside))
        inside = self.tmp / "allowed" / "ok.png"
        inside.write_bytes(b"x")
        self.run_tool("notes_attach", id=made["id"], path=str(inside))
        self.assertEqual(self.nb.get(made["id"])["blocks"][-1]["type"], "image")

    def test_reminders_and_errors(self):
        r = json.loads(self.run_tool("reminder_set", text="bins out", when="in 1 hour"))
        self.assertIn("bins out", self.run_tool("reminders_list"))
        self.run_tool("reminder_done", id=r["id"])
        self.assertEqual(self.run_tool("reminders_list"), "no reminders")
        with self.assertRaises(ToolError):
            self.run_tool("reminder_set", text="x", when="sometime")

    def test_delete_asks_first(self):
        self.assertEqual(hands.TOOLS["notes_delete"].permission, "ask")


if __name__ == "__main__":
    unittest.main()
