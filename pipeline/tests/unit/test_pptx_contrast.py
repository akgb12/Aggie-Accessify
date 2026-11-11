from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_THEME_COLOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt

from a11y_pipeline.adapters import get_adapter
from a11y_pipeline.adapters.pptx.colors import deck_run_colours
from a11y_pipeline.adapters.pptx.contrast import contrast_findings
from a11y_pipeline.adapters.pptx.writer import (
    recolour_edits,
    verify_updated_deck,
    write_updated_project,
)
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.evaluation.contrast import contrast_ratio, readable_colour


def _deck(root: Path) -> Path:
    # One slide in the style of a lecture agenda: a covered topic dimmed in the theme's light
    # grey above the current one in black, in the same box, and white text on a dark shape
    root.mkdir(parents=True, exist_ok=True)
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = "Today"
    box = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(6), Inches(2))
    covered = box.text_frame.paragraphs[0].add_run()
    covered.text = "A* search"
    covered.font.size = Pt(28)
    covered.font.color.theme_color = MSO_THEME_COLOR.BACKGROUND_1
    covered.font.color.brightness = -0.25
    current = box.text_frame.add_paragraph().add_run()
    current.text = "Graph search vs. tree search"
    current.font.size = Pt(28)
    current.font.color.rgb = RGBColor(0, 0, 0)
    label = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(7), Inches(2), Inches(2), Inches(1))
    label.fill.solid()
    label.fill.fore_color.rgb = RGBColor(0x20, 0x20, 0x20)
    label.text_frame.text = "Agent"
    deck = root / "deck.pptx"
    presentation.save(str(deck))
    return deck


def test_a_faint_colour_is_darkened_only_as_far_as_it_must_be() -> None:
    grey, white = (191, 191, 191), (255, 255, 255)
    fixed = readable_colour(grey, white, 4.5)
    assert fixed is not None
    assert 4.5 < contrast_ratio(fixed, white) < 4.8
    # Still a grey, so a dimmed item still looks dimmed next to black text
    assert fixed[0] == fixed[1] == fixed[2] and fixed[0] > 100
    # Orange stays orange
    orange = readable_colour((237, 125, 49), white, 4.5)
    assert orange is not None and orange[0] > orange[1] > orange[2]
    # Light text on a dark background gets lighter, and readable colours are kept
    assert readable_colour((90, 90, 90), (32, 32, 32), 4.5) > (90, 90, 90)  # type: ignore[operator]
    assert readable_colour((0, 0, 0), white, 4.5) == (0, 0, 0)
    # Nothing on a mid grey background reaches 21:1
    assert readable_colour((0, 0, 0), (128, 128, 128), 21.0) is None


def test_run_colours_follow_the_theme_and_the_shape_style(tmp_path: Path) -> None:
    runs = {run.text: run for run in deck_run_colours(_deck(tmp_path / "in"))}
    covered = runs["A* search"]
    # Background 1 darkened by a quarter is PowerPoint's light grey
    assert covered.colour == (191, 191, 191)
    assert covered.background == (255, 255, 255)
    assert covered.fails
    # A grey line sharing a box with black text is judged on its own
    assert not runs["Graph search vs. tree search"].fails
    # The shape style draws text in the theme's light colour on the shape's fill
    agent = runs["Agent"]
    assert agent.colour == (255, 255, 255)
    assert agent.background == (0x20, 0x20, 0x20)
    assert not agent.fails


def test_the_update_recolours_faint_text_and_nothing_else(tmp_path: Path) -> None:
    deck = _deck(tmp_path / "in")
    bundle = Bundle.from_path(deck.parent)
    adapter = get_adapter("pptx")
    ir = adapter.build_ir(bundle, adapter.preflight(bundle))
    findings = contrast_findings(deck, None, tmp_path / "work")
    assert [finding.run.text for finding in findings] == ["A* search"]
    container = ir.containers[0]
    container.attrs["contrast_fixes"] = [finding.record() for finding in findings]
    result = write_updated_project(bundle, ir, tmp_path / "out", tmp_path / "changes.diff")
    updated = result.project_root / "deck.pptx"
    runs = {run.text: run for run in deck_run_colours(updated)}
    assert not runs["A* search"].fails
    assert runs["Graph search vs. tree search"].colour == (0, 0, 0)
    assert any(op.operation == "fix_text_contrast" for op in result.operations)
    assert "text colour #BFBFBF -> #" in (tmp_path / "changes.diff").read_text(encoding="utf-8")
    # The check that nothing visible changed allows exactly the planned colours
    assert verify_updated_deck(bundle, updated, recolour_edits(ir)).identical
    assert not verify_updated_deck(bundle, updated).identical
