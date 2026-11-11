import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from a11y_pipeline.adapters.docx.ooxml import (
    DOCUMENT_PART,
    STYLES_PART,
    paragraphs,
    runs,
    text_of,
    w,
)
from a11y_pipeline.evaluation.contrast import (
    NORMAL_TEXT_RATIO,
    RGB,
    contrast_ratio,
    hex_colour,
    readable_colour,
    required_ratio,
)

# Work out the colour of every run of text in a Word document and what is behind it, the way
# Word does: the run's own setting, then its character style, its paragraph's style and the
# document defaults; shading on the run, its paragraph, its table cell, then the page. Text in
# text boxes, and cells a table style may shade, have no background that can be read here.

WHITE: RGB = (255, 255, 255)
SETTINGS_PART = "word/settings.xml"
# Word's highlighter colours
HIGHLIGHTS: dict[str, RGB] = {
    "yellow": (255, 255, 0),
    "green": (0, 255, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "blue": (0, 0, 255),
    "red": (255, 0, 0),
    "darkBlue": (0, 0, 128),
    "darkCyan": (0, 128, 128),
    "darkGreen": (0, 128, 0),
    "darkMagenta": (128, 0, 128),
    "darkRed": (128, 0, 0),
    "darkYellow": (128, 128, 0),
    "darkGray": (128, 128, 128),
    "lightGray": (192, 192, 192),
    "black": (0, 0, 0),
    "white": WHITE,
}
# Run properties that come after w:color in Word's schema order
AFTER_COLOUR = {
    "spacing", "w", "kern", "position", "sz", "szCs", "highlight", "u", "effect", "bdr", "shd",
    "fitText", "vertAlign", "rtl", "cs", "em", "lang", "eastAsianLayout", "specVanish", "oMath",
}  # fmt: skip
# Word's default size when nothing sets one: 10 points, in half-points
DEFAULT_HALF_POINTS = 20


@dataclass(frozen=True)
class WordRunColour:
    # Position of the run among the document's runs, as the writer counts them, and of its
    # paragraph among the paragraphs
    run: int
    paragraph: int
    text: str
    colour: RGB
    background: RGB
    points: float
    bold: bool

    @property
    def required(self) -> float:
        return required_ratio(self.points, self.bold)

    @property
    def ratio(self) -> float:
        return contrast_ratio(self.colour, self.background)

    def record(self, background: RGB | None = None) -> dict[str, object]:
        # The fix the writer applies, and what the report shows, against the background the
        # rendered page showed when it was measured
        background = background or self.background
        fixed = readable_colour(self.colour, background, NORMAL_TEXT_RATIO)
        record: dict[str, object] = {
            "run": self.run,
            "paragraph": self.paragraph,
            "text": self.text,
            "before": hex_colour(self.colour),
            "background": hex_colour(background),
            "ratio_before": round(contrast_ratio(self.colour, background), 2),
            "required": self.required,
        }
        if fixed is not None:
            record["after"] = hex_colour(fixed)
            record["ratio_after"] = round(contrast_ratio(fixed, background), 2)
        return record


def faint_runs(document: Path) -> list[WordRunColour]:
    # Every run of text too faint for what is behind it
    with zipfile.ZipFile(document) as package:
        names = set(package.namelist())
        root = etree.fromstring(package.read(DOCUMENT_PART))
        styles = _Styles(
            etree.fromstring(package.read(STYLES_PART)) if STYLES_PART in names else None
        )
        settings = etree.fromstring(package.read(SETTINGS_PART)) if SETTINGS_PART in names else None
    page = _page_colour(root, settings)
    # The list keeps every paragraph's element alive, so its identity is a stable key
    all_paragraphs = paragraphs(root)
    numbered = {id(node): index for index, node in enumerate(all_paragraphs)}
    found: list[WordRunColour] = []
    for index, run in enumerate(runs(root)):
        text = " ".join(text_of(run).split())
        if not text:
            continue
        measured = _run_colour(run, styles, page)
        if measured is None:
            continue
        colour, background, points, bold = measured
        paragraph = next(run.iterancestors(w("p")), None)
        number = numbered.get(id(paragraph), -1) if paragraph is not None else -1
        candidate = WordRunColour(index, number, text, colour, background, points, bold)
        if candidate.ratio < candidate.required:
            found.append(candidate)
    return found


def set_run_colour(run: etree._Element, colour: str) -> None:
    # Give a run one explicit colour, dropping any theme colour that would override it
    properties = run.find(w("rPr"))
    if properties is None:
        properties = etree.Element(w("rPr"))
        run.insert(0, properties)
    node = properties.find(w("color"))
    if node is None:
        node = etree.Element(w("color"))
        later = next(
            (child for child in properties if etree.QName(child).localname in AFTER_COLOUR), None
        )
        if later is None:
            properties.append(node)
        else:
            later.addprevious(node)
    for attribute in ("themeColor", "themeShade", "themeTint"):
        node.attrib.pop(w(attribute), None)
    node.set(w("val"), colour)


class _Styles:
    def __init__(self, root: etree._Element | None) -> None:
        self.by_id: dict[str, etree._Element] = {}
        self.defaults: etree._Element | None = None
        self.default_paragraph: str | None = None
        if root is None:
            return
        for style in root.iter(w("style")):
            identifier = style.get(w("styleId"))
            if identifier:
                self.by_id[identifier] = style
            if style.get(w("type")) == "paragraph" and style.get(w("default")) == "1":
                self.default_paragraph = identifier
        self.defaults = root.find(f"{w('docDefaults')}/{w('rPrDefault')}/{w('rPr')}")

    def chain(self, identifier: str | None) -> list[etree._Element]:
        # A style's run properties, then those of the styles it is based on
        found: list[etree._Element] = []
        seen: set[str] = set()
        while identifier and identifier not in seen and identifier in self.by_id:
            seen.add(identifier)
            style = self.by_id[identifier]
            properties = style.find(w("rPr"))
            if properties is not None:
                found.append(properties)
            based = style.find(w("basedOn"))
            identifier = based.get(w("val")) if based is not None else None
        return found

    def shaded(self, identifier: str | None) -> bool:
        # Whether a table style, or one it is based on, shades any cells
        seen: set[str] = set()
        while identifier and identifier not in seen and identifier in self.by_id:
            seen.add(identifier)
            style = self.by_id[identifier]
            for shading in style.iter(w("shd")):
                if _fill(shading) is not None:
                    return True
            based = style.find(w("basedOn"))
            identifier = based.get(w("val")) if based is not None else None
        return False


def _page_colour(root: etree._Element, settings: etree._Element | None) -> RGB:
    # Word shows the page colour only when told to
    shown = settings is not None and settings.find(w("displayBackgroundShape")) is not None
    background = root.find(w("background"))
    if shown and background is not None:
        colour = _hex(background.get(w("color"), ""))
        if colour is not None:
            return colour
    return WHITE


def _run_colour(
    run: etree._Element, styles: _Styles, page: RGB
) -> tuple[RGB, RGB, float, bool] | None:
    if any(etree.QName(node).localname == "txbxContent" for node in run.iterancestors()):
        return None
    paragraph = next(run.iterancestors(w("p")), None)
    own = run.find(w("rPr"))
    if own is not None and own.find(w("vanish")) is not None:
        return None
    character = own.find(w("rStyle")) if own is not None else None
    paragraph_properties = paragraph.find(w("pPr")) if paragraph is not None else None
    paragraph_style = (
        paragraph_properties.find(w("pStyle")) if paragraph_properties is not None else None
    )
    chain = (
        ([own] if own is not None else [])
        + styles.chain(character.get(w("val")) if character is not None else None)
        + styles.chain(
            paragraph_style.get(w("val"))
            if paragraph_style is not None
            else styles.default_paragraph
        )
        + ([styles.defaults] if styles.defaults is not None else [])
    )
    background = _background(run, paragraph_properties, own, styles, page)
    if background is None:
        return None
    colour_node = _first(chain, "color")
    value = colour_node.get(w("val"), "auto") if colour_node is not None else "auto"
    colour = _hex(value)
    if colour is None:
        # Automatic text is drawn black, or white on dark shading, so it is always readable
        return None
    size_node = _first(chain, "sz")
    half_points = (
        int(size_node.get(w("val"), DEFAULT_HALF_POINTS))
        if size_node is not None
        else DEFAULT_HALF_POINTS
    )
    bold_node = _first(chain, "b")
    bold = bold_node is not None and bold_node.get(w("val"), "true") not in {"0", "false"}
    return colour, background, half_points / 2, bold


def _background(
    run: etree._Element,
    paragraph_properties: etree._Element | None,
    own: etree._Element | None,
    styles: _Styles,
    page: RGB,
) -> RGB | None:
    if own is not None:
        highlight = own.find(w("highlight"))
        if highlight is not None and highlight.get(w("val")) in HIGHLIGHTS:
            return HIGHLIGHTS[highlight.get(w("val"), "")]
        shading = own.find(w("shd"))
        if shading is not None and _fill(shading) is not None:
            return _fill(shading)
    if paragraph_properties is not None:
        shading = paragraph_properties.find(w("shd"))
        if shading is not None and _fill(shading) is not None:
            return _fill(shading)
    cell = next(run.iterancestors(w("tc")), None)
    if cell is not None:
        shading = cell.find(f"{w('tcPr')}/{w('shd')}")
        if shading is not None and _fill(shading) is not None:
            return _fill(shading)
        table = next(cell.iterancestors(w("tbl")), None)
        style = table.find(f"{w('tblPr')}/{w('tblStyle')}") if table is not None else None
        if style is not None and styles.shaded(style.get(w("val"))):
            return None
    return page


def _first(chain: list[etree._Element], name: str) -> etree._Element | None:
    for properties in chain:
        node = properties.find(w(name))
        if node is not None:
            return node
    return None


def _fill(shading: etree._Element) -> RGB | None:
    return _hex(shading.get(w("fill"), ""))


def _hex(value: str) -> RGB | None:
    if len(value) != 6 or value.lower() == "auto":
        return None
    try:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except ValueError:
        return None
