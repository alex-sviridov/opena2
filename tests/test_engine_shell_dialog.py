"""The shared dialog-frame geometry (engine/shell/dialog.py): the constants are measured from the frame sprites, the helpers keep controls off the border band and the
corner skulls, and the shell's own framed windows (tips window, between-missions list) stay inside the free area."""

import os

import numpy as np
import pytest

pytest.importorskip("pygame")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from allods2.common import as_fs  # noqa: E402
from allods2.graphics import SpriteFile  # noqa: E402
from engine.shell import chargen as cg  # noqa: E402
from engine.shell import dialog as D  # noqa: E402
from engine.shell import locations as L  # noqa: E402
from helpers import GFS, needs_graphics  # noqa: E402
from shell_scenarios import Recorder, click, make_shell  # noqa: E402


def test_helpers_place_a_row_inside_the_free_area():
    w, h = 312, 200
    ix, iy, iw, ih = D.inner(w, h)
    assert (ix, iy, iw, ih) == (14, 16, 304 - 28, 192 - 32)
    y = D.bottom_row_y(h, 18)
    assert y + 18 + D.GAP + D.BORDER_Y == h - D.SHADOW                       # the gap above the bottom band
    assert D.clamp_inside((0, 0, 50, 20), w, h) == (14, 16, 50, 20) and D.clamp_inside((300, 190, 50, 20), w, h)[0] + 50 == ix + iw
    assert D.clamp_inside((20, 20, 999, 999), w, h)[2:] == (iw, ih)
    assert D.touches_corner((0, 0, 10, 10), w, h) and D.touches_corner((296, 180, 8, 8), w, h) and not D.touches_corner((60, 8, 100, 20), w, h)
    assert D.centre_x(w) == 152


@needs_graphics
def test_constants_are_the_measured_border_depths():
    """Rows / columns of the edge sprites that differ from the fill texture (the border band): top 16, bottom 16, left 14, right 13 (rounded up to 14)."""
    sf = SpriteFile.load("graphics/interface/lm.256", as_fs(GFS))
    fill = np.array(sf.to_rgba(0))[..., :3].astype(float).reshape(-1, 3)
    mu, sd = fill.mean(0), fill.std(0).sum()

    def band(i, axis):
        r = np.array(sf.to_rgba(i)).astype(float)
        d = (np.abs(r[..., :3] - mu).sum(2) > 3 * sd) | (r[..., 3] == 0)
        return d.mean(axis=axis) > 0.5
    assert int(band(2, 1).sum()) <= D.BORDER_Y and int(band(7, 1).sum()) <= D.BORDER_Y
    assert int(band(4, 0).sum()) <= D.BORDER_X and int(band(5, 0).sum()) <= D.BORDER_X


@needs_graphics
def test_tips_window_controls_are_inside_the_border_and_clear_of_the_skulls():
    sh, _ = make_shell(GFS)
    sh.start("menu")
    sh.go("newgame")
    sh.go("chargen", difficulty=2, hero=0, hero_code=0, name="Aldor")
    tw, (x, y, w, h) = sh.current.tips_win, cg.HINT
    for r in (tw.close, tw.check, tw.text_box):
        rel = (r[0] - x, r[1] - y, r[2], r[3])
        ix, iy, iw, ih = D.inner(w, h)
        assert ix <= rel[0] and iy <= rel[1] and rel[0] + rel[2] <= ix + iw and rel[1] + rel[3] <= iy + ih, r
    for r in (tw.close, tw.check):
        assert not D.touches_corner((r[0] - x, r[1] - y, r[2], r[3]), w, h)
    ct, cb = tw.close, tw.text_box
    assert ct[1] >= cb[1] + cb[3]                                           # the control row starts below the text box


@needs_graphics
def test_locations_dialog_keeps_every_control_inside_the_free_area_and_centres_its_headings():
    from engine.shell import Key
    sh, _ = make_shell(GFS)
    sh.start("menu")
    sh.go("newgame")
    sh.go("chargen", difficulty=2, hero=0, hero_code=0, name="Aldor")
    sh.handle(Key("return"))
    loc = sh.current
    fx, fy = loc.frame_at()
    for bx, by, bw, bh, label, m in loc.buttons():
        rel = (bx - fx, by - fy, bw, bh)
        assert D.clamp_inside(rel, L.W, L.H) == rel and not D.touches_corner(rel, L.W, L.H), label
    heads = [op for op in loc.scene().ops if type(op).__name__ == "Text"]
    assert heads and all(op.flags == 2 and op.x == fx + D.centre_x(L.W) for op in heads)         # headings and party lines are centred in the body


@needs_graphics
@pytest.mark.parametrize("size", [(640, 480), (800, 600)])
def test_in_game_dialogs_keep_their_exe_rects_off_the_border_and_the_skulls(size):
    """The exe's CONFIRMED rects of the in-game windows (menu, End Quest, pause, story, mission complete / failed) already sit inside the free area."""
    from engine.ui import Layout, modal as M
    from engine.ui.orders import MainText
    fs = as_fs(GFS)
    main, dl = MainText.load(fs), MainText.load(fs, "main/text/dialogs.txt")
    mt, dt = main.line, dl.line
    lay = Layout.for_size(*size)
    for d in (M.menu_dialog(lay, dt), M.endquest_dialog(lay, dt, True), M.pause_dialog(lay, mt), M.story_dialog(lay, mt, "", "0"),
              M.complete_dialog(lay, mt, dt), M.failed_dialog(lay, mt, dt, "reason text")):
        f = d.frame
        rects = [("btn " + b.label, b.rect) for b in d.buttons] + ([("text", d.text_rect)] if d.text_rect else [])
        for name, r in rects:
            rel = (r.x - f.x, r.y - f.y, r.w, r.h)
            assert D.clamp_inside(rel, f.w, f.h) == rel and not D.touches_corner(rel, f.w, f.h), (d.kind, name, rel)


@needs_graphics
def test_generator_preview_and_stat_digits_are_centred():
    """The hero name is centred on the preview panel's interior, labels left / values right-aligned inside it, the attribute digits centred in their 20 px boxes."""
    sh, _ = make_shell(GFS)
    sh.start("menu")
    sh.go("newgame")
    sh.go("chargen", difficulty=2, hero=0, hero_code=0, name="Aldor")
    ox, oy = sh.current.origin
    texts = [op for op in sh.current.scene().ops if type(op).__name__ == "Text"]
    name = next(t for t in texts if t.text == "Aldor")
    assert name.flags == 2 and name.x == ox + cg.PREVIEW_CX
    vals = [t for t in texts if t.x == ox + cg.PREVIEW_R]
    assert vals and all(t.flags == 1 for t in vals) and all(t.x < ox + 156 for t in texts if t.y > oy + 250 and t.x < ox + 160)
    digits = [t for t in texts if t.x == ox + cg.VALUE_X + cg.BOX // 2]
    assert len(digits) == 4 and all(t.flags == 2 for t in digits)
