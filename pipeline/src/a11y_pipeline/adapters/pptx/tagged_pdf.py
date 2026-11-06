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
from a11y_pipeline.adapters.pptx.writer import (
    A_NS,
    DECORATIVE_URI,
    P_NS,
    mark_decorative,
)

# Tagged, PDF/UA, no hidden slides and no notes pages: what PowerPoint's own Save as PDF gives
TAGGED_PDF_FILTER = (
    'pdf:impress_pdf_Export:{"UseTaggedPDF":{"type":"boolean","value":"true"},'
    '"PDFUACompliance":{"type":"boolean","value":"true"},'
    '"ExportHiddenSlides":{"type":"boolean","value":"false"},'
    '"ExportNotesPages":{"type":"boolean","value":"false"}}'
)
# The same for a Word document, through LibreOffice's Writer exporter
DOCUMENT_PDF_FILTER = (
    'pdf:writer_pdf_Export:{"UseTaggedPDF":{"type":"boolean","value":"true"},'
    '"PDFUACompliance":{"type":"boolean","value":"true"}}'
)
PATH_OPERATORS = {"m", "l", "c", "v", "y", "re", "h"}
PAINT_OPERATORS = {"S", "s", "f", "F", "f*", "B", "B*", "b", "b*"}
CLIP_OPERATORS = {"W", "W*", "n"}
# Operators that only set up how the next thing is drawn
STATE_OPERATORS = {"q", "gs", "cm", "w", "J", "j", "M", "d", "ri", "i", "rg", "RG", "g", "G"}


@dataclass(frozen=True)
class TaggedPdfResult:
    pdf: Path | None
    message: str
    artifacts_added: int = 0
    lists_wrapped: int = 0
    links_described: int = 0


def export_tagged_pdf(deck: Path, destination: Path) -> TaggedPdfResult:
    # Make the tagged PDF a professor would get from PowerPoint or Word, from the updated file
    soffice = find_soffice()
    if soffice is None:
        return TaggedPdfResult(None, "LibreOffice was not found, so no PDF was made")
    with tempfile.TemporaryDirectory(prefix="tagged-pdf-") as scratch:
        work = Path(scratch)
        prepared = work / deck.name
        is_document = deck.suffix.lower() == ".docx"
        if is_document:
            shutil.copy2(deck, prepared)
        else:
            prepare_deck_for_pdf(deck, prepared)
        command = [
            soffice,
            f"-env:UserInstallation=file://{work / 'lo-profile'}",
            "--headless",
            "--convert-to",
            DOCUMENT_PDF_FILTER if is_document else TAGGED_PDF_FILTER,
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
    # LibreOffice drops the description of a group and of a connector line. In the copy that
    # is exported, a group's description moves to its first drawn shape (the rest of its
    # drawing is decorative) and a described connector becomes a plain line; both look the same
    converted = 0
    with zipfile.ZipFile(deck) as source, zipfile.ZipFile(destination, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename.startswith("ppt/slides/slide") and item.filename.endswith(".xml"):
                root = etree.fromstring(data)
                changed = _groups_to_carriers(root) + _connectors_to_shapes(root)
                if changed:
                    converted += changed
                    data = etree.tostring(
                        root, xml_declaration=True, encoding="UTF-8", standalone=True
                    )
            target.writestr(item, data, compress_type=item.compress_type)
    return converted


def _groups_to_carriers(root: etree._Element) -> int:
    changed = 0
    for group in list(root.iter(f"{{{P_NS}}}grpSp")):
        properties = _properties(group)
        description = (properties.get("descr") or "").strip() if properties is not None else ""
        if not description:
            continue
        # Shapes with words stay readable text; only the drawing carries the description
        drawn = [
            shape
            for shape in _leaf_shapes(group)
            if not _has_text(shape) and not _is_decorative(_properties(shape))
        ]
        if not drawn:
            continue
        carrier = _properties(drawn[0])
        if carrier is not None:
            carrier.set("descr", description)
        for shape in drawn[1:]:
            shape_properties = _properties(shape)
            if shape_properties is not None:
                mark_decorative(shape_properties)
        changed += 1
    return changed


def _properties(shape: etree._Element) -> etree._Element | None:
    # The cNvPr of any kind of shape: its first child holds the non-visual properties
    return shape.find(f"./*[1]/{{{P_NS}}}cNvPr")


def _leaf_shapes(group: etree._Element) -> list[etree._Element]:
    shapes: list[etree._Element] = []
    for child in group:
        name = etree.QName(child).localname
        if name == "grpSp":
            shapes.extend(_leaf_shapes(child))
        elif name in {"sp", "pic", "cxnSp", "graphicFrame"}:
            shapes.append(child)
    return shapes


def _has_text(shape: etree._Element) -> bool:
    return any((run.text or "").strip() for run in shape.iter(f"{{{A_NS}}}t"))


def _is_decorative(properties: etree._Element | None) -> bool:
    if properties is None:
        return False
    return any(ext.get("uri") == DECORATIVE_URI for ext in properties.iter(f"{{{A_NS}}}ext"))


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
    # Fix what LibreOffice's export leaves out of PDF/UA: tags split across a drawing object,
    # untagged backgrounds, list items outside a list, and links without a description
    with pikepdf.open(path, allow_overwriting_input=True) as pdf:
        lifted: dict[Any, list[Any]] = {}
        for page in pdf.pages:
            _lift_open_tags_from_forms(pdf, page, lifted)
        artifacts = sum(_mark_untagged_as_artifacts(pdf, page) for page in pdf.pages)
        lists = _wrap_loose_list_items(pdf) + _move_links_inside_list_bodies(pdf)
        _retag_text_figures(pdf)
        _tag_untagged_links(pdf)
        links = _describe_links(pdf)
        pdf.save(path)
    return TaggedPdfResult(path, "Tagged PDF written", artifacts, lists, links)


def _structure_elements(pdf: pikepdf.Pdf) -> list[pikepdf.Dictionary]:
    # Every structure element, parents before children
    root = pdf.Root.get("/StructTreeRoot")
    found: list[pikepdf.Dictionary] = []
    pending = [root] if root is not None else []
    while pending:
        node = pending.pop(0)
        kids = node.get("/K")
        children = list(kids) if isinstance(kids, pikepdf.Array) else [kids]
        for kid in children:
            if isinstance(kid, pikepdf.Dictionary) and "/S" in kid:
                found.append(kid)
                pending.append(kid)
    return found


def _kids(node: pikepdf.Dictionary) -> list[Any]:
    kids = node.get("/K")
    if kids is None:
        return []
    return list(kids) if isinstance(kids, pikepdf.Array) else [kids]


def _retag_text_figures(pdf: pikepdf.Pdf) -> int:
    # A group of text boxes comes out as a figure holding paragraphs and no description; it
    # is text a screen reader should read, so it becomes a plain group
    retagged = 0
    for node in _structure_elements(pdf):
        if node.get("/S") != pikepdf.Name.Figure or "/Alt" in node or "/ActualText" in node:
            continue
        if any(isinstance(kid, pikepdf.Dictionary) and "/S" in kid for kid in _kids(node)):
            node.S = pikepdf.Name.Div
            retagged += 1
    return retagged


def _move_links_inside_list_bodies(pdf: pikepdf.Pdf) -> int:
    # A bullet that is all link comes out as item > link > body; lists need item > body > link
    moved = 0
    owners: dict[Any, pikepdf.Dictionary] = {}
    for item in _structure_elements(pdf):
        if item.get("/S") != pikepdf.Name.LI:
            continue
        children = _kids(item)
        for position, link in enumerate(children):
            if not isinstance(link, pikepdf.Dictionary) or link.get("/S") != pikepdf.Name.Link:
                continue
            bodies = [kid for kid in _kids(link) if _role(kid) == pikepdf.Name.LBody]
            if len(bodies) != 1:
                continue
            body = bodies[0]
            others = [kid for kid in _kids(link) if kid is not body and _role(kid) is None]
            content = _kids(body)
            for kid in content:
                if isinstance(kid, pikepdf.Dictionary) and "/S" in kid:
                    kid.P = link
            link.K = pikepdf.Array([*content, *others])
            link.P = body
            body.K = pikepdf.Array([link])
            body.P = item
            children[position] = body
            item.K = pikepdf.Array(children)
            owners[body.objgen] = link
            moved += 1
    if owners:
        _replace_parent_tree_owners(pdf, owners)
    return moved


def _tag_untagged_links(pdf: pikepdf.Pdf) -> int:
    # A link on a shape rather than on text is left out of the structure; it gets a Link tag
    # after the rest of its slide, so a screen reader reaches it
    root = pdf.Root.get("/StructTreeRoot")
    if root is None:
        return 0
    parent_tree = pikepdf.NumberTree(root.ParentTree) if "/ParentTree" in root else None
    if parent_tree is None:
        return 0
    next_key = int(root.get("/ParentTreeNextKey", 0))
    next_key = max([next_key, *(int(key) + 1 for key, _ in parent_tree.items())])
    top = _kids(root)
    added = 0
    for page in pdf.pages:
        for annotation in page.obj.get("/Annots", []):
            if annotation.get("/Subtype") != pikepdf.Name.Link or "/StructParent" in annotation:
                continue
            reference = pikepdf.Dictionary(Type=pikepdf.Name.OBJR, Obj=annotation, Pg=page.obj)
            link = pdf.make_indirect(
                pikepdf.Dictionary(
                    Type=pikepdf.Name.StructElem,
                    S=pikepdf.Name.Link,
                    P=root,
                    Pg=page.obj,
                    K=pikepdf.Array([reference]),
                )
            )
            on_page = [
                index
                for index, kid in enumerate(top)
                if isinstance(kid, pikepdf.Dictionary) and kid.get("/Pg") == page.obj
            ]
            top.insert(on_page[-1] + 1 if on_page else len(top), link)
            parent_tree[next_key] = link
            annotation.StructParent = next_key
            next_key += 1
            added += 1
    if added:
        root.K = pikepdf.Array(top)
        root.ParentTreeNextKey = next_key
    return added


def _role(node: Any) -> Any:
    return node.get("/S") if isinstance(node, pikepdf.Dictionary) else None


def _replace_parent_tree_owners(pdf: pikepdf.Pdf, owners: dict[Any, pikepdf.Dictionary]) -> None:
    # Content that moved from one element to another must point at its new owner
    tree = pdf.Root.StructTreeRoot.get("/ParentTree")
    pending = [tree] if tree is not None else []
    while pending:
        node = pending.pop()
        pending.extend(node.get("/Kids", []))
        numbers = node.get("/Nums", [])
        for index in range(1, len(numbers), 2):
            value = numbers[index]
            if isinstance(value, pikepdf.Array):
                for position, owner in enumerate(value):
                    if isinstance(owner, pikepdf.Dictionary) and owner.objgen in owners:
                        value[position] = owners[owner.objgen]
            elif isinstance(value, pikepdf.Dictionary) and value.objgen in owners:
                numbers[index] = owners[value.objgen]


def _lift_open_tags_from_forms(
    pdf: pikepdf.Pdf, page: pikepdf.Page, lifted: dict[Any, list[Any]]
) -> None:
    # Transparent text is drawn through a form that opens its tag inside the form while the
    # page closes it, so the text counts as untagged. The opening moves onto the page, in
    # front of the drawing of the form, where it wraps the whole form.
    instructions = list(pikepdf.parse_content_stream(page))
    xobjects = page.obj.get("/Resources", {}).get("/XObject", {})
    output: list[Any] = []
    changed = False
    for instruction in instructions:
        if str(instruction.operator) == "Do" and instruction.operands:
            form = xobjects.get(str(instruction.operands[0]))
            openers = _form_openers(pdf, form, lifted) if form is not None else []
            if openers:
                start = len(output)
                while start > 0 and str(output[start - 1].operator) in STATE_OPERATORS:
                    start -= 1
                output[start:start] = openers
                changed = True
        output.append(instruction)
    if changed:
        page.obj.Contents = pdf.make_stream(pikepdf.unparse_content_stream(output))


def _form_openers(pdf: pikepdf.Pdf, form: Any, lifted: dict[Any, list[Any]]) -> list[Any]:
    # The tags a form opens before drawing anything and never closes, taken out of the form
    if form.get("/Subtype") != pikepdf.Name.Form:
        return []
    if form.objgen in lifted:
        return lifted[form.objgen]
    instructions = list(pikepdf.parse_content_stream(form))
    leading = 0
    while leading < len(instructions) and str(instructions[leading].operator) in {"BMC", "BDC"}:
        leading += 1
    balance = sum(
        {"BMC": 1, "BDC": 1, "EMC": -1}.get(str(instruction.operator), 0)
        for instruction in instructions
    )
    count = min(leading, balance)
    openers = instructions[:count] if count > 0 else []
    if openers:
        form.write(pikepdf.unparse_content_stream(instructions[count:]))
    lifted[form.objgen] = openers
    return openers


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
    # Only a tag with a content ID links into the structure; a bare span does not
    return any(
        str(instruction.operator) == "BDC"
        and len(instruction.operands) > 1
        and isinstance(instruction.operands[1], pikepdf.Dictionary)
        and "/MCID" in instruction.operands[1]
        for instruction in pikepdf.parse_content_stream(target)
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
