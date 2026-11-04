import json
from pathlib import Path

from a11y_pipeline.capabilities.base import QuoteCheckOutput
from a11y_pipeline.models.client import ModelClient, ModelMessage, ModelRequest

QUOTE_PROMPT_VERSION = "quote_check_v1"
QUOTE_DEFAULT_MODEL = "claude-sonnet-5-5"


class QuoteCheckCapability:
    # A narrow second look: are these quoted words really written in the figure? Used only for
    # quotes the deterministic checks could not find, such as text inside a screenshot.
    def __init__(
        self,
        client: ModelClient,
        model: str = QUOTE_DEFAULT_MODEL,
        max_tokens: int = 400,
    ) -> None:
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        path = Path(__file__).parent / "prompts" / f"{QUOTE_PROMPT_VERSION}.md"
        self.prompt = path.read_text(encoding="utf-8").strip()

    def build_request(self, element_id: str, image_png: bytes, quotes: list[str]) -> ModelRequest:
        # The figure image and the quotes only, never the description they came from
        text = "Are these quotes written in the image?\n"
        text += json.dumps({"quotes": quotes}, ensure_ascii=False)
        return ModelRequest(
            model=self.model,
            system=self.prompt,
            messages=[ModelMessage(role="user", text=text, image_png=image_png)],
            output_schema=QuoteCheckOutput,
            prompt_version=QUOTE_PROMPT_VERSION,
            element_id=element_id,
            max_tokens=self.max_tokens,
        )

    def written(self, element_id: str, image_png: bytes, quotes: list[str]) -> list[str]:
        # The quotes the model sees written in the image; none when it gives no valid answer
        request = self.build_request(element_id, image_png, quotes)
        for _attempt in range(2):
            try:
                response = self.client.complete_structured(request)
                output = QuoteCheckOutput.model_validate(response.output.model_dump(mode="python"))
            except (TypeError, ValueError):
                continue
            answers = {result.quote: result.written for result in output.results}
            return [quote for quote in quotes if answers.get(quote)]
        return []
