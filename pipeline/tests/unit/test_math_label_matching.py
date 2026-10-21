from test_label_punctuation_matching import _figure

from a11y_pipeline.evaluation.concepts import evaluate_coverage
from a11y_pipeline.evaluation.mathtext import fold_math, math_label_present
from a11y_pipeline.evaluation.vetoes import figure_contradiction_veto
from a11y_pipeline.ir.models import Candidate, Container, DocumentIR, Patch
from a11y_pipeline.orchestration.candidates import evaluate_candidate


def test_math_notation_folds_to_the_spoken_letters() -> None:
    # "$X_1$", "X1" and "X 1" are one label; Greek letters match their names
    assert fold_math("$X_1$") == fold_math("X1") == fold_math("X 1") == "x1"
    assert fold_math(r"$\lambda$") == fold_math("λ") == "lambda"
    assert fold_math(r"$\hat{y}$") == fold_math("y-hat") == "yhat"


def test_subscript_labels_are_covered_by_plain_notation() -> None:
    # The model writes F1 where the source draws $F_1$; that is the same label
    alt = "A top node Y points to feature nodes F1, F2 and Fn."
    coverage = evaluate_coverage(alt, ["label:$Y$", "label:$F_1$", "label:$F_2$", "label:$F_n$"])
    assert coverage.coverage == 1.0


def test_one_character_math_labels_are_not_matched_by_accident() -> None:
    # A bare "$>$" folds to nothing, so it must not match every text
    assert not math_label_present("anything at all", "$>$")


def test_a_wrong_subscript_is_still_missing() -> None:
    # Notation tolerance must not make X2 stand in for X1
    coverage = evaluate_coverage("Nodes X2 and X3.", ["label:$X_1$"])
    assert coverage.coverage == 0.0


def test_words_drawn_in_the_figure_are_visible_even_without_a_node_label() -> None:
    # Axis names and yes/no edge labels are not extracted as node labels but are in the picture
    element = _figure("A decision tree: 'no' leads to Class 1 and 'yes' to a test.", [])
    visible = ["Feature $A$?", "Class 1"]
    assert figure_contradiction_veto(element, visible) is not None
    assert figure_contradiction_veto(element, visible, ["yes", "no", "Class", "1"]) is None


def test_a_quote_spanning_a_math_symbol_matches_the_drawn_words() -> None:
    # 'larger lambda, simpler model' is the drawn text "larger λ simpler model"
    element = _figure("A falling curve labeled 'larger lambda, simpler model'.", [])
    assert (
        figure_contradiction_veto(element, ["simpler model"], ["larger", "λ", "simpler", "model"])
        is None
    )


def test_a_made_up_label_is_still_vetoed_when_words_are_known() -> None:
    # Knowing the drawn words must not let an invented label through
    element = _figure("Boxes labeled 'Fold 6'.", [])
    veto = figure_contradiction_veto(element, ["Fold 1"], ["Fold", "1", "Test"])
    assert veto is not None
    assert veto.details["quoted_label"] == "Fold 6"


def test_a_short_quote_does_not_match_inside_a_longer_word() -> None:
    # 'no' is not found in "node"
    element = _figure("Arrow labeled 'no'.", [])
    assert figure_contradiction_veto(element, ["Class 1"], ["node", "Class", "1"]) is not None


def _document_with_two_figures() -> DocumentIR:
    # Two figures on one slide, one described faithfully and one with an invented label
    first = _figure("x", [])
    second = first.model_copy(deep=True)
    second.id = "slide_09/figure_02"
    return DocumentIR(
        document_id="doc123456789012",
        source_format="tex-beamer",
        main_file="main.tex",
        containers=[
            Container(id="slide_09", kind="slide", element_ids=[first.id, second.id]),
        ],
        elements={first.id: first, second.id: second},
    )


def test_one_contradicting_figure_does_not_disqualify_the_candidate() -> None:
    # Only the contradicting description is dropped; the other figure keeps its text
    document = _document_with_two_figures()
    patches = [
        Patch(
            element_id="slide_09/figure_01",
            path="accessibility.alt_text",
            value="A box labeled 'Input'.",
            by="model",
            round=0,
            note="",
        ),
        Patch(
            element_id="slide_09/figure_02",
            path="accessibility.alt_text",
            value="A box labeled 'Banana'.",
            by="model",
            round=0,
            note="",
        ),
    ]
    candidate = Candidate(candidate_id="c1", round=0, patches=patches)
    evaluation = evaluate_candidate(
        document,
        candidate,
        0.75,
        None,
        {"slide_09/figure_01": ["Input"], "slide_09/figure_02": ["Input"]},
    )
    assert evaluation.candidate.vetoes == []
    assert evaluation.candidate.scores["F"] == 100.0
    kept = evaluation.document.elements["slide_09/figure_01"].accessibility
    dropped = evaluation.document.elements["slide_09/figure_02"].accessibility
    assert kept.alt_text == "A box labeled 'Input'."
    assert dropped.alt_text is None
    assert evaluation.failing_element_ids == ["slide_09/figure_02"]
    codes = [issue.code for issue in evaluation.candidate.issues]
    assert "description_rejected" in codes
