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
RETRY_MS = 250                  # DECISION (see `update`)
PRIORITY = 0xDC                 # every ambience play passes priority 0xdc (`0x41bbcb`, `0x41bd80`)


@dataclass(frozen=True)
class Ambient:
    """`action`: `loop` (start, or update volume / pan of a running loop), `stop` (the source count fell to 0), `oneshot`."""
    action: str
    name: str
    sound: int = 0
    att: int = 0
    pan: int = 0


def object_class(rec):
    """`n44` / `n34` / `n58` of an `objects.reg` record, or None (CONFIRMED `FUN_0041b311`, the def fields are CONFIRMED in formats/animation.md):
    `DeadObject (+0x44) < 0`: `FireObject (+0x40) == -2` is n44 (the 21 burnt / dead versions), **any other such record counts for nothing** (the 106 stones,
    stumps and the like); `DeadObject >= 0` (an object with a dead version: a tree or bush that can burn): `Phases (+0x14) >= 2` is n34 (43 animated
    trees), else n58 (22 static bushes)."""
    if rec["DeadObject"] < 0:
        return 44 if rec["FireObject"] == -2 else None
    return 34 if rec["Phases"] >= 2 else 58


def hour_of(clock):
    """`(((clock >> 4) + 360) / 60) % 24` (client `+0x408`)."""
    return (((clock >> 4) + 360) // 60) % 24


def is_night(clock):
    h = hour_of(clock)
    return h < 4 or h > 19


def _cdiv(a, b):
    """C integer division (truncates toward zero)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def cell_mix(x, y, view):
    """`(pan_i, v_i)` of one source cell (CONFIRMED `0x41b5e9`-`0x41b72c`): `d = trunc(sqrt(dx^2 + dy^2))` from the view centre `(vx + (vw >> 1), vy + (vh >> 1))`,
    `v = max(0, trunc(10000 - (exp(d >> 3) - 1) * 100))` (loudness 0..10000, the attenuation is `v - 10000`), `pan = clamp(trunc(dx * 2000 / vw), +-2000)`."""
    cx, cy = view.x + (view.w >> 1), view.y + (view.h >> 1)
    dx, dy = x - cx, y - cy
    d = int(math.sqrt(dx * dx + dy * dy))
    k = d >> 3
    v = 0 if k > 9 else max(0, int(10000 - (math.exp(k) - 1) * 100))
    pan = max(-2000, min(2000, _cdiv(dx * 2000, view.w))) if view.w else 0
    return pan, v


def loop_mix(cells, view):
    """River / fire loop volume and pan from the source cells `[(x, y)]` (CONFIRMED): attenuation `max over cells of v_i - 10000` (the nearest cell
    wins), pan = `trunc(sum of trunc(pan_i * v_i / 10000) / count)`.  SFX bus is added by the caller."""
    best, tot = -10000, 0
    for x, y in cells:
        pan, v = cell_mix(x, y, view)
        best = max(best, v - 10000)
        tot += _cdiv(pan * v, 10000)
    return best, _cdiv(tot, len(cells))


class Ambience:
    def __init__(self, rng, ids=None):
        self.rng, self.ids = rng, ids                # `ids`: container of existing sfx ids (None = all exist)
        self.cell, self.next, self.loops = None, 0, {}
        self.classes = {}

    def _has(self, sid):
        return self.ids is None or sid in self.ids

    def scan(self, world, view, objects=True):
        """-> (river cells, fire cells, n34, n58, n44, object pan sum) in the window `[v - vw, v + 2 vw]` clamped to `[8, size - 8]`.  A fire-wall cell is
        one whose cell record holds a Wall of Fire stamp (`cell_fx` slot 0, `FUN_004203e0` flag `& 8`).  The exe counts objects **only on a timer pass**
        (`local_10`), so `objects=False` skips them; the pan sum is `sum of trunc(pan_i * v_i / 10000)` over every counted object."""
        x0, x1 = max(BORDER, view.x - view.w), min(world.width - BORDER, view.x + 2 * view.w) + 1
        y0, y1 = max(BORDER, view.y - view.h), min(world.height - BORDER, view.y + 2 * view.h) + 1
        river, fire, n, pans = [], [], {34: 0, 58: 0, 44: 0}, 0
        recs = world.assets.objects_reg() if objects and getattr(world, "assets", None) is not None else {}
        for y in range(y0, y1):
            for x in range(x0, x1):
                if 8 <= (int(world.cells[y, x]) & 0x1FFF) >> 6 <= 11:
                    river.append((x, y))
                fx = world.cell_fx.get((x, y))
                if fx is not None and fx[0] is not None:
                    fire.append((x, y))
                if not recs:
                    continue
                for i in world.objects_at(x, y):
                    o = world.objects[i]
                    if o.kind == "object" and o.type_id in recs:
                        c = self.classes.get(o.type_id, 0)
                        if c == 0:
                            c = self.classes[o.type_id] = object_class(recs[o.type_id]) or -1
                        if c > 0:
                            n[c] += 1
                            pan, v = cell_mix(x, y, view)
                            pans += _cdiv(pan * v, 10000)
        return river, fire, n[34], n[58], n[44], pans

    def oneshot_id(self, n34, n58, n44, clock):
        """CONFIRMED `0x41bc84`-`0x41bd7c`: `r = rand(n34 + n58 + n44 - 1)` (inclusive, so `0..total-1`); `base = 600; if n34 <= r: base = 620;
        if n34 + n58 <= r: base += 20` (so the forest sounds 600+ belong to the n34 trees, 620+ to the n58 bushes, 640+ to the n44 dead trees, each in
        proportion to the counts); night (`0x41bd0b`) adds 10; `id = base + rand(10)` (**inclusive: 0..10**, so a day roll can reach the first night id of
        the block) re-rolled until the slot exists (a `do ... while (slot == 0)` with no limit in the exe; here at most 32 tries, then None)."""
        base = 600
        r = self.rng.rand(n34 + n58 + n44 - 1)
        if n34 <= r:
            base = 620
        if n34 + n58 <= r:
            base += 20
        if is_night(clock):
            base += NIGHT_ADD
        for _ in range(32):
            sid = base + self.rng.rand(10)
            if self._has(sid):
                return sid
        return None

    def update(self, now_ms, world, view, clock):
        """One pass (when the camera cell changed or the timer expired): the loop actions and, on a timer pass with objects in the window, one one-shot
        (SFX bus only, no attenuation; pan = the mean of the objects' pans, CONFIRMED).  Loops and one-shots play with priority `0xdc` (`push 0xdc` at
        `0x41bbcb`, `0x41bd80`)."""
        cell = (view.x, view.y)
        due = now_ms >= self.next
        if cell == self.cell and not due:
            return []
        self.cell = cell
        river, fire, n34, n58, n44, pans = self.scan(world, view, objects=due)
        out = []
        for name, sid, cells in ((LOOP_RIVER, RIVER_ID, river), (LOOP_FIRE, FIRE_ID, fire)):
            if cells and self._has(sid):
                att, pan = loop_mix(cells, view)
                self.loops[name] = True
                out.append(Ambient("loop", name, sid, att, pan))
            elif self.loops.pop(name, None):
                out.append(Ambient("stop", name))
        total = n34 + n58 + n44
        if due and total:                      # the timer is re-armed only when a one-shot pass ran (`0x41bdb0`: inside `if (n34 + n58 + n44 != 0)`)
            self.next = now_ms + PERIOD_MS + self.rng.rand15() // 7
            sid = self.oneshot_id(n34, n58, n44, clock)
            if sid is not None:
                out.append(Ambient("oneshot", "tree", sid, 0, _cdiv(pans, total)))
        elif due:
            self.next = now_ms + RETRY_MS      # DECISION: the exe rescans on every frame while the window holds no object; we retry 4 times a second (speed)
        return out
