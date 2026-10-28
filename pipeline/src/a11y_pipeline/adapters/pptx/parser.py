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
# Alt text that names a file or a placeholder says nothing about the picture
JUNK_ALT = re.compile(
    r"^(\s*(picture|image|graphic|figure|chart|diagram|photo)\s*\d*\s*"
    r"|.*\.(png|jpe?g|gif|bmp|tiff?|emf|wmf|svg))$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FigureMedia:
    # What a figure element needs later: its picture bytes, when it is a picture
    element_id: str
    blob: bytes | None


def is_junk_alt(value: str) -> bool:
    return bool(JUNK_ALT.match(value.strip()))


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
    titles: list[str] = []
    for number, slide in enumerate(presentation.slides, start=1):
        cid = container_id(number)
        part_name = str(slide.part.partname).lstrip("/")
        geometry = _Geometry(slide_width, slide_height)
        container = Container(id=cid, kind="slide", rendered_pages=[number])
        title_text = ""
        drawing_ids: list[int] = []
        for z_index, shape in enumerate(slide.shapes):
            if _hidden(shape):
                continue
            element = _element_for(shape, cid, number, part_name, z_index, allocator, geometry)
            if element is None:
                if shape.shape_type in DRAWING_TYPES:
                    drawing_ids.append(shape.shape_id)
                continue
            elements[element.id] = element
            container.element_ids.append(element.id)
            if element.accessibility.role == "H1" and container.title_element_id is None:
                container.title_element_id = element.id
                title_text = str(element.content.get("text", "")).strip()
            media = element.attrs.get("media")
            if isinstance(media, str):
                asset = assets.setdefault(media, _asset(media, element.attrs["media_sha256"]))
                asset.used_by.append(element.id)
        if _is_ungrouped_diagram(slide, drawing_ids):
            issues.append(_ungrouped_diagram_issue(cid, number, len(drawing_ids)))
        if not title_text:
            issues.append(
                Issue(
                    element_id=None,
                    code="slide_missing_title",
                    severity="warning",
                    message=f"Slide {number} has no title, so screen-reader users cannot find it.",
                    details={"slide": number},
                )
            )
        titles.append(title_text)
        containers.append(container)
    core = presentation.core_properties
    metadata = {
        "title": (core.title or "").strip(),
        "language": (core.language or "").strip(),
        "slide_count": str(len(containers)),
    }
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
        left, top, width, height = shape.left, shape.top, shape.width, shape.height
        if None in (left, top, width, height) or not width or not height:
            return None
        x0 = left / EMU_PER_POINT
        x1 = (left + width) / EMU_PER_POINT
        y1 = (self.height - top) / EMU_PER_POINT
        y0 = (self.height - top - height) / EMU_PER_POINT
        return (x0, y0, x1, y1)


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
        labels = _figure_labels(shape)
        if labels:
            attrs["labels"] = labels
        fingerprint_text += "|" + "|".join(labels) + str(attrs.get("media_sha256", ""))
    elif semantic in {"heading", "paragraph"}:
        content["text"] = text
        if semantic == "heading":
            accessibility = Accessibility(role="H1")
    elif semantic == "table":
        rows = _table_rows(shape)
        content["rows"] = rows
        content["text"] = " | ".join(" ".join(row) for row in rows)
        attrs["first_row_header"] = bool(shape._element.xpath(".//a:tblPr/@firstRow") == ["1"])
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
            return ("heading", None)
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


def _is_ungrouped_diagram(slide: Any, drawing_ids: list[int]) -> bool:
    return len(drawing_ids) >= 4


def _ungrouped_diagram_issue(cid: str, number: int, count: int) -> Issue:
    return Issue(
        element_id=None,
        code="ungrouped_diagram",
        severity="warning",
        message=(
            f"Slide {number} draws a diagram from {count} separate shapes. Select them and group "
            "them (Ctrl+G) so one description can cover the whole diagram."
        ),
        details={"slide": number, "container": cid, "shapes": count},
    )


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
