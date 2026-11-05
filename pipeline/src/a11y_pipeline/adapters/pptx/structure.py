import re
from dataclasses import dataclass
from typing import Literal

# Deterministic layout reasoning for a slide: which loose shapes form a diagram, which are
# decoration, and whether the title can be moved to the front of the reading order safely.
# Boxes use slide points with a top-left origin, as PowerPoint stores them.

BoxKind = Literal["title", "body", "label", "drawing", "picture", "group", "table", "other"]

# Shapes closer than this many points are treated as touching, so an arrow that stops just
# short of a box still joins the box's diagram
TOUCH_MARGIN_POINTS = 6.0
# A cluster becomes a diagram when it has this many shapes, at least two of them drawn ones
DIAGRAM_MIN_SHAPES = 3
DIAGRAM_MIN_DRAWINGS = 2


@dataclass(frozen=True)
class Box:
    shape_id: int
    z: int
    kind: BoxKind
    bbox: tuple[float, float, float, float] | None
    text: str = ""


@dataclass(frozen=True)
class SlideLayout:
    # The diagrams found among loose shapes, and the drawn shapes that are only decoration
    diagrams: list[list[Box]]
    decorative: list[Box]


def analyze_layout(boxes: list[Box]) -> SlideLayout:
    # Group touching drawn shapes, grouped shapes and the text labels on them into diagrams.
    # A diagram is often part grouped and part loose; joining them gives one description.
    members = [box for box in boxes if box.kind in {"drawing", "group", "label"} and box.bbox]
    parent = {box.shape_id: box.shape_id for box in members}

    def find(shape_id: int) -> int:
        while parent[shape_id] != shape_id:
            parent[shape_id] = parent[parent[shape_id]]
            shape_id = parent[shape_id]
        return shape_id

    for index, first in enumerate(members):
        for second in members[index + 1 :]:
            if first.kind == "label" and second.kind == "label":
                continue
            if touches(first.bbox, second.bbox, TOUCH_MARGIN_POINTS):
                parent[find(first.shape_id)] = find(second.shape_id)
    clusters: dict[int, list[Box]] = {}
    for box in members:
        clusters.setdefault(find(box.shape_id), []).append(box)
    diagrams: list[list[Box]] = []
    decorative: list[Box] = []
    for cluster in sorted(clusters.values(), key=lambda group: min(box.z for box in group)):
        drawn = [box for box in cluster if box.kind in {"drawing", "group"}]
        if len(cluster) >= DIAGRAM_MIN_SHAPES and len(drawn) >= DIAGRAM_MIN_DRAWINGS:
            diagrams.append(sorted(cluster, key=lambda box: box.z))
        else:
            # A group on its own is described as a figure; only loose drawings are decoration
            decorative.extend(box for box in drawn if box.kind == "drawing")
    return SlideLayout(diagrams=diagrams, decorative=sorted(decorative, key=lambda box: box.z))


def touches(
    first: tuple[float, float, float, float] | None,
    second: tuple[float, float, float, float] | None,
    margin: float = 0.0,
) -> bool:
    # Whether two boxes overlap or come within `margin` points of each other
    if first is None or second is None:
        return False
    return not (
        first[2] + margin < second[0]
        or second[2] + margin < first[0]
        or first[3] + margin < second[1]
        or second[3] + margin < first[1]
    )


def title_can_move_first(boxes: list[Box], title: Box) -> bool:
    # Moving the title to the front changes stacking only against shapes drawn before it.
    # When none of them touches the title, the slide looks exactly the same. Touching rather
    # than overlapping, because a straight line has a box with no area.
    if title.bbox is None:
        return False
    return all(
        box.bbox is not None and not touches(box.bbox, title.bbox)
        for box in boxes
        if box.z < title.z
    )


def table_has_header_row(rows: list[list[str]]) -> bool:
    # A table whose first row reads like column names: two or more rows, mostly filled
    # first row, and not a row of numbers
    if len(rows) < 2 or not rows[0]:
        return False
    first = [cell.strip() for cell in rows[0]]
    filled = [cell for cell in first if cell]
    if 2 * len(filled) < len(first):
        return False
    return not all(NUMBER.fullmatch(cell) for cell in filled)


NUMBER = re.compile(r"[-+]?[\d.,%$]+")
# Titles PowerPoint and its templates fill in by themselves; they name no document
DEFAULT_TITLE = re.compile(r"(powerpoint )?presentation ?\d*", re.IGNORECASE)
# Common English words that are not also common words in other languages
ENGLISH_WORDS = {"the", "and", "of", "to", "is", "for", "that", "with", "are", "this"}


def is_default_title(title: str) -> bool:
    # "PowerPoint Presentation" and the like: a screen reader would announce it as the name
    return bool(DEFAULT_TITLE.fullmatch(" ".join(title.split())))


def guess_language(texts: list[str]) -> str | None:
    # The deck language when the text is plainly English; None when unsure
    words = re.findall(r"[^\W\d_]+", " ".join(texts).casefold())
    if len(words) < 20:
        return None
    ascii_share = sum(word.isascii() for word in words) / len(words)
    common = sum(word in ENGLISH_WORDS for word in words) / len(words)
    distinct = len(ENGLISH_WORDS.intersection(words))
    if ascii_share >= 0.95 and common >= 0.05 and distinct >= 3:
        return "en-US"
    return None
