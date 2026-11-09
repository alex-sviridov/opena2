"""Ambience (docs/engine/audio.md 2.4; CONFIRMED `FUN_0041b311`, INFERRED where marked): the river and fire-wall loops and the random one-shots of
trees and objects, scanned around the camera.  Pure: the world is read through `cells`, `cell_fx`, `objects_at` and `objects`; the result is a list of
`Ambient` actions for the Director.  Draws come from the audio layer's own `Rng`."""

import math
from dataclasses import dataclass

RIVER_ID, FIRE_ID = 50, 90
LOOP_RIVER, LOOP_FIRE = "river", "fire"
BORDER = 8                      # the scan window is clamped to [8, size - 8]
PERIOD_MS = 5000                # next one-shot at `now + 5000 + rand / 7` (`rand` = the CRT rand, 0..0x7fff)
NIGHT_ADD = 10


@dataclass(frozen=True)
class Ambient:
    """`action`: `loop` (start, or update volume / pan of a running loop), `stop` (the source count fell to 0), `oneshot`."""
    action: str
    name: str
    sound: int = 0
    att: int = 0
    pan: int = 0


def object_class(rec):
    """`n44` / `n34` / `n58` of an `objects.reg` record (the exe's def `+0x44 < 0 && +0x40 == -2`, else `+0x14 >= 2`, else the rest).  DECISION from
    the record fields (INFERRED layout `+0x14` Phases, `+0x40` FireObject, `+0x44` DeadObject, the order of the `anim.objects` keys): n44 = the 21 dead-tree
    records (`DeadObject < 0`, `FireObject == -2`), n34 = animated live trees and bushes (`Phases >= 2`, 45 records), n58 = stones and the rest (126)."""
    if rec["DeadObject"] < 0 and rec["FireObject"] == -2:
        return 44
    return 34 if rec["Phases"] >= 2 else 58


def hour_of(clock):
    """`(((clock >> 4) + 360) / 60) % 24` (client `+0x408`)."""
    return (((clock >> 4) + 360) // 60) % 24


def is_night(clock):
    h = hour_of(clock)
    return h < 4 or h > 19


def loop_mix(cells, view):
    """River / fire loop volume and pan from the source cells `[(x, y)]`: attenuation of the nearest cell `-(exp(d // 8) - 1) * 100` (`d` = integer cell
    distance from the view centre, floored at -10000), pan = mean of `clamp((x - cx) * 2000 / vw, +-2000)` weighted by each cell's loudness
    `(10000 - |v_i|) / 10000` (INFERRED reading of "`* v_i / 10000`").  SFX bus is added by the caller."""
    cx, cy = view.x + view.w // 2, view.y + view.h // 2
    best, pans = -10000, 0.0
    for x, y in cells:
        d = int(math.hypot(x - cx, y - cy))
        v = -10000 if d // 8 > 9 else int(max(-(math.exp(d // 8) - 1) * 100, -10000))
        best = max(best, v)
        p = max(-2000, min(2000, (x - cx) * 2000 / view.w)) if view.w else 0
        pans += p * (10000 - abs(v)) / 10000.0
    return best, int(pans / len(cells))


class Ambience:
    def __init__(self, rng, ids=None):
        self.rng, self.ids = rng, ids                # `ids`: container of existing sfx ids (None = all exist)
        self.cell, self.next, self.loops = None, 0, {}
        self.classes = {}

    def _has(self, sid):
        return self.ids is None or sid in self.ids

    def scan(self, world, view):
        """-> (river cells, fire cells, n34, n58, n44) in the window `[v - vw, v + 2 vw]` clamped to `[8, size - 8]`.  A fire-wall cell is one whose
        cell record holds a Wall of Fire stamp (`cell_fx` slot 0, `FUN_004203e0` flag `& 8`)."""
        x0, x1 = max(BORDER, view.x - view.w), min(world.width - BORDER, view.x + 2 * view.w) + 1
        y0, y1 = max(BORDER, view.y - view.h), min(world.height - BORDER, view.y + 2 * view.h) + 1
        river, fire, n = [], [], {34: 0, 58: 0, 44: 0}
        recs = world.assets.objects_reg() if getattr(world, "assets", None) is not None else {}
        for y in range(y0, y1):
            for x in range(x0, x1):
                if 8 <= (int(world.cells[y, x]) & 0x1FFF) >> 6 <= 11:
                    river.append((x, y))
                fx = world.cell_fx.get((x, y))
                if fx is not None and fx[0] is not None:
                    fire.append((x, y))
                for i in world.objects_at(x, y):
                    o = world.objects[i]
                    if o.kind == "object" and o.type_id in recs:
                        c = self.classes.get(o.type_id)
                        if c is None:
                            c = self.classes[o.type_id] = object_class(recs[o.type_id])
                        n[c] += 1
        return river, fire, n[34], n[58], n[44]

    def oneshot_id(self, n34, n58, clock):
        """`base = 600; if n34 <= rand(10): base = 620; if n34 + n58 <= rand(10): base += 20`; night +10; `id = base + rand(10)` re-rolled until the slot
        exists (at most 32 tries, then None).  DECISION: the id offset is 0..9 (`rng.rand(9)`): the id ranges of the table are 10 wide (600-609, 610-619 ...), so a
        0..10 draw would leak into the next range; the two comparison draws stay `rand(10)` (INFERRED)."""
        base = 600
        if n34 <= self.rng.rand(10):
            base = 620
        if n34 + n58 <= self.rng.rand(10):
            base += 20
        if is_night(clock):
            base += NIGHT_ADD
        for _ in range(32):
            sid = base + self.rng.rand(9)
            if self._has(sid):
                return sid
        return None

    def update(self, now_ms, world, view, clock):
        """One pass (when the camera cell changed or the timer expired): the loop actions and, on a timer pass with objects in the window, one one-shot
        (pan = mean of the objects' pans is approximated by the view centre: pan 0, INFERRED; SFX only, no attenuation)."""
        cell = (view.x, view.y)
        due = now_ms >= self.next
        if cell == self.cell and not due:
            return []
        self.cell = cell
        river, fire, n34, n58, n44 = self.scan(world, view)
        out = []
        for name, sid, cells in ((LOOP_RIVER, RIVER_ID, river), (LOOP_FIRE, FIRE_ID, fire)):
            if cells and self._has(sid):
                att, pan = loop_mix(cells, view)
                self.loops[name] = True
                out.append(Ambient("loop", name, sid, att, pan))
            elif self.loops.pop(name, None):
                out.append(Ambient("stop", name))
        if due:
            self.next = now_ms + PERIOD_MS + self.rng.rand15() // 7
            if n34 + n58 + n44:
                sid = self.oneshot_id(n34, n58, clock)
                if sid is not None:
                    out.append(Ambient("oneshot", "tree", sid, 0, 0))
        return out
