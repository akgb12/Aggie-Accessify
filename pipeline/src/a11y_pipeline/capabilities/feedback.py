from a11y_pipeline.ir.models import Issue

# Issue codes that describe a fixable problem with one figure description
REPAIRABLE_CODES = (
    "alt_low_coverage",
    "description_rejected",
    "alt_length_outlier",
    "alt_forbidden_opener",
    "alt_near_duplicate",
    "alt_file_name",
    "alt_missing",
    "judge_problem",
)


def repair_problems(issues: list[Issue], element_id: str) -> list[str]:
    # Turn the evaluator's findings for one figure into plain instructions for the next attempt
    problems: list[str] = []
    for issue in issues:
        if issue.element_id != element_id or issue.code not in REPAIRABLE_CODES:
            continue
        problem = _problem_text(issue)
        if problem and problem not in problems:
            problems.append(problem)
    return problems


def _problem_text(issue: Issue) -> str:
    # Word one finding so the model knows exactly what to change
    details = issue.details
    if issue.code == "alt_low_coverage":
        missing = [_concept_text(str(item)) for item in details.get("missing", [])]
        return (
            "These items drawn in the figure are not mentioned: "
            + "; ".join(missing)
            + ". Name each one. Write math labels the way a person would say them, "
            "for example X1 or x sub 1 for a subscripted x."
        )
    if issue.code == "description_rejected":
        if "quoted_label" in details:
            return (
                f"You quoted '{details['quoted_label']}', which is not drawn in the figure. "
                "Only quote text that appears in the figure."
            )
        return (
            f"You said {details.get('stated')} {details.get('stem')}, but the figure "
            f"shows {details.get('expected')}."
        )
    if issue.code == "alt_length_outlier":
        return (
            f"alt_text was {details.get('word_count')} words and the limit is "
            f"{details.get('limit')}. Shorten it and move detail to extended_description."
        )
    if issue.code == "judge_problem":
        return str(details.get("problem", issue.message))
    return issue.message


def _concept_text(concept: str) -> str:
    # Show one required concept as words
    if concept.startswith("label:"):
        return concept[len("label:") :]
    parts = concept.split(":", 2)
    if len(parts) == 3:
        return f"{parts[1]} {parts[2]} items"
    return concept
