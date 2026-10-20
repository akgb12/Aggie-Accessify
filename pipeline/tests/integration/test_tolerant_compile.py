from pathlib import Path

import pytest

from a11y_pipeline.adapters.tex_beamer.compile import (
    CompileError,
    compile_project,
    tex_version,
)

# "Missing number" is recoverable: TeX reports it, carries on, and still writes a PDF
RECOVERABLE = (
    "\\documentclass{article}\n\\begin{document}\nHello\\hspace{abc}world\n\\end{document}\n"
)
BROKEN = "\\documentclass{article}\n\\begin{document}\n\\begin{itemize}\nText\n\\end{document}\n"


def _project(tmp_path: Path, source: str) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.tex").write_text(source, encoding="utf-8")
    return root


@pytest.mark.tex
def test_strict_compile_stops_at_a_recoverable_error(tmp_path: Path) -> None:
    # Strict mode is for our own modified copies, which must compile cleanly
    root = _project(tmp_path, RECOVERABLE)

    with pytest.raises(CompileError, match="Missing number"):
        compile_project(root, "main.tex")


@pytest.mark.tex
def test_tolerant_compile_succeeds_when_a_pdf_is_produced(tmp_path: Path) -> None:
    # Like Overleaf, keep going past recoverable errors and report them without failing
    root = _project(tmp_path, RECOVERABLE)

    result = compile_project(root, "main.tex", strict=False)

    assert result.pdf_path.is_file()
    assert result.page_count == 1
    assert result.errors >= 1
    assert any("Missing number" in message for message in result.error_messages)


@pytest.mark.tex
def test_a_clean_project_reports_no_errors_in_either_mode(tmp_path: Path) -> None:
    root = _project(tmp_path, "\\documentclass{article}\n\\begin{document}\nHi\n\\end{document}\n")

    assert compile_project(root, "main.tex", strict=False).errors == 0
    assert compile_project(root, "main.tex").error_messages == ()


@pytest.mark.tex
def test_tolerant_compile_still_fails_when_no_pdf_can_be_made(tmp_path: Path) -> None:
    # A real failure is one Overleaf would also have: no PDF comes out
    root = _project(
        tmp_path, "\\documentclass{nonexistent-class-xyz}\n\\begin{document}\n\\end{document}\n"
    )

    with pytest.raises(CompileError) as error:
        compile_project(root, "main.tex", strict=False)

    assert error.value.blame == "source"
    assert "same step Overleaf runs" in error.value.user_message


@pytest.mark.tex
def test_internal_failures_never_blame_the_users_file(tmp_path: Path) -> None:
    root = _project(tmp_path, BROKEN)
    with pytest.raises(CompileError) as error:
        compile_project(root, "main.tex")

    message = error.value.as_internal().user_message

    assert "nothing to fix in it" in message
    assert "internal problem" in message


@pytest.mark.tex
def test_tex_version_names_the_release() -> None:
    version = tex_version()
    assert version is not None
    assert "TeX Live" in version


DECK = (
    "\\documentclass{beamer}\n"
    "\\begin{document}\n"
    "\\begin{frame}{First}\nFirst text.\n\\end{frame}\n"
    "\\begin{frame}{Second}\nSecond text.\n\\end{frame}\n"
    "\\begin{frame}{Third}\nThird text.\n\\end{frame}\n"
    "\\end{document}\n"
)


@pytest.mark.tex
def test_prepare_recovers_when_tracking_one_slide_breaks_compilation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A tracking marker that breaks one slide must not fail the run or blame the user's file
    from a11y_pipeline.adapters import get_adapter
    from a11y_pipeline.adapters.tex_beamer import markers

    real_marker_text = markers._marker_text

    def sabotage_slide_two(key: str, mcid: int, tag: str, semantic_type: str):
        prefix, suffix = real_marker_text(key, mcid, tag, semantic_type)
        if key.startswith("slide_02"):
            return prefix + "\\undefinedmacroxyz ", suffix
        return prefix, suffix

    monkeypatch.setattr(markers, "_marker_text", sabotage_slide_two)
    project = tmp_path / "input"
    project.mkdir()
    (project / "main.tex").write_text(DECK, encoding="utf-8")
    adapter = get_adapter("tex-beamer")
    bundle = __import__("a11y_pipeline.bundle.bundle", fromlist=["Bundle"]).Bundle.from_path(
        project
    )
    ir = adapter.build_ir(bundle, adapter.preflight(bundle))

    prepared = adapter.prepare(bundle, ir, tmp_path / "run", 120)

    recovered = [i for i in prepared.ir.issues if i.code == "unmarked_recovered"]
    assert [i.details["container_id"] for i in recovered] == ["slide_02"]
    assert prepared.original_pdf.is_file() and prepared.marked_pdf.is_file()
    assert any(
        e.mcid is not None for e in prepared.ir.elements.values() if e.id.startswith("slide_01/")
    )
    assert all(
        e.mcid is None for e in prepared.ir.elements.values() if e.id.startswith("slide_02/")
    )


@pytest.mark.tex
def test_prepare_processes_an_original_that_overleaf_would_render(tmp_path: Path) -> None:
    # A recoverable error in the user's own source is noted, never turned into a failed run
    from a11y_pipeline.adapters import get_adapter
    from a11y_pipeline.bundle.bundle import Bundle

    deck = DECK.replace("Second text.", "Second\\hspace{abc}text.")
    project = tmp_path / "input"
    project.mkdir()
    (project / "main.tex").write_text(deck, encoding="utf-8")
    adapter = get_adapter("tex-beamer")
    bundle = Bundle.from_path(project)
    ir = adapter.build_ir(bundle, adapter.preflight(bundle))

    prepared = adapter.prepare(bundle, ir, tmp_path / "run", 120)

    notes = [i for i in prepared.ir.issues if i.code == "tex_errors_tolerated"]
    assert len(notes) == 1 and notes[0].severity == "info"
    assert "Missing number" in notes[0].message
    assert "as Overleaf does" in notes[0].message
    assert not [i for i in prepared.ir.issues if i.code == "unmarked_recovered"]
    assert prepared.original_pdf.is_file() and prepared.marked_pdf.is_file()


def test_errors_beyond_ignores_line_shifts_and_counts_repeats() -> None:
    from a11y_pipeline.adapters.tex_beamer.compile import errors_beyond

    base = ("main.tex:10: Missing number, treated as zero.",)
    same_but_shifted = ("main.tex:42: Missing number, treated as zero.",)
    assert errors_beyond(base, same_but_shifted) == []
    twice = same_but_shifted * 2
    assert errors_beyond(base, twice) == ["main.tex:42: Missing number, treated as zero."]
    new = ("main.tex:7: Undefined control sequence.",)
    assert errors_beyond(base, same_but_shifted + new) == list(new)
