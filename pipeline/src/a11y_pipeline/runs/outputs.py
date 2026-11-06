import json
import shutil
from pathlib import Path
from typing import Any

from a11y_pipeline.adapters.docx.tagged_pdf import repair_document_tags
from a11y_pipeline.adapters.pptx.tagged_pdf import export_tagged_pdf
from a11y_pipeline.evaluation.verapdf import run_verapdf
from a11y_pipeline.ir.models import Issue
from a11y_pipeline.runs.manifest import write_manifest

# Raise this whenever a run gains a download, or a download changes, that can be built from
# the files a finished run already keeps. Older runs are then brought up to date without
# asking the model again. Version 1: tagged PDF, changes as a text file, format labels.
OUTPUTS_VERSION = 1


def write_office_outputs(output_dir: Path) -> tuple[list[dict[str, str]], list[Issue]]:
    # The downloads made from the updated deck or document alone, for a new run or an older
    # one; each is made only when it is missing
    changes = output_dir / "changes.diff"
    if changes.is_file() and not (output_dir / "changes.txt").is_file():
        # The list of changes is plain text, so it is offered as a file any computer opens
        shutil.copy2(changes, output_dir / "changes.txt")
    updated = _updated_file(output_dir)
    if updated is None:
        return [], []
    issues: list[Issue] = []
    pdf = output_dir / "tagged.pdf"
    if not pdf.is_file():
        issues = _export_pdf(updated, pdf)
    return office_outputs(updated.suffix.lower(), pdf.is_file()), issues


def _updated_file(output_dir: Path) -> Path | None:
    for name in ("updated.pptx", "updated.docx"):
        if (output_dir / name).is_file():
            return output_dir / name
    return None


def refresh_run_outputs(root: Path) -> bool:
    # Bring a finished run's downloads up to the current version; True when anything changed
    manifest_path = root / "manifest.json"
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    if int(manifest.get("outputs_version", 0)) >= OUTPUTS_VERSION:
        return False
    output_dir = root / "output"
    if _updated_file(output_dir) is not None:
        manifest["outputs"], _ = write_office_outputs(output_dir)
    manifest["outputs_version"] = OUTPUTS_VERSION
    write_manifest(manifest_path, manifest)
    return True


OFFICE_LABELS = {
    ".pptx": "Accessible PowerPoint (.pptx)",
    ".docx": "Accessible Word document (.docx)",
}


def office_outputs(suffix: str, pdf_made: bool = False) -> list[dict[str, str]]:
    # What a person can download from a finished PowerPoint or Word run. Both files are
    # accessible, so each is named by its format, not by how it is made.
    outputs = [{"label": OFFICE_LABELS[suffix], "path": f"output/updated{suffix}"}]
    if pdf_made:
        outputs.append({"label": "Accessible PDF (.pdf)", "path": "output/tagged.pdf"})
    outputs.append({"label": "Changes (Text File)", "path": "output/changes.txt"})
    return outputs


def _export_pdf(updated: Path, destination: Path) -> list[Issue]:
    # The tagged PDF is an extra download; when it cannot be made the file is still returned
    result = export_tagged_pdf(updated, destination)
    if result.pdf is not None and updated.suffix.lower() == ".docx":
        repair_document_tags(result.pdf, updated)
    if result.pdf is None:
        return [
            Issue(
                element_id=None,
                code="tagged_pdf_unavailable",
                severity="warning",
                message=f"No tagged PDF was made: {result.message}",
            )
        ]
    check = run_verapdf(result.pdf)
    if check.ran and not check.passed:
        return [
            Issue(
                element_id=None,
                code="tagged_pdf_not_compliant",
                severity="warning",
                message="veraPDF found parts of the tagged PDF that do not meet PDF/UA",
                details={"pass_rate": check.pass_rate},
            )
        ]
    return []
