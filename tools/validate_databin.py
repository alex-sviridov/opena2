"""Parse world/data/data.bin and check that every byte is consumed.

    python tools/validate_databin.py [DATA_DIR]

Prints the record count of each list, the parameter-array lengths seen per
list, and every modifier string (spells, special items) that does not
parse as a plain `stat=value[:time]` term.
"""

import collections
import sys

from allods2.common import DATA
from allods2.databin import databin, parse_modifier

LISTS = ("qualities", "materials", "stats", "armour", "shields", "weapons", "items",
         "monsters", "humans", "structures", "spells")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        db = databin(argv[0] if argv else DATA)
    except ValueError as e:
        print(e)
        return 1
    for name in LISTS:
        recs = getattr(db, name)
        sizes = collections.Counter(len(r.params) for r in recs if hasattr(r, "params"))
        print("%-10s %4d  params %s" % (name, len(recs), dict(sorted(sizes.items())) or "-"))
    odd = [(r.name, r.extra[-1]) for r in db.spells + db.items
           if r.extra and r.extra[-1] and parse_modifier(db, r.extra[-1]) is None]
    print("%d modifier strings not plain stat terms" % len(odd))
    for name, text in odd:
        print("  %s: %r" % (name, text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
