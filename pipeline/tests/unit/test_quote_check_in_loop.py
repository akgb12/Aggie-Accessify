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


def test_a_quote_of_other_text_on_the_slide_needs_no_model_check(tmp_path: Path) -> None:
    quoting_title = {
        "alt_text": "Five folds in a row; the third is marked Test, as 'Cross validation' shows."
    }
    fake = FakeModelClient(scripts={CV_ID: [quoting_title]})
    state = _run(tmp_path, fake)
    assert all(request.prompt_version != "quote_check_v1" for request in fake.requests)
    assert state.final_ir is not None
    assert state.final_ir.elements[CV_ID].accessibility.alt_text == quoting_title["alt_text"]


def test_a_picture_is_transcribed_first_and_its_text_makes_quotes_checkable(
    tmp_path: Path,
) -> None:
    document = _document()
    figure = document.elements[CV_ID]
    figure.attrs["contains_picture"] = True
    figure.attrs["text_unverifiable"] = True
    transcription = {"text": ["Fold 1", "held out once"]}
    fake = FakeModelClient(scripts={CV_ID: [transcription, QUOTING_CV]})
    state = run_pipeline(
        model_client=fake,
        effort="medium",
        settings=_settings(),
        run_id="inventory",
        telemetry_path=tmp_path / "telemetry.jsonl",
        base_ir=document,
        figure_inputs=_inputs(),
    )
    versions = [request.prompt_version for request in fake.requests]
    assert versions == ["text_inventory_v1", "figure_description_v6"]
    # The describer saw the transcription; the quote was found in it, so no check was needed
    assert "held out once" in fake.requests[1].messages[0].text
    assert state.figure_inputs[CV_ID].image_text == ["Fold 1", "held out once"]
    assert state.base_ir is not None
    assert state.base_ir.elements[CV_ID].attrs["text_unverifiable"] is False
    assert state.final_ir is not None
    assert state.final_ir.elements[CV_ID].accessibility.alt_text == QUOTING_CV["alt_text"]
