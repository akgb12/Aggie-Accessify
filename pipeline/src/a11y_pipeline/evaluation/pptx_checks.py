from a11y_pipeline.ir.models import DocumentIR

# The deterministic checks a PowerPoint deck can fail, and which provisional A metric each feeds.
# Names follow PowerPoint's own Accessibility Checker where it has a matching rule.


def pptx_check_results(ir: DocumentIR) -> dict[str, bool]:
    # Pass or fail for each document-level rule
    slides = [container for container in ir.containers if container.kind == "slide"]
    titles = [_title(ir, container.title_element_id) for container in slides]
    titled = [title for title in titles if title]
    figures = [e for e in ir.elements.values() if e.semantic_type == "figure"]
    tables = [e for e in ir.elements.values() if e.semantic_type == "table"]
    return {
        "slide_titles": len(titled) == len(slides),
        "unique_titles": len(set(titled)) == len(titled),
        "title_first_in_reading_order": _titles_first(ir),
        "figures_have_alt_text": all(_has_description(figure) for figure in figures),
        "tables_have_header_row": all(table.attrs.get("first_row_header") for table in tables),
        "document_title": bool(ir.metadata.get("title", "").strip()) or bool(titled),
        "document_language": bool(_language(ir)),
        "text_contrast": not any(issue.code == "low_contrast" for issue in ir.issues),
    }


def pptx_accessibility_metrics(
    ir: DocumentIR, figure_score: float | None
) -> dict[str, float | None]:
    # Provisional PowerPoint analogues of the A components; T/R/H/D/C are new definitions
    slides = [container for container in ir.containers if container.kind == "slide"]
    titles = [_title(ir, container.title_element_id) for container in slides]
    titled = [title for title in titles if title]
    checks = pptx_check_results(ir)
    ordered = _titled_slides_with_title_first(ir)
    return {
        "T": _share(len(titled), len(slides)),
        "R": _share(ordered[0], ordered[1]),
        "H": _share(len(set(titled)), len(titled)),
        "I": figure_score,
        "B": None,
        "M": None,
        "D": (
            50.0 * bool(ir.metadata.get("title", "").strip() or titled) + 50.0 * bool(_language(ir))
        ),
        "C": _share(sum(checks.values()), len(checks)),
    }


def _share(part: int | float, whole: int | float) -> float | None:
    return None if whole == 0 else 100.0 * part / whole


def _title(ir: DocumentIR, element_id: str | None) -> str:
    if element_id is None:
        return ""
    return " ".join(str(ir.elements[element_id].content.get("text", "")).split()).casefold()


def _has_description(element) -> bool:
    accessibility = element.accessibility
    if accessibility.decorative:
        return True
    return bool((accessibility.alt_text or "").strip())


def _titled_slides_with_title_first(ir: DocumentIR) -> tuple[int, int]:
    total = 0
    first = 0
    for container in ir.containers:
        if not _title(ir, container.title_element_id):
            continue
        total += 1
        # The parser decides this from the full stacking order, decorative shapes excluded
        if container.attrs.get("title_first", True):
            first += 1
    return first, total


def _language(ir: DocumentIR) -> str:
    # The deck language, or the one the update writes when the deck has none
    language = ir.metadata.get("language", "").strip()
    return language or ir.metadata.get("language_proposed", "").strip()


def _titles_first(ir: DocumentIR) -> bool:
    first, total = _titled_slides_with_title_first(ir)
    return first == total
