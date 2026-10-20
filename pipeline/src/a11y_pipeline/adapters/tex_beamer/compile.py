import re
import subprocess
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import pikepdf

MAX_RECORDED_ERRORS = 200


@dataclass(frozen=True)
class CompileResult:
    pdf_path: Path
    aux_path: Path
    log_path: Path
    page_count: int
    errors: int
    # First TeX errors that were tolerated because a PDF was still produced
    error_messages: tuple[str, ...] = field(default_factory=tuple)


class CompileError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        source_file: str,
        line: int | None,
        tex_error: str | None,
        log_path: Path,
    ):
        # Store the first actionable TeX failure
        super().__init__(message)
        self.source_file = source_file
        self.line = line
        self.tex_error = tex_error
        self.log_path = log_path
        # "source": the user's own project failed; "internal": one of our modified copies did
        self.blame = "source"

    def as_internal(self) -> "CompileError":
        # Mark this failure as ours so it is never reported as a problem with the user's file
        self.blame = "internal"
        return self

    @property
    def user_message(self) -> str:
        # Wording that is fair to the user about who needs to act
        detail = str(self)
        if self.blame == "internal":
            return (
                "We hit an internal problem while preparing your slides for tagging. "
                "Your own file compiled normally, so there is nothing to fix in it. "
                f"(Technical detail: {detail})"
            )
        return (
            "pdfLaTeX could not produce a PDF from this project, which is the same step "
            f"Overleaf runs. First error: {detail}"
        )


def compile_project(
    project_root: Path,
    main_file: str,
    timeout_seconds: int = 180,
    strict: bool = True,
) -> CompileResult:
    # Compile one isolated project with pdfLaTeX through latexmk. Strict mode stops at the first
    # error. Tolerant mode keeps going like Overleaf does and succeeds when a PDF is produced.
    root = project_root.resolve()
    main_path = root / main_file
    if not main_path.is_file():
        raise FileNotFoundError(f"Main TeX file does not exist: {main_file}")
    command = ["latexmk", "-pdf", "-interaction=nonstopmode"]
    command.append("-halt-on-error" if strict else "-f")
    command.extend(["-file-line-error", main_file])
    output_path = root / "latexmk_output.log"
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
        output = completed.stdout + completed.stderr
    except subprocess.TimeoutExpired as error:
        output = _timeout_output(error)
        output_path.write_text(output, encoding="utf-8")
        raise CompileError(
            f"TeX compilation timed out after {timeout_seconds} seconds",
            source_file=main_file,
            line=None,
            tex_error=None,
            log_path=output_path,
        ) from error
    output_path.write_text(output, encoding="utf-8")
    tex_log = main_path.with_suffix(".log")
    error_source = output
    if tex_log.is_file():
        error_source = tex_log.read_text(encoding="utf-8", errors="replace")
    pdf_ready = main_path.with_suffix(".pdf").is_file() and main_path.with_suffix(".aux").is_file()
    tolerated = not strict and pdf_ready
    if completed.returncode != 0 and not tolerated:
        tex_error, line = _first_tex_error(error_source)
        error_file, reported_line, reported_error = _first_file_error(output)
        if error_file is None:
            error_file = main_file
        if reported_line is not None:
            line = reported_line
        if tex_error is None:
            tex_error = reported_error
        location = error_file
        if line is not None:
            location = f"{error_file}:{line}"
        detail = tex_error or "latexmk failed without a TeX error line"
        raise CompileError(
            f"{location}: {detail}",
            source_file=error_file,
            line=line,
            tex_error=tex_error,
            log_path=output_path,
        )
    pdf_path = main_path.with_suffix(".pdf")
    aux_path = main_path.with_suffix(".aux")
    if not pdf_path.is_file() or not aux_path.is_file():
        raise CompileError(
            f"{main_file}: latexmk completed without expected PDF or AUX output",
            source_file=main_file,
            line=None,
            tex_error=None,
            log_path=output_path,
        )
    with pikepdf.open(pdf_path) as pdf:
        page_count = len(pdf.pages)
    messages = _all_file_errors(output) if completed.returncode != 0 else []
    return CompileResult(
        pdf_path=pdf_path,
        aux_path=aux_path,
        log_path=output_path,
        page_count=page_count,
        errors=len(messages),
        error_messages=tuple(messages[:MAX_RECORDED_ERRORS]),
    )


def _all_file_errors(output: str) -> list[str]:
    # List distinct "file:line: message" TeX errors in order of appearance
    found: list[str] = []
    for match in re.finditer(r"^(?:\./)?([^\s:]+\.\w+):(\d+): (.+)$", output, re.MULTILINE):
        message = f"{match.group(1)}:{match.group(2)}: {match.group(3).strip()}"
        if message not in found:
            found.append(message)
    return found


def error_text(message: str) -> str:
    # Drop the "file:line:" prefix so the same error at a shifted line still compares equal
    return re.sub(r"^[^\s:]+\.\w+:\d+: ", "", message)


def errors_beyond(baseline: tuple[str, ...], candidate: tuple[str, ...]) -> list[str]:
    # List candidate errors that appear more often than in the baseline compile
    remaining: dict[str, int] = {}
    for message in baseline:
        remaining[error_text(message)] = remaining.get(error_text(message), 0) + 1
    extra: list[str] = []
    for message in candidate:
        key = error_text(message)
        if remaining.get(key, 0) > 0:
            remaining[key] -= 1
        else:
            extra.append(message)
    return extra


@cache
def tex_version() -> str | None:
    # Report the pdfTeX and TeX Live release used, so results can be compared with Overleaf
    try:
        completed = subprocess.run(
            ["pdflatex", "--version"],
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    first_line = completed.stdout.strip().splitlines()[:1]
    return first_line[0].strip() if first_line else None


def _timeout_output(error: subprocess.TimeoutExpired) -> str:
    # Combine available process output after a timeout
    output = ""
    if error.stdout is not None:
        if isinstance(error.stdout, bytes):
            output += error.stdout.decode("utf-8", errors="replace")
        else:
            output += error.stdout
    if error.stderr is not None:
        if isinstance(error.stderr, bytes):
            output += error.stderr.decode("utf-8", errors="replace")
        else:
            output += error.stderr
    return output


def _first_tex_error(log_text: str) -> tuple[str | None, int | None]:
    # Extract the first TeX bang error and nearby source line
    match = re.search(r"^!\s*(.+)$", log_text, re.MULTILINE)
    if match is None:
        file_error = re.search(r"^[^:\n]+\.tex:(\d+):\s*(.+)$", log_text, re.MULTILINE)
        if file_error is None:
            return None, None
        return file_error.group(2).strip(), int(file_error.group(1))
    line_match = re.search(r"^l\.(\d+)\b", log_text[match.end() :], re.MULTILINE)
    line = None
    if line_match is not None:
        line = int(line_match.group(1))
    return match.group(1).strip(), line


def _first_file_error(
    output: str,
) -> tuple[str | None, int | None, str | None]:
    # Extract the first file line diagnostic emitted by pdfLaTeX
    match = re.search(r"^(.+?\.tex):(\d+):\s*(.+)$", output, re.MULTILINE)
    if match is None:
        return None, None, None
    source_file = match.group(1).strip()
    if source_file.startswith("./"):
        source_file = source_file[2:]
    return source_file, int(match.group(2)), match.group(3).strip()
