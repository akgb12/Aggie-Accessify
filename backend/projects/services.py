from pathlib import Path, PurePosixPath
from typing import Any

from django.core.files.storage import default_storage

from a11y_pipeline.adapters import adapter_name_for, get_adapter
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.bundle.mainfile import list_beamer_main_files, list_main_files
from projects.models import Project, Run
from projects.storage import (
    delete_prefix,
    delete_project_files,
    list_run_files,
    materialize_project,
    read_run_json,
    scratch_dir,
    validate_relative_path,
)

DOWNLOADABLE_ARTIFACTS = {
    "output/tagged.pdf",
    "output/updated_project.zip",
    "output/updated.pptx",
    "output/changes.diff",
    "report.html",
}
# What a finished Beamer run offers; PowerPoint runs list their own outputs in the manifest
BEAMER_OUTPUTS = [
    {"label": "Tagged PDF", "path": "output/tagged.pdf"},
    {"label": "Updated project (.zip)", "path": "output/updated_project.zip"},
    {"label": "Report", "path": "report.html"},
]


def project_preflight(project: Project, main_file: str | None = None) -> dict[str, object]:
    # Run pipeline preflight against files from Django storage
    with scratch_dir("preflight") as scratch:
        bundle_root = scratch / "bundle"
        materialize_project(project, bundle_root)
        candidates = list_main_files(bundle_root)
        if main_file is None:
            problem = _main_file_problem(bundle_root, candidates)
            if problem is not None:
                return _blocked_preflight(problem, candidates)
        bundle = Bundle.from_path(bundle_root, main_file)
        result = get_adapter(adapter_name_for(bundle.main_file)).preflight(bundle)
        issues: list[dict[str, object]] = []
        for issue in result.issues:
            issues.append(
                {
                    "code": issue.code,
                    "severity": issue.severity,
                    "message": issue.message,
                    "source_file": issue.source_file,
                    "line": issue.line,
                    "dependency": issue.dependency,
                }
            )
        return {
            "ok": result.ok and not result.missing_images,
            "main_file": bundle.main_file,
            "main_candidates": candidates,
            "problem": None,
            "missing_images": result.missing_images,
            "critical_blockers": result.missing_critical,
            "issues": issues,
        }


def _main_file_problem(root: Path, candidates: list[str]) -> dict[str, str] | None:
    # Explain why no single main file (Beamer source or PowerPoint deck) can be chosen yet
    if not any(root.rglob("*.tex")) and not any(root.rglob("*.pptx")):
        return {
            "code": "no_tex_files",
            "message": (
                "No slides were found. Upload a PowerPoint (.pptx) deck, or the Beamer (.tex) "
                "source of your slides (a .zip of the project works best); a PDF alone "
                "cannot be remediated."
            ),
        }
    if not candidates:
        return {
            "code": "no_beamer_main",
            "message": (
                "None of the .tex files is a Beamer presentation "
                "(it needs \\documentclass{beamer} and a document body)."
            ),
        }
    if len(candidates) > 1:
        return {
            "code": "choose_main_file",
            "message": (
                f"This project has {len(candidates)} slide files. Choose which one to process."
            ),
        }
    return None


def _blocked_preflight(problem: dict[str, str], candidates: list[str]) -> dict[str, object]:
    # Build a preflight result for a project that cannot run yet
    return {
        "ok": False,
        "main_file": None,
        "main_candidates": candidates,
        "problem": problem,
        "missing_images": [],
        "critical_blockers": [],
        "issues": [],
    }


def project_targets(project: Project) -> list[str]:
    # List what can be translated: Beamer sources (read to check) and PowerPoint decks (by name)
    with scratch_dir("targets") as scratch:
        materialize_project(project, scratch / "bundle", only_suffixes=(".tex",))
        beamer = list_beamer_main_files(scratch / "bundle")
    decks = [
        path
        for path in project.files.values_list("path", flat=True)
        if path.lower().endswith(".pptx")
        and not PurePosixPath(path).name.startswith("~$")
        and "__MACOSX" not in PurePosixPath(path).parts
    ]
    return sorted([*beamer, *decks])


def artifact_key(run: Run, relative_path: str) -> str:
    # Resolve one approved downloadable run artifact to its storage key
    relative = validate_relative_path(relative_path)
    allowed = relative in DOWNLOADABLE_ARTIFACTS
    path = PurePosixPath(relative)
    page_image = path.parts[0] in {"pages", "thumbs", "figures"}
    if len(path.parts) == 2 and page_image and path.suffix.lower() == ".png":
        allowed = True
    if not allowed:
        raise ValueError("Artifact path is not downloadable")
    if not run.storage_prefix:
        raise FileNotFoundError(relative)
    key = f"{validate_relative_path(run.storage_prefix)}/{relative}"
    if not default_storage.exists(key):
        raise FileNotFoundError(relative)
    return key


def build_review(run: Run) -> dict[str, object]:
    # Build the review payload from final run artifacts in storage
    prefix = validate_relative_path(run.storage_prefix)
    ir = read_run_json(prefix, "ir_final.json")
    issues_by_element: dict[str, list[dict[str, object]]] = {}
    document_issues: list[dict[str, object]] = []
    for issue in ir.get("issues", []):
        element_id = issue.get("element_id")
        if element_id:
            issues_by_element.setdefault(element_id, []).append(issue)
        else:
            document_issues.append(issue)
    elements: list[dict[str, object]] = []
    for element_id, element in ir["elements"].items():
        render = element["render"]
        accessibility = element["accessibility"]
        elements.append(
            {
                "id": element_id,
                "type": element["semantic_type"],
                "role": accessibility.get("role"),
                "status": accessibility["status"],
                "pages": render["pages"],
                "bbox": render.get("bbox"),
                "anchor": render.get("anchor"),
                "alt": accessibility.get("alt_text"),
                "extended_description": accessibility.get("extended_description"),
                "visible_pages": element.get("attrs", {}).get("visible_pages"),
                "image_url": _figure_image_url(run, element),
                "text": _text_excerpt(element.get("content", {})),
                "source": _source_payload(element.get("source")),
                "history": element.get("history", []),
                "issues": issues_by_element.get(element_id, []),
            }
        )
    history: list[dict[str, object]] = []
    for name in list_run_files(prefix, "candidates"):
        if name.endswith(".json"):
            history.append(read_run_json(prefix, f"candidates/{name}"))
    manifest = read_run_json(prefix, "manifest.json")
    return {
        "run_id": str(run.id),
        "render_engine": manifest.get("versions", {}).get("render_engine"),
        "source_format": ir.get("source_format", "tex-beamer"),
        "outputs": manifest.get("outputs") or BEAMER_OUTPUTS,
        "containers": ir["containers"],
        "elements": elements,
        "pages": _page_payloads(run, manifest),
        "scores": {"accessibility": run.a_score, "fidelity": run.f_score},
        "stop_reason": run.stop_reason,
        "round_history": history,
        "issues": document_issues,
    }


def _figure_image_url(run: Run, element: dict[str, Any]) -> str | None:
    # PowerPoint runs keep the picture each description was written for
    image = element.get("attrs", {}).get("image")
    return f"/api/runs/{run.id}/artifact/{image}" if isinstance(image, str) else None


def _text_excerpt(content: dict[str, Any]) -> str | None:
    # Return a short readable excerpt of an element's text or formula
    value = content.get("text") or content.get("tex")
    if not isinstance(value, str) or not value.strip():
        return None
    value = " ".join(value.split())
    return value if len(value) <= 200 else f"{value[:199]}…"


def _source_payload(source: dict[str, Any] | None) -> dict[str, object] | None:
    # Keep only the source location fields the review view needs
    if not source:
        return None
    return {
        "file": source.get("file"),
        "line_start": source.get("line_start"),
        "line_end": source.get("line_end"),
    }


def _page_payloads(run: Run, manifest: dict[str, Any]) -> list[dict[str, object]]:
    # Pair manifest page sizes with artifact URLs for the rendered images
    pages: list[dict[str, object]] = []
    for page in manifest.get("pages", []):
        pages.append(
            {
                "number": page["number"],
                "image_url": f"/api/runs/{run.id}/artifact/{page['image']}",
                "thumb_url": f"/api/runs/{run.id}/artifact/{page.get('thumb') or page['image']}",
                "width_points": page["width_points"],
                "height_points": page["height_points"],
            }
        )
    return pages


def delete_project_completely(project: Project) -> None:
    # Remove a project's source files, every run's stored output, then the rows
    delete_project_files(project)
    for run in project.runs.all():
        if run.storage_prefix:
            delete_prefix(run.storage_prefix)
    project.delete()
