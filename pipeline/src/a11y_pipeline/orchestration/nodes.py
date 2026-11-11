import hashlib

from a11y_pipeline.adapters import adapter_name_for, get_adapter
from a11y_pipeline.analysis.needs import analyze_needs
from a11y_pipeline.budget import BudgetExceeded
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.capabilities.base import (
    CapabilityResult,
    FigureDescriptionInput,
    FigureDescriptionOutput,
    FigureJudgeInput,
    FigureJudgeOutput,
)
from a11y_pipeline.capabilities.feedback import repair_problems
from a11y_pipeline.capabilities.figure_judge import FigureJudgeCapability
from a11y_pipeline.capabilities.quote_check import QuoteCheckCapability
from a11y_pipeline.capabilities.text_inventory import TextInventoryCapability
from a11y_pipeline.evaluation.vetoes import unknown_quoted_labels
from a11y_pipeline.ir.models import Candidate, DocumentIR, HistoryEntry, Issue, Patch
from a11y_pipeline.ir.patches import apply_patches
from a11y_pipeline.orchestration.candidates import evaluate_candidate
from a11y_pipeline.orchestration.effort import (
    ELEMENT_REPAIR_LIMIT,
    dollar_cap,
    round_cap,
)
from a11y_pipeline.orchestration.selection import accepts_candidate, select_best_candidate
from a11y_pipeline.orchestration.state import RunState
from a11y_pipeline.orchestration.stopping import StopContext, decide_stop
from a11y_pipeline.routing.router import route

SEED_WEAK_TEXT = "Five boxes in a row, one is blue."


def ingest_node(state: RunState) -> dict[str, object]:
    # Load the normalized source bundle
    if state.bundle is not None:
        return {}
    if state.input_path is None:
        if state.base_ir is not None:
            return {}
        raise ValueError("input_path or base_ir is required")
    bundle = Bundle.from_path(state.input_path, state.main_file)
    return {"bundle": bundle, "adapter_name": adapter_name_for(bundle.main_file)}


def preflight_node(state: RunState) -> dict[str, object]:
    # Run adapter preflight before model work
    if state.bundle is None:
        return {}
    adapter = get_adapter(state.adapter_name)
    result = adapter.preflight(state.bundle)
    updates: dict[str, object] = {"preflight_result": result}
    if not result.ok:
        updates["blocked"] = True
        updates["issues"] = _preflight_issues(result)
    return updates


def build_ir_node(state: RunState) -> dict[str, object]:
    # Build the frozen base document
    if state.base_ir is not None:
        return {}
    if state.bundle is None or state.preflight_result is None:
        raise ValueError("bundle and preflight result are required")
    adapter = get_adapter(state.adapter_name)
    document = adapter.build_ir(state.bundle, state.preflight_result)
    return {"base_ir": document}


def compile_and_map_node(state: RunState) -> dict[str, object]:
    # Prepare mapped figures through the adapter
    if state.bundle is None or state.base_ir is None:
        return {}
    if state.figure_inputs:
        return {}
    adapter = get_adapter(state.adapter_name)
    prepared = adapter.prepare(
        state.bundle,
        state.base_ir,
        state.telemetry_path.parent,
        state.config.compile_timeout_seconds,
    )
    return {
        "base_ir": prepared.ir,
        "figure_inputs": prepared.figure_inputs,
        "original_pdf": prepared.original_pdf,
        "marked_pdf": prepared.marked_pdf,
        "issues": list(prepared.ir.issues),
    }


def build_c0_node(state: RunState) -> dict[str, object]:
    # Build and evaluate deterministic fallback c0
    base_ir = _require_base_ir(state)
    candidate = Candidate(candidate_id="c0", round=0, patches=[])
    evaluation = evaluate_candidate(
        base_ir,
        candidate,
        state.config.concept_coverage_threshold,
        _nearby_text(state),
        _visible_labels(state),
        _rendered_text(state),
    )
    return {
        "candidates": [evaluation.candidate],
        "candidate_ir": evaluation.document,
        "failing_element_ids": evaluation.failing_element_ids,
        "selected_candidate_id": "c0",
        "active_patches": [],
    }


def analyze_needs_node(state: RunState) -> dict[str, object]:
    # Find all initial model tasks
    base_ir = _require_base_ir(state)
    tasks = analyze_needs(base_ir)
    element_ids: list[str] = []
    for task in tasks:
        element_ids.append(task.element_id)
    return {
        "tasks": tasks,
        "pending_element_ids": element_ids,
        "current_round": 0,
    }


def route_node(state: RunState) -> dict[str, object]:
    # Route only the pending figure identifiers
    selected = set(state.pending_element_ids)
    routed = route(state.tasks, element_ids=selected)
    return {"routed_tasks": routed}


def run_capabilities_node(state: RunState) -> dict[str, object]:
    # Run fixed or model figure descriptions
    if state.model_client is None and state.routed_tasks:
        raise ValueError("model_client is required for capability work")
    results: list[CapabilityResult] = []
    issues = list(state.issues)
    budget_exhausted = state.budget_exhausted
    figure_inputs = dict(state.figure_inputs)
    base_ir = state.base_ir
    for routed in state.routed_tasks:
        element_id = routed.task.element_id
        if state.current_round == 0 and element_id == state.seed_weak_element_id:
            results.append(_seed_weak_result(state, element_id))
            continue
        capability_input = state.figure_inputs.get(element_id)
        if capability_input is not None and state.current_round > 0:
            capability_input = _with_repair_feedback(state, capability_input)
        if capability_input is None:
            results.append(_missing_input_result(state, element_id))
            issues.append(
                Issue(
                    element_id=element_id,
                    code="capability_input_missing",
                    severity="error",
                    message="Figure capability input is unavailable",
                )
            )
            continue
        if routed.task.capability == "figure_description" and state.current_round == 0:
            try:
                transcribed = _transcribe_picture(state, capability_input)
            except BudgetExceeded:
                budget_exhausted = True
                break
            if transcribed is not None:
                capability_input = capability_input.model_copy(
                    update={
                        "image_text": transcribed,
                        "rendered_text": [*capability_input.rendered_text, *transcribed],
                    }
                )
                figure_inputs[element_id] = capability_input
                base_ir = _text_now_checkable(base_ir, element_id)
        capability = routed.capability(
            state.model_client,
            model=state.config.generator_model,
            max_tokens=state.config.model_max_output_tokens,
        )
        try:
            result = capability.run(
                capability_input,
                run_id=state.run_id,
                round_number=state.current_round,
            )
        except BudgetExceeded:
            budget_exhausted = True
            break
        results.append(_append_history_patch(state, result, element_id))
        if routed.task.capability == "figure_description":
            try:
                confirmed = _confirm_quotes(state, base_ir, capability_input, result)
            except BudgetExceeded:
                budget_exhausted = True
                break
            if confirmed:
                figure_inputs[element_id] = capability_input.model_copy(
                    update={"rendered_text": [*capability_input.rendered_text, *confirmed]}
                )
    budget_spent = state.budget_spent
    if state.budget_controller is not None:
        budget_spent = state.budget_controller.spent_usd
    return {
        "pending_results": results,
        "issues": issues,
        "budget_exhausted": budget_exhausted,
        "budget_spent": budget_spent,
        "figure_inputs": figure_inputs,
        "base_ir": base_ir,
    }


def _transcribe_picture(
    state: RunState, capability_input: FigureDescriptionInput
) -> list[str] | None:
    # Transcribe the words drawn in a figure that holds a picture, from the image alone, so
    # the description can quote them exactly and the checks can confirm the quotes
    if not state.config.transcribe_pictures or state.model_client is None:
        return None
    element = _require_base_ir(state).elements.get(capability_input.element_id)
    if element is None or not element.attrs.get("contains_picture"):
        return None
    inventory = TextInventoryCapability(state.model_client, model=state.config.generator_model)
    return inventory.transcribe(capability_input.element_id, capability_input.image_png)


def _text_now_checkable(base_ir: DocumentIR | None, element_id: str) -> DocumentIR | None:
    # With a transcription, quotes of a picture's text can be checked after all
    if base_ir is None or not base_ir.elements[element_id].attrs.get("text_unverifiable"):
        return base_ir
    updated = base_ir.model_copy(deep=True)
    updated.elements[element_id].attrs["text_unverifiable"] = False
    return updated


def _confirm_quotes(
    state: RunState,
    base_ir: DocumentIR | None,
    capability_input: FigureDescriptionInput,
    result: CapabilityResult,
) -> list[str]:
    # Quotes in a new description that the deterministic checks cannot find in the figure's
    # known text are put to a narrow yes/no check against the image. Confirmed quotes join
    # the figure's drawn text, so the evaluator accepts them; the rest are still vetoed.
    if not state.config.verify_quotes or state.model_client is None:
        return []
    if base_ir is None:
        return []
    element = base_ir.elements.get(capability_input.element_id)
    if element is None or element.attrs.get("text_unverifiable"):
        return []
    values = {patch.path: patch.value for patch in result.patches}
    text = "\n".join(
        str(values.get(path) or "")
        for path in ("accessibility.alt_text", "accessibility.extended_description")
    )
    quotes = unknown_quoted_labels(
        text, capability_input.visible_labels, capability_input.rendered_text
    )
    if not quotes:
        return []
    # Words elsewhere on the slide are real, not invented, even when quoted for this figure
    slide_words = [*capability_input.nearby_text, capability_input.slide_title or ""]
    unseen = unknown_quoted_labels(
        text,
        capability_input.visible_labels,
        [*capability_input.rendered_text, *slide_words],
    )
    confirmed = [quote for quote in quotes if quote not in unseen]
    if unseen:
        checker = QuoteCheckCapability(state.model_client, model=state.config.generator_model)
        image = capability_input.image_png
        confirmed += checker.written(capability_input.element_id, image, unseen)
    return confirmed


def synthesize_node(state: RunState) -> dict[str, object]:
    # Build cumulative patches for the next candidate
    patches = list(state.active_patches)
    for result in state.pending_results:
        patches.extend(result.patches)
    candidate = Candidate(
        candidate_id=f"c{len(state.candidates)}",
        round=state.current_round,
        patches=patches,
    )
    return {
        "active_patches": patches,
        "candidate_ir": None,
        "pending_candidate": candidate,
    }


def evaluate_node(state: RunState) -> dict[str, object]:
    # Evaluate the synthesized cumulative candidate
    base_ir = _require_base_ir(state)
    candidate = _pending_candidate(state)
    evaluation = _evaluate(state, base_ir, candidate, {})
    judgments = dict(state.judgments)
    budget_exhausted = state.budget_exhausted
    if state.config.judge_in_loop and state.model_client is not None:
        judgments, exhausted = _judge_figures(state, evaluation.document)
        budget_exhausted = budget_exhausted or exhausted
        evaluation = _evaluate(state, base_ir, candidate, _verdicts(judgments, evaluation.document))
    candidates = list(state.candidates)
    previous = candidates[-1]
    accepted = accepts_candidate(previous, evaluation.candidate)
    candidates.append(evaluation.candidate)
    selected = select_best_candidate(
        candidates,
        *_floors(state),
    )
    budget_spent = state.budget_spent
    if state.budget_controller is not None:
        budget_spent = state.budget_controller.spent_usd
    return {
        "candidates": candidates,
        "candidate_ir": evaluation.document,
        "failing_element_ids": evaluation.failing_element_ids,
        "last_candidate_accepted": accepted,
        "selected_candidate_id": selected.candidate_id,
        "pending_results": [],
        "pending_candidate": None,
        "judgments": judgments,
        "budget_exhausted": budget_exhausted,
        "budget_spent": budget_spent,
    }


def _floors(state: RunState) -> tuple[float, float]:
    # The A floor depends on the source format; F is shared. Word documents use the Office
    # floor, which like PowerPoint's is still provisional
    office = state.adapter_name in {"pptx", "docx"}
    floor_a = state.config.floor_a_pptx if office else state.config.floor_a
    return floor_a, state.config.floor_f


def _evaluate(
    state: RunState,
    base_ir: DocumentIR,
    candidate: Candidate,
    verdicts: dict[str, FigureJudgeOutput],
):
    # Evaluate one candidate with everything the run knows about its figures
    return evaluate_candidate(
        base_ir,
        candidate,
        state.config.concept_coverage_threshold,
        _nearby_text(state),
        _visible_labels(state),
        _rendered_text(state),
        verdicts,
    )


def _judge_key(element_id: str, alt_text: str, extended: str | None) -> str:
    # Identify one description so an unchanged text is never judged twice
    digest = hashlib.sha256(f"{alt_text}\n{extended or ''}".encode()).hexdigest()[:16]
    return f"{element_id}:{digest}"


def _verdicts(
    judgments: dict[str, dict[str, object]],
    document: DocumentIR,
) -> dict[str, FigureJudgeOutput]:
    # Look up the stored verdict for each figure's current description
    verdicts: dict[str, FigureJudgeOutput] = {}
    for element in document.elements.values():
        alt = element.accessibility.alt_text
        if element.semantic_type != "figure" or not alt:
            continue
        stored = judgments.get(
            _judge_key(element.id, alt, element.accessibility.extended_description)
        )
        if stored is not None:
            verdicts[element.id] = FigureJudgeOutput.model_validate(stored)
    return verdicts


def _judge_figures(
    state: RunState,
    document: DocumentIR,
) -> tuple[dict[str, dict[str, object]], bool]:
    # Judge every described figure whose current text has no verdict yet
    judgments = dict(state.judgments)
    capability = FigureJudgeCapability(
        state.model_client,
        model=state.config.generator_model,
        max_tokens=state.config.model_max_output_tokens,
    )
    for element in document.elements.values():
        alt = element.accessibility.alt_text
        capability_input = state.figure_inputs.get(element.id)
        if element.semantic_type != "figure" or not alt or capability_input is None:
            continue
        extended = element.accessibility.extended_description
        key = _judge_key(element.id, alt, extended)
        if key in judgments:
            continue
        try:
            verdict = capability.judge(
                FigureJudgeInput(
                    element_id=element.id,
                    image_png=capability_input.image_png,
                    alt_text=alt,
                    extended_description=extended,
                    slide_title=capability_input.slide_title,
                )
            )
        except BudgetExceeded:
            return judgments, True
        if verdict is not None:
            judgments[key] = verdict.model_dump(mode="json")
    return judgments, False


def decide_node(state: RunState) -> dict[str, object]:
    # Apply stopping and selection decisions
    reason = decide_stop(
        StopContext(
            failing_element_ids=state.failing_element_ids,
            current_round=state.current_round,
            round_cap=round_cap(state.effort),
            budget_spent=state.budget_spent,
            dollar_cap=(
                state.budget_controller.cap_usd
                if state.budget_controller is not None
                else dollar_cap(state.effort, state.config)
            ),
            accepted_improvement=state.last_candidate_accepted,
            repair_counts=state.repair_counts,
            repair_limit=ELEMENT_REPAIR_LIMIT,
            budget_exhausted=state.budget_exhausted,
        )
    )
    selected = select_best_candidate(
        state.candidates,
        *_floors(state),
    )
    return {"stop_reason": reason, "selected_candidate_id": selected.candidate_id}


def prepare_repair_node(state: RunState) -> dict[str, object]:
    # Advance one repair round for failing figures
    pending: list[str] = []
    counts = dict(state.repair_counts)
    for element_id in state.failing_element_ids:
        count = counts.get(element_id, 0)
        if count >= ELEMENT_REPAIR_LIMIT:
            continue
        pending.append(element_id)
        counts[element_id] = count + 1
    return {
        "current_round": state.current_round + 1,
        "repair_counts": counts,
        "pending_element_ids": pending,
        "routed_tasks": [],
    }


def finalize_node(state: RunState) -> dict[str, object]:
    # Materialize the selected candidate and review statuses
    base_ir = _require_base_ir(state)
    selected = _selected_candidate(state)
    evaluation = _evaluate(state, base_ir, selected, {})
    if state.judgments:
        evaluation = _evaluate(
            state, base_ir, selected, _verdicts(state.judgments, evaluation.document)
        )
    final_ir = evaluation.document.model_copy(deep=True)
    for element_id in evaluation.failing_element_ids:
        final_ir.elements[element_id].accessibility.status = "needs_review"
    return {
        "final_ir": final_ir,
        "selected_candidate_id": selected.candidate_id,
    }


def finalize_blocked_node(state: RunState) -> dict[str, object]:
    # Preserve preflight findings for a blocked run
    return {"final_ir": None}


def _require_base_ir(state: RunState) -> DocumentIR:
    # Return the required frozen base document
    if state.base_ir is None:
        raise ValueError("base_ir is required")
    return state.base_ir


def _nearby_text(state: RunState) -> dict[str, list[str]]:
    # Index nearby text from capability inputs
    values: dict[str, list[str]] = {}
    for element_id, capability_input in state.figure_inputs.items():
        values[element_id] = list(capability_input.nearby_text)
    return values


def _visible_labels(state: RunState) -> dict[str, list[str]]:
    # Index visible labels from capability inputs
    values: dict[str, list[str]] = {}
    for element_id, capability_input in state.figure_inputs.items():
        values[element_id] = list(capability_input.visible_labels)
    return values


def _with_repair_feedback(
    state: RunState,
    capability_input: FigureDescriptionInput,
) -> FigureDescriptionInput:
    # Show the model its earlier attempt and what the evaluator found wrong with it
    element_id = capability_input.element_id
    problems = repair_problems(state.candidates[-1].issues, element_id)
    if not problems:
        return capability_input
    previous = apply_patches(_require_base_ir(state), state.active_patches).elements[element_id]
    return capability_input.model_copy(
        update={
            "previous_alt": previous.accessibility.alt_text,
            "previous_extended": previous.accessibility.extended_description,
            "problems": problems,
        }
    )


def _rendered_text(state: RunState) -> dict[str, list[str]]:
    # Index the words drawn in each figure from capability inputs
    values: dict[str, list[str]] = {}
    for element_id, capability_input in state.figure_inputs.items():
        values[element_id] = list(capability_input.rendered_text)
    return values


def _seed_weak_result(state: RunState, element_id: str) -> CapabilityResult:
    # Build the fixed weak demonstration patch
    output = FigureDescriptionOutput(alt_text=SEED_WEAK_TEXT)
    values: list[tuple[str, object]] = [
        ("accessibility.alt_text", output.alt_text),
        ("accessibility.extended_description", output.extended_description),
        ("accessibility.decorative_suggested", output.decorative),
        ("accessibility.status", "model_generated"),
    ]
    patches: list[Patch] = []
    for path, value in values:
        patches.append(
            Patch(
                element_id=element_id,
                path=path,
                value=value,
                by="deterministic",
                round=0,
                note="Seeded weak demonstration text",
            )
        )
    history = HistoryEntry(
        run_id=state.run_id,
        round=0,
        change="Seeded weak demonstration text",
        by="deterministic",
    )
    result = CapabilityResult(patches=patches, history=history)
    return _append_history_patch(state, result, element_id)


def _missing_input_result(state: RunState, element_id: str) -> CapabilityResult:
    # Mark a figure whose prepared input is unavailable
    patch = Patch(
        element_id=element_id,
        path="accessibility.status",
        value="failed",
        by="deterministic",
        round=state.current_round,
        note="Figure capability input is unavailable",
    )
    return CapabilityResult(patches=[patch], history=None)


def _append_history_patch(
    state: RunState,
    result: CapabilityResult,
    element_id: str,
) -> CapabilityResult:
    # Append capability provenance through a cumulative patch
    if result.history is None:
        return result
    base_ir = _require_base_ir(state)
    current = apply_patches(base_ir, state.active_patches)
    history = list(current.elements[element_id].history)
    history.append(result.history)
    patches = list(result.patches)
    patches.append(
        Patch(
            element_id=element_id,
            path="history",
            value=history,
            by=result.history.by,
            round=state.current_round,
            note=result.history.change,
        )
    )
    return CapabilityResult(patches=patches, history=result.history)


def _pending_candidate(state: RunState) -> Candidate:
    # Read the transient synthesized candidate
    if state.pending_candidate is None:
        raise ValueError("one synthesized candidate is required")
    return state.pending_candidate


def _selected_candidate(state: RunState) -> Candidate:
    # Find the selected candidate by identifier
    for candidate in state.candidates:
        if candidate.candidate_id == state.selected_candidate_id:
            return candidate
    raise ValueError("selected candidate is unavailable")


def _preflight_issues(result: object) -> list[Issue]:
    # Convert adapter preflight findings to canonical issues
    converted: list[Issue] = []
    raw_issues = getattr(result, "issues", [])
    for issue in raw_issues:
        severity = "warning"
        if getattr(issue, "severity", "") == "critical":
            severity = "error"
        converted.append(
            Issue(
                element_id=None,
                code=str(getattr(issue, "code", "preflight_failed")),
                severity=severity,
                message=str(getattr(issue, "message", "Preflight failed")),
                details={
                    "source_file": getattr(issue, "source_file", ""),
                    "line": getattr(issue, "line", 0),
                    "dependency": getattr(issue, "dependency", None),
                },
            )
        )
    return converted
