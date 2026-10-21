from pathlib import Path

from PIL import Image, ImageDraw

from a11y_pipeline.ir.ids import fingerprint_source
from a11y_pipeline.ir.models import Accessibility, Element, RenderRef, SourceRef
from a11y_pipeline.render.visibility import element_visible_pages


def _figure(pages: list[int], bbox: tuple[float, float, float, float] | None) -> Element:
    raw = "figure"
    return Element(
        id="slide_01/figure_01",
        semantic_type="figure",
        subtype="diagram",
        parent_id="slide_01",
        content={},
        fingerprint=fingerprint_source(raw),
        source=SourceRef(
            file="main.tex",
            line_start=1,
            line_end=1,
            char_start=0,
            char_end=len(raw),
            native_type="tikzpicture",
            raw=raw,
        ),
        accessibility=Accessibility(role="Figure"),
        render=RenderRef(pages=pages, bbox=bbox),
    )


def _page(tmp_path: Path, name: str, drawn: bool) -> Path:
    # A 400x300 px page for a 200x150 pt slide, optionally with ink inside the figure box
    image = Image.new("RGB", (400, 300), (253, 253, 253))
    if drawn:
        draw = ImageDraw.Draw(image)
        for x in range(120, 280, 12):
            draw.rectangle((x, 120, x + 6, 200), fill=(20, 20, 20))
    path = tmp_path / name
    image.save(path)
    return path


def test_figure_is_visible_only_on_the_pages_where_it_has_ink(tmp_path: Path) -> None:
    images = [_page(tmp_path, "a.png", False), _page(tmp_path, "b.png", True)]
    element = _figure([1, 2], (50.0, 40.0, 150.0, 90.0))

    assert element_visible_pages(element, images, [(200.0, 150.0)] * 2) == [2]


def test_elements_on_one_page_or_without_a_box_are_left_alone(tmp_path: Path) -> None:
    images = [_page(tmp_path, "a.png", True)]
    sizes = [(200.0, 150.0)]
    assert element_visible_pages(_figure([1], (50.0, 40.0, 150.0, 90.0)), images, sizes) is None
    assert element_visible_pages(_figure([1, 2], None), images * 2, sizes * 2) is None


def test_no_visible_page_falls_back_to_showing_every_page(tmp_path: Path) -> None:
    images = [_page(tmp_path, "a.png", False), _page(tmp_path, "b.png", False)]
    element = _figure([1, 2], (50.0, 40.0, 150.0, 90.0))
    assert element_visible_pages(element, images, [(200.0, 150.0)] * 2) is None
