"""Decode every sprite under a directory and report RLE stream consistency.

    python tools/validate_sprites.py [INSTALL_DIR]

A sprite is consistent when its decoder consumes exactly its data block.
Reads the install's .res archives (default: allods2.common.INSTALL).
"""

import collections
import sys

from allods2 import graphics as gfx
from allods2.common import as_fs


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    fs = as_fs(argv[0] if argv else None)
    stats = collections.Counter()
    problems = []
    for path in fs.files():
        if not path.lower().endswith((".256", ".16a", ".16")):
            continue
        try:
            sf = gfx.SpriteFile.load(path, fs)
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
