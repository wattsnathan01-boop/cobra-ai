import asyncio
import io
import json
import unittest
from unittest import mock

from cobrad import screen
from cobrad.hands import ToolError

from test_core import run


def png(w, h, color="white"):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


MONITORS = [{"id": 0, "name": "eDP-1", "x": 0, "y": 0, "width": 1920, "height": 1200, "scale": 1,
             "transform": 0, "focused": False, "activeWorkspace": {"id": 1},
             "specialWorkspace": {"id": 0}},
            {"id": 1, "name": "HDMI-A-1", "x": 1920, "y": 0, "width": 1920, "height": 1080,
             "scale": 1, "transform": 0, "focused": True, "activeWorkspace": {"id": 2},
             "specialWorkspace": {"id": 0}}]
CLIENTS = [
    {"class": "kitty", "title": "nvim", "monitor": 1, "workspace": {"id": 2},
     "at": [1920, 0], "size": [960, 1080]},
    {"class": "Bitwarden", "title": "Vault", "monitor": 1, "workspace": {"id": 2},
     "at": [2880, 0], "size": [960, 540]},
    {"class": "firefox", "title": "Monzo - online banking", "monitor": 1, "workspace": {"id": 2},
     "at": [2880, 540], "size": [960, 540]},
    {"class": "steam", "title": "Steam", "monitor": 1, "workspace": {"id": 5},  # not visible
     "at": [1920, 0], "size": [400, 400]},
]


class CaptureTests(unittest.TestCase):
    def setUp(self):
        screen.SETTINGS["hide"] = ["bitwarden", "monzo"]
        screen.SETTINGS["max_side"] = 1280

    def capture(self, target="screen", active=None):
        async def fake_sh(*cmd, timeout=10):
            return json.dumps({"monitors": MONITORS, "clients": CLIENTS,
                               "activewindow": active or CLIENTS[0]}[cmd[1]])

        async def fake_grim(*cmd, timeout=10):
            self.grim = cmd
            size = cmd[cmd.index("-g") + 1].split(" ")[1]
            w, h = (int(float(v)) for v in size.split("x"))
            return png(w, h)
        with mock.patch.object(screen, "sh", fake_sh), mock.patch.object(screen, "sh_bytes", fake_grim):
            return run(screen.capture(target))

    def test_focused_monitor_with_private_windows_blacked_out(self):
        from PIL import Image
        shot = self.capture()
        self.assertEqual(shot.monitor, "HDMI-A-1")
        self.assertIn("1920,0 1920.0x1080.0", " ".join(self.grim))
        self.assertEqual(shot.hidden, 2)
        self.assertEqual(shot.windows, ["kitty"])  # steam is on another workspace
        self.assertEqual(max(shot.width, shot.height), 1280)
        img = Image.open(io.BytesIO(shot.png))
        self.assertEqual(img.getpixel((100, 100)), (255, 255, 255))      # kitty: visible
        self.assertEqual(img.getpixel((1000, 100)), (0, 0, 0))           # bitwarden: hidden
        self.assertEqual(img.getpixel((1000, 600)), (0, 0, 0))           # bank tab: hidden

    def test_refuses_to_look_at_a_private_focused_window(self):
        with self.assertRaises(ToolError):
            self.capture("window", active=CLIENTS[1])


class BoxTests(unittest.TestCase):
    def shot(self):
        return screen.Shot(b"", 1280, 720, "HDMI-A-1", (1920, 0), (1920, 1080))

    def test_maps_0_to_1000_onto_the_screen(self):
        box = screen.find_box('```json\n[{"bbox_2d": [100, 500, 300, 550], "label": "x"}]\n```',
                              self.shot())
        self.assertAlmostEqual(box["x"], 1920 + 192)
        self.assertAlmostEqual(box["y"], 540)
        self.assertAlmostEqual(box["w"], 384)
        self.assertAlmostEqual(box["h"], 54)

    def test_pixel_coordinates_are_converted(self):
        box = screen.find_box('[{"bbox_2d": [640, 360, 1280, 720]}]', self.shot())
        self.assertAlmostEqual(box["x"], 1920 + 960)
        self.assertAlmostEqual(box["w"], 960)

    def test_no_box(self):
        self.assertIsNone(screen.find_box("I can't find that.", self.shot()))

    def test_point_line_is_split_off(self):
        self.assertEqual(screen.split_point("Line 13 binds it.\nPOINT: the line \"bind = SUPER\"."),
                         ("Line 13 binds it.", 'the line "bind = SUPER"'))
        self.assertEqual(screen.split_point("Nothing to point at."), ("Nothing to point at.", None))


class LookTests(unittest.TestCase):
    def test_look_emits_indicators_and_a_point(self):
        events = []

        async def notify(ev):
            events.append(ev)
        shot = screen.Shot(b"x", 1000, 1000, "eDP-1", (0, 0), (1920, 1200), ["kitty"], 1)

        async def fake_capture(target):
            return shot

        async def fake_vision(s, prompt):
            if prompt.startswith("Locate"):
                return '[{"bbox_2d": [10, 10, 20, 20]}]'
            return "It's a missing semicolon.\nPOINT: the semicolon on line 4"
        with mock.patch.object(screen, "capture", fake_capture), \
                mock.patch.object(screen, "_vision", fake_vision), \
                mock.patch.object(screen, "notify", notify):
            out = run(screen.screen_look("what's wrong?"))
        self.assertIn("missing semicolon", out)
        self.assertIn("1 private window", out)
        self.assertEqual([e.get("state") or e.get("action") or e["type"] for e in events],
                         ["hide", "looking", "off", "point"])


if __name__ == "__main__":
    unittest.main()
