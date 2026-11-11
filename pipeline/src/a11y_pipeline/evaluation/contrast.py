import colorsys
from collections import Counter

from PIL import Image

RGB = tuple[int, int, int]

# WCAG 2.x minimum contrast between text and its background (success criterion 1.4.3)
NORMAL_TEXT_RATIO = 4.5
LARGE_TEXT_RATIO = 3.0
# Text at least this size in points counts as large, or this size when bold
LARGE_TEXT_POINTS = 18.0
LARGE_BOLD_TEXT_POINTS = 14.0
# A fixed colour clears the minimum by this much, so checkers that round differently agree
FIX_MARGIN = 0.1
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
# Measuring one word: pixels this far from the text's colour can be background; the
# background must cover this share of the word's box; and pixels this far from every blend of
# text and background are something else, of which only this share is allowed
WORD_TEXT_DISTANCE = 40
WORD_MIN_BACKGROUND_SHARE = 0.3
WORD_BLEND_DISTANCE = 40
WORD_MAX_STRAY_SHARE = 0.1
# Measured text this far from every blend of its expected colour and background is another
# colour, so the expected colour was misread
DRAWN_TOLERANCE = 48


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
    # Estimate the contrast of the text drawn in an image of one text box
    colours = text_colours(image)
    return None if colours is None else contrast_ratio(*colours)


def text_colours(image: Image.Image) -> tuple[RGB, RGB] | None:
    # The text colour and the background colour drawn in an image of some text: the most
    # common colour is the background, and the pixels furthest from it are the text
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
    return text_colour, background_colour


def colours_around_word(image: Image.Image, expected_text: RGB) -> tuple[RGB, RGB] | None:
    # The text and background colours in a tight image of one word whose colour is roughly
    # known. Glyphs fill much of such an image, so the background is the most common colour
    # well away from the text's, and the word is unreadable to measure when other colours
    # that are neither, nor a blend of the two at the glyph edges, cover much of it.
    rgb = image.convert("RGB")
    pixels = list(rgb.get_flattened_data())
    if len(pixels) < 20:
        return None
    far = [pixel for pixel in pixels if _distance(pixel, expected_text) >= WORD_TEXT_DISTANCE]
    if len(far) < WORD_MIN_BACKGROUND_SHARE * len(pixels):
        return None
    bucket = Counter(_coarse(pixel) for pixel in far).most_common(1)[0][0]
    background = _median([pixel for pixel in far if _coarse(pixel) == bucket])
    stray = sum(
        1
        for pixel in pixels
        if _distance_to_segment(pixel, expected_text, background) > WORD_BLEND_DISTANCE
    )
    if stray > WORD_MAX_STRAY_SHARE * len(pixels):
        return None
    ink = sorted(
        (
            (distance, pixel)
            for pixel in pixels
            if (distance := _distance(pixel, background)) >= MIN_TEXT_DISTANCE
        ),
        reverse=True,
    )
    if len(ink) < 3:
        return None
    count = max(3, int(len(ink) * GLYPH_CORE_SHARE))
    return _median([pixel for _, pixel in ink[:count]]), background


def drawn_as(measured: RGB, expected: RGB, background: RGB) -> bool:
    # Whether text measured on a page is the expected colour; small text's thin strokes blend
    # into the background, so any blend of the two counts
    return _distance_to_segment(measured, expected, background) <= DRAWN_TOLERANCE


def _distance_to_segment(pixel: RGB, start: RGB, end: RGB) -> float:
    # How far a colour is from every blend of two colours
    direction = [b - a for a, b in zip(start, end, strict=True)]
    length = sum(value * value for value in direction)
    if length == 0:
        return _distance(pixel, start)
    share = sum((p - a) * d for p, a, d in zip(pixel, start, direction, strict=True)) / length
    share = min(1.0, max(0.0, share))
    closest = tuple(a + share * d for a, d in zip(start, direction, strict=True))
    return sum((p - c) ** 2 for p, c in zip(pixel, closest, strict=True)) ** 0.5


def required_ratio(font_points: float | None, bold: bool = False) -> float:
    if font_points is None:
        return NORMAL_TEXT_RATIO
    if font_points >= LARGE_TEXT_POINTS or (bold and font_points >= LARGE_BOLD_TEXT_POINTS):
        return LARGE_TEXT_RATIO
    return NORMAL_TEXT_RATIO


def readable_colour(text: RGB, background: RGB, required: float) -> RGB | None:
    # The closest colour to the author's that is readable on the background: the same hue and
    # saturation, only darker (or lighter on a dark background) by as little as passes. Text
    # that was lighter than its background stays lighter when that can pass, so a dimmed item
    # still looks dimmed next to the text around it.
    target = required + FIX_MARGIN
    if contrast_ratio(text, background) >= target:
        return text
    darker_first = relative_luminance(text) <= relative_luminance(background)
    for darker in (darker_first, not darker_first):
        found = _shift_lightness(text, background, target, darker)
        if found is not None:
            return found
    return None


def hex_colour(colour: RGB) -> str:
    return "".join(f"{value:02X}" for value in colour)


def _shift_lightness(text: RGB, background: RGB, target: float, darker: bool) -> RGB | None:
    hue, lightness, saturation = colorsys.rgb_to_hls(*(value / 255 for value in text))
    end = 0.0 if darker else 1.0
    if contrast_ratio(_from_hls(hue, end, saturation), background) < target:
        return None
    # Search between the author's lightness and black (or white) for the nearest that passes
    near, far = lightness, end
    for _ in range(40):
        middle = (near + far) / 2
        if contrast_ratio(_from_hls(hue, middle, saturation), background) >= target:
            far = middle
        else:
            near = middle
    # Rounding to whole channel values can land just short, so step on until it passes
    step = -0.002 if darker else 0.002
    colour = _from_hls(hue, far, saturation)
    while contrast_ratio(colour, background) < target:
        far = min(1.0, max(0.0, far + step))
        colour = _from_hls(hue, far, saturation)
    return colour


def _from_hls(hue: float, lightness: float, saturation: float) -> RGB:
    red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
    return (round(red * 255), round(green * 255), round(blue * 255))


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
