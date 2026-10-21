import json
from pathlib import Path

from test_orchestration_graph import CV_ID, GOOD_CV, WEAK, _document, _inputs, _settings

from a11y_pipeline.capabilities.feedback import repair_problems
from a11y_pipeline.ir.models import Issue
from a11y_pipeline.models.fake import FakeModelClient
from a11y_pipeline.orchestration.graph import run_pipeline


def _context(request) -> dict:
    # Read the JSON context the capability sent with its request
    text = request.messages[0].text
    return json.loads(text.split("\n", 1)[1])


def test_repair_request_carries_the_earlier_text_and_what_was_wrong(tmp_path: Path) -> None:
    # The second attempt sees its weak first answer and the labels it left out
    fake = FakeModelClient(scripts={CV_ID: [WEAK, GOOD_CV]})
    run_pipeline(
        model_client=fake,
        effort="medium",
        settings=_settings(),
        run_id="feedback",
        telemetry_path=tmp_path / "telemetry.jsonl",
        base_ir=_document(),
        figure_inputs=_inputs(),
    )
    first, second = (_context(request) for request in fake.requests)
    assert "problems_to_fix" not in first
    assert second["previous_attempt"]["alt_text"] == WEAK["alt_text"]
    assert any("Test" in problem for problem in second["problems_to_fix"])


def test_problems_are_worded_for_each_kind_of_finding() -> None:
    # Each finding becomes one plain instruction, and other figures' findings are ignored
    issues = [
        Issue(
            element_id="a",
            code="alt_length_outlier",
            severity="warning",
            message="long",
            details={"word_count": 45, "limit": 40},
        ),
        Issue(
            element_id="a",
            code="description_rejected",
            severity="error",
            message="bad quote",
            details={"quoted_label": "Banana", "visible_labels": []},
        ),
        Issue(
            element_id="b",
            code="alt_missing",
            severity="error",
            message="missing",
        ),
    ]
    problems = repair_problems(issues, "a")
    assert len(problems) == 2
    assert "45 words" in problems[0]
    assert "Banana" in problems[1]
