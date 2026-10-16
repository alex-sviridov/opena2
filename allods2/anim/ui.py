"""Cursors and other animated UI sprites.

Spec: docs/formats/animation.md §4.8 / §4.9.

Cursors (CONFIRMED, table FUN_00480f17, class FUN_00480d20, mouse manager
0x60e6c0): each cursor is (file, hot x, hot y, period ms).  The mouse
manager (FUN_00428c10 / 0x4291f4) reads timeGetTime(); when more than
`period` ms passed since the last step it advances one frame and wraps at
the frame count; the cursor is drawn at (mouse x - hot x, mouse y - hot y)
with the sprite's own table (.16a alpha, or opaque .256).  Period
2000000000 = a still cursor.  Time is in milliseconds here.

Other UI sequences (chargen dice cube, PreCreate "blind", world-map flags,
inn unit pictures): files, loaders and frame counts are known; their frame
timing is not traced, so previews play them at a nominal 100 ms per frame
and the sets say `timed = False`.
"""

import os

from .base import Action, AnimationSet, FrameRef, blit, find_file

STILL = 2000000000
# FUN_00480f17: (path under graphics/cursors, hot x, hot y, period ms, global)
CURSORS = (
    ("default/sprites.16a", 4, 4, STILL, 0x630e8c), ("move/sprites.16a", 2, 3, 100, 0x630e90),
    ("swarm/sprites.16a", 2, 3, 100, 0x630e94), ("attack/sprites.16a", 3, 3, 100, 0x630e98),
    ("defend/sprites.16a", 16, 16, 100, 0x630e9c), ("select/sprites.16a", 3, 3, 100, 0x630ea0),
    ("patrol/sprites.16a", 8, 25, 100, 0x630ea4), ("cast/sprites.16a", 16, 16, 100, 0x630ea8),
    ("pickup/sprites.16a", 16, 12, 66, 0x630eac), ("arrow0/sprites.16a", 16, 6, STILL, 0x630eb0),
    ("arrow4/sprites.16a", 16, 28, STILL, 0x630eb4), ("arrow6/sprites.16a", 5, 16, STILL, 0x630eb8),
    ("arrow2/sprites.16a", 26, 16, STILL, 0x630ebc), ("arrow7/sprites.16a", 8, 9, STILL, 0x630ec0),
    ("arrow5/sprites.16a", 8, 24, STILL, 0x630ec4), ("arrow1/sprites.16a", 23, 9, STILL, 0x630ec8),
    ("arrow3/sprites.16a", 23, 24, STILL, 0x630ecc), ("sdefault/sprites.16a", 1, 1, STILL, 0x630ed0),
    ("smove.256", 0, 0, STILL, 0x630ed4), ("sattack.256", 0, 0, STILL, 0x630ed8),
    ("sdefend.256", 0, 0, STILL, 0x630edc), ("spatrol.256", 0, 0, STILL, 0x630ee0),
    ("scast.256", 0, 0, STILL, 0x630ee4), ("cantput/sprites.16a", 38, 36, STILL, 0x630ee8),
    ("town/sprites.16a", 16, 16, STILL, 0x630eec), ("dice/sprites.16a", 16, 16, 100, 0x630ef0),
    ("wait/sprites.16a", 16, 16, 100, 0x630ef4), ("backpack/sprites.16a", 16, 16, 100, 0x630ef8),
)
CURSORS_DIR = "graphics/cursors"

# UI .16a sequences: (name, path under data/, loader)
UI_SEQUENCES = (
    ("chrgen_cube", "graphics/interface/chrgen/cube/sprites.16a", "FUN_004313db"),
    ("chrgen_blind", "graphics/interface/chrgen/PreCreate/Blind/sprites.16a", "FUN_004364c3"),
    ("map_missionflag", "graphics/Global.Map/MissionFlag/sprites.16a", "FUN_00474320"),
    ("map_yourflag", "graphics/Global.Map/YourFlag/sprites.16a", "FUN_00474320"),
)
UI_NOMINAL_MS = 100


def cursor_name(path):
    return path.split("/")[0].replace(".256", "")


def cursor_frame(ms, period, count):
    """Frame after `ms` ms with the manager polled every millisecond: it
    steps when strictly more than `period` ms passed (FUN_00428c10), so one
    frame per period + 1 ms."""
    if period >= STILL or count <= 1:
        return 0
    return (ms // (period + 1)) % count


class CursorSet(AnimationSet):
    """One cursor; action "cursor", clock in ms; hotspot = (hot x, hot y)."""
    kind = "cursors"
    clock = "ms"

    def __init__(self, path, hx, hy, period, sprites=None, paths=None):
        super().__init__(cursor_name(path), sprites, paths)
        self.hot, self.period = (hx, hy), period
        self.alpha = path.endswith(".16a")
        n = self.count() or 1
        still = period >= STILL or n <= 1
        self.actions = {"cursor": Action("cursor", [0] if still else list(range(n)), clock="ms")}
        self.preview_step_ms = 100 if still else period + 1

    def frame_at(self, action, facing, ms, **kw):
        i = cursor_frame(ms, self.period, self.count())
        return FrameRef("main", i, False, self.hot, action, i)

    def preview_clip(self, action, facing):
        step = self.preview_step_ms
        return [(self.frame_at(action, facing, k * step), (0, 0))
                for k in range(self.actions[action].ticks)]

    def draw(self, canvas, ref, x, y):
        sf = self.sprites()
        if sf is None or not 0 <= ref.index < len(sf):
            return
        blit(canvas, sf, ref.index, x - self.hot[0], y - self.hot[1],
             sf.palette, "alpha" if self.alpha else "opaque")


class UiSequenceSet(AnimationSet):
    """A UI .16a sequence played frame by frame; timing not traced."""
    kind = "ui"
    clock = "ms"
    timed = False
    preview_step_ms = UI_NOMINAL_MS

    def __init__(self, name, loader, sprites=None, paths=None):
        super().__init__(name, sprites, paths)
        self.loader = loader
        self.actions = {"frames": Action("frames", list(range(max(self.count(), 1))), clock="ms")}

    def frame_at(self, action, facing, ms, **kw):
        i = (ms // UI_NOMINAL_MS) % max(self.count(), 1)
        wh = self.size("main", i) or (0, 0)
        return FrameRef("main", i, False, (wh[0] // 2, wh[1] // 2), action, i)

    def preview_clip(self, action, facing):
        return [(self.frame_at(action, facing, k * UI_NOMINAL_MS), (0, 0))
                for k in range(self.actions[action].ticks)]

    def draw(self, canvas, ref, x, y):
        sf = self.sprites()
        if sf is None or not 0 <= ref.index < len(sf):
            return
        blit(canvas, sf, ref.index, x - ref.hotspot[0], y - ref.hotspot[1], sf.palette, "alpha")


def load_cursor_set(key, data_dir):
    for path, hx, hy, period, _ in CURSORS:
        if cursor_name(path) == key:
            return CursorSet(path, hx, hy, period,
                             paths={"main": find_file(os.path.join(data_dir, CURSORS_DIR), path)})
    raise KeyError("unknown cursor %r" % key)


def ui_sequence_paths(data_dir):
    """[(name, path, loader)] of every animated UI sequence present: the
    named ones, then each interface/inn/*/sprites.16a (loader not found)."""
    out = []
    for name, rel, loader in UI_SEQUENCES:
        p = find_file(data_dir, rel)
        if p:
            out.append((name, p, loader))
    inn = find_file(data_dir, "graphics/interface/inn")
    if inn:
        for d in sorted(os.listdir(inn)):
            p = os.path.join(inn, d, "sprites.16a")
            if os.path.isfile(p):
                out.append(("inn_" + d.lower(), p, "not found"))
    return out


def load_ui_set(key, data_dir):
    for name, p, loader in ui_sequence_paths(data_dir):
        if name == key:
            return UiSequenceSet(name, loader, paths={"main": p})
    raise KeyError("unknown UI sequence %r" % key)
