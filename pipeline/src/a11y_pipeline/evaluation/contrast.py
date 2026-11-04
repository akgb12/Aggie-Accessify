from collections import Counter

from PIL import Image

# WCAG 2.x minimum contrast between text and its background (success criterion 1.4.3)
NORMAL_TEXT_RATIO = 4.5
LARGE_TEXT_RATIO = 3.0
# Text at least this size in points counts as large
LARGE_TEXT_POINTS = 18.0
# Below this colour distance from the background nothing in the box is treated as text
MIN_TEXT_DISTANCE = 20
# Share of the text's pixels, furthest from the background colour, taken as the text colour.
# Anti-aliased edges blend into the background, so only the core of each glyph is used.
GLYPH_CORE_SHARE = 0.3
# A second colour covering this share of the box means the background is not one colour
SECOND_BACKGROUND_SHARE = 0.12
# Fewer differing pixels than this is noise, not text
MIN_INK_PIXELS = 12
# Larger text boxes are sampled down to about this many pixels
MAX_PIXELS = 40_000


def relative_luminance(colour: tuple[int, int, int]) -> float:
    # WCAG relative luminance: undo the sRGB curve, then weight red, green and blue by how
    # bright each looks to the eye
    channels = []
    for value in colour:
        scaled = value / 255
        channels.append(scaled / 12.92 if scaled <= 0.04045 else ((scaled + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    # From 1 (identical colours) to 21 (black on white)
    lighter, darker = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def text_contrast(image: Image.Image) -> float | None:
    # Estimate the contrast of the text drawn in an image of one text box: the most common
    # colour is the background, and the pixels furthest from it are the text
    rgb = image.convert("RGB")
    if rgb.width * rgb.height > MAX_PIXELS:
        # Nearest-neighbour keeps real pixel colours, unlike smoothing filters
        factor = (MAX_PIXELS / (rgb.width * rgb.height)) ** 0.5
        size = (max(1, int(rgb.width * factor)), max(1, int(rgb.height * factor)))
        rgb = rgb.resize(size, Image.Resampling.NEAREST)
    pixels = list(rgb.get_flattened_data())
    if len(pixels) < 50:
        return None
    counts = Counter(_coarse(pixel) for pixel in pixels).most_common(2)
    background = counts[0][0]
    if len(counts) > 1 and counts[1][1] >= SECOND_BACKGROUND_SHARE * len(pixels):
        # Two large colour areas (text over a picture or a filled shape) leave the background
        # ambiguous, so the box is not measured rather than guessed
        return None
    background_pixels = [pixel for pixel in pixels if _coarse(pixel) == background]
    background_colour = _median(background_pixels)
    ink = sorted(
        (
            (distance, pixel)
            for pixel in pixels
            if (distance := _distance(pixel, background_colour)) >= MIN_TEXT_DISTANCE
        ),
        reverse=True,
    )
    if len(ink) < MIN_INK_PIXELS:
        return None
    count = max(MIN_INK_PIXELS, int(len(ink) * GLYPH_CORE_SHARE))
    text_colour = _median([pixel for _, pixel in ink[:count]])
    return contrast_ratio(text_colour, background_colour)


def required_ratio(font_points: float | None) -> float:
    if font_points is not None and font_points >= LARGE_TEXT_POINTS:
        return LARGE_TEXT_RATIO
    return NORMAL_TEXT_RATIO


def _coarse(pixel: tuple[int, int, int]) -> tuple[int, int, int]:
    return (pixel[0] // 16, pixel[1] // 16, pixel[2] // 16)


def _distance(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    return sum((a - b) ** 2 for a, b in zip(first, second, strict=True)) ** 0.5


def _median(pixels: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    middle = len(pixels) // 2
    return (
        sorted(pixel[0] for pixel in pixels)[middle],
        sorted(pixel[1] for pixel in pixels)[middle],
        sorted(pixel[2] for pixel in pixels)[middle],
    )
