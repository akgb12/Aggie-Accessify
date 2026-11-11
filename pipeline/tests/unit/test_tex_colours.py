from PIL import Image, ImageDraw

from a11y_pipeline.adapters.tex_beamer.colours import (
    apply_colour_edits,
    edits_from_records,
    evaluate,
    model_colour,
    plan_colour_edits,
)
from a11y_pipeline.evaluation.contrast import contrast_ratio
from a11y_pipeline.evaluation.page_contrast import word_colours

SOURCE = r"""\documentclass{beamer}
\setbeamercovered{transparent}
\definecolor{faint}{RGB}{200,200,200}
\colorlet{softer}{black!35}
\setbeamercolor{subtitle}{fg=gray!60}
\setbeamercolor{frametitle}{fg=white,bg=black}
\begin{document}
\begin{frame}{Today}
  \begin{itemize}
    \item<1> A* search
    \item<2> Graph search vs. tree search
  \end{itemize}
  {\color{gray!50} Covered last time}\par
  \textcolor{faint}{A faint note} and \textcolor<2->{softer}{a softer one}
  \textcolor{black}{Readable} % \textcolor{lightgray}{in a comment}
  \begin{tikzpicture}\color{lightgray}\fill (0,0) rectangle (1,1);\end{tikzpicture}
\end{frame}
\end{document}
"""


def test_xcolor_expressions_are_evaluated() -> None:
    names = {"black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0), "blue": (0, 0, 255)}
    assert evaluate("black!30", names) == (178, 178, 178)
    assert evaluate("red!50!blue", names) == (128, 0, 128)
    assert evaluate("rgb,255:red,1;green,2;blue,3", names) == (1, 2, 3)
    assert evaluate("-red", names) is None
    assert evaluate("unknown", names) is None
    assert model_colour("HTML", "500000") == (80, 0, 0)
    assert model_colour("rgb", "0.2,0.2,0.7") == (51, 51, 178)
    assert model_colour("gray", "0.75") == (191, 191, 191)


def test_faint_text_colours_get_readable_shades_and_nothing_else_changes() -> None:
    edits = plan_colour_edits({"main.tex": SOURCE}, "main.tex")
    kinds = [edit.kind for edit in edits]
    assert kinds.count("text_colour") == 3
    assert "covered_items" in kinds and "beamer_colour" in kinds
    for edit in edits:
        assert edit.ratio_after is not None and edit.ratio_after >= 4.5
    updated = apply_colour_edits(SOURCE, edits)
    assert r"\setbeamercovered{transparent=" in updated
    assert r"{\color[HTML]{757575} Covered last time}" in updated
    assert r"\textcolor<2->[HTML]{757575}{a softer one}" in updated
    assert "fg={rgb,255:red,117;green,117;blue,117}" in updated
    # White on its own black background, readable text, comments and drawings are left alone
    assert r"\setbeamercolor{frametitle}{fg=white,bg=black}" in updated
    assert r"\textcolor{black}{Readable}" in updated
    assert r"\textcolor{lightgray}{in a comment}" in updated
    assert r"\color{lightgray}\fill" in updated


def test_edits_are_found_again_in_a_copy_with_text_added() -> None:
    edits = plan_colour_edits({"main.tex": SOURCE}, "main.tex")
    restored = edits_from_records([edit.record() for edit in edits])
    # The tracked copy has markers added around elements, which moves every offset
    marked = SOURCE.replace(r"\item<1>", r"\aelspan{x-1}\item<1>")
    updated = apply_colour_edits(marked, restored)
    assert r"\aelspan{x-1}" in updated
    assert r"{\color[HTML]{757575} Covered last time}" in updated
    assert r"\textcolor[HTML]{757575}{A faint note}" in updated


def test_a_drawn_word_is_measured_without_knowing_its_colour() -> None:
    image = Image.new("RGB", (90, 30), (255, 255, 255))
    ImageDraw.Draw(image).text((2, 0), "search", fill=(191, 191, 191), font_size=28)
    measured = word_colours(image)
    assert measured is not None
    assert contrast_ratio(measured[0], (191, 191, 191)) < 1.3
    assert measured[1] == (255, 255, 255)
