from dataclasses import dataclass

from a11y_pipeline.capabilities.base import FigureJudgeOutput
from a11y_pipeline.evaluation.concepts import delivered_description, evaluate_coverage
from a11y_pipeline.evaluation.scores import figure_accessibility_score
from a11y_pipeline.evaluation.signals import evaluate_signals
from a11y_pipeline.evaluation.vetoes import evaluate_vetoes
from a11y_pipeline.ir.models import Candidate, DocumentIR, Element, Issue
from a11y_pipeline.ir.patches import apply_patches

# A judged figure never scores above its verdict; provisional like the other score weights
JUDGE_SCORES = {"good": 100.0, "needs_work": 70.0, "bad": 30.0}


@dataclass(frozen=True)
class CandidateEvaluation:
    candidate: Candidate
    document: DocumentIR
    failing_element_ids: list[str]


def evaluate_candidate(
    base_ir: DocumentIR,
    candidate: Candidate,
    coverage_threshold: float,
    nearby_text_by_element: dict[str, list[str]] | None = None,
    visible_labels_by_element: dict[str, list[str]] | None = None,
    rendered_text_by_element: dict[str, list[str]] | None = None,
    judged_by_element: dict[str, FigureJudgeOutput] | None = None,
) -> CandidateEvaluation:
    # Evaluate one cumulative candidate against the frozen base
    document = apply_patches(base_ir, candidate.patches)
    nearby = nearby_text_by_element or {}
    visible = visible_labels_by_element or {}
    all_vetoes = evaluate_vetoes(base_ir, document, visible, rendered_text_by_element)
    # A contradiction rejects that one figure's description; other vetoes disqualify the candidate
    rejected = {
        veto.element_id: veto
        for veto in all_vetoes
        if veto.code == "contradicts_source" and veto.element_id is not None
    }
    vetoes = [veto for veto in all_vetoes if veto.element_id not in rejected]
    issues: list[Issue] = []
    for element_id, veto in rejected.items():
        _reject_description(document.elements[element_id])
        issues.append(
            Issue(
                element_id=element_id,
                code="description_rejected",
                severity="error",
                message=veto.message,
                details=veto.details,
            )
        )
    figure_scores: list[float] = []
    flagged: set[str] = set()
    judged = judged_by_element or {}
    coverage_by_element: dict[str, float | None] = {}
    for element in document.elements.values():
        if element.semantic_type != "figure":
            continue
        coverage = evaluate_coverage(
            delivered_description(element),
            element.fidelity.required_concepts,
        )
        signals = evaluate_signals(
            element.id,
            element.accessibility.alt_text,
            element.fidelity.required_concepts,
            nearby.get(element.id, []),
        )
        issues.extend(signals.issues)
        if signals.warning_count:
            flagged.add(element.id)
        coverage_by_element[element.id] = coverage.coverage
        score = figure_accessibility_score(
            alt_present=bool((element.accessibility.alt_text or "").strip()),
            coverage=coverage.coverage,
            warning_count=signals.warning_count,
            vetoed=element.id in rejected,
            missing_asset=element.accessibility.status == "missing_asset",
        )
        verdict = judged.get(element.id)
        if verdict is not None and element.id not in rejected:
            score = min(score, JUDGE_SCORES[verdict.verdict])
            issues.extend(_judge_issues(element.id, verdict))
            if verdict.verdict != "good":
                flagged.add(element.id)
        figure_scores.append(score)
        if coverage.applicable and coverage.coverage is not None:
            if coverage.coverage < coverage_threshold:
                issues.append(
                    Issue(
                        element_id=element.id,
                        code="alt_low_coverage",
                        severity="error",
                        message="Figure alternative text is below the concept coverage threshold",
                        details={
                            "coverage": coverage.coverage,
                            "threshold": coverage_threshold,
                            "missing": coverage.missing,
                        },
                    )
                )
    failing = _failing_elements(
        document, coverage_by_element, coverage_threshold, set(rejected) | flagged
    )
    score_a = 100.0
    if figure_scores:
        score_a = sum(figure_scores) / len(figure_scores)
    score_f = 100.0
    if vetoes:
        score_f = 0.0
    evaluated = candidate.model_copy(deep=True)
    evaluated.scores = {"A": score_a, "F": score_f}
    evaluated.vetoes = vetoes
    evaluated.issues = issues
    return CandidateEvaluation(
        candidate=evaluated,
        document=document,
        failing_element_ids=failing,
    )


def _judge_issues(element_id: str, verdict: FigureJudgeOutput) -> list[Issue]:
    # One finding per problem the judge listed, so each can be fed back to the next attempt
    issues: list[Issue] = []
    problems = [f"Remove or correct: {item}" for item in verdict.invented]
    problems.extend(f"Add: {item}" for item in verdict.missing)
    if verdict.verdict != "good" and not problems:
        problems.append("A reviewer found this description unclear; make it more specific.")
    for problem in problems:
        issues.append(
            Issue(
                element_id=element_id,
                code="judge_problem",
                severity="warning",
                message=f"Judge ({verdict.verdict}): {problem}",
                details={"problem": problem, "verdict": verdict.verdict},
            )
        )
    return issues


def _reject_description(element: Element) -> None:
    # Remove a description that contradicts the figure so it is never delivered
    element.accessibility.alt_text = None
    element.accessibility.extended_description = None
    element.accessibility.status = "needs_review"


def _failing_elements(
    document: DocumentIR,
    coverage_by_element: dict[str, float | None],
    threshold: float,
    vetoed_ids: set[str],
) -> list[str]:
    # Find figures eligible for focused repair
    failing: list[str] = []
    for element in document.elements.values():
        if element.semantic_type != "figure":
            continue
        coverage = coverage_by_element.get(element.id)
        low_coverage = coverage is not None and coverage < threshold
        failed = element.accessibility.status == "failed"
        if low_coverage or failed or element.id in vetoed_ids:
            failing.append(element.id)
    return failing
