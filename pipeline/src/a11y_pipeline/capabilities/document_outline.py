import json
from pathlib import Path
from typing import Any

from a11y_pipeline.capabilities.base import (
    CapabilityResult,
    DocumentOutlineOutput,
    FigureDescriptionInput,
)
from a11y_pipeline.ir.models import HistoryEntry, Patch
from a11y_pipeline.models.client import ModelClient, ModelMessage, ModelRequest

OUTLINE_PROMPT_VERSION = "document_outline_v2"
OUTLINE_DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_LEVEL = 6
MAX_TITLE_WORDS = 20


class DocumentOutlineCapability:
    # One text-only step per Word document: which bold or large lines are headings and at what
    # level, which words wrongly marked as another language are English, and a title
    def __init__(
        self,
        client: ModelClient,
        model: str = OUTLINE_DEFAULT_MODEL,
        max_tokens: int = 2000,
        prompt_path: Path | None = None,
    ) -> None:
        self.client = client
        self.model = model
        self.max_tokens = max(max_tokens, 2000)
        if prompt_path is None:
            prompt_path = Path(__file__).parent / "prompts" / f"{OUTLINE_PROMPT_VERSION}.md"
        self.prompt = prompt_path.read_text(encoding="utf-8").strip()

    def build_request(self, capability_input: FigureDescriptionInput) -> ModelRequest:
        outline = capability_input.outline
        context = {
            "lines": outline.get("lines", []),
            "opening_lines": capability_input.nearby_text,
            "foreign_runs": outline.get("foreign_runs", []),
            "needs_title": outline.get("needs_title", False),
            "document_language": outline.get("language", ""),
        }
        text = "Decide this document's outline using the following context.\n"
        text += json.dumps(context, ensure_ascii=False, sort_keys=True)
        return ModelRequest(
            model=self.model,
            system=self.prompt,
            messages=[ModelMessage(role="user", text=text)],
            output_schema=DocumentOutlineOutput,
            prompt_version=OUTLINE_PROMPT_VERSION,
            element_id=capability_input.element_id,
            max_tokens=self.max_tokens,
        )

    def run(
        self,
        capability_input: FigureDescriptionInput,
        run_id: str,
        round_number: int = 0,
    ) -> CapabilityResult:
        request = self.build_request(capability_input)
        input_tokens = output_tokens = 0
        cost_usd = 0.0
        for _attempt in range(2):
            try:
                response = self.client.complete_structured(request)
                input_tokens += response.input_tokens
                output_tokens += response.output_tokens
                cost_usd += response.cost_usd
                output = DocumentOutlineOutput.model_validate(
                    response.output.model_dump(mode="python")
                )
            except (TypeError, ValueError):
                continue
            history = HistoryEntry(
                run_id=run_id,
                round=round_number,
                change="Decided headings, languages and title",
                by="model",
                model=self.model,
                prompt_version=OUTLINE_PROMPT_VERSION,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
            )
            patches = outline_patches(capability_input, output, round_number)
            return CapabilityResult(patches=patches, history=history)
        failed = Patch(
            element_id=capability_input.element_id,
            path="accessibility.status",
            value="failed",
            by="model",
            round=round_number,
            note="Document outline failed twice",
        )
        return CapabilityResult(patches=[failed], history=None)


def outline_patches(
    capability_input: FigureDescriptionInput, output: DocumentOutlineOutput, round_number: int
) -> list[Patch]:
    # Turn the decision into patches, keeping only what the input offered and never letting a
    # new heading skip a level below the heading before it
    outline = capability_input.outline
    lines: list[dict[str, Any]] = list(outline.get("lines", []))
    chosen = {heading.id: heading.level for heading in output.headings}
    patches: list[Patch] = []

    def patch(element_id: str, path: str, value: Any, note: str) -> None:
        patches.append(
            Patch(
                element_id=element_id,
                path=path,
                value=value,
                by="model",
                round=round_number,
                note=note,
            )
        )

    previous = 0
    for line in lines:
        if line.get("level") is not None:
            previous = int(line["level"])
            continue
        level = max(0, min(MAX_LEVEL, int(chosen.get(line["id"], 0))))
        if level:
            level = min(level, previous + 1)
            previous = level
        patch(line["id"], "attrs.outline_level", level, "Heading level decided")
        if level:
            patch(line["id"], "accessibility.role", f"H{level}", "Heading level decided")
    offered = {int(run["run"]) for run in outline.get("foreign_runs", [])}
    english = sorted(offered & {int(index) for index in output.english_runs})
    element_id = capability_input.element_id
    patch(element_id, "attrs.english_runs", english, "Language marks to correct")
    if outline.get("needs_title"):
        title = " ".join(output.title.split()).rstrip(".")
        if title and len(title.split()) <= MAX_TITLE_WORDS:
            patch(element_id, "content.text", title, "Proposed document title")
    patch(element_id, "accessibility.status", "model_generated", "Outline decided")
    return patches
