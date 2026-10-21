from a11y_pipeline.adapters.tex_beamer.writer import _escape_alt, _update_includegraphics


def test_alt_text_never_contains_a_line_break() -> None:
    # A blank line inside an option ends the paragraph in TeX and changes the page
    escaped = _escape_alt("Short text.\n\nLonger detail\nthat wraps.")
    assert "\n" not in escaped
    assert escaped == "Short text. Longer detail that wraps."


def test_includegraphics_with_an_extended_description_stays_on_one_option_line() -> None:
    # The merged option keeps no paragraph break, whether or not options already existed
    description = _escape_alt("Alt text.\n\nExtended detail.")
    plain = _update_includegraphics(r"\includegraphics{a.pdf}", description)
    with_options = _update_includegraphics(
        "\\includegraphics[\n    width=0.9\\linewidth,\n]{a.pdf}", description
    )
    for result in (plain, with_options):
        assert "\n\n" not in result
        assert "alt={Alt text. Extended detail.}" in result


def test_special_characters_other_than_braces_percent_and_hash_are_left_alone() -> None:
    # graphicx stores the alt value unexpanded, so these cannot break the option
    text = r"A & B, x_1^2 ~ $a$ \foo  =  c"
    assert _escape_alt(text) == r"A & B, x_1^2 ~ $a$ \foo = c"
