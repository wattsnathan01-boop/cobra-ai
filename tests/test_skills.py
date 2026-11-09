import tempfile
import unittest
from pathlib import Path

from cobrad.brain.router import choose
from cobrad.hands import ToolError, skills


class SkillsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        mine, shared = root / "mine", root / "shared"
        for d, name, desc in [(mine, "video", "Mine"), (shared, "video", "Shared"),
                              (shared, "maps", "Map animations")]:
            (d / name / "rules").mkdir(parents=True, exist_ok=True)
            (d / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\nHow to {name}.\n")
        (shared / "maps" / "rules" / "timing.md").write_text("timing tips")
        (shared / "maps" / "icon.png").write_bytes(b"\x89PNG")
        (root / "secret.md").write_text("nope")
        self.old = list(skills.DIRS)
        skills.configure([str(mine), str(shared), str(root / "missing")])

    def tearDown(self):
        skills.DIRS[:] = self.old
        self.tmp.cleanup()

    def test_list_prefers_earlier_folders(self):
        listing = skills.skills_list()
        self.assertIn("video: Mine", listing)
        self.assertNotIn("Shared", listing)
        self.assertIn("maps: Map animations", listing)

    def test_read_skill_and_pages(self):
        self.assertIn("How to maps.", skills.skill_read("maps"))
        self.assertEqual(skills.skill_read("maps", "rules/timing.md"), "timing tips")

    def test_refuses_outside_missing_and_binary(self):
        with self.assertRaises(ToolError):
            skills.skill_read("maps", "../../secret.md")
        with self.assertRaises(ToolError) as e:
            skills.skill_read("maps", "nope.md")
        self.assertIn("rules/timing.md", str(e.exception))
        with self.assertRaises(ToolError):
            skills.skill_read("maps", "icon.png")
        with self.assertRaises(ToolError):
            skills.skill_read("cooking")

    def test_video_jobs_go_to_claude(self):
        self.assertEqual(choose("make me a video about my cat with remotion", "auto", True), "claude")
        self.assertEqual(choose("play the next video", "auto", True), "local")


if __name__ == "__main__":
    unittest.main()
