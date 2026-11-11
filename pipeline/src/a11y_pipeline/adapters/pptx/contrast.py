import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from a11y_pipeline.adapters.pptx.colors import RunColour, deck_run_colours
from a11y_pipeline.evaluation.contrast import (
    NORMAL_TEXT_RATIO,
    RGB,
    colours_around_word,
    contrast_ratio,
    hex_colour,
    readable_colour,
)
from a11y_pipeline.evaluation.hidden_labels import HiddenLabelError, WordBox, extract_word_boxes
from a11y_pipeline.render.pages import RenderError, page_size_points, render_pages

# Decide which runs of text are too faint for their background and the colour each should take.
# The run's colour comes from the deck's XML. The background comes from the rendered slide
# where the run's words can be found there, which also covers text over pictures and shaded
# areas the XML cannot describe; elsewhere the XML's background is used.

EMU_PER_POINT = 12700
# Resolution for measuring colours; high enough that small text has solid glyph cores
CONTRAST_DPI = 110
# Two measurements this close are the same colour; anti-aliasing and JPEG-like rendering
# noise stay well inside it
SAME_COLOUR = 48
# The rendered text must be about the colour the XML says, or the XML was misread
TEXT_COLOUR_TOLERANCE = 80
# Words found this far outside the shape's box still belong to it
BOX_SLACK_POINTS = 2.0


@dataclass(frozen=True)
class ContrastFinding:
    run: RunColour
    background: RGB
    ratio: float
    # The new colour, or None when no colour of the same hue can pass
    fixed: RGB | None

    def record(self) -> dict[str, object]:
        # What the writer needs to recolour the run, and what the report shows
        record: dict[str, object] = {
            "part": self.run.part,
            "shape_id": self.run.shape_id,
            "top_shape_id": self.run.top_shape_id,
            "run": self.run.run,
            "text": self.run.text,
            "before": hex_colour(self.run.colour),
            "background": hex_colour(self.background),
            "ratio_before": round(self.ratio, 2),
            "required": self.run.required,
        }
        if self.fixed is not None:
            record["after"] = hex_colour(self.fixed)
            record["ratio_after"] = round(contrast_ratio(self.fixed, self.background), 2)
        return record


def contrast_findings(deck: Path, rendered: Path | None, work: Path) -> list[ContrastFinding]:
    # Every run that fails, with the colour that fixes it
    runs = deck_run_colours(deck)
    pages = _RenderedPages(rendered, work)
    findings: list[ContrastFinding] = []
    for run in runs:
        background = run.background
        measured = pages.measure(run)
        if measured is not None:
            text, measured_background = measured
            if _distance(text, run.colour) > TEXT_COLOUR_TOLERANCE:
                # The slide shows another colour than the XML reading gives, so this run is
                # left alone rather than recoloured on a guess
                continue
            background = measured_background
        if background is None:
            continue
        ratio = contrast_ratio(run.colour, background)
        if ratio >= run.required:
            continue
        # Fixed text meets the normal-text minimum whatever its size: checkers judge size in
        # different ways, and a size inherited through the theme is easy to misread
        fixed = (
            None if run.hyperlink else readable_colour(run.colour, background, NORMAL_TEXT_RATIO)
        )
        findings.append(ContrastFinding(run, background, ratio, fixed))
    return findings


class _RenderedPages:
    # Slide images and word positions, loaded once per slide
    def __init__(self, rendered: Path | None, work: Path) -> None:
        self.rendered = rendered
        self.images: list[Path] = []
        self.sizes: list[tuple[float, float]] = []
        self.words: dict[int, list[WordBox]] = {}
        if rendered is None:
            return
        try:
            self.images = render_pages(rendered, work, dpi=CONTRAST_DPI)
            self.sizes = page_size_points(rendered)
        except (OSError, RenderError, ValueError):
            self.images = []

    def measure(self, run: RunColour) -> tuple[RGB, RGB] | None:
        # The text and background colours drawn where the run's words are; None when the
        # words cannot be found or their backgrounds disagree
        if not self.images or run.box is None or run.slide > len(self.images):
            return None
        boxes = self._word_boxes(run)
        if not boxes:
            return None
        width, _ = self.sizes[run.slide - 1]
        measured: list[tuple[RGB, RGB]] = []
        with Image.open(self.images[run.slide - 1]) as image:
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
                colours = colours_around_word(crop, run.colour)
                if colours is not None:
                    measured.append(colours)
        if not measured:
            return None
        backgrounds = [background for _, background in measured]
        first = backgrounds[0]
        if any(_distance(first, other) > SAME_COLOUR for other in backgrounds[1:]):
            return None
        texts = sorted(measured, key=lambda pair: _distance(pair[0], run.colour))
        return texts[0][0], _middle(backgrounds)

    def _word_boxes(self, run: RunColour) -> list[tuple[float, float, float, float]]:
        # Boxes, in points from the top-left, of the drawn words that spell the run, inside
        # the shape that holds it
        if run.slide not in self.words:
            try:
                self.words[run.slide] = extract_word_boxes(self.rendered, run.slide)  # type: ignore[arg-type]
            except (HiddenLabelError, OSError, ValueError):
                self.words[run.slide] = []
        wanted = {token for token in _tokens(run.text)}
        if not wanted or run.box is None:
            return []
        left, top, right, bottom = (value / EMU_PER_POINT for value in run.box)
        slack = BOX_SLACK_POINTS
        found: list[tuple[float, float, float, float]] = []
        for word in self.words[run.slide]:
            x_mid = (word.bbox[0] + word.bbox[2]) / 2
            y_mid = (word.bbox[1] + word.bbox[3]) / 2
            if not (
                left - slack <= x_mid <= right + slack and top - slack <= y_mid <= bottom + slack
            ):
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
