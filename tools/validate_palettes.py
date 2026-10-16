"""Find every palette in the install, parse it the way the game does, and
check the rules in docs/formats/palettes.md.

    python tools/validate_palettes.py [INSTALL_DIR]

Exit status 0 when every rule holds on every file.
"""

import collections
import sys

from allods2 import graphics as gfx
from allods2.common import as_fs


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    fs = as_fs(argv[0] if argv else None)
    files = collections.Counter()
    count = collections.Counter()
    distinct = collections.defaultdict(set)
    zero = collections.Counter()
    reserved = collections.Counter()
    problems = []
    for rel, kind, pals in gfx.find_palettes(fs):
        files[kind] += 1
        for p in pals:
            count[kind] += 1
            distinct[kind].add(p.rgb.tobytes())
            zero[kind] += not p.rgb.any()
            reserved[kind] += bool(p.reserved.any())
        problems += ["%s: %s" % (rel, b) for b in gfx.check_palette_file(rel, kind, pals, fs)]
    print("%-10s %6s %9s %9s %9s %9s" % ("source", "files", "palettes", "distinct", "all-zero", "rsvd!=0"))
    for kind in sorted(files):
        print("%-10s %6d %9d %9d %9d %9d" % (kind, files[kind], count[kind], len(distinct[kind]),
                                            zero[kind], reserved[kind]))
    every = set().union(*distinct.values()) if distinct else set()
    print("total      %6d %9d %9d" % (sum(files.values()), sum(count.values()), len(every)))
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
