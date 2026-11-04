import io
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from a11y_pipeline.render import ocr
from a11y_pipeline.render.ocr import find_tesseract, ocr_words


def _png(text: str) -> bytes:
    image = Image.new("RGB", (420, 80), "white")
    ImageDraw.Draw(image).text((10, 20), text, fill="black", font_size=32)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_find_tesseract_honours_an_explicit_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = tmp_path / "tesseract"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setenv("TESSERACT_PATH", str(fake))
    assert find_tesseract() == str(fake)


def test_without_tesseract_ocr_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr, "find_tesseract", lambda: None)
    assert ocr_words(_png("then return node")) is None


@pytest.mark.skipif(find_tesseract() is None, reason="Tesseract is not installed")
def test_ocr_reads_the_words_in_a_picture() -> None:
    words = ocr_words(_png("then return node"))
    assert words is not None
    assert [word.lower() for word in words] == ["then", "return", "node"]
