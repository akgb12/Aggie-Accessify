from a11y_pipeline.capabilities.base import TextInventoryOutput
from a11y_pipeline.capabilities.text_inventory import TextInventoryCapability
from a11y_pipeline.models.fake import FakeModelClient

ELEMENT = "slide_10/figure_02"


def test_the_transcription_is_cleaned_and_kept_in_order() -> None:
    answer = {"text": ["if GOAL-TEST(problem,  STATE[node])", "then return node", " ", "x" * 400]}
    client = FakeModelClient(scripts={ELEMENT: [answer]})
    text = TextInventoryCapability(client).transcribe(ELEMENT, b"png")
    # Blank items and runs of text far too long to be a label are dropped
    assert text == ["if GOAL-TEST(problem, STATE[node])", "then return node"]
    request = client.requests[0]
    assert request.output_schema is TextInventoryOutput
    # Only the image is sent, never the slide's words
    assert request.messages[0].image_png == b"png"
    assert request.messages[0].text == "Transcribe the text written in this image."


def test_a_picture_without_text_gives_an_empty_list() -> None:
    client = FakeModelClient(scripts={ELEMENT: [{"text": []}]})
    assert TextInventoryCapability(client).transcribe(ELEMENT, b"png") == []


def test_no_valid_answer_gives_none() -> None:
    client = FakeModelClient(scripts={ELEMENT: [{"words": 1}, {"words": 2}]})
    assert TextInventoryCapability(client).transcribe(ELEMENT, b"png") is None
