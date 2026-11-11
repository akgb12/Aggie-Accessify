import re
from dataclasses import asdict, dataclass
from pathlib import Path

from a11y_pipeline.evaluation.contrast import (
    NORMAL_TEXT_RATIO,
    RGB,
    contrast_ratio,
    hex_colour,
    readable_colour,
)

# Find text colours in LaTeX source that are too faint to read on the page, and the edits that
# make them readable: \color and \textcolor, Beamer's \setbeamercolor foregrounds, and Beamer's
# see-through "covered" items. Each faint colour becomes the nearest shade of itself that
# passes, written out as an explicit colour. Colours inside TikZ pictures also paint shapes, so
# they are left alone.

WHITE: RGB = (255, 255, 255)
BLACK: RGB = (0, 0, 0)
# xcolor's base colours, which every document has
BASE_COLOURS: dict[str, RGB] = {
    "black": BLACK,
    "white": WHITE,
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "yellow": (255, 255, 0),
    "darkgray": (64, 64, 64),
    "gray": (128, 128, 128),
    "lightgray": (191, 191, 191),
    "brown": (191, 128, 64),
    "lime": (191, 255, 0),
    "olive": (128, 128, 0),
    "orange": (255, 128, 0),
    "pink": (255, 191, 191),
    "purple": (191, 0, 64),
    "teal": (0, 128, 128),
    "violet": (128, 0, 128),
}
# Beamer draws covered text this opaque when asked for "transparent" without a number
BEAMER_COVERED_OPACITY = 15
COVERED_MODES = {"transparent", "dynamic", "highly dynamic"}
# Beamer's default structure colour, used for frame titles and item labels
BEAMER_STRUCTURE: RGB = (51, 51, 179)

DEFINITION = re.compile(r"\\(definecolor|colorlet)\s*(?:\[[^\]]*\])?\s*\{")
COLOR = re.compile(r"\\(color|textcolor)(?![A-Za-z@])\s*(<[^>]*>)?\s*")
BEAMER_COLOR = re.compile(r"\\setbeamercolor\*?\s*\{")
COVERED = re.compile(r"\\setbeamercovered\s*\{")
TIKZ = re.compile(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", re.DOTALL)


@dataclass(frozen=True)
class ColourEdit:
    file: str
    start: int
    end: int
    old: str
    new: str
    # Which occurrence of the old text in the file this is, so the edit can be found again in
    # a copy of the file that has had other text added
    occurrence: int
    line: int
    kind: str
    before: str | None = None
    after: str | None = None
    ratio_before: float | None = None
    ratio_after: float | None = None

    def record(self) -> dict[str, object]:
        return asdict(self)


def plan_colour_edits(sources: dict[str, str], main_file: str) -> list[ColourEdit]:
    # Every faint text colour in the project and its fix; the main file is read first, so
    # colours it defines are known to the files it inputs
    order = [main_file] + sorted(name for name in sources if name != main_file)
    masked = {name: _mask_comments(sources[name]) for name in order if name in sources}
    names: dict[str, RGB] = dict(BASE_COLOURS)
    for name in order:
        if name in masked:
            _read_definitions(masked[name], names)
    background = _canvas(masked, names)
    covered_colours = [
        _beamer_fg(masked, names, "normal text", BLACK),
        _beamer_fg(masked, names, "structure", BEAMER_STRUCTURE),
    ]
    edits: list[ColourEdit] = []
    for name in order:
        if name not in masked:
            continue
        text = sources[name]
        hidden = masked[name]
        pictures = [match.span() for match in TIKZ.finditer(hidden)]
        found = _colour_edits(text, hidden, names, background, pictures)
        found += _beamer_edits(text, hidden, names, background)
        found += _covered_edits(text, hidden, covered_colours, background)
        for start, end, new, kind, before, after in sorted(found):
            old = text[start:end]
            edits.append(
                ColourEdit(
                    file=name,
                    start=start,
                    end=end,
                    old=old,
                    new=new,
                    occurrence=_occurrence(text, old, start),
                    line=text.count("\n", 0, start) + 1,
                    kind=kind,
                    before=hex_colour(before) if before else None,
                    after=hex_colour(after) if after else None,
                    ratio_before=round(contrast_ratio(before, background), 2) if before else None,
                    ratio_after=round(contrast_ratio(after, background), 2) if after else None,
                )
            )
    return edits


def apply_colour_edits(text: str, edits: list[ColourEdit]) -> str:
    # Apply a file's edits to a copy of it, finding each by its text and occurrence
    spans: list[tuple[int, int, str]] = []
    for edit in edits:
        start = locate(text, edit)
        if start is not None:
            spans.append((start, start + len(edit.old), edit.new))
    for start, end, new in sorted(spans, reverse=True):
        text = text[:start] + new + text[end:]
    return text


def apply_colour_edits_to(root: Path, edits: list[ColourEdit]) -> None:
    by_file: dict[str, list[ColourEdit]] = {}
    for edit in edits:
        by_file.setdefault(edit.file, []).append(edit)
    for name, file_edits in by_file.items():
        path = root / name
        if path.is_file():
            path.write_text(
                apply_colour_edits(path.read_text(encoding="utf-8"), file_edits),
                encoding="utf-8",
            )


def locate(text: str, edit: ColourEdit) -> int | None:
    # Where an edit's text starts in a file: at its recorded place when the file is the one it
    # was planned on, else at the same occurrence of the same text
    if text[edit.start : edit.end] == edit.old and _occurrence(text, edit.old, edit.start) == (
        edit.occurrence
    ):
        return edit.start
    return _nth(text, edit.old, edit.occurrence)


def edits_from_records(records: list[dict[str, object]]) -> list[ColourEdit]:
    return [ColourEdit(**record) for record in records]  # type: ignore[arg-type]


def evaluate(expression: str, names: dict[str, RGB]) -> RGB | None:
    # An xcolor expression such as gray, black!30 or red!50!blue; None for anything else
    expression = expression.strip()
    if not expression or expression.startswith("-") or "!!" in expression:
        return None
    if ":" in expression:
        return _extended(expression)
    parts = expression.split("!")
    colour = names.get(parts[0].strip())
    if colour is None:
        return None
    rest = parts[1:]
    while rest:
        try:
            share = float(rest[0]) / 100
        except ValueError:
            return None
        other = WHITE
        if len(rest) > 1:
            found = names.get(rest[1].strip())
            if found is None:
                return None
            other = found
        share = min(1.0, max(0.0, share))
        colour = _mix(colour, other, share)
        rest = rest[2:]
    return colour


def model_colour(model: str, spec: str) -> RGB | None:
    # A colour given in one of xcolor's models
    model = model.strip()
    values = [value.strip() for value in spec.split(",")]
    try:
        if model == "HTML" and len(values) == 1 and len(values[0]) == 6:
            return (int(values[0][0:2], 16), int(values[0][2:4], 16), int(values[0][4:6], 16))
        if model == "rgb" and len(values) == 3:
            return tuple(round(float(value) * 255) for value in values)  # type: ignore[return-value]
        if model == "RGB" and len(values) == 3:
            return tuple(int(float(value)) for value in values)  # type: ignore[return-value]
        if model in {"gray", "Gray"} and len(values) == 1:
            scale = 15 if model == "Gray" else 1
            level = round(float(values[0]) / scale * 255)
            return (level, level, level)
        if model == "cmyk" and len(values) == 4:
            cyan, magenta, yellow, black = (float(value) for value in values)
            return tuple(  # type: ignore[return-value]
                round((1 - min(1.0, part + black)) * 255) for part in (cyan, magenta, yellow)
            )
    except ValueError:
        return None
    return None


def _mix(first: RGB, second: RGB, share: float) -> RGB:
    return tuple(  # type: ignore[return-value]
        round(a * share + b * (1 - share)) for a, b in zip(first, second, strict=True)
    )


def _extended(expression: str) -> RGB | None:
    # xcolor's extended form, of which only rgb,255:red,R;green,G;blue,B is read
    match = re.fullmatch(
        r"\s*rgb\s*,\s*255\s*:\s*red\s*,\s*(\d+)\s*;\s*green\s*,\s*(\d+)\s*;\s*blue\s*,\s*(\d+)\s*",
        expression,
    )
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _mask_comments(text: str) -> str:
    # Blank out comments, keeping every offset, so patterns never match inside them
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        index = _comment_start(line)
        if index is None:
            out.append(line)
        else:
            ending = "\n" if line.endswith("\n") else ""
            body = line[: len(line) - len(ending)]
            out.append(body[:index] + " " * (len(body) - index) + ending)
    return "".join(out)


def _comment_start(line: str) -> int | None:
    index = 0
    while index < len(line):
        character = line[index]
        if character == "\\":
            index += 2
            continue
        if character == "%":
            return index
        index += 1
    return None


def _group(text: str, opening: int) -> int | None:
    # The index just past the brace group that opens at text[opening]
    if opening >= len(text) or text[opening] != "{":
        return None
    depth = 0
    index = opening
    while index < len(text):
        character = text[index]
        if character == "\\":
            index += 2
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return None


def _skip_space(text: str, index: int) -> int:
    while index < len(text) and text[index] in " \t\n":
        index += 1
    return index


def _read_definitions(hidden: str, names: dict[str, RGB]) -> None:
    for match in DEFINITION.finditer(hidden):
        name_end = _group(hidden, match.end() - 1)
        if name_end is None:
            continue
        name = hidden[match.end() : name_end - 1].strip()
        first = _skip_space(hidden, name_end)
        if match.group(1) == "colorlet":
            if first < len(hidden) and hidden[first] == "[":
                first = _skip_space(hidden, hidden.find("]", first) + 1)
            expression_end = _group(hidden, first)
            if expression_end is None:
                continue
            colour = evaluate(hidden[first + 1 : expression_end - 1], names)
        else:
            model_end = _group(hidden, first)
            if model_end is None:
                continue
            spec_start = _skip_space(hidden, model_end)
            spec_end = _group(hidden, spec_start)
            if spec_end is None:
                continue
            colour = model_colour(
                hidden[first + 1 : model_end - 1], hidden[spec_start + 1 : spec_end - 1]
            )
        if colour is not None:
            names[name] = colour


def _beamer_settings(hidden: str) -> list[tuple[str, int, int]]:
    # Every \setbeamercolor: the colour's name and where its option list sits
    found: list[tuple[str, int, int]] = []
    for match in BEAMER_COLOR.finditer(hidden):
        name_end = _group(hidden, match.end() - 1)
        if name_end is None:
            continue
        options_start = _skip_space(hidden, name_end)
        options_end = _group(hidden, options_start)
        if options_end is None:
            continue
        found.append(
            (hidden[match.end() : name_end - 1].strip(), options_start + 1, options_end - 1)
        )
    return found


def _options(hidden: str, start: int, end: int) -> dict[str, tuple[int, int]]:
    # Where each key's value sits in a key=value list, braces kept as part of the value
    values: dict[str, tuple[int, int]] = {}
    index = start
    while index < end:
        key_match = re.compile(r"\s*([A-Za-z ]+?)\s*=\s*").match(hidden, index, end)
        if key_match is None:
            comma = hidden.find(",", index, end)
            index = end if comma == -1 else comma + 1
            continue
        value_start = key_match.end()
        if value_start < end and hidden[value_start] == "{":
            value_end = _group(hidden, value_start) or end
        else:
            comma = hidden.find(",", value_start, end)
            value_end = end if comma == -1 else comma
        values[key_match.group(1).strip()] = (value_start, value_end)
        comma = hidden.find(",", value_end, end)
        index = end if comma == -1 else comma + 1
    return values


def _value(hidden: str, span: tuple[int, int]) -> str:
    value = hidden[span[0] : span[1]].strip()
    if value.startswith("{") and value.endswith("}"):
        value = value[1:-1]
    return value


def _canvas(masked: dict[str, str], names: dict[str, RGB]) -> RGB:
    # The page colour, which Beamer calls the background canvas
    for hidden in masked.values():
        for name, start, end in _beamer_settings(hidden):
            if name == "background canvas":
                span = _options(hidden, start, end).get("bg")
                colour = evaluate(_value(hidden, span), names) if span else None
                if colour is not None:
                    return colour
    return WHITE


def _beamer_fg(masked: dict[str, str], names: dict[str, RGB], wanted: str, default: RGB) -> RGB:
    # The foreground the document gives one of Beamer's colours, else Beamer's own
    for hidden in masked.values():
        for name, start, end in _beamer_settings(hidden):
            if name == wanted:
                span = _options(hidden, start, end).get("fg")
                colour = evaluate(_value(hidden, span), names) if span else None
                if colour is not None:
                    return colour
    return default


Found = tuple[int, int, str, str, RGB | None, RGB | None]


def _fixed(colour: RGB, background: RGB) -> RGB | None:
    if contrast_ratio(colour, background) >= NORMAL_TEXT_RATIO:
        return None
    return readable_colour(colour, background, NORMAL_TEXT_RATIO)


def _colour_edits(
    text: str,
    hidden: str,
    names: dict[str, RGB],
    background: RGB,
    pictures: list[tuple[int, int]],
) -> list[Found]:
    # \color and \textcolor: the optional model and the colour argument are replaced by an
    # explicit colour, keeping any overlay specification
    found: list[Found] = []
    for match in COLOR.finditer(hidden):
        if any(start <= match.start() < end for start, end in pictures):
            continue
        start = match.end()
        model = None
        index = start
        if index < len(hidden) and hidden[index] == "[":
            close = hidden.find("]", index)
            if close == -1:
                continue
            model = hidden[index + 1 : close]
            index = _skip_space(hidden, close + 1)
        end = _group(hidden, index)
        if end is None:
            continue
        argument = hidden[index + 1 : end - 1]
        colour = model_colour(model, argument) if model else evaluate(argument, names)
        if colour is None:
            continue
        fixed = _fixed(colour, background)
        if fixed is not None:
            found.append(
                (start, end, "[HTML]{" + hex_colour(fixed) + "}", "text_colour", colour, fixed)
            )
    return found


def _beamer_edits(text: str, hidden: str, names: dict[str, RGB], background: RGB) -> list[Found]:
    # A Beamer colour's foreground, judged against its own background when it has one
    found: list[Found] = []
    for name, start, end in _beamer_settings(hidden):
        if name == "background canvas":
            continue
        options = _options(hidden, start, end)
        span = options.get("fg")
        if span is None:
            continue
        colour = evaluate(_value(hidden, span), names)
        if colour is None:
            continue
        own = options.get("bg")
        behind = (evaluate(_value(hidden, own), names) if own else None) or background
        fixed = _fixed(colour, behind)
        if fixed is not None:
            red, green, blue = fixed
            value = "{rgb,255:red," + f"{red};green,{green};blue,{blue}" + "}"
            found.append((span[0], span[1], value, "beamer_colour", colour, fixed))
    return found


def _covered_edits(text: str, hidden: str, colours: list[RGB], background: RGB) -> list[Found]:
    # Beamer shows items still to come see-through; they must stay readable while dimmed, in
    # the text colour and in the structure colour of their labels
    found: list[Found] = []
    for match in COVERED.finditer(hidden):
        end = _group(hidden, match.end() - 1)
        if end is None:
            continue
        options = hidden[match.end() : end - 1]
        mode = options.split("=")[0].strip()
        if mode not in COVERED_MODES:
            continue
        opacity = BEAMER_COVERED_OPACITY
        number = re.fullmatch(r"\s*transparent\s*=\s*(\d+)\s*", options)
        if number:
            opacity = int(number.group(1))
        each = [_covered_opacity(colour, background) for colour in colours]
        if None in each:
            continue
        needed = max(value for value in each if value is not None)
        if mode == "transparent" and opacity >= needed:
            continue
        before = _mix(colours[0], background, opacity / 100)
        after = _mix(colours[0], background, needed / 100)
        found.append(
            (match.end(), end - 1, f"transparent={needed}", "covered_items", before, after)
        )
    return found


def _covered_opacity(colour: RGB, background: RGB) -> int | None:
    # The least opacity, in whole percent, at which covered text still passes
    for opacity in range(1, 101):
        mixed = _mix(colour, background, opacity / 100)
        if contrast_ratio(mixed, background) >= NORMAL_TEXT_RATIO + 0.1:
            return opacity
    return None


def _occurrence(text: str, old: str, start: int) -> int:
    count = 0
    index = text.find(old)
    while index != -1 and index < start:
        count += 1
        index = text.find(old, index + 1)
    return count


def _nth(text: str, old: str, occurrence: int) -> int | None:
    index = text.find(old)
    for _ in range(occurrence):
        if index == -1:
            return None
        index = text.find(old, index + 1)
    return None if index == -1 else index
