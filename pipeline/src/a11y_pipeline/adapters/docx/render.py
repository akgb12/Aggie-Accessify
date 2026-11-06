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
    # Find each text element's first words on the pages, never going back a page and, on a
    # page, starting after the last line found, so repeated lines land on their own copies
    words = DrawnWords(rendered)
    with pikepdf.open(rendered) as pdf:
        count = len(pdf.pages)
    page_words: dict[int, list[tuple[str, Any]]] = {}
    page = 1
    cursor = 0
    for element in ir.elements.values():
        if element.render.pages:
            if element.render.pages[0] > page:
                page, cursor = element.render.pages[0], 0
            continue
        text = str(element.content.get("text") or "")
        wanted = _words(text)
        if not wanted:
            continue
        # Later pages first, then this page from its top, for text drawn out of order
        tries = [(page, cursor)] + [(c, 0) for c in range(page + 1, min(count, page + 3) + 1)]
        tries.append((page, 0))
        for candidate, start in tries:
            if candidate not in page_words:
                page_words[candidate] = _flat_words(*words.page(candidate))
            found = _find(page_words[candidate], wanted, start)
            if found is not None:
                box, end = found
                element.render.pages = [candidate]
                element.render.bbox = box
                element.render.mapping_method = "position_match"
                element.render.confidence = 0.7
                if candidate != page or end > cursor:
                    page, cursor = candidate, end
                break


def _words(text: str) -> list[str]:
    return [word for word in re.findall(r"\w+", text.lower()) if word]


def _flat_words(
    words: list[Any], page_box: tuple[float, float, float, float]
) -> list[tuple[str, Any]]:
    # Each word piece on the page with its box in points from the bottom-left corner
    page_x0, page_y0, _, page_y1 = page_box
    flat: list[tuple[str, Any]] = []
    for word in words:
        x0, top, x1, bottom = word.bbox
        box = (x0 + page_x0, page_y1 - bottom + page_y0, x1 + page_x0, page_y1 - top + page_y0)
        for piece in _words(word.text):
            flat.append((piece, box))
    return flat


def _find(
    flat: list[tuple[str, Any]], wanted: list[str], start: int
) -> tuple[tuple[float, float, float, float], int] | None:
    # The first place from start whose words spell the wanted text's first words. The box
    # grows over as much of the rest of the text as follows on the page. Returns the box and
    # where the first words end, so a table's own cells are still found after it.
    head = wanted[:MATCH_WORDS]
    for index in range(start, len(flat) - len(head) + 1):
        if any(flat[index + offset][0] != head[offset] for offset in range(len(head))):
            continue
        end = index + len(head)
        span = end
        while (
            span < len(flat)
            and span - index < len(wanted)
            and flat[span][0] == wanted[span - index]
        ):
            span += 1
        boxes = [box for _, box in flat[index:span]]
        bbox = (
            min(box[0] for box in boxes),
            min(box[1] for box in boxes),
            max(box[2] for box in boxes),
            max(box[3] for box in boxes),
        )
        return bbox, end
    return None
