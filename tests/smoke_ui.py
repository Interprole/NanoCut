"""Optional headless desktop UI test. Run from the repository root."""

import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from playwright.sync_api import expect, sync_playwright

    from nanocut import server
    from nanocut.media import probe

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        with patch.object(server, "HOME", root):
            app = server.Server()
        thread = threading.Thread(target=app.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as pw, patch.object(server, "HOME", root):
                browser = pw.chromium.launch(
                    executable_path=os.getenv("NANOCUT_TEST_BROWSER") or shutil.which("chromium"),
                    args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"],
                )
                page = browser.new_page(
                    viewport={"width": 1360, "height": 820}, accept_downloads=True
                )
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(app.url)
                page.get_by_role("button", name="Try the example project").click()
                page.wait_for_selector(".block.active")
                assert page.locator(".block").count() == 3
                page.get_by_role("button", name="Next frame", exact=True).click()
                assert page.locator("#timecode").inner_text() == "00:00:00:01"
                page.locator("#split").click()
                assert page.locator(".block").count() == 4
                page.locator("#undo").click()
                assert page.locator(".block").count() == 3
                page.locator("#redo").click()
                assert page.locator(".block").count() == 4
                page.get_by_label("Clip speed", exact=True).fill("2")
                page.get_by_label("Clip speed", exact=True).press("Enter")
                page.locator("#play").click()
                expect(page.locator("#timecode")).not_to_have_text("00:00:00:01")
                page.locator("#play").click()
                page.locator("#zoom").fill("94")
                assert "1 tick" in page.locator("#grid-status").inner_text()
                page.locator("#fit").click()
                page.get_by_role("button", name="Edit captions", exact=True).click()
                page.locator("textarea").fill("0.1 | 1.0 | NanoCut test")
                page.locator("#submit").click()
                page.locator("#tiktok").click()
                page.locator("#submit").click()
                assert page.locator("#modal").is_visible()
                assert page.locator("#dialog-title").inner_text() == "Import TikTok guide audio"
                page.locator("#modal-cancel").click()
                page.locator("#project-menu").click()
                with patch.object(server, "picker", return_value=str(root / "session.nano")):
                    page.get_by_role("button", name="Save project", exact=False).click()
                    expect(page.locator("#status")).to_contain_text("Saved")
                assert (root / "session.nano").is_file()
                with patch.object(server, "picker", return_value=str(root / "test.mp4")):
                    page.locator("#export").click()
                    page.locator("[name=size]").select_option("854x480")
                    page.locator("#submit").click()
                    expect(page.locator("#status")).to_contain_text("Exported", timeout=120000)
                info = probe(root / "test.mp4")
                assert info["width"] == 854 and info["height"] == 480 and info["audio"]
                assert not errors, errors
                if os.getenv("NANOCUT_SCREENSHOT"):
                    page.screenshot(path=os.environ["NANOCUT_SCREENSHOT"])
                browser.close()
                print(
                    "Desktop UI, frame step, split, undo/redo, retime, playback, frame grid, captions, TikTok guide, project save and MP4 export passed."
                )
        finally:
            app.shutdown()
            app.workspace.cancel()
            app.server_close()


if __name__ == "__main__":
    main()
