"""Check the animation API against the whole install (animation.md §5.1):
every set loads, every action/facing/tick gives a valid frame and draws,
and every multi-frame sprite file is used by a set or listed in
allods2.anim.coverage.EXCLUSIONS.

    .venv/bin/python tools/validate_anim.py [DATA_DIR] [--no-draw] [-v]
"""

import argparse
import collections
import sys
import time

from allods2.anim.coverage import KNOWN_OUT_OF_RANGE, verify
from allods2.common import DATA


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("data", nargs="?", default=DATA)
    ap.add_argument("--no-draw", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.time()
    r = verify(a.data, draw=not a.no_draw)
    print("sets %d, frame requests %d, frames drawn %d (%.1f s)" % (r.sets, r.refs, r.drawn, time.time() - t0))
    print("multi-frame sprite files %d: reached %d, excluded %d, unreached %d"
          % (r.multi, r.multi - len(r.excluded) - len(r.unreached), len(r.excluded), len(r.unreached)))
    for k, n in r.out_of_range.items():
        print("  known out of range: %s (%d requests) - %s" % (k, n, KNOWN_OUT_OF_RANGE[k]))
    cats = collections.Counter(c for _, _, c, _ in r.excluded)
    print("  excluded by category: " + ", ".join("%s %d" % kv for kv in sorted(cats.items())))
    if a.verbose:
        for rel, n, c, why in r.excluded:
            print("    %-45s %4d  %-12s %s" % (rel, n, c, why))
    for key, m in r.errors:
        print("ERROR %s: %s" % (key, m))
    for rel, n in r.unreached:
        print("UNREACHED %s (%d frames)" % (rel, n))
    for pat in r.stale:
        print("STALE exclusion %s" % pat)
    print("OK" if r.ok else "FAILED")
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main())
