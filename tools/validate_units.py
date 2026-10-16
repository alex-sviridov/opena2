"""Check units.reg against the unit sprite files.

    python tools/validate_units.py [DATA_DIR]

For each Unit<n>: the sprite file and b.256 exist, the frame count equals
the block layout (stand | move | attack | dying | bones-or-idle), and every
frame index the draw formulas can produce (all 16 facings, all sequence
values, death stages 1..4) is inside the file. Then every hero file
heroes*/<weapon>/sprites.256 against the type its folder maps to
(FUN_0046f688): stand + (move + attack + idle) per direction, plus the
dying and bones blocks only for unarmed / mage_st.
"""

import os
import sys

from allods2 import graphics as gfx
from allods2 import units as U
from allods2.common import DATA


def frames_used(t, td):
    used = set()
    for d in range(16):
        used.add(U.stand_frame(t, d)[0])
        if t.MovePhases > 0:
            for p in set(t.sequence("Move")) or {0}:
                used.add(U.move_frame(t, d, p)[0])
        if t.AttackPhases > 0:
            for p in set(t.sequence("Attack")) or {0}:
                used.add(U.attack_frame(t, d, p)[0])
        if t.IdlePhases:
            for p in set(t.sequence("Idle")) or {0}:
                used.add(U.idle_frame(t, d, p)[0])
        if td is not None and td.DyingPhases > 0:
            for s in range(td.DyingPhases):
                used.add(("dying", U.dying_frame(td, d, s)[0]))
            if not t.IdlePhases:
                for stage in range(2, 2 + max(td.BonePhases, 0)):
                    used.add(("dying", U.bones_frame(td, d, stage)[0]))
    return used


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    data = argv[0] if argv else DATA
    types = U.unit_types(data)
    ids = U.by_id(types)
    counts, problems = {}, []

    def count(t):
        p = t.sprite_paths(data)[0]
        if p not in counts:
            counts[p] = len(gfx.SpriteFile.load(p)) if os.path.isfile(p) and os.path.getsize(p) > 4 else None
        return counts[p]

    exact = 0
    for t in types:
        n = count(t)
        if not t.file or n is None:
            problems.append("Unit%d (ID %d): no sprite file (%r)" % (t.index, t.id, t.file))
            continue
        if not os.path.isfile(t.sprite_paths(data)[1]):
            problems.append("Unit%d: no b.256" % t.index)
        exact += n == U.expected_frames(t)
        if n != U.expected_frames(t):
            problems.append("Unit%d %s: %d frames, layout expects %d"
                            % (t.index, t.file, n, U.expected_frames(t)))
        td = ids.get(t.Dying)
        for f in frames_used(t, td):
            src, idx = (td, f[1]) if isinstance(f, tuple) else (t, f)
            m = count(src) if src.file else None
            if m is not None and idx >= m:
                problems.append("Unit%d: frame %d past %s (%d frames)" % (t.index, idx, src.file, m))
                break
    print("%d unit types, %d with the exact block layout" % (len(types), exact))
    heroes = hero_exact = 0
    for kind in ("heroes", "heroes_l"):
        base = os.path.join(data, U.UNITS_DIR, kind)
        for folder in sorted(os.listdir(base)):
            p = os.path.join(base, folder, "sprites.256")
            if not os.path.isfile(p):
                continue
            heroes += 1
            n, want = len(gfx.SpriteFile.load(p)), U.hero_expected_frames(ids[U.HERO_TYPES[folder]], folder)
            hero_exact += n == want
            if n != want:
                problems.append("%s/%s: %d frames, layout expects %d" % (kind, folder, n, want))
    print("%d hero files, %d with the exact block layout" % (heroes, hero_exact))
    for p in problems:
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
