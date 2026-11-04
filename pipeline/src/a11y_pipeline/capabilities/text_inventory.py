from pathlib import Path

from a11y_pipeline.capabilities.base import TextInventoryOutput
from a11y_pipeline.models.client import ModelClient, ModelMessage, ModelRequest

INVENTORY_PROMPT_VERSION = "text_inventory_v1"
INVENTORY_DEFAULT_MODEL = "claude-sonnet-5-5"
# Text longer than this is not a label; it is dropped rather than trusted as a transcription
MAX_ITEM_CHARS = 300


class TextInventoryCapability:
    # Transcribe the words drawn in a picture, from the image alone. The slide's own text is
    # never shown, so the transcription cannot be steered by what the slide is about.
    def __init__(
        self,
        client: ModelClient,
        model: str = INVENTORY_DEFAULT_MODEL,
        max_tokens: int = 1000,
    ) -> None:
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        path = Path(__file__).parent / "prompts" / f"{INVENTORY_PROMPT_VERSION}.md"
        self.prompt = path.read_text(encoding="utf-8").strip()

    def build_request(self, element_id: str, image_png: bytes) -> ModelRequest:
        return ModelRequest(
            model=self.model,
            system=self.prompt,
            messages=[
                ModelMessage(
                    role="user",
                    text="Transcribe the text written in this image.",
                    image_png=image_png,
                )
            ],
            output_schema=TextInventoryOutput,
            prompt_version=INVENTORY_PROMPT_VERSION,
            element_id=element_id,
            max_tokens=self.max_tokens,
        )

    def transcribe(self, element_id: str, image_png: bytes) -> list[str] | None:
        # The pieces of text drawn in the image; None when the model gives no valid answer
        request = self.build_request(element_id, image_png)
        for _attempt in range(2):
            try:
                response = self.client.complete_structured(request)
                output = TextInventoryOutput.model_validate(
                    response.output.model_dump(mode="python")
                )
            except (TypeError, ValueError):
                continue
            items = [" ".join(item.split()) for item in output.text]
            return [item for item in items if item and len(item) <= MAX_ITEM_CHARS]
        return None
