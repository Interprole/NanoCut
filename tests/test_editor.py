"""Regression coverage for edits that must agree at exact frame boundaries."""

import array
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nanocut.media import ff, probe, render, run, subtitle_file
from nanocut.server import Workspace, atomic_json
from nanocut.tasks import prepare


class EditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.cache = patch("nanocut.tasks.CACHE", cls.root / "cache")
        cls.cache.start()
        a = cls.root / "two colors.mp4"
        ff(
            "-f",
            "lavfi",
            "-i",
            "color=red:s=96x64:r=24:d=0.5",
            "-f",
            "lavfi",
            "-i",
            "color=blue:s=96x64:r=24:d=0.5",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=330:duration=1",
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0[v]",
            "-map",
            "[v]",
            "-map",
            "2:a",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            a,
        )
        b = cls.root / "green overlay.png"
        ff("-f", "lavfi", "-i", "color=lime:s=96x64", "-frames:v", "1", b)
        cls.assets = {a["id"]: a for a in (prepare(a), prepare(b))}
        cls.base, cls.overlay = cls.assets
        cls.clip = dict(
            id="base",
            asset=cls.base,
            track=1,
            start=0,
            length=24,
            offset=0,
            rate=1,
            scale=1,
            x=0.5,
            y=0.5,
            volume=1,
            guide=False,
            cues=[],
            style="Studio",
        )

    @classmethod
    def tearDownClass(cls):
        cls.cache.stop()
        cls.temp.cleanup()

    def project(self, clips=None):
        return dict(
            name="Unit edit",
            width=96,
            height=64,
            fps=24,
            library=list(self.assets),
            clips=copy.deepcopy(clips if clips is not None else [self.clip]),
        )

    def pixels(self, p, file="output.mp4", w=96, h=64, fps=24):
        path = self.root / file
        render(p, self.assets, path, w, h, fps)
        return run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                path,
                "-an",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "pipe:1",
            ]
        )

    def test_speed_offset_and_overlay_frames(self):
        p = self.project(
            [
                dict(self.clip, offset=0.25, rate=2, length=9, start=2),
                dict(
                    self.clip,
                    id="overlay",
                    asset=self.overlay,
                    track=2,
                    start=3,
                    length=2,
                    scale=0.5,
                ),
            ]
        )
        rgb = self.pixels(p)
        self.assertEqual(len(rgb), 11 * 96 * 64 * 3)

        def pixel(frame, x=48, y=32):
            idx = ((frame * 64 + y) * 96 + x) * 3
            return tuple(rgb[idx : idx + 3])

        def assert_color(f, channel, x=48):
            color = pixel(f, x)
            self.assertGreater(color[channel], 200, (f, color))
            self.assertLess(max(v for i, v in enumerate(color) if i != channel), 40)

        self.assertLess(max(pixel(1)), 12)
        assert_color(2, 0)
        assert_color(3, 1)
        assert_color(4, 1)
        assert_color(4, 0, 5)
        assert_color(5, 2)
        assert_color(10, 2)

    def test_guide_audio_excluded_and_formats(self):
        p = self.project(
            [dict(self.clip, volume=0), dict(self.clip, id="guide", track=0, guide=True, length=96)]
        )
        for ext in ["wav", "flac", "m4a", "mp3", "mov", "webm", "mkv", "mp4"]:
            with self.subTest(ext=ext):
                path = self.root / ("mix." + ext)
                render(p, self.assets, path, 96, 64, 30)
                info = probe(path)
                self.assertAlmostEqual(info["duration"], 1, delta=0.09)
                pcm = run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-f", "s16le", "pipe:1"])
                self.assertLessEqual(max(map(abs, array.array("h", pcm))), 1)
        p["clips"][0]["volume"] = 1
        render(p, self.assets, self.root / "audible.wav", 96, 64, 24)
        self.assertTrue(
            any(
                run(
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-i",
                        self.root / "audible.wav",
                        "-f",
                        "s16le",
                        "pipe:1",
                    ]
                )
            )
        )

    def test_caption_timing_and_burn_in(self):
        p = self.project(
            [
                dict(
                    self.clip,
                    offset=0.25,
                    rate=0.5,
                    start=6,
                    length=18,
                    cues=[
                        {"in": 0, "out": 0.5, "text": "ONE"},
                        {"in": 0.5, "out": 1, "text": "TWO"},
                    ],
                )
            ]
        )
        srt = subtitle_file(p, False)
        self.assertIn("00:00:00,250 --> 00:00:00,750", srt)
        self.assertIn("00:00:00,750 --> 00:00:01,000", srt)
        annotated = self.pixels(p, "captions.mp4", 320, 240)
        p["clips"][0]["cues"] = []
        plain = self.pixels(p, "plain.mp4", 320, 240)
        self.assertNotEqual(annotated, plain)

    def test_project_roundtrip_and_source_integrity(self):
        p = self.project()
        workspace = Workspace()
        workspace.assets = dict(self.assets)
        out = self.root / "project.nano"
        atomic_json(out, workspace.pack(p, self.root))
        self.assertFalse(
            any(Path(k).is_absolute() for k in json.loads(out.read_text())["media"].values())
        )
        fresh = Workspace()
        self.assertEqual(fresh.load(out)["project"], p)
        self.assertEqual(set(fresh.assets), set(self.assets))
        dest = self.root / "keep.mp4"
        dest.write_bytes(b"previous export")
        p["clips"][0]["rate"] = 0
        with self.assertRaises(ValueError):
            render(p, self.assets, dest, 96, 64, 24)
        self.assertEqual(dest.read_bytes(), b"previous export")


if __name__ == "__main__":
    unittest.main()
