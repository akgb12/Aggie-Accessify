import json
import logging
from decimal import Decimal
from pathlib import Path

from django.tasks import task
from django.utils import timezone

from a11y_pipeline.cli import _model_client
from a11y_pipeline.config import Settings
from a11y_pipeline.models.client import ModelClient, ModelRequest, ModelResponse
from a11y_pipeline.orchestration.effort import dollar_cap
from a11y_pipeline.runs.folder import RunBlockedError, run_to_folder
from a11y_pipeline.runs.outputs import OUTPUTS_VERSION, refresh_run_outputs
from accounts.usage import charge_run, limit_message, reserve_run_budget
from projects.models import Run
from projects.storage import (
    download_run_files,
    materialize_project,
    scratch_dir,
    upload_run_folder,
)

logger = logging.getLogger(__name__)

# Source copies are large and reproducible from the project files, so they stay out of storage
SKIPPED_RUN_FOLDERS = ("work/original", "work/marked")
# The saved files newer downloads are built from when an older run is brought up to date
REFRESH_INPUTS = [
    "manifest.json",
    "output/updated.pptx",
    "output/updated.docx",
    "output/changes.diff",
]


@task
def run_pipeline_task(run_id: str) -> str:
    # Run one queued project through the complete pipeline in a scratch folder
    run = Run.objects.select_related("project__owner").get(id=run_id)
    pipeline_settings = Settings()
    # The run may spend what its effort allows, but never more than its owner has left
    granted = reserve_run_budget(run, Decimal(str(dollar_cap(run.effort, pipeline_settings))))
    if granted is not None and granted <= 0:
        run.status = Run.Status.FAILED
        run.finished_at = timezone.now()
        run.stop_reason = "usage_limit"
        run.error_message = limit_message(run.project.owner)
        run.save(update_fields=["status", "finished_at", "stop_reason", "error_message"])
        return str(run.id)
    meter: _SpendMeter | None = None
    try:
        with scratch_dir(f"run-{run.id}") as scratch:
            bundle_root = scratch / "bundle"
            output_root = scratch / "output"
            materialize_project(run.project, bundle_root)
            meter = _SpendMeter(_model_client(pipeline_settings, fresh=run.fresh))
            try:
                completed = run_to_folder(
                    bundle_root,
                    meter,
                    pipeline_settings,
                    effort=run.effort,
                    main_file=run.main_file or None,
                    seed_weak_element_id=run.seed_weak,
                    output_root=output_root,
                    max_cost_usd=float(granted) if granted is not None else None,
                )
            except RunBlockedError as error:
                upload_run_folder(run.id, error.folder.root, SKIPPED_RUN_FOLDERS)
                _update_run_from_manifest(run, error.folder.root, Run.Status.BLOCKED)
                charge_run(run)
                return str(run.id)
            upload_run_folder(run.id, completed.folder.root, SKIPPED_RUN_FOLDERS)
            _update_completed_run(run, completed.folder.root, completed)
            charge_run(run)
    except Exception as error:
        if run.status == Run.Status.RUNNING:
            # A run that fails partway has still paid for the model calls it made
            run.status = Run.Status.FAILED
            run.finished_at = timezone.now()
            run.error_message = _user_message(error)
            run.cost_usd = Decimal(str(meter.spent_usd if meter is not None else 0))
            run.save(update_fields=["status", "finished_at", "error_message", "cost_usd"])
            charge_run(run)
        raise
    return str(run.id)


class _SpendMeter:
    # Adds up what model calls cost, including calls that failed after they were billed
    def __init__(self, client: ModelClient) -> None:
        self.client = client
        self.spent_usd = 0.0

    def complete_structured(self, request: ModelRequest) -> ModelResponse:
        try:
            response = self.client.complete_structured(request)
        except Exception as error:
            self.spent_usd += float(getattr(error, "cost_usd", 0) or 0)
            raise
        self.spent_usd += response.cost_usd
        return response


def _user_message(error: Exception) -> str:
    # Prefer a message that is fair about who needs to act; never include credentials
    message = getattr(error, "user_message", None)
    if isinstance(message, str) and message:
        return message[:800]
    return f"{type(error).__name__}: Pipeline run failed"


def _update_completed_run(run: Run, root: Path, completed: object) -> None:
    # Persist scores and manifest totals from a completed run
    manifest = _read_manifest(root)
    totals = manifest.get("totals", {})
    run.status = Run.Status.SUCCEEDED
    run.finished_at = timezone.now()
    run.storage_prefix = f"runs/{run.id}"
    run.main_file = manifest.get("inputs", {}).get("main_file", run.main_file)
    run.model_provider = manifest.get("model", {}).get("provider", run.model_provider)
    run.stop_reason = manifest.get("stop_reason") or ""
    run.a_score = completed.stats.accessibility.value
    run.f_score = completed.stats.fidelity.value
    run.input_tokens = int(totals.get("input_tokens", 0))
    run.output_tokens = int(totals.get("output_tokens", 0))
    run.cost_usd = Decimal(str(totals.get("cost_usd", 0)))
    run.outputs_version = int(manifest.get("outputs_version", 0))
    run.save()


@task
def refresh_run_outputs_task(run_id: str) -> str:
    # Bring a finished run's downloads up to date in the background
    refresh_run_outputs_now(Run.objects.get(id=run_id))
    return run_id


def refresh_run_outputs_now(run: Run) -> bool:
    # Rebuild the downloads an older run is missing from the files it saved; no model calls.
    # True when the run gained or changed anything.
    try:
        with scratch_dir(f"refresh-{run.id}") as scratch:
            download_run_files(run.storage_prefix, REFRESH_INPUTS, scratch)
            changed = refresh_run_outputs(scratch)
            if changed:
                upload_run_folder(run.id, scratch)
    except Exception:
        logger.exception("Run %s could not be brought up to date", run.id)
        Run.objects.filter(id=run.id).update(refreshing=False)
        return False
    Run.objects.filter(id=run.id).update(outputs_version=OUTPUTS_VERSION, refreshing=False)
    return changed


def _update_run_from_manifest(run: Run, root: Path, status: str) -> None:
    # Persist safe metadata from a blocked pipeline run
    manifest = _read_manifest(root)
    totals = manifest.get("totals", {})
    run.status = status
    run.finished_at = timezone.now()
    run.storage_prefix = f"runs/{run.id}"
    run.main_file = manifest.get("inputs", {}).get("main_file", run.main_file)
    run.model_provider = manifest.get("model", {}).get("provider", run.model_provider)
    run.stop_reason = manifest.get("stop_reason") or "preflight_blocked"
    run.input_tokens = int(totals.get("input_tokens", 0))
    run.output_tokens = int(totals.get("output_tokens", 0))
    run.cost_usd = Decimal(str(totals.get("cost_usd", 0)))
    run.save()


def _read_manifest(root: Path) -> dict[str, object]:
    # Read one generated manifest without logging its contents
    return json.loads((root / "manifest.json").read_text(encoding="utf-8"))
