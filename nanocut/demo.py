"""Generate the bundled example locally using only FFmpeg and the standard library."""

import math
import struct
import zlib

from .media import ff
from .tasks import CACHE, prepare


def artwork(path, phase):
    w, h = 640, 360
    data = bytearray()
    for y in range(h):
        data.append(0)
        for x in range(w):
            u, v = (x - w * 0.5) / (h * 0.79), (y - h * 0.50) / (h * 0.79)
            a = math.atan2(v, u) + phase
            r = math.hypot(u, v)
            ridge = 0.53 + 0.11 * math.sin(3 * a + 0.4) + 0.043 * math.cos(5 * a)
            delta = r - ridge
            wave = 0.5 + 0.5 * math.cos(238 * delta + 4 * math.sin(3 * a + 7 * r))
            glow = math.exp(-abs(delta) * 11)
            stripe = glow * (0.23 + 0.77 * wave**3)
            t = 0.5 + 0.5 * math.sin(a + phase * 2)
            colors = (75 + 172 * t, 238 - 149 * t, 221 + 20 * t)
            data.extend(
                min(255, int(b + stripe * c + glow * 18)) for b, c in zip((9, 13, 21), colors)
            )

    def chunk(tag, contents):
        return (
            struct.pack(">I", len(contents))
            + tag
            + contents
            + struct.pack(">I", zlib.crc32(tag + contents) & 0xFFFFFFFF)
        )

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">2I5B", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(data))
        + chunk(b"IEND", b"")
    )


def example():
    folder = CACHE / "orbital-study-v1"
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, name in enumerate(("Orbit", "Refraction")):
        path = folder / (name + ".mp4")
        if not path.exists():
            art = folder / (name + ".png")
            artwork(art, i * 1.15)
            ff(
                "-i",
                art,
                "-vf",
                "zoompan=z='1+0.0012*on':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=144:s=640x360:fps=24",
                "-frames:v",
                "144",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "veryfast",
                path,
            )
        paths.append(path)
    audio = folder / "Low tide.wav"
    if not audio.exists():
        ff(
            "-f",
            "lavfi",
            "-i",
            "aevalsrc=0.05*(sin(2*PI*110*t)+0.45*sin(2*PI*165*t))*(0.55+0.45*sin(2*PI*0.35*t)):s=44100:d=10",
            "-af",
            "afade=t=in:d=1,afade=t=out:st=8.7:d=1.3",
            audio,
        )
    assets = [prepare(p) for p in [*paths, audio]]

    def clip(i, track, start, length):
        return dict(
            id=f"demo{i}",
            asset=assets[i]["id"],
            track=track,
            start=start,
            length=length,
            offset=0,
            rate=1,
            scale=1,
            x=0.5,
            y=0.5,
            volume=1,
            guide=False,
            style="Cinema",
            cues=[],
        )

    return assets, dict(
        name="Orbital study",
        fps=24,
        width=1280,
        height=720,
        library=[a["id"] for a in assets],
        clips=[clip(0, 1, 0, 120), clip(1, 1, 120, 120), clip(2, 0, 0, 240)],
    )
