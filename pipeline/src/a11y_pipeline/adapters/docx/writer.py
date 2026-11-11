import difflib
import json
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from a11y_pipeline.adapters.docx.colors import set_run_colour
from a11y_pipeline.adapters.docx.ooxml import (
    CORE_PART,
    DOCUMENT_PART,
    MC_NS,
    STYLES_PART,
    V_NS,
    figures,
    is_vml,
    paragraphs,
    runs,
    tables,
    text_of,
    w,
)
from a11y_pipeline.adapters.pptx.structure import is_default_title
from a11y_pipeline.adapters.pptx.writer import (
    alt_field_text,
    decorative_now,
    mark_decorative,
    set_core_properties,
)
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.ir.models import DocumentIR, Element, Issue
from a11y_pipeline.synthesis.plan import OutputOperation

CONTENT_TYPES_PART = "[Content_Types].xml"
PACKAGE_RELATIONSHIPS_PART = "_rels/.rels"
CORE_TYPE = "application/vnd.openxmlformats-package.core-properties+xml"
CORE_RELATIONSHIP = (
    "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"
)
EMPTY_CORE = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/'
    b'core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"></cp:coreProperties>'
)
# Paragraph properties that must come after w:outlineLvl in Word's schema order
AFTER_OUTLINE_LEVEL = {"divId", "cnfStyle", "rPr", "sectPr", "pPrChange"}
# Run properties that must come after w:lang
AFTER_LANGUAGE = {"eastAsianLayout", "specVanish", "oMath"}


@dataclass
class DocumentEdits:
    # Everything written into the document, by the position the parser numbered it at
    descriptions: dict[int, str] = field(default_factory=dict)
    decorative: set[int] = field(default_factory=set)
    header_tables: set[int] = field(default_factory=set)
    headings: dict[int, int] = field(default_factory=dict)
    english_runs: set[int] = field(default_factory=set)
    language: str | None = None
    default_language: str | None = None
    title: str | None = None
    # New text colours as hex, by run position
    recolours: dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DocxWriterResult:
    project_root: Path
    diff_path: Path
    issues: list[Issue]
    operations: list[OutputOperation]


def write_updated_project(
    bundle: Bundle,
    ir: DocumentIR,
    output_root: Path,
    diff_path: Path,
) -> DocxWriterResult:
    # Copy the project and write the accessibility changes into the document; every other
    # part of the package is copied byte for byte
    if output_root.exists():
        raise FileExistsError("Updated project destination already exists")
    output_root.mkdir(parents=True)
    for relative in bundle.files:
        target = output_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundle.root / relative, target)
    edits, operations, issues = _collect_edits(ir)
    document = output_root / bundle.main_file
    before = _rewrite_package(document, edits)
    _write_diff(ir, edits, before, diff_path)
    return DocxWriterResult(output_root, diff_path, issues, operations)


def _collect_edits(ir: DocumentIR) -> tuple[DocumentEdits, list[OutputOperation], list[Issue]]:
    edits = DocumentEdits()
    operations: list[OutputOperation] = []
    issues: list[Issue] = []

    def operation(name: str, element_id: str | None, **details: object) -> None:
        operations.append(
            OutputOperation(
                output="updated_source",
                operation=name,
                element_id=element_id,
                source_file=DOCUMENT_PART,
                details=dict(details),
            )
        )

    for element in ir.elements.values():
        if element.semantic_type == "figure":
            index = int(element.attrs["figure"])
            if decorative_now(element):
                edits.decorative.add(index)
                operation("mark_drawing_decorative", element.id, figure=index)
                continue
            description = alt_field_text(element)
            if description is None:
                if not element.accessibility.locked and not element.accessibility.decorative:
                    issues.append(_alt_missing(element))
                continue
            edits.descriptions[index] = description
            operation("set_drawing_alt_text", element.id, figure=index)
        elif element.semantic_type == "table" and element.attrs.get("header_row_added"):
            edits.header_tables.add(int(element.attrs["table"]))
            operation("set_table_header_row", element.id, table=element.attrs["table"])
        elif element.attrs.get("heading_candidate") and int(
            element.attrs.get("outline_level") or 0
        ):
            level = int(element.attrs["outline_level"])
            edits.headings[int(element.attrs["paragraph"])] = level
            operation("set_heading_level", element.id, level=level)
        elif element.subtype == "document_outline":
            edits.english_runs = {int(index) for index in element.attrs.get("english_runs", [])}
            if edits.english_runs:
                operation("set_run_language", element.id, runs=sorted(edits.english_runs))
            proposed = " ".join(str(element.content.get("text") or "").split())
            if element.attrs.get("needs_title"):
                edits.title = proposed or _fallback_title(ir)
    language = ir.metadata.get("language_proposed") or ir.metadata.get("language") or None
    edits.language = language
    if ir.metadata.get("language_proposed"):
        edits.default_language = ir.metadata["language_proposed"]
        operation("set_document_language", None, language=edits.default_language)
    if edits.title:
        operation("set_document_title", None, title=edits.title)
    for fix in contrast_fixes(ir):
        edits.recolours[int(fix["run"])] = str(fix["after"])
        operation(
            "fix_text_contrast", None, run=fix["run"], before=fix["before"], after=fix["after"]
        )
    return edits, operations, issues


def contrast_fixes(ir: DocumentIR) -> list[dict]:
    # The text colour fixes chosen when the document was prepared
    return [fix for fix in json.loads(ir.metadata.get("contrast_fixes", "[]")) if "after" in fix]


def write_expected_document(bundle: Bundle, ir: DocumentIR, destination: Path) -> Path | None:
    # The original document with only its colour fixes, which is how the update should look;
    # None when nothing is recoloured
    fixes = contrast_fixes(ir)
    if not fixes:
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(bundle.root / bundle.main_file, destination)
    _rewrite_package(
        destination, DocumentEdits(recolours={int(fix["run"]): str(fix["after"]) for fix in fixes})
    )
    return destination


def _fallback_title(ir: DocumentIR) -> str | None:
    # Every document gets a title: its Title line, else its first heading, else its file name
    if ir.metadata.get("title_proposed"):
        return ir.metadata["title_proposed"]
    for container in ir.containers:
        for element_id in container.element_ids:
            element = ir.elements[element_id]
            heading = element.semantic_type == "heading" or int(
                element.attrs.get("outline_level") or 0
            )
            text = " ".join(str(element.content.get("text") or "").split())
            if heading and text:
                return text[:120]
    stem = Path(ir.main_file).stem.replace("_", " ").replace("-", " ")
    return " ".join(stem.split()) or None


def _alt_missing(element: Element) -> Issue:
    return Issue(
        element_id=element.id,
        code="alt_missing",
        severity="error",
        message="Figure was not updated because alternative text is missing",
        details={"status": element.accessibility.status},
    )


def _rewrite_package(document: Path, edits: DocumentEdits) -> bytes:
    # Rewrite only the parts that change; returns the original document XML for the diff
    temporary = document.with_suffix(".docx.tmp")
    original = b""
    with zipfile.ZipFile(document) as source, zipfile.ZipFile(temporary, "w") as target:
        names = set(source.namelist())
        add_core = CORE_PART not in names and bool(edits.title or edits.language)
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == DOCUMENT_PART:
                original = data
                data = _edit_document(data, edits)
            elif item.filename == STYLES_PART and edits.default_language:
                data = _set_default_language(data, edits.default_language)
            elif item.filename == CORE_PART:
                data = set_core_properties(data, edits.title, edits.language)
            elif add_core and item.filename == CONTENT_TYPES_PART:
                data = _register_core_type(data)
            elif add_core and item.filename == PACKAGE_RELATIONSHIPS_PART:
                data = _register_core_relationship(data)
            target.writestr(item, data, compress_type=item.compress_type)
        if add_core:
            # A document saved without properties gets the part Word itself would write, so
            # the title and language have somewhere to live
            target.writestr(CORE_PART, set_core_properties(EMPTY_CORE, edits.title, edits.language))
    temporary.replace(document)
    return original


def _edit_document(data: bytes, edits: DocumentEdits) -> bytes:
    root = etree.fromstring(data)
    drawings = figures(root)
    for index, description in edits.descriptions.items():
        if index < len(drawings):
            _set_description(drawings[index], description)
    for index in edits.decorative:
        if index < len(drawings):
            node = drawings[index]
            if is_vml(node):
                node.set("alt", "")
            else:
                mark_decorative(node)
                _set_fallback_alt(node, "")
    all_tables = tables(root)
    for index in edits.header_tables:
        if index < len(all_tables):
            _set_header_row(all_tables[index])
    all_paragraphs = paragraphs(root)
    for index, level in edits.headings.items():
        if index < len(all_paragraphs):
            _set_outline_level(all_paragraphs[index], level)
    all_runs = runs(root)
    for index, colour in edits.recolours.items():
        if index < len(all_runs):
            set_run_colour(all_runs[index], colour)
    for index in edits.english_runs:
        if index < len(all_runs) and edits.language:
            language = all_runs[index].find(f"{w('rPr')}/{w('lang')}")
            if language is not None:
                language.set(w("val"), edits.language)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _set_description(node: etree._Element, description: str) -> None:
    # Word's Alt Text field: descr on a drawing, alt on an older VML shape
    if is_vml(node):
        node.set("alt", description)
        return
    node.set("descr", description)
    _set_fallback_alt(node, description)


def _set_fallback_alt(node: etree._Element, description: str) -> None:
    # A drawing with an older VML copy for old versions of Word gets the same text there
    choice = next((a for a in node.iterancestors() if etree.QName(a).localname == "Choice"), None)
    content = choice.getparent() if choice is not None else None
    if content is None or etree.QName(content).namespace != MC_NS:
        return
    fallback = content.find(f"{{{MC_NS}}}Fallback")
    if fallback is None:
        return
    for shape in fallback.iter(f"{{{V_NS}}}shape", f"{{{V_NS}}}group", f"{{{V_NS}}}rect"):
        shape.set("alt", description)


def _register_core_type(data: bytes) -> bytes:
    root = etree.fromstring(data)
    namespace = etree.QName(root).namespace
    override = etree.SubElement(root, f"{{{namespace}}}Override")
    override.set("PartName", f"/{CORE_PART}")
    override.set("ContentType", CORE_TYPE)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _register_core_relationship(data: bytes) -> bytes:
    root = etree.fromstring(data)
    namespace = etree.QName(root).namespace
    taken = {node.get("Id") for node in root}
    number = 1
    while f"rId{number}" in taken:
        number += 1
    relationship = etree.SubElement(root, f"{{{namespace}}}Relationship")
    relationship.set("Id", f"rId{number}")
    relationship.set("Type", CORE_RELATIONSHIP)
    relationship.set("Target", CORE_PART)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _set_header_row(table: etree._Element) -> None:
    # Word's "Repeat as header row": screen readers then read column names with each cell
    row = table.find(w("tr"))
    if row is None:
        return
    properties = row.find(w("trPr"))
    if properties is None:
        properties = etree.Element(w("trPr"))
        exceptions = row.find(w("tblPrEx"))
        row.insert(1 if exceptions is not None and row.index(exceptions) == 0 else 0, properties)
    flag = properties.find(w("tblHeader"))
    if flag is None:
        flag = etree.SubElement(properties, w("tblHeader"))
    flag.attrib.pop(w("val"), None)


def _set_outline_level(paragraph: etree._Element, level: int) -> None:
    # An outline level makes the line a heading for Word's navigation, screen readers and
    # the PDF, without changing its style or look; Word counts levels from 0
    properties = paragraph.find(w("pPr"))
    if properties is None:
        properties = etree.Element(w("pPr"))
        paragraph.insert(0, properties)
    outline = properties.find(w("outlineLvl"))
    if outline is None:
        outline = etree.Element(w("outlineLvl"))
        later = next(
            (child for child in properties if etree.QName(child).localname in AFTER_OUTLINE_LEVEL),
            None,
        )
        if later is None:
            properties.append(outline)
        else:
            later.addprevious(outline)
    outline.set(w("val"), str(max(0, min(8, level - 1))))


def _set_default_language(data: bytes, language: str) -> bytes:
    # The language every run uses unless it says otherwise
    root = etree.fromstring(data)
    defaults = root.find(w("docDefaults"))
    if defaults is None:
        defaults = etree.Element(w("docDefaults"))
        root.insert(0, defaults)
    run_default = defaults.find(w("rPrDefault"))
    if run_default is None:
        run_default = etree.SubElement(defaults, w("rPrDefault"))
        defaults.insert(0, run_default)
    properties = run_default.find(w("rPr"))
    if properties is None:
        properties = etree.SubElement(run_default, w("rPr"))
    element = properties.find(w("lang"))
    if element is None:
        element = etree.Element(w("lang"))
        later = next(
            (child for child in properties if etree.QName(child).localname in AFTER_LANGUAGE), None
        )
        if later is None:
            properties.append(element)
        else:
            later.addprevious(element)
    element.set(w("val"), language)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _write_diff(ir: DocumentIR, edits: DocumentEdits, original: bytes, diff_path: Path) -> None:
    # A readable list of what changed, in document order
    root = etree.fromstring(original) if original else None
    drawings = figures(root) if root is not None else []
    all_paragraphs = paragraphs(root) if root is not None else []
    lines: list[str] = []
    for element in ir.elements.values():
        where = _where(element)
        if element.semantic_type == "figure":
            index = int(element.attrs["figure"])
            if index in edits.decorative:
                lines.append(f"~ {where}: picture marked decorative")
            elif index in edits.descriptions:
                node = drawings[index] if index < len(drawings) else None
                old = ""
                if node is not None:
                    old = (node.get("alt") if is_vml(node) else node.get("descr")) or ""
                lines.extend(
                    difflib.unified_diff(
                        [old.strip()] if old.strip() else [],
                        [edits.descriptions[index]],
                        fromfile=f"{where} {element.subtype or 'figure'} alt text",
                        tofile="updated",
                        lineterm="",
                    )
                )
        elif (
            element.semantic_type == "table"
            and int(element.attrs.get("table", -1)) in edits.header_tables
        ):
            lines.append(f"~ {where}: table's first row marked as its header row")
        elif element.attrs.get("heading_candidate"):
            paragraph = int(element.attrs["paragraph"])
            if paragraph in edits.headings and paragraph < len(all_paragraphs):
                text = " ".join(text_of(all_paragraphs[paragraph]).split())[:80]
                lines.append(
                    f'~ {where}: "{text}" is now a level {edits.headings[paragraph]} heading'
                )
    for fix in contrast_fixes(ir):
        lines.append(
            f"~ text colour #{fix['before']} -> #{fix['after']} so it can be read "
            f"({fix['ratio_before']}:1 -> {fix['ratio_after']}:1): {fix['text'][:80]}"
        )
    if edits.english_runs:
        lines.append(f"~ {len(edits.english_runs)} run(s) of text marked as {edits.language}")
    if edits.default_language:
        lines.append(f"~ document language: {edits.default_language}")
    if (
        edits.title
        and is_default_title(ir.metadata.get("title", ""))
        or (edits.title and not ir.metadata.get("title"))
    ):
        lines.append(f"+ document title: {edits.title}")
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _where(element: Element) -> str:
    return f"page {element.render.pages[0]}" if element.render.pages else "document"
