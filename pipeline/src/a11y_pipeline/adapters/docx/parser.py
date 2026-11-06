import hashlib
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from lxml import etree

from a11y_pipeline.adapters.docx.math_text import math_text
from a11y_pipeline.adapters.docx.ooxml import (
    A_NS,
    CORE_PART,
    DOCUMENT_PART,
    M_NS,
    O_NS,
    R_NS,
    STYLES_PART,
    V_NS,
    WP_NS,
    figures,
    is_vml,
    maths,
    paragraphs,
    runs,
    tables,
    text_of,
    w,
)
from a11y_pipeline.adapters.pptx.parser import DECORATIVE_URI, is_junk_alt
from a11y_pipeline.adapters.pptx.structure import (
    guess_language,
    is_default_title,
    table_has_header_row,
)
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.ir.ids import IdAllocator, fingerprint_source
from a11y_pipeline.ir.models import (
    Accessibility,
    Container,
    DocumentIR,
    Element,
    Fidelity,
    Issue,
    SourceRef,
)

DC_NS = "http://purl.org/dc/elements/1.1/"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
# A heading is short: a line, not a sentence
MAX_HEADING_CHARACTERS = 120
MAX_HEADING_WORDS = 15
# Text this much larger than the body text reads as a heading
LARGER_POINTS = 1.5
# How much surrounding text a figure's description is given
NEARBY_PARAGRAPHS = 2
VAGUE_LINK_TEXT = {"here", "click here", "link", "this link", "this", "more", "read more", "click"}
CAPTION = re.compile(r"^(figure|fig\.|table|chart|graph|image)\s*\d", re.IGNORECASE)


@dataclass
class _Styles:
    # Paragraph styles by id: display name, outline level, bold and size, following basedOn
    names: dict[str, str] = field(default_factory=dict)
    outline: dict[str, int | None] = field(default_factory=dict)
    bold: dict[str, bool] = field(default_factory=dict)
    size: dict[str, float | None] = field(default_factory=dict)
    default_size: float = 11.0
    default_language: str = ""


def parse(bundle: Bundle) -> DocumentIR:
    # Read a Word document into the canonical model: one container per section, a section
    # starting at each heading or line that looks like one
    path = bundle.root / bundle.main_file
    with zipfile.ZipFile(path) as package:
        names = set(package.namelist())
        root = etree.fromstring(package.read(DOCUMENT_PART))
        styles = _read_styles(package.read(STYLES_PART) if STYLES_PART in names else None)
        relationships = _relationships(package, names)
        core = etree.fromstring(package.read(CORE_PART)) if CORE_PART in names else None
    builder = _Builder(bundle.main_file, styles, relationships)
    builder.read(root)
    texts = [text for text in builder.all_text if text]
    language = styles.default_language
    metadata: dict[str, str] = {
        "title": _core_title(core),
        "language": language,
        "paragraph_count": str(len(builder.paragraph_texts)),
    }
    guessed = guess_language(texts)
    if guessed and not language.lower().startswith(guessed[:2].lower()):
        # Word's default language says one thing and the text plainly another, often a template
        # made in another country; screen readers would read every word in the wrong voice
        metadata["language_proposed"] = guessed
    builder.finish(metadata, guessed)
    return DocumentIR(
        document_id=hashlib.sha256(path.read_bytes()).hexdigest()[:16],
        source_format="docx",
        main_file=bundle.main_file,
        metadata={key: value for key, value in metadata.items() if value or key == "title"},
        containers=builder.containers,
        elements=builder.elements,
        issues=builder.issues,
    )


class _Builder:
    def __init__(self, main_file: str, styles: _Styles, relationships: dict[str, str]) -> None:
        self.main_file = main_file
        self.styles = styles
        self.relationships = relationships
        self.allocator = IdAllocator()
        self.containers: list[Container] = []
        self.elements: dict[str, Element] = {}
        self.issues: list[Issue] = []
        self.all_text: list[str] = []
        self.paragraph_texts: list[str] = []
        self.figure_paragraph: dict[int, int] = {}
        self.figure_ids: list[str] = []
        self.candidates: list[str] = []
        self.headings: list[str] = []
        self.foreign_runs: list[dict[str, Any]] = []
        self.title_paragraph: str | None = None

    def read(self, root: etree._Element) -> None:
        body = root.find(w("body"))
        if body is None:
            return
        all_paragraphs = paragraphs(root)
        self.paragraph_texts = [" ".join(text_of(node).split()) for node in all_paragraphs]
        self.all_text = list(self.paragraph_texts)
        body_size = _body_size(all_paragraphs, self.styles)
        self._new_section()
        # Number each kind of node in the order the writer will find them again
        for kind, nodes in (
            ("figure", figures(root)),
            ("math", maths(root)),
            ("table", tables(root)),
        ):
            for number, found in enumerate(nodes):
                found.set(_mark(kind), str(number))
        # One reading order across figures and equations, which the PDF lists in the same order
        order = 0
        for found in root.iter(f"{{{WP_NS}}}docPr", f"{{{V_NS}}}shape", f"{{{M_NS}}}oMath"):
            if found.get(_mark("figure")) is not None or found.get(_mark("math")) is not None:
                found.set(_mark("order"), str(order))
                order += 1
        for index, node in enumerate(all_paragraphs):
            text = self.paragraph_texts[index]
            table = next(node.iterancestors(w("tbl")), None)
            in_table = table is not None
            in_textbox = any(True for _ in node.iterancestors(w("txbxContent")))
            within: int | None = None
            if in_table:
                outer = table
                for ancestor in table.iterancestors(w("tbl")):
                    outer = ancestor
                if outer.get(_mark("table")) is not None:
                    within = int(outer.get(_mark("table")))
                    if not _seen(outer):
                        self._add_table(outer, within)
            elif text and not in_textbox:
                self._add_paragraph(node, index, text, body_size)
            for drawing in node.iter(f"{{{WP_NS}}}docPr", f"{{{V_NS}}}shape"):
                if drawing.get(_mark("figure")) is not None:
                    self._add_figure(drawing, int(drawing.get(_mark("figure"))), index, within)
            for equation in node.iter(f"{{{M_NS}}}oMath"):
                if equation.get(_mark("math")) is not None:
                    self._add_math(equation, int(equation.get(_mark("math"))), index, within)
            self._links(node, index)
        self._foreign_runs(root)

    def _container(self) -> Container:
        return self.containers[-1]

    def _new_section(self) -> Container:
        container = Container(id=f"section_{len(self.containers) + 1:02d}", kind="section")
        self.containers.append(container)
        return container

    def _add(self, element: Element) -> None:
        self.elements[element.id] = element
        self._container().element_ids.append(element.id)

    def _add_paragraph(self, node: etree._Element, index: int, text: str, body_size: float) -> None:
        style_id = _style_id(node)
        style_name = self.styles.names.get(style_id, "")
        level = _outline_level(node, style_id, self.styles)
        if style_name.lower() == "title":
            if self.title_paragraph is None:
                self._start_section_for_heading()
                element = self._paragraph_element(node, index, text, "document_title", style_name)
                self._add(element)
                self.title_paragraph = element.id
                self._container().title_element_id = element.id
            return
        if level is not None:
            self._start_section_for_heading()
            element = self._paragraph_element(node, index, text, "heading", style_name)
            element.attrs["level"] = level
            element.attrs["styled"] = True
            element.accessibility.role = f"H{level}"
            self._add(element)
            self._container().title_element_id = element.id
            self.headings.append(element.id)
            return
        features = _heading_features(node, text, style_id, self.styles, body_size)
        if features is not None:
            self._start_section_for_heading()
        element = self._paragraph_element(node, index, text, "paragraph", style_name)
        if node.find(f"{w('pPr')}/{w('numPr')}") is not None:
            element.attrs["list_item"] = True
        if features is not None:
            element.attrs["heading_candidate"] = True
            element.attrs["features"] = features
            self.candidates.append(element.id)
            self._add(element)
            self._container().title_element_id = element.id
            return
        self._add(element)

    def _start_section_for_heading(self) -> None:
        # A heading opens a new section, unless the current one is still empty
        if self._container().element_ids:
            self._new_section()

    def _paragraph_element(
        self, node: etree._Element, index: int, text: str, semantic_type: str, style_name: str
    ) -> Element:
        element_id = self.allocator.allocate(self._container().id, semantic_type)  # type: ignore[arg-type]
        return Element(
            id=element_id,
            semantic_type=semantic_type,  # type: ignore[arg-type]
            content={"text": text},
            attrs={"paragraph": index, "style": style_name},
            fingerprint=fingerprint_source(f"p|{index}|{text}"),
            source=_source(index, "paragraph"),
        )

    def _add_table(self, table: etree._Element, index: int) -> None:
        _mark_seen(table)
        rows: list[list[str]] = []
        for row in table.findall(w("tr")):
            rows.append([" ".join(text_of(cell).split()) for cell in row.findall(w("tc"))])
        first = table.find(w("tr"))
        present = first is not None and _has_header_flag(first)
        element_id = self.allocator.allocate(self._container().id, "table")
        header = present or (len(rows) > 1 and table_has_header_row(rows))
        element = Element(
            id=element_id,
            semantic_type="table",
            content={"rows": rows[:3], "text": " ".join(rows[0]) if rows else ""},
            attrs={
                "table": index,
                "row_count": len(rows),
                "first_row_header": header,
                "header_row_added": header and not present,
            },
            fingerprint=fingerprint_source(f"t|{index}|{rows[:1]}"),
            source=_source(index, "table"),
        )
        self._add(element)

    def _add_figure(
        self, node: etree._Element, index: int, paragraph: int, within: int | None
    ) -> None:
        kind, subtype = _figure_kind(node)
        description, decorative = _alt_state(node)
        element_id = self.allocator.allocate(self._container().id, "figure")
        attrs: dict[str, Any] = {
            "figure": index,
            "kind": kind,
            "vml": is_vml(node),
            "paragraph": paragraph,
            "order": int(node.get(_mark("order"), "0")),
            "existing_alt": description,
            "in_table": within,
        }
        media = _media_part(node, self.relationships)
        if media is not None:
            attrs["media"] = media
        nearby, caption = self._nearby(paragraph)
        attrs["nearby"] = nearby
        if caption:
            attrs["caption"] = caption
        accessibility = Accessibility(status="needs_description")
        if decorative:
            accessibility = Accessibility(decorative=True, status="done", locked=True)
        elif description and not is_junk_alt(description):
            accessibility = Accessibility(alt_text=description, status="done", locked=True)
        element = Element(
            id=element_id,
            semantic_type="figure",
            subtype=subtype,
            content={},
            attrs=attrs,
            fingerprint=fingerprint_source(f"f|{index}|{kind}|{media or ''}"),
            source=_source(index, kind),
            accessibility=accessibility,
        )
        self._add(element)
        self.figure_ids.append(element_id)

    def _add_math(
        self, node: etree._Element, index: int, paragraph: int, within: int | None
    ) -> None:
        # Word reads its own equations aloud; the tagged PDF needs them as text
        text = math_text(node)
        element_id = self.allocator.allocate(self._container().id, "formula")
        element = Element(
            id=element_id,
            semantic_type="formula",
            content={"text": text},
            attrs={
                "math": index,
                "paragraph": paragraph,
                "order": int(node.get(_mark("order"), "0")),
                "in_table": within,
            },
            fingerprint=fingerprint_source(f"m|{index}|{text}"),
            source=_source(index, "math"),
            accessibility=Accessibility(alt_text=text or None, status="done"),
            # The text is the equation itself, read from its source, so it is exact
            fidelity=Fidelity(signature=fingerprint_source(text) if text else None),
        )
        self._add(element)

    def _nearby(self, paragraph: int) -> tuple[list[str], str | None]:
        # The paragraphs around a figure, and a caption next to it
        texts = self.paragraph_texts
        before = [text for text in texts[max(0, paragraph - 6) : paragraph] if text]
        after = [text for text in texts[paragraph + 1 : paragraph + 7] if text]
        own = texts[paragraph] if paragraph < len(texts) else ""
        nearby = [*before[-NEARBY_PARAGRAPHS:], *([own] if own else []), *after[:NEARBY_PARAGRAPHS]]
        caption = next(
            (text for text in [*after[:1], *before[-1:]] if CAPTION.match(text)),
            None,
        )
        return [text[:400] for text in nearby], caption

    def _links(self, node: etree._Element, paragraph: int) -> None:
        for link in node.iter(w("hyperlink")):
            text = " ".join(text_of(link).split())
            if text.lower().strip(" .") in VAGUE_LINK_TEXT:
                self.issues.append(
                    Issue(
                        element_id=None,
                        code="vague_link_text",
                        severity="warning",
                        message=(
                            f'A link reads only "{text}", which says nothing out of context. '
                            "Use words that say where it goes, such as the page's name."
                        ),
                        details={"paragraph": paragraph, "text": text},
                    )
                )

    def _foreign_runs(self, root: etree._Element) -> None:
        # Words marked as another language: left over from a template, or real foreign text
        for index, run in enumerate(runs(root)):
            language = run.find(f"{w('rPr')}/{w('lang')}")
            value = language.get(w("val")) if language is not None else None
            text = text_of(run).strip()
            if not value or not text:
                continue
            self.foreign_runs.append({"run": index, "language": value, "text": text[:80]})

    def finish(self, metadata: dict[str, str], guessed: str | None) -> None:
        # One element for the document's outline: the headings, the title and the languages,
        # decided together in one step
        if not self.containers[0].element_ids and len(self.containers) > 1:
            self.containers.pop(0)
        title_text = ""
        if self.title_paragraph is not None:
            title_text = str(self.elements[self.title_paragraph].content.get("text", ""))
        needs_title = not metadata.get("title") or is_default_title(metadata["title"])
        english = guessed is not None and guessed.startswith("en")
        # Only runs marked as something other than the document's real language
        foreign = [run for run in self.foreign_runs if not run["language"].lower().startswith("en")]
        foreign = foreign if english else []
        needs_work = bool(self.candidates or foreign or (needs_title and not title_text))
        first = self.containers[0]
        element_id = self.allocator.allocate(first.id, "unknown")
        outline = Element(
            id=element_id,
            semantic_type="unknown",
            subtype="document_outline",
            content={"text": title_text if needs_title else ""},
            attrs={
                "candidates": list(self.candidates),
                "headings": list(self.headings),
                "foreign_runs": foreign,
                "needs_title": needs_title,
                "english_runs": [],
            },
            fingerprint=fingerprint_source(f"outline|{self.main_file}"),
            source=_source(0, "document"),
            accessibility=Accessibility(status="needs_description" if needs_work else "done"),
        )
        self.elements[element_id] = outline
        first.element_ids.insert(0, element_id)
        self.issues.extend(_heading_level_issues(self.elements, self.headings))
        if needs_title and title_text:
            metadata["title_proposed"] = title_text


def _mark(kind: str) -> str:
    # Attributes set only on the parser's own copy of the XML, never written back
    return f"{{urn:a11y}}{kind}"


def _seen(table: etree._Element) -> bool:
    return table.get("{urn:a11y}seen") == "1"


def _mark_seen(table: etree._Element) -> None:
    # The parse works on its own copy of the XML, so a marker attribute is harmless
    table.set("{urn:a11y}seen", "1")


def _has_header_flag(row: etree._Element) -> bool:
    flag = row.find(f"{w('trPr')}/{w('tblHeader')}")
    if flag is None:
        return False
    return flag.get(w("val"), "true").lower() not in {"0", "false", "off"}


def _source(index: int, native_type: str) -> SourceRef:
    return SourceRef(
        file=DOCUMENT_PART,
        line_start=index,
        line_end=index,
        char_start=0,
        char_end=0,
        native_type=native_type,
    )


def _style_id(node: etree._Element) -> str:
    style = node.find(f"{w('pPr')}/{w('pStyle')}")
    return style.get(w("val"), "") if style is not None else ""


def _outline_level(node: etree._Element, style_id: str, styles: _Styles) -> int | None:
    # A heading level from the paragraph itself or its style; 1 is the top level
    own = node.find(f"{w('pPr')}/{w('outlineLvl')}")
    if own is not None:
        value = int(own.get(w("val"), "9"))
        return value + 1 if value < 9 else None
    name = styles.names.get(style_id, "").lower()
    match = re.fullmatch(r"heading ?(\d)", name)
    if match:
        return int(match.group(1))
    level = styles.outline.get(style_id)
    return level + 1 if level is not None and level < 9 else None


def _heading_features(
    node: etree._Element, text: str, style_id: str, styles: _Styles, body_size: float
) -> dict[str, Any] | None:
    # A short standalone line set apart by bold or size: it looks like a heading but a screen
    # reader cannot find it as one. The model decides; these are only the candidates.
    if len(text) > MAX_HEADING_CHARACTERS or len(text.split()) > MAX_HEADING_WORDS:
        return None
    if text.endswith((".", ",", ";")) or node.find(f"{w('pPr')}/{w('numPr')}") is not None:
        return None
    visible = [run for run in node.iter(w("r")) if text_of(run).strip()]
    if not visible:
        return None
    bold = all(_run_bold(run, style_id, styles) for run in visible)
    sizes = [_run_size(run, style_id, styles) for run in visible]
    size = max(sizes)
    larger = size >= body_size + LARGER_POINTS
    if not (bold or larger):
        return None
    alignment = node.find(f"{w('pPr')}/{w('jc')}")
    return {
        "bold": bold,
        "points": round(size, 1),
        "capitals": text.isupper(),
        "centered": alignment is not None and alignment.get(w("val")) == "center",
    }


def _run_bold(run: etree._Element, style_id: str, styles: _Styles) -> bool:
    flag = run.find(f"{w('rPr')}/{w('b')}")
    if flag is not None:
        return flag.get(w("val"), "true").lower() not in {"0", "false"}
    return styles.bold.get(style_id, False)


def _run_size(run: etree._Element, style_id: str, styles: _Styles) -> float:
    size = run.find(f"{w('rPr')}/{w('sz')}")
    if size is not None and size.get(w("val"), "").isdigit():
        return int(size.get(w("val"))) / 2
    return styles.size.get(style_id) or styles.default_size


def _body_size(nodes: list[etree._Element], styles: _Styles) -> float:
    # The most common text size, weighted by how much text uses it
    counts: Counter[float] = Counter()
    for node in nodes:
        style_id = _style_id(node)
        for run in node.iter(w("r")):
            characters = len(text_of(run))
            if characters:
                counts[_run_size(run, style_id, styles)] += characters
    return counts.most_common(1)[0][0] if counts else styles.default_size


def _read_styles(data: bytes | None) -> _Styles:
    styles = _Styles()
    if data is None:
        return styles
    root = etree.fromstring(data)
    defaults = root.find(f"{w('docDefaults')}/{w('rPrDefault')}/{w('rPr')}")
    if defaults is not None:
        size = defaults.find(w("sz"))
        if size is not None and size.get(w("val"), "").isdigit():
            styles.default_size = int(size.get(w("val"))) / 2
        language = defaults.find(w("lang"))
        if language is not None:
            styles.default_language = language.get(w("val"), "")
    raw: dict[str, etree._Element] = {}
    for style in root.findall(w("style")):
        if style.get(w("type")) == "paragraph":
            raw[style.get(w("styleId"), "")] = style
    for style_id in raw:
        chain = _style_chain(style_id, raw)
        name = raw[style_id].find(w("name"))
        styles.names[style_id] = name.get(w("val"), "") if name is not None else ""
        styles.outline[style_id] = _first(chain, f"{w('pPr')}/{w('outlineLvl')}", int)
        bold = _first(chain, f"{w('rPr')}/{w('b')}", lambda value: value not in {"0", "false"})
        styles.bold[style_id] = bool(bold)
        size = _first(chain, f"{w('rPr')}/{w('sz')}", lambda value: int(value) / 2)
        styles.size[style_id] = size
    return styles


def _style_chain(style_id: str, raw: dict[str, etree._Element]) -> list[etree._Element]:
    chain: list[etree._Element] = []
    current: str | None = style_id
    while current in raw and len(chain) < 20:
        style = raw[current]
        chain.append(style)
        based = style.find(w("basedOn"))
        current = based.get(w("val")) if based is not None else None
    return chain


def _first(chain: list[etree._Element], path: str, convert: Any) -> Any:
    for style in chain:
        found = style.find(path)
        if found is not None:
            try:
                return convert(found.get(w("val"), "true"))
            except ValueError:
                return None
    return None


def _relationships(package: zipfile.ZipFile, names: set[str]) -> dict[str, str]:
    # Relationship ids of the document part, to the package paths they point at
    part = "word/_rels/document.xml.rels"
    if part not in names:
        return {}
    root = etree.fromstring(package.read(part))
    found: dict[str, str] = {}
    for relationship in root.findall(f"{{{REL_NS}}}Relationship"):
        if relationship.get("TargetMode") == "External":
            continue
        target = relationship.get("Target", "")
        path = (
            PurePosixPath("word") / target
            if not target.startswith("/")
            else PurePosixPath(target[1:])
        )
        parts: list[str] = []
        for piece in path.parts:
            if piece == "..":
                if parts:
                    parts.pop()
            else:
                parts.append(piece)
        found[relationship.get("Id", "")] = "/".join(parts)
    return found


def _figure_kind(node: etree._Element) -> tuple[str, str]:
    # What the drawing is: its kind for the writer and the subtype the describer is told
    if is_vml(node):
        holder = node.getparent()
        ole = holder.find(f"{{{O_NS}}}OLEObject") if holder is not None else None
        if ole is not None:
            program = (ole.get("ProgID") or "").lower()
            if program.startswith("equation") or "mathtype" in program:
                return "vml_object", "equation"
            return "vml_object", "image"
        return "vml_picture", "image"
    graphic = (
        node.getparent().find(f".//{{{A_NS}}}graphicData") if node.getparent() is not None else None
    )
    uri = graphic.get("uri", "") if graphic is not None else ""
    kind = uri.rstrip("/").rsplit("/", 1)[-1]
    if kind == "picture":
        return "picture", "image"
    if kind == "chart" or kind.endswith("chart"):
        return "chart", "chart"
    if kind in {"wordprocessingGroup", "wordprocessingCanvas", "wordprocessingShape", "diagram"}:
        return kind, "diagram"
    return kind or "drawing", "other"


def _alt_state(node: etree._Element) -> tuple[str, bool]:
    # The author's own description, and whether they marked the drawing decorative
    if is_vml(node):
        return (node.get("alt") or "").strip(), False
    description = (node.get("descr") or "").strip()
    decorative = any(
        extension.get("uri") == DECORATIVE_URI
        and any(child.get("val") == "1" for child in extension)
        for extension in node.iter(f"{{{A_NS}}}ext")
    )
    return description, decorative


def _media_part(node: etree._Element, relationships: dict[str, str]) -> str | None:
    # The picture file a drawing shows, when it is a plain picture
    if is_vml(node):
        data = node.find(f"{{{V_NS}}}imagedata")
        rel = data.get(f"{{{R_NS}}}id") if data is not None else None
    else:
        holder = node.getparent()
        blip = holder.find(f".//{{{A_NS}}}blip") if holder is not None else None
        rel = blip.get(f"{{{R_NS}}}embed") if blip is not None else None
        graphic = holder.find(f".//{{{A_NS}}}graphicData") if holder is not None else None
        if graphic is None or not graphic.get("uri", "").endswith("/picture"):
            return None
    return relationships.get(rel or "")


def _core_title(core: etree._Element | None) -> str:
    if core is None:
        return ""
    title = core.find(f"{{{DC_NS}}}title")
    return " ".join((title.text or "").split()) if title is not None else ""


def _heading_level_issues(elements: dict[str, Element], headings: list[str]) -> list[Issue]:
    # A jump such as level 1 straight to level 3 leaves a gap in the outline a screen reader
    # user navigates by. Restyling is the author's call, so it is reported here; the tagged
    # PDF closes the gap.
    issues: list[Issue] = []
    previous = 0
    for element_id in headings:
        level = int(elements[element_id].attrs.get("level", 1))
        if level > previous + 1:
            issues.append(
                Issue(
                    element_id=element_id,
                    code="heading_level_skipped",
                    severity="warning",
                    message=(
                        f"This heading is level {level} but the heading before it is level "
                        f"{previous or 'none'}, so a level is skipped. Use Heading "
                        f"{previous + 1} for it."
                    ),
                    details={"level": level, "previous": previous},
                )
            )
        previous = level
    return issues


__all__ = ["Path", "parse"]
