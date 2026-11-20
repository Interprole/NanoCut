"""Launch NanoCut in a dedicated desktop window."""

import argparse
import multiprocessing
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from nanocut.server import HOME, Server


def browser_path():
    candidates = [
        shutil.which(n)
        for n in ("msedge", "google-chrome", "chromium", "chromium-browser", "chrome")
    ]
    for root in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        if os.getenv(root):
            candidates.extend(
                str(Path(os.environ[root]) / p)
                for p in (
                    "Microsoft/Edge/Application/msedge.exe",
                    "Google/Chrome/Application/chrome.exe",
                )
            )
    candidates.append("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    return next((p for p in candidates if p and Path(p).is_file()), None)


def main():
    ap = argparse.ArgumentParser(description="NanoCut video editor")
    ap.add_argument(
        "--serve", action="store_true", help="print the local editor URL and keep serving"
    )
    args = ap.parse_args()
    if not all(shutil.which(s) for s in ("ffmpeg", "ffprobe")):
        sys.exit("FFmpeg and ffprobe are required. Run Setup.cmd or see README.md.")
    server = Server()
    print("NanoCut desktop window:", server.url, flush=True)
    process = None
    if not args.serve:
        browser = browser_path()
        if browser:
            process = subprocess.Popen(
                [
                    browser,
                    "--app=" + server.url,
                    "--user-data-dir=" + str(HOME / "window-profile"),
                    "--window-size=1440,930",
                    "--lang=en-US",
                    "--no-first-run",
                    "--disable-sync",
                ]
            )
        else:
            webbrowser.open(server.url)
    if process:

        def monitor():
            time.sleep(2)
            if process.poll() is None:
                process.wait()
                server.shutdown()

        threading.Thread(target=monitor, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.workspace.cancel()
        server.server_close()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
