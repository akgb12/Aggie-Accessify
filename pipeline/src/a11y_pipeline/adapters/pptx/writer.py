import difflib
import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree
from pptx import Presentation

from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.ir.models import DocumentIR, Element, Issue
from a11y_pipeline.render.pixeldiff import PixelCheck
from a11y_pipeline.synthesis.plan import OutputOperation

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
CORE_PATH = "docProps/core.xml"
DC_NS = "http://purl.org/dc/elements/1.1/"
CP_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC_TERMS_NS = "http://purl.org/dc/terms/"


@dataclass(frozen=True)
class PptxWriterResult:
    project_root: Path
    diff_path: Path
    issues: list[Issue]
    operations: list[OutputOperation]


def write_updated_project(
    bundle: Bundle,
    ir: DocumentIR,
    output_root: Path,
    diff_path: Path,
) -> PptxWriterResult:
    # Copy the project and write descriptions into the deck, leaving everything else byte for byte
    if output_root.exists():
        raise FileExistsError("Updated project destination already exists")
    output_root.mkdir(parents=True)
    for relative in bundle.files:
        target = output_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundle.root / relative, target)
    operations: list[OutputOperation] = []
    issues: list[Issue] = []
    by_part: dict[str, dict[int, str]] = {}
    for element in ir.elements.values():
        if element.semantic_type != "figure":
            continue
        description = _description(element)
        if description is None:
            if not element.accessibility.locked and not element.accessibility.decorative:
                issues.append(
                    Issue(
                        element_id=element.id,
                        code="alt_missing",
                        severity="error",
                        message="Figure was not updated because alternative text is missing",
                        details={"status": element.accessibility.status},
                    )
                )
            continue
        by_part.setdefault(str(element.attrs["part"]), {})[int(element.attrs["shape_id"])] = (
            description
        )
        operations.append(
            OutputOperation(
                output="updated_source",
                operation="set_shape_alt_text",
                element_id=element.id,
                source_file=str(element.attrs["part"]),
                details={"shape_id": element.attrs["shape_id"]},
            )
        )
    deck = output_root / bundle.main_file
    title = _title_to_write(ir)
    replaced = _rewrite_package(deck, by_part, title)
    for part, written in replaced.items():
        missing = set(by_part.get(part, {})) - written
        for shape_id in sorted(missing):
            issues.append(
                Issue(
                    element_id=_element_for_shape(ir, part, shape_id),
                    code="alt_not_written",
                    severity="error",
                    message=f"Shape {shape_id} was not found in {part}; its text was not saved",
                    details={"part": part, "shape_id": shape_id},
                )
            )
    if title is not None:
        operations.append(
            OutputOperation(
                output="updated_source",
                operation="set_document_title",
                source_file=CORE_PATH,
                details={"title": title},
            )
        )
    _write_diff(bundle, deck, by_part, title, diff_path)
    return PptxWriterResult(
        project_root=output_root,
        diff_path=diff_path,
        issues=issues,
        operations=operations,
    )


def _description(element: Element) -> str | None:
    # One line of text for the shape's alt-text field: the short description, then the long one
    accessibility = element.accessibility
    if accessibility.locked or accessibility.decorative:
        return None
    if accessibility.status in {"missing_asset", "failed"}:
        return None
    alt = " ".join((accessibility.alt_text or "").split())
    if not alt:
        return None
    extended = " ".join((accessibility.extended_description or "").split())
    return f"{alt} {extended}" if extended else alt


def _title_to_write(ir: DocumentIR) -> str | None:
    # An empty document title is filled from the first slide title; an existing one is kept
    if ir.metadata.get("title", "").strip():
        return None
    for container in ir.containers:
        if container.title_element_id is None:
            continue
        text = str(ir.elements[container.title_element_id].content.get("text", ""))
        text = " ".join(text.split())
        if text:
            return text
    return None


def _element_for_shape(ir: DocumentIR, part: str, shape_id: int) -> str | None:
    for element in ir.elements.values():
        if element.attrs.get("part") == part and element.attrs.get("shape_id") == shape_id:
            return element.id
    return None


def _rewrite_package(
    deck: Path,
    by_part: dict[str, dict[int, str]],
    title: str | None,
) -> dict[str, set[int]]:
    # Rewrite only the slide parts that change; every other part is copied unchanged
    written: dict[str, set[int]] = {part: set() for part in by_part}
    temporary = deck.with_suffix(".pptx.tmp")
    with zipfile.ZipFile(deck) as source, zipfile.ZipFile(temporary, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename in by_part:
                data = _set_descriptions(data, by_part[item.filename], written[item.filename])
            elif item.filename == CORE_PATH and title is not None:
                data = _set_title(data, title)
            target.writestr(item, data, compress_type=item.compress_type)
    temporary.replace(deck)
    return written


def _set_descriptions(data: bytes, wanted: dict[int, str], written: set[int]) -> bytes:
    # Set descr on the top-level shapes whose ids are in `wanted`
    root = etree.fromstring(data)
    for properties in root.iterfind(f".//{{{P_NS}}}spTree/*/*/{{{P_NS}}}cNvPr"):
        shape_id = properties.get("id")
        if shape_id is not None and shape_id.isdigit() and int(shape_id) in wanted:
            if int(shape_id) in written:
                continue
            properties.set("descr", wanted[int(shape_id)])
            written.add(int(shape_id))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _set_title(data: bytes, title: str) -> bytes:
    root = etree.fromstring(data)
    node = root.find(f"{{{DC_NS}}}title")
    if node is None:
        node = etree.SubElement(root, f"{{{DC_NS}}}title")
    if (node.text or "").strip():
        return data
    node.text = title
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _write_diff(
    bundle: Bundle,
    deck: Path,
    by_part: dict[str, dict[int, str]],
    title: str | None,
    diff_path: Path,
) -> None:
    # A readable list of what changed; the deck itself is a binary file
    before = Presentation(str(bundle.root / bundle.main_file))
    lines: list[str] = []
    for slide in before.slides:
        part = str(slide.part.partname).lstrip("/")
        for shape in slide.shapes:
            if shape.shape_id in by_part.get(part, {}):
                old = (shape._element.xpath("./*[1]/p:cNvPr")[0].get("descr") or "").strip()
                lines.extend(
                    difflib.unified_diff(
                        [old] if old else [],
                        [by_part[part][shape.shape_id]],
                        fromfile=f"{part} shape {shape.shape_id} ({shape.name}) alt text",
                        tofile="updated",
                        lineterm="",
                    )
                )
    if title is not None:
        lines.append(f"+ document title: {title}")
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def verify_updated_deck(bundle: Bundle, deck: Path) -> PixelCheck:
    # Prove the update changed nothing visible: same slides, text, geometry and picture bytes
    original = _fingerprints(bundle.root / bundle.main_file)
    updated = _fingerprints(deck)
    different = [
        index + 1
        for index in range(max(len(original), len(updated)))
        if index >= len(original) or index >= len(updated) or original[index] != updated[index]
    ]
    return PixelCheck(
        identical=not different,
        original_pages=len(original),
        candidate_pages=len(updated),
        different_pages=different,
    )


def _fingerprints(deck: Path) -> list[str]:
    presentation = Presentation(str(deck))
    values: list[str] = []
    for slide in presentation.slides:
        parts: list[str] = []
        for shape in slide.shapes:
            node = etree.fromstring(etree.tostring(shape._element))
            for properties in node.iterfind(f".//{{{P_NS}}}cNvPr"):
                properties.attrib.pop("descr", None)
            parts.append(etree.tostring(node, method="c14n").decode("utf-8"))
            for blip in shape._element.xpath(".//a:blip/@r:embed"):
                try:
                    parts.append(hashlib.sha256(shape.part.related_part(blip).blob).hexdigest())
                except (KeyError, ValueError):
                    parts.append("missing-media")
        values.append(hashlib.sha256(json.dumps(parts).encode("utf-8")).hexdigest())
    return values
