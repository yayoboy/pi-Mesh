from gui.widgets._vkb_layout import (
    PAGES,
    ROWS_ALPHA,
    ROWS_SYM,
    ROWS_SYM2,
    page_for,
    shift_char,
)


def test_alpha_layout_is_three_rows():
    assert len(ROWS_ALPHA) == 3


def test_alpha_layout_qwerty_top_row():
    assert ROWS_ALPHA[0] == list("qwertyuiop")


def test_alpha_layout_lowercase_only():
    for row in ROWS_ALPHA:
        for ch in row:
            assert ch.islower(), f"{ch!r} should be lowercase"


def test_sym_first_row_is_digits_zero_last():
    assert ROWS_SYM[0] == list("1234567890")


def test_sym_layout_three_rows():
    assert len(ROWS_SYM) == 3


def test_sym2_layout_three_rows_last_empty():
    assert len(ROWS_SYM2) == 3
    assert ROWS_SYM2[2] == []


def test_sym2_includes_brackets_and_currency():
    flat = [c for row in ROWS_SYM2 for c in row]
    for c in ("{", "}", "[", "]", "<", ">", "€"):
        assert c in flat


def test_pages_constant_has_three_pages():
    assert len(PAGES) == 3
    assert PAGES[0] is ROWS_ALPHA
    assert PAGES[1] is ROWS_SYM
    assert PAGES[2] is ROWS_SYM2


def test_page_for_wraps_modulo():
    assert page_for(0) is ROWS_ALPHA
    assert page_for(3) is ROWS_ALPHA
    assert page_for(7) is ROWS_SYM
    assert page_for(-1) is ROWS_SYM2


def test_shift_char_upcases():
    assert shift_char("a") == "A"
    assert shift_char("z") == "Z"
    # Pass-through for non-letters
    assert shift_char("1") == "1"
    assert shift_char("!") == "!"


def test_no_overlap_between_pages():
    """Each character should appear in at most one layout."""
    a = {c for row in ROWS_ALPHA for c in row}
    s = {c for row in ROWS_SYM for c in row}
    s2 = {c for row in ROWS_SYM2 for c in row}
    # Period appears in ROWS_SYM bottom row already, so ALPHA rows should
    # not duplicate it. Check pairwise disjoint.
    assert not (a & s), f"alpha vs sym overlap: {a & s}"
    assert not (a & s2), f"alpha vs sym2 overlap: {a & s2}"
    assert not (s & s2), f"sym vs sym2 overlap: {s & s2}"
