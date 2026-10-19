"""Check the scenario sections 7, 10, 11, 12 (docs/formats/map.md part 6) on every campaign map of the install.

    python tools/validate_scenario.py [INSTALL_DIR]

Checks per map: every section parses and is consumed exactly; the three section 7 counts add up to the header's
`n_sec7`; instant / check ids are unique; every trigger reference names an existing record (else it is listed: the
compiler would map it to runtime index 0); every argument kind is 0..9; section 11 signposts name
an existing structure (types other than 0x46-0x4b are listed: the game ignores the record) and an instant position
inside the list; section 12 has exactly one leading default record.
Prints the kind histograms of instants and checks.
"""

import collections
import sys

from allods2.common import as_fs, campaign_maps
from allods2.formats import Map
from allods2.formats import scenario as S

POINTER_TYPES = range(0x46, 0x4C)


def check_map(m, problems, hist):
    name = m.name
    sc = m.scenario
    if len(sc.instants) + len(sc.checks) + len(sc.triggers) != m.header.n_sec7:
        problems.append("%s: section 7 counts do not add up to n_sec7 %d" % (name, m.header.n_sec7))
    ids = {}
    for what, recs in (("instant", sc.instants), ("check", sc.checks)):
        seen = [r.id for r in recs]
        if len(set(seen)) != len(seen):
            problems.append("%s: duplicate %s ids" % (name, what))
        ids[what] = set(seen)
        for r in recs:
            hist[what][r.type] += 1
            if any(not 0 <= k <= 9 for k in r.kinds):
                problems.append("%s: %s %d has an unknown argument kind %s" % (name, what, r.id, r.kinds))
    dangling = []
    for t in sc.triggers:
        if not t.active:
            hist["trigger"]["inactive"] += 1
            continue
        hist["trigger"]["once" if t.once else "repeating"] += 1
        for a, b in t.pairs:
            for c in (a, b) if a and b else ():
                if c not in ids["check"]:
                    dangling.append("%s: trigger %r names missing check %d" % (name, t.name, c))
        for i in t.instants:
            if i and i not in ids["instant"]:
                dangling.append("%s: trigger %r names missing instant %d" % (name, t.name, i))
    m.repops
    inns, shops, pointers = m.section11
    by_uid = {s.uid: s for s in m.structures}
    for p in pointers:
        s = by_uid.get(p.uid)
        if s is None:
            problems.append("%s: signpost record names missing uid %d" % (name, p.uid))
        elif s.type not in POINTER_TYPES:       # FUN_00561422 builds such a structure as a plain building: record unused
            dangling.append("%s: signpost record for uid %d of type %#x is ignored" % (name, p.uid, s.type))
        if not 0 <= p.instant < len(sc.instants):
            problems.append("%s: signpost uid %d instant position %d out of range" % (name, p.uid, p.instant))
    hist["sec11"]["inn"] += len(inns)
    hist["sec11"]["shop"] += len(shops)
    hist["sec11"]["pointer"] += len(pointers)
    default, zones = m.music
    if default is None or not default.is_default or any(z.is_default for z in zones):
        problems.append("%s: section 12 default record misplaced" % name)
    hist["sec12"]["zones"] += len(zones)
    return dangling


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    fs = as_fs(argv[0] if argv else None)
    problems, notes = [], []
    hist = collections.defaultdict(collections.Counter)
    maps = campaign_maps(fs)
    for path in maps:
        try:
            m = Map.load(path, fs)
            notes += check_map(m, problems, hist)
        except ValueError as e:
            problems.append("%s: %s" % (path, e))
    print("%d maps" % len(maps))
    for what in ("instant", "check"):
        print("%s kinds: %s" % (what, ", ".join("%#x x%d" % kv for kv in sorted(hist[what].items()))))
    for what in ("trigger", "sec11", "sec12"):
        print("%s: %s" % (what, dict(hist[what])))
    for n in notes:
        print("note:", n)
    for p in problems:
        print("PROBLEM:", p)
    print("OK" if not problems else "%d problems" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
