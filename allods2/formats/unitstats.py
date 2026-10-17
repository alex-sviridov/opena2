"""Unit and monster type table: named views of the data.bin monster and human records.

Spec: docs/data/units.md.  Nothing is copied out of the game: the table is built from the
install's data.bin on load.  Values are raw params (-1 = "keep the constructor default",
as in the exe); every param of a record is kept in `raw`, so nothing is lost.
"""

import re
from dataclasses import dataclass

from ..databin import databin

MONSTER, HUMAN = "monster", "human"
KINDS = (MONSTER, HUMAN)
GROUP = {MONSTER: "monsters", HUMAN: "humans"}

# Column label (lower case) -> field name, per kind.  Labels come from data.bin itself
# (DataBin.columns); the mapping only renames them.
_COMMON = {
    "body": "body", "reaction": "reaction", "mind": "mind", "spirit": "spirit",
    "healthmax": "hp_max", "manamax": "mana_max", "speed": "speed",
    "rotationspeed": "turn_rate", "scanrange": "scan_range", "defence": "defence",
    "typeid": "unit_type", "face": "face", "attackchargetime": "windup",
    "attackrelaxtime": "recovery", "tokensize": "token_size", "movementtype": "movement_type",
    "dyingtime": "dying_time", "serverid": "server_id", "knownspells": "known_spells",
}


def field_name(label):
    """snake_case field name of a data.bin column label."""
    low = label.lower()
    if low in _COMMON:
        return _COMMON[low]
    s = re.sub(r"\(.*?\)", "", low)                     # "Skill.Blade (Fire)" -> "skill.blade"
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return {"hp_regeneraton": "hp_regen", "mp_regeneraton": "mana_regen",
            "physicalmin": "damage_min", "physicalmax": "damage_max",
            "attackkind": "damage_kind", "tohit": "to_hit", "absorbtion": "absorption",
            "xpvalue": "xp",
            # loot (docs/data/units.md): chance 0..100, gold = base + rand(0..spread)
            "treasure_1_gold": "gold_chance", "treasuremin_1": "gold_base",
            "treasuremax_1": "gold_spread", "treasure_2_item": "item_chance",
            "treasuremin_2": "item_value_min", "treasuremax_2": "item_value_max",
            "treasuremask_2": "item_flags"}.get(s, s)


@dataclass(frozen=True)
class UnitType:
    """One data.bin monster or human record.

    kind        "monster" (group 5) or "human" (group 6)
    index       1-based template index in its list (`creature+0xc`)
    name        template name (cp1251), e.g. "Goblin_Pike"
    server_id   the `serverID` column: the key a map unit's `server_id` is matched against
    unit_type   units.reg type id (`typeID` column; humans: the base id, gender added by the exe)
    fields      every other column by field name (see `field_name`), raw values
    equipment   the trailing CStrings (monster 2, human 10 equipment strings)
    raw         all params in file order
    """
    kind: str
    index: int
    name: str
    server_id: int
    unit_type: int
    fields: dict
    equipment: tuple
    raw: tuple

    def __getattr__(self, key):
        try:
            return self.fields[key]
        except KeyError:
            raise AttributeError(key) from None

    def get(self, key, default=None):
        return self.fields.get(key, default)

    def to_dict(self):
        return {"kind": self.kind, "index": self.index, "name": self.name,
                "server_id": self.server_id, "unit_type": self.unit_type,
                "fields": dict(self.fields), "equipment": list(self.equipment)}


class UnitTable:
    """All unit types, looked up by (kind, server_id)."""

    def __init__(self, types):
        self.types = tuple(types)
        self._by_id = {(t.kind, t.server_id): t for t in self.types}

    def __len__(self):
        return len(self.types)

    def __iter__(self):
        return iter(self.types)

    def lookup(self, human, server_id):
        """The type a section 6 record (`is_human`, `server_id`) is built from, or None."""
        return self._by_id.get((HUMAN if human else MONSTER, server_id))

    def of_kind(self, kind):
        return [t for t in self.types if t.kind == kind]

    def to_dict(self):
        return {"units": [t.to_dict() for t in self.types]}


def build(db):
    """UnitTable of a DataBin.  Records without params (the editor's empty slots) are skipped;
    the first record of a `server_id` wins (the install has no duplicates)."""
    types, seen = [], set()
    for kind in KINDS:
        group = GROUP[kind]
        names = [field_name(c) for c in db.columns(group)]
        for i, rec in enumerate(getattr(db, group), 1):
            if not rec.params:
                continue
            f = {n: v for n, v in zip(names, rec.params)}
            sid = f["server_id"]
            if (kind, sid) in seen:
                continue
            seen.add((kind, sid))
            types.append(UnitType(kind, i, rec.name, sid, f["unit_type"],
                                  {k: v for k, v in f.items() if k not in ("server_id", "unit_type")},
                                  tuple(rec.extra), tuple(rec.params)))
    return UnitTable(types)


def load(fs=None):
    """The unit table of an install (`fs`: game file system)."""
    return build(databin(fs))
