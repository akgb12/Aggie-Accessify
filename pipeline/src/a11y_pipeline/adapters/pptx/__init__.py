from pathlib import Path
from typing import Any

from a11y_pipeline.adapters.base import PreparedDocument, WrittenDocument
from a11y_pipeline.adapters.context import figure_context
from a11y_pipeline.adapters.pptx.parser import parse, picture_blobs, picture_png
from a11y_pipeline.adapters.pptx.preflight import preflight
from a11y_pipeline.adapters.pptx.render import render_deck_pdf
from a11y_pipeline.adapters.pptx.writer import verify_updated_deck, write_updated_project
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.capabilities.base import FigureDescriptionInput
from a11y_pipeline.evaluation.concepts import build_figure_concepts
from a11y_pipeline.ir.models import DocumentIR, Issue
from a11y_pipeline.render.crop import crop_pdf_bbox

__all__ = ["PptxAdapter"]


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
        # Gather what the model sees for each figure that needs a description
        deck = bundle.root / bundle.main_file
        rendered = render_deck_pdf(deck, run_root / "work" / "render")
        blobs = picture_blobs(bundle, ir)
        issues: list[Issue] = []
        figure_inputs: dict[str, FigureDescriptionInput] = {}
        for element in ir.elements.values():
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
            figure_inputs[element.id] = FigureDescriptionInput(
                element_id=element.id,
                subtype=element.subtype or "other",
                image_png=image,
                source_code=None,
                visible_labels=labels if element.subtype == "diagram" else [],
                slide_title=slide_title,
                nearby_text=nearby,
                rendered_text=labels if element.subtype == "diagram" else [],
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
        # Write descriptions into the deck and prove nothing visible changed
        result = write_updated_project(bundle, ir, output_root, diff_path)
        check = verify_updated_deck(bundle, result.project_root / bundle.main_file)
        issues = list(result.issues)
        for slide in check.different_pages:
            issues.append(
                Issue(
                    element_id=None,
                    code="visual_change",
                    severity="veto",
                    message=f"The update changed slide {slide}",
                    details={"page": slide, "element_ids": []},
                )
            )
        return WrittenDocument(
            project_root=result.project_root,
            diff_path=result.diff_path,
            issues=issues,
            operations=result.operations,
            pixel_check=check,
        )


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
