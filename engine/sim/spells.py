"""Spell casting (phase I4): math, cast order, cast phases, carriers.

Facts: docs/data/spells.md 9, 9c (REA of the GOG exe, CONFIRMED unless tagged), docs/engine/combat.md 14.  Layer 4: reads and writes
`engine.world` only.
"""

import math
from dataclasses import dataclass

from allods2.formats import spelldefs

LIGHTNING, PRISMATIC_SPRAY = 10, 11             # `'\n'` / `'\v'` in FUN_00519998 / FUN_00519db8
SERVER_BOLT_TICKS, CLIENT_BOLT_TICKS = 10, 5    # missile carrier override (0x51be87) / client flight message (0x519998)


@dataclass(frozen=True)
class Wrapper:
    """The spell wrapper of a cast (`FUN_0051c391` spellbook entry or `FUN_0051906d` item wrapper): the spell number and, for a cast from an item
    (`unit+0x68 != 0`), the item's `castSpell=Name:N` count that replaces the unit-derived level."""
    number: int
    item_count: int = None


def distance(dx, dy):
    """`FUN_00516aae`: `__ftol(sqrt(dx^2 + dy^2))` of two positions in 1/256 cell."""
    return int(math.sqrt(dx * dx + dy * dy))


def client_flight_ticks(spell, dx, dy):
    """Flight time sent to the client (`FUN_00519998`): `distance / speed` for missile delivery, 5 for spells 10 and 11, 0 otherwise."""
    if spell.delivery != spelldefs.DELIVERY_MISSILE:
        return 0
    if spell.number in (LIGHTNING, PRISMATIC_SPRAY):
        return CLIENT_BOLT_TICKS
    return distance(dx, dy) // spell.speed


def flight_ticks(spell, dx, dy):
    """Flight time of the server's missile carrier (`FUN_00518d1e`: `(s16) distance / speed`; spells 10 and 11 are set to 10 afterwards by
    `FUN_00519db8`).  0 for a non-missile delivery."""
    if spell.delivery != spelldefs.DELIVERY_MISSILE:
        return 0
    if spell.number in (LIGHTNING, PRISMATIC_SPRAY):
        return SERVER_BOLT_TICKS
    return distance(dx, dy) // spell.speed


level_from = spelldefs.level_of                 # FUN_00519483 / FUN_00519db8: skill[sphere] - 30 + Mind, clamped 0..255


def wrapper_range(spell, wrapper, level):
    """Wrapper `+9`, the scaled range the approach test uses (`FUN_005195b1`): range + level / 30 (Teleport + level / 3)."""
    return spell.scaled(wrapper.item_count if wrapper.item_count is not None else level).max_range


def spell_record(spell, level):
    """The elemental part of a spell hit as an attack record: min' and spread' are bytes (`FUN_005195b1`), no physical part."""
    from .combatstats import AttackRecord
    sc = spell.scaled(level)
    return AttackRecord(elo=sc.damage_min & 0xFF, esp=sc.damage_spread & 0xFF, elem=spell.sphere)


def spell_damage(spell, level, block, rng, immune=False):
    """`FUN_0051e65b` -> `FUN_00516f6f` for a spell: the exe's own damage routine with an elemental-only record, so the draws are the exe's
    (the to-hit roll, then `min' + rand(0..spread')`, protection `ftol(x * (100 - p) / 100 + 0.75)`)."""
    from .combat import take_hit
    return take_hit(spell_record(spell, level), block, rng, immune=immune)


def recovery_ticks(base, hero_delay, complication, rng):
    """End of the release phase (`FUN_0050f12c` phase 5): `+0x135 + hero_delay + rand(0..3)`, plus the spell's `complication_level` for a
    learned spell (an item cast has cleared `+0x64`).  Byte-truncated by the caller."""
    return base + hero_delay + rng.rand(3) + complication
