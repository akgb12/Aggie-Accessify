import json
from pathlib import Path

from a11y_pipeline.capabilities.base import FigureJudgeInput, FigureJudgeOutput
from a11y_pipeline.models.client import ModelClient, ModelMessage, ModelRequest

JUDGE_PROMPT_VERSION = "figure_judge_v1"
JUDGE_DEFAULT_MODEL = "claude-sonnet-5-5"


class FigureJudgeCapability:
    def __init__(
        self,
        client: ModelClient,
        model: str = JUDGE_DEFAULT_MODEL,
        max_tokens: int = 1000,
    ) -> None:
        # Store model settings and load the fixed rubric
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        path = Path(__file__).parent / "prompts" / f"{JUDGE_PROMPT_VERSION}.md"
        self.prompt = path.read_text(encoding="utf-8").strip()

    def build_request(self, judge_input: FigureJudgeInput) -> ModelRequest:
        # The judge sees the image and the description only, never the source or its labels
        context = {
            "slide_title": judge_input.slide_title,
            "alt_text": judge_input.alt_text,
            "extended_description": judge_input.extended_description,
        }
        text = "Judge this description of the figure.\n"
        text += json.dumps(context, ensure_ascii=False, sort_keys=True)
        return ModelRequest(
            model=self.model,
            system=self.prompt,
            messages=[ModelMessage(role="user", text=text, image_png=judge_input.image_png)],
            output_schema=FigureJudgeOutput,
            prompt_version=JUDGE_PROMPT_VERSION,
            element_id=judge_input.element_id,
            max_tokens=self.max_tokens,
        )

    def judge(self, judge_input: FigureJudgeInput) -> FigureJudgeOutput | None:
        # One verdict, or None when the model gives no valid answer twice
        request = self.build_request(judge_input)
        for _attempt in range(2):
            try:
                response = self.client.complete_structured(request)
                return FigureJudgeOutput.model_validate(response.output.model_dump(mode="python"))
            except (TypeError, ValueError):
                continue
        return None
