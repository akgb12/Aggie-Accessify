import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from a11y_pipeline.bundle.bundle import Bundle

MAX_SLIDES = 500


@dataclass(frozen=True)
class PptxPreflightIssue:
    code: str
    severity: Literal["warning", "critical"]
    message: str
    source_file: str
    line: int = 0
    dependency: str | None = None


@dataclass(frozen=True)
class PptxPreflightResult:
    ok: bool
    slides: int = 0
    missing_images: list[str] = field(default_factory=list)
    missing_critical: list[str] = field(default_factory=list)
    assets: list[str] = field(default_factory=list)
    issues: list[PptxPreflightIssue] = field(default_factory=list)


def preflight(bundle: Bundle) -> PptxPreflightResult:
    # Check that the deck opens and is a plain .pptx before any model work
    deck = bundle.root / bundle.main_file
    blocked = _blocking_problem(deck)
    if blocked is not None:
        code, message = blocked
        issue = PptxPreflightIssue(code, "critical", message, bundle.main_file)
        return PptxPreflightResult(ok=False, issues=[issue], missing_critical=[bundle.main_file])
    from pptx import Presentation

    try:
        presentation = Presentation(str(deck))
    except Exception as error:  # python-pptx raises several unrelated types for damaged files
        issue = PptxPreflightIssue(
            "deck_unreadable",
            "critical",
            f"PowerPoint could not read this deck ({type(error).__name__}). "
            "Open it in PowerPoint, save it again as .pptx and upload that copy.",
            bundle.main_file,
        )
        return PptxPreflightResult(ok=False, issues=[issue], missing_critical=[bundle.main_file])
    slides = len(presentation.slides)
    issues: list[PptxPreflightIssue] = []
    if slides == 0:
        issues.append(
            PptxPreflightIssue(
                "no_slides", "critical", "This deck has no slides.", bundle.main_file
            )
        )
    if slides > MAX_SLIDES:
        issues.append(
            PptxPreflightIssue(
                "too_many_slides",
                "critical",
                f"This deck has {slides} slides; the limit is {MAX_SLIDES}.",
                bundle.main_file,
            )
        )
    critical = [issue for issue in issues if issue.severity == "critical"]
    return PptxPreflightResult(
        ok=not critical,
        slides=slides,
        missing_critical=[bundle.main_file] if critical else [],
        issues=issues,
    )


def _blocking_problem(deck: Path) -> tuple[str, str] | None:
    # Recognize the common "not really a .pptx" cases with a clear next step
    if not zipfile.is_zipfile(deck):
        with deck.open("rb") as source:
            header = source.read(8)
        if header.startswith(b"\xd0\xcf\x11\xe0"):
            return (
                "deck_encrypted_or_legacy",
                "This file is password-protected or an old .ppt deck. Remove the password or "
                "save it as .pptx in PowerPoint, then upload it again.",
            )
        return ("not_a_deck", "This file is not a PowerPoint (.pptx) deck.")
    with zipfile.ZipFile(deck) as archive:
        names = set(archive.namelist())
    if "ppt/presentation.xml" not in names:
        return ("not_a_deck", "This file is a zip but not a PowerPoint (.pptx) deck.")
    if any(name.endswith("vbaProject.bin") for name in names):
        return (
            "macros_present",
            "This deck contains macros (.pptm). Save a macro-free .pptx copy and upload that.",
        )
    return None
