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


# --- cast order, Brain mode 8, the cast phases (docs/data/spells.md 9c.1-9c.2) -------------------------------------------------------------

from engine.world import Carrier, CastReleased, CastStarted, SpellCast       # noqa: E402  (after the pure math above)
from . import movement as mv                                                 # noqa: E402
from .pathfinding import centre_x, centre_y, foot, unit_size                 # noqa: E402

CAST_ORDER = 0xD                    # unit.order (+0x50): cast at a unit (`FUN_0056d3e6`); the group pass turns it into Brain mode 8
BRAIN_CAST = 2                      # unit.brain_order (brain+0x9): a cast is in progress (`FUN_0056e906`)
CAST_STATE = 0xD                    # unit.state (+0x54): casting at a unit (0xe, at a cell, is phase K)
PHASE_START, PHASE_WINDUP, PHASE_RECOVERY = 0, 5, 7     # the swing's phases (`combat.py`), shared by states 3, 0xd and 0xe


def known_mask(u):
    """Spellbook bit mask (`unit+0x140`, bit n = spell n): the unit's own, else the template's `known_spells` (humans with mana, monsters with a
    mask other than 0 / -1; docs/data/units.md)."""
    if u.spellbook is not None:
        return u.spellbook
    t = u.stats
    if t is None:
        return 0
    m = t.get("known_spells", -1)
    if m is None or m <= 0:
        return 0
    if u.human and u.mana_max <= 0:
        return 0
    return m


def wrapper_of(u, spell_id):
    """`FUN_0051c391(n)`: the unit's wrapper of spell `n`, None when the spell is not in its book."""
    return Wrapper(spell_id) if (known_mask(u) >> spell_id) & 1 else None


def unit_level(u, spell):
    """`FUN_00519483` / `FUN_00519db8`: `skill[sphere] - 30 + Mind` of the caster (`unit+0xa8+2*sphere`, `unit+0x88`), clamped 0..255."""
    skill = u.skills[spell.sphere] if len(u.skills) > spell.sphere else 0
    mind = prog.attributes(u.stats)[2] if u.human and u.stats is not None else 0
    return level_from(skill, mind)


def cast_level(u, spell, item_count=None):
    """Level at release: the item's count for a cast from a weapon, else the caster's own."""
    return item_count if item_count is not None else unit_level(u, spell)


def set_cast(world, u, target, wrapper):
    """`FUN_0056d3e6(unit, target, wrapper)`: cancel, order 0xd, brain `+0x28` / `+0x30`, range `+0x14` = wrapper `+9`, Brain mode 0."""
    spell = world.spell_table.get(wrapper.number)
    mv.cancel(u)
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
        mv.stop_unit(world, u)
        return
    if t is not u and not in_cast_range(u, t):
        step = mv.follow_drive(world, u, t)
        u.state = mv.MOVE_STATE
        if step and u.path:
            mv._start_step(world, u)
        elif not u.mover.turning:
            mv._set_action(world, u, mv.IDLE)
        return
    spell_id = u.cast_wrapper.number
    u.brain_order = BRAIN_CAST
    u.swing_count = 0
    u.state = CAST_STATE
    u.cast = SpellCast(spell_id, target=t.id, item_count=u.cast_wrapper.item_count)
    mv.stop_unit(world, u)          # brain+0x60 == 0 for a player's cast: `FUN_0056dbc6` (state 0, order 0xc, mode 0)


def brain_cast(u):
    """Brain order 2 (`FUN_0056dca2`): state 0xd, count one tick, and once more than 2 ticks old with the done flag set, back to order 0."""
    u.state = CAST_STATE
    u.swing_count = (u.swing_count + 1) & 0xFF
    if u.swing_count > 2 and u.done:
        u.brain_order = 0
        u.state = mv.IDLE_STATE
        u.cast = None


def cast_start(world, u, c, st):
    """`FUN_00519998` at phase 0: the mage's mana check and spend (a cast from an item pays nothing), the step clock `+0x138 := tick` and the
    client's projectile message.  Returns False when the mana is short (nothing changes: the exe retries on its next Brain pass)."""
    spell = world.spell_table.get(c.spell)
    t = world.find_unit(c.target)
    if t is None:
        return False
    if st.mage and c.item_count is None:
        if u.mana < spell.mana_cost:
            return False
        u.mana -= spell.mana_cost
    ax, ay = u.x * 256 + u.sub_x, u.y * 256 + u.sub_y
    if unit_size(t) > 1:
        bx, by = (centre_x(t) & 0xFFFF) - 1, (centre_y(t) & 0xFFFF) - 1
    else:
        bx, by = t.x * 256 + t.sub_x, t.y * 256 + t.sub_y
    from .combat import log
    log(world, CastStarted(world.tick, u.id, t.id, c.spell, client_flight_ticks(spell, bx - ax, by - ay)))
    u.step_end = world.tick         # the client message `FUN_005041d6` stores the server tick in unit +0x138
    u.action, u.action_start_tick = mv.ATTACK, world.tick      # client action 8 plays the shared attack block (animation.md 2.4)
    return True


def cast_release(world, u, c, st):
    """`FUN_00519d7f` -> `FUN_00519db8` for the damage branch: cast XP, level, off-map test, then the missile carrier (`delivery == 2`, flight time from
    the distance NOW) or the point carrier at once (`delivery == 1`).  Spells with no scaled damage have other handlers (phase K): nothing happens."""
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
    sc = spell.scaled(level)
    if (sc.damage_min & 0xFF) + (sc.damage_spread & 0xFF) == 0 or spell.distribution != spelldefs.DIST_SINGLE:
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
                cast_release(world, u, c, st)
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
