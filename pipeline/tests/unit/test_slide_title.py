from a11y_pipeline.capabilities.base import FigureDescriptionInput, SlideTitleOutput
from a11y_pipeline.capabilities.slide_title import SlideTitleCapability, clean_title
from a11y_pipeline.models.fake import FakeModelClient


def test_titles_are_cleaned() -> None:
    assert clean_title("  Breadth-first search example. ") == "Breadth-first search example"
    assert clean_title("") == ""
    assert clean_title(" ".join(["word"] * 20)) == ""


def _input(image: bytes = b"") -> FigureDescriptionInput:
    return FigureDescriptionInput(
        element_id="slide_03/heading_01",
        subtype="slide_title",
        image_png=image,
        source_code=None,
        visible_labels=[],
        slide_title=None,
        nearby_text=["Nearest neighbours from a collection of two million images"],
        other_titles=["Scene completion", "Results"],
    )


def test_a_proposed_title_becomes_the_heading_text() -> None:
    client = FakeModelClient(scripts={"slide_03/heading_01": [{"title": "Nearest neighbours."}]})
    result = SlideTitleCapability(client).run(_input(), run_id="r")
    values = {patch.path: patch.value for patch in result.patches}
    assert values == {
        "content.text": "Nearest neighbours",
        "accessibility.status": "model_generated",
    }
    request = client.requests[0]
    assert request.output_schema is SlideTitleOutput
    # Without a slide image the request is text only, with the nearby titles to stay unique
    assert request.messages[0].image_png is None
    assert "Scene completion" in request.messages[0].text


def test_an_unusable_title_is_retried_then_marked_failed() -> None:
    long = " ".join(["word"] * 20)
    client = FakeModelClient(scripts={"slide_03/heading_01": [{"title": long}, {"title": ""}]})
    result = SlideTitleCapability(client).run(_input(b"png"), run_id="r")
    assert [(patch.path, patch.value) for patch in result.patches] == [
        ("accessibility.status", "failed")
    ]
    assert result.history is None
