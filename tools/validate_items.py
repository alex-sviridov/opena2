"""Check the item definitions (docs/data/items.md) against the whole install.

    python tools/validate_items.py [INSTALL_DIR]

Checks: every data.bin item record loads; every itemname.bin code resolves, is allowed by its class's
quality/material masks, has an inventory icon, a display name, and (itemname.pkt) the price and base
stats the formulas give; every item code of the 46 campaign maps resolves and every section 9 stat id
is a known stat; every monster / human equipment string resolves (the documented exclusion aside).
"""

import struct
import sys

from allods2.common import as_fs, campaign_maps
from allods2.databin import databin
from allods2.formats import Map, itemdefs as I
from allods2.formats.entities import decode_item

EQUIPMENT_EXCLUDED = {"Leather Gauntless"}      # a typo in data.bin: the exe discards it ("Invalid armor")


def packet_pairs(it):
    """The (stat id -> value) pairs itemname.pkt lists for a class item."""
    s, out = it.stats, {}
    if it.defn.kind == I.WEAPON:
        for k, v in ((13, s.damage_min), (14, s.damage_spread), (12, s.to_hit), (15, s.defence)):
            if v > 0:
                out[k] = v
        if s.damage_min and s.range > 1:
            out[38] = s.range
    else:
        for k, v in ((15, s.defence), (16, s.absorption)):
            if v > 0:
                out[k] = v
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    fs = as_fs(argv[0] if argv else None)
    table = I.load(fs)
    problems = []
    print("%d definitions: %s" % (len(table), ", ".join("%d %s" % (len(table.of_kind(k)), k) for k in I.KINDS)))
    packets = I.load_packets(fs)
    for p in packets:
        it = table.resolve(p.code)
        if it is None:
            problems.append("packet %04x does not resolve" % p.code)
            continue
        d = it.defn
        if d.kind != I.SPECIAL and not d.allows(it.quality, it.material):
            problems.append("%s: quality %d / material %d not allowed by its masks" % (d.name, it.quality, it.material))
        if not fs.isfile(I.icon_path(p.code)):
            problems.append("%04x %s: no icon %s" % (p.code, d.name, I.icon_path(p.code)))
        if table.name_of(p.code) is None:
            problems.append("%04x %s: no display name" % (p.code, d.name))
        if d.kind != I.SPECIAL:
            if it.stats.price != p.price:
                problems.append("%s: price %d, packet %d" % (d.name, it.stats.price, p.price))
            if packet_pairs(it) != dict(p.pairs):
                problems.append("%s: stats %s, packet %s" % (d.name, packet_pairs(it), dict(p.pairs)))
    print("%d packets, %d display names" % (len(packets), len(table.names)))
    codes = set()
    ids = set()
    for mp in campaign_maps(fs):
        m = Map.load(mp, fs)
        for g in m.item_groups:
            for mem in g.members:
                ic = decode_item(mem.code)
                codes.add(mem.code & 0xFFFF)
                if ic is None or table.lookup(ic) is None:
                    problems.append("%s: item code %04x does not resolve" % (mp, mem.code & 0xFFFF))
        recs = m.item_records
        for g in m.item_groups:
            for mem in g.members:
                r = recs[mem.record - 1] if mem.record else None
                if r is None or r.a or r.b:               # unclaimed records are spot payloads (map.md)
                    continue
                for sid, _ in r.props:
                    ids.add(sid)
                    if not 0 < sid < len(table.stats) or not table.stats[sid].name:
                        problems.append("%s: unknown stat id %d" % (mp, sid))
    print("%d distinct map item codes, stat ids %s" % (len(codes), sorted(ids)))
    db = databin(fs)
    n = 0
    for group in ("monsters", "humans"):
        for rec in getattr(db, group):
            for k, text in enumerate(rec.extra):
                if text.strip() and text.strip() not in EQUIPMENT_EXCLUDED:
                    n += 1
                    if table.parse_equipment(text, k if group == "humans" else None) is None:
                        problems.append("%s: equipment %r does not resolve" % (rec.name, text))
    print("%d equipment strings" % n)
    for p in problems:
        print(p)
    print("OK" if not problems else "%d problems" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
