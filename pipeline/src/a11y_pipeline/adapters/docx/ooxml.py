from lxml import etree

# WordprocessingML and the DrawingML, VML and math parts a Word document embeds
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
V_NS = "urn:schemas-microsoft-com:vml"
O_NS = "urn:schemas-microsoft-com:office:office"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
DOCUMENT_PART = "word/document.xml"
STYLES_PART = "word/styles.xml"
CORE_PART = "docProps/core.xml"


def w(name: str) -> str:
    return f"{{{W_NS}}}{name}"


def in_fallback(node: etree._Element) -> bool:
    # Word keeps an older copy of some drawings in mc:Fallback; only the first copy counts
    return any(
        etree.QName(ancestor).namespace == MC_NS and etree.QName(ancestor).localname == "Fallback"
        for ancestor in node.iterancestors()
    )


def paragraphs(root: etree._Element) -> list[etree._Element]:
    # Every paragraph in reading order, including those in tables and text boxes
    return [node for node in root.iter(w("p")) if not in_fallback(node)]


def runs(root: etree._Element) -> list[etree._Element]:
    return [node for node in root.iter(w("r")) if not in_fallback(node)]


def tables(root: etree._Element) -> list[etree._Element]:
    # Top-level tables only; a table inside a cell belongs to its outer table
    return [
        node
        for node in root.iter(w("tbl"))
        if not in_fallback(node) and not any(True for _ in node.iterancestors(w("tbl")))
    ]


def maths(root: etree._Element) -> list[etree._Element]:
    # Each Word equation once: an equation inside another is part of it
    return [
        node
        for node in root.iter(f"{{{M_NS}}}oMath")
        if not in_fallback(node) and not any(True for _ in node.iterancestors(f"{{{M_NS}}}oMath"))
    ]


def figures(root: etree._Element) -> list[etree._Element]:
    # Every drawing in reading order: a DrawingML drawing is found by its wp:docPr, an older
    # VML picture or embedded object by its v:shape
    found: list[etree._Element] = []
    for node in root.iter(f"{{{WP_NS}}}docPr", f"{{{V_NS}}}shape"):
        if in_fallback(node):
            continue
        if etree.QName(node).namespace == V_NS and not _vml_has_content(node):
            continue
        found.append(node)
    return found


def _vml_has_content(shape: etree._Element) -> bool:
    # A VML shape counts when it shows a picture or stands for an embedded object
    if shape.find(f"{{{V_NS}}}imagedata") is not None:
        return True
    return (
        shape.getparent() is not None and shape.getparent().find(f"{{{O_NS}}}OLEObject") is not None
    )


def text_of(node: etree._Element) -> str:
    return "".join(part.text or "" for part in node.iter(w("t")))


def is_vml(node: etree._Element) -> bool:
    return etree.QName(node).namespace == V_NS
