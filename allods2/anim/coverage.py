"""Whole-install check of the animation API (animation.md §5.1).

verify(data_dir) loads every set anim.all_keys names, asks every action
for every facing and tick (one pass plus a tail past the end), checks each
FrameRef and draws it, then compares the sprite files the sets read with
every multi-frame sprite file under graphics/.  A file no set reads must
match an EXCLUSIONS entry, and every entry must match at least one file,
so the list cannot go stale.
"""

import fnmatch
import os
from dataclasses import dataclass, field

from ..graphics import Canvas, SpriteFile
from . import all_keys, load_set
from .base import FACINGS

ENDS = {"loop", "idle", "hold", "once"}
CLOCKS = {"tick", "distance", "ms"}
TAIL = 8                     # ticks asked past the end of each action, except
                             # "once" ones: the object is gone after its lifetime

# Multi-frame sprite files no set reads: (glob under graphics/, lower case,
# category, reason).  Categories: "not animated" (sheets whose frame is
# picked by something other than time), "never loaded" (the game opens no
# such path), "empty" (0-byte files).
EXCLUSIONS = (
    ("font[1-4]/font[1-4].16", "not animated", "glyph sheets (fonts.md)"),
    ("font4/font4.16a", "not animated", "glyph sheet (fonts.md)"),
    ("interface/lm.256", "not animated", "UI widget sheet, drop-shadow blits (sprites.md)"),
    ("interface/radiob.256", "not animated", "UI widget sheet: radio button states (sprites.md)"),
    ("interface/scrlbars.256", "not animated", "UI widget sheet: scroll bar parts (sprites.md)"),
    ("interface/subobj.256", "not animated", "UI widget sheet, FUN_004478af (palettes.md §5)"),
    ("backpack/sprites.256", "not animated",
     "dropped sack: frame = obj+0x24 (0-5), no clock read; draw 0x46647f (animation.md §5.1)"),
    ("backpack/spritesb.256", "not animated", "its smoothing overlay"),
    ("cursors/attack.256", "never loaded", "not in the cursor table FUN_00480f17 (animation.md §4.8)"),
    ("cursors/pickup.256", "never loaded", "not in the cursor table FUN_00480f17 (animation.md §4.8)"),
    ("projectiles/firebolt/sprites.256", "never loaded", "firebolt has A16 = 1, the .16a is read (sprites.md)"),
    ("projectiles/firebolt/spritesb.256", "never loaded", "same (sprites.md)"),
    ("projectiles/diamonddust/sprites.16a", "never loaded",
     "no projectiles.reg record; the name is in no binary (animation.md §5.1)"),
    ("projectiles/freeze/sprites.16a", "never loaded", "same"),
    ("projectiles/smallxpl/sprites.16a", "never loaded", "same"),
    ("units/humans/swordsman/swordsman.256", "never loaded",
     "Unit0 key 'File0 ' has a trailing space (units.md, animation.md §2.5)"),
    ("units/humans/swordsman/swordsmanb.256", "never loaded", "same"),
    ("cursors/move.256", "empty", "0 bytes (sprites.md)"),
    ("cursors/patrol.256", "empty", "0 bytes (sprites.md)"),
    ("cursors/cast.256", "empty", "0 bytes (sprites.md)"),
    ("cursors/defend.256", "empty", "0 bytes (sprites.md)"),
    ("equipment/[fm]fighter/primary/0[01]05002.256", "empty", "0 bytes (sprites.md)"),
)

# Sets that ask for frames past the end of their file (the game draws nothing).
KNOWN_OUT_OF_RANGE = {
    "2": "Unit33: Flip file under a non-Flip type (animation.md §2.5)",
}


@dataclass
class Report:
    sets: int = 0
    refs: int = 0
    drawn: int = 0
    errors: list = field(default_factory=list)        # (key, message)
    out_of_range: dict = field(default_factory=dict)  # key -> count, documented ones only
    reached: set = field(default_factory=set)         # rel paths under graphics/
    unreached: list = field(default_factory=list)     # (rel, frames) not reached, not excluded
    excluded: list = field(default_factory=list)      # (rel, frames, category, reason)
    stale: list = field(default_factory=list)         # EXCLUSIONS patterns matching nothing
    multi: int = 0                                    # multi-frame (or empty) sprite files

    @property
    def ok(self):
        return not (self.errors or self.unreached or self.stale)


def _rel(path, gdir):
    return os.path.relpath(os.path.realpath(path), os.path.realpath(gdir)).replace(os.sep, "/").lower()


def sprite_files(data_dir):
    """[(rel, frames)] of every sprite file under graphics/ with more than
    one frame, plus 0-byte ones (frames = 0); rel lower case."""
    gdir = os.path.join(data_dir, "graphics")
    out = []
    for root, _, files in os.walk(gdir):
        for f in files:
            if not f.lower().endswith((".256", ".16", ".16a")):
                continue
            p = os.path.join(root, f)
            if os.path.getsize(p) == 0:
                out.append((_rel(p, gdir), 0))
                continue
            n = len(SpriteFile.load(p))
            if n > 1:
                out.append((_rel(p, gdir), n))
    return sorted(out)


def check_set(aset, key, report, draw=True):
    """Drive one set; append problems to report.errors."""
    err = lambda m: report.errors.append((key, m))
    if not aset.actions:
        err("no actions")
    facings = list(FACINGS) if len(aset.preview_facings) > 1 else list(aset.preview_facings)
    oor = 0
    for name, a in aset.actions.items():
        if not a.phases:
            err("%s: no phases" % name)
        if a.end not in ENDS or a.clock not in CLOCKS:
            err("%s: end %r clock %r" % (name, a.end, a.clock))
        for ev, t in a.events.items():
            if not 0 <= t < a.ticks:
                err("%s: event %s at %d outside 0..%d" % (name, ev, t, a.ticks - 1))
        step = aset.preview_step_ms if a.clock == "ms" else 1
        for d in facings:
            for k in range(a.ticks + (0 if a.end == "once" else TAIL)):
                ref = aset.frame_at(name, d, k * step)
                report.refs += 1
                if not all(isinstance(v, int) for v in ref.hotspot):
                    err("%s d%d t%d: hotspot %r" % (name, d, k, ref.hotspot))
                for p in aset.blits(ref):
                    if aset.sprites(p.source) is None:
                        err("%s d%d t%d: source %r" % (name, d, k, p.source))
                    elif not 0 <= p.index < aset.count(p.source):
                        oor += 1
                aset.extent(ref)
    if oor:
        if str(key) in KNOWN_OUT_OF_RANGE:
            report.out_of_range[str(key)] = oor
        else:
            err("%d frame requests past the end of their file" % oor)
    elif str(key) in KNOWN_OUT_OF_RANGE:
        err("listed in KNOWN_OUT_OF_RANGE but in range")
    if draw:
        cv = Canvas(320, 320)
        for name in aset.actions:
            for d in aset.preview_facings:
                for ref, _ in aset.preview_clip(name, d):
                    aset.draw(cv, ref, 160, 200)
                    report.drawn += 1
        if getattr(aset, "has_trail", False):
            pts = []
            for k in range(8):
                aset.record_trail(pts, 100 * 8 + 40 * k, 120 * 8)
            aset.draw_trail(cv, pts, 0, 0)
            report.drawn += len(pts)


def verify(data_dir, draw=True):
    report = Report()
    gdir = os.path.join(data_dir, "graphics")
    for cls, keys in all_keys(data_dir).items():
        for key in keys:
            try:
                aset = load_set(key, data_dir)
                report.sets += 1
                for src, p in aset.paths.items():
                    if isinstance(p, str) and os.path.isfile(p) and aset.sprites(src) is not None:
                        report.reached.add(_rel(p, gdir))
                check_set(aset, key, report, draw)
            except Exception as e:                    # noqa: BLE001 - reported, not hidden
                report.errors.append((key, "%s: %s" % (type(e).__name__, e)))
    used = set()
    for rel, n in sprite_files(data_dir):
        report.multi += 1
        if rel in report.reached:
            continue
        hit = next((x for x in EXCLUSIONS if fnmatch.fnmatchcase(rel, x[0])), None)
        if hit is None:
            report.unreached.append((rel, n))
        else:
            used.add(hit[0])
            report.excluded.append((rel, n, hit[1], hit[2]))
    report.stale = [x[0] for x in EXCLUSIONS if x[0] not in used]
    return report
