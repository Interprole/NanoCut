"""Prepare the selected weights during Windows setup."""
import sys

if sys.argv[1] == "foreground":
    from rembg import new_session
    new_session("u2netp", providers=["CPUExecutionProvider"])
else:
    from faster_whisper.utils import download_model
    from huggingface_hub.errors import LocalEntryNotFoundError
    try:
        download_model(sys.argv[1], local_files_only=True)
    except (FileNotFoundError, LocalEntryNotFoundError):
        download_model(sys.argv[1])
