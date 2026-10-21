from pathlib import Path

from PIL import Image, ImageStat

from a11y_pipeline.ir.models import Element

# A figure box that has not been revealed yet shows only the faint page background (about 2),
# while a visible figure is far above this level
INK_THRESHOLD = 12.0


def element_visible_pages(
    element: Element,
    page_images: list[Path],
    page_sizes: list[tuple[float, float]],
) -> list[int] | None:
    # Find the pages where an element's box shows ink, for slides that reveal content in steps
    bbox = element.render.bbox
    pages = element.render.pages
    if bbox is None or len(pages) < 2:
        return None
    visible: list[int] = []
    for number in pages:
        if number < 1 or number > len(page_images) or number > len(page_sizes):
            continue
        width_points, height_points = page_sizes[number - 1]
        with Image.open(page_images[number - 1]) as image:
            gray = image.convert("L")
            scale_x = gray.width / width_points
            scale_y = gray.height / height_points
            left = max(0, round(bbox[0] * scale_x))
            right = min(gray.width, round(bbox[2] * scale_x))
            top = max(0, round((height_points - bbox[3]) * scale_y))
            bottom = min(gray.height, round((height_points - bbox[1]) * scale_y))
            if right <= left or bottom <= top:
                continue
            ink = ImageStat.Stat(gray.crop((left, top, right, bottom))).stddev[0]
        if ink >= INK_THRESHOLD:
            visible.append(number)
    return visible or None
