"""The J1 widget table (docs/engine/ui-layout.md 11.6): every widget of the minimal UI as data.

A widget is an origin (`P` info panel, `B` command bar, `V` viewport, or a dialog name: the top-left of that dialog's screen-centred rect), an offset rect
relative to it, and the drawing recipe (graphic, font, colour table).  Readers (`info.py`, `bar.py`, `modal.py`) and the backend
both look rects up here; nothing in this module touches pygame."""

from dataclasses import dataclass

from .layout import Rect

# Dialogs (ui-layout 11.4, CONFIRMED `FUN_004dc4fc`): the constructor args give only the SIZE (r-l, b-t); the rect is snapped to 0x60 / 0x40 steps and centred on the screen.
# Fixed-size dialogs only; the text windows (pause, failed) and the mission-complete window get their height from `text_window` / `complete_window`.
DIALOG_RAW = {"menu": (340, 340), "endquest": (340, 240), "story": (580, 240)}


def snap_dialog(w, h):
    """`FUN_004dc4fc`: w' = ((w - 8) // 0x60) * 0x60 + 8, h' = ((h - 0x68) >> 6) * 0x40 + 0x68 (the frame body is w' - 8 x h' - 8, the last 8 px hold the drop shadow)."""
    return ((w - 8) // 0x60) * 0x60 + 8, (((h - 0x68) + (((h - 0x68) >> 31) & 0x3F)) >> 6) * 0x40 + 0x68


DIALOG_SIZE = {k: snap_dialog(*v) for k, v in DIALOG_RAW.items()}

FONT1_H = 15                    # CONFIRMED: `FUN_00402a90` = font vtable slot 9 (height of glyph 0) = 15 for font1 (`DAT_0061fac0`)
FONT1_PITCH = FONT1_H + 2       # CONFIRMED `FUN_004d4dc9` (line pitch `+0x60` = font height + 2 when the argument is 0)
TEXT_TOP, CAPTION_SHIFT = 0x38, 0xC


@dataclass(frozen=True)
class TextWindow:
    """Geometry of a text window / the complete window, all rects (dx, dy, w, h) relative to the frame; `w`, `h` the frame size (shadow included).
    `place_h` is the screen-centring height: the failed window is centred with `h - 0x40` (its +0x40 is added after the placement, `FUN_0044d237`)."""
    w: int
    h: int
    text: tuple
    caption: tuple
    buttons: tuple
    place_h: int = 0
    scroll: bool = False


def _span(w, y0, a, b, den):
    return (w * a // den, y0, w * b // den - w * a // den, 0x18)


def text_window_buttons(w, h, n):
    """Button rects (dx, dy, w, h) of a message window with `n` buttons (CONFIRMED `0x443238`, rects `0x443663..0x4437d5`): y from h - 0x3c to h - 0x24; one = (w/2 - 0x30, w/2 + 0x30),
    two = (w/7, 3w/7) and (4w/7, 6w/7), three = (3w/20, 7w/20), (8w/20, 12w/20), (13w/20, 17w/20) (integer division)."""
    y0 = h - 0x3C
    if n == 1:
        return [(w // 2 - 0x30, y0, 0x60, 0x18)]
    spans = {2: [(1, 3, 7), (4, 6, 7)], 3: [(3, 7, 20), (8, 12, 20), (13, 17, 20)]}[n]
    return [_span(w, y0, a, b, d) for a, b, d in spans]


def text_window(raw, nlines, caption=False, buttons=1):
    """Frame, text, caption and button rects of a message window (CONFIRMED `FUN_00443238`, `0x44286`, `FUN_004d51db`).  `raw` = the (w, h) of the constructor
    rect, `nlines` = a function `text rect width -> number of wrapped lines` (font1; `FUN_0045d479`: paragraphs at CR LF, greedy word wrap) or a number, `caption` =
    a caption string exists (its line sits at `0x30` and the text starts `0xc` lower), `buttons` = the stock button case (1 or 2; 0 = none, the failed window adds its own).
    The first snap gives the text rect `(0x28, top)-(w' - 0x28, h' - 0x58)`; the text widget then shrinks its bottom to `top + 17 * lines` (when `15 * lines` fits the rect height `h' - 0x58 - 0x38`;
    else it keeps the rect and gets a scroll bar), the height becomes `0x90 + bottom` and is snapped again: `h = ((0x90 + bottom - 0x68) / 0x40) * 0x40 + 0x68`."""
    w, h1 = snap_dialog(*raw)
    top = TEXT_TOP + (CAPTION_SHIFT if caption else 0)
    n = nlines(w - 0x50) if callable(nlines) else nlines
    shift = top - TEXT_TOP                                        # the caption's OffsetRect moves the whole text rect
    scroll = FONT1_H * n > h1 - 0x58 - TEXT_TOP
    bottom = h1 - 0x58 + shift if scroll else top + FONT1_PITCH * n
    _, h = snap_dialog(w, 0x90 + bottom)
    rects = tuple(text_window_buttons(w, h, buttons)) if buttons else ()
    cap = (0x28, top - 0x14, w - 0x50, 0x10) if caption else None
    return TextWindow(w, h, (0x28, top, w - 0x50, bottom - top), cap, rects, h, scroll)


def failed_window(raw, nlines, caption=True):
    """The mission-failed window (`FUN_0044d1e2` -> subclass `0x5ccf78`, build slot `FUN_0044d237`, CONFIRMED): the text window with no stock button, then `bottom += 0x40` (no
    new snap, no re-centring), and two buttons stacked at x `w/8 .. 7w/8`, y `h - 0x60 .. h - 0x48` ("Exit to Main Menu") and `h - 0x48 .. h - 0x30` ("Load Game"), `h` the new height."""
    tw = text_window(raw, nlines, caption, 0)
    w, h = tw.w, tw.h + 0x40
    lo, hi = w // 8, w * 7 // 8
    return TextWindow(w, h, tw.text, tw.caption, ((lo, h - 0x60, hi - lo, 0x18), (lo, h - 0x48, hi - lo, 0x18)), tw.h, tw.scroll)


def complete_window():
    """The mission-complete window (`FUN_0044da0f` over `FUN_00450300`, class `0x5cd098`, children `FUN_0044da55`, CONFIRMED): the constructor rect `(0x80, 0xc8)-(0x200, 0x17c)` is 384x180,
    snapped to 296x168; label `main 0x8c` (font1, normal table, draw flags 2) in `(0x28, 0x20)-(0xe8, 0x50)`; two buttons from the stack rule with next top = `h - 0x60` = 84 (the rect
    argument's bottom) and height 24: `Victory!` (V, message `0x41d`) at y 84..108 and `Continue` (`dialogs 0x9a`, C, message `0x446`) at 108..132, x `0x28 .. w' - 0x30`."""
    w, h = snap_dialog(0x200 - 0x80, 0x17C - 0xC8)
    x, bw = 0x28, w - 0x30 - 0x28
    return TextWindow(w, h, (0x28, 0x20, 0xC0, 0x30), None, ((x, 84, bw, 24), (x, 108, bw, 24)), h)


def centred(layout, w, h):
    """Top-left of a w x h dialog centred on the screen (`FUN_004dc4fc`: `(W - w) >> 1`, `(H - h) >> 1`)."""
    return (layout.size[0] - w) >> 1, (layout.size[1] - h) >> 1


# font numbers and colour-table names of `engine.backend_pygame.text`
F1, F2 = 1, 2
GOLD, SAGE, ORANGE, NORMAL, HI = "label", "value", "header", "normal", "highlight"


@dataclass(frozen=True)
class Widget:
    id: str
    origin: str                 # "P" | "B" | "V" | a DIALOG_SIZE name | "S" (screen)
    rect: tuple                 # (dx, dy, w, h) relative to the origin
    graphic: str = ""           # file(s) under graphics/interface or a rule name
    font: int = 0
    table: str = ""
    text: str = ""              # the text source (main.txt / dialogs.txt id) or rule
    reads: str = ""


def _w(*a, **k):
    return Widget(*a, **k)


# ids and rects: 11.1 (info panel buttons, source rect = draw rect), 11.2 (command cells), 11.4-11.5 (dialogs)
WIDGETS = {w.id: w for w in (
    _w("info.back", "P", (0, 0, 160, 242), "HumanBackR|TextBackR", reads="panel mode"),
    _w("info.portrait", "P", (0, 2, 160, 240), "infowindow|doll", reads="selected unit"),
    _w("info.btn_book", "P", (0, 4, 28, 37), "BookClosed", reads="flags"),
    _w("info.btn_pack", "P", (1, 0xC9, 28, 31), "BackPackCl", reads="flags"),
    _w("info.btn_mode", "P", (0x80, 4, 28, 32), "HumanMode|TextMode", reads="panel mode"),
    _w("info.btn_menu", "P", (0x7E, 0xCE, 32, 32), "diskette", reads="flags"),
    _w("bar.back", "B", (0, 0, 160, 80), "CommandBarR|HeadsR", reads="selection state"),
    _w("msg.line", "V", (8, 8, 0, 0), "", F1, HI, "11.5", reads="MessageLine"),
    _w("menu.frame", "menu", (0, 0) + DIALOG_SIZE["menu"], "lm.256"),
    _w("endquest.frame", "endquest", (0, 0) + DIALOG_SIZE["endquest"], "lm.256"),
    _w("story.frame", "story", (0, 0) + DIALOG_SIZE["story"], "lm.256", F1, HI, "event text"),
    _w("story.text", "story", (48, 36, 380, 136), "", F1, HI),                  # (0x30, 0x24)-(0x1ac, 0xac): CONFIRMED `FUN_0041d15e`
    _w("story.text_npc", "story", (128, 36, 300, 136), "", F1, HI),             # (0x80, 0x24)-(0x1ac, 0xac) when the section contains `npc`
    _w("story.picture", "story", (30, 54, 88, 114), "npc picture", reads="page npc"),   # FUN_004db920(0xc, 0x1e, 0x36, 0x76, 0xa8): (l, t, r, b), surface 88x108
    _w("story.ok", "story", (200, 172, 80, 26), "bevel", F1, NORMAL, "main 0x4d"),
)}
# `bar.cell[i]` and `menu.btn[k]` are families: see `cell_rect` and `button_rect`

# info panel buttons: (draw rect, hit rect) relative to P (11.1 table)
INFO_BUTTONS = {
    "book": ((0, 4), (0, 0, 28, 36)),
    "pack": ((1, 0xC9), (0, 202, 28, 40)),
    "mode": ((0x80, 4), (0x80, 0, 32, 36)),
    "menu": ((0x7E, 0xCE), (0x7E, 0xCE, 32, 32)),
}

CELL_ORIGIN, CELL_PITCH, CELL_SIZE, CELLS = (8, 7), 34, 34, 8       # 11.2: cell i = (8 + (i & 3) * 34, 7 + (i >> 2) * 34)
BUTTON_X0, BUTTON_X1, BUTTON_PITCH, BUTTON_TOP, BUTTON_H = 0x28, 0x30, 0x1E, 0x28, 0x1E    # 11.4 CONFIRMED (`FUN_00450300`, `0x4400d7`, `0x43ffc5`): x 0x28 .. width-0x30, pitch 0x1e, first at top + 0x28


def origin(layout, name):
    """Screen position (x, y) of an origin letter."""
    if name == "P":
        r = layout.info_panel.rect
    elif name == "B":
        r = layout.bar_panel.rect
    elif name == "V":
        r = layout.viewport
    elif name in DIALOG_SIZE:
        w, h = DIALOG_SIZE[name]
        return (layout.size[0] - w) >> 1, (layout.size[1] - h) >> 1
    else:
        return 0, 0
    return r.x, r.y


def widget_rect(layout, wid):
    """Screen `Rect` of the widget `wid`."""
    w = WIDGETS[wid]
    ox, oy = origin(layout, w.origin)
    dx, dy, ww, hh = w.rect
    return Rect(ox + dx, oy + dy, ww, hh)


def cell_rect(layout, i):
    """Screen rect of command-bar cell `i` (0..7)."""
    ox, oy = origin(layout, "B")
    return Rect(ox + CELL_ORIGIN[0] + (i & 3) * CELL_PITCH, oy + CELL_ORIGIN[1] + (i >> 2) * CELL_PITCH, CELL_SIZE, CELL_SIZE)


def info_button_rect(layout, name):
    """Screen hit rect of an info-panel button."""
    ox, oy = origin(layout, "P")
    _, (x, y, w, h) = INFO_BUTTONS[name]
    return Rect(ox + x, oy + y, w, h)


def button_rect(frame, k):
    """Rect of text button `k` of a dialog whose frame rect is `frame` (11.4: x from 0x28 to width-0x30, pitch 0x1e, first at top + 0x28)."""
    return Rect(frame.x + BUTTON_X0, frame.y + BUTTON_TOP + k * BUTTON_PITCH, frame.w - BUTTON_X0 - BUTTON_X1, BUTTON_H)
