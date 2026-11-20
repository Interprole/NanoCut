"""Read local media and render frame-based edits with FFmpeg."""

import json
import math
import os
import subprocess
import tempfile
from pathlib import Path

FORMATS = {
    "mp4": [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "19",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
    ],
    "mov": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac"],
    "mkv": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-c:a", "aac"],
    "webm": [
        "-c:v",
        "libvpx-vp9",
        "-deadline",
        "realtime",
        "-cpu-used",
        "6",
        "-crf",
        "32",
        "-b:v",
        "0",
        "-c:a",
        "libopus",
    ],
    "mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
    "wav": ["-c:a", "pcm_s16le"],
    "m4a": ["-c:a", "aac", "-b:a", "192k"],
    "flac": ["-c:a", "flac"],
}
VIDEO = {"mp4", "mov", "mkv", "webm"}
STYLES = {
    "Studio": ("Arial", 46, "&H00FFFFFF", -1, 1, 3),
    "Headline": ("Arial", 60, "&H004CE8FF", -1, 1, 4),
    "Cinema": ("Georgia", 46, "&H00E5F0FF", 0, 1, 2),
    "Boxed": ("Arial", 44, "&H00FFFFFF", -1, 3, 5),
    "Signal": ("Courier New", 43, "&H00BBFFC8", -1, 1, 3),
}


def run(args, **kwargs):
    proc = subprocess.run(
        [str(a) for a in args], stdout=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), stderr=subprocess.PIPE, **kwargs
    )
    if proc.returncode:
        raise ValueError(proc.stderr.decode(errors="replace")[-1800:] or "Media processing failed.")
    return proc.stdout


def ff(*args, **kwargs):
    return run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args], **kwargs)


def probe(path):
    data = json.loads(
        run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path])
    )
    streams = data["streams"]
    v = next(
        (
            s
            for s in streams
            if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic")
        ),
        {},
    )
    a = next((s for s in streams if s["codec_type"] == "audio"), {})
    still = bool(v) and data["format"]["format_name"] in {
        "image2",
        "png_pipe",
        "jpeg_pipe",
        "webp_pipe",
        "bmp_pipe",
        "tiff_pipe",
    }
    duration = float(
        data["format"].get("duration")
        or v.get("duration")
        or a.get("duration")
        or (5 if still else 0)
    )
    if not (v or a) or not math.isfinite(duration) or duration <= 0:
        raise ValueError("This file has no readable media duration.")
    w, h = v.get("width", 0), v.get("height", 0)
    rotation = next(
        (s.get("rotation", 0) for s in v.get("side_data_list", []) if "rotation" in s), 0
    )
    if abs(rotation) % 180 == 90:
        w, h = h, w
    return dict(
        name=Path(path).name,
        duration=duration,
        width=w,
        height=h,
        video=bool(v),
        audio=bool(a),
        still=still,
        codec=v.get("codec_name"),
        acodec=a.get("codec_name"),
        alpha=v.get("pix_fmt", "").startswith(
            ("yuva", "rgba", "bgra", "argb", "abgr", "gbrap", "ya")
        )
        or v.get("tags", {}).get("alpha_mode") == "1",
    )


def n(value, lo, hi):
    value = float(value)
    if not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError("An edit is outside the supported range.")
    return value


def whole(value, lo, hi):
    value = n(value, lo, hi)
    if not value.is_integer():
        raise ValueError("Frame positions must be whole numbers.")
    return int(value)


def atempo(rate):
    parts = []
    while rate < 0.5:
        parts.append("atempo=0.5")
        rate *= 2
    while rate > 2:
        parts.append("atempo=2")
        rate /= 2
    return ",".join([*parts, f"atempo={rate:.9f}"])


def captions(p):
    fps = p["fps"]
    for c in sorted(p["clips"], key=lambda x: (x["track"], x["start"])):
        if c.get("guide"):
            continue
        for cue in c.get("cues", []):
            start = max(0, (cue["in"] - c["offset"]) / c["rate"])
            end = min(c["length"] / fps, (cue["out"] - c["offset"]) / c["rate"])
            if end > start:
                yield (
                    c["start"] / fps + start,
                    c["start"] / fps + end,
                    c.get("style", "Studio"),
                    cue["text"],
                )


def stamp(seconds, scale, sep):
    ticks = round(seconds * scale)
    s, fraction = divmod(ticks, scale)
    minutes, s = divmod(s, 60)
    h, m = divmod(minutes, 60)
    return f"{h:02}:{m:02}:{s:02}{sep}{fraction:0{len(str(scale)) - 1}}"


def subtitle_file(p, ass):
    cues = sorted(captions(p), key=lambda cue: cue[0])
    if not ass:
        return "\n".join(
            f"{i}\n{stamp(a, 1000, ',')} --> {stamp(b, 1000, ',')}\n{t}\n"
            for i, (a, b, _, t) in enumerate(cues, 1)
        )
    width = round(1080 * p["width"] / p["height"])
    header = (
        f"[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: 1080\nWrapStyle: 0\n"
        "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
        "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
    )
    for name, (font, size, color, bold, border, outline) in STYLES.items():
        header += f"Style: {name},{font},{size},{color},&H000000FF,&H00171010,&H80101010,{bold},0,0,0,100,100,0,0,{border},{outline},0,2,30,30,65,1\n"
    header += "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    for a, b, style, t in cues:
        t = (
            t.replace("\\", "＼")
            .replace("{", "｛")
            .replace("}", "｝")
            .replace("\r", "")
            .replace("\n", r"\N")
        )
        header += f"Dialogue: 0,{stamp(a, 100, '.')},{stamp(b, 100, '.')},{style if style in STYLES else 'Studio'},,0,0,0,,{t}\n"
    return header


def render(p, assets, dest, width, height, fps, notify=lambda *args: None):
    """Compose originals. Clip intervals are half-open in the project timebase."""
    fmt = Path(dest).suffix.lower()[1:]
    if fmt not in FORMATS:
        raise ValueError("Choose a supported export format.")
    base = whole(p["fps"], 1, 120)
    fps = whole(fps, 1, 120)
    width, height = (whole(x, 16, 7680) // 2 * 2 for x in (width, height))
    output_w, output_h = width, height
    ratio = n(p["width"], 16, 7680) / n(p["height"], 16, 7680)
    width = max(2, min(width, round(height * ratio / 2) * 2))
    height = max(2, min(height, round(width / ratio / 2) * 2))
    order = {t: i for i, t in enumerate(p.get("tracks", []))}
    clips = sorted(
        (c for c in p["clips"] if not c.get("guide")), key=lambda c: (order.get(c["track"], c["track"]), c["start"])
    )
    if not clips:
        raise ValueError("Add a clip to the timeline first.")
    video = fmt in VIDEO
    inputs, filters, audio = [], [], []
    total = max((whole(c["start"], 0, 10**8) + whole(c["length"], 1, 10**8)) / base for c in clips)
    if video:
        filters.append(f"color=c=black:s={width}x{height}:r={fps}:d={total:.9f}[v0]")
    backdrop = "v0"
    caption_layers = {}
    input_index = 0
    for i, c in enumerate(clips):
        if c.get("kind") == "caption":
            if video:
                caption_layers[i] = subtitle_file(dict(p, clips=[c]), True)
                filters.append(f"[{backdrop}]ass=layer{i}.ass[layer{i}]")
                backdrop = f"layer{i}"
            continue
        stream = input_index
        input_index += 1
        asset = assets[c["asset"]]
        dur = c["length"] / base
        start = c["start"] / base
        first_frame = (c["start"] * fps + base - 1) // base
        past_last_frame = ((c["start"] + c["length"]) * fps + base - 1) // base
        rate = n(c["rate"], 0.0001, 10000)
        offset = n(c["offset"], 0, 10**8)
        volume = n(c["volume"], 0, 1)
        if asset["still"]:
            inputs += ["-loop", "1", "-framerate", str(fps)]
        elif offset:
            inputs += ["-ss", f"{offset:.9f}"]
        if asset["codec"] == "vp9" and asset["alpha"]:
            inputs += ["-c:v", "libvpx-vp9"]
        inputs += ["-t", f"{dur * rate:.9f}", "-i", asset["path"]]
        if asset["video"] and c["track"] >= 1 and video:
            size = n(c["scale"], 0.05, 2)
            sw, sh = max(2, round(width * size / 2) * 2), max(2, round(height * size / 2) * 2)
            x, y = n(c["x"], -1, 2), n(c["y"], -1, 2)
            effects = {"mono": "hue=s=0,", "mirror": "hflip,", "negative": "negate=components=r+g+b,"}
            angle = math.radians(n(c.get("rotation", 0), -360, 360))
            fx = effects.get(c.get("videoFx"), "")
            rotation = f"rotate={angle}:ow=rotw({angle}):oh=roth({angle}):c=black@0," if angle else ""
            filters += [
                f"[{stream}:v:0]setpts=(PTS-STARTPTS)/{rate:.9f},fps={fps}:round=near,"
                f"scale={sw}:{sh}:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1,"
                f"format=yuva420p,{fx}{rotation}tpad=stop_mode=clone:stop_duration={1 / fps:.9f},setpts=PTS+{first_frame}[clip{i}]",
                f"[{backdrop}][clip{i}]overlay=x={x}*W-w/2:y={y}*H-h/2:eof_action=pass:repeatlast=0:"
                f"enable='gte(n,{first_frame})*lt(n,{past_last_frame})'[v{i + 1}]",
            ]
            backdrop = f"v{i + 1}"
        if asset["audio"] and volume and c.get("kind") != "video":
            af = {"voice":"highpass=f=160,", "soft":"lowpass=f=2400,"}.get(c.get("audioFx"), "")
            filters.append(
                f"[{stream}:a:0]asetpts=PTS-STARTPTS,aresample=48000,{af}{atempo(rate)},volume={volume},"
                f"atrim=duration={dur:.9f},adelay={round(start * 48000)}S:all=1[a{i}]"
            )
            audio.append(f"[a{i}]")
    filters.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={total:.9f}[silence]")
    filters.append(
        f"[silence]{''.join(audio)}amix=inputs={1 + len(audio)}:normalize=0:duration=first[aout]"
    )
    dest = Path(dest).resolve()
    with tempfile.TemporaryDirectory(prefix=".nanocut-", dir=dest.parent) as tmp:
        tmp = Path(tmp)
        for i, content in caption_layers.items():
            (tmp / f"layer{i}.ass").write_text(content, encoding="utf-8")
        legacy = dict(p, clips=[c for c in clips if c.get("kind") != "caption"])
        if video and any(captions(legacy)):
            (tmp / "captions.ass").write_text(subtitle_file(legacy, True), encoding="utf-8")
            filters.append(f"[{backdrop}]ass=captions.ass[captioned]")
            backdrop = "captioned"
        if video and (width, height) != (output_w, output_h):
            filters.append(f"[{backdrop}]pad={output_w}:{output_h}:(ow-iw)/2:(oh-ih)/2[padded]")
            backdrop = "padded"
        (tmp / "edit.ffgraph").write_text(";\n".join(filters), encoding="utf-8")
        out = tmp / ("render." + fmt)
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-v",
            "error",
            "-nostdin",
            "-filter_complex_threads",
            "2",
            *inputs,
            "-/filter_complex",
            "edit.ffgraph",
        ]
        if video:
            cmd += ["-map", f"[{backdrop}]", "-pix_fmt", "yuv420p"]
        cmd += [
            "-map",
            "[aout]",
            *FORMATS[fmt],
            "-t",
            f"{total:.9f}",
            "-progress",
            "pipe:1",
            str(out),
        ]
        with (
            open(tmp / "errors", "w+b") as err,
            subprocess.Popen(cmd, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), cwd=tmp, stdout=subprocess.PIPE, stderr=err, text=True) as proc,
        ):
            for line in proc.stdout:
                if line.startswith("out_time_us="):
                    try:
                        notify(
                            "Rendering timeline", min(0.99, int(line.split("=")[1]) / 1e6 / total)
                        )
                    except ValueError:
                        pass
            if proc.wait():
                err.seek(0)
                raise ValueError(err.read().decode(errors="replace")[-1800:])
        os.replace(out, dest)
