from dataclasses import dataclass

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


class FigureDescriptionOutput(BaseModel):
    alt_text: str
    extended_description: str | None = None
    decorative: bool = False


@dataclass(frozen=True)
class CapabilityResult:
    patches: list[Patch]
    history: HistoryEntry | None
