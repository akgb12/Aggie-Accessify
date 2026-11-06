from lxml import etree

from a11y_pipeline.adapters.docx.ooxml import M_NS

# Large operators Word draws when an n-ary has no character set: the integral
NARY_WORDS = {
    "∑": "sum",
    "∏": "product",
    "∫": "integral",
    "∬": "double integral",
    "∮": "contour integral",
}


def math_text(node: etree._Element) -> str:
    # A Word equation as one line of plain text a screen reader can say, such as
    # "x = (-b ± sqrt(b^2 - 4ac))/(2a)"
    return " ".join(_text(node).split())


def _m(name: str) -> str:
    return f"{{{M_NS}}}{name}"


def _child(node: etree._Element, name: str) -> str:
    found = node.find(_m(name))
    return _text(found) if found is not None else ""


def _group(value: str) -> str:
    # Brackets only where a reader needs them to know where a part ends
    value = value.strip()
    if len(value) <= 1 or value.isalnum():
        return value
    return f"({value})"


def _property(node: etree._Element, properties: str, name: str, default: str) -> str:
    found = node.find(f"{_m(properties)}/{_m(name)}")
    if found is None:
        return default
    return found.get(_m("val"), default)


def _text(node: etree._Element) -> str:
    name = etree.QName(node).localname if etree.QName(node).namespace == M_NS else ""
    if name == "t":
        return node.text or ""
    if name == "f":
        return f"{_group(_child(node, 'num'))}/{_group(_child(node, 'den'))}"
    if name == "sSup":
        return f"{_child(node, 'e')}^{_group(_child(node, 'sup'))}"
    if name == "sSub":
        return f"{_child(node, 'e')}_{_group(_child(node, 'sub'))}"
    if name == "sSubSup":
        base = _child(node, "e")
        return f"{base}_{_group(_child(node, 'sub'))}^{_group(_child(node, 'sup'))}"
    if name == "rad":
        degree = _child(node, "deg").strip()
        inside = _child(node, "e")
        return f"root({degree}, {inside})" if degree else f"sqrt({inside})"
    if name == "d":
        begin = _property(node, "dPr", "begChr", "(")
        end = _property(node, "dPr", "endChr", ")")
        separator = _property(node, "dPr", "sepChr", ",")
        parts = [_text(part) for part in node.findall(_m("e"))]
        return f"{begin}{f'{separator} '.join(parts)}{end}"
    if name == "nary":
        symbol = _property(node, "naryPr", "chr", "∫")
        word = NARY_WORDS.get(symbol, symbol)
        lower = _child(node, "sub").strip()
        upper = _child(node, "sup").strip()
        limits = f" from {lower}" if lower else ""
        limits += f" to {upper}" if upper else ""
        return f"{word}{limits} of {_child(node, 'e')}"
    if name == "func":
        return f"{_child(node, 'fName')}({_child(node, 'e')})"
    if name in {"rPr", "ctrlPr", "dPr", "naryPr", "fPr", "radPr", "sSupPr", "sSubPr", "funcPr"}:
        return ""
    return "".join(_text(child) for child in node)
