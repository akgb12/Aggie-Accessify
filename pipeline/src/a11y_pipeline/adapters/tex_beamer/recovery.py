import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from a11y_pipeline.adapters.tex_beamer.compile import CompileError, CompileResult
from a11y_pipeline.adapters.tex_beamer.markers import inject_markers
from a11y_pipeline.adapters.tex_beamer.working_copy import recreate_marked_copy
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.ir.models import DocumentIR

MAX_ATTEMPTS = 8
SEARCH_LINES = 300
MARKER_KEY = re.compile(r"\\ael(?:span|figure)\{([^-{}]+)-")


@dataclass(frozen=True)
class MarkedCopy:
    ir: DocumentIR
    compiled: CompileResult
    skipped_containers: list[str]


def culprit_container(marked_root: Path, error: CompileError) -> str | None:
    # Find the slide whose tracking marker sits closest above a compile error
    if error.line is None:
        return None
    try:
        lines = (marked_root / error.source_file).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    last = min(error.line, len(lines)) - 1
    for index in range(last, max(-1, last - SEARCH_LINES), -1):
        found = MARKER_KEY.findall(lines[index])
        if found:
            return found[-1]
    return None


def compile_marked_copy(
    bundle: Bundle,
    ir: DocumentIR,
    marked_root: Path,
    injection_table_path: Path,
    compile_marked: Callable[[Path], CompileResult],
    max_attempts: int = MAX_ATTEMPTS,
) -> MarkedCopy:
    # Build the tracked copy; when it breaks, leave the offending slide untagged and retry
    skipped: list[str] = []
    last_error: CompileError | None = None
    for _ in range(max_attempts):
        working_ir = ir.model_copy(deep=True)
        recreate_marked_copy(bundle, working_ir, marked_root)
        inject_markers(working_ir, marked_root, injection_table_path, set(skipped))
        try:
            compiled = compile_marked(marked_root)
        except CompileError as error:
            last_error = error
            culprit = culprit_container(marked_root, error)
            if culprit is None or culprit in skipped:
                break
            skipped.append(culprit)
            continue
        return MarkedCopy(ir=working_ir, compiled=compiled, skipped_containers=skipped)
    if last_error is None:
        raise RuntimeError("Marked copy could not be prepared")
    raise last_error.as_internal()
