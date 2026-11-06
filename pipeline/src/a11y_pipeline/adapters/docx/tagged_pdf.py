import re
import zipfile
from pathlib import Path
from typing import Any

import pikepdf
from lxml import etree

from a11y_pipeline.adapters.docx.math_text import math_text
from a11y_pipeline.adapters.docx.ooxml import (
    DOCUMENT_PART,
    M_NS,
    O_NS,
    V_NS,
    WP_NS,
    figures,
    is_vml,
    maths,
)

HEADING = re.compile(r"^/H([1-6])$")
FIGURE_MARK = "{urn:a11y}figure"
MATH_MARK = "{urn:a11y}math"


def repair_document_tags(pdf_path: Path, document: Path) -> int:
    # Fill what LibreOffice leaves out of a Word document's tags: equations as text, older
    # VML pictures' descriptions, and heading levels that skip. Returns how many were fixed.
    equations, pictures = _alternates(document)
    fixed = 0
    with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
        formulas, figures_ = _tagged(pdf)
        if len(formulas) == len(equations):
            for node, text in zip(formulas, equations, strict=True):
                if text and not str(node.get("/Alt", "")).strip():
                    node.Alt = pikepdf.String(text)
                    fixed += 1
        missing = [node for node in figures_ if not str(node.get("/Alt", "")).strip()]
        if len(missing) == len(pictures):
            for node, text in zip(missing, pictures, strict=True):
                if text:
                    node.Alt = pikepdf.String(text)
                    fixed += 1
        fixed += _close_heading_gaps(pdf)
        pdf.save(pdf_path)
    return fixed


def _alternates(document: Path) -> tuple[list[str], list[str]]:
    # In reading order: the text for each equation (Word's own and older embedded ones) and
    # the description of each older VML picture
    with zipfile.ZipFile(document) as package:
        root = etree.fromstring(package.read(DOCUMENT_PART))
    # Mark the nodes on this private copy, then read them back in one pass in reading order
    for node in figures(root):
        node.set(FIGURE_MARK, "1")
    for node in maths(root):
        node.set(MATH_MARK, "1")
    equations: list[str] = []
    pictures: list[str] = []
    for node in root.iter(f"{{{WP_NS}}}docPr", f"{{{V_NS}}}shape", f"{{{M_NS}}}oMath"):
        if node.get(MATH_MARK):
            equations.append(math_text(node))
        elif node.get(FIGURE_MARK) and is_vml(node):
            holder = node.getparent()
            ole = holder.find(f"{{{O_NS}}}OLEObject") if holder is not None else None
            program = (ole.get("ProgID") or "").lower() if ole is not None else ""
            text = " ".join((node.get("alt") or "").split())
            if program.startswith("equation") or "mathtype" in program:
                equations.append(text)
            else:
                pictures.append(text)
    return equations, pictures


def _tagged(pdf: pikepdf.Pdf) -> tuple[list[pikepdf.Dictionary], list[pikepdf.Dictionary]]:
    # Formula and Figure tags in reading order
    formulas: list[pikepdf.Dictionary] = []
    figures_: list[pikepdf.Dictionary] = []
    root = pdf.Root.get("/StructTreeRoot")
    pending: list[Any] = [root] if root is not None else []
    while pending:
        node = pending.pop(0)
        if not isinstance(node, pikepdf.Dictionary):
            continue
        role = node.get("/S")
        if role == pikepdf.Name.Formula:
            formulas.append(node)
            continue
        if role == pikepdf.Name.Figure:
            figures_.append(node)
            continue
        kids = node.get("/K")
        children = list(kids) if isinstance(kids, pikepdf.Array) else [kids]
        pending[0:0] = [kid for kid in children if isinstance(kid, pikepdf.Dictionary)]
    return formulas, figures_


def _close_heading_gaps(pdf: pikepdf.Pdf) -> int:
    # Headings must not skip a level going deeper, as a reader navigates by them; a heading
    # that does is raised to one level below the heading before it
    root = pdf.Root.get("/StructTreeRoot")
    pending: list[Any] = [root] if root is not None else []
    previous = 0
    changed = 0
    while pending:
        node = pending.pop(0)
        if not isinstance(node, pikepdf.Dictionary):
            continue
        match = HEADING.match(str(node.get("/S", "")))
        if match:
            level = int(match.group(1))
            if level > previous + 1:
                level = previous + 1
                node.S = pikepdf.Name(f"/H{level}")
                changed += 1
            previous = level
        kids = node.get("/K")
        children = list(kids) if isinstance(kids, pikepdf.Array) else [kids]
        pending[0:0] = [kid for kid in children if isinstance(kid, pikepdf.Dictionary)]
    return changed
