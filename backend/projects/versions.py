import hashlib
import json
from pathlib import Path, PurePosixPath
from uuid import UUID

from a11y_pipeline.runs.known_descriptions import KnownDescriptions, known_descriptions
from projects.models import FileVersion, ProjectFile, Run
from projects.storage import ensure_versions, new_version, read_run_json

# A run starts from the current version of each file, and what it produces becomes the next
# version, so making a file accessible again builds on what the person last saw and edited.

READ_BLOCK = 1024 * 1024
OFFICE_OUTPUTS = {".pptx": "output/updated.pptx", ".docx": "output/updated.docx"}
BEAMER_OUTPUT = "output/updated_project"
# How many earlier runs of a file are searched for the descriptions they wrote
KNOWN_RUNS = 10


def snapshot_inputs(run: Run) -> None:
    # Note which version of each file the run starts from
    run.input_versions = {
        project_file.path: str(ensure_versions(project_file).id)
        for project_file in run.project.files.select_related("current_version")
    }
    run.save(update_fields=["input_versions"])


def earlier_descriptions(run: Run) -> KnownDescriptions:
    # The figure descriptions earlier runs of the same file wrote, so a file made accessible
    # before is read back the way it was made; the newest run wins where two wrote the same text
    earlier = (
        Run.objects.filter(
            project_id=run.project_id, main_file=run.main_file, status=Run.Status.SUCCEEDED
        )
        .exclude(id=run.id)
        .order_by("-created_at")[:KNOWN_RUNS]
    )
    known: KnownDescriptions = {}
    for previous in reversed(list(earlier)):
        try:
            known.update(
                known_descriptions(read_run_json(previous.storage_prefix, "ir_final.json"))
            )
        except (OSError, ValueError):
            continue
    return known


def save_run_outputs(run: Run, root: Path) -> str:
    # Keep what a finished run produced as the next version of each file it changed. Within a
    # run the result is the best of the candidates it scored, never below the version it
    # started from, so it is saved unless a final check vetoed it. Returns the outcome.
    outputs = _changed_outputs(run, root)
    if not outputs:
        outcome = Run.VersionOutcome.UNCHANGED
    elif _vetoed(root):
        outcome = Run.VersionOutcome.NOT_SAVED
    else:
        outcome = Run.VersionOutcome.SAVED
        for project_file, local in outputs:
            # A file changed by someone while the run worked keeps that change as current
            current = project_file.current_version_id is not None and str(
                project_file.current_version_id
            ) == run.input_versions.get(project_file.path)
            if not current:
                outcome = Run.VersionOutcome.SAVED_NOT_CURRENT
            with local.open("rb") as stream:
                new_version(
                    project_file, stream, FileVersion.Source.UPDATE, make_current=current, run=run
                )
    run.version_outcome = outcome
    run.save(update_fields=["version_outcome"])
    return outcome


def _changed_outputs(run: Run, root: Path) -> list[tuple[ProjectFile, Path]]:
    # Each project file the run's output changed, with the local file holding its new state
    files = {project_file.path: project_file for project_file in run.project.files.all()}
    suffix = PurePosixPath(run.main_file).suffix.lower()
    candidates: list[tuple[str, Path]] = []
    if suffix in OFFICE_OUTPUTS:
        candidates.append((run.main_file, root / OFFICE_OUTPUTS[suffix]))
    else:
        updated = root / BEAMER_OUTPUT
        if updated.is_dir():
            for local in sorted(updated.rglob("*")):
                if local.is_file():
                    candidates.append((local.relative_to(updated).as_posix(), local))
    changed: list[tuple[ProjectFile, Path]] = []
    inputs = FileVersion.objects.in_bulk(
        [value for value in run.input_versions.values() if value], field_name="id"
    )
    for path, local in candidates:
        project_file = files.get(path)
        if project_file is None or not local.is_file():
            continue
        started_from = inputs.get(_uuid(run.input_versions.get(path)))
        if started_from is not None and started_from.sha256 == _digest(local):
            continue
        changed.append((project_file, local))
    return changed


def _vetoed(root: Path) -> bool:
    final = root / "ir_final.json"
    if not final.is_file():
        return True
    issues = json.loads(final.read_text(encoding="utf-8")).get("issues", [])
    return any(issue.get("severity") == "veto" for issue in issues)


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(READ_BLOCK):
            digest.update(block)
    return digest.hexdigest()


def _uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except ValueError:
        return None
