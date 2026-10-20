from pathlib import Path

import pytest

from a11y_pipeline.adapters.tex_beamer.builder import build
from a11y_pipeline.adapters.tex_beamer.compile import CompileError, CompileResult
from a11y_pipeline.adapters.tex_beamer.parser import parse_file
from a11y_pipeline.adapters.tex_beamer.recovery import compile_marked_copy, culprit_container
from a11y_pipeline.bundle.bundle import Bundle

SOURCE = (
    "\\documentclass{beamer}\n"
    "\\begin{document}\n"
    "\\begin{frame}{First}\n"
    "First text.\n"
    "\\end{frame}\n"
    "\\begin{frame}{Second}\n"
    "Second text.\n"
    "\\end{frame}\n"
    "\\begin{frame}{Third}\n"
    "Third text.\n"
    "\\end{frame}\n"
    "\\end{document}\n"
)


def _error(line: int | None, source_file: str = "main.tex") -> CompileError:
    return CompileError(
        f"{source_file}:{line}: Something broke",
        source_file=source_file,
        line=line,
        tex_error="Something broke",
        log_path=Path("unused.log"),
    )


def _fake_result(root: Path) -> CompileResult:
    return CompileResult(
        pdf_path=root / "main.pdf",
        aux_path=root / "main.aux",
        log_path=root / "log",
        page_count=3,
        errors=0,
    )


def _setup(tmp_path: Path):
    project = tmp_path / "input"
    project.mkdir()
    (project / "main.tex").write_text(SOURCE, encoding="utf-8")
    return Bundle.from_path(project), build(parse_file(project))


def test_culprit_is_the_slide_whose_marker_is_closest_above_the_error(tmp_path: Path) -> None:
    root = tmp_path / "marked"
    root.mkdir()
    (root / "main.tex").write_text(
        "\\begin{frame}{\\aelspan{slide_01-heading_01}{0}{H2}{A}}\n"
        "\\aelspan{slide_01-paragraph_01}{1}{P}{text}\n"
        "\\end{frame}\n"
        "\\begin{frame}{\\aelspan{slide_02-heading_01}{0}{H2}{B}}\n"
        "\\aelfigure{slide_02-figure_01}{1}{\\includegraphics{x}}\n"
        "\\end{frame}\n",
        encoding="utf-8",
    )

    assert culprit_container(root, _error(3)) == "slide_01"
    assert culprit_container(root, _error(6)) == "slide_02"
    assert culprit_container(root, _error(None)) is None
    assert culprit_container(root, _error(2, "missing.tex")) is None


def test_a_slide_that_breaks_compilation_is_left_untagged_and_the_rest_continue(
    tmp_path: Path,
) -> None:
    bundle, ir = _setup(tmp_path)
    marked = tmp_path / "work" / "marked"
    table = tmp_path / "table.json"
    attempts: list[str] = []

    def compile_marked(root: Path) -> CompileResult:
        text = (root / "main.tex").read_text(encoding="utf-8")
        attempts.append(text)
        if "slide_02-paragraph_01" in text:
            line = next(
                i for i, ln in enumerate(text.splitlines(), 1) if "slide_02-paragraph_01" in ln
            )
            raise _error(line + 1)
        return _fake_result(root)

    result = compile_marked_copy(bundle, ir, marked, table, compile_marked)

    assert len(attempts) == 2
    assert result.skipped_containers == ["slide_02"]
    final = (marked / "main.tex").read_text(encoding="utf-8")
    assert "slide_02-" not in final
    assert "slide_01-" in final and "slide_03-" in final
    issues = [i for i in result.ir.issues if i.code == "unmarked_recovered"]
    assert [i.details["container_id"] for i in issues] == ["slide_02"]
    assert "Your source is fine" in issues[0].message
    assert all(e.mcid is None for e in result.ir.elements.values() if e.id.startswith("slide_02/"))
    assert any(
        e.mcid is not None for e in result.ir.elements.values() if e.id.startswith("slide_01/")
    )


def test_recovery_gives_up_fairly_when_the_culprit_cannot_be_found(tmp_path: Path) -> None:
    bundle, ir = _setup(tmp_path)

    def always_fails(root: Path) -> CompileResult:
        raise _error(None)

    with pytest.raises(CompileError) as error:
        compile_marked_copy(
            bundle, ir, tmp_path / "work" / "marked", tmp_path / "t.json", always_fails
        )

    assert error.value.blame == "internal"
    assert "nothing to fix in it" in error.value.user_message


def test_recovery_does_not_loop_when_the_same_slide_keeps_failing(tmp_path: Path) -> None:
    bundle, ir = _setup(tmp_path)
    calls = 0

    def fails_in_the_first_slide(root: Path) -> CompileResult:
        nonlocal calls
        calls += 1
        raise _error(4)

    with pytest.raises(CompileError) as error:
        compile_marked_copy(
            bundle, ir, tmp_path / "work" / "marked", tmp_path / "t.json", fails_in_the_first_slide
        )

    assert calls <= 3
    assert error.value.blame == "internal"
