from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.util import Inches

from a11y_pipeline.cli import _good_fake_response
from a11y_pipeline.config import Settings
from a11y_pipeline.models.cache import CachedModelClient, DiskModelCache
from a11y_pipeline.models.fake import FakeModelClient
from a11y_pipeline.runs.folder import run_to_folder

TITLE_ONLY = 5
BLANK = 6


def _deck(root: Path) -> Path:
    # A titled slide with a picture and an untitled slide: figure and title requests
    root.mkdir()
    Image.new("RGB", (60, 40), "red").save(root / "a.png")
    presentation = Presentation()
    first = presentation.slides.add_slide(presentation.slide_layouts[TITLE_ONLY])
    first.shapes.title.text = "Gradient descent"
    first.shapes.add_picture(str(root / "a.png"), Inches(1), Inches(2))
    presentation.slides.add_slide(presentation.slide_layouts[BLANK])
    presentation.save(str(root / "deck.pptx"))
    return root


def _run(deck: Path, cache: Path, output: Path, reuse: bool = True) -> FakeModelClient:
    model = FakeModelClient(default_generator=_good_fake_response)
    client = CachedModelClient(model, DiskModelCache(cache), reuse=reuse)
    run_to_folder(deck, client, Settings(model_provider="fake"), effort="low", output_root=output)
    return model


def test_running_an_unchanged_deck_again_reuses_every_answer(tmp_path: Path) -> None:
    deck = _deck(tmp_path / "project")
    cache = tmp_path / "cache"
    first = _run(deck, cache, tmp_path / "runs")
    assert first.requests
    # The same deck asks the same questions, so nothing reaches the model the second time
    assert _run(deck, cache, tmp_path / "runs").requests == []
    # A fresh run asks the model again for everything
    assert len(_run(deck, cache, tmp_path / "runs", reuse=False).requests) == len(first.requests)
