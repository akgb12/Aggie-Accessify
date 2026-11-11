import json
import re
import shutil
from pathlib import Path
from typing import Any

from a11y_pipeline.adapters.base import PreparedDocument, SourceAdapter, WrittenDocument
from a11y_pipeline.adapters.context import figure_context
from a11y_pipeline.adapters.docx import DocxAdapter
from a11y_pipeline.adapters.pptx import PptxAdapter
from a11y_pipeline.adapters.tex_beamer.aux_reader import apply_aux_mapping, read_aux
from a11y_pipeline.adapters.tex_beamer.builder import build, summarize
from a11y_pipeline.adapters.tex_beamer.colours import (
    ColourEdit,
    apply_colour_edits_to,
    plan_colour_edits,
)
from a11y_pipeline.adapters.tex_beamer.compile import (
    CompileError,
    CompileResult,
    compile_project,
    errors_beyond,
    tex_version,
)
from a11y_pipeline.adapters.tex_beamer.parser import parse
from a11y_pipeline.adapters.tex_beamer.preflight import preflight
from a11y_pipeline.adapters.tex_beamer.recovery import compile_marked_copy
from a11y_pipeline.adapters.tex_beamer.working_copy import create_working_copies
from a11y_pipeline.adapters.tex_beamer.writer import verify_updated_project, write_updated_project
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.capabilities.base import FigureDescriptionInput
from a11y_pipeline.evaluation.concepts import (
    build_figure_concepts,
    infer_tikz_labels,
)
from a11y_pipeline.evaluation.hidden_labels import detect_figure_hidden_labels
from a11y_pipeline.evaluation.page_contrast import FaintWord, faint_words
from a11y_pipeline.ir.models import DocumentIR, Element, Issue
from a11y_pipeline.render.crop import crop_pdf_bbox
from a11y_pipeline.render.pixeldiff import compare_pdf_pixels, visual_change_issues


class TexBeamerAdapter:
    def preflight(self, bundle: Bundle) -> Any:
        # Check a Beamer project before model work
        return preflight(bundle)

    def build_ir(self, bundle: Bundle, preflight_result: Any) -> DocumentIR:
        # Parse Beamer source into canonical records
        return build(parse(bundle), preflight_result)

    def summarize(self, ir: DocumentIR) -> str:
        # Summarize parsed Beamer elements
        return summarize(ir)

    def prepare(
        self,
        bundle: Bundle,
        ir: DocumentIR,
        run_root: Path,
        timeout_seconds: int,
    ) -> PreparedDocument:
        # Compile map and prepare Beamer figure inputs
        working_ir = ir.model_copy(deep=True)
        copies = create_working_copies(bundle, working_ir, run_root / "work")
        # Compile the user's own source the way Overleaf does: keep going past recoverable errors
        original = compile_project(copies.original, bundle.main_file, timeout_seconds, strict=False)
        # Faint text colours are fixed in every copy compiled from here on. The original with
        # only those fixes is how the output should look, so it stands in for the original in
        # every later comparison.
        colour_edits, reference = _fix_colours(
            bundle, copies.original, run_root / "work" / "expected", original, timeout_seconds
        )

        def compile_marked(root: Path) -> CompileResult:
            apply_colour_edits_to(root, colour_edits)
            return _compile_marked(root, bundle.main_file, timeout_seconds, original)

        marked_copy = compile_marked_copy(
            bundle,
            working_ir,
            copies.marked,
            run_root / "injection_table.json",
            compile_marked,
        )
        marked = marked_copy.compiled
        mapped = apply_aux_mapping(marked_copy.ir, read_aux(marked.aux_path))
        engine = tex_version()
        if engine:
            mapped.metadata["render_engine"] = engine
        if original.errors:
            mapped.issues.append(_tolerated_errors_issue(original.errors, original.error_messages))
        if colour_edits:
            mapped.metadata["contrast_fixes"] = json.dumps([edit.record() for edit in colour_edits])
        mapped.issues.extend(_contrast_issues(colour_edits, reference, run_root / "work"))
        pixel_check = compare_pdf_pixels(reference, marked.pdf_path)
        mapped.issues.extend(visual_change_issues(mapped, pixel_check))
        figure_inputs = _figure_inputs(mapped, reference, run_root / "crops")
        return PreparedDocument(
            ir=mapped,
            figure_inputs=figure_inputs,
            original_pdf=reference,
            marked_pdf=marked.pdf_path,
        )

    def write_back(
        self,
        bundle: Bundle,
        ir: DocumentIR,
        output_root: Path,
        diff_path: Path,
        verification_root: Path,
        original_pdf: Path,
        timeout_seconds: int,
    ) -> WrittenDocument:
        # Write and verify safe Beamer source updates
        result = write_updated_project(bundle, ir, output_root, diff_path)
        shutil.copytree(result.project_root, verification_root)
        verification = verify_updated_project(
            original_pdf,
            verification_root,
            bundle.main_file,
            timeout_seconds=timeout_seconds,
        )
        issues = list(result.issues)
        issues.extend(visual_change_issues(ir, verification.pixel_check))
        return WrittenDocument(
            project_root=result.project_root,
            diff_path=result.diff_path,
            issues=issues,
            operations=result.operations,
            pixel_check=verification.pixel_check,
        )


def _fix_colours(
    bundle: Bundle,
    original_copy: Path,
    expected_root: Path,
    original: CompileResult,
    timeout_seconds: int,
) -> tuple[list[ColourEdit], Path]:
    # Plan the colour fixes and compile the original with only them; a fix that breaks the
    # compile is dropped, and the original stays the reference
    sources = {
        name: (bundle.root / name).read_text(encoding="utf-8")
        for name in bundle.files
        if name.lower().endswith(".tex")
    }
    edits = plan_colour_edits(sources, bundle.main_file)
    if not edits:
        return [], original.pdf_path
    shutil.copytree(original_copy, expected_root)
    apply_colour_edits_to(expected_root, edits)
    try:
        expected = compile_project(expected_root, bundle.main_file, timeout_seconds, strict=False)
    except CompileError:
        return [], original.pdf_path
    if errors_beyond(original.error_messages, expected.error_messages):
        return [], original.pdf_path
    return edits, expected.pdf_path


def _contrast_issues(edits: list[ColourEdit], reference: Path, work: Path) -> list[Issue]:
    # Say which colours were fixed, and measure the pages as they will now look for any text
    # still too faint, such as text drawn in a TikZ picture or by a theme
    issues: list[Issue] = []
    for edit in edits:
        what = (
            "Items shown before their turn are now dimmed less"
            if edit.kind == "covered_items"
            else "A text colour too faint for its background now uses a readable shade of itself"
        )
        issues.append(
            Issue(
                element_id=None,
                code="contrast_fixed",
                severity="info",
                message=(
                    f"{what} ({edit.file} line {edit.line}): #{edit.before} became "
                    f"#{edit.after}, {edit.ratio_before}:1 became {edit.ratio_after}:1."
                ),
                details={"file": edit.file, "line": edit.line, "kind": edit.kind},
            )
        )
    by_page: dict[int, list[FaintWord]] = {}
    for word in faint_words(reference, work / "contrast"):
        by_page.setdefault(word.page, []).append(word)
    for page, words in sorted(by_page.items()):
        sample = " ".join(word.text for word in words[:6])
        lowest = min(words, key=lambda word: word.ratio)
        issues.append(
            Issue(
                element_id=None,
                code="low_contrast",
                severity="warning",
                message=(
                    f'Text on page {page} is hard to read on its background ("{sample}", '
                    f"about {lowest.ratio:.1f}:1; at least {lowest.required:g}:1 is needed). "
                    "Use a darker or lighter colour in the source."
                ),
                details={"page": page, "ratio": round(lowest.ratio, 2), "words": len(words)},
            )
        )
    return issues


def _compile_marked(
    root: Path,
    main_file: str,
    timeout_seconds: int,
    original: CompileResult,
) -> CompileResult:
    # The tracked copy may repeat errors the original already has, but must add none of its own
    if original.errors == 0:
        return compile_project(root, main_file, timeout_seconds)
    result = compile_project(root, main_file, timeout_seconds, strict=False)
    added = errors_beyond(original.error_messages, result.error_messages)
    if not added:
        return result
    location = re.match(r"^([^\s:]+\.\w+):(\d+): (.*)$", added[0])
    raise CompileError(
        added[0],
        source_file=location.group(1) if location else main_file,
        line=int(location.group(2)) if location else None,
        tex_error=location.group(3) if location else added[0],
        log_path=result.log_path,
    )


def _tolerated_errors_issue(count: int, messages: tuple[str, ...]) -> Issue:
    # Tell the user what pdfLaTeX reported without calling the render a failure
    first = messages[0] if messages else "see the compile log"
    return Issue(
        element_id=None,
        code="tex_errors_tolerated",
        severity="info",
        message=(
            f"pdfLaTeX reported {count} recoverable error(s) but still produced the PDF, "
            f"as Overleaf does. First: {first}"
        ),
        details={"count": count, "messages": list(messages[:10])},
    )


ADAPTER_REGISTRY: dict[str, SourceAdapter] = {
    "tex-beamer": TexBeamerAdapter(),
    "pptx": PptxAdapter(),
    "docx": DocxAdapter(),
}


def adapter_name_for(main_file: str) -> str:
    # A PowerPoint deck or Word document uses its own adapter; every other entry point is
    # Beamer source
    lower = main_file.lower()
    if lower.endswith(".pptx"):
        return "pptx"
    if lower.endswith(".docx"):
        return "docx"
    return "tex-beamer"


def get_adapter(name: str) -> SourceAdapter:
    # Return one registered source adapter
    adapter = ADAPTER_REGISTRY.get(name)
    if adapter is None:
        raise KeyError(f"source adapter is not registered: {name}")
    return adapter


def _figure_inputs(
    ir: DocumentIR,
    pdf_path: Path,
    crop_root: Path,
) -> dict[str, FigureDescriptionInput]:
    # Build model inputs from mapped source neutral figures
    inputs: dict[str, FigureDescriptionInput] = {}
    for element in ir.elements.values():
        if element.semantic_type != "figure":
            continue
        if element.accessibility.status != "needs_description":
            continue
        if not element.render.pages or element.render.bbox is None:
            continue
        slide_title, nearby_text = figure_context(ir, element)
        labels = _figure_labels(element)
        visible = list(labels)
        hidden: list[str] = []
        rendered: list[str] = []
        if element.subtype == "diagram" and labels:
            detection = detect_figure_hidden_labels(pdf_path, element, labels)
            visible = detection.visible_labels
            hidden = detection.hidden_labels
            rendered = [word.text for word in detection.words if not word.hidden]
        concepts = build_figure_concepts(element, nearby_text, visible, hidden)
        element.fidelity.required_concepts = list(concepts.required)
        element.fidelity.excluded_concepts = list(concepts.excluded)
        ir.issues.extend(concepts.issues)
        crop_path = crop_root / f"{element.id.replace('/', '-')}.png"
        crop_pdf_bbox(
            pdf_path,
            element.render.pages[-1],
            element.render.bbox,
            crop_path,
        )
        source_code = None
        if element.subtype == "diagram":
            source_code = element.source.raw
        inputs[element.id] = FigureDescriptionInput(
            element_id=element.id,
            subtype=element.subtype or "other",
            image_png=crop_path.read_bytes(),
            source_code=source_code,
            visible_labels=visible,
            slide_title=slide_title,
            nearby_text=nearby_text,
            rendered_text=rendered,
        )
    return inputs


def _figure_labels(element: Element) -> list[str]:
    # Read or infer source labels for one diagram
    if element.subtype != "diagram":
        return []
    parsed: list[str] = []
    values = element.attrs.get("tikz_labels")
    if isinstance(values, list):
        for value in values:
            if isinstance(value, str):
                parsed.append(value)
    return infer_tikz_labels(element.source.raw or "", parsed)


__all__ = [
    "ADAPTER_REGISTRY",
    "adapter_name_for",
    "PreparedDocument",
    "SourceAdapter",
    "WrittenDocument",
    "get_adapter",
]
