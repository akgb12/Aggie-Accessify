import io
import json
import zipfile
from pathlib import Path

import pikepdf
import pytest
from lxml import etree
from PIL import Image

from a11y_pipeline.adapters import adapter_name_for, get_adapter
from a11y_pipeline.adapters.docx.math_text import math_text
from a11y_pipeline.adapters.docx.render import _find
from a11y_pipeline.adapters.pptx.render import find_soffice
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.cli import _model_client
from a11y_pipeline.config import Settings
from a11y_pipeline.evaluation.docx_checks import docx_check_results
from a11y_pipeline.runs.folder import run_to_folder

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NAMESPACES = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
    'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"'
)
PICTURE = (
    '<w:p><w:r><w:drawing><wp:inline><wp:extent cx="571500" cy="381000"/>'
    '<wp:docPr id="1" name="Picture 1" descr="latex-image-1.pdf"/>'
    '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
    '<pic:pic><pic:nvPicPr><pic:cNvPr id="1" name="Picture 1"/><pic:cNvPicPr/></pic:nvPicPr>'
    '<pic:blipFill><a:blip r:embed="rIdImage"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
    '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="571500" cy="381000"/></a:xfrm>'
    '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
    "</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>"
)


XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE = "http://schemas.openxmlformats.org/package/2006"
WORD_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml"
_PACKAGE_RELATIONSHIPS = [
    ("rId1", f"{OFFICE}/officeDocument", "word/document.xml"),
    ("rId2", f"{PACKAGE}/relationships/metadata/core-properties", "docProps/core.xml"),
]
_DOCUMENT_RELATIONSHIPS = [
    ("rIdStyles", f"{OFFICE}/styles", "styles.xml"),
    ("rIdImage", f"{OFFICE}/image", "media/image1.png"),
]
_CORE = (
    f'{XML}<cp:coreProperties xmlns:cp="{PACKAGE}/metadata/core-properties" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title></dc:title></cp:coreProperties>'
)


def _relationships(items: list[tuple[str, str, str]]) -> str:
    entries = "".join(
        f'<Relationship Id="{rid}" Type="{kind}" Target="{target}"/>' for rid, kind, target in items
    )
    return f'{XML}<Relationships xmlns="{PACKAGE}/relationships">{entries}</Relationships>'


def _content_types() -> str:
    overrides = [
        ("/word/document.xml", f"{WORD_TYPE}.document.main+xml"),
        ("/word/styles.xml", f"{WORD_TYPE}.styles+xml"),
        ("/docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml"),
    ]
    defaults = [
        ("rels", "application/vnd.openxmlformats-package.relationships+xml"),
        ("xml", "application/xml"),
        ("png", "image/png"),
    ]
    body = "".join(f'<Default Extension="{e}" ContentType="{t}"/>' for e, t in defaults)
    body += "".join(f'<Override PartName="{n}" ContentType="{t}"/>' for n, t in overrides)
    return f'{XML}<Types xmlns="{PACKAGE}/content-types">{body}</Types>'


def _paragraph(
    text: str, bold: bool = False, style: str | None = None, lang: str | None = None
) -> str:
    properties = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    run_properties = ""
    if bold or lang:
        run_properties = "<w:rPr>" + ("<w:b/>" if bold else "")
        run_properties += f'<w:lang w:val="{lang}"/>' if lang else ""
        run_properties += "</w:rPr>"
    return (
        f'<w:p>{properties}<w:r>{run_properties}<w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
    )


def _document(root: Path, name: str = "handout.docx", core: bool = True) -> Path:
    # A small handout: a bold line that looks like a heading, styled headings that skip a
    # level, a picture with a file name for alt text, a table, an equation and a run of
    # English text marked as French
    body = "".join(
        [
            _paragraph("Week 3 Handout", bold=True),
            _paragraph("This handout covers the gas laws and how to use them in lab."),
            _paragraph("Background", style="Heading1"),
            _paragraph("Pressure and volume are related at a fixed temperature."),
            _paragraph("Details", style="Heading3"),
            _paragraph("Mode: ONLINE", lang="fr-FR"),
            PICTURE,
            "<w:tbl><w:tblPr/><w:tblGrid><w:gridCol/><w:gridCol/></w:tblGrid>"
            + "".join(
                f"<w:tr><w:tc><w:p><w:r><w:t>{a}</w:t></w:r></w:p></w:tc>"
                f"<w:tc><w:p><w:r><w:t>{b}</w:t></w:r></w:p></w:tc></w:tr>"
                for a, b in (("Gas", "Pressure"), ("Air", "101"), ("Helium", "98"))
            )
            + "</w:tbl>",
            "<w:p><m:oMath><m:f><m:num><m:r><m:t>P</m:t></m:r></m:num>"
            "<m:den><m:r><m:t>V</m:t></m:r></m:den></m:f></m:oMath></w:p>",
            *[
                _paragraph(f"Step {n} of the procedure is written out here in full.")
                for n in range(6)
            ],
        ]
    )
    document = f"{XML}<w:document {NAMESPACES}><w:body>{body}<w:sectPr/></w:body></w:document>"
    styles = (
        f"{XML}<w:styles {NAMESPACES}>"
        '<w:docDefaults><w:rPrDefault><w:rPr><w:sz w:val="22"/><w:lang w:val="en-US"/></w:rPr>'
        "</w:rPrDefault></w:docDefaults>"
        '<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>'
        '<w:pPr><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/>'
        '<w:pPr><w:outlineLvl w:val="2"/></w:pPr><w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>'
        "</w:styles>"
    )
    image = io.BytesIO()
    Image.new("RGB", (60, 40), "red").save(image, format="PNG")
    path = root / name
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("[Content_Types].xml", _content_types())
        package.writestr("_rels/.rels", _relationships(_PACKAGE_RELATIONSHIPS))
        package.writestr("word/_rels/document.xml.rels", _relationships(_DOCUMENT_RELATIONSHIPS))
        package.writestr("word/document.xml", document)
        package.writestr("word/styles.xml", styles)
        package.writestr("word/media/image1.png", image.getvalue())
        if core:
            package.writestr("docProps/core.xml", _CORE)
    return path


def _ir(root: Path):
    bundle = Bundle.from_path(root)
    adapter = get_adapter(adapter_name_for(bundle.main_file))
    return bundle, adapter, adapter.build_ir(bundle, adapter.preflight(bundle))


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    _document(root)
    return root


def test_a_word_document_is_found_and_read(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "~$handout.docx").write_bytes(b"lock")
    bundle, adapter, ir = _ir(root)
    assert bundle.main_file == "handout.docx"
    assert adapter_name_for("handout.docx") == "docx"
    assert ir.source_format == "docx"
    elements = list(ir.elements.values())
    candidate = next(e for e in elements if e.attrs.get("heading_candidate"))
    assert candidate.content["text"] == "Week 3 Handout"
    headings = [e for e in elements if e.semantic_type == "heading"]
    assert [e.attrs["level"] for e in headings] == [1, 3]
    assert any(issue.code == "heading_level_skipped" for issue in ir.issues)
    figure = next(e for e in elements if e.semantic_type == "figure")
    # A file name is not a description, so the picture is sent to be described
    assert figure.accessibility.status == "needs_description"
    assert figure.attrs["media"] == "word/media/image1.png"
    table = next(e for e in elements if e.semantic_type == "table")
    assert table.attrs["header_row_added"]
    formula = next(e for e in elements if e.semantic_type == "formula")
    assert formula.accessibility.alt_text == "P/V"
    outline = next(e for e in elements if e.subtype == "document_outline")
    assert outline.accessibility.status == "needs_description"
    assert [run["text"] for run in outline.attrs["foreign_runs"]] == ["Mode: ONLINE"]
    assert outline.attrs["needs_title"]


def test_word_equations_read_as_one_line_of_text() -> None:
    m = "http://schemas.openxmlformats.org/officeDocument/2006/math"
    equation = etree.fromstring(
        f'<m:oMath xmlns:m="{m}"><m:r><m:t>x=</m:t></m:r>'
        '<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr>'
        "<m:deg/><m:e><m:sSup><m:e><m:r><m:t>b</m:t></m:r></m:e><m:sup><m:r><m:t>2</m:t></m:r></m:sup>"
        "</m:sSup></m:e></m:rad></m:oMath>"
    )
    assert math_text(equation) == "x=sqrt(b^2)"


def test_repeated_lines_are_found_in_order_and_boxed_in_full() -> None:
    # Two answer lines read "True False"; a question wraps onto a second line
    flat = [
        ("true", (10, 90, 30, 100)),
        ("false", (60, 90, 80, 100)),
        ("which", (10, 70, 40, 80)),
        ("is", (45, 70, 55, 80)),
        ("right", (10, 60, 35, 70)),
        ("true", (10, 40, 30, 50)),
        ("false", (60, 40, 80, 50)),
    ]
    assert _find(flat, ["true", "false"], 0) == ((10, 90, 80, 100), 2)
    assert _find(flat, ["true", "false"], 2) == ((10, 40, 80, 50), 7)
    # The box covers every line of the text, not only its first words
    assert _find(flat, ["which", "is", "right"], 0) == ((10, 60, 55, 80), 5)


def test_a_full_run_returns_a_word_document_a_pdf_and_the_changes(tmp_path: Path) -> None:
    root = _project(tmp_path)
    settings = Settings(model_provider="fake")
    completed = run_to_folder(
        root, _model_client(settings), settings, effort="low", output_root=tmp_path / "runs"
    )
    output = completed.folder.output_dir
    state = completed.state
    assert state.adapter_name == "docx"
    assert state.final_ir is not None
    checks = docx_check_results(state.final_ir)
    assert checks["figures_have_alt_text"] and checks["tables_have_header_row"]
    # A line made into a heading is shown with the other model decisions
    made = next(e for e in state.final_ir.elements.values() if e.attrs.get("outline_level"))
    assert made.accessibility.status == "model_generated"
    updated = output / "updated.docx"
    with zipfile.ZipFile(updated) as package:
        root_xml = etree.fromstring(package.read("word/document.xml"))
        core = package.read("docProps/core.xml").decode()
    ns = {"w": W, "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"}
    # The look-alike heading is a heading now, by outline level, with its style untouched
    first = root_xml.find(".//w:body/w:p", ns)
    assert first.find("w:pPr/w:outlineLvl", ns) is not None
    assert first.find("w:pPr/w:pStyle", ns) is None
    assert root_xml.find(".//wp:docPr", ns).get("descr") not in (None, "latex-image-1.pdf")
    assert root_xml.find(".//w:tr/w:trPr/w:tblHeader", ns) is not None
    assert root_xml.find(".//w:lang", ns).get(f"{{{W}}}val") == "en-US"
    assert "<dc:title>Week 3 Handout</dc:title>" in core
    manifest = json.loads(completed.folder.manifest_path.read_text(encoding="utf-8"))
    paths = [item["path"] for item in manifest["outputs"]]
    assert "output/updated.docx" in paths and "output/changes.txt" in paths
    assert "is now a level 1 heading" in (output / "changes.txt").read_text(encoding="utf-8")
    if find_soffice() is not None:
        assert "output/tagged.pdf" in paths
        with pikepdf.open(output / "tagged.pdf") as pdf:
            roles = _roles(pdf)
        # The equation is read as text, and the skipped heading level is closed in the PDF
        assert "/Formula" in roles
        assert "/H3" not in roles
        assert completed.stats.fidelity.value == pytest.approx(100.0)


def _roles(pdf: pikepdf.Pdf) -> list[str]:
    found: list[str] = []
    pending = [pdf.Root.StructTreeRoot]
    while pending:
        node = pending.pop()
        if "/S" in node:
            found.append(str(node.S))
            if node.S == pikepdf.Name.Formula:
                assert str(node.get("/Alt", "")) == "P/V"
        kids = node.get("/K")
        children = list(kids) if isinstance(kids, pikepdf.Array) else [kids]
        pending.extend(kid for kid in children if isinstance(kid, pikepdf.Dictionary))
    return found


def test_a_document_saved_without_properties_gets_a_title(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    _document(root, core=False)
    bundle, adapter, ir = _ir(root)
    written = adapter.write_back(
        bundle, ir, tmp_path / "out", tmp_path / "changes.diff", tmp_path / "v", None, 60
    )
    with zipfile.ZipFile(written.project_root / "handout.docx") as package:
        core = package.read("docProps/core.xml").decode()
        types = package.read("[Content_Types].xml").decode()
        relationships = package.read("_rels/.rels").decode()
    # With no outline decided, the first heading names the document
    assert "<dc:title>Background</dc:title>" in core
    assert 'PartName="/docProps/core.xml"' in types
    assert 'Target="docProps/core.xml"' in relationships
