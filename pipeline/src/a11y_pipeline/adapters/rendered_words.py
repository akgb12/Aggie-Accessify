from pathlib import Path
from typing import Any

from a11y_pipeline.evaluation.hidden_labels import (
    HiddenLabelError,
    WordBox,
    extract_word_boxes,
    words_inside_figure,
)
from a11y_pipeline.render.crop import page_box_points

# Words this close outside a figure's edge still show in its crop
WORD_MARGIN_POINTS = 6.0


class DrawnWords:
    # The words the renderer drew on each page, read once per page with their positions
    def __init__(self, rendered: Path | None) -> None:
        self.rendered = rendered
        self.pages: dict[int, tuple[list[WordBox], tuple[float, float, float, float]]] = {}

    def page(self, number: int) -> tuple[list[WordBox], tuple[float, float, float, float]]:
        # Every word on one page, and the page's box
        if self.rendered is None:
            return [], (0.0, 0.0, 0.0, 0.0)
        if number not in self.pages:
            try:
                self.pages[number] = (
                    extract_word_boxes(self.rendered, number),
                    page_box_points(self.rendered, number),
                )
            except (HiddenLabelError, OSError, ValueError):
                self.pages[number] = ([], (0.0, 0.0, 0.0, 0.0))
        return self.pages[number]

    def inside(self, element: Any) -> list[str]:
        # Words drawn inside a figure's area, a little beyond its edges as the crop shows
        bbox = element.render.bbox
        if self.rendered is None or bbox is None or not element.render.pages:
            return []
        words, page_box = self.page(element.render.pages[0])
        margin = WORD_MARGIN_POINTS
        grown = (bbox[0] - margin, bbox[1] - margin, bbox[2] + margin, bbox[3] + margin)
        return [word.text for word in words_inside_figure(words, grown, page_box)]
