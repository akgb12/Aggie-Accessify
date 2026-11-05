import zipfile
from pathlib import Path

import pikepdf
import pytest
from lxml import etree
from pptx import Presentation
from pptx.enum.shapes import MSO_CONNECTOR
from pptx.util import Inches

from a11y_pipeline.adapters.pptx.render import find_soffice
from a11y_pipeline.adapters.pptx.tagged_pdf import (
    export_tagged_pdf,
    prepare_deck_for_pdf,
    repair_tags,
)

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
TITLE_ONLY = 5


def _deck_with_connectors(path: Path) -> Path:
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[TITLE_ONLY])
    slide.shapes.title.text = "Agents"
    described = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT, Inches(1), Inches(2), Inches(4), Inches(2)
    )
    described._element.xpath("./p:nvCxnSpPr/p:cNvPr")[0].set("descr", "Percepts flow in")
    slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(1), Inches(3), Inches(4), Inches(3))
    presentation.save(str(path))
    return path


def _slide_root(deck: Path) -> etree._Element:
    with zipfile.ZipFile(deck) as package:
        return etree.fromstring(package.read("ppt/slides/slide1.xml"))


def test_only_a_described_connector_becomes_a_plain_line(tmp_path: Path) -> None:
    deck = _deck_with_connectors(tmp_path / "deck.pptx")
    prepared = tmp_path / "prepared.pptx"
    assert prepare_deck_for_pdf(deck, prepared) == 1
    root = _slide_root(prepared)
    lines = root.findall(f".//{{{P_NS}}}sp/{{{P_NS}}}nvSpPr/{{{P_NS}}}cNvPr")
    assert "Percepts flow in" in [line.get("descr") for line in lines]
    assert len(root.findall(f".//{{{P_NS}}}cxnSp")) == 1
    # The deck the person downloads is not touched
    assert len(_slide_root(deck).findall(f".//{{{P_NS}}}cxnSp")) == 2


def _pdf_with_export_gaps(path: Path) -> Path:
    # One page as LibreOffice writes it: an untagged background, tagged text, list items
    # directly under a Div, and a link with no description
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(200, 100))
    page = pdf.pages[0]
    page.obj.Contents = pdf.make_stream(
        b"0 0 200 100 re f\n/P <</MCID 0>> BDC BT ET EMC\n1 1 1 rg 0 0 m 10 10 l S\n"
    )
    items = [
        pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.StructElem, S=pikepdf.Name.LI))
        for _ in range(2)
    ]
    paragraph = pdf.make_indirect(
        pikepdf.Dictionary(Type=pikepdf.Name.StructElem, S=pikepdf.Name.P, K=0, Pg=page.obj)
    )
    division = pdf.make_indirect(
        pikepdf.Dictionary(
            Type=pikepdf.Name.StructElem,
            S=pikepdf.Name.Div,
            K=pikepdf.Array([paragraph, *items]),
        )
    )
    for item in items:
        item.P = division
    pdf.Root.StructTreeRoot = pdf.make_indirect(
        pikepdf.Dictionary(Type=pikepdf.Name.StructTreeRoot, K=pikepdf.Array([division]))
    )
    link = pdf.make_indirect(
        pikepdf.Dictionary(
            Type=pikepdf.Name.Annot,
            Subtype=pikepdf.Name.Link,
            Rect=pikepdf.Array([0, 0, 10, 10]),
            A=pikepdf.Dictionary(S=pikepdf.Name.URI, URI=pikepdf.String("https://tamu.edu/")),
        )
    )
    page.obj.Annots = pikepdf.Array([link])
    pdf.save(path)
    return path


def test_repair_marks_untagged_drawing_wraps_list_items_and_describes_links(
    tmp_path: Path,
) -> None:
    path = _pdf_with_export_gaps(tmp_path / "deck.pdf")
    result = repair_tags(path)
    assert (result.artifacts_added, result.lists_wrapped, result.links_described) == (2, 1, 1)
    with pikepdf.open(path) as pdf:
        operators = [str(item.operator) for item in pikepdf.parse_content_stream(pdf.pages[0])]
        # Background and line are artifacts; the tagged text is left where it was
        assert operators[:3] == ["BMC", "re", "f"]
        assert operators.count("BMC") == 2
        assert operators.count("BDC") == 1
        division = pdf.Root.StructTreeRoot.K[0]
        assert [str(kid.S) for kid in division.K] == ["/P", "/L"]
        new_list = division.K[1]
        assert all(item.P.objgen == new_list.objgen for item in new_list.K)
        assert str(pdf.pages[0].obj.Annots[0].Contents) == "Link to https://tamu.edu/"


@pytest.mark.skipif(find_soffice() is None, reason="LibreOffice is not installed")
def test_a_deck_exports_as_a_tagged_pdf_that_keeps_the_connector_description(
    tmp_path: Path,
) -> None:
    deck = _deck_with_connectors(tmp_path / "deck.pptx")
    result = export_tagged_pdf(deck, tmp_path / "out" / "tagged.pdf")
    assert result.pdf is not None
    with pikepdf.open(result.pdf) as pdf:
        assert pdf.Root.MarkInfo.Marked
        figures: list[str] = []
        pending = [pdf.Root.StructTreeRoot]
        while pending:
            node = pending.pop()
            if node.get("/S") == pikepdf.Name.Figure:
                figures.append(str(node.get("/Alt", "")))
            kids = node.get("/K")
            children = list(kids) if isinstance(kids, pikepdf.Array) else [kids]
            pending.extend(kid for kid in children if isinstance(kid, pikepdf.Dictionary))
        assert "Percepts flow in" in figures
