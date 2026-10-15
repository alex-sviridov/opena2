"""Check every .png in the install against the rules a2mgr.dll applies.

    python tools/validate_png.py [DATA_DIR]

Equipment PNGs (graphics/equipment/...) are paper-doll layers: a2mgr draws
them only at 160 x 240 (FUN_10010d70) and looks them up as <prefix><id>.png
before <prefix><id>.256, so a numeric name must not also exist as .256.
Locale PNGs are a2mgr's own menu art (no size rule). Every file must decode.
"""

import collections
import glob
import os
import sys

from allods2 import graphics as gfx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_sprites import DEFAULT_DATA  # noqa: E402


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    data_dir = argv[0] if argv else DEFAULT_DATA
    stats = collections.Counter()
    problems = []
    for path in sorted(glob.glob(os.path.join(data_dir, "**", "*.png"), recursive=True)):
        rel = os.path.relpath(path, data_dir).replace(os.sep, "/")
        try:
            rgba = gfx.load_png(path)
        except OSError as e:
            problems.append("%s: %s" % (rel, e))
            continue
        if "/equipment/" not in rel:
            stats["locale/ui"] += 1
            continue
        h, w = rgba.shape[:2]
        stem = os.path.basename(path)[:-4]
        if (w, h) != (gfx.PAPERDOLL_W, gfx.PAPERDOLL_H):
            problems.append("%s: %dx%d, a2mgr would not draw it" % (rel, w, h))
        if not stem.isdigit():
            problems.append("%s: name is not a number" % rel)
        if os.path.exists(path[:-4] + ".256"):
            problems.append("%s: shadows %s.256" % (rel, stem))
        a = rgba[..., 3]
        stats["equipment"] += 1
        stats["  with partial alpha"] += bool(((a > 0) & (a < 255)).any())
    for k, v in stats.items():
        print("%-22s %d" % (k, v))
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
