import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from cobrad import settings
from cobrad.gate import Gate

from test_core import make_agent, run


class SetTomlTests(unittest.TestCase):
    def test_changes_only_that_value_and_keeps_comments(self):
        p = Path(tempfile.mkdtemp()) / "c.toml"
        p.write_text('# mine\n[voice]\n# which one\npiper_voice = "a"\n\n[files]\n'
                     'allowed = [\n    "~/x",\n]\nother = ["inline"]\n')
        settings.set_toml(p, "voice", "piper_voice", "b")
        settings.set_toml(p, "files", "allowed", ["~/y"])
        settings.set_toml(p, "wake", "enabled", False)
        text = p.read_text()
        self.assertIn("# mine", text)
        self.assertIn("# which one", text)
        self.assertEqual(tomllib.loads(text), {"voice": {"piper_voice": "b"},
                                               "files": {"allowed": ["~/y"], "other": ["inline"]},
                                               "wake": {"enabled": False}})


class FakeServer:
    def __init__(self, tmp):
        self.agent, _ = make_agent([])
        self.agent.gate = Gate({}, tmp / "audit.jsonl")
        self.wake = None
        self.voice = None
        self.follow_up_seconds = 8
        self.info = {"voice": "en_GB-cori-high", "model": "qwen3:8b"}


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patch = mock.patch.object(settings, "config_dir", return_value=self.tmp)
        self.patch.start()
        self.server = FakeServer(self.tmp)

    def tearDown(self):
        self.patch.stop()

    def test_permission_change_is_saved_and_live(self):
        from cobrad import hands
        hands.load_all()
        run(settings.apply(self.server, "permission.hypr_close", "always"))
        self.assertEqual(self.server.agent.gate.level("hypr_close"), "always")
        saved = tomllib.loads((self.tmp / "permissions.toml").read_text())
        self.assertEqual(saved["tools"]["hypr_close"], "always")

    def test_commands_can_never_be_always(self):
        from cobrad import hands
        hands.load_all()
        for tool in ("shell_run", "sudo_run"):
            with self.assertRaises(settings.SettingError):
                run(settings.apply(self.server, f"permission.{tool}", "always"))

    def test_persona_and_follow_up(self):
        run(settings.apply(self.server, "persona", "You are Cobra. Be brief and kind."))
        self.assertIn("brief and kind", self.server.agent.persona)
        self.assertIn("brief and kind", (self.tmp / "persona.md").read_text())
        run(settings.apply(self.server, "wake.follow_up_seconds", 99))
        self.assertEqual(self.server.follow_up_seconds, 20)  # clamped

    def test_unknown_setting_and_bad_folder(self):
        with self.assertRaises(settings.SettingError):
            run(settings.apply(self.server, "nope", 1))
        with self.assertRaises(settings.SettingError):
            run(settings.apply(self.server, "files.allowed", ["relative/folder"]))


if __name__ == "__main__":
    unittest.main()
