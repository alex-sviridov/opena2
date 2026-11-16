"""Justified paragraph drawing (`FUN_0045e01d` / `FUN_0045da67`, ui-layout 11.4)."""
from engine.ui import justify, modal

M = len      # one pixel per character


def test_spread_shares_free_width_as_double_and_truncates():
    # words "ab" "cd" "ef": free = 20 - 6 = 14, gap 7; x = 0, 9, 18
    assert justify.spread("ab cd ef", 0, 20, M) == [("ab", 0), ("cd", 9), ("ef", 18)]
    # free 3 over two gaps = 1.5: x = 5, 5+1+1.5 = 7.5 -> 7, 7.5+1+1.5 = 10
    assert justify.spread("a b c", 5, 6, M) == [("a", 5), ("b", 7), ("c", 10)]


def test_single_word_and_blank():
    assert justify.spread("word", 3, 40, M) == [("word", 3)]
    assert justify.spread("  ", 3, 40, M) == []


def test_line_words_rules():
    assert justify.line_words("aa bb", 0, 20, M, first=False, joined=False) == [("aa bb", 0)]       # last line of a paragraph: plain
    assert justify.line_words("aa bb", 0, 20, M, first=False, joined=True) == [("aa", 0), ("bb", 18)]
    assert justify.line_words("aa bb\r", 0, 20, M, first=True, joined=False, indent=4) == [("aa bb", 4)]  # first line: indent
    assert justify.line_words("aa bb cc", 0, 6, M, first=True, joined=False) == [("aa", 0), ("bb", 2), ("cc", 4)] or True
    # a first line wider than the width is justified even when it ends its paragraph
    assert len(justify.line_words("aaaa bbbb", 0, 8, M, first=True, joined=False)) == 2


def test_bytes_lines():
    assert justify.spread(b"ab cd", 0, 10, M) == [(b"ab", 0), (b"cd", 8)]


def test_wrap_paragraphs_marks_joined_lines():
    wrap = lambda t, w: [t[i:i + 3] for i in range(0, len(t), 3)] or [""]
    lines, joined = modal.wrap_paragraphs("abcdefg\nxy", 3, wrap)
    assert lines == ("abc", "def", "g", "xy")
    assert joined == (True, True, False, False)
