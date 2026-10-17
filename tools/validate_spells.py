"""Check the spell definitions (docs/data/spells.md) against the whole install.

    python tools/validate_spells.py [INSTALL_DIR]

Checks: data.bin group 8 loads (34 records, 29 named, numbers = spells.SPELL_NAMES); every sphere/target/
delivery value is in range; every missile spell has its projectile record and every record loads; every
spell has a cast sound entry in sfx.reg whose .wav exists (the documented gaps aside); every `castSpell` /
`teachSpell` term of items and equipment strings, every monster spell slot and every `known_spells` bit
resolves to a spell; texts (spell.txt names, spells.txt descriptions) are present.
"""

import re
import sys

from allods2.anim import projectiles as P
from allods2.common import as_fs
from allods2.databin import databin
from allods2.formats import spelldefs as S, unitstats
from allods2.reg import load_reg
from allods2.spells import SPELL_NAMES

NO_SOUND = {3, 7}                       # sound ids 514, 522 have no sfx.reg entry (spec section 7)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    fs = as_fs(argv[0] if argv else None)
    db = databin(fs)
    table = S.load(fs)
    problems = []
    print("%d records, %d spells, %d empty" % (len(db.spells), len(table), table.extra_records))
    if len(table) != len(SPELL_NAMES) - 1:
        problems.append("spell count %d" % len(table))
    recs = P.load_projectile_records(fs)
    reg = load_reg("sfx/sfx.reg", fs)
    sfx = {int(e.name[3:]): reg.blob[e.a:e.a + e.b].split(b"\0")[0].decode()
           for e in reg.entries if re.fullmatch(r"Sfx\d+", e.name)}
    for d in table:
        if d.key != SPELL_NAMES[d.number]:
            problems.append("%s: key %s" % (d.name, d.key))
        if not (1 <= d.sphere <= 5 and d.target in (1, 2) and d.delivery in (1, 2)):
            problems.append("%s: sphere/target/delivery out of range" % d.name)
        if d.missile and d.effect_id not in recs:
            problems.append("%s: no projectile record %d" % (d.name, d.effect_id))
        for eid in (d.effect_id, d.hit_effect_id):
            if eid in recs:
                try:
                    P.load_projectile_set(eid, fs, recs)
                except Exception as e:                      # noqa: BLE001
                    problems.append("%s: projectile %d: %s" % (d.name, eid, e))
        cast = d.sound_ids[0]
        if cast not in sfx:
            if d.number not in NO_SOUND:
                problems.append("%s: no sound %d" % (d.name, cast))
        elif not fs.isfile("sfx/" + sfx[cast].replace("\\", "/") + ".wav"):
            problems.append("%s: sound file %s missing" % (d.name, sfx[cast]))
        if not d.display_name:
            problems.append("%s: no display name" % d.name)
    n = 0
    for group in ("items", "weapons", "shields", "armour"):
        for rec in getattr(db, group):
            for text in (e for e in rec.extra if isinstance(e, str)):
                for m in re.finditer(r"(?:cast|teach)Spell=([A-Za-z_]+)", text, re.I):
                    n += 1
                    if not table.lookup(m.group(1)):
                        problems.append("%s: unknown spell %s" % (rec.name, m.group(1)))
    slots = known = 0
    for u in unitstats.load(fs):
        f = u.fields
        for k in (1, 2, 3):
            v = f.get("spell_%d" % k, -1)
            if v > 0:
                slots += 1
                if not table.get(v):
                    problems.append("%s: spell slot %d" % (u.name, v))
        mask = f.get("known_spells", -1)
        if mask > 0:
            known += 1
            for b in range(1, 31):
                if mask >> b & 1 and not table.get(b):
                    problems.append("%s: known spell bit %d" % (u.name, b))
        for e in u.equipment:
            for m in re.finditer(r"castSpell=([A-Za-z_]+)", e):
                n += 1
                if not table.lookup(m.group(1)):
                    problems.append("%s: equipment spell %s" % (u.name, m.group(1)))
    print("%d castSpell/teachSpell terms, %d monster slots, %d units with a spell mask" % (n, slots, known))
    for p in problems:
        print(p)
    print("OK" if not problems else "%d problems" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
