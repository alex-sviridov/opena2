"""Combat: the hit formulas, geometry and timers (pure functions), then the order, approach and swing (system parts).

Spec: docs/engine/combat.md (C§ numbers in the comments); routine addresses are there.  Layer 4: reads and writes `engine.world` only.
"""

from typing import NamedTuple

from engine.world import DEAD, Damage, Died, SpellCast

from . import movement as mv        # movement reaches back into this module only at call time (`_tick_unit`, `follow_drive`)
from .combatstats import CombatStats, u8, unit_combat_stats
from .pathfinding import centre_x, centre_y, foot
from .pathfinding import follow_distance as reach_gap       # `FUN_00556dcd`: whole cells between footprints + 1 (touching = 1)

# --- hit resolution (C§5.2, `FUN_00516f6f`) -----------------------------------------------------


class HitResult(NamedTuple):
    damage: int         # what `take_hit` returns (>= 0)
    hit: bool           # the physical part passed the roll (`T + roll > D`, the 90 rule or the sure-hit flag)
    roll: int           # rand(200) - 100, or 0 when the defender was immune (nothing was drawn)
    phys: int           # physical part after absorption and resistance (before the total is floored)
    second: int         # second part
    elemental: int      # elemental part


def resist(x, percent):
    """`trunc(x * (100 - p) / 100 + 0.75)` with the x87 constants 100.0 and 0.75 (`__ftol` truncates toward zero)."""
    return int(x * (100 - percent) / 100.0 + 0.75)


def take_hit_detail(rec, block, rng, *, human=False, sure_hit=False, bless=None, curse=None, immune=False):
    """`FUN_00516f6f`: the damage of one blow of attack record `rec` against armour block `block`, drawing from `rng` in the exe's order
    (Bless draw, Curse draw, physical spread, roll, second spread, elemental spread).  `human`: the attacker is a human (no x15
    scaling); `sure_hit`: attacker flag `+0x4c & 0x10`; `bless` / `curse`: chance 0..100 of the active effect, None when absent;
    `immune`: defender flag `+0x4c & 8`."""
    if immune:
        return HitResult(0, False, 0, 0, 0, 0)
    lo, sp = rec.lo, rec.sp
    if lo & 0x80 and not human:
        lo = (lo & 0x7F) * 15
        sp = sp * 15
    fixed = False
    if bless is not None and bless > rng.rand(100):
        lo += sp
        fixed = True
    if curse is not None and curse > rng.rand(100):
        fixed = True
    phys = lo if fixed else lo + rng.rand(sp)
    roll = rng.rand(200) - 100
    attack = rec.skill + roll
    hit = attack > block.defence or sure_hit or roll >= 90
    d1 = phys if hit else 0
    if d1 > 0:
        if not sure_hit:
            d1 = max(d1 - block.absorb, 0)
        pct = block.res[rec.kind] if 0 <= rec.kind < len(block.res) else 0
        if pct:
            d1 = resist(d1, pct)
    total = d1
    d2 = 0
    if rec.lo2 + rec.sp2 > 0:                      # not gated by the roll
        d2 = rec.lo2 + rng.rand(rec.sp2)
        if block.prot[2]:
            d2 = max(resist(d2, block.prot[2]), 0)
        total += d2
    d3 = 0
    if rec.elo + rec.esp > 0 and (attack > block.defence or rec.lo + rec.sp == 0):
        d3 = rec.elo + rng.rand(rec.esp)
        if 1 <= rec.elem <= 5 and block.prot[rec.elem]:
            d3 = max(resist(d3, block.prot[rec.elem]), 0)
        if d3 > 0:
            total += d3
    return HitResult(max(total, 0), hit, roll, d1, d2, d3)


def take_hit(rec, block, rng, **kw):
    """Damage only (see `take_hit_detail`)."""
    return take_hit_detail(rec, block, rng, **kw).damage


# --- geometry (C§3.1, C§5.1) --------------------------------------------------------------------

def attack_gap(a, b):
    """`FUN_005169de`: the range test of the hit.  `D` = Chebyshev distance of the centres in 1/256 cells; `D' = D - (size_a + size_b - 2) * 128`;
    1 when `D' <= 384`, else `(D' + 64) >> 8`."""
    d = max(abs(centre_x(a) - centre_x(b)), abs(centre_y(a) - centre_y(b)))
    d -= (a.size + b.size) * 128 - 256
    return 1 if d <= 0x180 else (d + 0x40) >> 8


def in_attack_range(a, b, rng_byte):
    """C§5.1: the hit lands when `attack_gap <= range` (the byte `+0x12c`)."""
    return attack_gap(a, b) <= rng_byte


def octant(frm, to):
    """`FUN_005568e4`: the 8-way facing (multiples of 32, 0 = north, clockwise) from `frm` towards `to`, by the sign quadrants and the 2:1 ratio
    rule; `dx == 0` / `dy == 0` count as non-positive.  16-bit centres as in the exe."""
    dx = (centre_x(to) - centre_x(frm))
    dy = (centre_y(to) - centre_y(frm))
    a = (-dx if dx < 1 else dx) & 0xFFFF
    b = (-dy if dy < 1 else dy) & 0xFFFF
    if dx < 1:
        if dy < 1:
            code = (12 if b * 2 < a else 13) if b < a else (15 if a * 2 < b else 14)
        else:
            code = (11 if b * 2 < a else 10) if b < a else (8 if a * 2 < b else 9)
    elif dy < 1:
        code = (3 if b * 2 < a else 2) if b < a else (0 if a * 2 < b else 1)
    else:
        code = (4 if b * 2 < a else 5) if b < a else (7 if a * 2 < b else 6)
    if code:
        code += 1
    return u8((code >> 1) << 5)


# --- timers (C§4) -------------------------------------------------------------------------------

def hero_delay(weapon_weight, reaction):
    """`L`: `clamp((weight + (30 - Reaction) * 5) / 12, 0, 12)`, C integer division (truncation toward zero)."""
    v = int((weapon_weight + (30 - reaction) * 5) / 12)
    return 0 if v < 0 else 12 if v >= 12 else v


def attack_extra(gap):
    """Arrow flight added to the wind-up (`FUN_00516b2f`): `(gap * 256 + 128) / 200` when `gap > 1`, else 0."""
    return (gap * 256 + 128) // 200 if gap > 1 else 0


# --- who may attack whom (C§2.2, `FUN_005711ea`) ------------------------------------------------

# 4 x 4 bytes built in the order manager's constructor (0x56827a..0x568310): row = attacker class, column = target class.
ATTACK_MATRIX = ((2, 1, 2, 4), (4, 2, 1, 0), (2, 1, 4, 0), (2, 1, 2, 4))


def can_attack(att_move, att_range, tgt_move, tgt_range):
    """False when the matrix byte is 0: melee ground units and ghosts cannot attack flyers.  The target class is its movement type,
    0 for a ground unit that shoots; a shooter always reads row 0."""
    col = 0 if tgt_move == 1 and tgt_range > 1 else tgt_move
    row = 0 if att_range > 1 else att_move
    return ATTACK_MATRIX[row][col] != 0


# =====================================================================================================================
# The fight: order 3, the executor, Brain mode 5 and the swing (C§2-C§5).  Layer 4: reads and writes `engine.world` only.
# =====================================================================================================================

BRAIN_SWING = 1                    # unit.brain_order: swing in progress (brain+0x9 == 1)
STATE_ATTACK = mv.ATTACK_STATE     # unit.state 3
PHASE_START, PHASE_WINDUP, PHASE_RECOVERY = 0, 5, 7
LOG_LIMIT = 20000


def log(world, entry):
    """Append to the fight log, keeping it bounded for sessions nobody drains."""
    world.fight_log.append(entry)
    if len(world.fight_log) > LOG_LIMIT:
        del world.fight_log[:LOG_LIMIT // 2]


def combat_stats(world, u):
    """The unit's `CombatStats`, built from its template and the item table on first use (None template: all zeros)."""
    st = u.combat
    if st is None:
        fx = u.fx if u.fx.any() else None
        if u.human and u.equipment and world.item_table is not None:
            from . import gear                  # a hero's own loadout replaces the template strings (sim/gear.py)
            g, load = gear.load_inputs(world, u)
            st = unit_combat_stats(u.stats, world.item_table, u.skills or None, fx=fx, gear=g, load=load) or CombatStats()
        else:
            st = unit_combat_stats(u.stats, world.item_table, u.skills or None, hard=u.tweak == 3, fx=fx) or CombatStats()
        u.combat = st
    return st


def attack_range(world, u):
    """`FUN_0056ac5b(u)`: the range every order issuer writes to `brain+0x14`: the range byte of the selected spell (`brain+0x78`, Ctrl+A;
    docs/engine/ai.md 12.8) when the book has it and `mana >= cost` (signed words), else the unit's attack range `+0x12c`."""
    base = combat_stats(world, u).range
    n = u.auto_spell
    if n and world.spell_table is not None:
        from . import spells
        sp = world.spell_table.get(n)
        if sp is not None and spells.wrapper_of(u, n) is not None and u.mana >= sp.mana_cost:
            return spells.wrapper_range(sp, spells.Wrapper(n), spells.unit_level(u, sp)) & 0xFF
    return base


def move_class(u):
    """movementType as the attack matrix reads it (humans carry -1 in data.bin and walk)."""
    return u.move_type if u.move_type in (1, 2, 3) else 1


class StructureTarget:
    """A structure (`world.objects`, kind structure / bridge) seen as an attack-order target (docs/engine/combat.md 5.5).  The exe hands the
    structure object to the same order code as a creature; everything those routines read of it is answered here: id, the anchor cell and
    sub-cell offsets (position object `obj+0x10`), token size 1 (vtable `+0x1c`, `0x541fe0`), movement class 0 (vtable `+0x20`, `0x541ff0`),
    flags `+0x4c` and state `+0x54` zero (the constructor clears `+0x4a..+0x5f`, `0x5155dd`)."""
    __slots__ = ("ob",)
    stats = None            # unit_size() -> 1
    state = 0
    move_type = 0
    hidden = False

    def __init__(self, ob):
        self.ob = ob

    id = property(lambda s: s.ob.id)
    x = property(lambda s: s.ob.x)
    y = property(lambda s: s.ob.y)
    sub_x = property(lambda s: s.ob.sub_x)
    sub_y = property(lambda s: s.ob.sub_y)
    owner = property(lambda s: s.ob.owner)
    hp = property(lambda s: s.ob.hp)


def find_target(world, tid):
    """The attack-order target lookup of command 0x19 (`0x4f52b4`): the creature table (`FUN_0052b2bd`), else the structure table
    (`FUN_0052bfa3`); None when neither has the id."""
    t = world.find_unit(tid)
    if t is None:
        ob = world.objects.get(tid)
        if ob is not None and ob.kind in ("structure", "bridge"):
            return StructureTarget(ob)
    return t


def can_order_attack(world, u, t):
    """`FUN_005711ea` != 0xffffff: the matrix of C§2.2 for attacker `u` and target `t`.  A structure is class 0 whatever the attacker (column 0
    is never 0: C§5.5), so it is always accepted."""
    if isinstance(t, StructureTarget):
        return True
    return can_attack(move_class(u), attack_range(world, u), move_class(t), attack_range(world, t))


def set_attack(world, u, t):
    """`FUN_0056d1be(unit, target)`: a member that is the target stops (`FUN_0056dba1`); else cancel, order 3, target, range, Brain mode 0
    (the executor sets mode 5 at the next group pass, C§2.3)."""
    if u is t:
        mv.fail_stop(world, u)
        return
    mv.cancel(u, world)
    u.order = mv.ATTACK_ORDER
    u.target = t.id
    u.range = attack_range(world, u)
    u.mode_go = u.mode_attack = u.mode_cast = False
    u.mode_follow = False
    u.anchor = None
    u.mover.waiting = u.mover.parked = False


def refresh_attack(world, u):
    """`FUN_00569321` case 3 -> `FUN_0056acc8`, run for every member of a group with order 0 at `tick & 15 == 6`: stop when the target is gone
    (state 0x10, a corpse, or an id the world freed), else Brain mode 5 with the target and the range."""
    t = find_target(world, u.target)
    if t is None or t.state == DEAD:
        mv.stop_unit(world, u)
        return
    if world.ai_on and combat_stats(world, u).mage and not isinstance(t, StructureTarget):
        pl = world.players.get(u.owner)
        if pl is not None and pl.human:
            from . import ai
            ai.human_attack(world, u, t)                # the player-owned mage branch of FUN_0056acc8: selected spell, mode 5, caster scan (ai.md 12.8)
            return
    u.mode_go = False
    u.mode_attack = True
    u.mode_follow = False
    u.mover.waiting = u.mover.parked = False
    u.range = attack_range(world, u)


def attack_mode(world, u):
    """Brain mode 5 (`FUN_0056eab5`): in range -> start the swing (`FUN_0056e8c3`), else approach with the follow driver (`FUN_0056ea52`)."""
    t = find_target(world, u.target)
    if t is None:
        if world.ai_on and (u.order == ai.GUARD_ORDER or ai.pool_driven(world, u)):
            u.mode_attack = False                   # a unit of a pool-driven group keeps its order; the next group pass picks a new target or the post (INFERRED)
        else:
            mv.stop_unit(world, u)                  # the id was freed (stage 5, flyer): the exe's pointer lookup fails
        return
    a, b = foot(u), foot(t)
    if u.facing == octant(a, b) and reach_gap(a, b) <= u.range:
        u.brain_order = BRAIN_SWING
        u.swing_count = 0
        u.state = STATE_ATTACK
        u.swing_target = t.id
        return
    step = mv.follow_drive(world, u, t)
    u.state = mv.MOVE_STATE
    if step:
        mv._step_or_turn(world, u)
    elif not u.mover.turning:
        mv._set_action(world, u, mv.IDLE)


def brain_swing(u):
    """Brain order 1 (`FUN_0056dca2`): state 3, count one tick, and once more than 2 ticks old with the done flag set, back to order 0."""
    u.state = STATE_ATTACK
    u.swing_count = (u.swing_count + 1) & 0xFF
    if u.swing_count > 2 and u.done:
        u.brain_order = 0
        u.state = mv.IDLE_STATE


def swing_tick(world, u):
    """State 3 of the creature tick (`FUN_0050f12c`): phase 0 starts the swing, phase 5 counts the wind-up down and resolves the hit at 0,
    phase 7 counts the recovery down and sets the done flag.  The timer is a byte."""
    st = combat_stats(world, u)
    if st.weapon_spell is not None and st.mage:     # state 3 phases 0 and 5: a mage whose weapon has a castSpell casts it instead of hitting
        if (u.phase == PHASE_START or (u.cast is None and u.phase == PHASE_WINDUP)) and u.swing_target is not None:
            u.cast = SpellCast(st.weapon_spell[0], target=u.swing_target, item_count=st.weapon_spell[1])    # +0x64 = weapon+0x84, +0x68 = weapon
        spells.cast_tick(world, u)
        return
    t = world.find_unit(u.swing_target)
    ob = world.objects.get(u.swing_target) if t is None and u.swing_target is not None else None   # FUN_00516c1f: a structure target (class dispatch)
    if u.phase == PHASE_START:
        extra = 0
        if (t is not None or ob is not None) and u.hp > 0:              # FUN_00516b2f: the start message needs both units and the attacker's HP
            from . import effects                                       # FUN_00516b2f: `FUN_005106d2(0xc)` -> the Invisibility effects get `+0x42 := 1`
            effects.end_invisibility(u)
            extra = attack_extra(attack_gap(foot(u), foot(t)) if ob is None else structure_gap(u, ob))
            if st.range > 1:                                            # message 0x72: the client's shoot action releases the arrow at ShootDelay
                effects.spawn_arrow(world, u, t if t is not None else ob)
            u.action, u.action_start_tick = mv.ATTACK, world.tick       # message 0x71: the client restarts the attack animation
            rest = st.windup + st.recovery                              # FUN_00504ab8: +0x138 = tick + +0x134 + +0x135 (the rest test, combat.md 12.5)
            u.step_end = world.tick + (rest if st.range > 1 else rest & 0xFF)   # +0x12c > 1: message 0x72 (dword); else 0x71 (byte argument)
        u.done = False
        u.phase = PHASE_WINDUP
        u.timer = (st.windup + extra) & 0xFF
    elif u.phase == PHASE_WINDUP:
        u.timer = (u.timer - 1) & 0xFF
        if u.timer == 0:
            if ob is not None:
                resolve_structure_attack(world, u, ob, st)
            elif t is not None:
                resolve_attack(world, u, t, st)
            u.phase = PHASE_RECOVERY
            delay = hero_delay(st.weapon_weight, st.reaction) if st.human and st.has_weapon else 0
            u.timer = (st.recovery + delay + world.rng.rand(3)) & 0xFF
    elif u.phase == PHASE_RECOVERY:
        u.timer = (u.timer - 1) & 0xFF
        if u.timer == 0:
            u.phase = PHASE_START
            u.done = True


def resolve_attack(world, a, t, st):
    """`FUN_00516c1f` -> `FUN_00516ceb` for a creature target (C§5.1): range gate, `take_hit`, HP (s16, may go below 0), log by the message 0x73
    rule, XP credit.  No test of the target's HP or state: a dying body and a corpse are hit (C§12.2)."""
    if a.hp <= 0 or not in_attack_range(foot(a), foot(t), a.range):
        return
    ts = combat_stats(world, t)
    res = take_hit_detail(st.record, ts.block, world.rng, human=st.human, sure_hit=st.sure_hit,
                          bless=a.bless, curse=a.curse)
    before = t.hp
    t.hp = before - res.damage                      # the exe's s16 (no wrap here: HP stays within +-32767 in play)
    if a.stats is not None:
        t.last_attacker = a.id
    if world.ai_on:
        ai.on_hit(world, a, t)                      # FUN_0056e6b8 at the end of take_hit (docs/engine/ai.md 8)
    if before > 0 or t.hp > -10:                    # message 0x73 (C§5.1 step 5)
        log(world, Damage(world.tick, a.id, t.id, res.damage, t.hp, res.roll, res.hit))
    xp.damage_credit(world, a, t, res.damage, before)
    if before > 0 and t.hp <= 0:
        log(world, Died(world.tick, t.id, a.id))


STRUCTURE_ARMOUR = 5               # FUN_005201b2: flat reduction of every structure hit


def structure_damage(rec, rng):
    """`FUN_005201b2` damage part (CONFIRMED): only the attack record's ELEMENTAL part counts: `d = emin + rand(espread)` (the spread is drawn only when
    `espread > 0`, `FUN_0051fa25`), minus 5, floored at 0.  Physical damage, to-hit and the second part are never read."""
    d = rec.elo
    if rec.esp > 0:
        d += rng.rand(rec.esp)               # FUN_0051fa25(n) = (rand15 * (n + 1)) >> 15 = rng.rand(n)
    d -= STRUCTURE_ARMOUR
    return d if d > 0 else 0


def structure_gap(a, ob):
    """`FUN_005169de` against a structure (CONFIRMED): the same routine as for creatures; the centre routines `FUN_0050d884` / `FUN_0050d8c0` read the
    position object at `obj+0x10` (for a structure its anchor, the top-left footprint cell's centre `(x << 8) + 0x80`; INFERRED that the position
    object holds the section 4 value as is) plus `(size - 1) * 0x80` with size = vtable `+0x1c`, which the structure class (vtable `0x5d1268`,
    `0x541fe0`) answers with **1** whatever its footprint, so a big building is hit from its top-left cell centre only."""
    cx = ((ob.x << 8) + ob.sub_x) & 0xFFFF
    cy = ((ob.y << 8) + ob.sub_y) & 0xFFFF
    f = foot(a)
    d = max(abs(centre_x(f) - cx), abs(centre_y(f) - cy))
    d -= (f.size + 1) * 128 - 256
    return 1 if d <= 0x180 else (d + 0x40) >> 8


def resolve_structure_attack(world, a, ob, st):
    """`FUN_00516c1f` -> `FUN_00516ea0` (CONFIRMED): nothing unless the attacker has HP > 0 and an owner and the gap is in range; then
    `structure.HP -= structure_damage` (s16; an indestructible structure (data.bin healthMax 0, server `+0x44`) takes 0) and message 0x73 when the
    structure had HP > 0 before or has HP > -10 now.  Nothing else happens at lethal damage (no block release, no removal: the exe only purges
    list entries, combat.md 5.4).  Returns the damage or None."""
    if a.hp <= 0 or a.owner is None or ob.kind not in ("structure", "bridge") or structure_gap(a, ob) > a.range:
        return None
    dmg = 0 if ob.hp_max == 0 or getattr(ob, "indestructible", False) else structure_damage(st.record, world.rng)
    before = ob.hp
    ob.hp = before - dmg
    if before > 0 or ob.hp > -10:
        log(world, Damage(world.tick, a.id, ob.id, dmg, ob.hp))
    return dmg


from . import ai, spells, xp    # noqa: E402  xp reads `combat_stats` and `log` from this module: bound at the end (circular on purpose)
