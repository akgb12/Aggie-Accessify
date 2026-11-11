import colorsys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lxml import etree
from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT

from a11y_pipeline.evaluation.contrast import RGB, contrast_ratio, required_ratio

# Work out the colour every run of text is drawn in, and the colour behind it, from the deck's
# XML the way PowerPoint does: the run's own setting, then the shape's, the layout's and the
# master's, through the theme. A background that is a picture or a gradient cannot be known
# from the XML, so it is left as None.

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = {"p": P_NS, "a": A_NS}
DEFAULT_POINTS = 18.0
WHITE: RGB = (255, 255, 255)
BLACK: RGB = (0, 0, 0)
FILLS = {"noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill"}
# Placeholder types that take the master's title text style; the rest of the placeholders that
# hold text take the body style
TITLE_TYPES = {"title", "ctrTitle"}
OTHER_TYPES = {"dt", "ftr", "sldNum", "hdr"}
PRESET_COLOURS: dict[str, RGB] = {
    "black": BLACK,
    "white": WHITE,
    "red": (255, 0, 0),
    "green": (0, 128, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
    "ltGray": (211, 211, 211),
    "dkGray": (169, 169, 169),
    "orange": (255, 165, 0),
}


@dataclass(frozen=True)
class RunColour:
    part: str
    slide: int
    # The shape that holds the text, which can sit inside a group, and the top-level shape the
    # document model knows it by
    shape_id: int
    top_shape_id: int
    # Position of the run among the shape's runs, in document order
    run: int
    text: str
    colour: RGB
    background: RGB | None
    points: float
    bold: bool
    hyperlink: bool
    # The holding shape's box on the slide in EMU from the top-left corner
    box: tuple[float, float, float, float] | None = None

    @property
    def required(self) -> float:
        return required_ratio(self.points, self.bold)

    @property
    def ratio(self) -> float | None:
        if self.background is None:
            return None
        return contrast_ratio(self.colour, self.background)

    @property
    def fails(self) -> bool:
        ratio = self.ratio
        return ratio is not None and ratio < self.required


def text_runs(shape: etree._Element) -> list[etree._Element]:
    # Every run of a shape's text in document order; the writer counts runs the same way
    return [
        node
        for node in shape.iter(f"{{{A_NS}}}r", f"{{{A_NS}}}fld")
        if node.find("a:t", NS) is not None
    ]


def deck_run_colours(deck: Path) -> list[RunColour]:
    presentation = Presentation(str(deck))
    defaults = presentation.part._element.find("p:defaultTextStyle", NS)
    found: list[RunColour] = []
    for number, slide in enumerate(presentation.slides, start=1):
        layout = slide.slide_layout
        master = layout.slide_master
        theme = _Theme(master)
        palette = theme.palette(_colour_map(slide._element, layout._element, master._element))
        context = _SlideStyles(palette, theme, layout._element, master._element, defaults)
        drawn = _drawn_shapes(slide._element, layout._element, master._element)
        background = _slide_background(palette, theme, slide._element, layout, master)
        part = str(slide.part.partname).lstrip("/")
        for index, item in enumerate(drawn):
            if item.layer != "slide" or item.hidden:
                continue
            found.extend(_shape_runs(item, drawn[:index], background, context, part, number))
    return found


@dataclass
class _Drawn:
    node: etree._Element
    top_id: int
    box: tuple[float, float, float, float] | None
    layer: str
    hidden: bool


class _Theme:
    def __init__(self, master: Any) -> None:
        self.colours: dict[str, RGB] = {}
        self.fill_styles: list[etree._Element] = []
        self.background_styles: list[etree._Element] = []
        for relationship in master.part.rels.values():
            if relationship.reltype != RT.THEME:
                continue
            root = etree.fromstring(relationship.target_part.blob)
            scheme = root.find(".//a:clrScheme", NS)
            for child in scheme if scheme is not None else []:
                colour = _plain_colour(child[0]) if len(child) else None
                if colour is not None:
                    self.colours[etree.QName(child).localname] = colour
            fills = root.find(".//a:fmtScheme/a:fillStyleLst", NS)
            backgrounds = root.find(".//a:fmtScheme/a:bgFillStyleLst", NS)
            self.fill_styles = list(fills) if fills is not None else []
            self.background_styles = list(backgrounds) if backgrounds is not None else []

    def palette(self, mapping: dict[str, str]) -> "_Palette":
        return _Palette(self.colours, mapping)

    def style_fill(self, index: int) -> etree._Element | None:
        # fillRef and bgRef index 1-999 into the fill styles and 1001 up into the backgrounds
        styles, position = (
            (self.background_styles, index - 1001)
            if index > 1000
            else (self.fill_styles, index - 1)
        )
        return styles[position] if 0 <= position < len(styles) else None


class _Palette:
    def __init__(self, scheme: dict[str, RGB], mapping: dict[str, str]) -> None:
        self.scheme = scheme
        self.mapping = mapping

    def resolve(
        self, node: etree._Element | None, placeholder: RGB | None = None
    ) -> tuple[RGB, float] | None:
        # A colour element and its adjustments; returns the colour and its opacity
        if node is None:
            return None
        kind = etree.QName(node).localname
        base: RGB | None
        if kind == "schemeClr":
            name = node.get("val", "")
            if name == "phClr":
                base = placeholder
            else:
                base = self.scheme.get(self.mapping.get(name, name))
        else:
            base = _plain_colour(node)
        if base is None:
            return None
        return _adjust(base, node)


def _plain_colour(node: etree._Element) -> RGB | None:
    kind = etree.QName(node).localname
    if kind == "srgbClr":
        return _hex(node.get("val", ""))
    if kind == "sysClr":
        return _hex(node.get("lastClr", "")) or (WHITE if node.get("val") == "window" else BLACK)
    if kind == "prstClr":
        return PRESET_COLOURS.get(node.get("val", ""))
    if kind == "scrgbClr":
        return tuple(  # type: ignore[return-value]
            _from_linear(int(node.get(axis, "0")) / 100000) for axis in ("r", "g", "b")
        )
    if kind == "hslClr":
        hue = int(node.get("hue", "0")) / 21600000
        saturation = int(node.get("sat", "0")) / 100000
        lightness = int(node.get("lum", "0")) / 100000
        red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
        return (round(red * 255), round(green * 255), round(blue * 255))
    return None


def _hex(value: str) -> RGB | None:
    if len(value) != 6:
        return None
    try:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except ValueError:
        return None


def _to_linear(value: int) -> float:
    scaled = value / 255
    return scaled / 12.92 if scaled <= 0.04045 else ((scaled + 0.055) / 1.055) ** 2.4


def _from_linear(value: float) -> int:
    value = min(1.0, max(0.0, value))
    scaled = value * 12.92 if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055
    return round(scaled * 255)


def _adjust(colour: RGB, node: etree._Element) -> tuple[RGB, float]:
    # Apply the adjustments PowerPoint stores under a colour, in order
    alpha = 1.0
    for adjustment in node:
        name = etree.QName(adjustment).localname
        value = int(adjustment.get("val", "0")) / 100000
        if name in {"lumMod", "lumOff", "satMod"}:
            hue, lightness, saturation = colorsys.rgb_to_hls(*(part / 255 for part in colour))
            if name == "lumMod":
                lightness *= value
            elif name == "lumOff":
                lightness += value
            else:
                saturation *= value
            lightness = min(1.0, max(0.0, lightness))
            saturation = min(1.0, max(0.0, saturation))
            red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
            colour = (round(red * 255), round(green * 255), round(blue * 255))
        elif name == "tint":
            colour = tuple(  # type: ignore[assignment]
                _from_linear(_to_linear(part) * value + (1 - value)) for part in colour
            )
        elif name == "shade":
            colour = tuple(_from_linear(_to_linear(part) * value) for part in colour)  # type: ignore[assignment]
        elif name == "alpha":
            alpha = value
    return colour, alpha


def _blend(colour: RGB, alpha: float, under: RGB) -> RGB:
    return tuple(  # type: ignore[return-value]
        round(top * alpha + bottom * (1 - alpha)) for top, bottom in zip(colour, under, strict=True)
    )


def _colour_map(*parts: etree._Element) -> dict[str, str]:
    # The slide's own mapping of bg1/tx1 onto the theme, else its layout's, else the master's
    for part in parts:
        override = part.find("p:clrMapOvr/a:overrideClrMapping", NS)
        if override is not None:
            return dict(override.attrib)
        mapping = part.find("p:clrMap", NS)
        if mapping is not None:
            return dict(mapping.attrib)
    return {"bg1": "lt1", "tx1": "dk1", "bg2": "lt2", "tx2": "dk2"}


class _SlideStyles:
    # The text styles a slide's shapes inherit from
    def __init__(
        self,
        palette: _Palette,
        theme: _Theme,
        layout: etree._Element,
        master: etree._Element,
        defaults: etree._Element | None,
    ) -> None:
        self.palette = palette
        self.theme = theme
        self.layout = layout
        self.master = master
        self.defaults = defaults

    def chain(
        self, shape: etree._Element, level: int
    ) -> tuple[list[etree._Element], list[etree._Element]]:
        # Run property sets from nearest to furthest, not counting the run's own: those that
        # outrank the shape style's font colour, and the deck-wide defaults that it outranks
        near: list[etree._Element] = []
        far: list[etree._Element] = []
        _add_level(near, shape.find("p:txBody/a:lstStyle", NS), level)
        placeholder = shape.find("./*[1]/p:nvPr/p:ph", NS)
        if placeholder is not None:
            kind = placeholder.get("type", "obj")
            for part in (self.layout, self.master):
                match = _matching_placeholder(part, kind, placeholder.get("idx"))
                if match is not None:
                    _add_level(near, match.find("p:txBody/a:lstStyle", NS), level)
            style = (
                "titleStyle"
                if kind in TITLE_TYPES
                else "otherStyle"
                if kind in OTHER_TYPES
                else "bodyStyle"
            )
            _add_level(near, self.master.find(f"p:txStyles/p:{style}", NS), level)
        _add_level(far, self.defaults, level)
        return near, far


def _add_level(found: list[etree._Element], styles: etree._Element | None, level: int) -> None:
    if styles is None:
        return
    for name in (f"a:lvl{level}pPr/a:defRPr", "a:defPPr/a:defRPr"):
        properties = styles.find(name, NS)
        if properties is not None:
            found.append(properties)
            return


def _matching_placeholder(
    part: etree._Element, kind: str, index: str | None
) -> etree._Element | None:
    shapes = part.findall("p:cSld/p:spTree/p:sp", NS)
    if index is not None:
        for shape in shapes:
            placeholder = shape.find("./*[1]/p:nvPr/p:ph", NS)
            if placeholder is not None and placeholder.get("idx") == index:
                return shape
    wanted = {"title": "title", "ctrTitle": "title"}.get(kind, kind)
    for shape in shapes:
        placeholder = shape.find("./*[1]/p:nvPr/p:ph", NS)
        if placeholder is None:
            continue
        other = placeholder.get("type", "obj")
        if {"title": "title", "ctrTitle": "title"}.get(other, other) == wanted:
            return shape
        if wanted in {"obj", "body", "subTitle"} and other in {"obj", "body"}:
            return shape
    return None


def _drawn_shapes(
    slide: etree._Element, layout: etree._Element, master: etree._Element
) -> list[_Drawn]:
    # Everything drawn on the slide in painting order: the master's and layout's own shapes,
    # when shown, under the slide's. Groups are opened so their members count one by one.
    drawn: list[_Drawn] = []
    layers = [("master", master), ("layout", layout), ("slide", slide)]
    if slide.get("showMasterSp") == "0":
        layers = [("slide", slide)]
    elif layout.get("showMasterSp") == "0":
        layers = [("layout", layout), ("slide", slide)]
    for layer, part in layers:
        tree = part.find("p:cSld/p:spTree", NS)
        if tree is None:
            continue
        for child in tree:
            if not isinstance(child.tag, str) or _local(child) in {
                "nvGrpSpPr",
                "grpSpPr",
                "extLst",
            }:
                continue
            if layer != "slide" and child.find("./*[1]/p:nvPr/p:ph", NS) is not None:
                # A layout's placeholders are prompts, never drawn on the slide
                continue
            top_id = _shape_id(child)
            _open(child, top_id, layer, _identity, drawn, _is_hidden(child))
            if layer == "slide" and drawn and drawn[-1].node is child and drawn[-1].box is None:
                drawn[-1].box = _inherited_box(child, layout, master)
    return drawn


def _inherited_box(
    shape: etree._Element, layout: etree._Element, master: etree._Element
) -> tuple[float, float, float, float] | None:
    # A placeholder that was never moved takes its position from the layout, else the master
    placeholder = shape.find("./*[1]/p:nvPr/p:ph", NS)
    if placeholder is None:
        return None
    for part in (layout, master):
        match = _matching_placeholder(part, placeholder.get("type", "obj"), placeholder.get("idx"))
        if match is not None:
            box = _box(match, _identity)
            if box is not None:
                return box
    return None


def _open(
    node: etree._Element,
    top_id: int,
    layer: str,
    transform: Any,
    drawn: list[_Drawn],
    hidden: bool,
) -> None:
    hidden = hidden or _is_hidden(node)
    if _local(node) == "grpSp":
        inner = _group_transform(node, transform)
        for child in node:
            if isinstance(child.tag, str) and _local(child) in {
                "sp",
                "grpSp",
                "pic",
                "graphicFrame",
                "cxnSp",
            }:
                _open(child, top_id, layer, inner, drawn, hidden)
        return
    drawn.append(_Drawn(node, top_id, _box(node, transform), layer, hidden))


def _identity(box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    return box


def _group_transform(group: etree._Element, outer: Any) -> Any:
    # Map a group's child coordinates onto the slide
    frame = group.find("p:grpSpPr/a:xfrm", NS)
    if frame is None:
        return outer
    offset = frame.find("a:off", NS)
    size = frame.find("a:ext", NS)
    child_offset = frame.find("a:chOff", NS)
    child_size = frame.find("a:chExt", NS)
    if None in (offset, size, child_offset, child_size):
        return outer
    x, y = int(offset.get("x", "0")), int(offset.get("y", "0"))
    cx, cy = int(size.get("cx", "0")), int(size.get("cy", "0"))
    chx, chy = int(child_offset.get("x", "0")), int(child_offset.get("y", "0"))
    chcx, chcy = int(child_size.get("cx", "0")) or 1, int(child_size.get("cy", "0")) or 1

    def inner(box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        left, top, right, bottom = box
        return outer(
            (
                x + (left - chx) * cx / chcx,
                y + (top - chy) * cy / chcy,
                x + (right - chx) * cx / chcx,
                y + (bottom - chy) * cy / chcy,
            )
        )

    return inner


def _box(node: etree._Element, transform: Any) -> tuple[float, float, float, float] | None:
    frame = node.find("p:spPr/a:xfrm", NS)
    if frame is None:
        frame = node.find("p:xfrm", NS)
    if frame is None:
        return None
    offset = frame.find("a:off", NS)
    size = frame.find("a:ext", NS)
    if offset is None or size is None:
        return None
    left, top = int(offset.get("x", "0")), int(offset.get("y", "0"))
    return transform((left, top, left + int(size.get("cx", "0")), top + int(size.get("cy", "0"))))


def _local(node: etree._Element) -> str:
    return etree.QName(node).localname


def _properties(node: etree._Element) -> etree._Element | None:
    # The cNvPr that holds a shape's id and hidden flag
    return node.find("./*[1]/p:cNvPr", NS)


def _shape_id(node: etree._Element) -> int:
    properties = _properties(node)
    value = properties.get("id", "") if properties is not None else ""
    return int(value) if value.isdigit() else -1


def _is_hidden(node: etree._Element) -> bool:
    properties = _properties(node)
    return properties is not None and properties.get("hidden") in {"1", "true"}


def _slide_background(
    palette: _Palette, theme: _Theme, slide: etree._Element, layout: Any, master: Any
) -> RGB | None:
    # The first part that sets a background decides it; a picture or gradient is unknown
    for part in (slide, layout._element, master._element):
        background = part.find("p:cSld/p:bg", NS)
        if background is None:
            continue
        properties = background.find("p:bgPr", NS)
        if properties is not None:
            return _solid(properties, palette, None)
        reference = background.find("p:bgRef", NS)
        if reference is not None:
            colour = palette.resolve(reference[0] if len(reference) else None)
            style = theme.style_fill(int(reference.get("idx", "0")))
            if style is None or _local(style) != "solidFill":
                return None
            resolved = palette.resolve(style[0] if len(style) else None, colour and colour[0])
            return resolved[0] if resolved else None
        return None
    return WHITE


def _solid(holder: etree._Element, palette: _Palette, under: RGB | None) -> RGB | None:
    # The colour of a holder's solid fill, blended over what is beneath when see-through
    for child in holder:
        if _local(child) == "solidFill":
            resolved = palette.resolve(child[0] if len(child) else None)
            if resolved is None:
                return None
            colour, alpha = resolved
            if alpha >= 1.0:
                return colour
            return None if under is None else _blend(colour, alpha, under)
    return None


def _shape_fill(node: etree._Element, context: _SlideStyles) -> str | tuple[RGB, float] | None:
    # "none" when the shape is see-through, a colour when solid, None when it cannot be known
    kind = _local(node)
    if kind == "pic" or kind == "graphicFrame":
        return None
    if kind == "cxnSp":
        return "none"
    properties = node.find("p:spPr", NS)
    for child in properties if properties is not None else []:
        name = _local(child)
        if name == "noFill":
            return "none"
        if name == "solidFill":
            return context.palette.resolve(child[0] if len(child) else None)
        if name in FILLS:
            return None
    reference = node.find("p:style/a:fillRef", NS)
    if reference is None or int(reference.get("idx", "0")) == 0:
        return "none"
    style = context.theme.style_fill(int(reference.get("idx", "0")))
    if style is None or _local(style) == "noFill":
        return "none"
    if _local(style) != "solidFill":
        return None
    colour = context.palette.resolve(reference[0] if len(reference) else None)
    return context.palette.resolve(style[0] if len(style) else None, colour and colour[0])


def _beneath(
    box: tuple[float, float, float, float] | None,
    lower: list[_Drawn],
    background: RGB | None,
    context: _SlideStyles,
) -> RGB | None:
    # What shows through behind a see-through shape: the nearest shape drawn under it, or the
    # slide background. A shape that only partly covers the box leaves it mixed, so unknown.
    if box is None:
        return None
    for item in reversed(lower):
        if item.hidden or item.box is None or not _overlaps(item.box, box):
            continue
        fill = _shape_fill(item.node, context)
        if fill == "none":
            continue
        if fill is None or not _contains(item.box, box):
            return None
        colour, alpha = fill  # type: ignore[misc]
        if alpha >= 1.0:
            return colour
        under = _beneath(item.box, lower[: lower.index(item)], background, context)
        return None if under is None else _blend(colour, alpha, under)
    return background


def _overlaps(first: tuple[float, ...], second: tuple[float, ...]) -> bool:
    return (
        first[0] < second[2]
        and second[0] < first[2]
        and first[1] < second[3]
        and second[1] < first[3]
    )


def _contains(outer: tuple[float, ...], inner: tuple[float, ...]) -> bool:
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and outer[2] >= inner[2]
        and outer[3] >= inner[3]
    )


def _shape_runs(
    item: _Drawn,
    lower: list[_Drawn],
    slide_background: RGB | None,
    context: _SlideStyles,
    part: str,
    number: int,
) -> list[RunColour]:
    node = item.node
    runs = text_runs(node)
    if not runs:
        return []
    behind = _beneath(item.box, lower, slide_background, context)
    fill = _shape_fill(node, context)
    if fill is None and _local(node) != "graphicFrame":
        shape_background = None
    elif fill == "none" or _local(node) == "graphicFrame":
        shape_background = behind
    else:
        colour, alpha = fill  # type: ignore[misc]
        shape_background = (
            colour if alpha >= 1.0 else (None if behind is None else _blend(colour, alpha, behind))
        )
    scale = _font_scale(node)
    found: list[RunColour] = []
    for index, run in enumerate(runs):
        text = "".join(node.text or "" for node in run.findall("a:t", NS)).strip()
        if not text:
            continue
        cell = _cell(run)
        near: list[etree._Element] = []
        far: list[etree._Element] = []
        if cell is not None:
            background = _cell_background(cell, node, shape_background, context)
        else:
            background = shape_background
            near, far = context.chain(node, _level(run))
        own = run.find("a:rPr", NS)
        near = ([own] if own is not None else []) + near
        properties = near + far
        colour = _text_colour(near, far, node, run, cell is not None, context)
        if colour is None:
            continue
        highlight = own.find("a:highlight", NS) if own is not None else None
        if highlight is not None and len(highlight):
            resolved = context.palette.resolve(highlight[0])
            background = resolved[0] if resolved else background
        if background is not None:
            text_rgb, alpha = colour
            colour_rgb = text_rgb if alpha >= 1.0 else _blend(text_rgb, alpha, background)
        else:
            colour_rgb = colour[0]
        points = _first_number(properties, "sz")
        found.append(
            RunColour(
                part=part,
                slide=number,
                shape_id=_shape_id(node),
                top_shape_id=item.top_id,
                run=index,
                text=text,
                colour=colour_rgb,
                background=background,
                points=(points / 100 if points else DEFAULT_POINTS) * scale,
                bold=_first_flag(properties, "b"),
                hyperlink=own is not None and own.find("a:hlinkClick", NS) is not None,
                box=item.box,
            )
        )
    return found


def _cell(run: etree._Element) -> etree._Element | None:
    for ancestor in run.iterancestors(f"{{{A_NS}}}tc"):
        return ancestor
    return None


def _cell_background(
    cell: etree._Element,
    frame: etree._Element,
    behind: RGB | None,
    context: _SlideStyles,
) -> RGB | None:
    # A cell's own fill, else what is behind the table; a table style paints cells in ways
    # this does not read, so styled tables count only cells with their own fill
    properties = cell.find("a:tcPr", NS)
    for child in properties if properties is not None else []:
        name = _local(child)
        if name == "noFill":
            return behind
        if name == "solidFill":
            resolved = context.palette.resolve(child[0] if len(child) else None)
            if resolved is None:
                return None
            colour, alpha = resolved
            return (
                colour
                if alpha >= 1.0
                else (None if behind is None else _blend(colour, alpha, behind))
            )
        if name in FILLS:
            return None
    if frame.find(".//a:tblPr/a:tableStyleId", NS) is not None:
        return None
    return behind


def _text_colour(
    near: list[etree._Element],
    far: list[etree._Element],
    shape: etree._Element,
    run: etree._Element,
    in_table: bool,
    context: _SlideStyles,
) -> tuple[RGB, float] | None:
    # The run's colour and opacity, or None when it is not one plain colour or a table style
    # decides it. The shape style's font colour outranks only the deck-wide defaults.
    own = run.find("a:rPr", NS)
    if (
        own is not None
        and own.find("a:hlinkClick", NS) is not None
        and own.find("a:solidFill", NS) is None
    ):
        # Links without their own colour are drawn in the theme's link colour
        colour = context.palette.scheme.get("hlink")
        return (colour, 1.0) if colour else None
    found = _fill_in(near, context)
    if found is not False:
        return found
    if in_table:
        if shape.find(".//a:tblPr/a:tableStyleId", NS) is not None:
            return None
    else:
        reference = shape.find("p:style/a:fontRef", NS)
        if reference is not None and len(reference):
            return context.palette.resolve(reference[0])
    found = _fill_in(far, context)
    if found is not False:
        return found
    colour = context.palette.scheme.get(context.palette.mapping.get("tx1", "dk1"))
    return (colour, 1.0) if colour else None


def _fill_in(
    properties: list[etree._Element], context: _SlideStyles
) -> tuple[RGB, float] | None | bool:
    # The first text fill set along the chain; False when none of them sets one
    for holder in properties:
        for child in holder:
            name = _local(child)
            if name == "solidFill":
                return context.palette.resolve(child[0] if len(child) else None)
            if name in FILLS:
                return None
    return False


def _level(run: etree._Element) -> int:
    paragraph = run.getparent()
    while paragraph is not None and _local(paragraph) != "p":
        paragraph = paragraph.getparent()
    properties = paragraph.find("a:pPr", NS) if paragraph is not None else None
    level = int(properties.get("lvl", "0")) if properties is not None else 0
    return min(9, max(1, level + 1))


def _first_number(properties: list[etree._Element], name: str) -> int | None:
    for holder in properties:
        value = holder.get(name)
        if value is not None and value.lstrip("-").isdigit():
            return int(value)
    return None


def _first_flag(properties: list[etree._Element], name: str) -> bool:
    for holder in properties:
        value = holder.get(name)
        if value is not None:
            return value in {"1", "true"}
    return False


def _font_scale(shape: etree._Element) -> float:
    # Shrink-on-overflow scales every font in the box down
    autofit = shape.find("p:txBody/a:bodyPr/a:normAutofit", NS)
    if autofit is None or autofit.get("fontScale") is None:
        return 1.0
    return int(autofit.get("fontScale", "100000")) / 100000
