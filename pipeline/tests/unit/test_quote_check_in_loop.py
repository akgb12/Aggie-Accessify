from pathlib import Path

from test_orchestration_graph import CV_ID, _document, _inputs, _settings

from a11y_pipeline.models.fake import FakeModelClient
from a11y_pipeline.orchestration.graph import run_pipeline

# Quotes text that is not among the extracted labels, as for text inside a screenshot
QUOTING_CV = {
    "alt_text": ("Five folds in a row; the third is marked Test and a note reads 'held out once'.")
}
PLAIN_CV = {"alt_text": "Five folds in a row; the third is marked Test, the rest train."}


def _run(tmp_path: Path, fake: FakeModelClient, **settings: object):
    return run_pipeline(
        model_client=fake,
        effort="medium",
        settings=_settings(**settings),
        run_id="quotes",
        telemetry_path=tmp_path / "telemetry.jsonl",
        base_ir=_document(),
        figure_inputs=_inputs(),
    )


def test_a_quote_the_model_sees_written_keeps_the_description(tmp_path: Path) -> None:
    confirmed = {"results": [{"quote": "held out once", "written": True}]}
    fake = FakeModelClient(scripts={CV_ID: [QUOTING_CV, confirmed]})
    state = _run(tmp_path, fake)
    assert [request.prompt_version for request in fake.requests][-1] == "quote_check_v1"
    assert state.final_ir is not None
    assert state.final_ir.elements[CV_ID].accessibility.alt_text == QUOTING_CV["alt_text"]
    assert "held out once" in state.figure_inputs[CV_ID].rendered_text
    codes = {issue.code for issue in state.candidates[-1].issues}
    assert "description_rejected" not in codes


def test_a_quote_the_model_does_not_see_is_still_rejected(tmp_path: Path) -> None:
    denied = {"results": [{"quote": "held out once", "written": False}]}
    fake = FakeModelClient(scripts={CV_ID: [QUOTING_CV, denied, PLAIN_CV]})
    state = _run(tmp_path, fake)
    assert "description_rejected" in {issue.code for issue in state.candidates[1].issues}
    # The repair writes a description without the invented quote, which is kept
    assert state.final_ir is not None
    assert state.final_ir.elements[CV_ID].accessibility.alt_text == PLAIN_CV["alt_text"]


def test_quotes_are_not_put_to_the_model_when_switched_off(tmp_path: Path) -> None:
    fake = FakeModelClient(scripts={CV_ID: [QUOTING_CV, PLAIN_CV]})
    _run(tmp_path, fake, verify_quotes=False)
    assert all(request.prompt_version != "quote_check_v1" for request in fake.requests)
