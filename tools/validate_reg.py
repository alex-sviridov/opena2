"""Parse every .reg file and check its byte accounting.

    python tools/validate_reg.py [DATA_DIR]

Header + 32·N directory + u32 blob size + blob must equal the file size;
every section's child range and every string/array blob range must be in
bounds; names with leading/trailing spaces (unreachable by the game's
lookup) are listed.
"""

import collections
import glob
import os
import sys

from allods2.common import DATA
from allods2.reg import T_FLOAT, T_INTS, T_STRING, load_reg


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    data = argv[0] if argv else DATA
    bad, types, odd = [], collections.Counter(), []
    paths = sorted(glob.glob(os.path.join(data, "**", "*.reg"), recursive=True))
    for p in paths:
        rel = os.path.relpath(p, data)
        try:
            r = load_reg(p)
        except ValueError as e:
            bad.append("%s: %s" % (rel, e))
            continue
        n = len(r.entries)
        for e in [r.root_entry] + r.entries:
            types[e.type] += 1
            if e.is_section and e.a + e.b > n:
                bad.append("%s: section %r children past directory" % (rel, e.name))
            if e.kind in (T_STRING, T_INTS) and e.a + e.b > len(r.blob):
                bad.append("%s: %r blob range past end" % (rel, e.name))
            if e.kind not in (0, 1, 2, 3, T_FLOAT, T_INTS):
                bad.append("%s: %r unknown type %d" % (rel, e.name, e.type))
            if e.name != e.name.strip():
                odd.append("%s: %r" % (rel, e.name))
    print("%d files, entry types %s" % (len(paths), dict(sorted(types.items()))))
    for o in odd:
        print("unreachable name", o)
    for b in bad:
        print(b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
