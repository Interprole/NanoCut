"""Personal developer-app OAuth and upload-to-inbox flow."""

import hashlib
import json
import os
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen


def api(endpoint, data, token=None):
    body = json.dumps(data).encode() if token else urlencode(data).encode()
    headers = {"Content-Type": "application/json" if token else "application/x-www-form-urlencoded"}
    if token:
        headers["Authorization"] = "Bearer " + token
    with urlopen(
        Request("https://open.tiktokapis.com/" + endpoint, body, headers), timeout=60
    ) as response:
        result = json.load(response)
    error = result.get("error")
    if isinstance(error, str) or isinstance(error, dict) and error.get("code") != "ok":
        raise ValueError(
            "TikTok declined the request: "
            + str(error.get("message") if isinstance(error, dict) else error)
        )
    return result


def send_draft(path, notify):
    key = os.getenv("TIKTOK_CLIENT_KEY")
    secret = os.getenv("TIKTOK_CLIENT_SECRET")
    if not key or not secret:
        raise ValueError(
            "Configure your approved TikTok developer app first. See TikTok setup in README.md."
        )
    port = int(os.getenv("TIKTOK_REDIRECT_PORT", "53682"))
    redirect = f"http://127.0.0.1:{port}/callback/"
    verifier, state = secrets.token_urlsafe(48), secrets.token_hex(24)
    result = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            u = urlsplit(self.path)
            q = parse_qs(u.query)
            if u.path != "/callback/" or not secrets.compare_digest(q.get("state", [""])[0], state):
                self.send_error(400)
                return
            result.update(q)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Return to NanoCut to see the upload status.")

    with HTTPServer(("127.0.0.1", port), Callback) as callback:
        callback.timeout = 1
        url = "https://www.tiktok.com/v2/auth/authorize/?" + urlencode(
            dict(
                client_key=key,
                scope="video.upload",
                response_type="code",
                redirect_uri=redirect,
                state=state,
                code_challenge_method="S256",
                code_challenge=hashlib.sha256(verifier.encode()).hexdigest(),
            )
        )
        notify("Authorize the draft upload in your browser", None)
        webbrowser.open(url)
        deadline = time.monotonic() + 240
        while not result and time.monotonic() < deadline:
            callback.handle_request()
    if not result.get("code"):
        raise ValueError("TikTok authorization was declined or timed out.")
    auth = api(
        "v2/oauth/token/",
        dict(
            client_key=key,
            client_secret=secret,
            code=result["code"][0],
            redirect_uri=redirect,
            grant_type="authorization_code",
            code_verifier=verifier,
        ),
    )
    token = auth["access_token"]
    size = Path(path).stat().st_size
    chunk = min(size, 16 * 1024 * 1024)
    count = max(1, size // chunk)
    upload = api(
        "v2/post/publish/inbox/video/init/",
        dict(
            source_info=dict(
                source="FILE_UPLOAD", video_size=size, chunk_size=chunk, total_chunk_count=count
            )
        ),
        token,
    )["data"]
    with open(path, "rb") as f:
        for i in range(count):
            pos = f.tell()
            buf = f.read(chunk if i < count - 1 else size - pos)
            headers = {
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes {pos}-{pos + len(buf) - 1}/{size}",
            }
            with urlopen(
                Request(upload["upload_url"], buf, headers, method="PUT"), timeout=120
            ) as r:
                r.read()
            notify("Sending draft to TikTok", f.tell() / size)
    for _ in range(30):
        status = api("v2/post/publish/status/fetch/", {"publish_id": upload["publish_id"]}, token)[
            "data"
        ]
        if status["status"] in {"SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"}:
            return "Draft delivered. Open your TikTok inbox to add a sound and publish."
        if status["status"] == "FAILED":
            raise ValueError(
                "TikTok processing failed: " + status.get("fail_reason", "unknown reason")
            )
        notify("TikTok is processing the upload", None)
        time.sleep(2)
    return "Upload transferred. TikTok is still processing it. Check your TikTok inbox."
