from pathlib import Path

from a11y_pipeline.adapters.tex_beamer.builder import build
from a11y_pipeline.adapters.tex_beamer.markers import inject_markers
from a11y_pipeline.adapters.tex_beamer.parser import parse_file
from a11y_pipeline.adapters.tex_beamer.working_copy import create_working_copies
from a11y_pipeline.bundle.bundle import Bundle

SOURCE = (
    "\\documentclass{beamer}\n"
    "\\begin{document}\n"
    "\\begin{frame}{Slide}\n"
    "\\begin{columns}[T,totalwidth=\\textwidth]\n"
    "\\begin{column}[t]{0.5\\textwidth}\n"
    "Left text.\n"
    "\\end{column}\n"
    "\\begin{column}{0.5\\textwidth}\n"
    "Right text.\n"
    "\\end{column}\n"
    "\\end{columns}\n"
    "\\begin{minipage}[t]{0.4\\textwidth}\n"
    "Inside minipage.\n"
    "\\end{minipage}\n"
    "\\end{frame}\n"
    "\\end{document}\n"
)


def _project(tmp_path: Path) -> Path:
    # Write the sample deck into a fresh project folder
    project = tmp_path / "input"
    project.mkdir()
    (project / "main.tex").write_text(SOURCE, encoding="utf-8")
    return project


def test_option_lists_on_wrappers_are_not_read_as_slide_text(tmp_path: Path) -> None:
    # [T,totalwidth=\textwidth] and [t]{0.5\textwidth} are layout options, not content
    ir = build(parse_file(_project(tmp_path)))

    texts = [str(e.content.get("text", "")) for e in ir.elements.values() if e.content.get("text")]

    assert "Left text." in texts
    assert "Right text." in texts
    assert "Inside minipage." in texts
    for text in texts:
        assert "totalwidth" not in text
        assert not text.startswith("[")
        assert "0.5" not in text


def test_marked_copy_keeps_wrapper_options_intact(tmp_path: Path) -> None:
    # Markers must never separate an environment from its option list
    project = _project(tmp_path)
    bundle = Bundle.from_path(project)
    ir = build(parse_file(project))
    copies = create_working_copies(bundle, ir, tmp_path / "work")

    inject_markers(ir, copies.marked)
    marked = (copies.marked / "main.tex").read_text(encoding="utf-8")

    assert "\\begin{columns}[T,totalwidth=\\textwidth]\n" in marked
    assert "\\begin{column}[t]{0.5\\textwidth}\n" in marked
    assert "\\begin{minipage}[t]{0.4\\textwidth}\n" in marked
