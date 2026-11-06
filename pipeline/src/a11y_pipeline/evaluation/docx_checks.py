from a11y_pipeline.ir.models import DocumentIR, Element

# The deterministic checks a Word document can fail, and which provisional A metric each feeds.
# Names follow Word's own Accessibility Checker where it has a matching rule.

# A document this long without one heading cannot be navigated by headings
HEADINGS_EXPECTED_FROM = 8


def docx_check_results(ir: DocumentIR) -> dict[str, bool]:
    headings = _headings(ir)
    paragraphs = [e for e in ir.elements.values() if e.semantic_type == "paragraph"]
    figures = [e for e in ir.elements.values() if e.semantic_type == "figure"]
    tables = [e for e in ir.elements.values() if e.semantic_type == "table"]
    formulas = [e for e in ir.elements.values() if e.semantic_type == "formula"]
    return {
        "headings_present": bool(headings) or len(paragraphs) < HEADINGS_EXPECTED_FROM,
        "heading_levels_in_order": _skips(headings) == 0,
        "figures_have_alt_text": all(_has_description(figure) for figure in figures),
        "tables_have_header_row": all(
            table.attrs.get("first_row_header") or int(table.attrs.get("row_count", 0)) < 2
            for table in tables
        ),
        "equations_have_text": all((f.accessibility.alt_text or "").strip() for f in formulas),
        "document_title": bool(_title(ir)),
        "document_language": bool(_language(ir)),
    }


def docx_accessibility_metrics(
    ir: DocumentIR, figure_score: float | None
) -> dict[str, float | None]:
    # Provisional Word analogues of the A components
    headings = _headings(ir)
    checks = docx_check_results(ir)
    return {
        "T": 100.0 if checks["headings_present"] else 0.0,
        "R": None,
        "H": None if not headings else 100.0 * (len(headings) - _skips(headings)) / len(headings),
        "I": figure_score,
        "B": None,
        "M": None,
        "D": 50.0 * bool(_title(ir)) + 50.0 * bool(_language(ir)),
        "C": 100.0 * sum(checks.values()) / len(checks),
    }


def _headings(ir: DocumentIR) -> list[int]:
    # Heading levels in reading order: styled headings and lines the outline step promoted
    levels: list[int] = []
    for container in ir.containers:
        for element_id in container.element_ids:
            element = ir.elements[element_id]
            if element.semantic_type == "heading":
                levels.append(int(element.attrs.get("level", 1)))
            elif int(element.attrs.get("outline_level") or 0):
                levels.append(int(element.attrs["outline_level"]))
    return levels


def _skips(levels: list[int]) -> int:
    previous = 0
    skipped = 0
    for level in levels:
        if level > previous + 1:
            skipped += 1
        previous = level
    return skipped


def _has_description(element: Element) -> bool:
    accessibility = element.accessibility
    if accessibility.decorative or accessibility.decorative_suggested:
        return True
    return bool((accessibility.alt_text or "").strip())


def _title(ir: DocumentIR) -> str:
    outline = next((e for e in ir.elements.values() if e.subtype == "document_outline"), None)
    proposed = str(outline.content.get("text") or "") if outline is not None else ""
    return (
        ir.metadata.get("title", "") or proposed or ir.metadata.get("title_proposed", "")
    ).strip()


def _language(ir: DocumentIR) -> str:
    return (ir.metadata.get("language_proposed") or ir.metadata.get("language", "")).strip()
