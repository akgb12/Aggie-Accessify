import json
from pathlib import Path

from test_orchestration_graph import CV_ID, GOOD_CV, _document, _inputs, _settings

from a11y_pipeline.models.fake import FakeModelClient
from a11y_pipeline.orchestration.graph import run_pipeline

FIXED_CV = {
    "alt_text": (
        "Five-fold cross-validation: five folds in a row, with the blue third box "
        "marked Test and the other four used for training."
    )
}


def _run(tmp_path: Path, fake: FakeModelClient, **settings: object):
    # Run the one-figure document with the given scripted model
    return run_pipeline(
        model_client=fake,
        effort="medium",
        settings=_settings(**settings),
        run_id="judge",
        telemetry_path=tmp_path / "telemetry.jsonl",
        base_ir=_document(),
        figure_inputs=_inputs(),
    )


def test_a_needs_work_verdict_triggers_a_repair_that_sees_the_judge_findings(
    tmp_path: Path,
) -> None:
    # The judge's missing items reach the next attempt, and the better text wins
    fake = FakeModelClient(
        scripts={
            CV_ID: [
                GOOD_CV,
                {"verdict": "needs_work", "invented": [], "missing": ["the blue test fold"]},
                FIXED_CV,
                {"verdict": "good", "invented": [], "missing": []},
            ]
        }
    )
    state = _run(tmp_path, fake, judge_in_loop=True)

    assert len(fake.requests) == 4
    repair = json.loads(fake.requests[2].messages[0].text.split("\n", 1)[1])
    assert any("blue test fold" in problem for problem in repair["problems_to_fix"])
    assert state.stop_reason == "nothing_failing"
    assert state.final_ir is not None
    assert state.final_ir.elements[CV_ID].accessibility.alt_text == FIXED_CV["alt_text"]
    assert state.candidates[1].scores["A"] == 70.0
    assert state.candidates[2].scores["A"] == 100.0


def test_the_judge_is_not_called_unless_enabled(tmp_path: Path) -> None:
    # Without the setting the loop is exactly the string-matching loop
    fake = FakeModelClient(scripts={CV_ID: [GOOD_CV]})
    state = _run(tmp_path, fake)
    assert len(fake.requests) == 1
    assert state.judgments == {}


def test_the_same_text_is_judged_once(tmp_path: Path) -> None:
    # A repair that returns identical text does not buy a second verdict
    fake = FakeModelClient(
        scripts={
            CV_ID: [
                GOOD_CV,
                {"verdict": "needs_work", "invented": [], "missing": ["x"]},
                GOOD_CV,
                GOOD_CV,
            ]
        }
    )
    state = _run(tmp_path, fake, judge_in_loop=True)
    judge_calls = [r for r in fake.requests if r.prompt_version == "figure_judge_v1"]
    assert len(judge_calls) == 1
    assert len(state.judgments) == 1
