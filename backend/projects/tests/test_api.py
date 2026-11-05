import io
import json
import zipfile
from pathlib import Path
from uuid import uuid4

import boto3
import pytest
from django.conf import settings as django_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client
from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart
from PIL import Image
from pptx import Presentation
from pptx.util import Inches

from projects.models import Project, Run
from projects.storage import UnsafePathError, validate_relative_path

REPOSITORY_ROOT = Path(__file__).parents[3]
LECTURE_SAMPLE = REPOSITORY_ROOT / "pipeline" / "tests" / "fixtures" / "lecture_sample"


def _create_project(client: Client, name: str = "Lecture") -> dict[str, object]:
    # Create one project through the API
    response = client.post(
        "/api/projects",
        data=json.dumps({"name": name}),
        content_type="application/json",
    )
    assert response.status_code == 201
    return response.json()


def _lecture_zip() -> bytes:
    # Build a complete lecture fixture archive in memory
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(LECTURE_SAMPLE.rglob("*")):
            if source.is_file():
                archive.write(source, source.relative_to(LECTURE_SAMPLE).as_posix())
    return stream.getvalue()


@pytest.mark.django_db
def test_project_crud(client: Client) -> None:
    # Exercise project creation listing detail update and deletion
    created = _create_project(client)
    project_id = created["id"]

    listed = client.get("/api/projects")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == project_id

    detail = client.get(f"/api/projects/{project_id}")
    assert detail.status_code == 200
    assert detail.json()["name"] == "Lecture"

    updated = client.patch(
        f"/api/projects/{project_id}",
        data=json.dumps({"name": "Updated lecture"}),
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated lecture"

    deleted = client.delete(f"/api/projects/{project_id}")
    assert deleted.status_code == 204
    assert not Project.objects.filter(id=project_id).exists()


@pytest.mark.django_db
def test_multi_file_upload_replaces_existing_path(client: Client) -> None:
    # Upload multiple files and replace one matching path
    project = _create_project(client)
    project_id = project["id"]
    response = client.post(
        f"/api/projects/{project_id}/upload",
        {
            "files": [
                SimpleUploadedFile("main.tex", b"first"),
                SimpleUploadedFile("notes.txt", b"notes"),
            ]
        },
    )
    assert response.status_code == 200
    paths: list[str] = []
    for record in response.json()["files"]:
        paths.append(record["path"])
    assert paths == ["main.tex", "notes.txt"]

    replaced = client.post(
        f"/api/projects/{project_id}/upload",
        {"files": [SimpleUploadedFile("main.tex", b"second")]},
    )
    assert replaced.status_code == 200
    record = Project.objects.get(id=project_id).files.get(path="main.tex")
    assert record.size == 6


@pytest.mark.django_db
def test_zip_upload_uses_safe_extraction(client: Client) -> None:
    # Reject traversal in an uploaded zip archive
    project = _create_project(client)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("../outside.tex", "unsafe")
    upload = SimpleUploadedFile("project.zip", stream.getvalue())
    response = client.post(
        f"/api/projects/{project['id']}/upload",
        {"files": [upload]},
    )
    assert response.status_code == 400
    assert Project.objects.get(id=project["id"]).files.count() == 0


def test_uploaded_paths_reject_absolute_and_traversal() -> None:
    # Reject unsafe project and artifact style paths
    unsafe = [
        "/tmp/main.tex",
        "../main.tex",
        "figs/../../main.tex",
        r"C:\main.tex",
        "figs//a.png",
        "figs/",
        "",
    ]
    for value in unsafe:
        with pytest.raises(UnsafePathError):
            validate_relative_path(value)


@pytest.mark.django_db
def test_missing_file_put_flow(client: Client) -> None:
    # Fill a missing image slot and clear preflight findings
    project = _create_project(client)
    project_id = project["id"]
    main_source = (LECTURE_SAMPLE / "main.tex").read_bytes()
    uploaded = client.post(
        f"/api/projects/{project_id}/upload",
        {"files": [SimpleUploadedFile("main.tex", main_source)]},
    )
    assert uploaded.status_code == 200

    missing = client.get(f"/api/projects/{project_id}/preflight")
    assert missing.status_code == 200
    assert missing.json()["missing_images"] == ["figs/regression"]
    assert not missing.json()["ok"]

    image = (LECTURE_SAMPLE / "figs" / "regression.png").read_bytes()
    put_data = encode_multipart(
        BOUNDARY,
        {"file": SimpleUploadedFile("regression.png", image, content_type="image/png")},
    )
    filled = client.put(
        f"/api/projects/{project_id}/files/figs/regression",
        data=put_data,
        content_type=MULTIPART_CONTENT,
    )
    assert filled.status_code == 200
    assert Project.objects.get(id=project_id).files.filter(path="figs/regression.png").exists()

    ready = client.get(f"/api/projects/{project_id}/preflight")
    assert ready.status_code == 200
    assert ready.json()["ok"]
    assert ready.json()["missing_images"] == []
    assert ready.json()["critical_blockers"] == []


BEAMER_SOURCE = (
    b"\\documentclass{beamer}\n\\begin{document}\n"
    b"\\begin{frame}{A}\nText\n\\end{frame}\n\\end{document}\n"
)


def _upload(client: Client, project_id: str, files: dict[str, bytes]):
    # Upload named files to a project through the API
    return client.post(
        f"/api/projects/{project_id}/upload",
        {"files": [SimpleUploadedFile(name, body) for name, body in files.items()]},
    )


@pytest.mark.django_db
def test_preflight_explains_a_pdf_only_project(client: Client) -> None:
    # A PDF alone has no source to remediate and says so
    project = _create_project(client)
    assert _upload(client, project["id"], {"slides.pdf": b"%PDF-1.4"}).status_code == 200
    result = client.get(f"/api/projects/{project['id']}/preflight").json()
    assert result["ok"] is False
    assert result["main_file"] is None
    assert result["problem"]["code"] == "no_tex_files"
    assert "PDF" in result["problem"]["message"]


@pytest.mark.django_db
def test_preflight_rejects_tex_without_beamer(client: Client) -> None:
    # Plain LaTeX documents are not Beamer presentations
    project = _create_project(client)
    source = b"\\documentclass{article}\n\\begin{document}x\\end{document}\n"
    _upload(client, project["id"], {"notes.tex": source})
    result = client.get(f"/api/projects/{project['id']}/preflight").json()
    assert result["problem"]["code"] == "no_beamer_main"


@pytest.mark.django_db
def test_preflight_asks_for_a_main_file_when_several_exist(client: Client) -> None:
    # Offer every Beamer candidate and accept an explicit choice
    project = _create_project(client)
    _upload(client, project["id"], {"b.tex": BEAMER_SOURCE, "a.tex": BEAMER_SOURCE})
    result = client.get(f"/api/projects/{project['id']}/preflight").json()
    assert result["ok"] is False
    assert result["problem"]["code"] == "choose_main_file"
    assert result["main_candidates"] == ["a.tex", "b.tex"]

    chosen = client.get(f"/api/projects/{project['id']}/preflight?main_file=b.tex").json()
    assert chosen["ok"] is True
    assert chosen["main_file"] == "b.tex"
    assert chosen["problem"] is None

    invalid = client.get(f"/api/projects/{project['id']}/preflight?main_file=missing.tex")
    assert invalid.status_code == 400


@pytest.mark.django_db
def test_targets_list_only_beamer_files_without_downloading_other_files(client: Client) -> None:
    # The file switcher needs the translatable decks, not every figure in the project
    project = _create_project(client)
    notes = b"\\documentclass{article}\n\\begin{document}x\\end{document}\n"
    _upload(
        client,
        project["id"],
        {"b.tex": BEAMER_SOURCE, "a.tex": BEAMER_SOURCE, "notes.tex": notes, "fig.png": b"png"},
    )
    result = client.get(f"/api/projects/{project['id']}/targets")
    assert result.status_code == 200
    assert result.json() == {"candidates": ["a.tex", "b.tex"]}
    assert client.get(f"/api/projects/{uuid4()}/targets").status_code == 404


@pytest.mark.django_db
def test_remove_project_file(client: Client) -> None:
    # Remove one file from storage and the database
    project = _create_project(client)
    _upload(client, project["id"], {"keep.tex": b"k", "drop.pdf": b"d"})
    response = client.delete(f"/api/projects/{project['id']}/files/drop.pdf")
    assert response.status_code == 200
    assert [item["path"] for item in response.json()["files"]] == ["keep.tex"]
    assert _stored_keys() == [f"projects/{project['id']}/files/keep.tex"]
    assert client.delete(f"/api/projects/{project['id']}/files/drop.pdf").status_code == 404
    assert client.delete(f"/api/projects/{project['id']}/files/..%2Fx").status_code in {400, 404}


@pytest.mark.django_db(transaction=True)
@pytest.mark.tex
@pytest.mark.slow
def test_medium_run_review_and_artifact_downloads(client: Client) -> None:
    # Run the complete fake pipeline and inspect review artifacts
    project = _create_project(client)
    project_id = project["id"]
    upload = SimpleUploadedFile(
        "lecture_sample.zip",
        _lecture_zip(),
        content_type="application/zip",
    )
    uploaded = client.post(
        f"/api/projects/{project_id}/upload",
        {"files": [upload]},
    )
    assert uploaded.status_code == 200

    preflight = client.get(f"/api/projects/{project_id}/preflight")
    assert preflight.status_code == 200
    assert preflight.json()["ok"]
    assert preflight.json()["main_file"] == "main.tex"

    queued = client.post(
        f"/api/projects/{project_id}/runs",
        data=json.dumps(
            {
                "effort": "medium",
                "seed_weak": "slide_04/figure_01",
            }
        ),
        content_type="application/json",
    )
    assert queued.status_code == 202
    run_id = queued.json()["id"]
    run = Run.objects.get(id=run_id)
    assert run.status == Run.Status.SUCCEEDED
    assert run.storage_prefix == f"runs/{run.id}"
    assert run.model_provider == "fake"
    assert run.input_tokens == 24
    assert run.output_tokens == 16

    review = client.get(f"/api/runs/{run_id}/review")
    assert review.status_code == 200
    review_data = review.json()
    figure = None
    for element in review_data["elements"]:
        if element["id"] == "slide_04/figure_01":
            figure = element
            break
    assert figure is not None
    assert figure["status"] == "model_generated"
    assert figure["alt"]
    assert figure["source"]["file"] == "main.tex"
    assert figure["source"]["line_start"] <= figure["source"]["line_end"]
    assert figure["history"]
    assert "visible_pages" in figure
    first_page = review_data["pages"][0]
    assert first_page["thumb_url"].endswith(".png")
    assert "/artifact/thumbs/" in first_page["thumb_url"]
    thumb = client.get(first_page["thumb_url"])
    assert thumb.status_code == 200
    texts = [element["text"] for element in review_data["elements"] if element["text"]]
    assert "Course Logistics" in texts

    listed_runs = client.get(f"/api/projects/{project_id}/runs")
    assert listed_runs.status_code == 200
    assert [item["id"] for item in listed_runs.json()] == [run_id]
    assert review_data["pages"]
    assert review_data["round_history"]

    artifacts = [
        "output/tagged.pdf",
        "output/updated_project.zip",
        "report.html",
        review_data["pages"][0]["image_url"].split("/artifact/", 1)[1],
    ]
    for artifact in artifacts:
        response = client.get(f"/api/runs/{run_id}/artifact/{artifact}")
        assert response.status_code == 200

    traversal = client.get(f"/api/runs/{run_id}/artifact/%2E%2E/manifest.json")
    assert traversal.status_code in {400, 404}

    keys = _stored_keys()
    assert f"runs/{run_id}/output/tagged.pdf" in keys
    assert f"runs/{run_id}/manifest.json" in keys
    assert f"runs/{run_id}/ir_final.json" in keys
    assert not any(key.startswith(f"runs/{run_id}/work/original/") for key in keys)
    assert not any(key.startswith(f"runs/{run_id}/work/marked/") for key in keys)
    assert not list((Path(django_settings.SCRATCH_DIR)).glob("*"))
    page = review_data["pages"][0]
    assert page["width_points"] > 0
    assert page["height_points"] > 0

    deleted = client.delete(f"/api/projects/{project_id}")
    assert deleted.status_code == 204
    assert _stored_keys() == []


def _stored_keys() -> list[str]:
    # List every object key in the test bucket
    client = boto3.client("s3", region_name="us-east-1")
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=django_settings.TEST_BUCKET_NAME):
        for item in page.get("Contents", []):
            keys.append(item["Key"])
    return sorted(keys)


@pytest.mark.django_db
def test_project_files_are_stored_under_plain_keys(client: Client) -> None:
    # Store project files at projects/<id>/files/<path> in the bucket
    project = _create_project(client)
    client.post(
        f"/api/projects/{project['id']}/upload",
        {"files": [SimpleUploadedFile("main.tex", b"x")]},
    )
    assert _stored_keys() == [f"projects/{project['id']}/files/main.tex"]


@pytest.mark.django_db
def test_artifact_rejects_traversal_and_unlisted_paths(client: Client) -> None:
    # Only approved relative artifact paths are served
    project = Project.objects.create(name="p")
    run = Run.objects.create(
        project=project,
        effort="low",
        model_provider="fake",
        storage_prefix="runs/abc",
    )
    for path in ["manifest.json", "output/../manifest.json", "work/original/main.pdf"]:
        response = client.get(f"/api/runs/{run.id}/artifact/{path}")
        assert response.status_code in {400, 404}
    missing = client.get(f"/api/runs/{run.id}/artifact/report.html")
    assert missing.status_code == 404


def test_ensure_bucket_is_idempotent(settings) -> None:
    # Create a missing bucket once and leave an existing one alone
    options = {**settings.STORAGES["default"]["OPTIONS"], "bucket_name": "another-bucket"}
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {**settings.STORAGES["default"], "OPTIONS": options},
    }
    first = io.StringIO()
    call_command("ensure_bucket", stdout=first)
    second = io.StringIO()
    call_command("ensure_bucket", stdout=second)
    assert "Created bucket another-bucket" in first.getvalue()
    assert "already exists" in second.getvalue()


def test_backend_code_follows_storage_rules() -> None:
    # Backend code never opens stored files by path or uses presigned URLs
    forbidden = [
        "generate_presigned",
        "presigned",
        "FileSystemStorage",
        "MEDIA_ROOT",
        "default_storage.path(",
        'querystring_auth": True',
        "put_object_acl",
        "default_acl",
    ]
    backend_root = Path(__file__).parents[2]
    for source in list((backend_root / "projects").rglob("*.py")) + [
        backend_root / "config" / "settings.py"
    ]:
        if source.name == "test_api.py":
            continue
        text = source.read_text(encoding="utf-8")
        for word in forbidden:
            assert word not in text, f"{word} found in {source.name}"


def _deck_bytes() -> bytes:
    # A three-slide deck with one undescribed picture and one slide without a title
    stream = io.BytesIO()
    picture = io.BytesIO()
    Image.new("RGB", (60, 40), "red").save(picture, format="PNG")
    picture.seek(0)
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = "Gradient descent"
    slide.shapes.add_picture(picture, Inches(1), Inches(2))
    presentation.slides.add_slide(presentation.slide_layouts[5]).shapes.title.text = "Summary"
    untitled = presentation.slides.add_slide(presentation.slide_layouts[6])
    untitled.shapes.add_textbox(Inches(1), Inches(2), Inches(4), Inches(1)).text = "Questions"
    presentation.save(stream)
    return stream.getvalue()


@pytest.mark.django_db
def test_targets_include_powerpoint_decks_but_not_office_lock_files(client: Client) -> None:
    # A deck is translatable by name; Office's "~$" lock files are not decks
    project = _create_project(client)
    _upload(client, project["id"], {"talk.pptx": _deck_bytes(), "~$talk.pptx": b"lock"})
    result = client.get(f"/api/projects/{project['id']}/targets")
    assert result.json() == {"candidates": ["talk.pptx"]}


@pytest.mark.django_db(transaction=True)
def test_powerpoint_run_returns_an_updated_deck(client: Client) -> None:
    # Upload a deck, translate it with the fake model, then review and download the result
    project = _create_project(client)
    project_id = project["id"]
    _upload(client, project_id, {"talk.pptx": _deck_bytes()})
    preflight = client.get(f"/api/projects/{project_id}/preflight")
    assert preflight.json()["ok"]
    assert preflight.json()["main_file"] == "talk.pptx"
    queued = client.post(
        f"/api/projects/{project_id}/runs",
        data=json.dumps({"effort": "low", "main_file": "talk.pptx"}),
        content_type="application/json",
    )
    assert queued.status_code == 202
    run = Run.objects.get(id=queued.json()["id"])
    assert run.status == Run.Status.SUCCEEDED, run.error_message
    assert run.main_file == "talk.pptx"
    review = client.get(f"/api/runs/{run.id}/review").json()
    assert review["source_format"] == "pptx"
    assert {"label": "Accessible PowerPoint (.pptx)", "path": "output/updated.pptx"} in review[
        "outputs"
    ]
    assert {"label": "Changes (Text File)", "path": "output/changes.txt"} in review["outputs"]
    changes = client.get(f"/api/runs/{run.id}/artifact/output/changes.txt")
    assert changes.status_code == 200
    figure = next(e for e in review["elements"] if e["type"] == "figure")
    assert figure["alt"]
    assert figure["image_url"]
    assert client.get(figure["image_url"]).status_code == 200
    download = client.get(f"/api/runs/{run.id}/artifact/output/updated.pptx")
    assert download.status_code == 200
    updated = Presentation(io.BytesIO(b"".join(download.streaming_content)))
    picture = next(shape for shape in updated.slides[0].shapes if shape.shape_type == 13)
    assert picture._element.xpath("./p:nvPicPr/p:cNvPr")[0].get("descr")
    # The untitled slide gets a proposed title, explained in the review
    title = next(e for e in review["elements"] if e["id"] == "slide_03/heading_01")
    assert title["text"] and "Proposed title" in title["note"]
    assert updated.slides[2].shapes[0].text_frame.text == title["text"]
