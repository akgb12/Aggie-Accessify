from pathlib import Path

from a11y_pipeline.adapters.tex_beamer.builder import build
from a11y_pipeline.adapters.tex_beamer.parser import parse_file
from a11y_pipeline.adapters.tex_beamer.preflight import preflight
from a11y_pipeline.adapters.tex_beamer.writer import write_updated_project
from a11y_pipeline.bundle.bundle import Bundle

SOURCE = r"""\documentclass{beamer}
\begin{document}
\begin{frame}{Results}
  \includegraphics[width=3cm,alt={A plot of \{x\} against y}]{plot.png}
  \includegraphics[alt={image}]{other.png}
  % a11y-alt: Five folds in a row
  % a11y-alt: with the third one picked.
  % a11y-alt:
  % a11y-alt: The other four folds train the model.
  \begin{tikzpicture}\draw (0,0) -- (1,1);\end{tikzpicture}
  \begin{tikzpicture}\draw (0,0) -- (1,0);\end{tikzpicture}
\end{frame}
\end{document}
"""


def _project(root: Path) -> Path:
    root.mkdir()
    (root / "main.tex").write_text(SOURCE, encoding="utf-8")
    for name in ("plot.png", "other.png"):
        (root / name).write_bytes(b"png")
    return root


def _build(root: Path):
    return build(parse_file(root), preflight(Bundle.from_path(root)))


def _figures(root: Path) -> list:
    ir = _build(root)
    return [element for element in ir.elements.values() if element.semantic_type == "figure"]


def test_descriptions_already_in_the_source_are_kept_as_the_authors(tmp_path: Path) -> None:
    plot, other, folds, line = _figures(_project(tmp_path / "in"))
    assert plot.accessibility.status == "done" and plot.accessibility.locked
    assert plot.accessibility.alt_text == "A plot of {x} against y"
    assert folds.accessibility.alt_text == "Five folds in a row with the third one picked."
    assert folds.accessibility.extended_description == "The other four folds train the model."
    # A placeholder description, or none, still needs one
    assert other.accessibility.status == "needs_description"
    assert line.accessibility.status == "needs_description"


def test_an_updated_source_is_not_given_its_descriptions_twice(tmp_path: Path) -> None:
    root = _project(tmp_path / "in")
    bundle = Bundle.from_path(root)
    ir = _build(root)
    for element in ir.elements.values():
        if element.semantic_type == "figure" and not element.accessibility.locked:
            element.accessibility.alt_text = "A new description."
            element.accessibility.status = "model_generated"
    result = write_updated_project(bundle, ir, tmp_path / "out", tmp_path / "changes.diff")
    updated = (result.project_root / "main.tex").read_text(encoding="utf-8")
    assert updated.count("% a11y-alt: Five folds in a row") == 1
    assert updated.count("alt={A plot of \\{x\\} against y}") == 1
    assert updated.count("% a11y-alt: A new description.") == 1
    # Running the update on its own output changes nothing more
    again = _build(result.project_root)
    figures = [e for e in again.elements.values() if e.semantic_type == "figure"]
    assert all(figure.accessibility.locked for figure in figures)
