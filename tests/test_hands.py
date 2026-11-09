import asyncio
import os
import tempfile
import tomllib
import unittest
from unittest import mock
from pathlib import Path

from cobrad import hands
from cobrad.gate import Gate
from cobrad.hands import ToolError, files, shell

from test_core import make_agent, run


class FileSandboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.allowed = self.tmp / "notes"
        self.allowed.mkdir()
        (self.allowed / "todo.md").write_text("one\ntwo\nthree\n")
        self.outside = self.tmp / "private"
        self.outside.mkdir()
        (self.outside / "secret.txt").write_text("hunter2")
        files.configure([str(self.allowed)])
        self._never = list(files.NEVER)

    def tearDown(self):
        files.NEVER[:] = self._never

    def test_reads_inside_allowed_folders(self):
        out = files.files_read(str(self.allowed / "todo.md"))
        self.assertIn("two", out)
        self.assertIn("todo.md", files.files_list(str(self.allowed)))

    def test_refuses_outside_dotdot_and_symlink_escapes(self):
        for path in [self.outside / "secret.txt", self.allowed / ".." / "private" / "secret.txt"]:
            with self.assertRaises(ToolError):
                files.files_read(str(path))
        (self.allowed / "sneaky").symlink_to(self.outside)
        with self.assertRaises(ToolError):
            files.files_read(str(self.allowed / "sneaky" / "secret.txt"))
        with self.assertRaises(ToolError):
            files.files_read("relative/path.md")

    def test_off_limits_even_inside_an_allowed_folder(self):
        keys = self.allowed / "keys"
        keys.mkdir()
        (keys / "id").write_text("key")
        files.NEVER.append(str(keys))
        with self.assertRaises(ToolError):
            files.files_read(str(keys / "id"))
        self.assertNotIn("keys", run(files.files_search("key")))

    def test_search_by_name_and_content(self):
        self.assertIn("todo.md", run(files.files_search("todo")))
        self.assertIn("todo.md:2:two", run(files.files_search("two")))
        self.assertNotIn("secret", run(files.files_search("hunter2")))

    def test_edit_shows_a_diff_then_saves_with_a_backup(self):
        path = str(self.allowed / "todo.md")
        p = run(files.files_write_preview(path, find="two", replace="TWO"))
        self.assertEqual(p["kind"], "edit")
        self.assertIn({"op": "-", "text": "two"}, p["diff"])
        self.assertIn({"op": "+", "text": "TWO"}, p["diff"])
        self.assertTrue(p["summary"].startswith("1 line changed"), p["summary"])
        self.assertNotEqual(p["diff"][0]["op"], "@")
        files.files_write(path, find="two", replace="TWO")
        self.assertEqual((self.allowed / "todo.md").read_text(), "one\nTWO\nthree\n")
        self.assertEqual((self.allowed / "todo.md.bak").read_text(), "one\ntwo\nthree\n")

    def test_edit_text_must_appear_exactly_once(self):
        path = str(self.allowed / "todo.md")
        for find in ["missing", "o"]:
            with self.assertRaises(ToolError):
                run(files.files_write_preview(path, find=find, replace="x"))

    def test_create_a_new_file(self):
        path = str(self.allowed / "new" / "idea.md")
        self.assertEqual(run(files.files_write_preview(path, content="hi\n"))["kind"], "create")
        files.files_write(path, content="hi\n")
        self.assertEqual((self.allowed / "new" / "idea.md").read_text(), "hi\n")
        self.assertFalse((self.allowed / "new" / "idea.md.bak").exists())


class ShellTests(unittest.TestCase):
    def test_runs_and_reports_exit_code(self):
        out = run(shell.shell_run("echo hello; exit 3"))
        self.assertTrue(out.startswith("exit code 3"))
        self.assertIn("hello", out)

    def test_root_commands_go_to_sudo_run(self):
        for cmd in ["sudo pacman -Syu", "ls && sudo rm x"]:
            with self.assertRaises(ToolError):
                run(shell.shell_run_preview(cmd))
        self.assertIn("sudo", run(shell.sudo_run_preview("pacman -Syu"))["tags"])

    def test_timeout_stops_it(self):
        async def go():
            return await shell._run(["bash", "-c", "sleep 5"], Path("/"), timeout=0.2)
        with self.assertRaises(ToolError):
            run(go())


class GateRememberTests(unittest.TestCase):
    def test_always_is_saved_but_never_for_commands(self):
        tmp = Path(tempfile.mkdtemp())
        user = tmp / "permissions.toml"
        user.write_text('# mine\n[tools]\nmedia = "always"\n')
        gate = Gate({}, tmp / "audit.jsonl", user_file=user)
        self.assertTrue(gate.remember("files_write"))
        self.assertFalse(gate.remember("shell_run"))
        self.assertFalse(gate.remember("files_delete"))  # Never stays Never
        saved = tomllib.loads(user.read_text())["tools"]
        self.assertEqual(saved, {"media": "always", "files_write": "always"})
        self.assertTrue(user.read_text().startswith("# mine"))
        self.assertEqual(gate.level("files_write"), "always")


class AgentPermissionTests(unittest.TestCase):
    def test_never_tools_are_blocked_and_announced(self):
        tmp = Path(tempfile.mkdtemp()).resolve()
        (tmp / "old").write_text("x")
        files.configure([str(tmp)])
        events = []

        async def emit(ev):
            events.append(ev)
        agent, _ = make_agent([("", [{"name": "files_delete",
                                      "arguments": {"path": str(tmp / "old")}}]), ("Okay", None)])
        run(agent.ask("delete it", emit, None))
        self.assertTrue((tmp / "old").exists())
        blocked = next(e for e in events if e["type"] == "blocked")
        self.assertEqual(blocked["preview"]["kind"], "delete")

    def test_preview_reaches_the_confirm_and_bad_calls_never_ask(self):
        tmp = Path(tempfile.mkdtemp()).resolve()
        (tmp / "a.txt").write_text("hello\n")
        files.configure([str(tmp)])
        seen = []

        async def confirm(tool, args, preview=None):
            seen.append(preview)
            return False
        agent, _ = make_agent([
            ("", [{"name": "files_write", "arguments": {"path": str(tmp / "a.txt"),
                                                        "find": "nope", "replace": "x"}}]),
            ("", [{"name": "files_write", "arguments": {"path": str(tmp / "a.txt"),
                                                        "find": "hello", "replace": "bye"}}]),
            ("Okay", None)])
        run(agent.ask("edit it", lambda ev: asyncio.sleep(0), confirm))
        self.assertEqual(len(seen), 1)  # the bad find never reached you
        self.assertEqual(seen[0]["kind"], "edit")
        self.assertEqual((tmp / "a.txt").read_text(), "hello\n")


class HyprTests(unittest.TestCase):
    def test_lua_strings_are_escaped(self):
        from cobrad.hands.hypr import lua_str
        self.assertEqual(lua_str('say "hi" \\ bye'), '"say \\"hi\\" \\\\ bye"')

    def test_falls_back_to_classic_dispatch_on_older_hyprland(self):
        from cobrad.hands import hypr
        calls = []

        async def fake_sh(*cmd, timeout=10):
            calls.append(cmd)
            return "Invalid dispatcher" if len(calls) == 1 else "ok"
        real, hypr.sh = hypr.sh, fake_sh
        try:
            run(hypr.dispatch("hl.dsp.focus({ workspace = 2 })", "workspace", "2"))
        finally:
            hypr.sh = real
        self.assertEqual(calls[1], ("hyprctl", "dispatch", "workspace", "2"))

    def test_unknown_app_suggests_close_matches(self):
        from cobrad.hands.apps import match_app
        apps = {"google chrome": "google-chrome", "kitty": "kitty"}
        with self.assertRaises(ToolError) as e:
            match_app(apps, "kity")
        self.assertIn("kitty", str(e.exception))
        self.assertIn("browser", str(e.exception))


class PackageTests(unittest.TestCase):
    def fake_pacman(self, repo, aur=(), installed=()):
        from cobrad.hands import packages

        async def fake_c(*cmd, timeout=30):
            name = cmd[-1]
            if cmd[:2] == ("pacman", "-Si") and name in repo:
                return f"Repository      : extra\nName            : {name}\nVersion         : 1.0-1\nDownload Size   : 20.00 KiB\n"
            if cmd[:3] == ("yay", "-Si", "--aur") and name in aur:
                return f"Repository      : aur\nName            : {name}\nVersion         : 2.0-1\n"
            if cmd[:2] == ("pacman", "-Q") and name in installed:
                return f"{name} 1.0-1\n"
            raise ToolError("not found")
        return mock.patch.object(packages, "_c", fake_c)

    def test_preview_lists_what_will_be_installed(self):
        from cobrad.hands import packages
        with self.fake_pacman({"cowsay", "htop"}, installed={"htop"}):
            p = run(packages.packages_install_preview(["cowsay", "htop"]))
        self.assertEqual([(x["name"], bool(x["installed"])) for x in p["packages"]],
                         [("cowsay", False), ("htop", True)])
        self.assertEqual(p["command"], "pacman -S --needed cowsay")
        self.assertNotIn("AUR", p["tags"])

    def test_aur_packages_are_flagged(self):
        from cobrad.hands import packages
        with self.fake_pacman(set(), aur={"some-app-bin"}), mock.patch.object(packages.shutil, "which", return_value="/usr/bin/yay"):
            p = run(packages.packages_install_preview(["some-app-bin"]))
        self.assertIn("AUR", p["tags"])
        self.assertTrue(p["warning"])

    def test_refuses_unknown_installed_and_odd_names(self):
        from cobrad.hands import packages
        with self.fake_pacman({"htop"}, installed={"htop"}), mock.patch.object(packages.shutil, "which", return_value=None):
            for bad in (["htop"], ["nope"], ["rm -rf /"], []):
                with self.assertRaises(ToolError):
                    run(packages.packages_install_preview(bad))

    def test_installs_never_get_always(self):
        from cobrad.gate import NO_ALWAYS
        self.assertIn("packages_install", NO_ALWAYS)


class RegistryTests(unittest.TestCase):
    def test_new_tools_have_defaults(self):
        hands.load_all()
        self.assertEqual(hands.TOOLS["files_read"].permission, "always")
        self.assertEqual(hands.TOOLS["files_write"].permission, "ask")
        self.assertEqual(hands.TOOLS["shell_run"].permission, "ask")
        self.assertEqual(hands.TOOLS["files_delete"].permission, "never")


if __name__ == "__main__":
    unittest.main()
