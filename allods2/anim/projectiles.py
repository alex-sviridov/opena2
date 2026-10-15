"""Projectiles and spell effects: projectiles.reg.

Spec: docs/formats/animation.md §1.2 (loader FUN_004824cc), §4.4 (this
API: tick FUN_00471643, draw FUN_00471fee, all CONFIRMED).

Age: obj+0x9c, +1 at the start of every tick.  Projectiles a unit fires
(shoot/cast events, FUN_0046c28b / FUN_0046c4f1) start at age 0, so the
first drawn tick has age 1; the ones the server's messages create (0x86,
0x8b, 0x8c) start at -1, first drawn age 0.  `age0` selects that.

Phase rule by ID (obj+0x74):
- default: (age / 2) mod Phases, one frame per 2 ticks, loops for the flight;
- 0x1c, 0x1e (lightning, prismatic chain): age-1 = 0..12 indexes the
  ping-pong 4 3 2 1 0 1 2 1 0 1 2 3 4; other ages keep the last value;
- 0x36 (teleport): age - 1;  0x17 and the attached "hit" IDs 0x10, 0x14,
  0x18, 0x22, 0x2c, 0x2e, 0x30, 0x32, 0x38, 0x3c, 0x3e, 0x40, 0x42: age.
Frame: phase + Phases * d, d = (facing - 8) & 15 (with Flip, d > 8 ->
16 - d mirrored); just phase when RotationPhases == 1.
Draw (anchor = (x, y - z), box = record Width x Height, default 64):
- A16 = 1: .16a alpha blit with the file's palette;
- Palette != 0 (.256): opaque with its own palette, then the b.256 overlay
  at 50 % with the overlay's own (all-zero) palette, always;
- Palette = 0: opaque with projectiles.pal.
Special draws: 7 = screen lens (allods2.anim.lens), 0x17 = frame 8 falling
from 28 px above while age < 8, then frame age - 8; 0x1c / 0x1e = one sprite
per point of a list (0x1e: + 5 * colour); 0x38 = nothing.
Lifetime: obj+0xa8 ticks; flight time from distance or the server
(animation.md §1.4); the object is gone when it reaches 0.
"""

import os

from ..graphics import load_palettes
from ..reg import load_reg
from .base import COMPASS, Action, AnimationSet, FrameRef, blit, find_file

PROJECTILES_DIR = "graphics/projectiles"
PING_PONG = (4, 3, 2, 1, 0, 1, 2, 1, 0, 1, 2, 3, 4)       # jump table 0x471fba
HIT_IDS = (0x10, 0x14, 0x18, 0x22, 0x2c, 0x2e, 0x30, 0x32, 0x38, 0x3c, 0x3e, 0x40, 0x42)
LENS_ID, HAIL_ID, LIGHTNING_ID, CHAIN_ID, TELEPORT_ID, HEAL_ID = 7, 0x17, 0x1c, 0x1e, 0x36, 0x38
# fixed lifetimes set by the client (FUN_0046c4f1 / message 0x8c), ticks
FIXED_LIFETIME = {LIGHTNING_ID: 13, CHAIN_ID: 13, TELEPORT_ID: 21, 0x38: 1, 0x3c: 1}


def load_projectile_records(data_dir):
    reg = load_reg(os.path.join(data_dir, PROJECTILES_DIR, "projectiles.reg"))
    out = {}
    for n in range(reg.get("Global/Count", 0)):
        sec = reg.get("Projectile%d" % n)
        if sec is None:
            continue
        r = sec.to_dict()
        for k, d in (("Phases", -1), ("RotationPhases", 16), ("Width", 64), ("Height", 64),
                     ("SFX", 0), ("Palette", 0), ("Homing", 0), ("Flip", 0), ("A16", 0)):
            r.setdefault(k, d)
        out[r["ID"]] = r
    return out


def phase_rule(pid):
    if pid in (LIGHTNING_ID, CHAIN_ID):
        return "pingpong"
    if pid == TELEPORT_ID:
        return "age-1"
    if pid == HAIL_ID or pid in HIT_IDS:
        return "age"
    return "half"


class ProjectileSet(AnimationSet):
    """One projectiles.reg record.  One action: "flight" (default rule,
    loops) or "effect" (the special rules, plays once).
    frame_at(action, facing, tick, age0=None, phase0=0, colour=0)."""
    kind = "projectiles"

    def __init__(self, rec, sprites=None, paths=None, shade_palette=None):
        super().__init__("%d_%s" % (rec["ID"], rec["File"].replace("\\", "_")), sprites, paths)
        self.rec = rec
        self.pid = rec["ID"]
        self.rule = phase_rule(self.pid)
        self.shade_palette = shade_palette
        self.directional = rec["RotationPhases"] != 1
        self.preview_facings = COMPASS if self.directional else (8,)
        P = max(rec["Phases"], 1)
        if self.rule == "half":
            self.actions = {"flight": Action("flight", [k // 2 for k in range(2 * P)])}
        else:
            n = FIXED_LIFETIME.get(self.pid, P + (8 if self.pid == HAIL_ID else 0))
            self.actions = {"effect": Action("effect", list(range(n)), end="once")}

    @property
    def default_age0(self):
        """0 for unit-fired IDs (arrows, catapult shots, 7), -1 for spell
        effects created by server messages.  INFERRED default."""
        return 0 if self.pid < 8 else -1

    def phase(self, tick, age0=None, phase0=0):
        age = (self.default_age0 if age0 is None else age0) + 1 + tick
        P = max(self.rec["Phases"], 1)
        if self.rule == "half":
            return (age // 2) % P
        if self.rule == "pingpong":
            ph = phase0
            for a in range(1, age + 1):
                if 0 <= a - 1 < len(PING_PONG):
                    ph = PING_PONG[a - 1]
            return ph
        if self.rule == "age-1":
            return age - 1
        return age

    def frame_at(self, action, facing, tick, *, age0=None, phase0=0, colour=0):
        ph = self.phase(tick, age0, phase0)
        r = self.rec
        P = max(r["Phases"], 1)
        hot = (r["Width"] // 2, r["Height"] // 2)
        if self.pid == HEAL_ID:
            return FrameRef("main", -1, False, hot, action, ph)
        if self.pid == LENS_ID:
            return FrameRef("main", -1, False, (0, 0), action, ph, effect="lens")
        if self.pid == HAIL_ID:
            if ph < 8:
                return FrameRef("main", 8, False, (hot[0], hot[1] + 28 - 4 * ph), action, ph)
            return FrameRef("main", ph - 8, False, hot, action, ph)
        if self.pid == CHAIN_ID:
            return FrameRef("main", ph + 5 * colour, False, hot, action, ph)
        mirrored = False
        if self.directional:
            d = (facing - 8) & 15
            if r["Flip"] and d > 8:
                d, mirrored = 16 - d, True
            index = ph + P * d
        else:
            index = ph
        return FrameRef("main", index, mirrored, hot, action, ph)

    def preview_clip(self, action, facing):
        n = self.actions[action].ticks
        return [(self.frame_at(action, facing, k), (0, 0)) for k in range(n)]

    def extent(self, ref):
        if ref.effect == "lens":
            from .lens import LENS_SIZE
            return (-LENS_SIZE, -LENS_SIZE, LENS_SIZE, LENS_SIZE)
        return super().extent(ref)

    def draw(self, canvas, ref, x, y, z=0, smoothing=True):
        if ref.effect == "lens":
            from .lens import apply_lens
            apply_lens(canvas.pix, x, y - z)
            return
        sf = self.sprites()
        if sf is None or not 0 <= ref.index < len(sf):
            return
        left, top = x - ref.hotspot[0], y - ref.hotspot[1] - z
        r = self.rec
        if r["A16"]:
            blit(canvas, sf, ref.index, left, top, sf.palette, "alpha", ref.mirrored)
        elif r["Palette"]:
            blit(canvas, sf, ref.index, left, top, sf.palette, "opaque", ref.mirrored)
            ov = self.overlay()
            if ov is not None and ref.index < len(ov):
                blit(canvas, ov, ref.index, left, top, ov.palette, "half", ref.mirrored)
        else:
            blit(canvas, sf, ref.index, left, top, self.shade_palette, "opaque", ref.mirrored)


def projectile_paths(rec, data_dir):
    root = os.path.join(data_dir, PROJECTILES_DIR)
    if rec["A16"]:
        return {"main": find_file(root, rec["File"] + ".16a")}
    return {"main": find_file(root, rec["File"] + ".256"),
            "main_b": find_file(root, rec["File"] + "b.256")}


def load_projectile_set(pid, data_dir, records=None):
    recs = records or load_projectile_records(data_dir)
    rec = recs[int(pid)]
    pal = load_palettes(os.path.join(data_dir, PROJECTILES_DIR, "projectiles.pal"))[0].rgb
    return ProjectileSet(rec, paths=projectile_paths(rec, data_dir), shade_palette=pal)
