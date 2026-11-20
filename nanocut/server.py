import base64
import shutil
import json
import mimetypes
import multiprocessing as mp
import os
import queue
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .media import FORMATS, subtitle_file
from .tasks import MODELS, prepare, worker

ROOT = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("NANOCUT_HOME", Path.home() / ".nanocut"))
MEDIA = "*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.mpg *.mpeg *.mts *.m2ts *.mp3 *.wav *.m4a *.aac *.ogg *.flac *.jpg *.jpeg *.png *.webp *.bmp"
STATIC = {"index.html", "style.css", "app.js", "timeline.js", "studio.js", "icon.svg"}


def atomic_json(path, data):
    path = Path(path)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, encoding="utf-8", delete=False) as f:
        tmp = Path(f.name)
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def picker(mode, title, types, ext=None, name=None):
    config = dict(mode=mode, title=title, filetypes=types)
    if ext:
        config.update(defaultextension="." + ext, initialfile=name or "Untitled." + ext)
    p = subprocess.run(
        [sys.executable, "-m", "nanocut.dialog"],
        input=json.dumps(config).encode(),
        stdout=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), stderr=subprocess.PIPE,
        cwd=ROOT,
    )
    if p.returncode:
        raise ValueError(
            "The native file picker could not open. Install Tk and run NanoCut from a desktop session."
        )
    return json.loads(p.stdout)


def public(asset):
    return {k: v for k, v in asset.items() if k not in {"path", "thumb", "preview", "wave"}}


class Workspace:
    def __init__(self):
        HOME.mkdir(parents=True, exist_ok=True)
        self.staging = HOME / "Projects" / secrets.token_hex(8)
        self.assets = {}
        self.project_path = None
        self.job = None
        self.lock = threading.RLock()
        self.ctx = mp.get_context("spawn")

    def begin(self, kind, data):
        if self.job and self.job["process"].is_alive():
            raise ValueError("Finish or cancel the current task first.")
        q = self.ctx.Queue()
        proc = self.ctx.Process(target=worker, args=(kind, data, q))
        proc.start()
        self.job = dict(
            process=proc, q=q, kind=kind, status="running", label="Starting", fraction=None
        )
        return {"started": True}

    def cancel(self):
        if self.job:
            proc = self.job["process"]
            if proc.is_alive():
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(proc.pid), "/T", "/F"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), capture_output=True
                    )
                else:
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        proc.terminate()
                proc.join(2)
            self.job["status"] = "cancelled"
        return True

    def poll(self):
        j = self.job
        if not j:
            return {"status": "idle"}
        if j["status"] == "running":
            while True:
                try:
                    kind, data = j["q"].get_nowait()
                except queue.Empty:
                    if not j["process"].is_alive() and j["status"] == "running":
                        j.update(status="error", result="The worker stopped unexpectedly.")
                    break
                if kind == "progress":
                    j["label"], j["fraction"] = data
                else:
                    if kind == "done" and j["kind"] in {"import", "cutout", "download", "narrate"}:
                        values = data if isinstance(data, list) else [data]
                        self.assets.update({a["id"]: a for a in values})
                        data = [public(a) for a in values]
                    j.update(status=kind, result=data)
                    break
        return {k: v for k, v in j.items() if k not in {"process", "q"}}

    def pack(self, p, folder):
        ids = list(dict.fromkeys(p["library"] + [c["asset"] for c in p["clips"]]))

        def reference(a):
            try:
                return os.path.relpath(a["path"], folder)
            except ValueError:
                return a["path"]

        return dict(version=1, project=p, media={i: reference(self.assets[i]) for i in ids})

    def load(self, path):
        path = Path(path)
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("version") != 1:
            raise ValueError("This project version is not supported.")
        updated = {}
        for ident, ref in doc["media"].items():
            src = (path.parent / ref).resolve()
            if not src.is_file():
                chosen = picker(
                    "open",
                    "Locate missing file · " + src.name,
                    [("Media", MEDIA), ("All files", "*")],
                )
                if not chosen:
                    raise ValueError("Open cancelled. The current project is still open.")
                src = Path(chosen)
            a = prepare(src)
            a["id"] = ident
            updated[ident] = a
        self.assets.update(updated)
        return {"project": doc["project"], "assets": [public(a) for a in updated.values()]}

    def dest(self, ext, name):
        p = picker("save", "Choose destination", [(ext.upper(), "*." + ext)], ext, name)
        if p and Path(p).suffix.lower() != "." + ext:
            raise ValueError("Use the selected file extension.")
        if p and any(Path(a["path"]).resolve() == Path(p).resolve() for a in self.assets.values()):
            raise ValueError("Choose a new filename to preserve your source media.")
        return p

    def media_dir(self):
        if self.project_path:
            path = Path(self.project_path)
            return path.with_name(path.stem + ".media")
        return self.staging

    def generated(self, name, ext):
        folder = self.media_dir()
        folder.mkdir(parents=True, exist_ok=True)
        return str(folder / (name + "-" + secrets.token_hex(4) + "." + ext))

    def call(self, op, d):
        if op == "install":
            return self.begin(op, {"component": d["component"]})
        if op in {"narrate", "translate"}:
            if not d["cues"] or d.get("provider") not in ({"local", "openai", "piper"} if op == "narrate" else {"local", "openai"}):
                raise ValueError("Select timed captions and a provider.")
            if op == "narrate":
                d["dest"] = self.generated("Narration", "wav")
            return self.begin(op, d)
        if op == "update":
            from .tools import latest
            return latest()
        if op == "graphic":
            data = base64.b64decode(d["png"], validate=True)
            if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > 8000000:
                raise ValueError("Invalid graphic.")
            dest = self.generated("Graphic", "png")
            Path(dest).write_bytes(data)
            return self.begin("import", {"paths": [dest]})
        if op == "sound":
            from .media import ff
            sounds = {"Beep": "sine=f=880:d=0.18", "Bass hit":"sine=f=90:d=0.4",
                      "Noise sweep":"anoisesrc=color=pink:duration=0.5:amplitude=0.3"}
            dest = self.generated("Sound", "wav")
            ff("-f", "lavfi", "-i", sounds[d["sound"]], "-af", "afade=t=out:st=0.05:d=0.32", dest)
            return self.begin("import", {"paths": [dest]})
        if op == "demo":
            from .demo import example

            assets, p = example()
            self.assets.update({a["id"]: a for a in assets})
            self.project_path = None
            return {"project": p, "assets": [public(a) for a in assets]}
        if op == "state":
            return {
                "models": MODELS,
                "recover": (HOME / "recovery.nano").exists(),
                "tiktok": bool(
                    os.getenv("TIKTOK_CLIENT_KEY") and os.getenv("TIKTOK_CLIENT_SECRET")
                ),
            }
        if op == "job":
            return self.poll()
        if op == "cancel":
            return self.cancel()
        if op == "new":
            self.staging = HOME / "Projects" / secrets.token_hex(8)
            self.project_path = None
            return True
        if op == "import":
            paths = picker("multi", "Import media", [("Media", MEDIA), ("All files", "*")])
            return self.begin("import", {"paths": paths}) if paths else None
        if op == "open" or op == "recover":
            path = (
                HOME / "recovery.nano"
                if op == "recover"
                else picker("open", "Open NanoCut project", [("NanoCut", "*.nano")])
            )
            if not path:
                return None
            result = self.load(path)
            self.project_path = None if op == "recover" else path
            return result
        if op in {"save", "autosave"}:
            path = self.project_path
            if op == "autosave":
                path = HOME / "recovery.nano"
            elif not path or d.get("as"):
                path = picker(
                    "save",
                    "Save project",
                    [("NanoCut", "*.nano")],
                    "nano",
                    d["project"]["name"] + ".nano",
                )
            if not path:
                return None
            if op == "save" and path != self.project_path:
                target = Path(path).with_name(Path(path).stem + ".media")
                for ident in d["project"]["library"]:
                    asset = self.assets[ident]
                    src = Path(asset["path"])
                    if src.parent == self.media_dir() and target != src.parent:
                        target.mkdir(parents=True, exist_ok=True)
                        dest = target / src.name
                        if dest.exists():
                            dest = target / (secrets.token_hex(4) + "-" + src.name)
                        shutil.copy2(src, dest)
                        asset["path"] = str(dest)
                        if asset["preview"] == str(src):
                            asset["preview"] = str(dest)
            atomic_json(path, self.pack(d["project"], Path(path).parent))
            if op == "save":
                self.project_path = path
            return str(path)
        if op == "srt":
            p = self.dest("srt", d["project"]["name"] + ".srt")
            if p:
                Path(p).write_text(subtitle_file(d["project"], False), encoding="utf-8")
            return p
        if op == "export":
            fmt = d["format"]
            if fmt not in FORMATS:
                raise ValueError("Invalid format.")
            dest = self.dest(fmt, d["project"]["name"] + "." + fmt)
            if not dest:
                return None
            return self.begin(op, dict(d, dest=dest, assets=self.assets))
        if op == "download":
            fmt = d["format"]
            if fmt not in {"mp3", "mp4"}:
                raise ValueError("Invalid download format.")
            dest = self.generated("Download", fmt)
            return self.begin(op, dict(d, dest=dest)) if dest else None
        if op in {"whisper", "cutout"}:
            a = self.assets[d["asset"]]
            if op == "whisper" and not a["audio"]:
                raise ValueError("Select a clip with audio.")
            if op == "cutout" and not a["video"]:
                raise ValueError("Select a visual clip.")
            if op == "cutout":
                ext = "png" if a["still"] else "webm"
                dest = self.generated("Foreground", ext)
                if not dest:
                    return None
                d["dest"] = dest
            return self.begin(op, dict(d, path=a["path"]))
        if op == "tiktok":
            path = picker(
                "open",
                "Choose the exported MP4 to send to your TikTok inbox",
                [("MP4 video", "*.mp4")],
            )
            return self.begin(op, {"path": path}) if path else None
        raise ValueError("Unknown command.")


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        self.workspace = Workspace()
        self.key = secrets.token_urlsafe(32)
        super().__init__(("127.0.0.1", 0), Handler)
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.url = self.origin + "/" + self.key + "/"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def route(self):
        path = urlsplit(self.path).path
        prefix = "/" + self.server.key + "/"
        if self.headers.get("Host") != self.server.origin.split("//")[1] or not path.startswith(
            prefix
        ):
            return None
        return path[len(prefix) :]

    def reply(self, data, status=200):
        content = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        route = self.route()
        if (
            not route
            or not route.startswith("api/")
            or self.headers.get("Origin") != self.server.origin
        ):
            return self.send_error(403)
        try:
            size = int(self.headers.get("Content-Length", 0))
            if not 0 <= size <= 24 * 1024 * 1024:
                raise ValueError("Project data is too large.")
            data = json.loads(self.rfile.read(size))
            from contextlib import nullcontext
            with (nullcontext() if route == "api/update" else self.server.workspace.lock):
                value = self.server.workspace.call(route[4:], data)
            self.reply({"value": value})
        except Exception as exc:
            self.reply({"error": str(exc)}, 400)

    def do_GET(self):
        route = self.route()
        if route is None:
            return self.send_error(404)
        route = route or "index.html"
        if route in STATIC:
            path = ROOT / "web" / route
        elif re.fullmatch(r"(media|thumb|wave)/[a-zA-Z0-9_-]+", route):
            kind, ident = route.split("/")
            a = self.server.workspace.assets.get(ident)
            if not a:
                return self.send_error(404)
            path = Path(a["preview" if kind == "media" else kind] or "")
        else:
            return self.send_error(404)
        try:
            with path.open("rb") as f:
                size = path.stat().st_size
                start, end = 0, size - 1
                ranges = self.headers.get("Range")
                if ranges:
                    match = re.fullmatch(r"bytes=(\d+)-(\d*)", ranges)
                    if not match:
                        return self.send_error(416)
                    start = int(match[1])
                    end = min(int(match[2]), end) if match[2] else end
                    if start > end:
                        return self.send_error(416)
                self.send_response(206 if ranges else 200)
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src https://www.youtube-nocookie.com https://www.tiktok.com; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
                )
                self.send_header(
                    "Content-Type", mimetypes.guess_type(str(path))[0] or "application/octet-stream"
                )
                self.send_header("Accept-Ranges", "bytes")
                if ranges:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(end - start + 1))
                self.end_headers()
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    block = f.read(min(65536, remaining))
                    if not block:
                        break
                    self.wfile.write(block)
                    remaining -= len(block)
        except (ConnectionError, OSError):
            return
