import importlib.util
import json
import os
import subprocess
import sys
from urllib.request import Request, urlopen

VERSION = "1.1.0.1"
RELEASES = "https://github.com/Interprole/NanoCut/releases"


def ensure_package(module, requirement, notify):
    if importlib.util.find_spec(module) is None:
        pip_install([requirement], notify)


def pip_install(args, notify):
    notify("Preparing packages", None)
    proc = subprocess.run([sys.executable, "-m", "pip", "--disable-pip-version-check", "install", "--no-input", *args],
                          capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if proc.returncode:
        raise ValueError(proc.stderr.decode(errors="replace")[-1500:])


def install(component, notify):
    from .tasks import MODELS
    if component == "downloader":
        pip_install(["--upgrade", "yt-dlp[default]"], notify)
    elif component in MODELS:
        ensure_package("faster_whisper", "faster-whisper>=1.2.1,<2", notify)
        from faster_whisper.utils import download_model
        notify("Preparing Whisper " + component, None)
        try:
            download_model(component, local_files_only=True)
        except OSError:
            download_model(component)
    elif component == "foreground":
        ensure_package("rembg", "rembg[cpu]>=2.0.75,<3", notify)
        from rembg import new_session
        new_session("u2netp", providers=["CPUExecutionProvider"])
        if os.name == "nt":
            from pathlib import Path
            (Path(os.environ["LOCALAPPDATA"])/"NanoCutRuntime"/"foreground-ready").touch()
    else:
        raise ValueError("Unknown component.")
    return "Ready"


def latest():
    req = Request("https://api.github.com/repos/Interprole/NanoCut/releases/latest", headers={"User-Agent": "NanoCut/"+VERSION})
    with urlopen(req, timeout=6) as response:
        tag = json.load(response)["tag_name"].removeprefix("v")
    import re
    if not re.fullmatch(r"\d+(\.\d+){0,3}", tag):
        raise ValueError("Unrecognized release version.")
    def parts(v):
        return tuple((v.split(".") + ["0"]*4)[:4])
    return {"version": tag, "newer": tuple(map(int,parts(tag))) > tuple(map(int,parts(VERSION)))}
