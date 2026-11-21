"""Run Argos translation weights directly on timed subtitle text."""
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

from .tools import ensure_package

INDEX = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"


def find_model(source, target, folder):
    if (folder / "model" / "model.bin").is_file():
        return folder
    data = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    for metadata in (data / "argos-translate" / "packages").glob("*/metadata.json"):
        info = json.loads(metadata.read_text(encoding="utf-8"))
        candidate = metadata.parent
        if (info.get("from_code"), info.get("to_code")) == (source, target) and (candidate / "model/model.bin").is_file():
            return candidate


def download_pair(source, target, folder, notify):
    notify(f"Downloading local translation model · {source} → {target}", None)
    with urlopen(Request(INDEX, headers={"User-Agent": "NanoCut"}), timeout=30) as reply:
        packages = json.load(reply)
    package = next((p for p in packages if (p.get("from_code"), p.get("to_code")) == (source, target)), None)
    if not package:
        raise ValueError("No direct local model for this language pair. Choose another pair or the API.")
    url = next((url for url in package["links"] if url.startswith("https://")), None)
    if not url:
        raise ValueError("No HTTPS download for this language model.")
    folder.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=folder.parent) as temp:
        temp = Path(temp)
        archive = temp / "package.zip"
        with urlopen(Request(url, headers={"User-Agent": "NanoCut"}), timeout=120) as response, archive.open("wb") as out:
            shutil.copyfileobj(response, out)
        with zipfile.ZipFile(archive) as z:
            meta = next(n for n in z.namelist() if n.count("/") == 1 and n.endswith("/metadata.json"))
            prefix = meta.rsplit("/", 1)[0] + "/"
            files = {"metadata.json", "sentencepiece.model", "bpe.model"}
            extracted = temp / "ready"
            for name in z.namelist():
                if not name.startswith(prefix):
                    continue
                rel = name[len(prefix):]
                if rel not in files and not (rel.startswith("model/") and rel.count("/") == 1):
                    continue
                if not rel or name.endswith("/") or any(x in rel for x in ("..", "\\", ":")):
                    continue
                dest = extracted / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                with z.open(name) as src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out)
        if not (extracted / "model/model.bin").is_file():
            raise ValueError("Incomplete language model.")
        if not folder.exists():
            extracted.rename(folder)
    return folder


class CaptionTranslator:
    def __init__(self, source, target, notify):
        folder = Path.home() / ".nanocut" / "translation" / f"{source}-{target}"
        model = find_model(source, target, folder) or download_pair(source, target, folder, notify)
        ensure_package("ctranslate2", "ctranslate2>=4,<5", notify)
        import ctranslate2

        self.engine = ctranslate2.Translator(str(model / "model"), device="cpu", compute_type="int8",
                                            intra_threads=min(8, os.cpu_count() or 1))
        info = json.loads((model / "metadata.json").read_text(encoding="utf-8"))
        self.prefix = info.get("target_prefix")
        if (model / "sentencepiece.model").is_file():
            ensure_package("sentencepiece", "sentencepiece>=0.2,<1", notify)
            import sentencepiece as sp

            tokenizer = sp.SentencePieceProcessor(model_file=str(model / "sentencepiece.model"))
            self.encode = lambda text: tokenizer.encode(text, out_type=str)
            self.decode = tokenizer.decode_pieces
        elif (model / "bpe.model").is_file():
            ensure_package("sacremoses", "sacremoses", notify)
            ensure_package("subword_nmt", "subword-nmt", notify)
            from sacremoses import MosesTokenizer, MosesPunctNormalizer, MosesDetokenizer
            from subword_nmt.apply_bpe import BPE

            with (model / "bpe.model").open(encoding="utf-8") as f:
                bpe = BPE(f)
            normalizer, tokenizer = MosesPunctNormalizer(lang=source), MosesTokenizer(lang=source)
            detokenizer = MosesDetokenizer(lang=target)
            self.encode = lambda text: bpe.segment_tokens(tokenizer.tokenize(normalizer.normalize(text)))
            self.decode = lambda tokens: detokenizer.detokenize(" ".join(tokens).replace("@@ ", "").split())
        else:
            raise ValueError("This local model has no supported tokenizer.")

    def translate(self, text):
        tokens = self.encode(text)
        chunks = [tokens[start:start+250] for start in range(0, len(tokens), 250)]
        prefix = [[self.prefix]] * len(chunks) if self.prefix else None
        results = self.engine.translate_batch(chunks, target_prefix=prefix, beam_size=4)
        lines = []
        for result in results:
            words = result.hypotheses[0]
            if self.prefix and words[:1] == [self.prefix]:
                words = words[1:]
            lines.append(self.decode(words))
        return " ".join(lines).strip()
