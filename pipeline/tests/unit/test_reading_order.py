from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.util import Inches

from a11y_pipeline.adapters import get_adapter
from a11y_pipeline.adapters.pptx.writer import verify_updated_deck, write_updated_project
from a11y_pipeline.analysis.reading_order import (
    Drawn,
    Unit,
    plan_reading_order,
    reorder_keeping_stacking,
)
from a11y_pipeline.bundle.bundle import Bundle

TITLE = (60, 20, 900, 90)


def test_a_layout_with_one_reading_is_put_in_that_order() -> None:
    # The picture on the right was added before the text on the left
    units = [
        Unit("title", TITLE, 0),
        Unit("picture", (520, 120, 900, 400), 1),
        Unit("text", (60, 120, 480, 400), 2),
        Unit("footer", (60, 440, 900, 500), 3),
    ]
    plan = plan_reading_order(units, first="title")
    assert (plan.decision, plan.order) == ("reorder", ["title", "text", "picture", "footer"])


def test_an_order_that_already_follows_the_layout_is_kept() -> None:
    units = [Unit("title", TITLE, 0), Unit("text", (60, 120, 480, 400), 1)]
    assert plan_reading_order(units, first="title").decision == "keep"


def test_two_columns_read_either_way_are_left_to_the_author() -> None:
    # Rows line up across the columns, so rows first and columns first disagree
    left_top, left_bottom = (60, 120, 400, 200), (60, 240, 400, 320)
    right_top, right_bottom = (500, 120, 900, 200), (500, 240, 900, 320)
    by_columns = [
        Unit("left top", left_top, 0),
        Unit("left bottom", left_bottom, 1),
        Unit("right top", right_top, 2),
        Unit("right bottom", right_bottom, 3),
    ]
    assert plan_reading_order(by_columns).decision == "keep"
    mixed = [
        Unit("right bottom", right_bottom, 0),
        Unit("left top", left_top, 1),
        Unit("right top", right_top, 2),
        Unit("left bottom", left_bottom, 3),
    ]
    plan = plan_reading_order(mixed)
    assert plan.decision == "unclear"
    assert plan.order == ["right bottom", "left top", "right top", "left bottom"]


def test_pieces_no_gap_separates_keep_their_order() -> None:
    # A label drawn over a picture
    units = [Unit("label", (300, 200, 400, 240), 0), Unit("picture", (100, 120, 800, 400), 1)]
    assert plan_reading_order(units).decision == "keep"


def test_shapes_that_touch_keep_their_stacking() -> None:
    drawn = [Drawn(1, (0, 0, 100, 100)), Drawn(2, (50, 50, 150, 150))]
    assert reorder_keeping_stacking(drawn, [2, 1], 0) is None
    apart = [Drawn(1, (0, 0, 100, 100)), Drawn(2, (300, 0, 400, 100))]
    assert reorder_keeping_stacking(apart, [2, 1], 0) == [2, 1]
    # A shape that may be drawn anywhere cannot be passed
    anywhere = [Drawn(1, (0, 0, 100, 100)), Drawn(3, None), Drawn(2, (300, 0, 400, 100))]
    assert reorder_keeping_stacking(anywhere, [2, 1], 0) is None


def test_shapes_nobody_reads_stay_before_the_shape_they_preceded() -> None:
    drawn = [Drawn(1, (0, 0, 10, 10)), Drawn(9, (500, 0, 510, 10)), Drawn(2, (300, 0, 310, 10))]
    assert reorder_keeping_stacking(drawn, [2, 1], 0) == [9, 2, 1]


def _deck(root: Path, joined: bool = False) -> Path:
    # A title, then a picture on the right added before the text on the left; `joined` draws a
    # line from the picture to the text between the two
    root.mkdir()
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = "Search"
    image = root / "chart.png"
    Image.new("RGB", (60, 40), "blue").save(image)
    picture = slide.shapes.add_picture(str(image), Inches(5), Inches(2), Inches(4), Inches(3))
    picture._element.xpath("./p:nvPicPr/p:cNvPr")[0].set("descr", "A bar chart of costs.")
    if joined:
        slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, Inches(1.5), Inches(2.5), Inches(5), Inches(2.5)
        )
    box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(2), Inches(1), Inches(1))
    box.text_frame.text = "Costs rise with depth."
    presentation.save(str(root / "deck.pptx"))
    return root


def _parse(root: Path):
    adapter = get_adapter("pptx")
    bundle = Bundle.from_path(root)
    return bundle, adapter.build_ir(bundle, adapter.preflight(bundle))


def _names(deck: Path) -> list[str]:
    return [shape.name for shape in Presentation(str(deck)).slides[0].shapes]


def test_the_updated_deck_reads_in_layout_order_and_looks_the_same(tmp_path: Path) -> None:
    bundle, ir = _parse(_deck(tmp_path / "deck"))
    slide = ir.containers[0]
    assert slide.attrs["shape_order"]
    texts = [ir.elements[element_id].semantic_type for element_id in slide.element_ids]
    assert texts == ["heading", "paragraph", "figure"]
    result = write_updated_project(bundle, ir, tmp_path / "out", tmp_path / "changes.txt")
    deck = result.project_root / "deck.pptx"
    assert _names(deck)[1:] == ["Rectangle 3", "Picture 2"]
    assert verify_updated_deck(bundle, deck).identical
    assert "reading order now follows the layout" in (tmp_path / "changes.txt").read_text()
    # Read again, the updated deck already reads in order
    _, again = _parse(result.project_root)
    assert "shape_order" not in again.containers[0].attrs
    assert not [issue for issue in again.issues if issue.code == "reading_order_unclear"]


def test_a_slide_that_cannot_be_reordered_without_restacking_is_listed(tmp_path: Path) -> None:
    # The line touches both, so the picture stays below it and the line below the text
    _, ir = _parse(_deck(tmp_path / "deck", joined=True))
    assert "shape_order" not in ir.containers[0].attrs
    assert [issue.details for issue in ir.issues if issue.code == "reading_order_unclear"] == [
        {"slide": 1}
    ]
