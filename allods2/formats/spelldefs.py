"""Spell definitions: the 29 spells of data.bin group 8 (`spells`) with their display texts and the
exe's level scaling rules.

Spec: docs/data/spells.md.  Nothing is copied out of the game: the table is built from the install's
data.bin (and main/text/spell.txt, spells.txt for display names and descriptions) on load.  The raw
params are kept in `raw`; `fields` names them (-1 = "not set").  Rounding follows the exe: `__ftol`
truncates toward zero; byte stores wrap mod 256 (not reproduced: the data stays far below).
"""

import math
import re
from dataclasses import dataclass, field

from ..databin import databin, parse_modifier
from ..spells import SPELL_NAMES, effect_id

# data.bin params by index (docs/data/spells.md section 2); P is the index into `raw`.
FIELDS = ("complication_level", "mana_cost", "sphere", "item", "target", "delivery", "max_range", "speed",
          "distribution", "radius", "area_affect", "area_duration", "area_frequency", "apply_method",
          "duration", "frequency", "damage_min", "damage_max", "defensive", "skill_offset", "scroll_cost",
          "book_cost")
P = {n: i for i, n in enumerate(FIELDS)}
SPHERES = ("", "fire", "water", "air", "earth", "astral")      # sphere 1..5, 0 = none (FUN_00543040 ff.)
TARGET_UNIT, TARGET_POINT = 1, 2                                # `target` (FUN_00519441)
DELIVERY_INSTANT, DELIVERY_MISSILE = 1, 2                       # `delivery` (FUN_00519998)
DIST_SINGLE, DIST_DIAMOND, DIST_WALL, DIST_FIELD = 1, 3, 4, 5   # `distribution` (FUN_00519db8, FUN_00518024)
TEXT_TICKS = 16                                                 # modifier / duration time unit: 16 ticks
HEAL, DRAIN_LIFE = 24, 26                                       # excluded from the damage-carrier branch
TELEPORT, STONE_CURSE, INVISIBILITY = 23, 18, 12
DESCRIPTION_ALIAS = {"animate dead": "animated dead"}        # spell.txt vs spells.txt spelling (INFERRED pairing)
TEXT_FILES = ("main/text/spell.txt", "main/text/spells.txt")

# Spell numbers handled by their own case of the effect switch (FUN_00519db8); every other spell with
# damage uses the shared damage carrier.  Values name the handler for `SpellDef.kind`.
CASES = {4: "protection", 8: "protection", 13: "protection", 19: "protection",
         6: "poison_cloud", 12: "invisibility", 14: "darkness", 15: "light", 17: "wall_of_earth",
         18: "stone_curse", 20: "bless", 28: "curse", 21: "haste", 29: "slow", 22: "control_spirit",
         23: "teleport", 24: "heal", 25: "summon", 26: "drain_life", 27: "shield"}


def ftol(x):
    """The exe's `__ftol`: truncation toward zero."""
    return int(x)


def level_of(skill, mind):
    """Spell level of a caster (FUN_00519db8, FUN_00519483): school skill - 30 + Mind, clamped to
    0..255.  Item casts use the item's `castSpell` count instead."""
    return max(0, min(255, skill - 30 + mind))


@dataclass(frozen=True)
class Scaled:
    """Level-scaled values of one spell (`SpellDef.scaled`, FUN_005195b1)."""
    level: int
    max_range: int
    damage_min: int
    damage_spread: int
    duration: int          # ticks (u16)


@dataclass(frozen=True)
class SpellDef:
    """One data.bin spell record.

    number   1-based = record position = `allods2.spells.SPELLS` number
    name     data.bin name ("Fire Arrow"); display_name from spell.txt ("Stone Missile" for Diamond Dust)
    fields   the 22 params by `FIELDS`; also readable as attributes
    modifier_text  the trailing CString (quotes cut); modifiers its comma-separated `name=value[:time]` terms
    """
    number: int
    name: str
    display_name: str
    fields: dict
    modifier_text: str = ""
    modifiers: tuple = ()
    kind_text: str = ""
    description: str = ""
    raw: tuple = ()

    def __getattr__(self, key):
        try:
            return self.__dict__["fields"][key]
        except KeyError:
            raise AttributeError(key) from None

    @property
    def key(self):
        """allods2.spells name ("fire_arrow")."""
        return SPELL_NAMES[self.number]

    @property
    def element(self):
        return SPHERES[self.sphere]

    @property
    def missile(self):
        return self.delivery == DELIVERY_MISSILE

    @property
    def targets_unit(self):
        return self.target == TARGET_UNIT

    @property
    def has_damage(self):
        return self.damage_min + self.damage_max > 0

    @property
    def effect_id(self):
        """Unit-attached / flight effect id 2n + 8."""
        return effect_id(self.number)

    @property
    def hit_effect_id(self):
        """Secondary effect id 2n + 9 (impact, area)."""
        return effect_id(self.number, True)

    @property
    def sound_ids(self):
        """sfx.reg ids `500 + effect id` (cast) and `500 + hit effect id`."""
        return 500 + self.effect_id, 500 + self.hit_effect_id

    @property
    def handler(self):
        """Which branch of the effect switch serves the spell: a name of `CASES`, "damage" (the shared
        damage carrier: damage params set and not Heal / Drain Life) or "none"."""
        if self.has_damage and self.number not in (HEAL, DRAIN_LIFE):
            return "damage"
        return CASES.get(self.number, "none")

    def scaled(self, level):
        """Range, damage and duration at spell `level` (FUN_005195b1).  Damage is
        `min' + rand(0..spread')` per hit, duration in ticks."""
        level &= 0xFF
        rng = self.max_range
        if self.number == TELEPORT:
            rng += level // 3
        elif rng:
            rng += level // 30
        m = level / 30.0 + 1.0
        lo = ftol(self.damage_min * m) if self.damage_min > 0 else 0
        spread = ftol(self.damage_max * m - lo) if self.damage_max > 0 else 0
        if self.duration > 0:
            if self.number == INVISIBILITY:
                dur = level << 4
            elif self.number == STONE_CURSE:
                dur = level * 15 * 16 * 2 // 100
            else:
                dur = ftol(self.duration * 1.1 ** level * TEXT_TICKS)
        elif self.area_duration > 0:
            dur = (self.area_duration << 4) + (level << 4) // 10
        else:
            dur = 0
        return Scaled(level, rng, lo, spread, dur)

    def to_dict(self):
        return {"number": self.number, "name": self.name, "display_name": self.display_name,
                "key": self.key, "element": self.element, "handler": self.handler,
                "fields": dict(self.fields), "modifier_text": self.modifier_text,
                "modifiers": [{"kind": m.kind, "value": m.value, "mode": m.mode, "time": m.time}
                              for m in self.modifiers],
                "kind_text": self.kind_text, "description": self.description,
                "effect_id": self.effect_id, "hit_effect_id": self.hit_effect_id}


def damage_taken(rolled, protection):
    """Elemental damage after the target's protection percent (FUN_00516f6f):
    `ftol(rolled * (100 - protection) / 100 + 0.75)`, never below 0."""
    if protection:
        rolled = ftol(rolled * (100 - protection) / 100.0 + 0.75)
        rolled = max(rolled, 0)
    return rolled


class SpellTable:
    """All spell definitions, indexed by number (1-based) and name."""

    def __init__(self, defs, extra_records=0):
        self.defs = tuple(defs)
        self.extra_records = extra_records        # empty trailing records (31..34), no name
        self._by_number = {d.number: d for d in self.defs}
        self._by_name = {}
        for d in self.defs:
            self._by_name[d.name.lower()] = d
            self._by_name[d.key] = d

    def __len__(self):
        return len(self.defs)

    def __iter__(self):
        return iter(self.defs)

    def get(self, number):
        return self._by_number.get(number)

    def lookup(self, name):
        """By data.bin name, `castSpell=` form ("Fire_Arrow") or `allods2.spells` key; None if unknown."""
        n = name.strip().lower().replace(" ", "_")
        return self._by_name.get(n) or self._by_name.get(n.replace("_", " "))

    def of_sphere(self, sphere):
        return [d for d in self.defs if d.sphere == sphere]

    def to_dict(self):
        return {"spells": [d.to_dict() for d in self.defs], "empty_records": self.extra_records}


def parse_modifiers(db, text):
    """The terms of a spell's modifier text: quotes cut, split at commas; terms the plain parser does
    not accept (`Invisibility = ON`) are dropped (the exe special-cases the spell)."""
    out = []
    for part in text.strip().strip('"').split(","):
        m = parse_modifier(db, part) if part.strip() else None
        if m is not None:
            out.append(m)
    return tuple(out)


def build(db, texts=None):
    """SpellTable of a DataBin.  `texts` = (spell.txt lines, spells.txt lines) or None.  Records without
    a name (the 5 trailing ones) are counted in `extra_records` and left out."""
    names, descs = texts or ((), ())
    by_name = {}
    for line in descs:
        head, _, body = line.partition("#")
        m = re.match(r"(.*?)\s*\(([^)]*)\)\s*$", head)
        if m and body:
            by_name[m.group(1).strip().lower()] = (m.group(2), body.strip())
    defs, empty = [], 0
    for n, rec in enumerate(db.spells, 1):
        if not rec.name or not rec.params:
            empty += 1
            continue
        text = rec.extra[0] if rec.extra else ""
        disp = names[n - 1].strip() if n - 1 < len(names) and names[n - 1].strip() else rec.name
        kind, desc = by_name.get(DESCRIPTION_ALIAS.get(disp.lower(), disp.lower()), ("", ""))
        defs.append(SpellDef(n, rec.name, disp, dict(zip(FIELDS, rec.params)), text.strip().strip('"'),
                             parse_modifiers(db, text), kind, desc, tuple(rec.params)))
    return SpellTable(defs, empty)


def load_texts(fs):
    """(spell.txt lines, spells.txt lines) decoded as cp1251, ((), ()) when a file is missing.  Line k
    of spell.txt names spell k + 1; spells.txt lines are `Name (Type)#Description` matched by name."""
    out = []
    for p in TEXT_FILES:
        try:
            out.append(bytes(fs.read(p)).decode("cp1251").split("\r\n"))
        except (OSError, KeyError, FileNotFoundError):
            out.append([])
    return tuple(out)


def load(fs=None):
    """The spell table of an install (`fs`: game file system), texts included."""
    from ..common import as_fs
    fs = as_fs(fs)
    return build(databin(fs), load_texts(fs))
