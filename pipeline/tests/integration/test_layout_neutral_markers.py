from pathlib import Path

import pytest
from PIL import Image

from a11y_pipeline.adapters import get_adapter
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.render.pixeldiff import _images_identical, compare_pdf_pixels

DECK = (
    "\\documentclass{beamer}\n"
    "\\usepackage{amsmath}\n"
    "\\begin{document}\n"
    "\\begin{frame}{Equations}\n"
    "\\small\n"
    "\\begin{itemize}\n"
    "  \\item We have three classes:\n"
    "  \\[\n"
    "    s=\\text{Sports}, \\qquad p=\\text{Politics}\n"
    "  \\]\n"
    "\n"
    "  \\item Feature order:\n"
    "  \\[\n"
    "    [\\#\\text{win},\\ \\#\\text{game}]\n"
    "  \\]\n"
    "\\pause\n"
    "  \\item A last bullet after the equations.\n"
    "\\end{itemize}\n"
    "\\end{frame}\n"
    "\\end{document}\n"
)


def _prepare(tmp_path: Path, deck: str):
    project = tmp_path / "input"
    project.mkdir()
    (project / "main.tex").write_text(deck, encoding="utf-8")
    adapter = get_adapter("tex-beamer")
    bundle = Bundle.from_path(project)
    ir = adapter.build_ir(bundle, adapter.preflight(bundle))
    return adapter.prepare(bundle, ir, tmp_path / "run", 120)


@pytest.mark.tex
def test_a_list_item_ending_in_a_display_equation_does_not_shift_the_page(tmp_path: Path) -> None:
    # A closing marker after a display used to add an empty line and push the rest down
    prepared = _prepare(tmp_path, DECK)

    check = compare_pdf_pixels(prepared.original_pdf, prepared.marked_pdf)

    assert check.different_pages == []
    assert not [i for i in prepared.ir.issues if i.code == "visual_change"]


@pytest.mark.tex
def test_markers_stay_inside_the_equation_so_they_still_close_the_item(tmp_path: Path) -> None:
    _prepare(tmp_path, DECK)
    marked = (tmp_path / "run" / "work" / "marked" / "main.tex").read_text(encoding="utf-8")

    first_item = marked.split("\\item", 2)[1]
    assert first_item.rstrip().endswith("}\\]") or "}\n  \\]" in first_item


def test_visual_check_tolerates_antialiasing_flicker_but_not_a_real_shift(tmp_path: Path) -> None:
    base = Image.new("RGB", (200, 120), "white")
    for x in range(20, 180):
        for y in (40, 41, 80, 81):
            base.putpixel((x, y), (0, 0, 0))
    flicker = base.copy()
    for x in range(20, 180, 2):
        # edge pixels a few gray levels off, as when a glyph sits a hair to one side
        flicker.putpixel((x, 41), (40, 40, 40))
        flicker.putpixel((x, 81), (40, 40, 40))
    shifted = Image.new("RGB", base.size, "white")
    shifted.paste(base, (0, 3))
    paths = {}
    for name, image in {"base": base, "flicker": flicker, "shifted": shifted}.items():
        paths[name] = tmp_path / f"{name}.png"
        image.save(paths[name])

    assert _images_identical(paths["base"], paths["flicker"])
    assert not _images_identical(paths["base"], paths["shifted"])


@pytest.mark.tex
def test_equations_inside_bullets_are_part_of_the_tagged_structure(tmp_path: Path) -> None:
    # A display equation inside a bullet must own a structure element, nested in the bullet body
    import pikepdf

    from a11y_pipeline.evaluation.pdf_checks import check_pdf
    from a11y_pipeline.synthesis.tagger import tag_pdf

    prepared = _prepare(tmp_path, DECK)
    tagged = tmp_path / "tagged.pdf"

    tag_pdf(prepared.marked_pdf, prepared.ir, tagged)
    checks = check_pdf(tagged, prepared.ir)

    codes = {issue.code for issue in checks.issues}
    assert "structure_content_missing" not in codes
    assert "broken_mcid_link" not in codes
    with pikepdf.open(tagged) as pdf:
        roles: list[str] = []

        def walk(node) -> None:
            roles.append(str(node.get("/S", "")))
            children = node.get("/K")
            if isinstance(children, pikepdf.Array):
                for child in children:
                    if isinstance(child, pikepdf.Dictionary) and "/S" in child:
                        walk(child)

        walk(pdf.Root.StructTreeRoot.K)
    assert roles.count("/Formula") == 2
