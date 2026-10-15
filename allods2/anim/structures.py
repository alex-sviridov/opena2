"""Structures (buildings) and the two VariableSize bridges.

Spec: docs/formats/animation.md §1.2 (loader FUN_00482e99), §1.3 (draw
FUN_004669e8, bridges FUN_004679f3 / FUN_00467bdb), §3.2 (tick
FUN_004676d2), §4.2 (this API).

A structure file is a grid of 32 x 32 pieces, cell = col + row * W, W x FH
of them for the intact building.  The picture is FH cells high; its bottom
TileHeight rows are the footprint.  The anchor is the top-left corner of
the footprint (the structure's cell position), so piece (col, row) is drawn
at (32 col, 32 (row - (FH - TileHeight))) from it.
"""

import os

from ..reg import load_reg
from .base import CELL, Action, AnimationSet, FrameRef, Part, blit, find_file

STRUCTURES_DIR = "graphics/structures"
BRIDGE9_ID = 0x21           # map loader 0x4abf1b: class 0x5d8c50 (FUN_004679f3)
BRIDGE14_ID = 0x25          # class 0x5d8ca8 (FUN_00467bdb)


def _seq(times, frames):
    out = []
    for t, f in zip(times or [], frames or []):
        out.extend([f] * t)
    return out


def load_structure_records(data_dir):
    """structures.reg records by ID (FUN_00482e99 fields as dicts)."""
    reg = load_reg(os.path.join(data_dir, STRUCTURES_DIR, "structures.reg"))
    out = {}
    for n in range(reg.get("Global/Count", 0)):
        sec = reg.get("Structure%d" % n)
        if sec is None:
            continue
        r = sec.to_dict()
        r.setdefault("Phases", -1)
        r["seq"] = _seq(r.get("AnimTime"), r.get("AnimFrame")) if r["Phases"] > 1 else []
        mask = r.get("AnimMask") or ""
        r["mask"] = mask if r["Phases"] > 1 else ""
        out[r.get("ID", -1)] = r
    return out


class StructureSet(AnimationSet):
    """One structures.reg record.

    Actions: "intact" (loops the AnimTime/AnimFrame sequence, or a single
    still) and "destroyed" (static) when the building can be destroyed.
    frame_at(action, 0, tick, start=0, animate=True): the phase index runs
    (start + tick) mod len, start = obj+0x74 on the first shown tick;
    animate=False is the frozen state (not in sight, or the "Object
    animations" option off, DAT_005fb974).
    """
    kind = "structures"

    def __init__(self, rec, sprites=None, paths=None):
        super().__init__("%d_%s" % (rec["ID"], rec["File"].replace("\\", "_")), sprites, paths)
        self.rec = rec
        self.W, self.TH, self.FH = rec["TileWidth"], rec["TileHeight"], rec["FullHeight"]
        self.seq = rec["seq"]
        self.mask = rec["mask"]
        self.A = sum(c != "-" for c in self.mask[:self.W * self.FH])
        acts = [Action("intact", list(self.seq) or [0])]
        if not rec.get("Indestructible"):
            acts.append(Action("destroyed", [0], end="hold"))
        self.actions = {a.name: a for a in acts}

    def piece(self, cell, k, destroyed=False):
        """Frame of piece `cell` at sequence value k (FUN_004669e8).  The
        destroyed frame count - W*FH + cell is the file's last W*FH pieces,
        so files without a destroyed block show their intact (or last
        animation) pieces (animation.md §1.3)."""
        wf = self.W * self.FH
        if destroyed:
            return self.count() - wf + cell
        if k and cell < len(self.mask) and self.mask[cell] != "-":
            return wf + (k - 1) * self.A + sum(c != "-" for c in self.mask[:cell])
        return cell

    def frame_at(self, action, facing, tick, *, start=0, animate=True):
        destroyed = action == "destroyed"
        k = 0
        if self.seq and animate and not destroyed:
            k = self.seq[(start + tick) % len(self.seq)]
        top = CELL * (self.FH - self.TH)
        parts = tuple(Part("main", self.piece(c + r * self.W, k, destroyed), CELL * c, CELL * r - top)
                      for r in range(self.FH) for c in range(self.W))
        return FrameRef("main", -1, False, (0, top), action, k, parts=parts)

    def draw(self, canvas, ref, x, y, smoothing=True, palette=None):
        """Pieces with the file's own palette (+0x18), then the b.256 overlay
        at 50 % with the main sprite's table when Smoothing is on."""
        sf, ov = self.sprites(), self.overlay() if smoothing else None
        pal = palette if palette is not None else sf.palette
        for p in ref.parts:
            if p.index < len(sf):
                blit(canvas, sf, p.index, x + p.dx, y + p.dy, pal, "opaque")
            if ov is not None and p.index < len(ov):
                blit(canvas, ov, p.index, x + p.dx, y + p.dy, pal, "half")


class BridgeSet(StructureSet):
    """VariableSize bridges: the map gives the size in cells (record
    +0xa/+0xc).  ID 0x21: 9 pieces (corners, edges, centre).  ID 0x25: 14
    pieces; the bottom row's even cells play 8 + (clock & 3), one frame per
    tick."""
    kind = "bridges"

    def __init__(self, rec, w=4, h=4, sprites=None, paths=None):
        super().__init__(rec, sprites, paths)
        self.w, self.h = w, h
        self.actions = {"bridge": Action("bridge", [0, 1, 2, 3] if rec["ID"] == BRIDGE14_ID else [0])}

    def bridge_piece(self, x, y, clock):
        w, h = self.w, self.h
        if self.rec["ID"] == BRIDGE14_ID:          # FUN_00467bdb
            if (x, y) == (0, 0):
                return 0
            if (x, y) == (w - 1, 0):
                return 3
            if y == 0:
                return 1 + (x & 1)
            if (x, y) == (0, h - 1):
                return 7
            if (x, y) == (w - 1, h - 1):
                return 13
            if y == h - 1:
                return 12 if x & 1 else 8 + (clock & 3)
            return 4 if x == 0 else 6 if x == w - 1 else 5
        corner = {(0, 0): 0, (w - 1, 0): 2, (0, h - 1): 6, (w - 1, h - 1): 8}   # FUN_004679f3
        if (x, y) in corner:
            return corner[(x, y)]
        if y == 0:
            return 1
        if y == h - 1:
            return 7
        return 3 if x == 0 else 5 if x == w - 1 else 4

    def frame_at(self, action, facing, tick, **kw):
        parts = tuple(Part("main", self.bridge_piece(x, y, tick), CELL * x, CELL * y)
                      for y in range(self.h) for x in range(self.w))
        return FrameRef("main", -1, False, (0, 0), action, tick & 3, parts=parts)


def structure_paths(rec, data_dir):
    base = find_file(os.path.join(data_dir, STRUCTURES_DIR), rec["File"] + ".256")
    over = find_file(os.path.join(data_dir, STRUCTURES_DIR), rec["File"] + "b.256")
    return {"main": base, "main_b": over}


def load_structure_set(sid, data_dir, records=None, **kw):
    recs = records or load_structure_records(data_dir)
    rec = recs[int(sid)]
    cls = BridgeSet if rec.get("VariableSize") else StructureSet
    return cls(rec, paths=structure_paths(rec, data_dir), **kw)
