from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.util import Inches

from a11y_pipeline.adapters import get_adapter
from a11y_pipeline.bundle.bundle import Bundle
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
