import re
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
from a11y_pipeline.evaluation.hidden_labels import HiddenLabelError, WordBox, extract_word_boxes
from a11y_pipeline.render.pages import RenderError, page_size_points, render_pages

# Measure every word drawn on a PDF's pages against what is behind it, for documents whose
# colours are only known once they are drawn, such as compiled LaTeX.

# Small text needs this resolution for its thin strokes to show their real colour
PAGE_DPI = 200
# A word box is about this much taller than the font size
BOX_TO_FONT = 1.2
# Two measurements this close are the same colour; anti-aliasing and rendering noise stay
# well inside it
SAME_COLOUR = 48
# Words found this far outside a box still belong to it
BOX_SLACK_POINTS = 2.0


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


class RenderedText:
    # Page images and word positions of a rendered document, loaded once per page, for
    # measuring text whose colour is known but whose background may not be
    def __init__(self, rendered: Path | None, work: Path, dpi: int = PAGE_DPI) -> None:
        self.rendered = rendered
        self.images: list[Path] = []
        self.sizes: list[tuple[float, float]] = []
        self.words: dict[int, list[WordBox]] = {}
        if rendered is None:
            return
        try:
            self.images = render_pages(rendered, work, dpi=dpi)
            self.sizes = page_size_points(rendered)
        except (OSError, RenderError, ValueError):
            self.images = []

    def measure(
        self,
        page: int,
        box: tuple[float, ...] | None,
        text: str,
        colour: RGB,
    ) -> tuple[RGB, RGB] | None:
        # The text and background colours drawn where the text's words are, inside a box in
        # points from the page's top-left corner; None when the words cannot be found or
        # their backgrounds disagree
        if not self.images or not 1 <= page <= len(self.images):
            return None
        boxes = self._word_boxes(page, box, text)
        if not boxes:
            return None
        width = self.sizes[page - 1][0]
        measured: list[tuple[RGB, RGB]] = []
        with Image.open(self.images[page - 1]) as image:
            scale = image.width / width
            for left, top, right, bottom in boxes:
                crop = image.crop(
                    (
                        int(left * scale),
                        int(top * scale),
                        int(right * scale) + 1,
                        int(bottom * scale) + 1,
                    )
                )
                colours = colours_around_word(crop, colour)
                if colours is not None:
                    measured.append(colours)
        if not measured:
            return None
        backgrounds = [background for _, background in measured]
        first = backgrounds[0]
        if any(_distance(first, other) > SAME_COLOUR for other in backgrounds[1:]):
            return None
        closest = min(measured, key=lambda pair: _distance(pair[0], colour))
        return closest[0], _middle(backgrounds)

    def _word_boxes(
        self, page: int, box: tuple[float, ...] | None, text: str
    ) -> list[tuple[float, float, float, float]]:
        # Boxes of the drawn words that spell the text, inside the box when there is one
        if page not in self.words:
            try:
                self.words[page] = extract_word_boxes(self.rendered, page)  # type: ignore[arg-type]
            except (HiddenLabelError, OSError, ValueError):
                self.words[page] = []
        wanted = set(_tokens(text))
        if not wanted:
            return []
        slack = BOX_SLACK_POINTS
        found: list[tuple[float, float, float, float]] = []
        for word in self.words[page]:
            if box is not None:
                x_mid = (word.bbox[0] + word.bbox[2]) / 2
                y_mid = (word.bbox[1] + word.bbox[3]) / 2
                left, top, right, bottom = box
                inside = (
                    left - slack <= x_mid <= right + slack
                    and top - slack <= y_mid <= bottom + slack
                )
                if not inside:
                    continue
            if set(_tokens(word.text)) & wanted:
                found.append(word.bbox)
        return found


def _tokens(text: str) -> list[str]:
    return [token for token in re.split(r"\W+", text.casefold()) if token]


def _distance(first: RGB, second: RGB) -> float:
    return sum((a - b) ** 2 for a, b in zip(first, second, strict=True)) ** 0.5


def _middle(colours: list[RGB]) -> RGB:
    middle = len(colours) // 2
    return tuple(sorted(colour[axis] for colour in colours)[middle] for axis in range(3))  # type: ignore[return-value]
