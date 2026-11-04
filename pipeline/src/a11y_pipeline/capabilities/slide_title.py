import json
from pathlib import Path

from a11y_pipeline.capabilities.base import (
    CapabilityResult,
    FigureDescriptionInput,
    SlideTitleOutput,
)
from a11y_pipeline.ir.models import HistoryEntry, Patch
from a11y_pipeline.models.client import ModelClient, ModelMessage, ModelRequest

TITLE_PROMPT_VERSION = "slide_title_v1"
TITLE_DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_TITLE_WORDS = 12


class SlideTitleCapability:
    def __init__(
        self,
        client: ModelClient,
        model: str = TITLE_DEFAULT_MODEL,
        max_tokens: int = 200,
        prompt_path: Path | None = None,
    ) -> None:
        # Store model settings and load the fixed prompt
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        if prompt_path is None:
            prompt_path = Path(__file__).parent / "prompts" / f"{TITLE_PROMPT_VERSION}.md"
        self.prompt = prompt_path.read_text(encoding="utf-8").strip()

    def build_request(self, capability_input: FigureDescriptionInput) -> ModelRequest:
        # The slide image when there is one, with its words and the nearby slide titles
        context = {
            "slide_text": capability_input.nearby_text,
            "other_titles": capability_input.other_titles,
        }
        text = "Propose a title for this slide using the following context.\n"
        text += json.dumps(context, ensure_ascii=False, sort_keys=True)
        message = ModelMessage(
            role="user",
            text=text,
            image_png=capability_input.image_png or None,
        )
        return ModelRequest(
            model=self.model,
            system=self.prompt,
            messages=[message],
            output_schema=SlideTitleOutput,
            prompt_version=TITLE_PROMPT_VERSION,
            element_id=capability_input.element_id,
            max_tokens=self.max_tokens,
        )

    def run(
        self,
        capability_input: FigureDescriptionInput,
        run_id: str,
        round_number: int = 0,
    ) -> CapabilityResult:
        # Propose a title, with one retry for malformed or unusable output
        request = self.build_request(capability_input)
        input_tokens = 0
        output_tokens = 0
        cost_usd = 0.0
        for _attempt in range(2):
            try:
                response = self.client.complete_structured(request)
                input_tokens += response.input_tokens
                output_tokens += response.output_tokens
                cost_usd += response.cost_usd
                output = SlideTitleOutput.model_validate(response.output.model_dump(mode="python"))
            except (TypeError, ValueError):
                continue
            title = clean_title(output.title)
            if not title:
                continue
            history = HistoryEntry(
                run_id=run_id,
                round=round_number,
                change="Proposed slide title",
                by="model",
                model=self.model,
                prompt_version=TITLE_PROMPT_VERSION,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
            )
            patches = [
                Patch(
                    element_id=capability_input.element_id,
                    path=path,
                    value=value,
                    by="model",
                    round=round_number,
                    note="Proposed slide title",
                )
                for path, value in (
                    ("content.text", title),
                    ("accessibility.status", "model_generated"),
                )
            ]
            return CapabilityResult(patches=patches, history=history)
        failed = Patch(
            element_id=capability_input.element_id,
            path="accessibility.status",
            value="failed",
            by="model",
            round=round_number,
            note="Slide title proposal failed twice",
        )
        return CapabilityResult(patches=[failed], history=None)


def clean_title(value: str) -> str:
    # One line, no trailing period, and short enough to be a title
    title = " ".join(value.split()).strip().rstrip(".").strip()
    if not title or len(title.split()) > MAX_TITLE_WORDS:
        return ""
    return title
