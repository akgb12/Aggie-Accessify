import hashlib
import json
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, BinaryIO
from uuid import uuid4

from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Max

from a11y_pipeline.bundle.unzip import safe_extract_zip
from projects.models import FileVersion, Project, ProjectFile, Run


class UnsafePathError(ValueError):
    pass


def validate_relative_path(value: str) -> str:
    # Validate one relative POSIX storage path
    if not value or "\x00" in value or "\\" in value:
        raise UnsafePathError("Path must be a nonempty relative POSIX path")
    if value.startswith("/") or value.endswith("/") or "//" in value:
        raise UnsafePathError("Path must not contain empty segments")
    posix_path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise UnsafePathError("Absolute paths are not allowed")
    if ".." in posix_path.parts or "." in posix_path.parts:
        raise UnsafePathError("Path traversal is not allowed")
    normalized = posix_path.as_posix()
    if normalized in {"", "."}:
        raise UnsafePathError("Path must name a file")
    return normalized


def project_storage_path(project_id: object, relative_path: str) -> str:
    # Build a validated project storage name
    safe_path = validate_relative_path(relative_path)
    return f"projects/{project_id}/files/{safe_path}"


def run_storage_key(run_id: object, relative_path: str) -> str:
    # Build a validated run output storage name
    safe_path = validate_relative_path(relative_path)
    return f"runs/{run_id}/{safe_path}"


@contextmanager
def scratch_dir(name: str) -> Iterator[Path]:
    # Provide a local working folder that is always removed afterwards
    root = Path(settings.SCRATCH_DIR) / f"{name}-{uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=False)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def save_project_file(
    project: Project,
    relative_path: str,
    content: BinaryIO,
) -> ProjectFile:
    # Replace one project file through Django storage, keeping what it held before as a version
    safe_path = validate_relative_path(relative_path)
    storage_path = project_storage_path(project.id, safe_path)
    existing = ProjectFile.objects.filter(project=project, path=safe_path).first()
    if existing is not None:
        ensure_versions(existing)
    if default_storage.exists(storage_path):
        default_storage.delete(storage_path)
    saved_path = default_storage.save(storage_path, File(content))
    if saved_path != storage_path:
        default_storage.delete(saved_path)
        raise RuntimeError("Storage changed the requested project path")
    digest = hashlib.sha256()
    size = 0
    with default_storage.open(storage_path, "rb") as stored:
        while True:
            block = stored.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
            size += len(block)
    with transaction.atomic():
        record, _ = ProjectFile.objects.update_or_create(
            project=project,
            path=safe_path,
            defaults={"size": size, "sha256": digest.hexdigest()},
        )
    record_upload(record)
    return record


# Every state a project file has been in is kept as a version, so nothing a person uploads or a
# run produces is ever lost. The working copy under files/ holds the current version, and each
# version keeps its own copy under versions/.


def version_storage_path(project_id: object, version_id: object) -> str:
    return f"projects/{project_id}/versions/{version_id}"


def ensure_versions(project_file: ProjectFile) -> FileVersion:
    # The file's current version, saving what it holds now as its first version when it
    # was added before versions were kept
    if project_file.current_version_id is not None:
        return project_file.current_version
    working = project_storage_path(project_file.project_id, project_file.path)
    with default_storage.open(working, "rb") as stream:
        return new_version(project_file, stream, FileVersion.Source.UPLOAD, make_current=True)


def record_upload(project_file: ProjectFile) -> FileVersion | None:
    # Keep a newly uploaded working copy as a version; uploading the same bytes again adds none
    current = project_file.current_version
    if current is not None and current.sha256 == project_file.sha256:
        return None
    working = project_storage_path(project_file.project_id, project_file.path)
    with default_storage.open(working, "rb") as stream:
        return new_version(project_file, stream, FileVersion.Source.UPLOAD, make_current=True)


def restore_version(version: FileVersion) -> FileVersion:
    # Make an earlier version current again by adding a copy of it, so history is never
    # rewritten and the version being replaced can itself be restored later
    project_file = version.project_file
    with default_storage.open(version_storage_path(project_file.project_id, version.id)) as stream:
        return new_version(
            project_file,
            stream,
            FileVersion.Source.RESTORE,
            make_current=True,
            restored_from=version,
        )


def delete_versions(project_file: ProjectFile) -> None:
    # Remove the stored copies of every version of one file
    for version_id in project_file.versions.values_list("id", flat=True):
        key = version_storage_path(project_file.project_id, version_id)
        if default_storage.exists(key):
            default_storage.delete(key)


def new_version(
    project_file: ProjectFile,
    stream: BinaryIO,
    source: str,
    *,
    make_current: bool,
    run: Run | None = None,
    restored_from: FileVersion | None = None,
) -> FileVersion:
    content = stream.read()
    with transaction.atomic():
        # Numbering under a lock keeps two saves of one file from taking the same number
        locked = ProjectFile.objects.select_for_update().get(pk=project_file.pk)
        highest = locked.versions.aggregate(highest=Max("number"))["highest"] or 0
        version = FileVersion(
            project_file=locked,
            number=highest + 1,
            source=source,
            run=run,
            restored_from=restored_from,
            size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )
        _write(version_storage_path(locked.project_id, version.id), content)
        version.save()
        if make_current:
            _write(project_storage_path(locked.project_id, locked.path), content)
            locked.current_version = version
            locked.size = version.size
            locked.sha256 = version.sha256
            locked.save(update_fields=["current_version", "size", "sha256", "uploaded_at"])
    project_file.refresh_from_db()
    return version


def _write(key: str, content: bytes) -> None:
    validate_relative_path(key)
    if default_storage.exists(key):
        default_storage.delete(key)
    saved = default_storage.save(key, File(BytesIO(content)))
    if saved != key:
        default_storage.delete(saved)
        raise RuntimeError("Storage changed the requested version path")


def upload_project_files(project: Project, uploads: list[object]) -> list[ProjectFile]:
    # Save a zip bundle or multiple individual uploads
    if not uploads:
        raise ValueError("At least one file is required")
    if len(uploads) == 1 and str(uploads[0].name).lower().endswith(".zip"):
        return _upload_zip(project, uploads[0])
    saved: list[ProjectFile] = []
    for upload in uploads:
        if str(upload.name).lower().endswith(".zip"):
            raise ValueError("A zip archive must be uploaded by itself")
        saved.append(save_project_file(project, str(upload.name), upload))
    return saved


def save_missing_slot(project: Project, slot: str, upload: object) -> ProjectFile:
    # Fill a missing path while preserving the uploaded extension
    safe_slot = validate_relative_path(slot)
    upload_name = validate_relative_path(str(upload.name))
    destination = safe_slot
    if not PurePosixPath(safe_slot).suffix:
        suffix = PurePosixPath(upload_name).suffix
        if suffix:
            destination = f"{safe_slot}{suffix}"
    return save_project_file(project, destination, upload)


def materialize_project(
    project: Project,
    destination: Path,
    only_suffixes: tuple[str, ...] | None = None,
) -> None:
    # Copy project files (all, or only some file types) from storage into a bundle folder
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    for project_file in project.files.all():
        relative = validate_relative_path(project_file.path)
        if only_suffixes is not None and not relative.lower().endswith(only_suffixes):
            continue
        output = (root / relative).resolve()
        if not output.is_relative_to(root):
            raise UnsafePathError("Stored project path escapes the bundle")
        output.parent.mkdir(parents=True, exist_ok=True)
        storage_path = project_storage_path(project.id, relative)
        with default_storage.open(storage_path, "rb") as source, output.open("wb") as target:
            shutil.copyfileobj(source, target)


def delete_project_files(project: Project) -> None:
    # Delete all project inputs, and every version of them, through Django storage
    for project_file in project.files.all():
        delete_versions(project_file)
        storage_path = project_storage_path(project.id, project_file.path)
        if default_storage.exists(storage_path):
            default_storage.delete(storage_path)


def delete_project_file(project: Project, relative_path: str) -> bool:
    # Delete one project input from storage and the database
    safe_path = validate_relative_path(relative_path)
    storage_path = project_storage_path(project.id, safe_path)
    if default_storage.exists(storage_path):
        default_storage.delete(storage_path)
    for project_file in ProjectFile.objects.filter(project=project, path=safe_path):
        delete_versions(project_file)
    deleted, _ = ProjectFile.objects.filter(project=project, path=safe_path).delete()
    return deleted > 0


def upload_run_folder(run_id: object, folder: Path, skip: tuple[str, ...] = ()) -> int:
    # Upload one finished run folder to runs/<run_id>/ and return the file count
    root = folder.resolve()
    uploaded = 0
    for source in sorted(root.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(root).as_posix()
        if any(relative == name or relative.startswith(f"{name}/") for name in skip):
            continue
        key = run_storage_key(run_id, relative)
        if default_storage.exists(key):
            default_storage.delete(key)
        with source.open("rb") as stream:
            saved = default_storage.save(key, File(stream))
        if saved != key:
            default_storage.delete(saved)
            raise RuntimeError("Storage changed the requested run path")
        uploaded += 1
    return uploaded


def download_run_files(prefix: str, relative_paths: list[str], destination: Path) -> None:
    # Copy the named stored run files that exist into a local folder, keeping their paths
    root = destination.resolve()
    for relative in relative_paths:
        key = f"{prefix}/{validate_relative_path(relative)}"
        if not default_storage.exists(key):
            continue
        output = (root / relative).resolve()
        if not output.is_relative_to(root):
            raise UnsafePathError("Stored run path escapes the folder")
        output.parent.mkdir(parents=True, exist_ok=True)
        with default_storage.open(key, "rb") as source, output.open("wb") as target:
            shutil.copyfileobj(source, target)


def run_file_exists(prefix: str, relative_path: str) -> bool:
    # Check for one stored run file by its relative path
    return default_storage.exists(f"{prefix}/{validate_relative_path(relative_path)}")


def read_run_json(prefix: str, relative_path: str) -> Any:
    # Read and decode one JSON file stored with a run
    key = f"{prefix}/{validate_relative_path(relative_path)}"
    with default_storage.open(key, "rb") as stored:
        return json.loads(stored.read().decode("utf-8"))


def list_run_files(prefix: str, folder: str) -> list[str]:
    # List file names directly inside one stored run folder
    _, names = default_storage.listdir(f"{prefix}/{validate_relative_path(folder)}")
    return sorted(names)


def delete_prefix(prefix: str) -> None:
    # Delete every stored object below a prefix
    directories, names = default_storage.listdir(prefix)
    for name in names:
        default_storage.delete(f"{prefix}/{name}")
    for directory in directories:
        delete_prefix(f"{prefix}/{directory}")


def _upload_zip(project: Project, upload: object) -> list[ProjectFile]:
    # Extract one archive with the pipeline safety checks
    with scratch_dir("upload") as root:
        archive_path = root / "upload.zip"
        with archive_path.open("wb") as archive:
            for chunk in upload.chunks():
                archive.write(chunk)
        extracted_root = root / "extracted"
        paths = safe_extract_zip(archive_path, extracted_root)
        saved: list[ProjectFile] = []
        for path in paths:
            with (extracted_root / path).open("rb") as source:
                saved.append(save_project_file(project, path, source))
        return saved
