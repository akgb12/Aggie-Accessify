from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches

from a11y_pipeline.adapters import get_adapter
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.ir.models import Candidate
from a11y_pipeline.orchestration.candidates import evaluate_candidate
from a11y_pipeline.runs.known_descriptions import known_descriptions, restore_known_descriptions

SHORT = "A loss curve falling over training."
LONG = "The curve drops quickly over the first ten epochs, then flattens near 0.1."


def _deck(root: Path, descriptions: list[str]) -> Path:
    # One slide with a picture per description, each holding it in its alt text field
    root.mkdir()
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = "Training"
    for index, description in enumerate(descriptions):
        image = root / f"{index}.png"
        Image.new("RGB", (60, 40), ("red", "blue")[index % 2]).save(image)
        picture = slide.shapes.add_picture(str(image), Inches(1 + 4 * index), Inches(2))
        picture._element.xpath("./p:nvPicPr/p:cNvPr")[0].set("descr", description)
    presentation.save(str(root / "deck.pptx"))
    return root


def _figures(root: Path) -> tuple:
    adapter = get_adapter("pptx")
    bundle = Bundle.from_path(root)
    ir = adapter.build_ir(bundle, adapter.preflight(bundle))
    return ir, [element for element in ir.elements.values() if element.semantic_type == "figure"]


def test_a_description_an_earlier_run_wrote_is_split_back_into_its_parts(tmp_path: Path) -> None:
    earlier = {
        "elements": {
            "slide_01/figure_01": {
                "semantic_type": "figure",
                "accessibility": {"alt_text": SHORT, "extended_description": LONG},
            }
        }
    }
    # The update wrote both parts as one line; the author wrote the second picture's text
    root = _deck(tmp_path / "deck", [f"{SHORT} {LONG}", "A professor's own description."])
    ir, (written, authored) = _figures(root)
    assert written.accessibility.alt_text == f"{SHORT} {LONG}"
    assert restore_known_descriptions(ir, known_descriptions(earlier)) == 1
    assert (written.accessibility.alt_text, written.accessibility.extended_description) == (
        SHORT,
        LONG,
    )
    assert written.accessibility.locked
    assert authored.accessibility.alt_text == "A professor's own description."
    assert authored.accessibility.extended_description is None


def test_a_description_an_earlier_run_wrote_is_scored_against_the_same_terms(
    tmp_path: Path,
) -> None:
    earlier = {
        "elements": {
            "f": {
                "semantic_type": "figure",
                "accessibility": {"alt_text": SHORT, "extended_description": LONG},
                "fidelity": {"required_concepts": ["label:loss"], "excluded_concepts": ["x"]},
            }
        }
    }
    root = _deck(tmp_path / "deck", [f"{SHORT} {LONG}"])
    ir, (figure,) = _figures(root)
    assert figure.fidelity.required_concepts == []
    restore_known_descriptions(ir, known_descriptions(earlier))
    assert figure.fidelity.required_concepts == ["label:loss"]
    assert figure.fidelity.excluded_concepts == []


def test_a_description_someone_edited_is_read_as_written(tmp_path: Path) -> None:
    earlier = {
        "elements": {
            "f": {
                "semantic_type": "figure",
                "accessibility": {"alt_text": SHORT, "extended_description": LONG},
            }
        }
    }
    root = _deck(tmp_path / "deck", [f"{SHORT} {LONG} Edited by hand."])
    ir, (figure,) = _figures(root)
    assert restore_known_descriptions(ir, known_descriptions(earlier)) == 0
    assert figure.accessibility.alt_text == f"{SHORT} {LONG} Edited by hand."


def test_a_lone_shape_with_a_description_is_a_described_figure(tmp_path: Path) -> None:
    # An earlier run describes a diagram on one of its shapes and marks the rest decorative,
    # so read again the described shape stands alone; it is read out, so it still counts
    root = tmp_path / "deck"
    root.mkdir()
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = "Search"
    described = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(1), Inches(2), Inches(1), Inches(1))
    described._element.xpath("./p:nvSpPr/p:cNvPr")[0].set("descr", SHORT)
    slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(5), Inches(2), Inches(1), Inches(1))
    presentation.save(str(root / "deck.pptx"))
    _, figures = _figures(root)
    assert [(figure.accessibility.alt_text, figure.accessibility.locked) for figure in figures] == [
        (SHORT, True)
    ]


def test_a_picture_the_update_marks_decorative_is_left_out_of_the_score(tmp_path: Path) -> None:
    # The score counts what the updated file holds, so reading it again scores the same
    root = _deck(tmp_path / "deck", [""])
    ir, (picture,) = _figures(root)
    picture.accessibility.alt_text = "A cartoon robot."
    picture.accessibility.status = "model_generated"
    candidate = Candidate(candidate_id="c0", round=0, patches=[])
    assert evaluate_candidate(ir, candidate, 0.75).candidate.scores["A"] == 60.0
    picture.accessibility.decorative_suggested = True
    assert evaluate_candidate(ir, candidate, 0.75).candidate.scores["A"] == 100.0
