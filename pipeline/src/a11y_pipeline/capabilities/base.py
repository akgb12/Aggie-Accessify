from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from a11y_pipeline.ir.models import HistoryEntry, Patch


class FigureDescriptionInput(BaseModel):
    element_id: str
    subtype: str
    image_png: bytes
    source_code: str | None
    visible_labels: list[str]
    slide_title: str | None
    nearby_text: list[str]
    # Words drawn in the figure, used to check a description; never sent to the model
    rendered_text: list[str] = []
    # Set only when repairing: the earlier attempt and what was wrong with it
    previous_alt: str | None = None
    previous_extended: str | None = None
    problems: list[str] = []
    # Titles of nearby slides: context for a slide title or for what a figure teaches
    other_titles: list[str] = []
    # A transcription of the words drawn in the image, from the text inventory
    image_text: list[str] = []


class FigureDescriptionOutput(BaseModel):
    alt_text: str
    extended_description: str | None = None
    decorative: bool = False


class SlideTitleOutput(BaseModel):
    title: str


class QuoteResult(BaseModel):
    quote: str
    written: bool


class QuoteCheckOutput(BaseModel):
    results: list[QuoteResult]


class TextInventoryOutput(BaseModel):
    text: list[str]


@dataclass(frozen=True)
class CapabilityResult:
    patches: list[Patch]
    history: HistoryEntry | None


class FigureJudgeInput(BaseModel):
    element_id: str
    image_png: bytes
    alt_text: str
    extended_description: str | None = None
    slide_title: str | None = None


class FigureJudgeOutput(BaseModel):
    verdict: Literal["good", "needs_work", "bad"]
    # Details the description states that the image does not show
    invented: list[str] = []
    # Important things the image shows that the description leaves out
    missing: list[str] = []
