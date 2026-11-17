from dataclasses import dataclass
from typing import Literal

# Reading order from layout, for any format that places content freely on a page: a slide, a
# PDF page, a Word text box. Boxes are in points with a top-left origin, y growing downward.
# The rule is the one people read by: top to bottom, then left to right, with columns read
# whole. When the layout allows more than one sensible order, nothing is changed.

Bbox = tuple[float, float, float, float]
Decision = Literal["keep", "reorder", "unclear"]

# A cut between two blocks may cross a box by this many points, since a text box is often a
# little taller or wider than the text inside it
CUT_TOLERANCE_POINTS = 4.0


@dataclass(frozen=True)
class Unit:
    # Something read as one piece: a paragraph, a picture, a diagram with its labels
    id: str
    bbox: Bbox
    stored: int


@dataclass(frozen=True)
class OrderPlan:
    # keep: the current order already follows the layout. reorder: one order clearly does.
    # unclear: the layout reads more than one way and the current order is neither.
    decision: Decision
    order: list[str]


def plan_reading_order(units: list[Unit], first: str | None = None) -> OrderPlan:
    # Compare the current order with the order the layout gives, read by rows first and by
    # columns first. `first` is read before everything else whatever its place, as a title is.
    stored = [unit.id for unit in sorted(units, key=lambda unit: unit.stored)]
    rest = [unit for unit in units if unit.id != first]
    lead = [first] if first is not None and len(rest) < len(units) else []
    if lead:
        stored = lead + [unit_id for unit_id in stored if unit_id != first]
    by_rows = lead + _xy_cut(rest, rows_first=True)
    by_columns = lead + _xy_cut(rest, rows_first=False)
    if stored in (by_rows, by_columns):
        return OrderPlan("keep", stored)
    if by_rows == by_columns:
        return OrderPlan("reorder", by_rows)
    return OrderPlan("unclear", stored)


def _xy_cut(units: list[Unit], rows_first: bool) -> list[str]:
    # Split the units at a clear horizontal or vertical gap and read each part in turn. A set
    # that no gap separates, such as a label on a picture, keeps its current order.
    if len(units) <= 1:
        return [unit.id for unit in units]
    for axis in (1, 0) if rows_first else (0, 1):
        parts = _split(units, axis)
        if len(parts) > 1:
            return [unit_id for part in parts for unit_id in _xy_cut(part, rows_first)]
    return [unit.id for unit in sorted(units, key=lambda unit: unit.stored)]


def _split(units: list[Unit], axis: int) -> list[list[Unit]]:
    # Bands of units along one axis (1 for rows, 0 for columns) with a gap between each band
    def extent(unit: Unit) -> tuple[float, float]:
        low, high = unit.bbox[axis], unit.bbox[axis + 2]
        trim = min(CUT_TOLERANCE_POINTS, (high - low) / 4)
        return low + trim, high - trim

    parts: list[list[Unit]] = []
    end = float("-inf")
    for unit in sorted(units, key=lambda unit: (extent(unit)[0], unit.stored)):
        low, high = extent(unit)
        if not parts or low >= end:
            parts.append([unit])
        else:
            parts[-1].append(unit)
        end = max(end, high) if len(parts[-1]) > 1 else high
    return parts


@dataclass(frozen=True)
class Drawn:
    # A shape in drawing order. A shape with no box may be drawn anywhere, so it keeps its
    # place against every other shape.
    id: int
    bbox: Bbox | None


def reorder_keeping_stacking(
    drawn: list[Drawn], wanted: list[int], margin: float
) -> list[int] | None:
    # Where the reading order is the drawing order, as in PowerPoint, a new reading order is a
    # new drawing order. Shapes that touch keep their stacking, so the page looks the same.
    # Returns the full drawing order with `wanted` read in that order, or None when stacking
    # does not allow it. Shapes not in `wanted` stay just before the shape they preceded.
    position = {shape.id: index for index, shape in enumerate(drawn)}
    if len(position) != len(drawn) or any(shape_id not in position for shape_id in wanted):
        return None
    after: dict[int, set[int]] = {shape.id: set() for shape in drawn}
    for index, first in enumerate(drawn):
        for second in drawn[index + 1 :]:
            if _may_overlap(first.bbox, second.bbox, margin):
                after[first.id].add(second.id)
    for earlier, later in zip(wanted, wanted[1:], strict=False):
        after[earlier].add(later)
    rank = {shape_id: index for index, shape_id in enumerate(wanted)}
    following: dict[int, int] = {}
    upcoming = len(wanted)
    for shape in reversed(drawn):
        if shape.id in rank:
            upcoming = rank[shape.id]
        following[shape.id] = upcoming

    def key(shape_id: int) -> tuple[int, int, int]:
        return (following[shape_id], int(shape_id in rank), position[shape_id])

    waiting = {shape_id: 0 for shape_id in after}
    for later_ids in after.values():
        for later in later_ids:
            waiting[later] += 1
    ready = sorted((shape_id for shape_id, count in waiting.items() if count == 0), key=key)
    order: list[int] = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for later in after[current]:
            waiting[later] -= 1
            if waiting[later] == 0:
                ready.append(later)
        ready.sort(key=key)
    if len(order) != len(drawn):
        return None
    return order


def _may_overlap(first: Bbox | None, second: Bbox | None, margin: float) -> bool:
    if first is None or second is None:
        return True
    return not (
        first[2] + margin < second[0]
        or second[2] + margin < first[0]
        or first[3] + margin < second[1]
        or second[3] + margin < first[1]
    )
