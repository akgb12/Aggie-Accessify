from dataclasses import dataclass
from pathlib import Path

from a11y_pipeline.adapters.pptx.colors import RunColour, deck_run_colours
from a11y_pipeline.evaluation.contrast import (
    NORMAL_TEXT_RATIO,
    RGB,
    contrast_ratio,
    drawn_as,
    hex_colour,
    readable_colour,
)
from a11y_pipeline.evaluation.page_contrast import RenderedText

# Decide which runs of text are too faint for their background and the colour each should take.
# The run's colour comes from the deck's XML. The background comes from the rendered slide
# where the run's words can be found there, which also covers text over pictures and shaded
# areas the XML cannot describe; elsewhere the XML's background is used.

EMU_PER_POINT = 12700
# Resolution for measuring colours; high enough that small text has solid glyph cores
CONTRAST_DPI = 110


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
    pages = RenderedText(rendered, work, CONTRAST_DPI)
    findings: list[ContrastFinding] = []
    for run in runs:
        background = run.background
        box = None if run.box is None else tuple(value / EMU_PER_POINT for value in run.box)
        measured = pages.measure(run.slide, box, run.text, run.colour) if box else None
        if measured is not None:
            text, measured_background = measured
            if not drawn_as(text, run.colour, measured_background):
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
