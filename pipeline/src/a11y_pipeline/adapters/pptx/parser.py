import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE, PP_PLACEHOLDER
from pptx.shapes.base import BaseShape

from a11y_pipeline.adapters.pptx.structure import (
    Box,
    BoxKind,
    analyze_layout,
    guess_language,
    is_default_title,
    table_has_header_row,
    title_can_move_first,
)
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.ir.ids import IdAllocator, container_id, fingerprint_source
from a11y_pipeline.ir.models import (
    Accessibility,
    Asset,
    Classification,
    Container,
    DocumentIR,
    Element,
    Issue,
    RenderRef,
    SourceRef,
)

EMU_PER_POINT = 12700
DECORATIVE_URI = "{C183D7F6-B498-43B3-948B-1728B52AA6E4}"
DECORATIVE_NS = "http://schemas.microsoft.com/office/drawing/2017/decorative"
TITLE_PLACEHOLDERS = {
    PP_PLACEHOLDER.TITLE,
    PP_PLACEHOLDER.CENTER_TITLE,
    PP_PLACEHOLDER.VERTICAL_TITLE,
}
# Shapes that draw a diagram but carry no text of their own
DRAWING_TYPES = {MSO_SHAPE_TYPE.AUTO_SHAPE, MSO_SHAPE_TYPE.LINE, MSO_SHAPE_TYPE.FREEFORM}
# Alt text that names a file, a camera's numbering or a placeholder says nothing about the
# picture
JUNK_ALT = re.compile(
    r"^(\s*(picture|image|graphic|figure|chart|diagram|photo)\s*\d*\s*"
    r"|.*\.(png|jpe?g|gif|bmp|tiff?|emf|wmf|svg|pdf|eps|heic|webp)"
    r"|\s*(img|dsc|dscn|pxl|screenshot|screen shot)[\s_-]*[\d_ .-]*(at [\d. ]+(am|pm)?)?)$",
    re.IGNORECASE,
)
# Office writes a guess of its own and labels it; it is a draft for the author to check
AUTO_ALT = re.compile(r"description automatically generated", re.IGNORECASE)


@dataclass(frozen=True)
class FigureMedia:
    # What a figure element needs later: its picture bytes, when it is a picture
    element_id: str
    blob: bytes | None


def is_junk_alt(value: str) -> bool:
    text = value.strip()
    return bool(JUNK_ALT.match(text) or AUTO_ALT.search(text))


def parse(bundle: Bundle) -> DocumentIR:
    # Read a .pptx deck into the canonical document model, one container per slide
    deck = bundle.root / bundle.main_file
    presentation = Presentation(str(deck))
    slide_width = presentation.slide_width or 1
    slide_height = presentation.slide_height or 1
    elements: dict[str, Element] = {}
    containers: list[Container] = []
    assets: dict[str, Asset] = {}
    issues: list[Issue] = []
    allocator = IdAllocator()
    texts: list[str] = []
    for number, slide in enumerate(presentation.slides, start=1):
        cid = container_id(number)
        part_name = str(slide.part.partname).lstrip("/")
        geometry = _Geometry(slide_width, slide_height)
        container = Container(id=cid, kind="slide", rendered_pages=[number])
        boxes: list[Box] = []
        shapes: dict[int, BaseShape] = {}
        for z_index, shape in enumerate(slide.shapes):
            if _hidden(shape):
                continue
            shapes[shape.shape_id] = shape
            element = _element_for(shape, cid, number, part_name, z_index, allocator, geometry)
            boxes.append(_box(shape, z_index, element, geometry))
            if element is None:
                continue
            _decorate_flat_group(element)
            elements[element.id] = element
            container.element_ids.append(element.id)
            if element.accessibility.role == "H1" and container.title_element_id is None:
                container.title_element_id = element.id
            if element.content.get("text"):
                texts.append(str(element.content["text"]))
            media = element.attrs.get("media")
            if isinstance(media, str):
                asset = assets.setdefault(media, _asset(media, element.attrs["media_sha256"]))
                asset.used_by.append(element.id)
        slide_context = _SlideContext(
            cid, number, part_name, container, boxes, shapes, elements, allocator, geometry
        )
        _add_diagrams_and_decoration(slide_context)
        _order_title_first(slide_context, issues)
        if container.title_element_id is None:
            _add_title_to_write(slide_context)
        _sort_reading_order(container, elements)
        containers.append(container)
    issues.extend(_duplicate_title_issues(containers, elements))
    core = presentation.core_properties
    title = (core.title or "").strip()
    metadata = {
        # A default title names nothing, so it is treated as missing and replaced
        "title": "" if is_default_title(title) else title,
        "language": (core.language or "").strip(),
        "slide_count": str(len(containers)),
    }
    if not metadata["language"]:
        metadata["language_proposed"] = guess_language(texts) or ""
    return DocumentIR(
        document_id=hashlib.sha256(deck.read_bytes()).hexdigest()[:16],
        source_format="pptx",
        main_file=bundle.main_file,
        metadata={key: value for key, value in metadata.items() if value or key == "title"},
        containers=containers,
        elements=elements,
        assets=assets,
        issues=issues,
    )


class _Geometry:
    # Convert slide EMU to PDF-style points with a bottom-left origin, as the rest of the pipeline
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

    def bbox(self, shape: BaseShape) -> tuple[float, float, float, float] | None:
        top_left = self.top_left(shape)
        return None if top_left is None else self.from_top_left(top_left)

    def top_left(self, shape: BaseShape) -> tuple[float, float, float, float] | None:
        # The shape's box in points as PowerPoint stores it, measured from the top-left corner.
        # Lines can have zero width or height, which still counts as a box.
        left, top, width, height = shape.left, shape.top, shape.width, shape.height
        if None in (left, top, width, height) or (not width and not height):
            return None
        return (
            left / EMU_PER_POINT,
            top / EMU_PER_POINT,
            (left + width) / EMU_PER_POINT,
            (top + height) / EMU_PER_POINT,
        )

    def from_top_left(
        self, box: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        # Flip a top-left box to the bottom-left origin the rest of the pipeline uses
        height = self.height / EMU_PER_POINT
        return (box[0], height - box[3], box[2], height - box[1])


def _hidden(shape: BaseShape) -> bool:
    return shape._element.xpath(".//p:cNvPr[1]/@hidden") == ["1"]


def _cnv_pr(shape: BaseShape) -> Any:
    found = shape._element.xpath(
        "./*[1]/p:cNvPr | ./p:nvPicPr/p:cNvPr | ./p:nvGraphicFramePr/p:cNvPr"
    )
    return found[0] if found else None


def _alt_state(shape: BaseShape) -> tuple[str, bool]:
    # The author's own alt text, and whether they marked the shape decorative
    node = _cnv_pr(shape)
    if node is None:
        return "", False
    description = (node.get("descr") or "").strip()
    decorative = False
    for extension in node.xpath(".//a:ext"):
        if extension.get("uri") == DECORATIVE_URI:
            for child in extension:
                if etree.QName(child).namespace == DECORATIVE_NS and child.get("val") == "1":
                    decorative = True
    return description, decorative


def _element_for(
    shape: BaseShape,
    cid: str,
    slide_number: int,
    part_name: str,
    z_index: int,
    allocator: IdAllocator,
    geometry: _Geometry,
) -> Element | None:
    kind = _classify(shape)
    if kind is None:
        return None
    semantic, subtype = kind
    element_id = allocator.allocate(cid, semantic)
    text = _shape_text(shape)
    attrs: dict[str, Any] = {
        "shape_id": shape.shape_id,
        "shape_name": shape.name,
        "part": part_name,
        "z_index": z_index,
    }
    content: dict[str, Any] = {}
    accessibility = Accessibility()
    fingerprint_text = f"{semantic}|{subtype}|{shape.name}|{text}"
    if semantic == "figure":
        accessibility = _figure_accessibility(shape, attrs, subtype)
        # Text inside a picture is only readable with OCR, which the checks need to know
        attrs["contains_picture"] = subtype == "image" or bool(shape._element.xpath(".//p:pic"))
        labels = _figure_labels(shape)
        if labels:
            attrs["labels"] = labels
        fingerprint_text += "|" + "|".join(labels) + str(attrs.get("media_sha256", ""))
    elif semantic in {"heading", "paragraph"}:
        content["text"] = text
        sizes = [int(value) / 100 for value in shape._element.xpath(".//a:rPr/@sz")]
        if sizes:
            attrs["font_points"] = min(sizes)
        if semantic == "heading":
            accessibility = Accessibility(role="H1")
    elif semantic == "table":
        rows = _table_rows(shape)
        content["rows"] = rows
        content["text"] = " | ".join(" ".join(row) for row in rows)
        attrs["first_row_header"] = bool(shape._element.xpath(".//a:tblPr/@firstRow") == ["1"])
        if not attrs["first_row_header"] and table_has_header_row(rows):
            # Turn on PowerPoint's "Header Row" so screen readers announce column names
            attrs["first_row_header"] = True
            attrs["header_row_added"] = True
        accessibility = Accessibility(
            status="done" if attrs["first_row_header"] else "needs_review"
        )
    render = RenderRef(
        pages=[slide_number],
        bbox=geometry.bbox(shape),
        mapping_method="geometry",
        confidence=1.0,
    )
    return Element(
        id=element_id,
        semantic_type=semantic,
        subtype=subtype,
        content=content,
        attrs=attrs,
        fingerprint=fingerprint_source(fingerprint_text),
        source=SourceRef(
            file=part_name,
            line_start=shape.shape_id,
            line_end=shape.shape_id,
            char_start=z_index,
            char_end=z_index,
            native_type=etree.QName(shape._element).localname,
        ),
        render=render,
        classification=Classification(method="deterministic", confidence=1.0),
        accessibility=accessibility,
    )


def _classify(shape: BaseShape) -> tuple[Any, str | None] | None:
    # Decide what a top-level shape is; plain drawing shapes with no text are not elements
    if shape.is_placeholder:
        placeholder = shape.placeholder_format.type
        if placeholder in TITLE_PLACEHOLDERS:
            # An empty title box shows nothing when presented and names nothing
            return ("heading", None) if _shape_text(shape) else None
        if placeholder == PP_PLACEHOLDER.PICTURE and shape.shape_type == MSO_SHAPE_TYPE.PLACEHOLDER:
            return ("figure", "image") if _has_picture(shape) else None
    kind = shape.shape_type
    if kind in {MSO_SHAPE_TYPE.PICTURE, MSO_SHAPE_TYPE.LINKED_PICTURE}:
        return ("figure", "image")
    if kind == MSO_SHAPE_TYPE.GROUP:
        return ("figure", "diagram")
    if getattr(shape, "has_chart", False) and shape.has_chart:
        return ("figure", "chart")
    if getattr(shape, "has_table", False) and shape.has_table:
        return ("table", None)
    if kind in {MSO_SHAPE_TYPE.EMBEDDED_OLE_OBJECT, MSO_SHAPE_TYPE.LINKED_OLE_OBJECT}:
        return ("figure", "other")
    if getattr(shape, "has_text_frame", False) and shape.has_text_frame and _shape_text(shape):
        return ("paragraph", None)
    return None


def _has_picture(shape: BaseShape) -> bool:
    return bool(shape._element.xpath(".//a:blip"))


def _shape_text(shape: BaseShape) -> str:
    if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
        return "\n".join(
            "".join(run.text for run in paragraph.runs).strip()
            for paragraph in shape.text_frame.paragraphs
            if paragraph.runs
        ).strip()
    return ""


def _table_rows(shape: BaseShape) -> list[list[str]]:
    return [[cell.text.strip() for cell in row.cells] for row in shape.table.rows]


def _figure_labels(shape: BaseShape) -> list[str]:
    # Text drawn inside a group or chart, in reading order, to check a description against
    labels: list[str] = []
    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        for member in _walk(shape.shapes):
            text = _shape_text(member)
            if text:
                labels.extend(line.strip() for line in text.splitlines() if line.strip())
    elif getattr(shape, "has_chart", False) and shape.has_chart:
        chart = shape.chart
        if chart.has_title and chart.chart_title.has_text_frame:
            labels.append(chart.chart_title.text_frame.text.strip())
        try:
            labels.extend(str(name) for name in chart.plots[0].categories)
            labels.extend(series.name for series in chart.plots[0].series)
        except (IndexError, ValueError):
            pass
    seen: set[str] = set()
    unique: list[str] = []
    for label in labels:
        if label and label not in seen:
            seen.add(label)
            unique.append(label)
    return unique


def _walk(shapes: Any) -> Any:
    for member in shapes:
        yield member
        if member.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _walk(member.shapes)


def _figure_accessibility(
    shape: BaseShape, attrs: dict[str, Any], subtype: str | None
) -> Accessibility:
    description, decorative = _alt_state(shape)
    attrs["existing_alt"] = description
    part = _embedded_part(shape, subtype)
    if part is not None:
        attrs["media"] = str(part.partname).lstrip("/")
        attrs["media_sha256"] = hashlib.sha256(part.blob).hexdigest()
    if decorative:
        return Accessibility(decorative=True, status="done", locked=True)
    if description and not is_junk_alt(description):
        return Accessibility(alt_text=description, status="done", locked=True)
    return Accessibility(status="needs_description")


def _embedded_part(shape: BaseShape, subtype: str | None) -> Any | None:
    # The package part holding a picture's pixels; groups and charts have none of their own
    if subtype not in {"image", "other"}:
        return None
    relationships = shape._element.xpath(".//a:blip/@r:embed")
    if not relationships:
        return None
    try:
        return shape.part.related_part(relationships[0])
    except (KeyError, ValueError):
        return None


def picture_png(blob: bytes) -> bytes | None:
    # Re-encode an embedded picture as PNG for the model; None for formats Pillow cannot read
    try:
        with Image.open(io.BytesIO(blob)) as image:
            image.load()
            converted = image.convert("RGBA") if image.mode in {"P", "LA"} else image
            buffer = io.BytesIO()
            converted.save(buffer, format="PNG")
            return buffer.getvalue()
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def _duplicate_title_issues(
    containers: list[Container], elements: dict[str, Element]
) -> list[Issue]:
    # Screen-reader users jump between slides by title, so repeated titles look like one slide.
    # Changing a visible title is the author's call, so this is reported, not fixed.
    by_title: dict[str, list[int]] = {}
    for number, container in enumerate(containers, start=1):
        if container.title_element_id is None:
            continue
        text = " ".join(str(elements[container.title_element_id].content.get("text", "")).split())
        if text:
            by_title.setdefault(text.casefold(), []).append(number)
    issues: list[Issue] = []
    for slides in by_title.values():
        if len(slides) < 2:
            continue
        listed = ", ".join(str(slide) for slide in slides)
        for slide in slides:
            issues.append(
                Issue(
                    element_id=containers[slide - 1].title_element_id,
                    code="duplicate_title",
                    severity="warning",
                    message=(
                        f"Slides {listed} share this title, so in a slide list they look the same. "
                        'Add a word that tells them apart, such as "(continued)" or the example '
                        "shown."
                    ),
                    details={"slides": slides},
                )
            )
    return issues


def _decorate_flat_group(element: Element) -> None:
    # A group with no height or no width is a set of straight lines, such as a divider. It
    # carries no information a description could give, so it is marked decorative.
    bbox = element.render.bbox
    if element.subtype != "diagram" or bbox is None or element.accessibility.locked:
        return
    if bbox[2] - bbox[0] > 0 and bbox[3] - bbox[1] > 0:
        return
    element.accessibility = Accessibility(decorative=True, status="done")
    element.attrs["mark_decorative"] = True


@dataclass
class _SlideContext:
    cid: str
    number: int
    part_name: str
    container: Container
    boxes: list[Box]
    shapes: dict[int, BaseShape]
    elements: dict[str, Element]
    allocator: IdAllocator
    geometry: "_Geometry"


def _box(shape: BaseShape, z_index: int, element: Element | None, geometry: "_Geometry") -> Box:
    # Where a shape sits and what kind of thing it is, for layout reasoning
    kind: BoxKind = "other"
    if element is not None:
        if element.semantic_type == "heading":
            kind = "title"
        elif element.semantic_type == "table":
            kind = "table"
        elif element.semantic_type == "paragraph":
            kind = "body" if shape.is_placeholder else "label"
        elif element.subtype == "image":
            kind = "picture"
        elif element.subtype == "diagram" and not element.accessibility.locked:
            # A group the author described or marked decorative stays as it is
            kind = "group" if not element.accessibility.decorative else "other"
    elif etree.QName(shape._element).localname in {"sp", "cxnSp"} and not shape.is_placeholder:
        kind = "drawing"
    text = str(element.content.get("text", "")) if element is not None else ""
    return Box(shape.shape_id, z_index, kind, geometry.top_left(shape), text)


def _add_diagrams_and_decoration(slide: _SlideContext) -> None:
    # Loose drawn shapes that touch become one described diagram; lone ones are decoration
    layout = analyze_layout(slide.boxes)
    for cluster in layout.diagrams:
        element = _diagram_element(slide, cluster)
        if element is not None:
            slide.elements[element.id] = element
            slide.container.element_ids.append(element.id)
    decorative: list[int] = []
    for box in layout.decorative:
        description, already = _alt_state(slide.shapes[box.shape_id])
        if not already and not description:
            decorative.append(box.shape_id)
    slide.container.attrs["decorative_shape_ids"] = decorative


def _diagram_element(slide: _SlideContext, cluster: list[Box]) -> Element | None:
    # One figure for a diagram drawn from loose shapes. Its description is stored on one of
    # its drawn shapes (the carrier) and the other drawn shapes are marked decorative, so a
    # screen reader announces the diagram once. Text labels stay readable.
    groups = [box for box in cluster if box.kind == "group"]
    drawings = [box for box in cluster if box.kind == "drawing"] + groups
    states = {box.shape_id: _alt_state(slide.shapes[box.shape_id]) for box in drawings}
    open_drawings = [box for box in drawings if not states[box.shape_id][1]]
    if not open_drawings:
        return None
    described = [
        box
        for box in open_drawings
        if states[box.shape_id][0] and not is_junk_alt(states[box.shape_id][0])
    ]
    carrier = described[0] if described else open_drawings[0]
    existing = states[carrier.shape_id][0]
    labels = _cluster_labels(cluster)
    # Groups joined into this diagram are no longer figures of their own
    for group in groups:
        absorbed = _element_for_shape_id(slide, group.shape_id)
        if absorbed is None:
            continue
        for label in absorbed.attrs.get("labels", []):
            if label not in labels:
                labels.append(label)
        del slide.elements[absorbed.id]
        slide.container.element_ids.remove(absorbed.id)
    shape = slide.shapes[carrier.shape_id]
    attrs: dict[str, Any] = {
        "shape_id": carrier.shape_id,
        "shape_name": shape.name,
        "part": slide.part_name,
        "z_index": carrier.z,
        "cluster_shape_ids": [box.shape_id for box in cluster],
        "decorative_shape_ids": [
            box.shape_id
            for box in open_drawings
            if box is not carrier and not states[box.shape_id][0]
        ],
        "existing_alt": existing,
    }
    if labels:
        attrs["labels"] = labels
    accessibility = Accessibility(status="needs_description")
    if described:
        accessibility = Accessibility(alt_text=existing, status="done", locked=True)
    element_id = slide.allocator.allocate(slide.cid, "figure")
    ids = ",".join(str(box.shape_id) for box in cluster)
    return Element(
        id=element_id,
        semantic_type="figure",
        subtype="diagram",
        attrs=attrs,
        fingerprint=fingerprint_source(f"cluster|{ids}|{'|'.join(labels)}"),
        source=SourceRef(
            file=slide.part_name,
            line_start=carrier.shape_id,
            line_end=carrier.shape_id,
            char_start=carrier.z,
            char_end=carrier.z,
            native_type="shape_cluster",
        ),
        render=RenderRef(
            pages=[slide.number],
            bbox=slide.geometry.from_top_left(_union(cluster)),
            mapping_method="geometry",
            confidence=1.0,
        ),
        classification=Classification(
            method="deterministic", confidence=0.8, evidence=["touching drawn shapes"]
        ),
        accessibility=accessibility,
    )


def _element_for_shape_id(slide: _SlideContext, shape_id: int) -> Element | None:
    for element_id in slide.container.element_ids:
        element = slide.elements[element_id]
        if element.attrs.get("shape_id") == shape_id:
            return element
    return None


def _cluster_labels(cluster: list[Box]) -> list[str]:
    # The words written on a diagram, top to bottom and left to right
    labels: list[str] = []
    placed = sorted(
        (box for box in cluster if box.kind == "label" and box.bbox),
        key=lambda box: (round(box.bbox[1]), box.bbox[0]) if box.bbox else (0, 0),
    )
    for box in placed:
        for line in box.text.splitlines():
            if line.strip() and line.strip() not in labels:
                labels.append(line.strip())
    return labels


def _union(cluster: list[Box]) -> tuple[float, float, float, float]:
    boxes = [box.bbox for box in cluster if box.bbox]
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _order_title_first(slide: _SlideContext, issues: list[Issue]) -> None:
    # A screen reader reads shapes in stacking order, so the title must come first. Moving it
    # is only done when no earlier shape overlaps it, which keeps the slide looking the same.
    container = slide.container
    if container.title_element_id is None:
        return
    title = slide.elements[container.title_element_id]
    title_box = next(box for box in slide.boxes if box.shape_id == title.attrs["shape_id"])
    skipped = set(container.attrs.get("decorative_shape_ids", []))
    for element in slide.elements.values():
        if element.id.startswith(f"{slide.cid}/"):
            skipped.update(element.attrs.get("decorative_shape_ids", []))
    readable_before = [
        box
        for box in slide.boxes
        if box.z < title_box.z
        and box.shape_id not in skipped
        and not _alt_state(slide.shapes[box.shape_id])[1]
    ]
    if not readable_before:
        container.attrs["title_first"] = True
        return
    if title_can_move_first(slide.boxes, title_box):
        container.attrs["title_first"] = True
        container.attrs["move_title_first"] = True
        return
    container.attrs["title_first"] = False
    issues.append(
        Issue(
            element_id=title.id,
            code="title_not_first",
            severity="warning",
            message=(
                f"Slide {slide.number}'s title is not read first, and moving it automatically "
                "would change how overlapping shapes are stacked. In PowerPoint, open "
                "Arrange > Reading Order and drag the title to the top."
            ),
            details={"slide": slide.number},
        )
    )


def _add_title_to_write(slide: _SlideContext) -> None:
    # A slide without a title gets an empty title for the model to write. It is saved as a
    # title placeholder placed just above the slide, as Microsoft suggests, so nothing moves.
    element_id = slide.allocator.allocate(slide.cid, "heading")
    slide.elements[element_id] = Element(
        id=element_id,
        semantic_type="heading",
        content={"text": ""},
        attrs={"part": slide.part_name, "z_index": -1, "added_title": True},
        fingerprint=fingerprint_source(f"added-title|{slide.part_name}"),
        source=SourceRef(
            file=slide.part_name,
            line_start=0,
            line_end=0,
            char_start=-1,
            char_end=-1,
            native_type="added_title",
        ),
        render=RenderRef(pages=[slide.number], mapping_method="geometry", confidence=1.0),
        accessibility=Accessibility(role="H1", status="needs_description"),
    )
    slide.container.element_ids.insert(0, element_id)
    slide.container.title_element_id = element_id
    slide.container.attrs["title_first"] = True


def _sort_reading_order(container: Container, elements: dict[str, Element]) -> None:
    # Elements in the order a screen reader meets them in the updated deck
    def position(element_id: str) -> tuple[int, int]:
        element = elements[element_id]
        is_title = element_id == container.title_element_id
        if is_title and container.attrs.get("title_first"):
            return (0, 0)
        return (1, int(element.attrs.get("z_index", 0)))

    container.element_ids.sort(key=position)


def _asset(media: str, sha256: str) -> Asset:
    return Asset(
        id=f"asset_{hashlib.sha256(media.encode()).hexdigest()[:8]}",
        referenced_as=media,
        resolved_path=media,
        status="found",
        origin="embedded",
        sha256=sha256,
        used_by=[],
    )


def picture_blobs(bundle: Bundle, ir: DocumentIR) -> dict[str, bytes]:
    # Read the picture bytes of every figure that is itself a picture
    presentation = Presentation(str(bundle.root / bundle.main_file))
    wanted = {
        (element.attrs["part"], element.attrs["shape_id"]): element
        for element in ir.elements.values()
        if element.semantic_type == "figure" and element.attrs.get("media")
    }
    blobs: dict[str, bytes] = {}
    for slide in presentation.slides:
        part_name = str(slide.part.partname).lstrip("/")
        for shape in slide.shapes:
            element = wanted.get((part_name, shape.shape_id))
            if element is None:
                continue
            part = _embedded_part(shape, element.subtype)
            if part is not None:
                blobs[element.id] = part.blob
    return blobs


__all__ = ["Path", "FigureMedia", "is_junk_alt", "parse", "picture_blobs", "picture_png"]
