"""Open every .res archive of an install and check its byte accounting.

    python tools/validate_res.py [INSTALL_DIR]

INSTALL_DIR defaults to allods2.common.INSTALL.  Per archive: the directory
ends the file; every entry is reached exactly once from the root; file
ranges tile 0x18..directory with no gap or overlap; every walked path
resolves back to its own entry through the game's lookup (shadowed names
are listed); entry types seen.
"""

import glob
import os
import sys

from a2res import ResArchive
from allods2.common import INSTALL


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    install = argv[0] if argv else INSTALL
    paths = sorted(glob.glob(os.path.join(install, "*.[rR][eE][sS]")))
    if not paths:
        print("no .res files in %s" % install)
        return 1
    total_bad = 0
    for p in paths:
        try:
            arc = ResArchive(p)
        except ValueError as e:
            print("%s: %s" % (os.path.basename(p), e))
            total_bad += 1
            continue
        with arc:
            bad, odd, types, nfiles, nbytes = arc.check()
        print("%-13s %5d files %11d bytes, %5d entries, types %s%s" % (
            os.path.basename(p), nfiles, nbytes, len(arc.entries),
            " ".join("0x%x:%d" % kv for kv in sorted(types.items())),
            "" if not odd else ", unreachable: " + ", ".join(odd)))
        for b in bad:
            print("   BAD", b)
        total_bad += len(bad)
    print("%d archives, %d problems" % (len(paths), total_bad))
    return 1 if total_bad else 0


if __name__ == "__main__":
    sys.exit(main())
