"""The data side of the spellbook window (phase J builds the window on top): the 24 spell slots, the enable mask of the spell buttons and the tooltip
fields of each spell.  No windows, no pygame.  Spec: docs/data/spells.md 9e (CONFIRMED in allods2.exe, routines in the comments).

The exe's view `FUN_004167c2` walks the selection and fills, per slot (0..23): the OR of the selected objects' slot masks (`view+0x148`) and the tooltip arrays
that `FUN_004c628f` prints.  The slot of a spell is its position in the byte table `0x5f8124` (`spelldefs.SPELLS_TXT_ORDER`)."""

from dataclasses import dataclass, field

from allods2.formats import spelldefs
from engine.sim import spells

SLOT_SPELLS = spelldefs.SPELLS_TXT_ORDER     # slot -> spell number (table 0x5f8124); spells 9, 14, 15, 28, 29 have no slot
SLOTS = len(SLOT_SPELLS)

# main.txt line numbers of the tooltip labels (`FUN_0041f350(k)`, FUN_004c628f)
L_MANA, L_DAMAGE, L_RANGE, L_DURATION = 0x75, 0x76, 0x7b, 0x7c
L_SPEED, L_RESISTANCE, L_SIGHT, L_MAX_PROB, L_RAYS, L_MIN_PROB, L_ABSORPTION = 0xb6, 0xb7, 0xb8, 0xb9, 0xba, 0xbb, 0xd9

HASTE, DARKNESS, LIGHT = 21, 14, 15


def spell_of_slot(slot):
    """The spell number of a button slot (0..23); the command's `button` is `slot + 1` (`FUN_004195fa`)."""
    return SLOT_SPELLS[slot]


def slot_of_spell(number):
    """The slot of a spell number, None for the five spells without a button."""
    try:
        return SLOT_SPELLS.index(number)
    except ValueError:
        return None


def slot_mask_of_book(book):
    """`obj+0x18` from `obj+0x1c` (client update, `0x4103b7`-`0x4103f2`): bit `n` (spell n) -> bit `slot_of_spell(n)`; spells without a slot drop out."""
    m = 0
    for slot, n in enumerate(SLOT_SPELLS):
        if (book >> n) & 1:
            m |= 1 << slot
    return m


def unit_slot_mask(u):
    """`obj+0x18` of a unit: the slots of the spells of its book (`spells.known_mask`).  No mana and no cost test: the exe's button mask follows the
    spellbook only (spells.md 9e.1)."""
    return slot_mask_of_book(spells.known_mask(u))


def scroll_slot_mask(u):
    """`view+0x150` of one unit (`FUN_004167c2` `0x4173c6`): the slot bits of the spells of its backpack scrolls (item class `0xe`, castSpell as the first
    effect; `FUN_0041eb20` = the item's spell number, 0 drops out).  The item-cast command is `CastScroll` (`0x25`, spells.md 9c.5)."""
    m = 0
    for it in u.pack:
        if it.cls == spells.SCROLL_CLASS and it.mods and it.mods[0][0] == spells.CAST_SPELL_MOD:
            slot = slot_of_spell(it.mods[0][1])
            if slot is not None:
                m |= 1 << slot
    return m


def selection_slot_mask(world, ids):
    """`view+0x148`: the OR of the slot masks of the living selected units (`FUN_004167c2`).  The caller passes the own selection; the exe fills
    `obj+0x18` only for the local player's units (`0x41037c`)."""
    m = 0
    for uid in ids:
        u = world.units.get(uid)
        if u is not None and u.hp > 0:
            m |= unit_slot_mask(u)
    return m


# ---- tooltip fields ------------------------------------------------------------------------------------------------------------------------------------

def _skill_and_mind(u, spell):
    """The client copy's bytes: school skill `obj+0x156+sphere` and Mind `obj+0x145`."""
    if u.human:
        skill = u.skills[spell.sphere] if len(u.skills) > spell.sphere else 0
    else:
        skill = spells.monster_skill(u.stats, spell.sphere)
    return skill & 0xFF, spells.mind_of(u) & 0xFF


def wrapper_level(skill, mind):
    """`FUN_0051951d(skill, mind)`: the byte `skill + mind - 30` **wraps** (8-bit add, no clamp) before `FUN_005195b1` scales the wrapper."""
    return (skill + mind - 30) & 0xFF


def helper_level(skill, mind):
    """The level handed to the helpers `0x5197e3`..`0x519966` (view local): `skill + mind - 30` clamped to 0..255."""
    return max(0, min(255, skill + mind - 30))


def haste_speed(level):
    """`FUN_00519966` (spell 21): `level / 15 + 1`."""
    return level // 15 + 1


def protection_value(level):
    """`FUN_0051989f` (spells 4, 8, 13, 19): `level / 2`."""
    return level // 2


def rays(level):
    """`FUN_005197e3` (spell 11): `min(7, level / 20 + 2)`."""
    return min(7, level // 20 + 2)


def bless_probability(level):
    """`FUN_00519837` (spell 20): `level * 4 / 5 + 20` (`spelldefs.bless_value`)."""
    return level * 4 // 5 + 20


def curse_probability(level):
    """`FUN_0051986b` (spell 28): `level * 4 / 5 + 20`.  Curse has no slot, so the spellbook never shows the row."""
    return level * 4 // 5 + 20


def light_sight(level):
    """`FUN_00519922` (spells 14, 15): `-1 - level / 30`.  Neither has a slot: the Sight row exists in the tooltip code but no spellbook entry fills it."""
    return -1 - level // 30


def shield_absorption(level):
    """`FUN_005198f1` (spell 27): `level / 10 + 3`."""
    return level // 10 + 3


PROTECTIONS = (4, 8, 13, 19)


def _helper(number, level):
    """(row label, value) of the spell-number helpers, None when the spell has none."""
    if number == HASTE:
        return L_SPEED, haste_speed(level)
    if number in PROTECTIONS:
        return L_RESISTANCE, protection_value(level)
    if number == 11:
        return L_RAYS, rays(level)
    if number == 20:
        return L_MAX_PROB, bless_probability(level)
    if number == 28:
        return L_MIN_PROB, curse_probability(level)
    if number in (DARKNESS, LIGHT):
        return L_SIGHT, light_sight(level)
    if number == 27:
        return L_ABSORPTION, shield_absorption(level)
    return None


@dataclass
class SpellEntry:
    """One spellbook entry for a selection: the party aggregate of the tooltip arrays of slot `slot` (`view+0x154..0x934`).

    damage_lo / damage_hi   sums over the party of `min'` and `min' + spread'` (`+0x154` / `+0x1b4`); None when the sum is 0 (no row)
    range_lo / range_hi     min / max of the wrapper range byte `+9` (`+0x214` / `+0x274`)
    duration_lo / _hi       min / max of the wrapper duration `+0x10` in ticks (`+0x394` / `+0x3f4`); Stone Curse has min 0
    extra                   (label line, lo, hi) of the one spell-number helper row (Speed, Resistance, Rays, probability, Absorption), None for no row
    """
    slot: int
    number: int
    name: str
    text: str
    description: str
    mana_cost: int
    damage_lo: int = 0
    damage_hi: int = 0
    range_lo: int = None
    range_hi: int = None
    duration_lo: int = None
    duration_hi: int = None
    extra: tuple = None
    members: int = 0
    _acc: dict = field(default_factory=dict, repr=False)

    @property
    def damage(self):
        return (self.damage_lo, self.damage_hi) if self.damage_hi else None

    @property
    def range(self):
        return (self.range_lo, self.range_hi) if self.range_hi else None

    @property
    def duration(self):
        return (self.duration_lo, self.duration_hi) if self.duration_hi else None

    # field names the task lists, by the label of the row
    @property
    def speed(self):
        return self.extra[1:] if self.extra and self.extra[0] == L_SPEED else None

    @property
    def resistance(self):
        return self.extra[1:] if self.extra and self.extra[0] == L_RESISTANCE else None

    @property
    def sight(self):
        return self.extra[1:] if self.extra and self.extra[0] == L_SIGHT else None

    @property
    def max_probability(self):
        return self.extra[1:] if self.extra and self.extra[0] == L_MAX_PROB else None

    @property
    def min_probability(self):
        return self.extra[1:] if self.extra and self.extra[0] == L_MIN_PROB else None

    @property
    def rays(self):
        return self.extra[1:] if self.extra and self.extra[0] == L_RAYS else None

    @property
    def absorption(self):
        return self.extra[1:] if self.extra and self.extra[0] == L_ABSORPTION else None


def _text_line(slot, spell, lines):
    """`FUN_00474733(slot)`: line `slot` of spells.txt (`Name (Type)#Description`); rebuilt from the table when the lines are not given."""
    if lines is not None and slot < len(lines):
        return lines[slot]
    return "%s (%s)#%s" % (spell.display_name, spell.kind_text, spell.description)


def spellbook(world, unit_ids, lines=None):
    """The entries of the spellbook for a selection (`unit_ids`, normally the own selection), ordered by slot: every slot whose spell some living
    unit of the selection knows and whose unit counts for the tooltip.  `lines` = the spells.txt lines (optional).  Empty without a spell table.

    The units that count are the living ones with a non-empty slot mask; the exe additionally requires the client object's type `obj+0x24` to be
    0x17 or 0x18 (the drawn mage body: `mage` / `mage_st`, spells.md 9e.4), which the engine does not model (DECISION: every own mage counts)."""
    table = world.spell_table
    if table is None:
        return []
    entries = {}
    for uid in unit_ids:
        u = world.units.get(uid)
        if u is None or u.hp <= 0:
            continue
        mask = unit_slot_mask(u)
        for slot in range(SLOTS):
            if not (mask >> slot) & 1:
                continue
            spell = table.get(SLOT_SPELLS[slot])
            if spell is None:
                continue
            skill, mind = _skill_and_mind(u, spell)
            sc = spell.scaled(wrapper_level(skill, mind))
            lvl = helper_level(skill, mind)
            e = entries.get(slot)
            if e is None:
                e = entries[slot] = SpellEntry(slot, spell.number, spell.display_name, _text_line(slot, spell, lines), spell.description, spell.mana_cost)
            e.members += 1
            lo, spread = sc.damage_min & 0xFF, sc.damage_spread & 0xFF
            e.damage_lo += lo
            e.damage_hi += lo + spread
            rng, dur = sc.max_range & 0xFF, sc.duration & 0xFFFF
            e.range_lo = rng if e.range_lo is None else min(e.range_lo, rng)
            e.range_hi = rng if e.range_hi is None else max(e.range_hi, rng)
            e.duration_lo = dur if e.duration_lo is None else min(e.duration_lo, dur)
            e.duration_hi = dur if e.duration_hi is None else max(e.duration_hi, dur)
            if spell.number == spelldefs.STONE_CURSE:
                e.duration_lo = 0                       # `0x416d90`: the slot of spell 0x12 zeroes the minimum after every unit
            h = _helper(spell.number, lvl)
            if h is not None and h[1] != 0:
                if e.extra is None:
                    e.extra = (h[0], h[1], h[1])
                else:
                    e.extra = (h[0], min(e.extra[1], h[1]), max(e.extra[2], h[1]))
    return [entries[s] for s in sorted(entries)]


def _pair(fmt_one, fmt_two, lo, hi):
    return fmt_one % lo if lo == hi else fmt_two % (lo, hi)


def tooltip(entry, labels):
    """The tooltip string of `FUN_004c628f` for an entry: `labels[k]` = main.txt line k.  `#` is the line break; rows in the exe's order (damage, range, duration, then the
    helper row).  Formats are the exe's (`0x5f6414`..`0x5f651c`): a party range prints `lo...hi` for the helper rows, `lo-hi` for damage and range, `lo -hi` for the duration."""
    out = ["%s#%s: %d" % (entry.text, labels[L_MANA], entry.mana_cost)]
    if entry.damage_hi:
        out.append("#" + labels[L_DAMAGE] + ": " + _pair("%d", "%d-%d", entry.damage_lo, entry.damage_hi))
    if entry.range_hi:
        out.append("#" + labels[L_RANGE] + ": " + _pair("%d", "%d-%d", entry.range_lo, entry.range_hi))
    if entry.duration_hi:
        lo, hi = entry.duration_lo / 16.0, entry.duration_hi / 16.0
        out.append("#" + labels[L_DURATION] + ": " + (("%5.1f" % lo) if entry.duration_lo == entry.duration_hi else ("%5.1f -%5.1f" % (lo, hi))))
    if entry.extra is not None:
        label, lo, hi = entry.extra
        if label == L_SPEED or label == L_SIGHT:
            row = _pair("%d", "%d...%d", lo, hi)
        elif label == L_RESISTANCE:
            row = _pair("+%d", "+%d...+%d", lo, hi)
        elif label in (L_MAX_PROB, L_MIN_PROB):
            row = _pair("+%d%%", "+%d...+%d%%", lo, hi)
        else:                                           # rays, absorption
            row = _pair("%d", "%d-%d", lo, hi)
        out.append("#" + labels[label] + ": " + row)
    return "".join(out)
