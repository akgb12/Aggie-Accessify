import shutil
from pathlib import Path
from typing import Any

from PIL import Image

from a11y_pipeline.adapters.base import PreparedDocument, WrittenDocument
from a11y_pipeline.adapters.context import figure_context
from a11y_pipeline.adapters.pptx.parser import parse, picture_blobs, picture_png
from a11y_pipeline.adapters.pptx.preflight import preflight
from a11y_pipeline.adapters.pptx.render import render_deck_pdf
from a11y_pipeline.adapters.pptx.structure import touches
from a11y_pipeline.adapters.pptx.writer import verify_updated_deck, write_updated_project
from a11y_pipeline.adapters.rendered_words import DrawnWords
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.capabilities.base import FigureDescriptionInput
from a11y_pipeline.evaluation.concepts import build_figure_concepts
from a11y_pipeline.evaluation.contrast import LARGE_TEXT_POINTS, required_ratio, text_contrast
from a11y_pipeline.ir.models import DocumentIR, Issue
from a11y_pipeline.render.crop import crop_pdf_bbox
from a11y_pipeline.render.ocr import ocr_words
from a11y_pipeline.render.pages import page_size_points, render_page, render_pages
from a11y_pipeline.render.pixeldiff import PixelCheck, compare_pdf_pixels

__all__ = ["PptxAdapter"]

# A whole slide shown to the model to propose a title; low resolution is enough to read it
SLIDE_IMAGE_DPI = 60
# Resolution for measuring text contrast; high enough that small text has solid glyph cores
CONTRAST_DPI = 110
# OCR that finds fewer words than this has probably missed the picture's text
MIN_OCR_WORDS = 5


class PptxAdapter:
    def preflight(self, bundle: Bundle) -> Any:
        # Check that the deck opens and is a plain .pptx
        return preflight(bundle)

    def build_ir(self, bundle: Bundle, preflight_result: Any) -> DocumentIR:
        # Read slides and shapes into canonical records
        return parse(bundle)

    def summarize(self, ir: DocumentIR) -> str:
        # One line per element, like the Beamer summary
        lines = [f"{len(ir.containers)} slides"]
        for element in ir.elements.values():
            text = str(element.content.get("text", ""))[:60]
            lines.append(
                f"{element.id} {element.semantic_type} {element.accessibility.status} {text}"
            )
        return "\n".join(lines) + "\n"

    def prepare(
        self,
        bundle: Bundle,
        ir: DocumentIR,
        run_root: Path,
        timeout_seconds: int,
    ) -> PreparedDocument:
        # Gather what the model sees for each figure that needs a description, and for each
        # slide that needs a title
        deck = bundle.root / bundle.main_file
        rendered = render_deck_pdf(deck, run_root / "work" / "render")
        blobs = picture_blobs(bundle, ir)
        issues: list[Issue] = []
        figure_inputs: dict[str, FigureDescriptionInput] = {}
        if rendered is None:
            issues.extend(_keep_table_headers_unchanged(ir))
        else:
            issues.extend(_contrast_issues(ir, rendered, run_root / "work" / "contrast"))
        drawn_words = DrawnWords(rendered)
        for element in ir.elements.values():
            if element.semantic_type == "heading" and element.attrs.get("added_title"):
                figure_inputs[element.id] = _title_input(
                    ir, element, blobs, rendered, run_root / "slides"
                )
                continue
            if element.semantic_type != "figure":
                continue
            if element.accessibility.status != "needs_description":
                continue
            image = _figure_image(element, blobs, rendered, run_root / "crops")
            if image is None:
                issues.append(_no_image_issue(element.id, rendered is None))
                continue
            slide_title, nearby = figure_context(ir, element)
            labels = [str(label) for label in element.attrs.get("labels", [])]
            if element.subtype == "diagram":
                concepts = build_figure_concepts(element, nearby, labels, [])
                element.fidelity.required_concepts = list(concepts.required)
                element.fidelity.excluded_concepts = list(concepts.excluded)
                ir.issues.extend(concepts.issues)
            else:
                ir.issues.extend(build_figure_concepts(element, nearby).issues)
            drawn = list(labels) + drawn_words.inside(element)
            if _contains_picture(ir, element):
                # The loop transcribes the text of every figure holding a picture
                element.attrs["contains_picture"] = True
                read = ocr_words(image)
                if read is not None and len(read) >= MIN_OCR_WORDS:
                    drawn.extend(read)
                else:
                    # Text in the picture could not be read, so quotes of it cannot be checked
                    element.attrs["text_unverifiable"] = True
            figure_inputs[element.id] = FigureDescriptionInput(
                element_id=element.id,
                subtype=element.subtype or "other",
                image_png=image,
                source_code=None,
                visible_labels=labels if element.subtype == "diagram" else [],
                slide_title=slide_title,
                nearby_text=nearby,
                rendered_text=drawn,
                other_titles=_neighbour_titles(ir, element.render.pages[0]),
            )
        ir.issues.extend(issues)
        return PreparedDocument(
            ir=ir,
            figure_inputs=figure_inputs,
            original_pdf=rendered,
            marked_pdf=None,
        )

    def write_back(
        self,
        bundle: Bundle,
        ir: DocumentIR,
        output_root: Path,
        diff_path: Path,
        verification_root: Path,
        original_pdf: Path | None,
        timeout_seconds: int,
    ) -> WrittenDocument:
        # Write the changes into the deck and prove nothing visible changed: the XML check
        # always, and a render comparison when LibreOffice is installed. A slide whose look
        # changed has its layout changes (header rows, title moves) undone and is written again.
        undone: list[Issue] = []
        undo: set[str] = set()
        attempts = ("all", "headers", "titles")
        for attempt, change in enumerate(attempts, start=1):
            if change != "all":
                undone.extend(_undo_layout_changes(ir, undo, change))
            if output_root.exists():
                shutil.rmtree(output_root)
            result = write_updated_project(bundle, ir, output_root, diff_path)
            deck = result.project_root / bundle.main_file
            changed = set(verify_updated_deck(bundle, deck).different_pages)
            if original_pdf is not None:
                changed |= _rendered_changes(deck, original_pdf, verification_root / str(attempt))
            undo = {
                part
                for part, slide in result.slide_parts.items()
                if slide in changed and part in result.layout_parts
            }
            if not undo:
                break
        issues = list(result.issues) + undone
        for slide in sorted(changed):
            issues.append(
                Issue(
                    element_id=None,
                    code="visual_change",
                    severity="veto",
                    message=f"The update changed slide {slide}",
                    details={"page": slide, "element_ids": []},
                )
            )
        slides = len(ir.containers)
        return WrittenDocument(
            project_root=result.project_root,
            diff_path=result.diff_path,
            issues=issues,
            operations=result.operations,
            pixel_check=PixelCheck(
                identical=not changed,
                original_pages=slides,
                candidate_pages=slides,
                different_pages=sorted(changed),
            ),
        )


def _contains_picture(ir: DocumentIR, element: Any) -> bool:
    # A picture, a group holding one, or a diagram drawn over one
    if element.attrs.get("contains_picture"):
        return True
    bbox = element.render.bbox
    if bbox is None:
        return False
    for other in ir.elements.values():
        if other.id == element.id or other.subtype != "image" or other.render.bbox is None:
            continue
        if other.render.pages == element.render.pages and touches(other.render.bbox, bbox):
            return True
    return False


def _rendered_changes(deck: Path, original_pdf: Path, work: Path) -> set[int]:
    # Slides that look different once the updated deck is rendered
    updated_pdf = render_deck_pdf(deck, work)
    if updated_pdf is None:
        return set()
    return set(compare_pdf_pixels(original_pdf, updated_pdf).different_pages)


def _undo_layout_changes(ir: DocumentIR, parts: set[str], change: str) -> list[Issue]:
    # Put back one kind of layout change on slides whose look changed: table header rows
    # first, since they restyle a table, then title moves
    issues: list[Issue] = []
    for container in ir.containers:
        part = _part_of(ir, container.element_ids)
        if part not in parts or not container.rendered_pages:
            continue
        slide = container.rendered_pages[0]
        undone = False
        if change == "headers":
            for element_id in container.element_ids:
                element = ir.elements[element_id]
                if element.attrs.get("header_row_added"):
                    element.attrs["header_row_added"] = False
                    element.attrs["first_row_header"] = False
                    element.accessibility.status = "needs_review"
                    undone = True
            what = "Turning on the table header row"
            advice = "In PowerPoint, tick Table Design > Header Row if the new style is fine."
        else:
            if container.attrs.get("move_title_first"):
                container.attrs["move_title_first"] = False
                container.attrs["title_first"] = False
                undone = True
            what = "Moving the title to the start of the reading order"
            advice = "In PowerPoint, open Arrange > Reading Order and drag the title to the top."
        if undone:
            issues.append(
                Issue(
                    element_id=None,
                    code="layout_change_undone",
                    severity="warning",
                    message=f"{what} changed how slide {slide} looks, so it was undone. {advice}",
                    details={"slide": slide, "change": change},
                )
            )
    return issues


def _part_of(ir: DocumentIR, element_ids: list[str]) -> str | None:
    for element_id in element_ids:
        part = ir.elements[element_id].attrs.get("part")
        if part:
            return str(part)
    return None


def _contrast_issues(ir: DocumentIR, rendered: Path, work: Path) -> list[Issue]:
    # Report text whose colour is too close to its background, measured on the rendered slide.
    # Report only: changing a professor's colours is their call.
    try:
        pages = render_pages(rendered, work, dpi=CONTRAST_DPI)
        sizes = page_size_points(rendered)
    except (OSError, RuntimeError, ValueError):
        return []
    issues: list[Issue] = []
    for element in ir.elements.values():
        bbox = element.render.bbox
        if element.semantic_type not in {"heading", "paragraph"} or bbox is None:
            continue
        if not element.content.get("text") or not element.render.pages:
            continue
        page = element.render.pages[0]
        if page > len(pages):
            continue
        width, height = sizes[page - 1]
        with Image.open(pages[page - 1]) as image:
            scale = image.width / width
            box = (
                max(0, int(bbox[0] * scale)),
                max(0, int((height - bbox[3]) * scale)),
                min(image.width, int(bbox[2] * scale)),
                min(image.height, int((height - bbox[1]) * scale)),
            )
            if box[2] - box[0] < 4 or box[3] - box[1] < 4:
                continue
            ratio = text_contrast(image.crop(box))
        points = element.attrs.get("font_points")
        if points is None and element.semantic_type == "heading":
            points = LARGE_TEXT_POINTS
        needed = required_ratio(points)
        if ratio is not None and ratio < needed:
            issues.append(
                Issue(
                    element_id=element.id,
                    code="low_contrast",
                    severity="warning",
                    message=(
                        f"This text's colour is close to its background (about {ratio:.1f}:1; "
                        f"at least {needed:g}:1 is needed). Use a darker or lighter colour."
                    ),
                    details={"ratio": round(ratio, 2), "required": needed, "slide": page},
                )
            )
    return issues


def _keep_table_headers_unchanged(ir: DocumentIR) -> list[Issue]:
    # Without a renderer a header row's restyling cannot be checked, so tables are left as is
    issues: list[Issue] = []
    for element in ir.elements.values():
        if element.attrs.get("header_row_added"):
            element.attrs["header_row_added"] = False
            element.attrs["first_row_header"] = False
            element.accessibility.status = "needs_review"
            issues.append(
                Issue(
                    element_id=element.id,
                    code="table_header_unchecked",
                    severity="warning",
                    message=(
                        "This table's first row looks like a header, but it was not marked "
                        "because no renderer is installed to check that its look stays the same. "
                        "In PowerPoint, tick Table Design > Header Row."
                    ),
                )
            )
    return issues


def _title_input(
    ir: DocumentIR,
    element: Any,
    blobs: dict[str, bytes],
    rendered: Path | None,
    slide_root: Path,
) -> FigureDescriptionInput:
    # What the model sees to propose a title: the slide itself, its words, and nearby titles
    number = element.render.pages[0]
    image = b""
    if rendered is not None:
        path = slide_root / f"slide-{number:03d}.png"
        try:
            render_page(rendered, number, path, dpi=SLIDE_IMAGE_DPI)
            image = path.read_bytes()
        except (OSError, ValueError, RuntimeError):
            image = b""
    container = ir.containers[number - 1]
    if not image:
        pictures = [
            blobs[element_id] for element_id in container.element_ids if element_id in blobs
        ]
        if len(pictures) == 1:
            image = picture_png(pictures[0]) or b""
    words = [
        str(ir.elements[element_id].content.get("text", "")).strip()
        for element_id in container.element_ids
        if ir.elements[element_id].content.get("text")
    ]
    words.extend(
        str(label)
        for element_id in container.element_ids
        for label in ir.elements[element_id].attrs.get("labels", [])
    )
    return FigureDescriptionInput(
        element_id=element.id,
        subtype="slide_title",
        image_png=image,
        source_code=None,
        visible_labels=[],
        slide_title=None,
        nearby_text=[word for word in words if word],
        other_titles=_neighbour_titles(ir, number),
    )


def _neighbour_titles(ir: DocumentIR, number: int) -> list[str]:
    # The nearest real titles before and after the slide, however far away, so a proposed
    # title names the lesson's topic and stays unique within a run of untitled slides
    def title(index: int) -> str:
        container = ir.containers[index]
        if container.title_element_id is None:
            return ""
        return " ".join(
            str(ir.elements[container.title_element_id].content.get("text", "")).split()
        )

    before = [title(index) for index in range(number - 2, -1, -1)]
    after = [title(index) for index in range(number, len(ir.containers))]
    earlier = [text for text in before if text][:2]
    later = [text for text in after if text][:1]
    return list(reversed(earlier)) + later


def _figure_image(
    element: Any,
    blobs: dict[str, bytes],
    rendered: Path | None,
    crop_root: Path,
) -> bytes | None:
    # Pictures use their own pixels; groups, charts and objects are cropped from the render
    blob = blobs.get(element.id)
    if blob is not None:
        png = picture_png(blob)
        if png is not None:
            return png
    if rendered is None or element.render.bbox is None or not element.render.pages:
        return None
    path = crop_root / f"{element.id.replace('/', '-')}.png"
    try:
        crop_pdf_bbox(rendered, element.render.pages[-1], element.render.bbox, path)
    except (OSError, ValueError, RuntimeError):
        return None
    return path.read_bytes()


def _no_image_issue(element_id: str, no_renderer: bool) -> Issue:
    reason = (
        "no slide renderer (LibreOffice) is installed, so shapes that are not plain pictures "
        "cannot be shown to the model"
        if no_renderer
        else "the figure could not be rendered"
    )
    return Issue(
        element_id=element_id,
        code="figure_image_unavailable",
        severity="warning",
        message=f"This figure was not described: {reason}.",
    )
