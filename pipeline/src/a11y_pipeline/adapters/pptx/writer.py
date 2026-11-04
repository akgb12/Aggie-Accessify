import difflib
import hashlib
import json
import shutil
import zipfile
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree
from pptx import Presentation

from a11y_pipeline.adapters.pptx.structure import touches
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.ir.models import DocumentIR, Element, Issue
from a11y_pipeline.render.pixeldiff import PixelCheck
from a11y_pipeline.synthesis.plan import OutputOperation

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
CORE_PATH = "docProps/core.xml"
DC_NS = "http://purl.org/dc/elements/1.1/"
CP_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC_TERMS_NS = "http://purl.org/dc/terms/"
DECORATIVE_URI = "{C183D7F6-B498-43B3-948B-1728B52AA6E4}"
DECORATIVE_NS = "http://schemas.microsoft.com/office/drawing/2017/decorative"
EMU_PER_POINT = 12700
# The name given to a title this tool adds, so the check below can tell it from the author's
ADDED_TITLE_NAME = "Title (added for accessibility)"
# Added titles sit one inch above the top edge of the slide, where they are never shown
ADDED_TITLE_OFFSET_EMU = 914400
ADDED_TITLE_HEIGHT_EMU = 685800
# Children of a shape tree that are not shapes
TREE_PROPERTIES = {"nvGrpSpPr", "grpSpPr", "extLst"}


@dataclass
class SlideEdits:
    # Everything written into one slide part
    descriptions: dict[int, str] = field(default_factory=dict)
    decorative: set[int] = field(default_factory=set)
    header_tables: set[int] = field(default_factory=set)
    move_first: int | None = None
    new_title: str | None = None

    def changes_layout(self) -> bool:
        # Header rows restyle a table and moving shapes changes stacking; both are checked
        return bool(self.header_tables) or self.move_first is not None


@dataclass(frozen=True)
class PptxWriterResult:
    project_root: Path
    diff_path: Path
    issues: list[Issue]
    operations: list[OutputOperation]
    slide_parts: dict[str, int]
    layout_parts: set[str]


def write_updated_project(
    bundle: Bundle,
    ir: DocumentIR,
    output_root: Path,
    diff_path: Path,
) -> PptxWriterResult:
    # Copy the project and write the accessibility changes into the deck; every other part of
    # the package is copied byte for byte
    if output_root.exists():
        raise FileExistsError("Updated project destination already exists")
    output_root.mkdir(parents=True)
    for relative in bundle.files:
        target = output_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundle.root / relative, target)
    edits, operations, issues = _collect_edits(ir)
    deck = output_root / bundle.main_file
    title = _title_to_write(ir)
    language = _language_to_write(ir)
    written = _rewrite_package(deck, edits, title, language)
    for part, shape_ids in written.items():
        for shape_id in sorted(set(edits[part].descriptions) - shape_ids):
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
    if language is not None:
        operations.append(
            OutputOperation(
                output="updated_source",
                operation="set_document_language",
                source_file=CORE_PATH,
                details={"language": language},
            )
        )
    _write_diff(bundle, edits, title, language, diff_path)
    return PptxWriterResult(
        project_root=output_root,
        diff_path=diff_path,
        issues=issues,
        operations=operations,
        slide_parts=_slide_parts(ir),
        layout_parts={part for part, edit in edits.items() if edit.changes_layout()},
    )


def _collect_edits(
    ir: DocumentIR,
) -> tuple[dict[str, SlideEdits], list[OutputOperation], list[Issue]]:
    # Turn the final document into per-slide edits
    edits: dict[str, SlideEdits] = {}
    operations: list[OutputOperation] = []
    issues: list[Issue] = []

    def slide(part: str) -> SlideEdits:
        return edits.setdefault(part, SlideEdits())

    def operation(name: str, part: str, element_id: str | None, **details: object) -> None:
        operations.append(
            OutputOperation(
                output="updated_source",
                operation=name,
                element_id=element_id,
                source_file=part,
                details=dict(details),
            )
        )

    for element in ir.elements.values():
        part = str(element.attrs.get("part", ""))
        if element.semantic_type == "figure" and _decorative_now(element):
            slide(part).decorative.add(int(element.attrs["shape_id"]))
            operation(
                "mark_shapes_decorative", part, element.id, shape_ids=[element.attrs["shape_id"]]
            )
        elif element.semantic_type == "figure":
            description = _description(element)
            if description is None:
                if not element.accessibility.locked and not element.accessibility.decorative:
                    issues.append(_alt_missing(element))
                continue
            shape_id = int(element.attrs["shape_id"])
            slide(part).descriptions[shape_id] = description
            operation("set_shape_alt_text", part, element.id, shape_id=shape_id)
            for member in element.attrs.get("decorative_shape_ids", []):
                slide(part).decorative.add(int(member))
            if element.attrs.get("decorative_shape_ids"):
                operation(
                    "mark_diagram_parts_decorative",
                    part,
                    element.id,
                    shape_ids=list(element.attrs["decorative_shape_ids"]),
                )
        elif element.semantic_type == "table" and element.attrs.get("header_row_added"):
            slide(part).header_tables.add(int(element.attrs["shape_id"]))
            operation("set_table_header_row", part, element.id, shape_id=element.attrs["shape_id"])
        elif element.semantic_type == "heading" and element.attrs.get("added_title"):
            text = " ".join(str(element.content.get("text", "")).split())
            if text:
                slide(part).new_title = text
                operation("add_slide_title", part, element.id, title=text)
            else:
                issues.append(
                    Issue(
                        element_id=element.id,
                        code="slide_missing_title",
                        severity="warning",
                        message=(
                            f"Slide {element.render.pages[0]} has no title, so screen-reader "
                            "users cannot find it."
                        ),
                        details={"slide": element.render.pages[0]},
                    )
                )
    for container in ir.containers:
        part = _container_part(ir, container.element_ids)
        decorative = [int(value) for value in container.attrs.get("decorative_shape_ids", [])]
        if decorative and part:
            slide(part).decorative.update(decorative)
            operation("mark_shapes_decorative", part, None, shape_ids=decorative)
        if container.attrs.get("move_title_first") and container.title_element_id and part:
            title = ir.elements[container.title_element_id]
            slide(part).move_first = int(title.attrs["shape_id"])
            operation("move_title_first", part, title.id, shape_id=title.attrs["shape_id"])
    return edits, operations, issues


def _decorative_now(element: Element) -> bool:
    # A flat group of lines, or a picture the describer judged to carry no information. A
    # picture the author described keeps the author's text.
    if element.attrs.get("mark_decorative"):
        return True
    accessibility = element.accessibility
    return (
        accessibility.decorative_suggested
        and not accessibility.locked
        and accessibility.status == "model_generated"
    )


def _alt_missing(element: Element) -> Issue:
    return Issue(
        element_id=element.id,
        code="alt_missing",
        severity="error",
        message="Figure was not updated because alternative text is missing",
        details={"status": element.accessibility.status},
    )


def _container_part(ir: DocumentIR, element_ids: list[str]) -> str | None:
    for element_id in element_ids:
        part = ir.elements[element_id].attrs.get("part")
        if part:
            return str(part)
    return None


def _slide_parts(ir: DocumentIR) -> dict[str, int]:
    # Slide part name for every slide number
    parts: dict[str, int] = {}
    for container in ir.containers:
        part = _container_part(ir, container.element_ids)
        if part and container.rendered_pages:
            parts[part] = container.rendered_pages[0]
    return parts


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


def _language_to_write(ir: DocumentIR) -> str | None:
    if ir.metadata.get("language", "").strip():
        return None
    return ir.metadata.get("language_proposed") or None


def _element_for_shape(ir: DocumentIR, part: str, shape_id: int) -> str | None:
    for element in ir.elements.values():
        if element.attrs.get("part") == part and element.attrs.get("shape_id") == shape_id:
            return element.id
    return None


def _rewrite_package(
    deck: Path,
    edits: dict[str, SlideEdits],
    title: str | None,
    language: str | None,
) -> dict[str, set[int]]:
    # Rewrite only the slide parts that change; every other part is copied unchanged
    written: dict[str, set[int]] = {part: set() for part in edits}
    size = _slide_size(deck)
    temporary = deck.with_suffix(".pptx.tmp")
    with zipfile.ZipFile(deck) as source, zipfile.ZipFile(temporary, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename in edits:
                data = _edit_slide(data, edits[item.filename], written[item.filename], size)
            elif item.filename == CORE_PATH and (title is not None or language is not None):
                data = _set_core_properties(data, title, language)
            target.writestr(item, data, compress_type=item.compress_type)
    temporary.replace(deck)
    return written


def _slide_size(deck: Path) -> tuple[int, int]:
    presentation = Presentation(str(deck))
    return int(presentation.slide_width or 0), int(presentation.slide_height or 0)


def _edit_slide(
    data: bytes,
    edits: SlideEdits,
    written: set[int],
    size: tuple[int, int],
) -> bytes:
    # Apply one slide's edits to its XML
    root = etree.fromstring(data)
    tree = root.find(f".//{{{P_NS}}}cSld/{{{P_NS}}}spTree")
    if tree is None:
        return data
    shapes = _top_level_shapes(tree)
    by_id: dict[int, etree._Element] = {}
    for shape in shapes:
        properties = _shape_properties(shape)
        shape_id = properties.get("id") if properties is not None else None
        if shape_id is not None and shape_id.isdigit():
            by_id[int(shape_id)] = shape
    for shape_id, description in edits.descriptions.items():
        shape = by_id.get(shape_id)
        properties = _shape_properties(shape) if shape is not None else None
        if properties is not None:
            properties.set("descr", description)
            written.add(shape_id)
    for shape_id in edits.decorative:
        shape = by_id.get(shape_id)
        properties = _shape_properties(shape) if shape is not None else None
        if properties is not None:
            _mark_decorative(properties)
    for shape_id in edits.header_tables:
        shape = by_id.get(shape_id)
        if shape is None:
            continue
        for table_properties in shape.iter(f"{{{A_NS}}}tblPr"):
            table_properties.set("firstRow", "1")
    first_position = list(tree).index(shapes[0]) if shapes else len(tree)
    if edits.move_first is not None and edits.move_first in by_id:
        moving = by_id[edits.move_first]
        tree.remove(moving)
        tree.insert(first_position, moving)
    if edits.new_title:
        # Shape ids are unique across the whole slide, including shapes inside groups
        ids = [int(value) for value in tree.xpath(".//p:cNvPr/@id", namespaces={"p": P_NS})]
        next_id = max((value for value in ids if value >= 0), default=1) + 1
        tree.insert(first_position, _added_title(next_id, edits.new_title, size[0]))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _top_level_shapes(tree: etree._Element) -> list[etree._Element]:
    return [
        child
        for child in tree
        if isinstance(child.tag, str) and etree.QName(child).localname not in TREE_PROPERTIES
    ]


def _shape_properties(shape: etree._Element) -> etree._Element | None:
    # The cNvPr element that holds a shape's id, name, alt text and decorative flag
    if len(shape) == 0:
        return None
    first = shape[0]
    return first.find(f"{{{P_NS}}}cNvPr")


def _mark_decorative(properties: etree._Element) -> None:
    # PowerPoint's "Mark as decorative": an extension on the shape's properties
    for extension in properties.iter(f"{{{A_NS}}}ext"):
        if extension.get("uri") == DECORATIVE_URI:
            return
    extensions = properties.find(f"{{{A_NS}}}extLst")
    if extensions is None:
        extensions = etree.SubElement(properties, f"{{{A_NS}}}extLst")
    extension = etree.SubElement(extensions, f"{{{A_NS}}}ext", uri=DECORATIVE_URI)
    marker = etree.SubElement(
        extension, f"{{{DECORATIVE_NS}}}decorative", nsmap={"adec": DECORATIVE_NS}
    )
    marker.set("val", "1")
    properties.attrib.pop("descr", None)


def _added_title(shape_id: int, text: str, slide_width: int) -> etree._Element:
    # A title placeholder placed above the slide, so screen readers find it and nobody sees it
    p = f"{{{P_NS}}}"
    a = f"{{{A_NS}}}"
    shape = etree.Element(f"{p}sp", nsmap={"p": P_NS, "a": A_NS})
    non_visual = etree.SubElement(shape, f"{p}nvSpPr")
    etree.SubElement(non_visual, f"{p}cNvPr", id=str(shape_id), name=ADDED_TITLE_NAME)
    locks = etree.SubElement(non_visual, f"{p}cNvSpPr")
    etree.SubElement(locks, f"{a}spLocks", noGrp="1")
    placeholder = etree.SubElement(non_visual, f"{p}nvPr")
    etree.SubElement(placeholder, f"{p}ph", type="title")
    properties = etree.SubElement(shape, f"{p}spPr")
    transform = etree.SubElement(properties, f"{a}xfrm")
    etree.SubElement(transform, f"{a}off", x="0", y=str(-ADDED_TITLE_OFFSET_EMU))
    etree.SubElement(
        transform, f"{a}ext", cx=str(max(slide_width, 1)), cy=str(ADDED_TITLE_HEIGHT_EMU)
    )
    body = etree.SubElement(shape, f"{p}txBody")
    etree.SubElement(body, f"{a}bodyPr")
    etree.SubElement(body, f"{a}lstStyle")
    paragraph = etree.SubElement(body, f"{a}p")
    run = etree.SubElement(paragraph, f"{a}r")
    etree.SubElement(run, f"{a}rPr", lang="en-US", dirty="0")
    etree.SubElement(run, f"{a}t").text = text
    return shape


def _set_core_properties(data: bytes, title: str | None, language: str | None) -> bytes:
    root = etree.fromstring(data)
    for name, value in (("title", title), ("language", language)):
        if value is None:
            continue
        node = root.find(f"{{{DC_NS}}}{name}")
        if node is None:
            node = etree.SubElement(root, f"{{{DC_NS}}}{name}")
        if not (node.text or "").strip():
            node.text = value
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _write_diff(
    bundle: Bundle,
    edits: dict[str, SlideEdits],
    title: str | None,
    language: str | None,
    diff_path: Path,
) -> None:
    # A readable list of what changed; the deck itself is a binary file
    before = Presentation(str(bundle.root / bundle.main_file))
    lines: list[str] = []
    for number, slide in enumerate(before.slides, start=1):
        part = str(slide.part.partname).lstrip("/")
        edit = edits.get(part)
        if edit is None:
            continue
        names = {shape.shape_id: shape.name for shape in slide.shapes}
        if edit.new_title:
            lines.append(f"+ slide {number}: added title, kept above the slide: {edit.new_title}")
        if edit.move_first is not None:
            lines.append(f"~ slide {number}: title moved to the start of the reading order")
        for shape_id in sorted(edit.header_tables):
            lines.append(f"~ slide {number}: {names.get(shape_id, shape_id)} first row is a header")
        if edit.decorative:
            marked = ", ".join(str(names.get(shape, shape)) for shape in sorted(edit.decorative))
            lines.append(f"~ slide {number}: marked decorative: {marked}")
        for shape in slide.shapes:
            if shape.shape_id in edit.descriptions:
                old = (shape._element.xpath("./*[1]/p:cNvPr")[0].get("descr") or "").strip()
                lines.extend(
                    difflib.unified_diff(
                        [old] if old else [],
                        [edit.descriptions[shape.shape_id]],
                        fromfile=f"slide {number} {shape.name} alt text",
                        tofile="updated",
                        lineterm="",
                    )
                )
    if title is not None:
        lines.append(f"+ document title: {title}")
    if language is not None:
        lines.append(f"+ document language: {language}")
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def verify_updated_deck(bundle: Bundle, deck: Path) -> PixelCheck:
    # Prove from the XML that the update changed nothing a viewer sees. Every original shape
    # must be unchanged apart from alt text, the decorative flag and the table header switch;
    # the only new shape allowed is an added title above the slide; and shapes that overlap
    # must keep their stacking order.
    original = _slide_shapes(bundle.root / bundle.main_file)
    updated = _slide_shapes(deck)
    different: list[int] = []
    for index in range(max(len(original), len(updated))):
        if index >= len(original) or index >= len(updated):
            different.append(index + 1)
        elif not _same_look(original[index], updated[index]):
            different.append(index + 1)
    return PixelCheck(
        identical=not different,
        original_pages=len(original),
        candidate_pages=len(updated),
        different_pages=different,
    )


@dataclass(frozen=True)
class _Shape:
    shape_id: int
    name: str
    fingerprint: str
    bbox: tuple[float, float, float, float] | None


def _slide_shapes(deck: Path) -> list[list[_Shape]]:
    presentation = Presentation(str(deck))
    slides: list[list[_Shape]] = []
    for slide in presentation.slides:
        shapes: list[_Shape] = []
        for shape in slide.shapes:
            node = deepcopy(shape._element)
            for properties in node.iter(f"{{{P_NS}}}cNvPr"):
                properties.attrib.pop("descr", None)
                for extension in list(properties.iter(f"{{{A_NS}}}ext")):
                    if extension.get("uri") == DECORATIVE_URI:
                        extension.getparent().remove(extension)
                for extensions in list(properties.iter(f"{{{A_NS}}}extLst")):
                    if len(extensions) == 0:
                        properties.remove(extensions)
            for table_properties in node.iter(f"{{{A_NS}}}tblPr"):
                table_properties.attrib.pop("firstRow", None)
            parts = [etree.tostring(node, method="c14n").decode("utf-8")]
            for blip in shape._element.xpath(".//a:blip/@r:embed"):
                try:
                    parts.append(hashlib.sha256(shape.part.related_part(blip).blob).hexdigest())
                except (KeyError, ValueError):
                    parts.append("missing-media")
            shapes.append(
                _Shape(
                    shape_id=shape.shape_id,
                    name=shape.name,
                    fingerprint=hashlib.sha256(json.dumps(parts).encode("utf-8")).hexdigest(),
                    bbox=_bbox(shape),
                )
            )
        slides.append(shapes)
    return slides


def _bbox(shape: object) -> tuple[float, float, float, float] | None:
    left = getattr(shape, "left", None)
    top = getattr(shape, "top", None)
    width = getattr(shape, "width", None)
    height = getattr(shape, "height", None)
    if None in (left, top, width, height):
        return None
    return (left, top, left + width, top + height)


def _same_look(original: list[_Shape], updated: list[_Shape]) -> bool:
    before = {shape.shape_id: shape for shape in original}
    after = {shape.shape_id: shape for shape in updated}
    for shape_id, shape in after.items():
        if shape_id not in before and shape.name != ADDED_TITLE_NAME:
            return False
        if shape_id not in before and shape.bbox is not None and shape.bbox[3] > 0:
            return False
    for shape_id, shape in before.items():
        if shape_id not in after or after[shape_id].fingerprint != shape.fingerprint:
            return False
    position = {shape.shape_id: index for index, shape in enumerate(updated)}
    for index, first in enumerate(original):
        for second in original[index + 1 :]:
            if position[first.shape_id] < position[second.shape_id]:
                continue
            # A shape without a box, or one that touches, may be drawn over the other
            if first.bbox is None or second.bbox is None or touches(first.bbox, second.bbox):
                return False
    return True
