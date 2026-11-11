import json
import shutil
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.util import Inches

from a11y_pipeline.adapters import get_adapter
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.capabilities.base import FigureDescriptionInput, FigureDescriptionOutput
from a11y_pipeline.cli import _good_fake_response
from a11y_pipeline.config import Settings
from a11y_pipeline.ir.models import Candidate
from a11y_pipeline.models.fake import FakeModelClient
from a11y_pipeline.orchestration.candidates import evaluate_candidate
from a11y_pipeline.orchestration.nodes import _with_earlier_quotes
from a11y_pipeline.runs.folder import run_to_folder
from a11y_pipeline.runs.known_descriptions import (
    EARLIER_DESCRIPTION,
    known_descriptions,
    restore_known_descriptions,
)

SHORT = "A loss curve falling over training."
LONG = "The curve drops quickly over the first ten epochs, then flattens near 0.1."


def _diagram_deck(root: Path) -> Path:
    # A grouped diagram: a box labelled Start joined to one labelled Goal
    root.mkdir()
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = "Search tree"
    group = slide.shapes.add_group_shape()
    for text, left in (("Start", 1), ("Goal", 4)):
        box = group.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(left), Inches(3), Inches(1), Inches(1)
        )
        box.text_frame.text = text
    group.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT, Inches(2), Inches(3.5), Inches(4), Inches(3.5)
    )
    presentation.save(str(root / "deck.pptx"))
    return root


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
    # The run's own description may be improved; the author's stays locked as written
    assert not written.accessibility.locked
    assert written.attrs[EARLIER_DESCRIPTION]
    assert authored.accessibility.locked
    assert EARLIER_DESCRIPTION not in authored.attrs
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


WEAK = "Two shapes joined by a line."
GOOD = "A box labelled Start joins a box labelled Goal by a straight line."


def _diagram(ir) -> str:
    return next(
        element.id
        for element in ir.elements.values()
        if element.semantic_type == "figure" and element.subtype == "diagram"
    )


def _translate(root: Path, out: Path, descriptions: list[str], known=None):
    # One run whose model answers the diagram with the given descriptions in turn
    settings = Settings(model_provider="fake")
    ir = _figures(root)[0]
    if known:
        restore_known_descriptions(ir, known)
    outputs = [FigureDescriptionOutput(alt_text=text) for text in descriptions]
    client = FakeModelClient({_diagram(ir): outputs}, default_generator=_good_fake_response)
    done = run_to_folder(
        root, client, settings, effort="low", output_root=out, known_descriptions=known
    )
    following = out / "next"
    following.mkdir()
    shutil.copy2(done.folder.output_dir / "updated.pptx", following / "deck.pptx")
    final = json.loads((done.folder.root / "ir_final.json").read_text())
    return done, client, following, known_descriptions(final)


def _diagram_alt(done) -> str | None:
    return done.state.final_ir.elements[_diagram(done.state.final_ir)].accessibility.alt_text


def test_a_retranslate_keeps_a_better_description_and_never_a_worse_one(tmp_path: Path) -> None:
    deck = _diagram_deck(tmp_path / "in")
    first, _, current, known = _translate(deck, tmp_path / "r1", [WEAK] * 4)
    assert _diagram_alt(first) == WEAK
    # A new attempt that scores no higher leaves the earlier description and the file as is
    same, _, unchanged, _ = _translate(current, tmp_path / "r2", ["Two joined shapes."], known)
    assert _diagram_alt(same) == WEAK
    assert same.stats.accessibility.value == first.stats.accessibility.value
    assert (unchanged / "deck.pptx").read_bytes() == (current / "deck.pptx").read_bytes()
    # One that covers what the earlier one missed replaces it and raises the score
    better, _, improved, known = _translate(current, tmp_path / "r3", [GOOD], known)
    assert _diagram_alt(better) == GOOD
    assert better.stats.accessibility.value > first.stats.accessibility.value
    # A description already at the most its figure can score is not tried again
    again, client, _, _ = _translate(improved, tmp_path / "r4", [], known)
    assert _diagram_alt(again) == GOOD
    assert again.stats.accessibility.value == better.stats.accessibility.value
    assert not [r for r in client.requests if r.element_id == _diagram(again.state.final_ir)]


def test_quotes_an_earlier_run_checked_are_not_rejected_unseen(tmp_path: Path) -> None:
    # The run that wrote the description confirmed its quote against the image itself
    quoted = 'A shop front with a sign reading "BACKYARD".'
    root = _deck(tmp_path / "deck", [quoted])
    earlier = {
        "elements": {"f": {"semantic_type": "figure", "accessibility": {"alt_text": quoted}}}
    }
    ir, (picture,) = _figures(root)
    restore_known_descriptions(ir, known_descriptions(earlier))
    blank = FigureDescriptionInput(
        element_id=picture.id,
        subtype="image",
        image_png=b"",
        source_code=None,
        visible_labels=[],
        slide_title=None,
        nearby_text=[],
        rendered_text=["shop"],
    )
    inputs = _with_earlier_quotes(ir, {picture.id: blank})
    assert inputs[picture.id].rendered_text == ["shop", "BACKYARD"]
