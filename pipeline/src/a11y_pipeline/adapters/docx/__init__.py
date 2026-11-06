import shutil
import zipfile
from pathlib import Path
from typing import Any

from a11y_pipeline.adapters.base import PreparedDocument, WrittenDocument
from a11y_pipeline.adapters.docx.parser import parse
from a11y_pipeline.adapters.docx.preflight import preflight
from a11y_pipeline.adapters.docx.render import place_elements, render_document_pdf, render_marked
from a11y_pipeline.adapters.docx.writer import write_updated_project
from a11y_pipeline.adapters.pptx.parser import picture_png
from a11y_pipeline.adapters.rendered_words import DrawnWords
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.capabilities.base import FigureDescriptionInput
from a11y_pipeline.evaluation.concepts import build_figure_concepts
from a11y_pipeline.ir.models import DocumentIR, Element, Issue
from a11y_pipeline.render.crop import crop_pdf_bbox
from a11y_pipeline.render.ocr import ocr_words
from a11y_pipeline.render.pixeldiff import PixelCheck, compare_pdf_pixels

__all__ = ["DocxAdapter"]

# OCR that finds fewer words than this has probably missed the picture's text
MIN_OCR_WORDS = 5
# How many lines the outline step sees from the top of the document, to find its title
OPENING_LINES = 6


class DocxAdapter:
    def preflight(self, bundle: Bundle) -> Any:
        # Check that the document opens and is a plain .docx
        return preflight(bundle)

    def build_ir(self, bundle: Bundle, preflight_result: Any) -> DocumentIR:
        # Read paragraphs, drawings, tables and equations into canonical records
        return parse(bundle)

    def summarize(self, ir: DocumentIR) -> str:
        lines = [f"{len(ir.containers)} sections"]
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
        # Render the document once with a marker on each drawing, place every element on its
        # page, and gather what the model sees for each figure and for the outline
        document = bundle.root / bundle.main_file
        rendered, placements = render_marked(document, run_root / "work" / "render")
        if rendered is not None:
            place_elements(ir, rendered, placements)
        media = _media(document, ir)
        drawn_words = DrawnWords(rendered)
        figure_inputs: dict[str, FigureDescriptionInput] = {}
        issues: list[Issue] = []
        for element in ir.elements.values():
            if element.subtype == "document_outline":
                if element.accessibility.status == "needs_description":
                    figure_inputs[element.id] = _outline_input(ir, element)
                continue
            if element.semantic_type != "figure":
                continue
            if element.accessibility.status != "needs_description":
                continue
            image = _figure_image(element, media, rendered, run_root / "crops")
            if image is None:
                issues.append(_no_image_issue(element.id, rendered is None))
                continue
            section_title, other_titles = _section_titles(ir, element)
            nearby = [str(text) for text in element.attrs.get("nearby", [])]
            ir.issues.extend(build_figure_concepts(element, nearby).issues)
            drawn = drawn_words.inside(element)
            if element.attrs.get("media") or element.subtype == "image":
                # A picture's own words come from reading the picture
                element.attrs["contains_picture"] = True
                read = ocr_words(image)
                if read is not None and len(read) >= MIN_OCR_WORDS:
                    drawn.extend(read)
                else:
                    element.attrs["text_unverifiable"] = True
            figure_inputs[element.id] = FigureDescriptionInput(
                element_id=element.id,
                subtype=element.subtype or "other",
                image_png=image,
                source_code=None,
                visible_labels=[],
                slide_title=section_title,
                nearby_text=nearby,
                rendered_text=drawn,
                other_titles=other_titles,
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
        # Write the changes into the document and check the pages look the same. Pages that
        # changed have their table header rows, then their new headings, undone and are
        # written again.
        undone: list[Issue] = []
        changed: set[int] = set()
        for attempt, change in enumerate(("all", "headers", "headings"), start=1):
            if change != "all":
                undone.extend(_undo_on_pages(ir, changed, change))
            if output_root.exists():
                shutil.rmtree(output_root)
            result = write_updated_project(bundle, ir, output_root, diff_path)
            changed = set()
            if original_pdf is not None:
                updated = render_document_pdf(
                    result.project_root / bundle.main_file, verification_root / str(attempt)
                )
                if updated is not None:
                    changed = set(compare_pdf_pixels(original_pdf, updated).different_pages)
            if not changed:
                break
        issues = list(result.issues) + undone
        for page in sorted(changed):
            issues.append(
                Issue(
                    element_id=None,
                    code="visual_change",
                    severity="veto",
                    message=f"The update changed page {page}",
                    details={"page": page, "element_ids": []},
                )
            )
        pages = max((page for c in ir.containers for page in c.rendered_pages), default=0)
        return WrittenDocument(
            project_root=result.project_root,
            diff_path=result.diff_path,
            issues=issues,
            operations=result.operations,
            pixel_check=PixelCheck(
                identical=not changed,
                original_pages=pages,
                candidate_pages=pages,
                different_pages=sorted(changed),
            ),
        )


def _media(document: Path, ir: DocumentIR) -> dict[str, bytes]:
    # The picture file of every figure that is a plain picture
    wanted = {
        element.id: str(element.attrs["media"])
        for element in ir.elements.values()
        if element.semantic_type == "figure" and element.attrs.get("media")
    }
    found: dict[str, bytes] = {}
    with zipfile.ZipFile(document) as package:
        names = set(package.namelist())
        for element_id, part in wanted.items():
            if part in names:
                found[element_id] = package.read(part)
    return found


def _figure_image(
    element: Element, media: dict[str, bytes], rendered: Path | None, crop_root: Path
) -> bytes | None:
    # Pictures use their own pixels; charts, shapes, older formats and equations are cropped
    # from the render
    blob = media.get(element.id)
    if blob is not None:
        png = picture_png(blob)
        if png is not None:
            return png
    if rendered is None or element.render.bbox is None or not element.render.pages:
        return None
    path = crop_root / f"{element.id.replace('/', '-')}.png"
    try:
        crop_pdf_bbox(rendered, element.render.pages[0], element.render.bbox, path)
    except (OSError, ValueError, RuntimeError):
        return None
    return path.read_bytes()


def _section_titles(ir: DocumentIR, element: Element) -> tuple[str | None, list[str]]:
    # The heading of the figure's section, and the two headings before and one after it
    container_id = element.id.split("/", 1)[0]
    titles: list[str] = []
    position = 0
    for index, container in enumerate(ir.containers):
        title = ""
        if container.title_element_id is not None:
            title = str(ir.elements[container.title_element_id].content.get("text", ""))
        titles.append(" ".join(title.split()))
        if container.id == container_id:
            position = index
    own = titles[position] or None
    earlier = [title for title in titles[:position] if title][-2:]
    later = [title for title in titles[position + 1 :] if title][:1]
    return own, [*earlier, *later]


def _outline_input(ir: DocumentIR, outline: Element) -> FigureDescriptionInput:
    # What the outline step sees: each candidate line with how it looks, the existing
    # headings, the opening lines, and words marked as another language
    def line(element_id: str) -> dict[str, Any]:
        element = ir.elements[element_id]
        entry: dict[str, Any] = {
            "id": element_id,
            "text": str(element.content.get("text", ""))[:200],
        }
        if element.semantic_type == "heading":
            entry["level"] = element.attrs.get("level")
        entry.update(element.attrs.get("features", {}))
        if element.render.pages:
            entry["page"] = element.render.pages[0]
        return entry

    ordered = [
        element_id
        for container in ir.containers
        for element_id in container.element_ids
        if element_id in set(outline.attrs["candidates"]) | set(outline.attrs["headings"])
    ]
    opening = [
        str(element.content["text"])[:200]
        for element in ir.elements.values()
        if element.semantic_type in {"paragraph", "heading", "document_title"}
        and element.content.get("text")
    ][:OPENING_LINES]
    return FigureDescriptionInput(
        element_id=outline.id,
        subtype="document_outline",
        image_png=b"",
        source_code=None,
        visible_labels=[],
        slide_title=None,
        nearby_text=opening,
        outline={
            "lines": [line(element_id) for element_id in ordered],
            "foreign_runs": outline.attrs.get("foreign_runs", []),
            "needs_title": bool(outline.attrs.get("needs_title")),
            "language": ir.metadata.get("language_proposed") or ir.metadata.get("language", ""),
        },
    )


def _undo_on_pages(ir: DocumentIR, pages: set[int], change: str) -> list[Issue]:
    # Put back one kind of change on pages whose look changed
    issues: list[Issue] = []
    for element in ir.elements.values():
        if not set(element.render.pages) & pages:
            continue
        if change == "headers" and element.attrs.get("header_row_added"):
            element.attrs["header_row_added"] = False
            element.attrs["first_row_header"] = False
            element.accessibility.status = "needs_review"
            issues.append(
                _undone(element.id, "Marking the table's first row as a header row", element)
            )
        if change == "headings" and element.attrs.get("outline_level"):
            element.attrs["outline_level"] = 0
            element.accessibility.status = "needs_review"
            issues.append(_undone(element.id, "Making this line a heading", element))
    return issues


def _undone(element_id: str, what: str, element: Element) -> Issue:
    page = element.render.pages[0]
    return Issue(
        element_id=element_id,
        code="layout_change_undone",
        severity="warning",
        message=f"{what} changed how page {page} looks, so it was undone. Check it in Word.",
        details={"page": page},
    )


def _no_image_issue(element_id: str, no_renderer: bool) -> Issue:
    reason = (
        "no renderer (LibreOffice) is installed, so drawings that are not plain pictures "
        "cannot be shown to the model"
        if no_renderer
        else "the figure could not be found on the rendered pages"
    )
    return Issue(
        element_id=element_id,
        code="figure_image_unavailable",
        severity="warning",
        message=f"This figure was not described: {reason}.",
    )
