"""Shared pieces of the animation API: the game clock, actions, frame
references, sprite loading and the draw modes.  Spec:
docs/formats/animation.md.

Every animation class (units, structures, objects, projectiles, terrain,
cursors) is an AnimationSet subclass with the same surface:

    aset.actions                     name -> Action
    aset.preview_facings             facings worth showing (one for undirected kinds)
    aset.frame_at(action, facing, t) FrameRef (t in ticks, or ms when aset.clock == "ms")
    aset.draw(canvas, ref, x, y)     draw anchored at (x, y)
    aset.extent(ref)                 (x0, y0, x1, y1) drawn area around the anchor
    aset.preview_clip(action, facing)  [(FrameRef, (dx, dy) ground shift)] for one pass
"""

import os
from dataclasses import dataclass, field

from ..graphics import SpriteFile

# FUN_00492068: ticks per second by game speed 0..8; period = 1000 // rate ms.
TICK_RATES = (8, 10, 12, 14, 16, 20, 24, 28, 32)
DEFAULT_SPEED = 4                       # FUN_0048750d
FACINGS = range(16)                     # obj+0x70, clockwise from screen-up
COMPASS = (8, 10, 12, 14, 0, 2, 4, 6)   # one facing per stored animated direction, front first
CELL = 32                               # pixels per map cell
CELL_UNITS = 256                        # map units per cell (pos >> 8)
UNITS_PER_PIXEL = 8                     # units.md ShootOffset


def period_ms(speed=DEFAULT_SPEED):
    return 1000 // TICK_RATES[speed]


def tick_at_ms(ms, speed=DEFAULT_SPEED):
    """Ticks elapsed after `ms` milliseconds of the fixed-step loop
    (FUN_0048e7d0), ignoring its 16-tick re-base jitter."""
    return int(ms) // period_ms(speed)


def find_file(root, rel):
    """Path of `rel` (backslashes allowed) under `root`, matching each
    component case-insensitively as Windows does; None when absent."""
    path = root
    for part in rel.replace("\\", "/").split("/"):
        if not part:
            continue
        exact = os.path.join(path, part)
        if os.path.exists(exact):
            path = exact
            continue
        try:
            names = {n.lower(): n for n in os.listdir(path)}
        except OSError:
            return None
        if part.lower() not in names:
            return None
        path = os.path.join(path, names[part.lower()])
    return path


@dataclass
class Action:
    """One animation.

    phases: one element per tick (per 16 map units for unit `move`).
    end: "loop"; "idle" (once, then the idle state); "hold" (static, or the
        last phase held); "once" (plays, then the object is gone).
    clock: "tick", "distance" or "ms".
    events: name -> tick.
    source: which sprite file of the set the frames come from.
    """
    name: str
    phases: list
    end: str = "loop"
    clock: str = "tick"
    events: dict = field(default_factory=dict)
    source: str = "main"

    @property
    def ticks(self):
        return len(self.phases)


@dataclass(frozen=True)
class Part:
    """One blit of a composite frame: top-left (dx, dy) relative to the
    anchor."""
    source: str
    index: int
    dx: int
    dy: int
    mirrored: bool = False


@dataclass(frozen=True)
class FrameRef:
    """A frame to draw.  hotspot = the anchor (object position) inside the
    frame box, the same whether mirrored or not (mirroring flips in place).
    action/phase = what is shown, which can differ from the action asked for
    after a once-action has ended.  parts: the blits of a composite frame
    (structures, bridges, terrain); empty for single-sprite frames.
    effect: a non-sprite draw ("lens") or None."""
    source: str
    index: int
    mirrored: bool
    hotspot: tuple
    action: str
    phase: int
    events: tuple = ()
    parts: tuple = ()
    effect: str = None


class AnimationSet:
    """Base: sprite files by source name, lazily loaded from `paths`."""
    kind = ""
    clock = "tick"
    preview_facings = (0,)

    def __init__(self, name, sprites=None, paths=None):
        self.name = name
        self.paths = dict(paths or {})
        self._sprites = dict(sprites or {})
        self.actions = {}

    def sprites(self, source="main"):
        if source not in self._sprites:
            p = self.paths.get(source)
            self._sprites[source] = SpriteFile.load(p) if p and os.path.isfile(p) else None
        return self._sprites[source]

    def overlay(self, source="main"):
        """The b.256 smoothing overlay of a source, or None."""
        return self.sprites(source + "_b")

    def count(self, source="main"):
        sf = self.sprites(source)
        return len(sf) if sf is not None else 0

    def size(self, source, index):
        sf = self.sprites(source)
        if sf is None or not 0 <= index < len(sf):
            return None
        return sf[index].width, sf[index].height

    def blits(self, ref):
        """[Part] a FrameRef draws."""
        if ref.parts:
            return list(ref.parts)
        if ref.index < 0 or ref.effect:
            return []
        return [Part(ref.source, ref.index, -ref.hotspot[0], -ref.hotspot[1], ref.mirrored)]

    def extent(self, ref):
        x0 = y0 = x1 = y1 = 0
        for p in self.blits(ref):
            wh = self.size(p.source, p.index)
            if wh is None:
                continue
            x0, y0 = min(x0, p.dx), min(y0, p.dy)
            x1, y1 = max(x1, p.dx + wh[0]), max(y1, p.dy + wh[1])
        return x0, y0, x1, y1

    def preview_clip(self, action, facing):
        a = self.actions[action]
        return [(self.frame_at(action, facing, k), (0, 0)) for k in range(max(a.ticks, 1))]

    def missing_frames(self):
        """[(action, facing, source, index)] the set can ask for past the end
        of their file (the game draws nothing there)."""
        out = []
        for name in self.actions:
            for d in self.preview_facings:
                for ref, _ in self.preview_clip(name, d):
                    for p in self.blits(ref):
                        if p.index >= self.count(p.source):
                            out.append((name, d, p.source, p.index))
        return out


def blit(canvas, sf, index, x, y, palette, mode, mirror=False):
    """One sprite blit in a game draw mode (sprites.md):
    opaque (+0x14/+0x18), half (+0x34/+0x38, 50 %), alpha (.16a)."""
    s = sf[index]
    if mode == "alpha":
        canvas.draw_16a(s, x, y, palette, mirror=mirror)
    elif mode == "half":
        canvas.draw_256_translucent(s, x, y, palette, mirror=mirror)
    else:
        canvas.draw_256(s, x, y, palette, mirror=mirror)
