import zipfile
from pathlib import Path

from lxml import etree

from a11y_pipeline.adapters.docx.ooxml import DOCUMENT_PART
from a11y_pipeline.adapters.pptx.preflight import PptxPreflightIssue, PptxPreflightResult
from a11y_pipeline.bundle.bundle import Bundle

# The same result shape as a deck's preflight, so the rest of the run treats both alike
DocxPreflightIssue = PptxPreflightIssue
DocxPreflightResult = PptxPreflightResult


def preflight(bundle: Bundle) -> DocxPreflightResult:
    # Check that the document opens and is a plain .docx before any model work
    document = bundle.root / bundle.main_file
    blocked = _blocking_problem(document)
    if blocked is None:
        try:
            with zipfile.ZipFile(document) as package:
                etree.fromstring(package.read(DOCUMENT_PART))
        except (KeyError, OSError, zipfile.BadZipFile, etree.XMLSyntaxError) as error:
            blocked = (
                "document_unreadable",
                f"Word could not read this document ({type(error).__name__}). Open it in Word, "
                "save it again as .docx and upload that copy.",
            )
    if blocked is not None:
        code, message = blocked
        issue = DocxPreflightIssue(code, "critical", message, bundle.main_file)
        return DocxPreflightResult(ok=False, issues=[issue], missing_critical=[bundle.main_file])
    return DocxPreflightResult(ok=True)


def _blocking_problem(document: Path) -> tuple[str, str] | None:
    # Recognize the common "not really a .docx" cases with a clear next step
    if not zipfile.is_zipfile(document):
        with document.open("rb") as source:
            header = source.read(8)
        if header.startswith(b"\xd0\xcf\x11\xe0"):
            return (
                "document_encrypted_or_legacy",
                "This file is password-protected or an old .doc document. Remove the password "
                "or save it as .docx in Word, then upload it again.",
            )
        return ("not_a_document", "This file is not a Word (.docx) document.")
    with zipfile.ZipFile(document) as archive:
        names = set(archive.namelist())
    if DOCUMENT_PART not in names:
        return ("not_a_document", "This file is a zip but not a Word (.docx) document.")
    if any(name.endswith("vbaProject.bin") for name in names):
        return (
            "macros_present",
            "This document contains macros (.docm). Save a macro-free .docx copy and upload that.",
        )
    return None
