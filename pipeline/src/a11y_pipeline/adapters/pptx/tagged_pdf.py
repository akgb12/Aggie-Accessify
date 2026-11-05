import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pikepdf
from lxml import etree

from a11y_pipeline.adapters.pptx.render import RENDER_TIMEOUT_SECONDS, find_soffice

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
# Tagged, PDF/UA, no hidden slides and no notes pages: what PowerPoint's own Save as PDF gives
TAGGED_PDF_FILTER = (
    'pdf:impress_pdf_Export:{"UseTaggedPDF":{"type":"boolean","value":"true"},'
    '"PDFUACompliance":{"type":"boolean","value":"true"},'
    '"ExportHiddenSlides":{"type":"boolean","value":"false"},'
    '"ExportNotesPages":{"type":"boolean","value":"false"}}'
)
PATH_OPERATORS = {"m", "l", "c", "v", "y", "re", "h"}
PAINT_OPERATORS = {"S", "s", "f", "F", "f*", "B", "B*", "b", "b*"}
CLIP_OPERATORS = {"W", "W*", "n"}


@dataclass(frozen=True)
class TaggedPdfResult:
    pdf: Path | None
    message: str
    artifacts_added: int = 0
    lists_wrapped: int = 0
    links_described: int = 0


def export_tagged_pdf(deck: Path, destination: Path) -> TaggedPdfResult:
    # Make the tagged PDF a professor would get from PowerPoint, from the updated deck
    soffice = find_soffice()
    if soffice is None:
        return TaggedPdfResult(None, "LibreOffice was not found, so no PDF was made")
    with tempfile.TemporaryDirectory(prefix="tagged-pdf-") as scratch:
        work = Path(scratch)
        prepared = work / deck.name
        prepare_deck_for_pdf(deck, prepared)
        command = [
            soffice,
            f"-env:UserInstallation=file://{work / 'lo-profile'}",
            "--headless",
            "--convert-to",
            TAGGED_PDF_FILTER,
            "--outdir",
            str(work),
            str(prepared),
        ]
        try:
            subprocess.run(command, capture_output=True, check=True, timeout=RENDER_TIMEOUT_SECONDS)
        except (subprocess.SubprocessError, OSError):
            return TaggedPdfResult(None, "LibreOffice could not export the deck as PDF")
        exported = work / f"{prepared.stem}.pdf"
        if not exported.is_file():
            return TaggedPdfResult(None, "LibreOffice did not write a PDF")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(exported, destination)
    return repair_tags(destination)


def prepare_deck_for_pdf(deck: Path, destination: Path) -> int:
    # LibreOffice drops the description of a connector line, so a described connector is
    # written as a plain line shape in the copy that is exported; it looks the same
    converted = 0
    with zipfile.ZipFile(deck) as source, zipfile.ZipFile(destination, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename.startswith("ppt/slides/slide") and item.filename.endswith(".xml"):
                root = etree.fromstring(data)
                changed = _connectors_to_shapes(root)
                if changed:
                    converted += changed
                    data = etree.tostring(
                        root, xml_declaration=True, encoding="UTF-8", standalone=True
                    )
            target.writestr(item, data, compress_type=item.compress_type)
    return converted


def _connectors_to_shapes(root: etree._Element) -> int:
    changed = 0
    for connector in list(root.iter(f"{{{P_NS}}}cxnSp")):
        names = connector.find(f"{{{P_NS}}}nvCxnSpPr")
        properties = names.find(f"{{{P_NS}}}cNvPr") if names is not None else None
        if properties is None or not (properties.get("descr") or "").strip():
            continue
        connector.tag = f"{{{P_NS}}}sp"
        names.tag = f"{{{P_NS}}}nvSpPr"
        shape_properties = names.find(f"{{{P_NS}}}cNvCxnSpPr")
        if shape_properties is not None:
            shape_properties.tag = f"{{{P_NS}}}cNvSpPr"
            # Connection points belong only to connectors
            for child in list(shape_properties):
                if etree.QName(child).localname in {"stCxn", "endCxn"}:
                    shape_properties.remove(child)
        changed += 1
    return changed


def repair_tags(path: Path) -> TaggedPdfResult:
    # Fix what LibreOffice's export leaves out of PDF/UA: untagged backgrounds, list items
    # outside a list, and links without a description
    with pikepdf.open(path, allow_overwriting_input=True) as pdf:
        artifacts = sum(_mark_untagged_as_artifacts(pdf, page) for page in pdf.pages)
        lists = _wrap_loose_list_items(pdf)
        links = _describe_links(pdf)
        pdf.save(path)
    return TaggedPdfResult(path, "Tagged PDF written", artifacts, lists, links)


def _mark_untagged_as_artifacts(pdf: pikepdf.Pdf, page: pikepdf.Page) -> int:
    # Anything drawn outside a tag is a background or a decoration, so it becomes an artifact
    instructions = list(pikepdf.parse_content_stream(page))
    output: list[Any] = []
    added = 0
    depth = 0
    index = 0
    while index < len(instructions):
        operator = str(instructions[index].operator)
        end = _untagged_unit_end(pdf, page, instructions, index) if depth == 0 else None
        if end is not None:
            output.append(
                pikepdf.ContentStreamInstruction([pikepdf.Name.Artifact], pikepdf.Operator("BMC"))
            )
            output.extend(instructions[index : end + 1])
            output.append(pikepdf.ContentStreamInstruction([], pikepdf.Operator("EMC")))
            added += 1
            index = end + 1
            continue
        if operator in {"BMC", "BDC"}:
            depth += 1
        elif operator == "EMC":
            depth = max(depth - 1, 0)
        output.append(instructions[index])
        index += 1
    if added:
        page.obj.Contents = pdf.make_stream(pikepdf.unparse_content_stream(output))
    return added


def _untagged_unit_end(
    pdf: pikepdf.Pdf, page: pikepdf.Page, instructions: list[Any], start: int
) -> int | None:
    # The last instruction of something drawn that starts here, or None if nothing is drawn
    operator = str(instructions[start].operator)
    if operator == "BT":
        for index in range(start + 1, len(instructions)):
            current = str(instructions[index].operator)
            if current in {"BMC", "BDC"}:
                return None
            if current == "ET":
                return index
        return None
    if operator in PATH_OPERATORS:
        for index in range(start + 1, len(instructions)):
            current = str(instructions[index].operator)
            if current in PAINT_OPERATORS:
                return index
            if current in CLIP_OPERATORS:
                return None
            if current not in PATH_OPERATORS:
                return None
        return None
    if operator in {"sh", "INLINE IMAGE"}:
        return start
    if operator == "Do" and not _form_is_tagged(page, instructions[start].operands):
        return start
    return None


def _form_is_tagged(page: pikepdf.Page, operands: Any) -> bool:
    # A form that carries its own tagged content must not be hidden inside an artifact
    xobjects = page.obj.get("/Resources", {}).get("/XObject", {})
    target = xobjects.get(str(operands[0])) if operands else None
    if target is None or target.get("/Subtype") != pikepdf.Name.Form:
        return False
    return any(
        str(instruction.operator) == "BDC" for instruction in pikepdf.parse_content_stream(target)
    )


def _wrap_loose_list_items(pdf: pikepdf.Pdf) -> int:
    # A list item must sit inside a list; runs of items found elsewhere get a list around them
    root = pdf.Root.get("/StructTreeRoot")
    if root is None:
        return 0
    wrapped = 0
    pending = [root]
    while pending:
        node = pending.pop()
        kids = node.get("/K")
        if kids is None:
            continue
        children = list(kids) if isinstance(kids, pikepdf.Array) else [kids]
        if node.get("/S") != pikepdf.Name.L and any(_is_list_item(kid) for kid in children):
            children, added = _group_list_items(pdf, node, children)
            node.K = pikepdf.Array(children)
            wrapped += added
        pending.extend(kid for kid in children if isinstance(kid, pikepdf.Dictionary))
    return wrapped


def _is_list_item(node: Any) -> bool:
    return isinstance(node, pikepdf.Dictionary) and node.get("/S") == pikepdf.Name.LI


def _group_list_items(
    pdf: pikepdf.Pdf, parent: pikepdf.Dictionary, children: list[Any]
) -> tuple[list[Any], int]:
    grouped: list[Any] = []
    run: list[Any] = []
    added = 0

    def close_run() -> None:
        nonlocal added
        if not run:
            return
        new_list = pdf.make_indirect(
            pikepdf.Dictionary(
                Type=pikepdf.Name.StructElem, S=pikepdf.Name.L, P=parent, K=pikepdf.Array(run)
            )
        )
        if "/Pg" in run[0]:
            new_list.Pg = run[0].Pg
        for item in run:
            item.P = new_list
        grouped.append(new_list)
        run.clear()
        added += 1

    for child in children:
        if _is_list_item(child):
            run.append(child)
        else:
            close_run()
            grouped.append(child)
    close_run()
    return grouped, added


def _describe_links(pdf: pikepdf.Pdf) -> int:
    # Every link needs a description; the web address, or the page it goes to, is used
    described = 0
    page_numbers = {page.obj.objgen: number for number, page in enumerate(pdf.pages, start=1)}
    for page in pdf.pages:
        for annotation in page.obj.get("/Annots", []):
            if annotation.get("/Subtype") != pikepdf.Name.Link:
                continue
            if str(annotation.get("/Contents", "")).strip():
                continue
            annotation.Contents = pikepdf.String(_link_description(annotation, page_numbers))
            described += 1
    return described


def _link_description(annotation: pikepdf.Dictionary, pages: dict[Any, int]) -> str:
    action = annotation.get("/A", {})
    uri = str(action.get("/URI", "")).strip()
    if uri:
        return f"Link to {uri}"
    destination = annotation.get("/Dest", action.get("/D"))
    if isinstance(destination, pikepdf.Array) and len(destination) > 0:
        number = pages.get(destination[0].objgen) if destination[0].is_indirect else None
        if number is not None:
            return f"Link to slide {number}"
    return "Link"
