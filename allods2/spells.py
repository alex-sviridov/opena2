"""Spell numbers and the effect / projectile ids derived from them.
Spec: docs/formats/palettes.md §7 "Effect ids"."""

# allods2.exe name table at 0x5f8f50, entries 0x32 + n.  n = spell.txt index + 1.
SPELL_NAMES = (
    "unused_spell_0", "fire_arrow", "fire_ball", "wall_of_fire",
    "protection_from_fire", "ice_missile", "poison_cloud", "blizzard",
    "protection_from_water", "acid_stream", "lightning", "prismatic_spray",
    "invisibility", "protection_from_air", "darkness", "light",
    "diamond_dust", "wall_of_earth", "stone_curse", "protection_from_earth",
    "bless", "haste", "control_spirit", "teleport", "heal", "summon",
    "drain_life", "shield", "curse", "slow",
)
SPELLS = {name: n for n, name in enumerate(SPELL_NAMES)}


def effect_id(spell, secondary=False):
    """Effect / projectile type id of a spell (FUN_00519db8): 2n + 8, or
    2n + 9 for the secondary projectile.  `spell` is a number or name."""
    n = SPELLS[spell] if isinstance(spell, str) else spell
    return 2 * n + 8 + (1 if secondary else 0)


def spell_of_effect(eid):
    """Inverse of effect_id: (spell name, secondary), or None for ids below
    10 (arrows, catapult shots, steam)."""
    n, odd = divmod(eid - 8, 2)
    if eid < 10 or n >= len(SPELL_NAMES):
        return None
    return SPELL_NAMES[n], bool(odd)
