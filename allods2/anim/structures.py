"""Structures (buildings) and the two VariableSize bridges.

Spec: docs/formats/animation.md §1.2 (loader FUN_0047d8af), §1.3 (draw
FUN_00461649, bridges FUN_00462654 / FUN_0046283c), §3.2 (tick
FUN_00462333), §4.2 (this API).

A structure file is a grid of 32 x 32 pieces, cell = col + row * W, W x FH
of them for the intact building.  The picture is FH cells high; its bottom
TileHeight rows are the footprint.  The anchor is the top-left corner of
the footprint (the structure's cell position), so piece (col, row) is drawn
at (32 col, 32 (row - (FH - TileHeight))) from it.
"""



from ..common import as_fs, find, join
from ..reg import load_reg
from ..units import expand_sequence
from .base import CELL, Action, AnimationSet, FrameRef, Part, blit, record_name

STRUCTURES_DIR = "graphics/structures"
BRIDGE9_ID = 0x21           # map loader 0x4a479b: class 0x5cea88 (FUN_00462654)
BRIDGE14_ID = 0x25          # class 0x5ceae0 (FUN_0046283c)


def load_structure_records(fs=None):
    """structures.reg records by ID (FUN_0047d8af fields as dicts)."""
    reg = load_reg(STRUCTURES_DIR + "/structures.reg", as_fs(fs))
    out = {}
    for r in reg.records("Structure", "Count"):
        animated = r.setdefault("Phases", -1) > 1
        r["seq"] = expand_sequence(r.get("AnimTime"), r.get("AnimFrame")) if animated else []
        r["mask"] = (r.get("AnimMask") or "") if animated else ""
        out[r.get("ID", -1)] = r
    return out


class StructureSet(AnimationSet):
    """One structures.reg record.

    Actions: "intact" (loops the AnimTime/AnimFrame sequence, or a single
    still) and "destroyed" (static) when the building can be destroyed.
    frame_at(action, 0, tick, start=0, animate=True): the phase index runs
    (start + tick) mod len, start = obj+0x74 on the first shown tick;
    animate=False is the frozen state (not in sight, or the "Object
    animations" option off, DAT_005f17ec).
    """
    kind = "structures"

    def __init__(self, rec, sprites=None, paths=None, fs=None):
        super().__init__(record_name(rec), sprites, paths, fs)
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
        """Frame of piece `cell` at sequence value k (FUN_00461649).  The
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

    def __init__(self, rec, w=4, h=4, sprites=None, paths=None, fs=None):
        super().__init__(rec, sprites, paths, fs)
        self.w, self.h = w, h
        self.actions = {"bridge": Action("bridge", [0, 1, 2, 3] if rec["ID"] == BRIDGE14_ID else [0])}

    def bridge_piece(self, x, y, clock):
        w, h = self.w, self.h
        if self.rec["ID"] == BRIDGE14_ID:          # FUN_0046283c
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
        corner = {(0, 0): 0, (w - 1, 0): 2, (0, h - 1): 6, (w - 1, h - 1): 8}   # FUN_00462654
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


def structure_paths(rec, fs):
    root = join(STRUCTURES_DIR, rec["File"])
    return {"main": find(fs, root + ".256"), "main_b": find(fs, root + "b.256")}


def load_structure_set(sid, fs=None, records=None, **kw):
    fs = as_fs(fs)
    recs = records or load_structure_records(fs)
    rec = recs[int(sid)]
    cls = BridgeSet if rec.get("VariableSize") else StructureSet
    return cls(rec, paths=structure_paths(rec, fs), fs=fs, **kw)
