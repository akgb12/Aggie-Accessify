import json
import shutil
from pathlib import Path

from pptx import Presentation

from a11y_pipeline.adapters.pptx.render import find_soffice
from a11y_pipeline.runs.outputs import OUTPUTS_VERSION, refresh_run_outputs

TITLE_ONLY = 5


def _old_pptx_run(root: Path) -> Path:
    # A finished PowerPoint run from before the current outputs: a deck, a diff and a manifest
    # that lists only the deck and the diff
    output = root / "output"
    output.mkdir(parents=True)
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[TITLE_ONLY])
    slide.shapes.title.text = "Agents"
    presentation.save(str(output / "updated.pptx"))
    (output / "changes.diff").write_text("--- slide 1 title\n+++ updated\n", encoding="utf-8")
    manifest = {
        "run_id": "old",
        "outputs": [
            {"label": "Accessible PowerPoint (.pptx)", "path": "output/updated.pptx"},
            {"label": "Changes", "path": "output/changes.diff"},
        ],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _manifest(root: Path) -> dict[str, object]:
    return json.loads((root / "manifest.json").read_text(encoding="utf-8"))


def test_an_older_run_gains_the_current_downloads_without_the_model(tmp_path: Path) -> None:
    root = _old_pptx_run(tmp_path / "run")
    assert refresh_run_outputs(root) is True
    manifest = _manifest(root)
    assert manifest["outputs_version"] == OUTPUTS_VERSION
    paths = [output["path"] for output in manifest["outputs"]]
    assert "output/changes.txt" in paths
    assert (root / "output" / "changes.txt").read_text(encoding="utf-8").startswith("--- slide 1")
    if find_soffice() is not None:
        assert "output/tagged.pdf" in paths
        assert (root / "output" / "tagged.pdf").is_file()
    # A run that is already current is left alone
    assert refresh_run_outputs(root) is False


def test_a_beamer_run_only_records_that_it_is_current(tmp_path: Path) -> None:
    root = tmp_path / "run"
    root.mkdir()
    (root / "manifest.json").write_text(json.dumps({"run_id": "tex"}), encoding="utf-8")
    assert refresh_run_outputs(root) is True
    manifest = _manifest(root)
    assert manifest["outputs_version"] == OUTPUTS_VERSION
    assert "outputs" not in manifest
    shutil.rmtree(root)
