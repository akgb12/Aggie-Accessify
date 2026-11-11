import json
import zipfile
from pathlib import Path

from lxml import etree

from a11y_pipeline.adapters import get_adapter
from a11y_pipeline.adapters.docx.colors import faint_runs, set_run_colour
from a11y_pipeline.adapters.docx.writer import write_updated_project
from a11y_pipeline.bundle.bundle import Bundle

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
PACKAGE = "http://schemas.openxmlformats.org/package/2006"
OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WORD_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml"
# Word's own "White, Background 1, Darker 35%"
GREYED = '<w:color w:val="A6A6A6" w:themeColor="background1" w:themeShade="A6"/>'


def _run(text: str, properties: str = "") -> str:
    return f'<w:r><w:rPr>{properties}</w:rPr><w:t xml:space="preserve">{text}</w:t></w:r>'


def _document(root: Path) -> Path:
    # A handout with a greyed-out note, a note in a pale character style, dark text, and
    # white text on a navy shaded paragraph
    body = (
        "<w:p>"
        + _run("Covered last week", f'{GREYED}<w:sz w:val="22"/>')
        + "</w:p>"
        + "<w:p>"
        + _run("A pale aside", '<w:rStyle w:val="Pale"/>')
        + _run(" and dark text", '<w:color w:val="333333"/>')
        + "</w:p>"
        + '<w:p><w:pPr><w:shd w:val="clear" w:color="auto" w:fill="1F3864"/></w:pPr>'
        + _run("White on navy", '<w:color w:val="FFFFFF"/>')
        + "</w:p>"
    )
    document = f'{XML}<w:document xmlns:w="{W}"><w:body>{body}<w:sectPr/></w:body></w:document>'
    styles = (
        f'{XML}<w:styles xmlns:w="{W}">'
        '<w:docDefaults><w:rPrDefault><w:rPr><w:sz w:val="22"/></w:rPr></w:rPrDefault>'
        "</w:docDefaults>"
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/></w:style>'
        '<w:style w:type="character" w:styleId="Pale"><w:name w:val="Pale"/>'
        '<w:rPr><w:color w:val="BFBFBF"/></w:rPr></w:style>'
        "</w:styles>"
    )
    types = (
        f'{XML}<Types xmlns="{PACKAGE}/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="/word/document.xml" ContentType="{WORD_TYPE}.document.main+xml"/>'
        f'<Override PartName="/word/styles.xml" ContentType="{WORD_TYPE}.styles+xml"/></Types>'
    )
    root.mkdir(parents=True, exist_ok=True)
    path = root / "handout.docx"
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("[Content_Types].xml", types)
        package.writestr(
            "_rels/.rels",
            f'{XML}<Relationships xmlns="{PACKAGE}/relationships"><Relationship Id="rId1" '
            f'Type="{OFFICE}/officeDocument" Target="word/document.xml"/></Relationships>',
        )
        package.writestr(
            "word/_rels/document.xml.rels",
            f'{XML}<Relationships xmlns="{PACKAGE}/relationships"><Relationship Id="rId1" '
            f'Type="{OFFICE}/styles" Target="styles.xml"/></Relationships>',
        )
        package.writestr("word/document.xml", document)
        package.writestr("word/styles.xml", styles)
    return path


def test_faint_runs_are_found_through_their_styles_and_shading(tmp_path: Path) -> None:
    found = {run.text: run for run in faint_runs(_document(tmp_path / "in"))}
    assert set(found) == {"Covered last week", "A pale aside"}
    assert found["Covered last week"].colour == (166, 166, 166)
    # The pale colour comes from the character style
    assert found["A pale aside"].colour == (191, 191, 191)
    assert found["A pale aside"].background == (255, 255, 255)


def test_a_new_colour_replaces_the_theme_colour_in_schema_order() -> None:
    run = etree.fromstring(
        f'<w:r xmlns:w="{W}"><w:rPr><w:b/><w:sz w:val="22"/></w:rPr><w:t>x</w:t></w:r>'
    )
    set_run_colour(run, "757575")
    names = [etree.QName(child).localname for child in run.find(f"{{{W}}}rPr")]
    assert names == ["b", "color", "sz"]
    themed = etree.fromstring(
        f'<w:r xmlns:w="{W}"><w:rPr><w:color w:val="A6A6A6" w:themeColor="background1"/>'
        "</w:rPr><w:t>x</w:t></w:r>"
    )
    set_run_colour(themed, "757575")
    colour = themed.find(f"{{{W}}}rPr/{{{W}}}color")
    assert colour.get(f"{{{W}}}val") == "757575"
    assert colour.get(f"{{{W}}}themeColor") is None


def test_the_update_recolours_faint_runs(tmp_path: Path) -> None:
    document = _document(tmp_path / "in")
    bundle = Bundle.from_path(document.parent)
    adapter = get_adapter("docx")
    ir = adapter.build_ir(bundle, adapter.preflight(bundle))
    ir.metadata["contrast_fixes"] = json.dumps([run.record() for run in faint_runs(document)])
    result = write_updated_project(bundle, ir, tmp_path / "out", tmp_path / "changes.diff")
    updated = result.project_root / "handout.docx"
    assert faint_runs(updated) == []
    assert sum(op.operation == "fix_text_contrast" for op in result.operations) == 2
    assert "text colour #A6A6A6 -> #" in (tmp_path / "changes.diff").read_text(encoding="utf-8")
    with zipfile.ZipFile(updated) as package:
        xml = package.read("word/document.xml").decode("utf-8")
    # Dark text and the white text on navy are untouched
    assert 'w:val="333333"' in xml and 'w:val="FFFFFF"' in xml
