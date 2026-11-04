from a11y_pipeline.capabilities.base import QuoteCheckOutput
from a11y_pipeline.capabilities.quote_check import QuoteCheckCapability
from a11y_pipeline.models.fake import FakeModelClient

ELEMENT = "slide_10/figure_02"


def test_only_quotes_the_model_sees_written_are_confirmed() -> None:
    answer = {
        "results": [
            {"quote": "then return node", "written": True},
            {"quote": "gradient boosting", "written": False},
        ]
    }
    client = FakeModelClient(scripts={ELEMENT: [answer]})
    confirmed = QuoteCheckCapability(client).written(
        ELEMENT, b"png", ["then return node", "gradient boosting"]
    )
    assert confirmed == ["then return node"]
    request = client.requests[0]
    assert request.output_schema is QuoteCheckOutput
    # The checker sees the image and the quotes, never the description
    assert request.messages[0].image_png == b"png"
    assert "gradient boosting" in request.messages[0].text


def test_no_valid_answer_confirms_nothing() -> None:
    client = FakeModelClient(scripts={ELEMENT: [{"bad": 1}, {"bad": 2}]})
    assert QuoteCheckCapability(client).written(ELEMENT, b"png", ["zebra"]) == []
