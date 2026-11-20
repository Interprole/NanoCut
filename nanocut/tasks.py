"""Long-running operations executed in a separate, cancellable process."""

import hashlib
import os
import subprocess
import tempfile
import time
import wave
from pathlib import Path
from urllib.parse import urlparse

from .media import ff, n, probe, render

CACHE = Path(os.environ.get("NANOCUT_CACHE", Path.home() / ".nanocut" / "cache"))
MODELS = {"tiny": 0.13, "base": 0.24, "small": 0.65, "medium": 1.7, "large-v3": 3.4, "turbo": 1.15}


def prepare(path, notify=lambda *args: None):
    path = Path(path).resolve(strict=True)
    info = probe(path)
    key = hashlib.sha256(
        f"{path}|{path.stat().st_size}|{path.stat().st_mtime_ns}|3".encode()
    ).hexdigest()[:24]
    CACHE.mkdir(parents=True, exist_ok=True)
    thumb = CACHE / (key + ".jpg")
    preview = path
    ext = path.suffix.lower()
    direct = (
        (info["still"] and ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp"})
        or (not info["video"] and ext in {".mp3", ".wav", ".ogg", ".m4a", ".flac"})
        or (
            info["codec"] == "h264"
            and ext in {".mp4", ".m4v"}
            and info["acodec"] in {None, "aac", "mp3"}
        )
        or (info["codec"] in {"vp8", "vp9", "av1"} and ext == ".webm")
    )
    with tempfile.TemporaryDirectory(dir=CACHE) as tmp:
        tmp = Path(tmp)
        if not direct:
            notify("Preparing a playback copy", None)
            ext = (
                ".png"
                if info["still"]
                else (".webm" if info["alpha"] and info["video"] else ".mp4")
                if info["video"]
                else ".m4a"
            )
            preview = CACHE / (key + ext)
            if not preview.exists():
                if info["still"]:
                    opt = ["-frames:v", "1"]
                elif info["video"]:
                    opt = ["-vf", "scale='min(1280,iw)':-2"]
                    opt += (
                        [
                            "-c:v",
                            "libvpx-vp9",
                            "-pix_fmt",
                            "yuva420p",
                            "-auto-alt-ref",
                            "0",
                            "-deadline",
                            "realtime",
                            "-cpu-used",
                            "6",
                            "-c:a",
                            "libopus",
                        ]
                        if ext == ".webm"
                        else [
                            "-c:v",
                            "libx264",
                            "-preset",
                            "ultrafast",
                            "-pix_fmt",
                            "yuv420p",
                            "-c:a",
                            "aac",
                            "-movflags",
                            "+faststart",
                        ]
                    )
                else:
                    opt = ["-vn", "-c:a", "aac"]
                ff("-i", path, *opt, tmp / preview.name)
                os.replace(tmp / preview.name, preview)
        if not thumb.exists():
            if info["video"]:
                ff(
                    "-i",
                    path,
                    "-vf",
                    "scale=256:144:force_original_aspect_ratio=decrease,pad=256:144:(ow-iw)/2:(oh-ih)/2",
                    "-frames:v",
                    "1",
                    tmp / "thumb.jpg",
                )
            else:
                ff(
                    "-t",
                    min(45, info["duration"]),
                    "-i",
                    path,
                    "-filter_complex",
                    "aformat=channel_layouts=mono,showwavespic=s=256x144:colors=0x69d7c1",
                    "-frames:v",
                    "1",
                    tmp / "thumb.jpg",
                )
            os.replace(tmp / "thumb.jpg", thumb)
    return dict(info, id=key, path=str(path), preview=str(preview), thumb=str(thumb))


def download(d, notify):
    parsed = urlparse(d["url"].strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not any(
        host == h or host.endswith("." + h) for h in ("youtube.com", "youtu.be", "tiktok.com")
    ):
        raise ValueError("Enter an HTTPS YouTube or TikTok link.")
    try:
        import yt_dlp
        from yt_dlp.utils import download_range_func
    except ImportError:
        raise ValueError("Install the download tools using Setup.cmd or the README.") from None
    a = n(d.get("from", 0), 0, 10**7)
    b = n(d["to"], 0, 10**7) if d.get("to") is not None else float("inf")
    if b <= a:
        raise ValueError("End time must be after start time.")
    dest = Path(d["dest"])
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        output = Path(tmp) / ("ready" + dest.suffix)

        def progress(s):
            total = s.get("total_bytes") or s.get("total_bytes_estimate")
            notify("Downloading media", (s.get("downloaded_bytes", 0) / total if total else None))

        opts = dict(
            outtmpl=str(Path(tmp) / "source.%(ext)s"),
            noplaylist=True,
            quiet=True,
            progress_hooks=[progress],
            format="bestaudio/best" if dest.suffix == ".mp3" else "bv*+ba/b",
            merge_output_format="mkv",
            js_runtimes={"node": {}, "deno": {}},
            compat_opts={"no-certifi"},
        )
        local_trim = d.get("transfer") == "full" and (a or b != float("inf"))
        if not local_trim and (a or b != float("inf")):
            opts.update(
                download_ranges=download_range_func(None, [(a, b)]), force_keyframes_at_cuts=True
            )
        with yt_dlp.YoutubeDL(opts) as dl:
            try:
                dl.download([parsed.geturl()])
            except yt_dlp.utils.DownloadError as exc:
                extra = (
                    " Try Full source transfer if the server does not support excerpt requests."
                    if not local_trim
                    else ""
                )
                raise ValueError(str(exc) + extra) from exc
        source = next(
            (f for f in Path(tmp).glob("source.*") if f.suffix not in {".part", ".ytdl"}), None
        )
        if not source:
            raise ValueError("The download produced no media file.")
        notify("Preparing downloaded clip", None)
        trim = ["-ss", str(a)] if local_trim else []
        if local_trim and b != float("inf"):
            trim += ["-t", str(b - a)]
        if dest.suffix.lower() == ".mp3":
            ff(*trim, "-i", source, "-vn", "-c:a", "libmp3lame", "-q:a", "2", output)
        else:
            ff(
                *trim,
                "-i",
                source,
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-vf",
                "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                output,
            )
        os.replace(output, dest)
    return prepare(dest, notify)


def transcribe(d, notify):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise ValueError("Install local AI tools first. On Windows, run Install-AI.cmd.") from None
    import numpy as np

    model = d["model"]
    if model not in MODELS:
        raise ValueError("Unknown Whisper model.")
    pos, duration = d["offset"], d["duration"]
    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / "speech.wav"
        notify("Reading clip audio", None)
        ff("-ss", pos, "-t", duration, "-i", d["path"], "-vn", "-ac", "1", "-ar", "16000", audio)
        notify("Loading Whisper · first use downloads the model", None)
        engine = WhisperModel(
            model,
            device="cpu",
            compute_type="int8",
            cpu_threads=max(1, min(os.cpu_count() or 4, 8)),
        )
        start = time.monotonic()
        with wave.open(str(audio), "rb") as wav:
            samples = (
                np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float32)
                / 32768
            )
        segments, _ = engine.transcribe(
            samples, language=d.get("language") or None, beam_size=3, vad_filter=True
        )
        cues = []
        for s in segments:
            if s.text.strip():
                cues.append(
                    {"in": pos + s.start, "out": pos + min(duration, s.end), "text": s.text.strip()}
                )
            elapsed = time.monotonic() - start
            remain = round(elapsed * max(0, duration - s.end) / max(0.01, s.end))
            notify(f"Recognizing speech · about {remain}s left", min(0.99, s.end / duration))
        return {"cues": cues, "ratio": (time.monotonic() - start) / max(0.01, duration)}


def cutout(d, notify):
    try:
        from PIL import Image
        from rembg import new_session, remove
    except ImportError:
        raise ValueError("Install local AI tools first. On Windows, run Install-AI.cmd.") from None
    src, dest = d["path"], Path(d["dest"])
    info = probe(src)
    fps = d["fps"]
    scale = min(1, 1280 / max(info["width"], info["height"]))
    w, h = (max(2, round(v * scale / 2) * 2) for v in (info["width"], info["height"]))
    notify("Loading background model · first use downloads weights", None)
    session = new_session("u2netp", providers=["CPUExecutionProvider"])
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        tmp = Path(tmp)
        out = tmp / ("foreground" + dest.suffix)
        if info["still"]:
            with Image.open(src) as im:
                remove(im.convert("RGB"), session=session).save(out, "PNG")
        else:
            args = [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-ss",
                str(d["offset"]),
                "-t",
                str(d["duration"]),
                "-i",
                src,
                "-vf",
                f"fps={fps},scale={w}:{h}",
                "-an",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "pipe:1",
            ]
            enc = [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgba",
                "-s",
                f"{w}x{h}",
                "-r",
                str(fps),
                "-i",
                "pipe:0",
                "-ss",
                str(d["offset"]),
                "-t",
                str(d["duration"]),
                "-i",
                src,
                "-map",
                "0:v",
                "-map",
                "1:a?",
                "-c:v",
                "libvpx-vp9",
                "-deadline",
                "realtime",
                "-cpu-used",
                "6",
                "-auto-alt-ref",
                "0",
                "-pix_fmt",
                "yuva420p",
                "-c:a",
                "libopus",
                str(out),
            ]
            with (
                subprocess.Popen(args, stdout=subprocess.PIPE) as reader,
                subprocess.Popen(enc, stdin=subprocess.PIPE) as writer,
            ):
                count = 0
                try:
                    while data := reader.stdout.read(w * h * 3):
                        frame = Image.frombytes("RGB", (w, h), data)
                        writer.stdin.write(remove(frame, session=session).convert("RGBA").tobytes())
                        count += 1
                        notify(
                            f"Removing background · frame {count}",
                            min(0.99, count / max(1, d["duration"] * fps)),
                        )
                finally:
                    reader.stdout.close()
                    writer.stdin.close()
                if reader.wait() or writer.wait() or not count:
                    raise ValueError("Background removal could not encode the clip.")
        os.replace(out, dest)
    return prepare(dest, notify)


def worker(kind, d, queue):
    if os.name != "nt":
        os.setsid()

    def notify(label, fraction):
        queue.put(("progress", (label, fraction)))

    try:
        if kind == "import":
            result = [prepare(p, notify) for p in d["paths"]]
        elif kind == "export":
            render(d["project"], d["assets"], d["dest"], d["width"], d["height"], d["fps"], notify)
            result = d["dest"]
        elif kind == "download":
            result = download(d, notify)
        elif kind == "whisper":
            result = transcribe(d, notify)
        elif kind == "cutout":
            result = cutout(d, notify)
        elif kind == "tiktok":
            from .tiktok import send_draft

            result = send_draft(d["path"], notify)
        else:
            raise ValueError("Unknown operation.")
        queue.put(("done", result))
    except Exception as exc:
        queue.put(("error", str(exc) or type(exc).__name__))
