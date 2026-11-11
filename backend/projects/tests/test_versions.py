import json
from pathlib import Path

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import Client

from accounts.models import User
from projects.models import FileVersion, Project, ProjectFile, Run
from projects.storage import ensure_versions, project_storage_path, save_project_file
from projects.tests.test_api import _create_project, _deck_bytes, _stored_keys, _upload
from projects.versions import save_run_outputs, snapshot_inputs


def _versions(client: Client, project_id: str, path: str) -> list[dict[str, object]]:
    response = client.get(f"/api/projects/{project_id}/versions", {"path": path})
    assert response.status_code == 200
    return response.json()


def _download(client: Client, project_id: str, version: dict[str, object]) -> bytes:
    response = client.get(f"/api/projects/{project_id}/versions/{version['id']}/download")
    assert response.status_code == 200
    return b"".join(response.streaming_content)


def _working_copy(project_id: str, path: str) -> bytes:
    with default_storage.open(project_storage_path(project_id, path), "rb") as stored:
        return stored.read()


def _run(client: Client, project_id: str, path: str) -> Run:
    queued = client.post(
        f"/api/projects/{project_id}/runs",
        data=json.dumps({"effort": "low", "main_file": path}),
        content_type="application/json",
    )
    assert queued.status_code == 202
    return Run.objects.get(id=queued.json()["id"])


@pytest.mark.django_db
def test_uploading_again_keeps_the_earlier_file_as_a_version(client: Client) -> None:
    project = _create_project(client)
    _upload(client, project["id"], {"notes.tex": b"first"})
    _upload(client, project["id"], {"notes.tex": b"second"})
    # The same bytes again add nothing
    _upload(client, project["id"], {"notes.tex": b"second"})
    versions = _versions(client, project["id"], "notes.tex")
    assert [(v["number"], v["source"], v["current"]) for v in versions] == [
        (2, "upload", True),
        (1, "upload", False),
    ]
    assert _download(client, project["id"], versions[1]) == b"first"
    files = client.get(f"/api/projects/{project['id']}").json()["files"]
    assert (files[0]["version"], files[0]["versions"]) == (2, 2)


@pytest.mark.django_db
def test_a_file_from_before_versions_keeps_its_content_as_version_one(user: User) -> None:
    project = Project.objects.create(owner=user, name="Old")
    default_storage.save(project_storage_path(project.id, "a.tex"), ContentFile(b"old"))
    ProjectFile.objects.create(project=project, path="a.tex", size=3, sha256="x")
    save_project_file(project, "a.tex", ContentFile(b"new", name="a.tex"))
    record = ProjectFile.objects.get(project=project)
    assert [(v.number, v.size) for v in record.versions.order_by("number")] == [(1, 3), (2, 3)]
    assert record.current_version.number == 2


@pytest.mark.django_db
def test_restoring_adds_the_earlier_version_as_the_newest(client: Client) -> None:
    project = _create_project(client)
    _upload(client, project["id"], {"notes.tex": b"first"})
    _upload(client, project["id"], {"notes.tex": b"second"})
    first = _versions(client, project["id"], "notes.tex")[1]
    response = client.post(f"/api/projects/{project['id']}/versions/{first['id']}/restore")
    assert response.status_code == 200
    newest = response.json()[0]
    assert (newest["number"], newest["source"], newest["restored_from"]) == (3, "restore", 1)
    assert newest["current"]
    assert _working_copy(project["id"], "notes.tex") == b"first"


@pytest.mark.django_db
def test_versions_belong_to_their_owner(client: Client) -> None:
    project = _create_project(client)
    _upload(client, project["id"], {"notes.tex": b"first"})
    version = _versions(client, project["id"], "notes.tex")[0]
    other = User.objects.create_user(
        "other", "correct-horse-battery", first_name="O", last_name="U"
    )
    stranger = Client()
    stranger.force_login(other)
    base = f"/api/projects/{project['id']}/versions"
    assert stranger.get(base, {"path": "notes.tex"}).status_code == 404
    assert stranger.get(f"{base}/{version['id']}/download").status_code == 404
    assert stranger.post(f"{base}/{version['id']}/restore").status_code == 404


@pytest.mark.django_db
def test_deleting_a_project_removes_every_version(client: Client) -> None:
    project = _create_project(client)
    _upload(client, project["id"], {"notes.tex": b"first"})
    _upload(client, project["id"], {"notes.tex": b"second"})
    assert client.delete(f"/api/projects/{project['id']}").status_code == 204
    assert _stored_keys() == []


@pytest.mark.django_db(transaction=True)
def test_running_again_starts_from_the_last_result_and_keeps_edits(client: Client) -> None:
    project = _create_project(client)
    project_id = project["id"]
    _upload(client, project_id, {"talk.pptx": _deck_bytes()})

    first = _run(client, project_id, "talk.pptx")
    assert first.status == Run.Status.SUCCEEDED, first.error_message
    payload = client.get(f"/api/runs/{first.id}").json()
    assert (payload["input_version"], payload["output_version"]) == (1, 2)
    assert payload["version_outcome"] == "saved"
    made = _versions(client, project_id, "talk.pptx")[0]
    assert (made["source"], made["run_id"], made["current"]) == ("update", str(first.id), True)
    # The working copy is now the accessible deck, which the run also offers for download
    download = client.get(f"/api/runs/{first.id}/artifact/output/updated.pptx")
    assert _working_copy(project_id, "talk.pptx") == b"".join(download.streaming_content)

    # Running the accessible deck again finds nothing to change, so no version is added
    second = _run(client, project_id, "talk.pptx")
    payload = client.get(f"/api/runs/{second.id}").json()
    assert (payload["input_version"], payload["output_version"]) == (2, None)
    assert payload["version_outcome"] == "unchanged"
    assert len(_versions(client, project_id, "talk.pptx")) == 2

    # A deck the person edited and uploaded again is where the next run starts
    _upload(client, project_id, {"talk.pptx": _deck_bytes()})
    third = _run(client, project_id, "talk.pptx")
    payload = client.get(f"/api/runs/{third.id}").json()
    assert (payload["input_version"], payload["output_version"]) == (3, 4)


def _finished_run(user: User, tmp_path: Path, issues: list[dict[str, object]]) -> Run:
    # A run of notes.tex whose output changed it, finished with the given final issues
    project = Project.objects.create(owner=user, name="P")
    save_project_file(project, "notes.tex", ContentFile(b"before", name="notes.tex"))
    run = Run.objects.create(
        project=project, effort="low", model_provider="fake", main_file="notes.tex"
    )
    snapshot_inputs(run)
    output = tmp_path / "output" / "updated_project"
    output.mkdir(parents=True)
    (output / "notes.tex").write_bytes(b"after")
    (tmp_path / "ir_final.json").write_text(json.dumps({"issues": issues}), encoding="utf-8")
    return run


@pytest.mark.django_db
def test_a_result_that_failed_a_check_is_not_saved(user: User, tmp_path: Path) -> None:
    run = _finished_run(user, tmp_path, [{"code": "visual_change", "severity": "veto"}])
    assert save_run_outputs(run, tmp_path) == Run.VersionOutcome.NOT_SAVED
    assert FileVersion.objects.count() == 1
    assert _working_copy(run.project_id, "notes.tex") == b"before"


@pytest.mark.django_db
def test_a_file_changed_during_the_run_stays_current(user: User, tmp_path: Path) -> None:
    run = _finished_run(user, tmp_path, [])
    save_project_file(run.project, "notes.tex", ContentFile(b"edited", name="notes.tex"))
    assert save_run_outputs(run, tmp_path) == Run.VersionOutcome.SAVED_NOT_CURRENT
    record = ProjectFile.objects.get(project=run.project)
    assert [v.number for v in record.versions.all()] == [3, 2, 1]
    assert record.current_version.number == 2
    assert _working_copy(run.project_id, "notes.tex") == b"edited"


@pytest.mark.django_db
def test_ensure_versions_is_idempotent(user: User) -> None:
    project = Project.objects.create(owner=user, name="P")
    record = save_project_file(project, "a.tex", ContentFile(b"x", name="a.tex"))
    assert ensure_versions(record).id == ensure_versions(record).id
    assert record.versions.count() == 1
