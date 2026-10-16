"""Cursors and other animated UI sprites.

Spec: docs/formats/animation.md §4.8 / §4.9.

Cursors (CONFIRMED, table FUN_0047b92d, class FUN_0047b736, mouse manager
0x604500): each cursor is (file, hot x, hot y, period ms).  The mouse
manager (FUN_004263c0 / 0x4269a4) reads timeGetTime(); when more than
`period` ms passed since the last step it advances one frame and wraps at
the frame count; the cursor is drawn at (mouse x - hot x, mouse y - hot y)
with the sprite's own table (.16a alpha, or opaque .256).  Period
2000000000 = a still cursor.  Time is in milliseconds here.

Other UI sequences (CONFIRMED, §4.9), wall-clock ms with the screen
polled every millisecond:
- PreCreate "blind": frames 1..14 (frame 0 never drawn), one per redraw,
  a redraw when more than 0x43 ms passed (68 ms); the random idle gaps
  between runs are not modelled.
- World-map flags: one frame per redraw, at most one per 100 ms.
- Inn pictures (FUN_00499783 / draw FUN_00497adf): only the selected one
  advances, when more than 0x7d ms passed (126 ms); the others hold.
- Chargen cube: loaded but never drawn (dead asset); previews play it at a
  nominal 100 ms per frame and the set says `timed = False`.
"""


from ..common import as_fs, find, join
from .base import Action, AnimationSet, FrameRef

STILL = 2000000000
# FUN_0047b92d: (path under graphics/cursors, hot x, hot y, period ms, global)
CURSORS = (
    ("default/sprites.16a", 4, 4, STILL, 0x626cb8), ("move/sprites.16a", 2, 3, 100, 0x626cbc),
    ("swarm/sprites.16a", 2, 3, 100, 0x626cc0), ("attack/sprites.16a", 3, 3, 100, 0x626cc4),
    ("defend/sprites.16a", 16, 16, 100, 0x626cc8), ("select/sprites.16a", 3, 3, 100, 0x626ccc),
    ("patrol/sprites.16a", 8, 25, 100, 0x626cd0), ("cast/sprites.16a", 16, 16, 100, 0x626cd4),
    ("pickup/sprites.16a", 16, 12, 66, 0x626cd8), ("arrow0/sprites.16a", 16, 6, STILL, 0x626cdc),
    ("arrow4/sprites.16a", 16, 28, STILL, 0x626ce0), ("arrow6/sprites.16a", 5, 16, STILL, 0x626ce4),
    ("arrow2/sprites.16a", 26, 16, STILL, 0x626ce8), ("arrow7/sprites.16a", 8, 9, STILL, 0x626cec),
    ("arrow5/sprites.16a", 8, 24, STILL, 0x626cf0), ("arrow1/sprites.16a", 23, 9, STILL, 0x626cf4),
    ("arrow3/sprites.16a", 23, 24, STILL, 0x626cf8), ("sdefault/sprites.16a", 1, 1, STILL, 0x626cfc),
    ("smove.256", 0, 0, STILL, 0x626d00), ("sattack.256", 0, 0, STILL, 0x626d04),
    ("sdefend.256", 0, 0, STILL, 0x626d08), ("spatrol.256", 0, 0, STILL, 0x626d0c),
    ("scast.256", 0, 0, STILL, 0x626d10), ("cantput/sprites.16a", 38, 36, STILL, 0x626d14),
    ("town/sprites.16a", 16, 16, STILL, 0x626d18), ("dice/sprites.16a", 16, 16, 100, 0x626d1c),
    ("wait/sprites.16a", 16, 16, 100, 0x626d20), ("backpack/sprites.16a", 16, 16, 100, 0x626d24),
)
CURSORS_DIR = "graphics/cursors"

# UI .16a sequences: (name, path under data/, loader)
UI_SEQUENCES = (
    ("chrgen_cube", "graphics/interface/chrgen/cube/sprites.16a", "FUN_0042eba1 (never drawn)"),
    ("chrgen_blind", "graphics/interface/chrgen/PreCreate/Blind/sprites.16a", "FUN_00433a3d"),
    ("map_missionflag", "graphics/Global.Map/MissionFlag/sprites.16a", "FUN_0046eeb0"),
    ("map_yourflag", "graphics/Global.Map/YourFlag/sprites.16a", "FUN_0046eeb0"),
    # drawn instead of MissionFlag / YourFlag when map +0x1b0 != 0 (FUN_0046fdd5)
    ("map_flag1", "graphics/Global.Map/Flag1/sprites.16a", "FUN_0046eeb0"),
    ("map_flag", "graphics/Global.Map/Flag/sprites.16a", "FUN_0046eeb0"),
    ("map_flagonmap", "graphics/Global.Map/FlagOnMap/sprites.16a", "FUN_0046eeb0"),
)
UI_NOMINAL_MS = 100
# name or name prefix -> (ms per frame, first frame drawn); missing = untimed
UI_TIMING = {
    "chrgen_blind": (0x43 + 1, 1),        # FUN_0043541e: redraw when > 0x43 ms
    "map_missionflag": (99 + 1, 0),       # FUN_004715a5: redraw when > 99 ms
    "map_yourflag": (99 + 1, 0),
    "map_flag1": (99 + 1, 0),             # counter +0x128, as MissionFlag
    "map_flag": (99 + 1, 0),              # counter +0x130, as YourFlag
    "map_flagonmap": (99 + 1, 0),         # counter +0x128
    "inn_": (0x7d + 1, 0),                # FUN_00497adf: selected entry, > 0x7d ms
}


def ui_timing(name):
    for key, timing in UI_TIMING.items():
        if name == key or (key.endswith("_") and name.startswith(key)):
            return timing
    return None


def cursor_name(path):
    return path.split("/")[0].replace(".256", "")


def cursor_frame(ms, period, count):
    """Frame after `ms` ms with the manager polled every millisecond: it
    steps when strictly more than `period` ms passed (FUN_004263c0), so one
    frame per period + 1 ms."""
    if period >= STILL or count <= 1:
        return 0
    return (ms // (period + 1)) % count


class CursorSet(AnimationSet):
    """One cursor; action "cursor", clock in ms; hotspot = (hot x, hot y)."""
    kind = "cursors"
    clock = "ms"

    def __init__(self, path, hx, hy, period, sprites=None, paths=None, fs=None):
        super().__init__(cursor_name(path), sprites, paths, fs)
        self.hot, self.period = (hx, hy), period
        self.blit_mode = "alpha" if path.endswith(".16a") else "opaque"
        n = self.count() or 1
        still = period >= STILL or n <= 1
        self.actions = {"cursor": Action("cursor", [0] if still else list(range(n)), clock="ms")}
        self.preview_step_ms = 100 if still else period + 1

    def frame_at(self, action, facing, ms, **kw):
        i = cursor_frame(ms, self.period, self.count())
        return FrameRef("main", i, False, self.hot, action, i)


class UiSequenceSet(AnimationSet):
    """A UI .16a sequence played frame by frame at its screen's rate
    (UI_TIMING); untimed ones (the never-drawn cube) at UI_NOMINAL_MS."""
    kind = "ui"
    clock = "ms"
    blit_mode = "alpha"

    def __init__(self, name, loader, sprites=None, paths=None, fs=None):
        super().__init__(name, sprites, paths, fs)
        self.loader = loader
        timing = ui_timing(name)
        self.timed = timing is not None
        self.preview_step_ms, first = timing or (UI_NOMINAL_MS, 0)
        n = max(self.count(), 1)
        self.frames = list(range(min(first, n - 1), n))
        self.actions = {"frames": Action("frames", self.frames, clock="ms")}

    def frame_at(self, action, facing, ms, **kw):
        i = self.frames[(ms // self.preview_step_ms) % len(self.frames)]
        wh = self.size("main", i) or (0, 0)
        return FrameRef("main", i, False, (wh[0] // 2, wh[1] // 2), action, i)


def load_cursor_set(key, fs=None):
    fs = as_fs(fs)
    for path, hx, hy, period, _ in CURSORS:
        if cursor_name(path) == key:
            return CursorSet(path, hx, hy, period, fs=fs,
                             paths={"main": find(fs, join(CURSORS_DIR, path))})
    raise KeyError("unknown cursor %r" % key)


def ui_sequence_paths(fs=None):
    """[(name, path, loader)] of every animated UI sequence present: the
    named ones, then each interface/inn/*/sprites.16a (FUN_00499783: Unit%d
    by unit type id, HeroFighter / HeroMage for heroes)."""
    fs = as_fs(fs)
    out = []
    for name, rel, loader in UI_SEQUENCES:
        p = find(fs, rel)
        if p:
            out.append((name, p, loader))
    inn = "graphics/interface/inn"
    if fs.isdir(inn):
        for d in sorted(fs.listdir(inn), key=str.lower):
            p = find(fs, join(inn, d, "sprites.16a"))
            if p:
                out.append(("inn_" + d.lower(), p, "FUN_00499783"))
    return out


def load_ui_set(key, fs=None):
    fs = as_fs(fs)
    for name, p, loader in ui_sequence_paths(fs):
        if name == key:
            return UiSequenceSet(name, loader, paths={"main": p}, fs=fs)
    raise KeyError("unknown UI sequence %r" % key)
