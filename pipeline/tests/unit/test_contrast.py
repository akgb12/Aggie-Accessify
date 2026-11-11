import pytest
from PIL import Image, ImageDraw

from a11y_pipeline.evaluation.contrast import (
    colours_around_word,
    contrast_ratio,
    required_ratio,
    text_contrast,
)


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
    # Bold text is large from 14 points
    assert required_ratio(14, bold=True) == 3.0
    assert required_ratio(14) == 4.5


def test_one_word_is_measured_even_when_its_glyphs_fill_the_box() -> None:
    image = Image.new("RGB", (90, 30), (255, 255, 255))
    ImageDraw.Draw(image).text((2, 0), "search", fill=(191, 191, 191), font_size=28)
    measured = colours_around_word(image, (191, 191, 191))
    assert measured is not None
    text, background = measured
    assert background == (255, 255, 255)
    assert contrast_ratio(text, (191, 191, 191)) < 1.3
    # A word over a picture with other colours is not measured
    noisy = image.copy()
    ImageDraw.Draw(noisy).rectangle((0, 0, 44, 29), fill=(30, 120, 200))
    assert colours_around_word(noisy, (191, 191, 191)) is None
