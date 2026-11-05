"""Cell record effects ("traps") and the hidden caster (docs/engine/effects.md 9; CONFIRMED in the GOG allods2.exe unless marked).

A cell record carries one 6-byte effect `+0x34..+0x39` = (spell, power, source x, source y, target x, target y), written by
`FUN_0055ba36(cell, effect)` from the map's section 9 (`FUN_00562745` 0x564280) and the scenario instant 25 "Set trap"
(`FUN_0057847e`); refused on a cell whose live layer has bit 0 (static block).  Nothing ever clears it (the record is not empty while
`+0x34 != 0`, `FUN_005513b6`), so the trap fires every time.

- Reader 1, `FUN_005503af` (the occupant place of `FUN_0055020a`, ground movement classes 1 and 2 only, for each footprint cell in the
  loop's order, BEFORE the slot test): spell 0x17 (Teleport) stores the target cell in `brain+0xb0` (`Unit.teleport_to`, word `ty << 8 |
  tx`); any other spell: `FUN_004f0832(sx, sy, unit, spell, power)` = a hidden caster at the source cell casts the spell at the unit
  (`FUN_00519408`, the test in between, is a constant 1).
- Reader 2, `FUN_00555b38` at the step end (the unit at a centre, after the stamps): the record of the unit's own cell with spell 0x17
  teleports at once, `FUN_0055a96c(unit, tx, ty)`.
- `brain+0xb0` is consumed by the Brain tick under brain order 0 at a centre, before the mode switch (`0x56e01b`-`0x56e087`):
  `FUN_0055a96c` then `brain+0xb0 := 0` whatever the result.
- The hidden caster `FUN_004f06ac(sx, sy, spell, power)`: a 0x208-byte monster object (vtable `0x5d0eb0`, its slot 0x18 is the creature tick
  `FUN_0050f12c`) with id 0 and no player, at the source cell's centre, NOT placed in the cell slots (it blocks nothing), HP 30, Mind 30
  (`+0x88 = 0x1e`), the spell's sphere skill = power (so its level = power), a one-spell book, windup / recovery 1 (`+0x134`, `+0x135`), then
  state 0xd with the target (`FUN_004f0832`) or state 0xe with the target cell (`FUN_004f086f`, instant 21).  Its constructor draws
  `rand(128)` (facing, `FUN_0050e173`).  It lives in the transient list `server+0x2c`, ticked in step 2 of every server tick
  (`FUN_004f04cf`: before the area effects and the creatures) and deleted after the tick in which `+0x136` (done) is set.
"""

from engine.cellslots import movement_class, pack
from engine.world import SpellCast, Unit

TELEPORT = 0x17
CASTER_HP = 30                  # FUN_0050ec60: +0x94 / +0x96
CASTER_MIND = 30                # FUN_004f06ac: +0x88 = 0x1e


# --- the record --------------------------------------------------------------------------------------------------------------------------

def set_record(world, x, y, effect):
    """`FUN_0055ba36`: store the 6-byte effect in the record of cell (x, y) (made when missing); refused (False) when the live layer has
    bit 0 there (water, rock, structure ground, the map border)."""
    x, y = x & 0xFF, y & 0xFF
    if not (0 <= x < world.width and 0 <= y < world.height) or world.block[y, x] & 1:
        return False
    world.cell_effects[(x, y)] = tuple(int(b) & 0xFF for b in effect)
    if world.slots.on_enter is None:                    # the reader in FUN_005503af (CellSlots.place)
        world.slots.on_enter = lambda u, idx: on_enter(world, u, idx)
    return True


def section9_records(m):
    """The section 9 records `FUN_00562745` registers as cell effects (0x5641c5-0x564280): an unclaimed record with `a` or `b` != 0 and kind
    (`u16 +0x10`) < 4: cell (a, b), effect (c low byte, the byte at +0x18 = c's high word low byte, pair 0 id, pair 0 value, pair 1 id, pair 1
    value), every value its low byte.  Returns [((x, y), effect)] in record order."""
    out = []
    for r in m.item_records:
        kind = int.from_bytes(r.flags[0:2], "little")
        if (r.a or r.b) and kind < 4:
            p = list(r.props) + [(0, 0), (0, 0)]           # INFERRED: the install's 30 records all have two pairs
            eff = (r.c & 0xFF, (r.c >> 16) & 0xFF, p[0][0] & 0xFF, p[0][1] & 0xFF, p[1][0] & 0xFF, p[1][1] & 0xFF)
            out.append(((r.a & 0xFF, r.b & 0xFF), eff))
    return out


def load_map(world, m):
    """The map-load writer (`0x564280`); returns the number of records stored."""
    return sum(set_record(world, x, y, eff) for (x, y), eff in section9_records(m))


def instant_effect(n):
    """`FUN_0057847e` (instant 25): (cell, effect) = ((n2, n3), (n0, n1, sx, sy, tx, ty)); source and target are the trap cell when n4 == 0,
    else (n4, n5) and (n6, n7)."""
    x, y = n[2] & 0xFF, n[3] & 0xFF
    src, dst = ((x, y), (x, y)) if n[4] == 0 else ((n[4], n[5]), (n[6], n[7]))
    return (x, y), (n[0], n[1], src[0], src[1], dst[0], dst[1])


# --- the readers -------------------------------------------------------------------------------------------------------------------------

def on_enter(world, u, idx):
    """`FUN_005503af` before its slot test: the effect of the record of cell `idx` (16-bit word) for a unit of class 1 or 2."""
    eff = world.cell_effects.get((idx & 0xFF, idx >> 8))
    if eff is None or not eff[0] or movement_class(u) not in (1, 2):
        return
    spell, power, sx, sy, tx, ty = eff
    if spell == TELEPORT:
        u.teleport_to = pack(tx, ty)
    else:
        cast_at_unit(world, sx, sy, u, spell, power)


def step_end(world, u):
    """The tail of `FUN_00555b38` at a centre: a Teleport record on the unit's own cell teleports it now."""
    eff = world.cell_effects.get((u.x, u.y))
    if eff is not None and eff[0] == TELEPORT:
        from .effects import teleport
        teleport(world, u, eff[4], eff[5])


def pending(world, u):
    """Brain order 0 at a centre (`0x56e01b`): a stored `brain+0xb0` teleports (`FUN_0055a96c`) and is cleared."""
    from .effects import teleport
    cell = u.teleport_to
    teleport(world, u, cell & 0xFF, cell >> 8)
    u.teleport_to = 0


# --- the hidden caster -------------------------------------------------------------------------------------------------------------------

class CasterStats(dict):
    """The template a hidden caster reads: Mind 30 and `spell_power` = the power (a non-mage monster reads `spell_power` for every school,
    `spells.monster_skill`; the object sets only the spell's sphere, the only one its cast reads)."""

    def __getattr__(self, key):
        return self.get(key)


def _caster(world, sx, sy, spell, power):
    """`FUN_004f06ac` (see the module text): returns the new object, appended to `world.transients`."""
    from .combatstats import CombatStats
    facing = 0x40 + world.rng.rand(128)                 # FUN_0050e173: the creature constructor's facing draw
    c = Unit(0, 0, 0, sx & 0xFF, sy & 0xFF, facing=facing & 0xFF, hp=CASTER_HP, hp_max=CASTER_HP, move_type=1,
             stats=CasterStats(mind=CASTER_MIND, spell_power=power & 0xFF))
    c.order = 0xB                                       # FUN_0050ec60: +0x50 = 0xb
    c.combat = CombatStats(human=False, mage=False, windup=1, recovery=1)
    world.transients.append(c)
    return c


def cast_at_unit(world, sx, sy, t, spell, power):
    """`FUN_004f0832(sx, sy, unit, spell, power)`: the hidden caster in state 0xd at `t`."""
    c = _caster(world, sx, sy, spell, power)
    c.state = 0xD
    c.cast = SpellCast(spell & 0xFF, target=t.id)
    return c


def cast_at_cell(world, sx, sy, tx, ty, spell, power):
    """`FUN_004f086f(sx, sy, tx, ty, spell, power)`: the hidden caster in state 0xe at cell (tx, ty)."""
    c = _caster(world, sx, sy, spell, power)
    c.state = 0xE
    c.cast = SpellCast(spell & 0xFF, cell=(tx & 0xFF, ty & 0xFF))
    return c


def transient_system(world, commands):
    """Step 2 of the server tick (`FUN_004f04cf`): every transient object in list order runs its creature tick, then leaves the list when its
    done flag `+0x136` is set.  The tick of a hidden caster is the state switch's cast phases (`spells.cast_tick`): no effects, HP 30, no group,
    Brain mode 0 under order 0xb (INFERRED: the Brain tick does nothing for it).  A cast whose start fails (target gone) leaves `+0x136` at its
    constructor value 1, so the object is deleted after that tick."""
    if not world.transients:
        return
    from . import spells
    done, i = set(), 0
    while i < len(world.transients):                    # an object appended during the pass is visited in it (MFC list walk)
        c = world.transients[i]
        if c.state in (spells.CAST_STATE, spells.CELL_STATE):
            spells.cast_tick(world, c)
        if c.done:
            done.add(id(c))
        i += 1
    if done:
        world.transients[:] = [c for c in world.transients if id(c) not in done]
