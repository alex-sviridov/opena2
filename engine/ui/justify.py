"""Justified paragraph drawing of the text widgets (`FUN_0045e01d` line classifier, `FUN_0045da67` word spreader; docs/engine/ui-layout.md 11.4, CONFIRMED).

A wrapped line is *joined* when it is not the last line of its paragraph (the exe: the wrapper ends a paragraph's last line with a CR).  A joined line is spread over the
widget's width; the first line of a paragraph is indented by the font-side field `+0x80` (0 in every install window, INFERRED) and is also spread when its measure is wider than
the width.  Spreading: the words are cut at single spaces, the free width `width - sum(word widths)` is shared over the `n - 1` gaps as a *double*, each word is drawn at
the truncated running x.  One word is drawn at x.  Pure: `measure(str) -> int`."""


def spread(line, x, width, measure):
    """`FUN_0045da67`: [(word, x)] of one spread line starting at `x` with `width` pixels."""
    words = line.split()
    if not words:
        return []
    total = sum(measure(w) for w in words)
    gap = (width - total) / (len(words) - 1) if len(words) > 1 else float(width - total)
    out, fx = [], float(x)
    for w in words:
        out.append((w, int(fx)))
        fx += measure(w) + gap
    return out


def line_words(line, x, width, measure, first, joined, indent=0):
    """`FUN_0045e01d` for one line: [(text, x)] to draw.  `first` = first line of its paragraph, `joined` = not the last line of it."""
    line = line.rstrip(b"\r" if isinstance(line, bytes) else "\r")           # str or font bytes
    if first:
        x, width = x + indent, width - indent
        if measure(line.strip()) > width + indent:
            joined = True
    if not joined:
        return [(line, x)]
    return spread(line, x, width, measure)


def paragraph_flags(lines_per_paragraph):
    """[(first, joined)] for the lines of paragraphs given as lists of lines."""
    out = []
    for para in lines_per_paragraph:
        n = len(para)
        out += [(i == 0, i < n - 1) for i in range(n)]
    return out
