from pathlib import Path

import pytest
from pptx import Presentation
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.util import Inches

from a11y_pipeline.adapters import get_adapter
from a11y_pipeline.adapters.pptx.render import find_soffice
from a11y_pipeline.adapters.pptx.structure import (
    Box,
    analyze_layout,
    guess_language,
    table_has_header_row,
    title_can_move_first,
)
from a11y_pipeline.adapters.pptx.writer import (
    ADDED_TITLE_NAME,
    DECORATIVE_URI,
    verify_updated_deck,
)
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.cli import _model_client
from a11y_pipeline.config import Settings
from a11y_pipeline.evaluation.pptx_checks import pptx_check_results
from a11y_pipeline.runs.folder import run_to_folder

TITLE_ONLY = 5


def _box(shape_id: int, kind: str, bbox, z: int | None = None, text: str = "") -> Box:
    return Box(shape_id, shape_id if z is None else z, kind, bbox, text)  # type: ignore[arg-type]


def test_touching_drawn_shapes_form_a_diagram_and_lone_ones_are_decoration() -> None:
    layout = analyze_layout(
        [
            _box(1, "drawing", (0, 0, 50, 30)),
            _box(2, "drawing", (52, 10, 100, 10)),  # an arrow that stops 2pt short of box 1
            _box(3, "drawing", (102, 0, 150, 30)),
            _box(4, "label", (5, 5, 45, 25), text="Start"),
            _box(5, "drawing", (300, 300, 400, 300)),  # a lone line far away
            _box(6, "label", (500, 500, 520, 520), text="note"),
        ]
    )
    assert [[box.shape_id for box in diagram] for diagram in layout.diagrams] == [[1, 2, 3, 4]]
    assert [box.shape_id for box in layout.decorative] == [5]


def test_text_labels_alone_never_make_a_diagram() -> None:
    layout = analyze_layout(
        [
            _box(1, "label", (0, 0, 50, 30), text="a"),
            _box(2, "label", (40, 0, 90, 30), text="b"),
            _box(3, "label", (80, 0, 130, 30), text="c"),
        ]
    )
    assert layout.diagrams == []
    assert layout.decorative == []


def test_the_title_moves_first_only_when_nothing_before_it_touches_it() -> None:
    title = _box(9, "title", (0, 0, 500, 60), z=5)
    picture = _box(1, "picture", (0, 100, 200, 300), z=1)
    assert title_can_move_first([picture, title], title)
    banner = _box(2, "drawing", (0, 0, 600, 80), z=2)
    assert not title_can_move_first([picture, banner, title], title)
    # A straight line has a box without area but is still drawn over the title
    underline = _box(3, "drawing", (0, 30, 500, 30), z=3)
    assert not title_can_move_first([picture, underline, title], title)


def test_header_rows_are_recognised() -> None:
    assert table_has_header_row([["Agent", "Sensors"], ["Taxi", "Cameras"]])
    assert table_has_header_row([["", "Crossword", "Driving"], ["Observable", "Fully", "No"]])
    assert not table_has_header_row([["Only one row"]])
    assert not table_has_header_row([["1", "2"], ["3", "4"]])
    assert not table_has_header_row([["", "", "x"], ["a", "b", "c"]])


def test_language_is_proposed_only_for_plain_english() -> None:
    english = ["The agent perceives the environment and acts on it with the goal of a high score"]
    assert guess_language(english * 2) == "en-US"
    assert guess_language(["Graph"]) is None
    assert guess_language(["Der Agent nimmt die Umgebung wahr und handelt in ihr " * 3]) is None


def _diagram_deck(root: Path) -> Path:
    # Slide 1: a diagram drawn from loose shapes, a lone line and a table without a header row,
    # with the title read last. Slide 2: an empty title box and no other title.
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[TITLE_ONLY])
    slide.shapes.title.text = "Search tree"
    slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(3), Inches(1), Inches(1))
    slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(4), Inches(3), Inches(1), Inches(1))
    slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT, Inches(2), Inches(3.5), Inches(4), Inches(3.5)
    )
    label = slide.shapes.add_textbox(Inches(1.1), Inches(3.2), Inches(0.8), Inches(0.5))
    label.text_frame.text = "Start"
    slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT, Inches(7), Inches(6.5), Inches(9), Inches(6.5)
    )
    frame = slide.shapes.add_table(2, 2, Inches(6), Inches(4.5), Inches(3), Inches(1))
    for column, (name, value) in enumerate((("Agent", "Taxi"), ("Sensors", "Cameras"))):
        frame.table.cell(0, column).text = name
        frame.table.cell(1, column).text = value
    frame._element.xpath(".//a:tblPr")[0].attrib.pop("firstRow", None)
    # Put the title last in the stacking order, so a screen reader reaches it last
    tree = slide.shapes._spTree
    heading = slide.shapes.title._element
    tree.remove(heading)
    tree.append(heading)
    empty = presentation.slides.add_slide(presentation.slide_layouts[TITLE_ONLY])
    empty.shapes.add_textbox(
        Inches(1), Inches(3), Inches(4), Inches(1)
    ).text_frame.text = "Nearest neighbours from a collection of two million images"
    deck_root = root / "project"
    deck_root.mkdir()
    presentation.save(str(deck_root / "deck.pptx"))
    return deck_root


@pytest.fixture
def diagram_root(tmp_path: Path) -> Path:
    return _diagram_deck(tmp_path)


def _parse(root: Path):
    bundle = Bundle.from_path(root)
    adapter = get_adapter("pptx")
    return bundle, adapter, adapter.build_ir(bundle, adapter.preflight(bundle))


def test_the_parser_plans_every_layout_fix(diagram_root: Path) -> None:
    _, _, ir = _parse(diagram_root)
    first, second = ir.containers
    diagram = next(e for e in ir.elements.values() if e.source.native_type == "shape_cluster")
    assert diagram.subtype == "diagram"
    assert diagram.accessibility.status == "needs_description"
    assert diagram.attrs["labels"] == ["Start"]
    assert len(diagram.attrs["cluster_shape_ids"]) == 4
    assert len(diagram.attrs["decorative_shape_ids"]) == 2
    assert len(first.attrs["decorative_shape_ids"]) == 1  # the lone line
    assert first.attrs["move_title_first"] is True
    assert first.element_ids[0] == first.title_element_id
    table = next(e for e in ir.elements.values() if e.semantic_type == "table")
    assert table.attrs["header_row_added"] is True
    # The empty title box does not count; a title is planned for the model to write
    added = ir.elements[second.title_element_id]
    assert added.attrs["added_title"] is True
    assert added.accessibility.status == "needs_description"
    assert pptx_check_results(ir)["title_first_in_reading_order"]


def test_write_back_applies_the_fixes_without_changing_the_look(
    diagram_root: Path, tmp_path: Path
) -> None:
    bundle, adapter, ir = _parse(diagram_root)
    diagram = next(e for e in ir.elements.values() if e.source.native_type == "shape_cluster")
    diagram.accessibility.alt_text = "A start box with an arrow to a circle"
    diagram.accessibility.status = "model_generated"
    added = ir.elements[ir.containers[1].title_element_id]
    added.content["text"] = "Nearest neighbours"
    written = adapter.write_back(
        bundle, ir, tmp_path / "out", tmp_path / "changes.diff", tmp_path / "v", None, 60
    )
    deck = written.project_root / "deck.pptx"
    assert written.pixel_check.identical
    reread = Presentation(str(deck))
    first = reread.slides[0]
    shapes = list(first.shapes)
    assert shapes[0].is_placeholder and shapes[0].text_frame.text == "Search tree"
    carrier = next(s for s in shapes if s.shape_id == diagram.attrs["shape_id"])
    assert carrier._element.xpath("./*[1]/p:cNvPr/@descr") == [diagram.accessibility.alt_text]
    decorative = [
        s.shape_id for s in shapes if s._element.xpath(f".//a:ext[@uri='{DECORATIVE_URI}']")
    ]
    assert sorted(decorative) == sorted(
        diagram.attrs["decorative_shape_ids"] + ir.containers[0].attrs["decorative_shape_ids"]
    )
    table = next(s for s in shapes if getattr(s, "has_table", False) and s.has_table)
    assert table._element.xpath(".//a:tblPr/@firstRow") == ["1"]
    second = list(reread.slides[1].shapes)
    title = second[0]
    assert title.name == ADDED_TITLE_NAME
    assert title.text_frame.text == "Nearest neighbours"
    assert title.top + title.height <= 0
    ids = reread.slides[1]._element.xpath(".//p:cNvPr/@id")
    assert len(ids) == len(set(ids))
    diff = (tmp_path / "changes.diff").read_text(encoding="utf-8")
    assert "marked decorative" in diff and "added title" in diff and "first row" in diff


def test_the_check_catches_a_shape_that_moved(diagram_root: Path, tmp_path: Path) -> None:
    bundle, adapter, ir = _parse(diagram_root)
    written = adapter.write_back(
        bundle, ir, tmp_path / "out", tmp_path / "changes.diff", tmp_path / "v", None, 60
    )
    deck = written.project_root / "deck.pptx"
    presentation = Presentation(str(deck))
    shape = next(s for s in presentation.slides[0].shapes if s.has_text_frame and s.text == "Start")
    shape.left += Inches(1)
    presentation.save(str(deck))
    assert verify_updated_deck(bundle, deck).different_pages == [1]


def test_a_full_run_writes_titles_and_descriptions(diagram_root: Path, tmp_path: Path) -> None:
    settings = Settings(model_provider="fake")
    completed = run_to_folder(
        diagram_root, _model_client(settings), settings, effort="low", output_root=tmp_path / "r"
    )
    assert completed.stats.fidelity.value == 100.0
    ir = completed.state.final_ir
    assert ir is not None
    checks = pptx_check_results(ir)
    assert checks["slide_titles"] and checks["figures_have_alt_text"]
    assert checks["title_first_in_reading_order"]
    # The table has a built-in style, so a header row would restyle it. With a renderer that
    # change is seen and undone; without one it is never made. Either way the person is told.
    assert not checks["tables_have_header_row"]
    codes = {issue.code for issue in ir.issues}
    assert codes & {"layout_change_undone", "table_header_unchecked"}
    deck = Presentation(str(completed.folder.output_dir / "updated.pptx"))
    assert deck.slides[1].shapes[0].text_frame.text == "Overview of slide 02"
    if find_soffice() is not None:
        # With a renderer the review shows real slide images
        assert len(list((completed.folder.root / "pages").glob("*.png"))) == 2


def test_a_group_joins_the_loose_diagram_it_touches_but_never_becomes_decoration() -> None:
    layout = analyze_layout(
        [
            _box(1, "group", (0, 0, 100, 60)),
            _box(2, "drawing", (102, 30, 160, 30)),
            _box(3, "label", (110, 10, 150, 25), text="cost 2"),
            _box(4, "group", (400, 400, 500, 500)),
        ]
    )
    assert [[box.shape_id for box in diagram] for diagram in layout.diagrams] == [[1, 2, 3]]
    assert layout.decorative == []
