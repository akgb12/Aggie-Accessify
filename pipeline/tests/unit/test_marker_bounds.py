from a11y_pipeline.adapters.tex_beamer.markers import _before_trailing_display, _paragraph_bounds


def _end(raw: str) -> int:
    # Where the closing marker goes for an element covering the whole source
    return _before_trailing_display(raw, 0, len(raw))


def test_plain_text_keeps_its_end() -> None:
    raw = "Just some text."
    assert _end(raw) == len(raw)


def test_marker_closes_before_a_trailing_pause_and_keeps_it_outside() -> None:
    raw = "For an unknown point, we guess its class.\n\\pause"
    assert raw[: _end(raw)] == "For an unknown point, we guess its class."


def test_marker_closes_before_a_trailing_display_equation() -> None:
    raw = "We have three classes:\n\\[\n  s=p.\n\\]"
    assert raw[_end(raw) :].strip() == "\\]"
    assert raw[: _end(raw)].endswith("s=p.")


def test_marker_closes_before_a_display_followed_by_a_pause() -> None:
    raw = "Feature order:\n\\[\n  [a,b]\n\\]\n\n\\pause"
    assert raw[_end(raw) :].lstrip().startswith("\\]")
    assert raw[: _end(raw)].endswith("[a,b]")


def test_marker_closes_inside_a_trailing_centered_block_without_a_dangling_space() -> None:
    raw = "ML objective:\n\\begin{center}\n\\textbf{Generalize.}\n\\end{center}"
    cut = _end(raw)
    assert raw[cut:] == "\n\\end{center}"
    assert not raw[:cut].endswith((" ", "\n"))


def test_equations_in_the_middle_do_not_move_the_marker() -> None:
    raw = "Before \\[ x \\] and then more text."
    assert _end(raw) == len(raw)


def test_a_leading_vspace_stays_outside_the_paragraph_marker() -> None:
    raw = "\\vspace{0.3em}\n\\small\nDescription: it grows."
    start, end = _paragraph_bounds(raw)
    assert raw[:start] == "\\vspace{0.3em}\n"
    assert end == len(raw)


def test_paragraph_without_leading_spacing_is_unchanged() -> None:
    raw = "Plain paragraph."
    assert _paragraph_bounds(raw) == (0, len(raw))
