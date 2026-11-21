"""Timed captions, translation and speech synthesis for project audio tracks."""
import difflib
import json
import os
import re
import subprocess
import tempfile
import wave
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .media import atempo, ff, n, probe


def align_script(script, words):
    """Anchor supplied words to recognized speech, interpolating unmatched boundaries."""
    lines = [line.strip() for line in script.splitlines() if line.strip()]
    if len(lines) == 1:
        lines = re.split(r"(?<=[.!?。！？])\s+", lines[0])
    if not lines or not words:
        raise ValueError("No spoken words could be aligned with the script.")
    normalize = lambda word: re.sub(r"[^\w]", "", word.casefold())
    tokens, spans = [], []
    for line in lines:
        start = len(tokens)
        tokens.extend(normalize(w) for w in line.split())
        spans.append((start, len(tokens)))
    matches = difflib.SequenceMatcher(None, tokens, [normalize(w[0]) for w in words], autojunk=False)
    anchors = {}
    for i, j, count in matches.get_matching_blocks():
        anchors.update({i+k: words[j+k][1:] for k in range(count)})
    if len(anchors) < max(1, len(tokens) * 0.2):
        raise ValueError("Too few script words match the recording. Check the language and selected interval.")
    boundaries = {0: words[0][1], len(tokens): words[-1][2]}
    for i, (start, end) in anchors.items():
        boundaries[i+1] = end
    for i, (start, _) in anchors.items():
        boundaries[i] = start
    known = sorted(boundaries)
    for left, right in zip(known, known[1:]):
        for i in range(left+1, right):
            boundaries[i] = boundaries[left] + (boundaries[right]-boundaries[left])*(i-left)/(right-left)
    return [{"in": boundaries[a], "out": anchors[b-1][1] if b-1 in anchors else boundaries[b],
             "text": line} for line, (a, b) in zip(lines, spans)]


def openai(endpoint, data, key):
    key = key or os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("Enter an OpenAI API key or set OPENAI_API_KEY.")
    req = Request("https://api.openai.com/v1/" + endpoint, json.dumps(data).encode(),
                  {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=120) as response:
            return response.read()
    except HTTPError as exc:
        raise ValueError(f"OpenAI returned HTTP {exc.code}. Check your key, model and API billing.") from None


def translate(d, notify):
    source, target = d["source"].strip().lower(), d["target"].strip().lower()
    if not all(re.fullmatch("[a-z]{2,3}(-[a-z]+)?", code) for code in (source, target)):
        raise ValueError("Enter source and target language codes, such as en and ru.")
    if source == target:
        raise ValueError("Choose two different languages.")
    if d["provider"] == "local":
        from .translation import CaptionTranslator
        pair = CaptionTranslator(source, target, notify)
    cues = []
    for i, cue in enumerate(d["cues"]):
        notify(f"Translating caption {i+1} of {len(d['cues'])}", i/len(d["cues"]))
        if d["provider"] == "local":
            text = pair.translate(cue["text"])
        else:
            resp = openai("chat/completions", {"model": d.get("model") or "gpt-4o-mini",
                "messages": [{"role": "system", "content": f"Translate the subtitle from {source} to {target}. Output only the translation."},
                             {"role": "user", "content": cue["text"]}]}, d.get("key"))
            text = json.loads(resp)["choices"][0]["message"]["content"]
        cues.append(dict(cue, text=text.strip()))
    return cues


def local_voice(text, dest, voice):
    if os.name != "nt":
        import shutil
        exe = shutil.which("espeak-ng") or shutil.which("espeak")
        if not exe:
            raise ValueError("Install eSpeak NG for local speech on this platform.")
        args = [exe, "-w", str(dest), *(["-v", voice] if voice else []), "--stdin"]
        subprocess.run(args, input=text.encode(), check=True)
        return
    script = """$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Speech
$s=New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
if ($env:NANOCUT_VOICE) { $s.SelectVoice($env:NANOCUT_VOICE) }
$s.SetOutputToWaveFile($env:NANOCUT_WAV)
$s.Speak([IO.File]::ReadAllText($env:NANOCUT_TEXT))
} finally { $s.Dispose() }"""
    src = dest.with_suffix(".txt")
    src.write_text(text, encoding="utf-8")
    env = dict(os.environ, NANOCUT_TEXT=str(src), NANOCUT_WAV=str(dest), NANOCUT_VOICE=voice)
    proc = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                          env=env, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if proc.returncode:
        raise ValueError("Windows speech synthesis failed. Select an installed Windows desktop voice.")


PIPER_VOICES = {"en_US-lessac-medium", "ru_RU-irina-medium", "de_DE-thorsten-medium",
                "fr_FR-siwis-medium", "es_ES-davefx-medium"}


def piper_voice(name, notify):
    import sys
    from .tools import ensure_package
    if name not in PIPER_VOICES:
        raise ValueError("Unknown Piper voice.")
    ensure_package("piper", "piper-tts>=1.3,<2", notify)
    import onnxruntime
    onnxruntime.disable_telemetry_events()
    from piper import PiperVoice
    folder = Path.home() / ".nanocut" / "voices"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (name + ".onnx")
    config = folder / (name + ".onnx.json")
    if not path.exists() or not config.exists():
        notify("Downloading Piper voice " + name, None)
        with tempfile.TemporaryDirectory(dir=folder) as tmp:
            proc = subprocess.run([sys.executable, "-m", "piper.download_voices", name], cwd=tmp,
                                  capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if proc.returncode:
                raise ValueError("Could not download the selected Piper voice.")
            for file in (config, path):
                os.replace(Path(tmp) / file.name, file)
    return PiperVoice.load(str(path))


def narrate(d, notify):
    from .tasks import prepare
    dest = Path(d["dest"])
    piper = piper_voice(d["piperVoice"], notify) if d["provider"] == "piper" else None
    with tempfile.TemporaryDirectory(dir=dest.parent) as folder:
        root = Path(folder)
        # Place each cue on the sample grid, retaining silence and overlapping speech.
        import array
        duration = n(d["duration"], 0.001, 86400)
        out = root / "mix.wav"
        with out.open("w+b") as raw:
            samples = round(duration * 24000)
            raw.truncate(samples * 2)
            for i, cue in enumerate(d["cues"]):
                a, b = max(0, cue["in"]), min(cue["out"], duration)
                if b <= a or not cue["text"].strip():
                    continue
                notify(f"Voicing caption {i+1} of {len(d['cues'])}", i/len(d["cues"]))
                wav = root / "voice.wav"
                if piper:
                    with wave.open(str(wav), "wb") as stream:
                        piper.synthesize_wav(cue["text"], stream)
                elif d["provider"] == "local":
                    local_voice(cue["text"], wav, d.get("voice", ""))
                else:
                    wav.write_bytes(openai("audio/speech", {"model": d.get("model") or "gpt-4o-mini-tts",
                        "input": cue["text"], "voice": d.get("voice") or "alloy", "response_format":"wav"}, d.get("key")))
                rate = max(1, probe(wav)["duration"] / (b-a))
                pcm = ff("-i", wav, "-af", atempo(rate), "-t", b-a, "-ac", "1", "-ar", "24000", "-f", "s16le", "pipe:1")
                start = round(a*24000)*2
                pcm = pcm[:max(0, samples*2-start)]
                raw.seek(start)
                prev = array.array("h", raw.read(len(pcm)))
                new = array.array("h", pcm)
                raw.seek(start)
                raw.write(array.array("h", (max(-32768,min(32767,x+y)) for x,y in zip(prev,new))).tobytes())
            raw.seek(0)
            with wave.open(str(root/"ready.wav"), "wb") as w:
                w.setparams((1,2,24000,0,"NONE",""))
                while chunk := raw.read(1024*1024):
                    w.writeframesraw(chunk)
        os.replace(root/"ready.wav", dest)
    return prepare(dest, notify)
