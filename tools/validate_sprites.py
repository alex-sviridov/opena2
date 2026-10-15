"""Decode every sprite under a directory and report RLE stream consistency.

    python tools/validate_sprites.py [DATA_DIR]

A sprite is consistent when its decoder consumes exactly its data block.
DATA_DIR defaults to the game install under samples/.
"""

import collections
import glob
import os
import sys

from allods2 import graphics as gfx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_DATA = os.path.join(ROOT, "samples", "Allods2_en_251005", "Allods2_en", "data")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    data_dir = argv[0] if argv else DEFAULT_DATA
    stats = collections.Counter()
    problems = []
    for path in sorted(glob.glob(os.path.join(data_dir, "**", "*"), recursive=True)):
        if not path.lower().endswith((".256", ".16a", ".16")):
            continue
        try:
            sf = gfx.SpriteFile.load(path)
        except ValueError as e:
            problems.append("%s: %s" % (path, e))
            continue
        for i, s in enumerate(sf.sprites):
            used, size, _ = gfx.check_sprite(s, sf.kind)
            ok = used == size
            stats[(sf.kind, ok)] += 1
            if not ok:
                problems.append("%s[%d]: consumed %d of %d bytes" % (path, i, used, size))
    for (kind, ok), n in sorted(stats.items()):
        print("%-6s %-12s %d" % (kind, "consistent" if ok else "INCONSISTENT", n))
    for p in problems:
        print(p)
    return 1 if any(not ok for (_, ok) in stats) else 0


if __name__ == "__main__":
    sys.exit(main())
