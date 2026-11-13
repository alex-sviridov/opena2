"""Shared geometry of the dialog frame (`lm.256`, ui-layout 11.4) for the shell's own windows (tips window, between-missions list): where the ornamental border
and the corner skulls are, so controls and text are placed inside the free area instead of on the art.

A `Frame(x, y, w, h)` op is the body `w - 8` x `h - 8` plus the 8 px drop shadow.  MEASURED from the frame sprites (`tests/test_engine_shell_dialog.py`
recomputes them): the border band is `BORDER_X` px deep on the left / right edges and `BORDER_Y` px on the top / bottom edges (the edge sprites 2 / 7 and 4 / 5
differ from the fill texture only that deep); the skull ornaments cover a `CORNER` px square (their bounding box, measured on the corner sprites) at each body corner.  The exe's own dialogs (options, menu, story)
keep their CONFIRMED rects; these helpers serve the windows whose rect is ours or whose exe rect runs into the art (DECISION, chargen.md 1.5)."""

SHADOW = 8
BORDER_X, BORDER_Y = 14, 16
CORNER = 40                                     # measured: the bounding box of the skull on the corner sprites
GAP = 4                                         # free pixels between a control and the border band


def body(w, h):
    """The frame body size of a `Frame(.., w, h)` (the shadow excluded)."""
    return w - SHADOW, h - SHADOW


def inner(w, h):
    """`(x, y, w, h)` of the area inside the border band, relative to the frame's top-left."""
    bw, bh = body(w, h)
    return BORDER_X, BORDER_Y, bw - 2 * BORDER_X, bh - 2 * BORDER_Y


def bottom_row_y(h, control_h):
    """Top of a row of controls `control_h` high that sits `GAP` above the bottom border band (frame-relative)."""
    return h - SHADOW - BORDER_Y - GAP - control_h


def centre_x(w):
    """Frame-relative x of the body's horizontal centre (a centred title sits between the corner skulls)."""
    return (w - SHADOW) // 2


def clamp_inside(rect, w, h):
    """`rect` (x, y, rw, rh), frame-relative, moved the least into `inner(w, h)` (it is shrunk only when larger than the area)."""
    x, y, rw, rh = rect
    ix, iy, iw, ih = inner(w, h)
    rw, rh = min(rw, iw), min(rh, ih)
    return max(ix, min(x, ix + iw - rw)), max(iy, min(y, iy + ih - rh)), rw, rh


def touches_corner(rect, w, h):
    """True when `rect` (frame-relative) overlaps one of the four corner skull squares."""
    x, y, rw, rh = rect
    bw, bh = body(w, h)
    for cx, cy in ((0, 0), (bw - CORNER, 0), (0, bh - CORNER), (bw - CORNER, bh - CORNER)):
        if x < cx + CORNER and x + rw > cx and y < cy + CORNER and y + rh > cy:
            return True
    return False


def between_corners(w):
    """`(x0, x1)` frame-relative: the span of the bottom (or top) row between the two corner skulls, a `GAP` clear of each."""
    return CORNER + GAP, w - SHADOW - CORNER - GAP
