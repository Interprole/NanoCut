import io
import json
import zipfile
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nanocut.media import ff, probe
from nanocut.speech import align_script, narrate, translate


class SpeechTests(unittest.TestCase):
    def test_script_anchors_and_gaps(self):
        words = [("Hello", .2, .6), ("there", .65, .9), ("everyone", 1.5, 2.)]
        self.assertEqual(align_script("Hello there!\nEveryone.", words), [
            {"text": "Hello there!", "in": .2, "out": .9},
            {"text": "Everyone.", "in": 1.5, "out": 2.}])
        with self.assertRaises(ValueError):
            align_script("unrelated script", words)

    def test_narration_keeps_silence_and_length(self):
        real = os.name == "nt"
        def fake_local(text, dest, voice):
            ff("-f","lavfi","-i","sine=frequency=380:duration=1",dest)
        from nanocut.speech import local_voice
        with tempfile.TemporaryDirectory() as tmp, patch("nanocut.speech.local_voice", local_voice if real else fake_local):
            dest=Path(tmp)/"voice.wav"
            with patch("nanocut.tasks.CACHE", Path(tmp)/"cache"):
                narrate({"provider":"local","dest":str(dest),"duration":2,
                         "cues":[{"in":.5,"out":1.5,"text":"NanoCut sound check"}]},lambda *a:None)
            self.assertAlmostEqual(probe(dest)["duration"],2,places=2)
            raw=ff("-i",dest,"-f","s16le","pipe:1")
            self.assertFalse(any(raw[:24000]))
            self.assertTrue(any(raw[24000:72000]))
            self.assertFalse(any(raw[72000:]))

    def test_model_install_and_offline_reuse(self):
        from nanocut.translation import download_pair, find_model
        index = [{"from_code":"en", "to_code":"ru", "links":["https://example.test/model"]}]
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as weights:
            weights.writestr("pair/metadata.json", json.dumps(index[0]))
            weights.writestr("pair/model/model.bin", b"weights")
            weights.writestr("pair/sentencepiece.model", b"tokens")
            weights.writestr("pair/stanza/extra", b"unused sentence splitter")
        archive.seek(0)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "en-ru"
            with patch("nanocut.translation.urlopen", side_effect=[io.BytesIO(json.dumps(index).encode()),archive]):
                download_pair("en","ru",folder,lambda *a:None)
            self.assertEqual(find_model("en","ru",folder),folder)
            self.assertFalse((folder/"stanza").exists())
            self.assertEqual((folder/"model/model.bin").read_bytes(),b"weights")

    def test_api_translation_retains_times(self):
        cues=[{"text":"Hello", "in":.25, "out":1.5}]
        with patch("nanocut.speech.openai",return_value=b'{"choices":[{"message":{"content":"Hola"}}]}'):
            result=translate({"source":"en","target":"es","provider":"openai","cues":cues},lambda *a:None)
        self.assertEqual(result,[dict(cues[0],text="Hola")])
