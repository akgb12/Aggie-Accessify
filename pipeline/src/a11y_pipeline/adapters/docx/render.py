import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pikepdf
from lxml import etree

from a11y_pipeline.adapters.docx.ooxml import DOCUMENT_PART, figures, is_vml
from a11y_pipeline.adapters.pptx.render import RENDER_TIMEOUT_SECONDS, find_soffice
from a11y_pipeline.adapters.rendered_words import DrawnWords
from a11y_pipeline.ir.models import DocumentIR, Element

# A tagged export: the tags say where each figure and equation landed on which page
DOCUMENT_PDF_FILTER = (
    'pdf:writer_pdf_Export:{"UseTaggedPDF":{"type":"boolean","value":"true"},'
    '"PDFUACompliance":{"type":"boolean","value":"true"}}'
)
MARKER = "A11YFIG{:05d}"
MARKER_PATTERN = re.compile(r"^A11YFIG(\d{5})$")
# How many of a paragraph's first words identify it on a page
MATCH_WORDS = 6


@dataclass(frozen=True)
class Placement:
    page: int
    bbox: tuple[float, float, float, float] | None


@dataclass
class TaggedPlacements:
    # Where the export put each tagged figure: by marker, and in order for the rest
    by_marker: dict[int, Placement] = field(default_factory=dict)
    unmarked_figures: list[Placement] = field(default_factory=list)
    formulas: list[Placement] = field(default_factory=list)


def render_document_pdf(document: Path, output_dir: Path) -> Path | None:
    # Render a Word document to a tagged PDF with LibreOffice; None when it is not installed
    soffice = find_soffice()
    if soffice is None:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        soffice,
        f"-env:UserInstallation=file://{output_dir / 'lo-profile'}",
        "--headless",
        "--convert-to",
        DOCUMENT_PDF_FILTER,
        "--outdir",
        str(output_dir),
        str(document),
    ]
    try:
        subprocess.run(command, capture_output=True, check=True, timeout=RENDER_TIMEOUT_SECONDS)
    except (subprocess.SubprocessError, OSError):
        return None
    pdf = output_dir / f"{document.stem}.pdf"
    return pdf if pdf.is_file() else None


def render_marked(document: Path, output_dir: Path) -> tuple[Path | None, TaggedPlacements]:
    # Render a copy whose drawings carry numbered markers as their descriptions. Markers do
    # not change the look, so the render doubles as the original's pages.
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="marked-docx-") as scratch:
        marked = Path(scratch) / document.name
        _write_markers(document, marked)
        rendered = render_document_pdf(marked, Path(scratch) / "out")
        if rendered is None:
            return None, TaggedPlacements()
        destination = output_dir / f"{document.stem}.pdf"
        shutil.copy2(rendered, destination)
    return destination, read_placements(destination)


def _write_markers(document: Path, destination: Path) -> None:
    with zipfile.ZipFile(document) as source, zipfile.ZipFile(destination, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == DOCUMENT_PART:
                root = etree.fromstring(data)
                for index, node in enumerate(figures(root)):
                    if not is_vml(node):
                        node.set("descr", MARKER.format(index))
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            target.writestr(item, data, compress_type=item.compress_type)


def read_placements(pdf_path: Path) -> TaggedPlacements:
    # Walk the tags in reading order and note each figure's and equation's page and box
    placements = TaggedPlacements()
    with pikepdf.open(pdf_path) as pdf:
        pages = {page.obj.objgen: number for number, page in enumerate(pdf.pages, start=1)}
        root = pdf.Root.get("/StructTreeRoot")
        if root is None:
            return placements
        pending: list[tuple[Any, int]] = [(root, 1)]
        while pending:
            node, page = pending.pop(0)
            if not isinstance(node, pikepdf.Dictionary):
                continue
            if node.get("/Pg") is not None:
                page = pages.get(node.Pg.objgen, page)
            role = node.get("/S")
            if role in (pikepdf.Name.Figure, pikepdf.Name.Formula):
                placement = Placement(page, _bbox(node))
                marker = MARKER_PATTERN.match(str(node.get("/Alt", "")))
                if role == pikepdf.Name.Formula:
                    placements.formulas.append(placement)
                elif marker:
                    placements.by_marker[int(marker.group(1))] = placement
                else:
                    placements.unmarked_figures.append(placement)
                continue
            kids = node.get("/K")
            children = list(kids) if isinstance(kids, pikepdf.Array) else [kids]
            # Depth first, in order: children go to the front of the queue
            pending[0:0] = [(kid, page) for kid in children if isinstance(kid, pikepdf.Dictionary)]
    return placements


def _bbox(node: pikepdf.Dictionary) -> tuple[float, float, float, float] | None:
    attributes = node.get("/A")
    for attribute in attributes if isinstance(attributes, pikepdf.Array) else [attributes]:
        if isinstance(attribute, pikepdf.Dictionary) and "/BBox" in attribute:
            x0, y0, x1, y1 = (float(value) for value in attribute.BBox)
            return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    return None


def place_elements(ir: DocumentIR, rendered: Path, placements: TaggedPlacements) -> list[str]:
    # Give each element its page (and box where known). Figures come from the tags; equations
    # and older pictures, which carry no marker, are matched in reading order; text is found
    # by its first words, page by page. Returns the ids of figures that could not be placed.
    figures_ = [element for element in ir.elements.values() if element.semantic_type == "figure"]
    for element in figures_:
        if element.attrs.get("vml"):
            continue
        placement = placements.by_marker.get(int(element.attrs["figure"]))
        if placement is not None:
            _set(element, placement, "marker")
    older = sorted(
        (e for e in figures_ if e.attrs.get("vml") and e.subtype != "equation"),
        key=lambda e: e.attrs["order"],
    )
    if len(older) == len(placements.unmarked_figures):
        for element, placement in zip(older, placements.unmarked_figures, strict=True):
            _set(element, placement, "position_match")
    equations = sorted(
        (
            e
            for e in ir.elements.values()
            if e.semantic_type == "formula"
            or (e.semantic_type == "figure" and e.subtype == "equation")
        ),
        key=lambda e: e.attrs["order"],
    )
    if len(equations) == len(placements.formulas):
        for element, placement in zip(equations, placements.formulas, strict=True):
            _set(element, placement, "position_match")
    _place_text(ir, rendered)
    for container in ir.containers:
        pages = sorted(
            {
                page
                for element_id in container.element_ids
                for page in ir.elements[element_id].render.pages
            }
        )
        container.rendered_pages = pages
    return [element.id for element in figures_ if not element.render.pages]


def _set(element: Element, placement: Placement, method: str) -> None:
    element.render.pages = [placement.page]
    element.render.bbox = placement.bbox
    element.render.mapping_method = method  # type: ignore[assignment]
    element.render.confidence = 1.0 if method == "marker" else 0.8


def _place_text(ir: DocumentIR, rendered: Path) -> None:
    # Find each text element's first words on the pages, never going back a page
    words = DrawnWords(rendered)
    with pikepdf.open(rendered) as pdf:
        count = len(pdf.pages)
    page_words: dict[int, tuple[list[Any], tuple[float, float, float, float]]] = {}
    page = 1
    for element in ir.elements.values():
        if element.render.pages:
            page = max(page, element.render.pages[0])
            continue
        text = str(element.content.get("text") or "")
        wanted = _words(text)[:MATCH_WORDS]
        if not wanted:
            continue
        for candidate in range(page, min(count, page + 3) + 1):
            if candidate not in page_words:
                page_words[candidate] = words.page(candidate)
            box = _find(*page_words[candidate], wanted)
            if box is not None:
                element.render.pages = [candidate]
                element.render.bbox = box
                element.render.mapping_method = "position_match"
                element.render.confidence = 0.7
                page = candidate
                break


def _words(text: str) -> list[str]:
    return [word for word in re.findall(r"\w+", text.lower()) if word]


def _find(
    words: list[Any], page_box: tuple[float, float, float, float], wanted: list[str]
) -> tuple[float, float, float, float] | None:
    # The box around the first run of page words that spells the wanted words, in points from
    # the bottom-left corner like every other box
    flat: list[tuple[str, Any]] = []
    for word in words:
        for piece in _words(word.text):
            flat.append((piece, word))
    for start in range(len(flat) - len(wanted) + 1):
        if all(flat[start + offset][0] == wanted[offset] for offset in range(len(wanted))):
            boxes = [flat[start + offset][1].bbox for offset in range(len(wanted))]
            page_x0, page_y0, _, page_y1 = page_box
            left = min(box[0] for box in boxes) + page_x0
            right = max(box[2] for box in boxes) + page_x0
            top = min(box[1] for box in boxes)
            bottom = max(box[3] for box in boxes)
            return (left, page_y1 - bottom + page_y0, right, page_y1 - top + page_y0)
    return None
