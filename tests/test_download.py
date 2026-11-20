"""Exercise the actual yt-dlp/FFmpeg transfer with a deterministic local media origin."""

import importlib.util
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from nanocut.media import ff, probe
from nanocut.server import Server
from nanocut.tasks import download, prepare


@unittest.skipUnless(
    importlib.util.find_spec("yt_dlp"), "Install the download dependency for the transfer test."
)
class DownloadTest(unittest.TestCase):
    def test_source_range_and_local_trim(self):
        from yt_dlp.extractor.youtube import YoutubeIE

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "fixture.mp4"
            ff(
                "-f",
                "lavfi",
                "-i",
                "testsrc2=s=128x72:r=24:d=3",
                "-f",
                "lavfi",
                "-i",
                "sine=440:duration=3",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                src,
            )
            origin = Server()
            asset = prepare(src)
            origin.workspace.assets[asset["id"]] = asset
            thread = threading.Thread(target=origin.serve_forever, daemon=True)
            thread.start()
            metadata = {
                "id": "BaW_jenozKc",
                "title": "Test source",
                "duration": 3,
                "formats": [
                    {
                        "format_id": "combined",
                        "ext": "mp4",
                        "vcodec": "h264",
                        "acodec": "aac",
                        "url": origin.url + "media/" + asset["id"],
                    }
                ],
            }
            try:
                with patch.object(YoutubeIE, "_real_extract", return_value=metadata):
                    for mode, ext in [("range", "mp4"), ("full", "mp3")]:
                        path = root / ("excerpt." + ext)
                        result = download(
                            {
                                "url": "https://www.youtube.com/watch?v=BaW_jenozKc",
                                "from": 1,
                                "to": 2,
                                "dest": str(path),
                                "transfer": mode,
                            },
                            lambda *args: None,
                        )
                        self.assertEqual(result["name"], path.name)
                        self.assertAlmostEqual(probe(path)["duration"], 1, delta=0.12)
            finally:
                origin.shutdown()
                origin.server_close()
