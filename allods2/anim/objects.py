"""Map objects (trees, bushes, stones, ...): objects.reg.

Spec: docs/formats/animation.md §1.2 (loader FUN_0047e4a0), §1.3 / §4.3
(draw inside the view draw FUN_00406fea, 0x408b24-0x409480).

Frame (all CONFIRMED):
- animated, when the sequence is not empty and the cell is fully visible
  (tile bits 0xc000): Index + seq[(clock + X + X*Y) mod len], X/Y = cell;
- otherwise Index;
- tile bit 0x2000 (burnt ground) with DeadObject != -1: frame 0 of the dead
  object's File;
- "Object animations" off (DAT_005fb974 == 0): frame 0 of the file, not
  Index (0x408d3c), a quirk for objects that share a file.
Placement: the anchor is the cell centre (32 X + 16, 32 Y + 16, minus the
relief height); top-left = anchor - ((CenterX - Width/2) + w/2,
(CenterY - Height/2) + h/2), always with the record of the object itself,
also when the dead object's frame is drawn.  Opaque blit with the file's own
palette (+0x14 with main+0x14), b.256 overlay at 50 % when Smoothing is on.
"""

import os

from ..common import find_file
from ..reg import load_reg
from ..units import center_anchor, expand_sequence
from .base import Action, AnimationSet, FrameRef, record_name

OBJECTS_DIR = "graphics/objects"
INT_KEYS = ("File", "Index", "Phases", "Width", "Height", "CenterX", "CenterY",
            "FireObject", "DeadObject")


def load_object_records(data_dir):
    """objects.reg records by ID with Parent inheritance (Parent = an ID;
    ints default to the parent's, empty AnimationTime/Frame come from the
    parent's section)."""
    reg = load_reg(os.path.join(data_dir, OBJECTS_DIR, "objects.reg"))
    files = reg["Files"].to_dict()
    out = {}
    for raw in reg.records("Object", "ObjectCount"):
        parent = out.get(raw.get("Parent", -1))
        r = {"ID": raw.get("ID", -1), "DescText": raw.get("DescText", "")}
        for k in INT_KEYS:
            r[k] = raw.get(k, parent[k] if parent else -1)
        for k in ("AnimationTime", "AnimationFrame"):
            v = raw.get(k)
            r[k] = v if v else (parent[k] if parent else [])
        r["seq"] = expand_sequence(r["AnimationTime"], r["AnimationFrame"])
        r["file"] = files.get("File%d" % r["File"], "") if r["File"] >= 0 else ""
        out[r["ID"]] = r
    return out


class ObjectSet(AnimationSet):
    """One objects.reg record.  Actions: "anim" (when it has a sequence),
    "still" (Index), "dead" (DeadObject's frame 0, when there is one).
    frame_at("anim", 0, clock, x=0, y=0) uses the view clock and the cell."""
    kind = "objects"

    def __init__(self, rec, dead=None, sprites=None, paths=None):
        super().__init__(record_name(rec, "file"), sprites, paths)
        self.rec, self.dead = rec, dead
        acts = []
        if rec["seq"]:
            acts.append(Action("anim", rec["seq"]))
        acts.append(Action("still", [0], end="hold"))
        if dead is not None:
            acts.append(Action("dead", [0], end="hold", source="dead"))
        self.actions = {a.name: a for a in acts}

    def anchor(self, w, h):
        r = self.rec
        return center_anchor(r["CenterX"], r["CenterY"], r["Width"], r["Height"], w, h)

    def frame_at(self, action, facing, tick, *, x=0, y=0, animate=True):
        r = self.rec
        if action == "dead":
            src, i, ph = "dead", 0, 0
        elif not animate:
            src, i, ph = "main", 0, 0
        elif action == "anim":
            ph = r["seq"][(tick + x + x * y) % len(r["seq"])]
            src, i = "main", r["Index"] + ph
        else:
            src, i, ph = "main", r["Index"], 0
        wh = self.size(src, i)
        return FrameRef(src, i, False, self.anchor(*wh) if wh else (0, 0), action, ph)

    def draw(self, canvas, ref, x, y, smoothing=True, palette=None):
        if self.blit_ref(canvas, ref, x, y, palette) and smoothing:
            pal = palette if palette is not None else self.sprites(ref.source).palette
            self.blit_overlay(canvas, ref, x, y, pal)


def object_paths(rec, data_dir, prefix="main"):
    root = os.path.join(data_dir, OBJECTS_DIR)
    return {prefix: find_file(root, rec["file"] + ".256"),
            prefix + "_b": find_file(root, rec["file"] + "b.256")}


def load_object_set(oid, data_dir, records=None):
    recs = records or load_object_records(data_dir)
    rec = recs[int(oid)]
    dead = recs.get(rec["DeadObject"]) if rec["DeadObject"] >= 0 else None
    paths = object_paths(rec, data_dir)
    if dead is not None:
        paths.update(object_paths(dead, data_dir, "dead"))
    return ObjectSet(rec, dead, paths=paths)
