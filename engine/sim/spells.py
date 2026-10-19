"""Spell casting (phase I4): math, cast order, cast phases, carriers.

Facts: docs/data/spells.md 9, 9c (REA of the GOG exe, CONFIRMED unless tagged), docs/engine/combat.md 14.  Layer 4: reads and writes
`engine.world` only.
"""

import math
from dataclasses import dataclass

from allods2.formats import spelldefs

LIGHTNING, PRISMATIC_SPRAY = 10, 11             # `'\n'` / `'\v'` in FUN_00519998 / FUN_00519db8
INVISIBILITY, TELEPORT, HEAL, DRAIN_LIFE, SHIELD, CURSE = 12, 23, 24, 26, 27, 28      # spell numbers the AI code names (docs/engine/ai.md 12)
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


# --- cast order, Brain mode 8, the cast phases (docs/data/spells.md 9c.1-9c.2) -------------------------------------------------------------

from engine.world import Carrier, CastReleased, CastStarted, SpellCast       # noqa: E402  (after the pure math above)
from . import movement as mv                                                 # noqa: E402
from .pathfinding import centre_x, centre_y, foot, unit_size                 # noqa: E402

CAST_ORDER = 0xD                    # unit.order (+0x50): cast at a unit (`FUN_0056d3e6`); the group pass turns it into Brain mode 8
BRAIN_CAST = 2                      # unit.brain_order (brain+0x9): a cast is in progress (`FUN_0056e906`)
CAST_STATE = 0xD                    # unit.state (+0x54): casting at a unit
CELL_STATE = 0xE                    # unit.state: casting at a cell (`FUN_0056e986`)
CELL_ORDER = 0xE                    # unit.order: cast at a cell (`FUN_0056d446`, command 0x1f); the group pass turns it into Brain mode 9
PHASE_START, PHASE_WINDUP, PHASE_RECOVERY = 0, 5, 7     # the swing's phases (`combat.py`), shared by states 3, 0xd and 0xe


BOOK_BITS = ((1 << 30) - 1) & ~1      # spells 1..29 (the book loops `n = 1..0x1d`)


def monster_slots(t):
    """The three special-attack slots of a monster template (`FUN_005114f3` 0x511c70-0x511d56): `(spell, probability * 0x147)` per slot, (0, 0)
    for an unused one (`spell_i <= 0`: the brain stays memset 0).  `brain+0x7c+4i` / `brain+0x88+4i`; docs/engine/ai.md 12.1."""
    out = []
    for i in (1, 2, 3):
        n = t.get("spell_%d" % i, -1) if t is not None else -1
        q = t.get("probability_%d" % i, 0) if t is not None else 0
        out.append((n, q * 0x147) if n is not None and n > 0 else (0, 0))
    return tuple(out)


def _monster_mage_mask(t):
    m = t.get("known_spells", -1)
    return m if m is not None and m not in (0, -1) else None


def known_mask(u):
    """Spellbook bit mask (`unit+0x140`, bit n = spell n): the unit's own, else built as the creature set-up does: a human with mana from
    `known_spells`; a monster from `known_spells` when it is neither 0 nor -1 (the mage book, `0x511dd6`), else from its special-attack slot
    spells (`0x511d22`, only when `spell_1 > 0`).  docs/engine/ai.md 12.1."""
    if u.spellbook is not None:
        return u.spellbook
    t = u.stats
    if t is None:
        return 0
    m = t.get("known_spells", -1)
    if u.human:
        if m is None or m <= 0 or u.mana_max <= 0:
            return 0
        return m
    mm = _monster_mage_mask(t)
    if mm is not None:
        return mm & BOOK_BITS
    if (t.get("spell_1", -1) or 0) <= 0:
        return 0
    mask = 0
    for n, _ in monster_slots(t):
        if n:
            mask |= 1 << n
    return mask


def wrapper_of(u, spell_id):
    """`FUN_0051c391(n)`: the unit's wrapper of spell `n`, None when the spell is not in its book."""
    return Wrapper(spell_id) if (known_mask(u) >> spell_id) & 1 else None


_MONSTER_SKILLS = ("skillfire", "skillwater", "skillair", "skillearth", "skillastral")


def monster_skill(t, sphere):
    """`unit+0xa8+2*sphere` of a monster (`FUN_005114f3`): `spell_power` (p54) for every school, replaced by p57..p61 (raw, -1 kept) for a mage."""
    if t is None or not 1 <= sphere <= 5:
        return 0
    if _monster_mage_mask(t) is not None:
        return t.get(_MONSTER_SKILLS[sphere - 1], -1)
    return t.get("spell_power", -1)


def mind_of(u):
    """`unit+0x88` (Mind): a human's recomputed attribute, a monster's template value."""
    if u.stats is None:
        return 0
    return prog.attributes(u.stats)[2] if u.human else (u.stats.get("mind", 0) or 0)


def unit_level(u, spell):
    """`FUN_00519483` / `FUN_00519db8`: `skill[sphere] - 30 + Mind` of the caster (`unit+0xa8+2*sphere`, `unit+0x88`), clamped 0..255."""
    if u.human:
        skill = u.skills[spell.sphere] if len(u.skills) > spell.sphere else 0
    else:
        skill = monster_skill(u.stats, spell.sphere)
    return level_from(skill, mind_of(u))


def cast_level(u, spell, item_count=None):
    """Level at release: the item's count for a cast from a weapon, else the caster's own."""
    return item_count if item_count is not None else unit_level(u, spell)


def set_cast(world, u, target, wrapper):
    """`FUN_0056d3e6(unit, target, wrapper)`: cancel, order 0xd, brain `+0x28` / `+0x30`, range `+0x14` = wrapper `+9`, Brain mode 0."""
    spell = world.spell_table.get(wrapper.number)
    mv.cancel(u, world)
    u.order = CAST_ORDER
    u.cast_target = target.id
    u.cast_wrapper = wrapper
    u.range = wrapper_range(spell, wrapper, unit_level(u, spell))
    u.mode_go = u.mode_attack = u.mode_look = u.mode_cast = False
    u.anchor = None
    u.mover.waiting = u.mover.parked = False


def cast_group(world, g, spell_id, target, cancel_group):
    """Command `0x1e` (`FUN_004f515d` -> `FUN_005702be`): cancel the group (`FUN_00570e83`), then for every member that has the spell in its book
    `set_cast`.  A member without the spell only gets the cancel (INFERRED: the exe's call for `+0x44 == 0` did not resolve)."""
    cancel_group(world, g)
    for i in g.members:
        u = world.units[i]
        w = wrapper_of(u, spell_id)
        if w is not None:
            set_cast(world, u, target, w)


def refresh_cast(world, u):
    """Group pass, order 0xd (`FUN_00569321` -> `FUN_0056c72b`): Brain mode 8 with the target and the wrapper, range = wrapper `+9`.  A target id
    the world freed stops the unit (INFERRED: the exe dereferences a dangling pointer), as `combat.refresh_attack` does."""
    t = world.find_unit(u.cast_target)
    if t is None or u.cast_wrapper is None:
        mv.stop_unit(world, u)
        return
    spell = world.spell_table.get(u.cast_wrapper.number)
    u.mode_go = u.mode_attack = u.mode_look = False
    u.mode_cast = True
    u.mover.waiting = u.mover.parked = False
    u.range = wrapper_range(spell, u.cast_wrapper, unit_level(u, spell))


def in_cast_range(u, t):
    """`FUN_0055532d`: facing equals the octant to the target and the gap level is within the range: the same test as the melee attack."""
    from . import combat
    a, b = foot(u), foot(t)
    return u.facing == combat.octant(a, b) and combat.reach_gap(a, b) <= u.range


def cast_mode(world, u):
    """Brain mode 8 (`FUN_0056ebc0`): out of range -> the follow driver of the melee approach and state 1; else start the cast (`FUN_0056e906`)."""
    t = world.find_unit(u.cast_target)
    if t is None:
        if u.ai_cast:
            u.mode_cast = False         # as for an AI's mode 5 (combat.attack_mode): the next group pass decides again (INFERRED: the exe's dangling pointer)
        else:
            mv.stop_unit(world, u)
        return
    if t is not u and not in_cast_range(u, t):
        step = mv.follow_drive(world, u, t)
        u.state = mv.MOVE_STATE
        if step:
            mv._step_or_turn(world, u)
        elif not u.mover.turning:
            mv._set_action(world, u, mv.IDLE)
        return
    spell_id = u.cast_wrapper.number
    u.brain_order = BRAIN_CAST
    u.swing_count = 0
    u.state = CAST_STATE
    u.cast = SpellCast(spell_id, target=t.id, item_count=u.cast_wrapper.item_count)
    if not u.ai_cast:
        mv.stop_unit(world, u)      # brain+0x60 == 0 for a player's cast: `FUN_0056dbc6` (state 0, order 0xc, mode 0); an AI cast keeps mode 8 (ai.md 12.7)


def set_cell_cast(world, u, cell, wrapper):
    """`FUN_0056d446(unit, x, y, wrapper)` (command 0x1f): cancel, order 0xe, brain `+0x3c` = the cell, `+0x30` = wrapper, range = wrapper `+9`, Brain mode 0."""
    spell = world.spell_table.get(wrapper.number)
    mv.cancel(u, world)
    u.order = CELL_ORDER
    u.cast_cell = (int(cell[0]) & 0xFF, int(cell[1]) & 0xFF)
    u.cast_wrapper = wrapper
    u.range = wrapper_range(spell, wrapper, unit_level(u, spell))
    u.mode_go = u.mode_attack = u.mode_look = u.mode_cast = u.mode_cell = False
    u.anchor = None
    u.mover.waiting = u.mover.parked = False


def cell_cast_group(world, g, spell_id, cell, cancel_group):
    """Command `0x1f` (`FUN_004f515d` -> `FUN_0057033d`): only for a spell that targets a cell (`FUN_0051941a`: param `target == 2`); cancel the group,
    then `set_cell_cast` for every member with the spell in its book (the others only get the cancel, as for `cast_group`)."""
    spell = world.spell_table.get(spell_id)
    if spell is None or spell.target != 2:
        return
    cancel_group(world, g)
    for i in g.members:
        u = world.units[i]
        w = wrapper_of(u, spell_id)
        if w is not None:
            set_cell_cast(world, u, cell, w)


def refresh_cell(world, u):
    """Group pass, order 0xe (`FUN_00569321` -> `FUN_0056969c(unit, brain+0x3c, brain+0x30)`): Brain mode 9, range = wrapper `+9`."""
    if u.cast_wrapper is None or u.cast_cell is None:
        mv.stop_unit(world, u)
        return
    spell = world.spell_table.get(u.cast_wrapper.number)
    u.mode_go = u.mode_attack = u.mode_look = u.mode_cast = False
    u.mode_cell = True
    u.mover.waiting = u.mover.parked = False
    u.range = wrapper_range(spell, u.cast_wrapper, unit_level(u, spell))


def facing_to_cell(u, cell):
    """`FUN_00556b2c(unit, cell)`: the 8-way facing (sector * 32) from the unit's cell to `cell` (spelldefs.direction8, the 2:1 rule)."""
    return spelldefs.direction8(cell[0] - u.x, cell[1] - u.y) << 5


def cell_mode(world, u):
    """Brain mode 9 (`FUN_0056ec3f`): in range (`FUN_0055539a`: facing == `FUN_00556b2c(cell)` and Chebyshev(cell, unit cell) <= range) -> start the
    cell cast (`FUN_0056e986`); else `FUN_0056e4ac(unit, cell, range)`: the move driver `FUN_00555411` towards the cell, which within `range` of it only
    turns to it (`FUN_00556da2`), and state 1."""
    from .pathfinding import chebyshev
    cell = u.cast_cell
    here = (u.x, u.y)
    if u.cast_wrapper is None or cell is None:
        mv.stop_unit(world, u)
        return
    face = facing_to_cell(u, cell)
    dist = chebyshev(here, cell)
    if u.facing == face and dist <= u.range:
        u.brain_order = BRAIN_CAST
        u.swing_count = 0
        u.state = CELL_STATE
        u.cast = SpellCast(u.cast_wrapper.number, cell=tuple(cell), item_count=u.cast_wrapper.item_count)
        if not u.ai_cast:
            mv.stop_unit(world, u)      # FUN_0056e986: brain+0x60 == 0 -> FUN_0056dbc6
        return
    m = u.mover
    if dist <= u.range:                 # FUN_00555411 at a centre, within the stop distance: only the turn (range 0 never gets here: dist 0 is in range)
        if u.facing != face or m.turning:
            mv._set_action(world, u, mv.TURN)
        mv._turn_toward(u, face)
    else:
        if m.goal != tuple(cell):
            m.goal = tuple(cell)
            m.arrived = m.failed = False
        mv.go_tick(world, u)
        if m.waiting or m.parked:       # FUN_00555411's blocker turn writes Brain mode 10 / 0 over mode 9 (the engine's wait is mode 1 + waiting)
            u.mode_cell, u.mode_go = False, True
    u.state = mv.MOVE_STATE


def brain_cast(u):
    """Brain order 2 (`FUN_0056dca2`): state 0xd (0xe for a cell cast, brain `+0x5c == 0`), count one tick, and once more than 2 ticks old with
    the done flag set, back to order 0."""
    u.state = CELL_STATE if (u.cast is not None and u.cast.cell is not None) else CAST_STATE
    u.swing_count = (u.swing_count + 1) & 0xFF
    if u.swing_count > 2 and u.done:
        u.brain_order = 0
        u.state = mv.IDLE_STATE
        u.cast = None


def cast_start(world, u, c, st):
    """`FUN_00519998` at phase 0: the mage's mana check and spend (a cast from an item pays nothing), the step clock `+0x138 := tick` and the
    client's projectile message.  Returns False when the mana is short (nothing changes: the exe retries on its next Brain pass)."""
    spell = world.spell_table.get(c.spell)
    t = None
    if c.cell is None:
        t = world.find_unit(c.target)
        if t is None:
            return False
    if st.mage and c.item_count is None:
        if u.mana < spell.mana_cost:
            return False
        u.mana -= spell.mana_cost
    ax, ay = u.x * 256 + u.sub_x, u.y * 256 + u.sub_y
    if t is None:
        bx, by = c.cell[0] * 256 + 128, c.cell[1] * 256 + 128      # INFERRED: the cell centre (only the client's flight time uses it)
    elif unit_size(t) > 1:
        bx, by = (centre_x(t) & 0xFFFF) - 1, (centre_y(t) & 0xFFFF) - 1
    else:
        bx, by = t.x * 256 + t.sub_x, t.y * 256 + t.sub_y
    from .combat import log
    if spell.number == PRISMATIC_SPRAY and t is not None:
        stub_release(world, u, spell.number)        # FUN_00519998: the chain FUN_00519c04 (up to min(7, L/20 + 2) targets) runs here: not built
    log(world, CastStarted(world.tick, u.id, t.id if t is not None else None, c.spell, client_flight_ticks(spell, bx - ax, by - ay)))
    u.step_end = world.tick         # the client message `FUN_005041d6` stores the server tick in unit +0x138
    u.action, u.action_start_tick = mv.ATTACK, world.tick      # client action 8 plays the shared attack block (animation.md 2.4)
    return True


def stub_release(world, u, number, target=None, cell=None):
    """A release whose effect handler (`FUN_00519db8` switch case, area / field carrier, chain, summon, teleport ...) is not built: nothing changes in the
    world (mana, animation and recovery already ran); the release is counted in `World.unbuilt_casts` (spell number -> count).  Not a guess of the effect."""
    world.unbuilt_casts[number] = world.unbuilt_casts.get(number, 0) + 1


def heal(world, t, amount, caster=None):
    """`FUN_00510484(amount)`: HP += amount, capped at the maximum; a unit that rises from HP < 1 to HP > 0 is revived (`FUN_00510534`)."""
    from .combat import log
    from engine.world import Healed
    before = t.hp
    t.hp = min(t.hp + amount, t.hp_max)
    log(world, Healed(world.tick, caster.id if caster is not None else None, t.id, amount, t.hp))
    if before < 1 and t.hp > 0:
        revive(world, t)


def revive(world, t):
    """`FUN_00510534`: the dying state is undone: corpse stage byte `+0x13c := 0` (the next HP <= 0 starts the countdown again), phase 0, done flag 1,
    defence `<<= 1` then the recompute (vtable +0x58; INFERRED: it rebuilds the combat numbers, so the engine drops its halved copy), HP at least 1, then
    `FUN_0056dba1` (cancel + order 0xc on the own cell).  `FUN_005551d6(position)` is not decoded (INFERRED: a grid update; nothing modelled)."""
    t.death_seen = False
    t.death_tick = None
    t.phase = 0
    t.done = True
    t.combat = None
    t.hp = max(t.hp, 1)
    mv.fail_stop(world, t)
    mv._set_action(world, t, mv.IDLE)


def _rand1(rng, n):
    """`FUN_0051fa4e(n)` = `FUN_0051fa25(n - 1) + 1` (1..n; n == 0 draws and gives 1)."""
    return rng.rand(n - 1) + 1


def heal_release(world, u, t, spell, level):
    """`FUN_00519db8` case 0x18 (`0x51a2b8`): no effect on a target whose owner the caster is at war with (relation bit 1); otherwise, when the target
    has HP > -10 and an HP regeneration (`+0x98 != 0`): `min' + rand(1..spread')` capped at `maxHP - HP`, then `FUN_00510484`."""
    from . import ai, vitals
    if ai.at_war(world, u.owner, t.owner):
        return
    if t.hp <= -10 or not vitals.regen_rates(t)[0]:
        return
    sc = spell.scaled(level)
    amount = (sc.damage_min & 0xFF) + _rand1(world.rng, sc.damage_spread & 0xFF)
    cap = t.hp_max - t.hp
    heal(world, t, amount if amount < cap else cap, u)


def drain_release(world, u, t, spell, level):
    """`FUN_00519db8` case 0x1a (`0x51a3f3`), creature targets only: `(min' + rand(1..spread')) * (100 - protAstral) / 100` (C division), capped at the
    target's HP + 10; if positive: the caster's damage XP credit (vtable +0x6c), the AI hit reaction, target HP -= amount, last attacker := caster, then
    the caster heals the amount (`FUN_00510484`)."""
    from . import ai, xp
    from .combat import combat_stats, log
    from engine.world import Damage, Died
    sc = spell.scaled(level)
    amount = (sc.damage_min & 0xFF) + _rand1(world.rng, sc.damage_spread & 0xFF)
    p = combat_stats(world, t).block.prot[5]
    amount = int(amount * (100 - p) / 100)              # cdq / idiv: truncation toward zero
    cap = t.hp + 10
    amount = amount if amount < cap else cap
    if amount <= 0:
        return
    before = t.hp
    xp.damage_credit(world, u, t, amount, before)
    if world.ai_on:
        ai.on_hit(world, u, t)
    t.hp = before - amount
    log(world, Damage(world.tick, u.id, t.id, amount, t.hp, 0, True))
    t.last_attacker = u.id
    if before > 0 and t.hp <= 0:
        log(world, Died(world.tick, t.id, u.id))
    heal(world, u, amount, u)


def cast_release_cell(world, u, c, st):
    """State 0xe release: `FUN_00519db8(caster, 0, x, y)`: the cast XP, then the cell handlers (area / field carriers, teleport, raise dead ...),
    none of which is built yet: `stub_release`."""
    from . import xp
    spell = world.spell_table.get(c.spell)
    if st.mage and c.item_count is None:
        xp.award(world, u, int(0.5 * spell.mana_cost + 0.5), spell.sphere)
    stub_release(world, u, spell.number, cell=c.cell)


def cast_release(world, u, c, st):
    """`FUN_00519d7f` -> `FUN_00519db8` for a unit target: cast XP, level, off-map test, then Heal (24) and Drain Life (26), or the damage branch: the missile
    carrier (`delivery == 2`, flight time from the distance NOW) or the point carrier at once (`delivery == 1`).  Every other handler is `stub_release`."""
    from . import xp
    from .combat import log
    spell = world.spell_table.get(c.spell)
    if spell.number == PRISMATIC_SPRAY:             # FUN_00519d7f skips spell 11 (it has no unit-target release)
        return
    t = world.find_unit(c.target)
    level = cast_level(u, spell, c.item_count)
    if st.mage and c.item_count is None:
        xp.award(world, u, int(0.5 * spell.mana_cost + 0.5), spell.sphere)      # vtable +0x70 = FUN_005131ef: AddExp(ftol(0.5 * mana + 0.5), 0, sphere)
    if t is None:
        return
    if spell.number in (HEAL, DRAIN_LIFE):
        (heal_release if spell.number == HEAL else drain_release)(world, u, t, spell, level)
        log(world, CastReleased(world.tick, u.id, t.id, c.spell, level, 0))
        return
    sc = spell.scaled(level)
    if (sc.damage_min & 0xFF) + (sc.damage_spread & 0xFF) == 0 or spell.distribution != spelldefs.DIST_SINGLE:
        stub_release(world, u, spell.number, target=t)
        return
    carrier = 0
    if spell.delivery == spelldefs.DELIVERY_MISSILE:
        dx = (t.x * 256 + t.sub_x) - (u.x * 256 + u.sub_x)
        dy = (t.y * 256 + t.sub_y) - (u.y * 256 + u.sub_y)
        carrier = world.next_carrier_id()
        n = flight_ticks(spell, dx, dy) & 0xFFFF
        world.carriers.append(Carrier(carrier, "missile", u.id, t.id, c.spell, level, n, world.tick, True, (u.x * 256 + u.sub_x, u.y * 256 + u.sub_y), n,
                                      (t.x * 256 + t.sub_x, t.y * 256 + t.sub_y)))
    else:
        carrier = world.next_carrier_id()
        world.carriers.append(Carrier(carrier, "point", u.id, t.id, c.spell, level, 0, world.tick, True, (u.x * 256 + u.sub_x, u.y * 256 + u.sub_y), 0, (t.x * 256 + t.sub_x, t.y * 256 + t.sub_y)))
    log(world, CastReleased(world.tick, u.id, t.id, c.spell, level, carrier))


def cast_tick(world, u):
    """States 3 (weapon spell), `0xd` and `0xe` of the creature tick (`FUN_0050f12c`): the swing's phase machine.  Phase 0 starts the cast (mana,
    message), phase 5 counts the windup down and releases the effect, phase 7 the recovery.  Facts: spells.md 9c.2."""
    from .combat import combat_stats, hero_delay
    st = combat_stats(world, u)
    c = u.cast
    if u.phase == PHASE_START:
        if c is not None and cast_start(world, u, c, st):
            u.done = False
            u.phase = PHASE_WINDUP
            u.timer = st.windup & 0xFF
    elif u.phase == PHASE_WINDUP:
        u.timer = (u.timer - 1) & 0xFF
        if u.timer == 0:
            if c is not None:
                (cast_release_cell if c.cell is not None else cast_release)(world, u, c, st)
                if c.item_count is not None:        # unit +0x68 / +0x64 := 0 (a staff stays, a scroll would be deleted: no pack items yet)
                    u.cast = c = None
            u.phase = PHASE_RECOVERY
            delay = hero_delay(st.weapon_weight, st.reaction) if st.human and st.has_weapon else 0
            comp = world.spell_table.get(c.spell).complication_level if c is not None else 0
            u.timer = recovery_ticks(st.recovery, delay, comp, world.rng) & 0xFF
    elif u.phase == PHASE_RECOVERY:
        u.timer = (u.timer - 1) & 0xFF
        if u.timer == 0:
            u.phase = PHASE_START
            u.done = True


# --- carriers (docs/data/spells.md 9c.3) -------------------------------------------------------------------------------------------------

def carrier_system(world, commands):
    """`FUN_0052c279` over the active list in creation order, before the creature pass of the same tick.  A missile counts its flight down and,
    below 1, appends its point carrier to the tail of the list (visited later in this pass); a point carrier applies the effect on its visit."""
    done = set()
    i = 0
    while i < len(world.carriers):
        c = world.carriers[i]
        if c.kind == "missile":
            c.ticks_left -= 1
            if c.ticks_left < 1:
                world.carriers.append(Carrier(world.next_carrier_id(), "point", c.caster, c.target, c.spell, c.level, 0, c.born, c.hostile, c.start, c.flight, c.aim))
                done.add(c.uid)
        else:
            apply_point(world, c)
            done.add(c.uid)
        i += 1
    if done:
        world.carriers[:] = [c for c in world.carriers if c.uid not in done]


def apply_point(world, c):
    """`FUN_00517949`: the elemental effect (`FUN_0051e65b` -> `FUN_00516f6f`) on a target that is still in the world, then the attacker bookkeeping
    (victim's last attacker, the AI hit reaction `FUN_0056e6b8`) for a hostile spell whose caster is still valid."""
    from . import ai, xp
    from .combat import combat_stats, log
    from engine.world import Damage, Died
    t = world.find_unit(c.target)
    if t is None:
        return
    caster = world.units.get(c.caster)              # the caster object's +0x14 is 0 once it left the world (INFERRED: removed from `units`)
    spell = world.spell_table.get(c.spell)
    from .combat import take_hit_detail
    res = take_hit_detail(spell_record(spell, c.level), combat_stats(world, t).block, world.rng)
    before = t.hp
    t.hp = before - res.damage
    if c.hostile and caster is not None:
        t.last_attacker = caster.id
        if world.ai_on:
            ai.on_hit(world, caster, t)
    if before > 0 or t.hp > -10:
        log(world, Damage(world.tick, c.caster, t.id, res.damage, t.hp, res.roll, True))
    if caster is not None:
        xp.damage_credit(world, caster, t, res.damage, before)
    if before > 0 and t.hp <= 0:
        log(world, Died(world.tick, t.id, c.caster))


from allods2.formats import progression as prog         # noqa: E402  (unit_level)
