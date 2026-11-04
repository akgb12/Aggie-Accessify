import io
import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image

OCR_TIMEOUT_SECONDS = 60
# Small crops are enlarged before reading; Tesseract reads text best at about 30 pixels high
MIN_OCR_WIDTH = 1200
# Page segmentation mode 11: find as much scattered text as possible, as on a diagram
SPARSE_TEXT_MODE = "11"


def find_tesseract() -> str | None:
    # Tesseract is optional, like LibreOffice: found from TESSERACT_PATH or on PATH
    configured = os.environ.get("TESSERACT_PATH", "").strip()
    for candidate in (configured, shutil.which("tesseract") or ""):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def ocr_words(image_png: bytes) -> list[str] | None:
    # The words Tesseract reads in an image, in reading order; None when OCR is unavailable
    tesseract = find_tesseract()
    if tesseract is None:
        return None
    try:
        with Image.open(io.BytesIO(image_png)) as image:
            prepared = image.convert("RGB")
            if prepared.width < MIN_OCR_WIDTH:
                scale = MIN_OCR_WIDTH / max(prepared.width, 1)
                size = (MIN_OCR_WIDTH, max(1, int(prepared.height * scale)))
                prepared = prepared.resize(size, Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            prepared.save(buffer, format="PNG")
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
    try:
        completed = subprocess.run(
            [tesseract, "stdin", "stdout", "--psm", SPARSE_TEXT_MODE],
            input=buffer.getvalue(),
            capture_output=True,
            check=False,
            timeout=OCR_TIMEOUT_SECONDS,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if completed.returncode != 0:
        return None
    text = completed.stdout.decode("utf-8", errors="replace")
    return [word for word in text.split() if word.strip()]
