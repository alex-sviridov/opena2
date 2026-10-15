"""Check every .alm Tiles block against the terrain strips.

    python tools/validate_terrain.py [INSTALL_DIR]

Byte accounting: the M7R container walks to EOF and the Tiles block is
exactly width·height u16. Then every cell must name an existing strip
(set 0..12, strip 0..3); cells whose row is past the end of their strip
are counted (the game reads past the bitmap there) and listed per map.
"""

import collections
import glob
import os
import sys

import numpy as np

from allods2.alm import load_alm
from allods2.graphics import terrain as tr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = os.path.join(ROOT, "samples", "Allods2_en_251005", "Allods2_en")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    base = argv[0] if argv else DEFAULT
    terrain = tr.TerrainSet.load(os.path.join(base, "data", "graphics", "terrain"))
    rows = np.zeros((16, 4), int)
    for (s, j), a in terrain.strips.items():
        rows[s, j] = a.shape[0] // tr.TILE
    stats = collections.Counter()
    bad_maps, past = [], []
    for path in sorted(glob.glob(os.path.join(base, "maps", "*.alm"))):
        try:
            m = load_alm(path)
            t = m.tiles.astype(int)
        except (ValueError, KeyError) as e:
            bad_maps.append("%s: %s" % (os.path.basename(path), e))
            continue
        s, j, r = (t & 0x1FFF) >> 6, (t >> 4) & 3, t & 0xF
        missing = (s >= tr.SETS).sum()
        over = (r >= rows[np.minimum(s, 15), j]).sum() - missing
        stats["maps"] += 1
        stats["cells"] += t.size
        stats["cells with dirt flag"] += int(((t & tr.DIRT_FLAG) != 0).sum())
        stats["cells on water sets"] += int(((s >= 8) & (s <= 11)).sum())
        stats["cells naming a missing set"] += int(missing)
        stats["cells past their strip"] += int(over)
        stats["other high bits set"] += int(((t & 0xC000) != 0).sum())
        if over:
            past.append("%s: %d" % (m.name, over))
    for k, v in stats.items():
        print("%-28s %d" % (k, v))
    if past:
        print("maps with cells past their strip:", ", ".join(past))
    for b in bad_maps:
        print(b)
    return 1 if bad_maps or stats["cells naming a missing set"] else 0


if __name__ == "__main__":
    sys.exit(main())
