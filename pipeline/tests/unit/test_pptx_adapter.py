import io
import zipfile
from pathlib import Path

import pytest
from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.util import Inches

from a11y_pipeline.adapters import adapter_name_for, get_adapter
from a11y_pipeline.adapters.pptx.parser import DECORATIVE_NS, DECORATIVE_URI, is_junk_alt
from a11y_pipeline.adapters.pptx.render import find_soffice
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.bundle.mainfile import (
    MainFileNotFoundError,
    MultipleMainFilesError,
    find_main_file,
)
from a11y_pipeline.cli import _model_client
from a11y_pipeline.config import Settings
from a11y_pipeline.evaluation.pptx_checks import pptx_check_results
from a11y_pipeline.runs.folder import run_to_folder

TITLE_ONLY = 5
BLANK = 6


def _png(path: Path, colour: str) -> Path:
    Image.new("RGB", (60, 40), colour).save(path)
    return path


def _build_deck(root: Path, name: str = "deck.pptx") -> Path:
    # Four slides: a titled slide with two pictures, a group diagram, a table, an untitled slide
    presentation = Presentation()
    first = presentation.slides.add_slide(presentation.slide_layouts[TITLE_ONLY])
    first.shapes.title.text = "Gradient descent"
    plain = first.shapes.add_picture(str(_png(root / "a.png", "red")), Inches(1), Inches(2))
    described = first.shapes.add_picture(str(_png(root / "b.png", "blue")), Inches(5), Inches(2))
    described._element.xpath("./p:nvPicPr/p:cNvPr")[0].set("descr", "A blue square plot")
    plain._element.xpath("./p:nvPicPr/p:cNvPr")[0].set("descr", "Picture 3")

    second = presentation.slides.add_slide(presentation.slide_layouts[TITLE_ONLY])
    second.shapes.title.text = "Pipeline"
    group = second.shapes.add_group_shape()
    box = group.shapes.add_shape(1, Inches(1), Inches(2), Inches(2), Inches(1))
    box.text_frame.text = "Input"
    other = group.shapes.add_shape(1, Inches(4), Inches(2), Inches(2), Inches(1))
    other.text_frame.text = "Output"

    third = presentation.slides.add_slide(presentation.slide_layouts[TITLE_ONLY])
    third.shapes.title.text = "Results"
    third.shapes.add_table(2, 2, Inches(1), Inches(2), Inches(4), Inches(1))

    presentation.slides.add_slide(presentation.slide_layouts[BLANK])
    deck = root / name
    presentation.save(str(deck))
    return deck


@pytest.fixture
def deck_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    _build_deck(root)
    return root


def _ir(root: Path):
    bundle = Bundle.from_path(root)
    adapter = get_adapter("pptx")
    return bundle, adapter, adapter.build_ir(bundle, adapter.preflight(bundle))


def test_a_deck_is_found_as_the_main_file_and_routes_to_the_pptx_adapter(deck_root: Path) -> None:
    bundle = Bundle.from_path(deck_root)
    assert bundle.main_file == "deck.pptx"
    assert adapter_name_for(bundle.main_file) == "pptx"
    assert adapter_name_for("main.tex") == "tex-beamer"


def test_office_lock_files_and_several_decks_are_handled(deck_root: Path) -> None:
    (deck_root / "~$deck.pptx").write_bytes(b"lock")
    assert find_main_file(deck_root) == "deck.pptx"
    _build_deck(deck_root, "second.pptx")
    with pytest.raises(MultipleMainFilesError):
        find_main_file(deck_root)
    assert find_main_file(deck_root, "second.pptx") == "second.pptx"
    with pytest.raises(MainFileNotFoundError):
        find_main_file(deck_root, "missing.pptx")


def test_the_parser_reads_slides_titles_and_figures(deck_root: Path) -> None:
    _, _, ir = _ir(deck_root)
    assert ir.source_format == "pptx"
    assert [container.id for container in ir.containers] == [f"slide_0{n}" for n in range(1, 5)]
    assert ir.containers[0].title_element_id == "slide_01/heading_01"
    assert ir.elements["slide_01/heading_01"].content["text"] == "Gradient descent"
    first = ir.elements["slide_01/figure_01"]
    # "Picture 3" names nothing, so it is treated as missing
    assert first.accessibility.status == "needs_description"
    second = ir.elements["slide_01/figure_02"]
    assert second.accessibility.alt_text == "A blue square plot"
    assert second.accessibility.locked
    group = ir.elements["slide_02/figure_01"]
    assert group.subtype == "diagram"
    assert group.attrs["labels"] == ["Input", "Output"]
    assert ir.elements["slide_03/table_01"].attrs["first_row_header"] is True
    # The untitled slide gets an empty title for the model to propose
    untitled = ir.elements[ir.containers[3].title_element_id]
    assert untitled.attrs["added_title"] and untitled.accessibility.status == "needs_description"


def test_geometry_uses_a_bottom_left_origin_in_points(deck_root: Path) -> None:
    _, _, ir = _ir(deck_root)
    x0, y0, x1, y1 = ir.elements["slide_01/figure_01"].render.bbox
    assert x0 == pytest.approx(72.0)  # 1 inch
    assert y1 > y0 and x1 > x0
    # The picture sits 2 inches from the top of a 7.5 inch slide, so its top edge is 5.5 in up
    assert y1 == pytest.approx(5.5 * 72.0)


def test_an_author_marked_decorative_figure_is_left_alone(deck_root: Path) -> None:
    deck = deck_root / "deck.pptx"
    presentation = Presentation(str(deck))
    picture = next(s for s in presentation.slides[0].shapes if s.shape_type == 13)
    properties = picture._element.xpath("./p:nvPicPr/p:cNvPr")[0]
    extensions = etree.SubElement(
        properties, "{http://schemas.openxmlformats.org/drawingml/2006/main}extLst"
    )
    extension = etree.SubElement(
        extensions, "{http://schemas.openxmlformats.org/drawingml/2006/main}ext", uri=DECORATIVE_URI
    )
    etree.SubElement(extension, f"{{{DECORATIVE_NS}}}decorative", val="1")
    presentation.save(str(deck))
    _, _, ir = _ir(deck_root)
    figure = ir.elements["slide_01/figure_01"]
    assert figure.accessibility.decorative
    assert figure.accessibility.status == "done"


def test_junk_alt_text_is_recognised() -> None:
    assert is_junk_alt("Picture 12")
    assert is_junk_alt("diagram.png")
    assert not is_junk_alt("A bar chart of sales by quarter")


def test_preflight_explains_files_that_are_not_plain_decks(tmp_path: Path) -> None:
    adapter = get_adapter("pptx")
    legacy = tmp_path / "old"
    legacy.mkdir()
    (legacy / "deck.pptx").write_bytes(b"\xd0\xcf\x11\xe0" + b"\x00" * 600)
    # Not a zip, so the bundle cannot even choose it as a main file
    with pytest.raises(MainFileNotFoundError):
        Bundle.from_path(legacy, "deck.pptx")
    macro = tmp_path / "macro"
    macro.mkdir()
    with zipfile.ZipFile(macro / "deck.pptx", "w") as archive:
        archive.writestr("ppt/presentation.xml", "<p/>")
        archive.writestr("ppt/vbaProject.bin", b"x")
    result = adapter.preflight(Bundle.from_path(macro, "deck.pptx"))
    assert not result.ok
    assert result.issues[0].code == "macros_present"


def test_write_back_sets_alt_text_and_changes_nothing_else(deck_root: Path, tmp_path: Path) -> None:
    bundle, adapter, ir = _ir(deck_root)
    figure = ir.elements["slide_01/figure_01"]
    figure.accessibility.alt_text = "A red rectangle"
    figure.accessibility.extended_description = "It is plain red."
    figure.accessibility.status = "model_generated"
    written = adapter.write_back(
        bundle, ir, tmp_path / "out", tmp_path / "changes.diff", tmp_path / "v", None, 60
    )
    updated = written.project_root / "deck.pptx"
    reread = Presentation(str(updated))
    descriptions = [
        shape._element.xpath("./p:nvPicPr/p:cNvPr")[0].get("descr")
        for shape in reread.slides[0].shapes
        if shape.shape_type == 13
    ]
    assert "A red rectangle It is plain red." in descriptions
    assert "A blue square plot" in descriptions
    assert written.pixel_check.identical
    with zipfile.ZipFile(deck_root / "deck.pptx") as before, zipfile.ZipFile(updated) as after:
        assert before.namelist() == after.namelist()
        changed = [n for n in before.namelist() if before.read(n) != after.read(n)]
    # The slide that got a description, and the empty document title filled from slide 1
    assert changed == ["docProps/core.xml", "ppt/slides/slide1.xml"]
    assert "A red rectangle" in (tmp_path / "changes.diff").read_text(encoding="utf-8")
    # The undescribed diagram and the untitled slide are reported; nothing failed to save
    codes = {issue.code for issue in written.issues}
    assert codes == {"alt_missing", "slide_missing_title"}


def test_an_empty_document_title_is_filled_from_the_first_slide(
    deck_root: Path, tmp_path: Path
) -> None:
    bundle, adapter, ir = _ir(deck_root)
    written = adapter.write_back(
        bundle, ir, tmp_path / "out", tmp_path / "changes.diff", tmp_path / "v", None, 60
    )
    assert Presentation(str(written.project_root / "deck.pptx")).core_properties.title == (
        "Gradient descent"
    )


def test_a_default_document_title_is_replaced_and_a_real_one_kept(tmp_path: Path) -> None:
    for existing, expected in (
        ("PowerPoint Presentation", "Gradient descent"),
        ("Presentation1", "Gradient descent"),
        ("CSCE 625 Lecture 2", "CSCE 625 Lecture 2"),
    ):
        root = tmp_path / existing.replace(" ", "_")
        root.mkdir()
        deck = _build_deck(root)
        presentation = Presentation(str(deck))
        presentation.core_properties.title = existing
        presentation.save(str(deck))
        bundle, adapter, ir = _ir(root)
        written = adapter.write_back(
            bundle, ir, root / "out", root / "changes.diff", root / "v", None, 60
        )
        title = Presentation(str(written.project_root / "deck.pptx")).core_properties.title
        assert title == expected


def test_prepare_sends_picture_pixels_and_skips_unrenderable_shapes(
    deck_root: Path, tmp_path: Path
) -> None:
    bundle, adapter, ir = _ir(deck_root)
    prepared = adapter.prepare(bundle, ir, tmp_path, 60)
    assert "slide_01/figure_01" in prepared.figure_inputs
    image = Image.open(io.BytesIO(prepared.figure_inputs["slide_01/figure_01"].image_png))
    assert image.size == (60, 40)
    assert prepared.figure_inputs["slide_01/figure_01"].slide_title == "Gradient descent"
    # The figure also knows the lesson around it, and that it holds a picture
    assert prepared.figure_inputs["slide_01/figure_01"].other_titles == ["Pipeline"]
    assert prepared.ir.elements["slide_01/figure_01"].attrs["contains_picture"] is True
    if find_soffice() is None:
        assert "slide_02/figure_01" not in prepared.figure_inputs
        assert any(issue.code == "figure_image_unavailable" for issue in prepared.ir.issues)


def test_the_checks_report_what_is_missing(deck_root: Path) -> None:
    _, _, ir = _ir(deck_root)
    checks = pptx_check_results(ir)
    assert not checks["slide_titles"]
    assert not checks["figures_have_alt_text"]
    assert checks["unique_titles"]


def test_find_soffice_honours_an_explicit_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = tmp_path / "soffice"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setenv("SOFFICE_PATH", str(fake))
    assert find_soffice() == str(fake)


def test_a_full_run_returns_an_updated_deck(deck_root: Path, tmp_path: Path) -> None:
    settings = Settings(model_provider="fake")
    completed = run_to_folder(
        deck_root, _model_client(settings), settings, effort="low", output_root=tmp_path / "runs"
    )
    output = completed.folder.output_dir
    assert (output / "updated.pptx").is_file()
    assert (output / "updated_project.zip").is_file()
    state = completed.state
    assert state.adapter_name == "pptx"
    assert state.final_ir is not None
    assert state.final_ir.elements["slide_01/figure_01"].accessibility.alt_text
    assert completed.stats.fidelity.value == 100.0
    manifest = (completed.folder.manifest_path).read_text(encoding="utf-8")
    assert "output/updated.pptx" in manifest
    # With LibreOffice installed the run also offers a tagged PDF of the updated deck
    if find_soffice() is not None:
        assert (output / "tagged.pdf").is_file()
        assert "output/tagged.pdf" in manifest


def test_a_picture_the_describer_judges_decorative_is_marked_decorative(
    deck_root: Path, tmp_path: Path
) -> None:
    bundle, adapter, ir = _ir(deck_root)
    figure = ir.elements["slide_01/figure_01"]
    figure.accessibility.alt_text = "A plain red border"
    figure.accessibility.decorative_suggested = True
    figure.accessibility.status = "model_generated"
    written = adapter.write_back(
        bundle, ir, tmp_path / "out", tmp_path / "changes.diff", tmp_path / "v", None, 60
    )
    reread = Presentation(str(written.project_root / "deck.pptx"))
    shape = next(s for s in reread.slides[0].shapes if s.shape_id == figure.attrs["shape_id"])
    properties = shape._element.xpath("./p:nvPicPr/p:cNvPr")[0]
    assert properties.get("descr") is None
    assert properties.xpath(f".//a:ext[@uri='{DECORATIVE_URI}']")
    assert written.pixel_check.identical
