from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from a11y_pipeline.evaluation.contrast import (
    GLYPH_CORE_SHARE,
    MIN_TEXT_DISTANCE,
    RGB,
    colours_around_word,
    contrast_ratio,
    required_ratio,
)
from a11y_pipeline.evaluation.hidden_labels import HiddenLabelError, extract_word_boxes
from a11y_pipeline.render.pages import RenderError, page_size_points, render_pages

# Measure every word drawn on a PDF's pages against what is behind it, for documents whose
# colours are only known once they are drawn, such as compiled LaTeX.

# Small text needs this resolution for its thin strokes to show their real colour
PAGE_DPI = 200
# A word box is about this much taller than the font size
BOX_TO_FONT = 1.2


@dataclass(frozen=True)
class FaintWord:
    page: int
    text: str
    ratio: float
    required: float
    colour: RGB
    background: RGB


def faint_words(pdf: Path, work: Path) -> list[FaintWord]:
    try:
        images = render_pages(pdf, work, dpi=PAGE_DPI)
        sizes = page_size_points(pdf)
    except (OSError, RenderError, ValueError):
        return []
    found: list[FaintWord] = []
    for number, path in enumerate(images, start=1):
        try:
            words = extract_word_boxes(pdf, number)
        except (HiddenLabelError, OSError, ValueError):
            continue
        width = sizes[number - 1][0]
        with Image.open(path) as image:
            scale = image.width / width
            for word in words:
                left, top, right, bottom = word.bbox
                crop = image.crop(
                    (
                        int(left * scale),
                        int(top * scale),
                        int(right * scale) + 1,
                        int(bottom * scale) + 1,
                    )
                )
                measured = word_colours(crop)
                if measured is None:
                    continue
                colour, background = measured
                ratio = contrast_ratio(colour, background)
                needed = required_ratio((bottom - top) / BOX_TO_FONT)
                if ratio < needed:
                    found.append(FaintWord(number, word.text, ratio, needed, colour, background))
    return found


def word_colours(image: Image.Image) -> tuple[RGB, RGB] | None:
    # The colours of a word whose colour is not known in advance: first a guess at the text
    # from the pixels furthest from the most common colour, then the exact measurement
    rgb = image.convert("RGB")
    pixels = list(rgb.get_flattened_data())
    if len(pixels) < 20:
        return None
    coarse = Counter((red // 16, green // 16, blue // 16) for red, green, blue in pixels)
    bucket = coarse.most_common(1)[0][0]
    background = [
        pixel for pixel in pixels if (pixel[0] // 16, pixel[1] // 16, pixel[2] // 16) == bucket
    ]
    middle = background[len(background) // 2]
    ink = sorted(
        (
            (distance, pixel)
            for pixel in pixels
            if (distance := sum((a - b) ** 2 for a, b in zip(pixel, middle, strict=True)) ** 0.5)
            >= MIN_TEXT_DISTANCE
        ),
        reverse=True,
    )
    if len(ink) < 3:
        return None
    core = [pixel for _, pixel in ink[: max(3, int(len(ink) * GLYPH_CORE_SHARE))]]
    guess = tuple(sorted(pixel[axis] for pixel in core)[len(core) // 2] for axis in range(3))
    return colours_around_word(rgb, guess)  # type: ignore[arg-type]
