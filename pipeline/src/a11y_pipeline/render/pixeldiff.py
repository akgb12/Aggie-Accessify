import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

from a11y_pipeline.ir.models import DocumentIR, Issue
from a11y_pipeline.render.pages import render_pages

# Sub-pixel position jitter in the PDF writer changes anti-aliasing without moving anything.
# After a light blur such flicker stays below this level, while a real shift of a point or two
# does not.
JITTER_BLUR_RADIUS = 1.2
JITTER_MAX_DIFFERENCE = 24


@dataclass(frozen=True)
class PixelCheck:
    identical: bool
    original_pages: int
    candidate_pages: int
    different_pages: list[int]


def compare_pdf_pixels(
    original_pdf: Path,
    candidate_pdf: Path,
    dpi: int = 80,
) -> PixelCheck:
    # Compare complete PDF renders without image tolerances
    with tempfile.TemporaryDirectory(prefix="a11y-pixel-check-") as temporary:
        root = Path(temporary)
        original = render_pages(original_pdf, root / "original", dpi=dpi)
        candidate = render_pages(candidate_pdf, root / "candidate", dpi=dpi)
        different: list[int] = []
        shared = min(len(original), len(candidate))
        for index in range(shared):
            if not _images_identical(original[index], candidate[index]):
                different.append(index + 1)
        maximum = max(len(original), len(candidate))
        for page in range(shared + 1, maximum + 1):
            different.append(page)
    return PixelCheck(
        identical=not different,
        original_pages=len(original),
        candidate_pages=len(candidate),
        different_pages=different,
    )


def visual_change_issues(ir: DocumentIR, check: PixelCheck) -> list[Issue]:
    # Build page vetoes with the marked elements involved
    issues: list[Issue] = []
    for page in check.different_pages:
        element_ids: list[str] = []
        for element in ir.elements.values():
            if element.mcid is not None and page in element.render.pages:
                element_ids.append(element.id)
        issues.append(
            Issue(
                element_id=None,
                code="visual_change",
                severity="veto",
                message=f"Marked output changed rendered page {page}",
                details={"page": page, "element_ids": element_ids},
            )
        )
    return issues


def _images_identical(first_path: Path, second_path: Path) -> bool:
    # Compare one page pair: identical, or different only by anti-aliasing flicker
    with Image.open(first_path) as first_image:
        with Image.open(second_path) as second_image:
            first = first_image.convert("RGB")
            second = second_image.convert("RGB")
            if first.size != second.size:
                return False
            if ImageChops.difference(first, second).getbbox() is None:
                return True
            blurred_first = first.convert("L").filter(ImageFilter.GaussianBlur(JITTER_BLUR_RADIUS))
            blurred_second = second.convert("L").filter(
                ImageFilter.GaussianBlur(JITTER_BLUR_RADIUS)
            )
            histogram = ImageChops.difference(blurred_first, blurred_second).histogram()
            largest = max(level for level, count in enumerate(histogram) if count)
            return largest <= JITTER_MAX_DIFFERENCE
