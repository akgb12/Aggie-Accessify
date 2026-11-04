import pytest
from PIL import Image, ImageDraw

from a11y_pipeline.evaluation.contrast import contrast_ratio, required_ratio, text_contrast


def test_contrast_follows_the_wcag_formula() -> None:
    assert contrast_ratio((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0)
    assert contrast_ratio((255, 255, 255), (255, 255, 255)) == pytest.approx(1.0)
    # PowerPoint's default light grey on white fails the 4.5:1 minimum
    assert contrast_ratio((191, 191, 191), (255, 255, 255)) < 2.0


def _text_image(text_colour, background, second_background=None) -> Image.Image:
    image = Image.new("RGB", (200, 60), background)
    draw = ImageDraw.Draw(image)
    if second_background is not None:
        draw.rectangle((0, 0, 99, 59), fill=second_background)
    draw.text((110, 20), "Search", fill=text_colour, font_size=24)
    return image


def test_text_contrast_is_measured_against_a_plain_background() -> None:
    grey = text_contrast(_text_image((191, 191, 191), (255, 255, 255)))
    assert grey == pytest.approx(contrast_ratio((191, 191, 191), (255, 255, 255)), rel=0.05)
    black = text_contrast(_text_image((0, 0, 0), (255, 255, 0)))
    assert black is not None and black > 15
    # Text over two large colour areas has no single background, so it is not measured
    assert text_contrast(_text_image((0, 0, 0), (255, 255, 255), (255, 255, 0))) is None
    assert text_contrast(Image.new("RGB", (100, 40), "white")) is None


def test_large_text_needs_less_contrast() -> None:
    assert required_ratio(24) == 3.0
    assert required_ratio(12) == 4.5
    assert required_ratio(None) == 4.5
