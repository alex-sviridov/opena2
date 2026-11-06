"""Spell effects (phase K2): effect objects on units, the per-tick effect pass, the effect carriers (point, area, field), cell effect slots.

Spec: docs/engine/effects.md (REA of the GOG exe, CONFIRMED unless tagged); written from the spec, not from decompiler output.
Layer 4: reads and writes `engine.world` only.

- `make_effect` = the `FUN_00519db8` switch cases that build an effect object (section 3); `release` = the rest of `FUN_00519db8` after
  the level / XP / off-map test: the carrier choice (point / area / field, missile or at once) and Teleport.
- `apply` = `FUN_0051ce12` (merge, Bless / Curse cancel), `tick_unit` = the effect pass of the creature tick (`FUN_0050f12c` -> `FUN_0051cc9f`),
  `_pulse` / `_undo` / `_switch` = `FUN_0051d175` / `FUN_0051d337` / `FUN_0051d436`.
- `point_tick` = `FUN_00517949` with an effect, `area_tick` = `FUN_00517cfe` (modes 0, 1), `field_tick` = `FUN_0051806c`, `reach` =
  `FUN_00518681`; the cell slots are `World.cell_fx` (`FUN_0055a37a` / `FUN_0055a533` / `FUN_005189b5`).
"""

from allods2.formats import spelldefs

from engine.world import Carrier, Effect

# effect flags (+0x3d)
F_DURATION, F_CONTINUOUS, F_CHARGES, F_SINGLE, F_FINISHED = 1, 2, 4, 8, 0x80
FOREVER = 0x2581                # ticks >= 9601 never count down (FUN_0051cc9f)
# spell numbers with an id-specific path
FIRE_BALL, WALL_OF_FIRE, POISON, BLIZZARD, ACID = 2, 3, 6, 7, 9
INVISIBILITY, DARKNESS, LIGHT, WALL_OF_EARTH, STONE_CURSE = 12, 14, 15, 17, 18
BLESS, CURSE, TELEPORT = 20, 28, 23
PROTECTIONS = (4, 8, 13, 19)
HASTE, SLOW, SHIELD = 21, 29, 27
STONE_BIT = 1 << STONE_CURSE    # 0x40000: Brain order 4 (the unit does nothing while it is set)
BRAIN_STONE = 4                 # brain+9 = 4 (`0x56dd24`, `0x56dfca`)
STONE_STATE = 0x1B
# stat kinds (FUN_0051d436)
K_DEFENCE, K_ABSORB, K_SPEED, K_SCAN, K_PROT0 = 15, 16, 17, 19, 20
K_HP_REGEN, K_MANA_REGEN = 8, 11             # the regeneration potions: bonus words +0xde / +0xe2 (kind 11 only on a mage, `FUN_0053a5a0`)
# cell record slots by spell (FUN_00518ba3)
CELL_SLOT = {WALL_OF_FIRE: 0, POISON: 2, WALL_OF_EARTH: 3, LIGHT: 4, DARKNESS: 5}
# what `release` builds (the damage branch covers the damage spells; 11 Prismatic Spray, 22, 24, 25, 26 are elsewhere)
BUILT = frozenset(PROTECTIONS + (POISON, INVISIBILITY, DARKNESS, LIGHT, WALL_OF_EARTH, STONE_CURSE, BLESS, CURSE, HASTE, SLOW, SHIELD,
                                 TELEPORT))


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def ftol(x):
    return int(x)


def bit(n):
    return 1 << (n & 31)


def timed(e):
    """`FUN_0051cc53`: flags & (duration | continuous)."""
    return bool(e.flags & (F_DURATION | F_CONTINUOUS))


def find(u, n):
    """`FUN_005106f4(n)`: the first effect of id `n` in the list, or None."""
    for e in u.effects:
        if e.id == n:
            return e
    return None


def active(u, n):
    """`FUN_005106d2(n)`: bit `n` of the effect mask (`unit+0x144`)."""
    return bool(u.effect_mask & bit(n))


# --- the effect object of a cast (FUN_00519db8 switch, effects.md 3) -----------------------------------------------------------------

def duration_ticks(spell, level):
    """`ftol(1.1^L * p14 * 16.0)` stored as u16 (`0x51b41c`-`0x51b453`)."""
    return ftol(1.1 ** level * spell.duration * 16.0) & 0xFFFF


def _text(spell, n):
    """`FUN_0051caa0(text)`: the first term of the modifier text (one object), flags = its time mode, ticks = time << 4 for a timed mode."""
    m = spell.modifiers[0] if spell.modifiers else None
    if m is None:
        return Effect(n)
    e = Effect(n, kind=m.kind, flags=m.mode, value=m.value)
    if m.mode & (F_DURATION | F_CONTINUOUS | F_CHARGES):
        e.value = s16(e.value)
        e.ticks = (m.time << 4) & 0xFFFF
    return e


def make_effect(world, spell, level, learned, target):
    """The switch case of a non-damage spell: the effect template, or None when the cast ends with no effect (Invisibility / Stone Curse with 0 ticks).
    `learned`: a learned spell (caster `+0x68 == 0`); `target`: the target unit (Stone Curse's protection draw)."""
    n = spell.number
    if n in PROTECTIONS:
        e = _text(spell, n)
        e.flags |= F_DURATION
        e.value = s16(level // 2)
        e.ticks = duration_ticks(spell, level)
    elif n == POISON:
        e = _text(spell, n)
        e.value = s16(ftol(e.value * (level / 45.0 + 1.0)))
    elif n == INVISIBILITY:
        e = Effect(n, flags=F_DURATION, ticks=(level << 4) & 0xFFFF)
        if e.ticks == 0:
            return None
    elif n == DARKNESS:
        e = _text(spell, n)
        e.value = s16(-1 - level // 30)
    elif n == LIGHT:
        e = _text(spell, n)
        e.value = s16(level // 30 + 1)
    elif n == WALL_OF_EARTH:
        e = Effect(0)                                   # plain, id 0 (`0x51b1de`): the carrier skips it
    elif n == STONE_CURSE:
        e = _text(spell, n)
        e.flags |= F_DURATION
        e.ticks = (level * 0xF0 * (2 if learned else 1) // 100) & 0xFFFF
        if target is not None:                          # vtable +0x2c: a creature
            from .combat import combat_stats
            pe = combat_stats(world, target).block.prot[4]
            e.ticks = world.rng.rand(e.ticks * (100 - pe) // 100) & 0xFFFF
            if e.ticks == 0:
                return None
    elif n in (BLESS, CURSE):
        e = Effect(n, flags=F_DURATION, value=s16(level * 4 // 5 + 20), ticks=duration_ticks(spell, level))
    elif n in (HASTE, SLOW):
        e = _text(spell, n)
        e.flags |= F_DURATION
        e.value = s16(level // 15 + 1)
        if n == SLOW:
            e.value = -e.value
        e.ticks = duration_ticks(spell, level)
    elif n == SHIELD:
        e = _text(spell, n)
        e.flags |= F_DURATION
        e.value = s16(level // 10 + 3)
        e.ticks = duration_ticks(spell, level)
    else:                                               # default case 0x51ba22: plain effect with the spell's id
        e = Effect(n)
    if n != WALL_OF_EARTH:
        e.id = n
    return e


# --- apply, tick, stat changes (FUN_0051ce12, FUN_0051cc9f, FUN_0051d175 / d337 / d436) --------------------------------------------------

def _mirror_add(u, e):
    if e.id == INVISIBILITY:
        u.hidden = True
    elif e.id == BLESS:
        u.bless = e.value
    elif e.id == CURSE:
        u.curse = e.value


def _mirror_remove(u, e):
    if e.id == INVISIBILITY:
        u.hidden = False
    elif e.id == BLESS:
        u.bless = None
    elif e.id == CURSE:
        u.curse = None


def apply(world, u, t):
    """`FUN_0051ce12(unit)` with template `t` (effects.md 4)."""
    if timed(t) and t.id in (BLESS, CURSE):
        e = find(u, CURSE if t.id == BLESS else BLESS)
        if e is not None:                               # they cancel each other; the new one is not added
            u.effect_mask &= ~bit(e.id)
            _undo(world, u, e)
            u.effects.remove(e)
            _mirror_remove(u, e)
            return
    if not timed(t):
        _pulse(world, u, t)
        return
    e = find(u, t.id)
    if e is None:
        c = t.copy()
        if c.id != POISON:
            _pulse(world, u, c)
        u.effects.append(c)
        u.effect_mask |= bit(c.id)
        _mirror_add(u, c)
    else:                                               # merge: the larger value (signed) and the longer time (u16), never a stack
        _undo(world, u, e)
        e.value = max(s16(e.value), s16(t.value))
        e.ticks = max(e.ticks, t.ticks)
        if e.id != POISON:
            _pulse(world, u, e)
        _mirror_add(u, e)


def tick(world, u, e):
    """`FUN_0051cc9f(unit)`: a continuous effect acts when `ticks & 7 == 0`; then the countdown (not at >= 0x2581); at 0: undo (not for a
    continuous one), the mask bit cleared, finished."""
    if not timed(e):
        return
    if e.flags & F_CONTINUOUS and (e.ticks & 7) == 0:
        _pulse(world, u, e)
    if e.ticks < FOREVER:
        e.ticks = (e.ticks - 1) & 0xFFFF
        if e.ticks == 0:
            if not e.flags & F_CONTINUOUS:
                _undo(world, u, e)
            u.effect_mask &= ~bit(e.id)
            e.flags |= F_FINISHED


def tick_unit(world, u):
    """The effect pass at the top of the creature tick (`FUN_0050f12c` `0x50f162`): every effect in list order ticks, a finished one is
    removed.  Also ends the engine's legacy `invis_ending` flag (a unit made hidden without an effect object)."""
    if u.effects:
        for e in list(u.effects):
            tick(world, u, e)
            if e.flags & F_FINISHED:
                u.effects.remove(e)
                _mirror_remove(u, e)
    if u.invis_ending:
        u.invis_ending = False
        if find(u, INVISIBILITY) is None:
            u.hidden = False


def end_invisibility(u):
    """`FUN_00516b2f` (swing start) and `FUN_00519998` (a cast at another unit): every Invisibility effect gets `+0x42 := 1`, so the next
    effect pass ends it."""
    if u.hidden or active(u, INVISIBILITY):
        for e in u.effects:
            if e.id == INVISIBILITY:
                e.ticks = 1
        u.invis_ending = True


def _water_protection(world, u):
    from .combat import combat_stats
    return combat_stats(world, u).block.prot[2]


def _pulse(world, u, e):
    """`FUN_0051d175`: Poison takes HP (water protection, rounding + 0.5), Light lowers a non-human's scan, Darkness a human's; the rest goes
    through the stat switch with +1."""
    if e.id == POISON:
        d = -s16(e.value)
        p = _water_protection(world, u)
        if p != 0:
            d = ftol(d * (100 - p) / 100.0 + 0.5)
        if d != 0:
            from . import xp
            from .combat import log
            from engine.world import Damage, Died
            before = u.hp
            u.hp = before - d
            caster = world.units.get(e.caster) if e.caster is not None else None
            if e.caster is not None and (caster is None or caster.hp < 0):
                e.caster = None                         # FUN_00542770: the caster's HP < 0 drops it (a removed caster: INFERRED the same)
                caster = None
            if caster is not None:
                xp.damage_credit(world, caster, u, d, before, spell=POISON)
            log(world, Damage(world.tick, e.caster, u.id, d, u.hp, 0, True))
            if before > 0 and u.hp <= 0:
                log(world, Died(world.tick, u.id, e.caster))
    elif e.id == LIGHT:
        if not u.human:
            u.fx.scan -= s16(e.value)
    elif e.id == DARKNESS:
        if u.human:
            u.fx.scan += s16(e.value)
            u.fx.scan_direct += s16(e.value)
    else:
        _switch(world, u, e, 1)


def _undo(world, u, e):
    """`FUN_0051d337`: the reverse of `_pulse` for Light / Darkness, nothing for Poison, else the stat switch with -1."""
    if e.id == LIGHT:
        if not u.human:
            u.fx.scan += s16(e.value)
    elif e.id == DARKNESS:
        if u.human:
            u.fx.scan -= s16(e.value)
            u.fx.scan_direct -= s16(e.value)
    elif e.id != POISON:
        _switch(world, u, e, -1)


def _switch(world, u, e, sign):
    """`FUN_0051d436(unit, sign)` for the kinds spells produce (effects.md 5), then the recompute (vtable +0x58).  Other kinds (item modifiers)
    are applied by `combatstats` from the equipment, not here."""
    fx = u.fx
    if u.human and fx.speed > 24:                       # `if unit+0xd8 > 24: unit+0xd8 := 0` (the bonus word; a monster's stays 0)
        fx.speed = 0
    a = sign * (s16(e.value) if e.flags & (F_DURATION | F_CONTINUOUS | F_CHARGES) else e.value)
    k = e.kind
    st = None if u.human else _monster_stats(world, u)
    if k == K_DEFENCE:
        if u.human:
            fx.defence += a
        else:
            new = max(0, st.block.defence + a)
            fx.defence += new - st.block.defence
            st.block.defence = new
    elif k == K_ABSORB:
        if u.human:
            fx.absorb = max(0, fx.absorb + a)           # DECISION: the clamp of the bonus word without the equipment's part (no spell lowers it)
        else:
            fx.absorb += a
            st.block.absorb = s16(st.block.absorb + a)
    elif k == K_SPEED:
        fx.speed += a
    elif k == K_SCAN:
        fx.scan += a
    elif K_PROT0 <= k < K_PROT0 + 6:
        fx.prot[k - K_PROT0] = max(0, fx.prot[k - K_PROT0] + a)
    elif k == K_HP_REGEN:
        fx.hp_regen += a
    elif k == K_MANA_REGEN and _monster_stats(world, u).mage:
        fx.mana_regen += a
    _recompute(world, u)


def _monster_stats(world, u):
    from .combat import combat_stats
    return combat_stats(world, u)


def _recompute(world, u):
    """vtable +0x58: a human's `FUN_0051366b` rebuilds the combat numbers from the template, the equipment and the bonus words (the engine drops
    its cached `CombatStats`), and `FUN_005113e7` zeroes the speed bonus when the sum is negative; `+0xa4 = base + bonus` drops Darkness's direct
    part.  A monster's (`FUN_005118be`) touches only the mana regeneration: the direct changes stay."""
    if not u.human:
        return
    u.combat = None
    from . import movement as mv
    if mv.unit_speed(u) < 0:
        u.fx.speed = 0
    u.fx.scan_direct = 0


# --- carriers (effects.md 6) ---------------------------------------------------------------------------------------------------------------

def _target_pos(t):
    """The position the carrier uses for a unit target: its position in 1/256 cell; a footprint larger than 1 cell: its centre - 1 per axis."""
    from .pathfinding import centre_x, centre_y, foot, unit_size
    if unit_size(t) > 1:
        f = foot(t)
        return (centre_x(f) & 0xFFFF) - 1, (centre_y(f) & 0xFFFF) - 1
    return t.x * 256 + t.sub_x, t.y * 256 + t.sub_y


def release(world, u, spell, level, t=None, cell=None, learned=True):
    """`FUN_00519db8` from the switch on, for the spells this module builds (`BUILT` and the damage spells whose `distribution != 1`).
    Returns the new carrier (or True when the cast ended without one), None when the spell is not built here."""
    from . import spells as sp
    n = spell.number
    sc = spell.scaled(level)
    damage = (sc.damage_min & 0xFF) + (sc.damage_spread & 0xFF) != 0 and n not in (sp.HEAL, sp.DRAIN_LIFE)
    if damage:
        if spell.distribution == spelldefs.DIST_SINGLE:
            return None                                 # the phase I missile / point path of spells.cast_release
    elif n not in BUILT:
        return None
    if n == TELEPORT and not damage:
        dest = cell if t is None else (t.x, t.y)
        teleport(world, u, dest[0] & 0xFF, dest[1] & 0xFF)
        return True
    eff = None
    if not damage:
        eff = make_effect(world, spell, level, learned, t)
        if eff is None:
            return True
        eff.caster = u.id
    hostile = spell.defensive != 1                      # carrier +0x41 = (wrapper +0xa == 0)
    start = (u.x * 256 + u.sub_x, u.y * 256 + u.sub_y)
    if t is not None:
        pos = _target_pos(t)
    else:
        pos = (cell[0] * 256 + 128, cell[1] * 256 + 128)       # INFERRED: FUN_0054f9b9 puts a cell's position at its centre
    centre = ((pos[0] >> 8) & 0xFF, (pos[1] >> 8) & 0xFF)
    uid = world.next_carrier_id()
    if spell.distribution == spelldefs.DIST_SINGLE:
        if t is None:
            return True                                 # "Spell: oops, can't cast point effect": nothing
        c = Carrier(uid, "point", u.id, t.id, n, level, 0, world.tick, hostile, start, 0, pos, effect=eff)
    else:
        life = s16(spell.area_duration << 4)
        mode = 0
        if life != 0:
            life = s16(life + (level << 4) // 10)
            mode = 1
        if spell.distribution == spelldefs.DIST_FIELD:
            mode, life = 2, 0
        direction = spelldefs.direction8(centre[0] - u.x, centre[1] - u.y)
        c = Carrier(uid, "field" if mode == 2 else "area", u.id, t.id if t is not None else None, n, level, 0, world.tick, hostile, start, 0, pos,
                    effect=eff, centre=centre, radius=spell.radius & 0xFF, mode=mode, life=life, direction=direction)
    if spell.delivery == spelldefs.DELIVERY_MISSILE:
        flight = (sp.distance(pos[0] - start[0], pos[1] - start[1]) // spell.speed) & 0xFFFF     # FUN_00518d1e: (s16) distance / speed
        c.ticks_left = c.flight = flight
        c.kind = "missile"
    world.carriers.append(c)
    return c


def landed(world, c):
    """The carrier a missile appends when it lands (`FUN_00542e60`): its point or area carrier."""
    kind = "point" if c.centre is None else ("field" if c.mode == 2 else "area")
    return Carrier(world.next_carrier_id(), kind, c.caster, c.target, c.spell, c.level, 0, c.born, c.hostile, c.start, c.flight, c.aim,
                   effect=c.effect, centre=c.centre, radius=c.radius, mode=c.mode, life=c.life, direction=c.direction)


def teleport(world, u, x, y):
    """`FUN_0055a96c(unit, x, y)` (spell case 0x17 `0x51a554`, instant 27, the Teleport cell records of sim/traps.py): when the cell passes the
    free test `FUN_0055a928` (= `FUN_005563ca`'s two layers at that cell; the unit's own stamps count, so its own cell is never free) the unit is
    released (`FUN_00553891`), moved to the cell centre and placed again (`FUN_0055020a`: a cell record effect there fires), then
    `FUN_0056dba1` = cancel + stand (order 0xc, anchor the new cell, Brain mode 0, `brain+0x50 := 0`: a move group's pass restarts it).
    Corrected: the stand at `0x55a9f8` was missed before.  The brain order (a cast in progress) is untouched, so a caster's recovery runs on.
    `FUN_00502019` is the client update."""
    from . import triggers
    if u.id not in world.units or not triggers._free(world, u, x, y):
        return False
    world._index_del(world._ucells, u)
    world.release(u)
    m = u.mover
    m.step_target = m.step_from = None
    m.steps = m.step_ticks = 0
    u.x, u.y, u.sub_x, u.sub_y = x, y, 128, 128         # INFERRED: the centre of the cell (FUN_0054fbf7)
    world._index_add(world._ucells, u)
    world.slots.place(u)
    from . import movement as mv
    mv.set_stand(world, u)                              # FUN_0056dba1 (0x55a9f8)
    return True


def point_tick(world, c):
    """`FUN_00517949` for an effect: the apply on a target still in the world, then for a hostile spell with a caster the last attacker, the
    spell number and the hit reaction (area flag 0)."""
    from . import ai
    t = world.find_unit(c.target)
    if t is None:
        return
    apply(world, t, c.effect)
    caster = world.units.get(c.caster)
    if c.hostile and caster is not None:
        t.last_attacker = caster.id
        if world.ai_on:
            ai.on_hit(world, caster, t)


def _occupants(world, x, y, both):
    """The units of the cell record: the ground occupant (`rec+4`, `FUN_0055201a` / `FUN_00551edb`) and, with `both`, the air occupant
    (`rec+8`, `FUN_00552079`).  Structures (`FUN_00559b7f`) are not modelled as targets."""
    from engine.cellslots import pack
    idx = pack(x, y)
    out = []
    g = world.slots.occ[0].get(idx)
    if g is not None and g in world.units:
        out.append(world.units[g])
    if both:
        a = world.slots.occ[1].get(idx)
        if a is not None and a in world.units:
            out.append(world.units[a])
    return out


def _damage(world, c, t, record):
    """`FUN_0051e65b`: the elemental hit (`take_hit`), HP, the caster's XP credit for the spell (`FUN_00513128(victim, dmg, spell)`)."""
    from . import xp
    from .combat import combat_stats, log, take_hit_detail
    from engine.world import Damage, Died
    caster = world.units.get(c.caster)
    res = take_hit_detail(record, combat_stats(world, t).block, world.rng)
    before = t.hp
    t.hp = before - res.damage
    if before > 0 or t.hp > -10:
        log(world, Damage(world.tick, c.caster, t.id, res.damage, t.hp, res.roll, True))
    if caster is not None:
        xp.damage_credit(world, caster, t, res.damage, before, spell=c.spell)
    if before > 0 and t.hp <= 0:
        log(world, Died(world.tick, t.id, c.caster))


def reach(world, c, t):
    """`FUN_00518681(unit)`: an area or field reaches a unit: nothing for Wall of Earth; Fire Ball hits with min' and spread' divided by size^2;
    a damage carrier hits; an effect is applied.  Then (not Light) the last attacker (not Darkness) and the hit reaction with the area flag."""
    from . import ai
    from . import spells as sp
    from .pathfinding import unit_size
    if t is None or c.spell == WALL_OF_EARTH:
        return
    if c.effect is None:
        rec = sp.spell_record(world.spell_table.get(c.spell), c.level)
        if c.spell == FIRE_BALL:
            s = unit_size(t)
            rec.elo, rec.esp = (rec.elo & 0xFF) // (s * s), (rec.esp & 0xFF) // (s * s)
        _damage(world, c, t, rec)
    else:
        apply(world, t, c.effect)
    if c.spell == LIGHT or c.caster is None:
        return
    caster = world.units.get(c.caster)
    if caster is None:
        t.last_attacker = None
        return
    if c.spell != DARKNESS:
        t.last_attacker = caster.id
    if world.ai_on:
        ai.on_hit(world, caster, t, area=True)


def _slot(spell):
    return CELL_SLOT.get(spell, 0)


def _holds(world, c, x, y):
    """`FUN_0055a8f8`: the cell's slot of the carrier's spell holds this carrier."""
    v = world.cell_fx.get((x, y))
    return v is not None and v[_slot(c.spell)] == c.uid


def _unstamp(world, uid, spell, x, y):
    """`FUN_0055a533`: the slot is cleared when it holds that carrier."""
    v = world.cell_fx.get((x, y))
    k = _slot(spell)
    if v is not None and v[k] == uid:
        world.set_cell_fx(x, y, k, None)


def _carrier_spell(world, uid):
    for c in world.carriers:
        if c.uid == uid:
            return c.spell
    return None


def _interact(world, spell, x, y):
    """`FUN_005189b5`: fire removes a poison cloud (and slot 1, never used); poison on a fire wall removes itself; Light and Darkness on one cell
    remove each other and themselves."""
    v = world.cell_fx.get((x, y))
    if v is None:
        return
    if spell in (FIRE_BALL, WALL_OF_FIRE):
        if v[2] is not None:
            _unstamp(world, v[2], POISON, x, y)
        v = world.cell_fx.get((x, y))
        if v is not None and v[1] is not None:
            world.set_cell_fx(x, y, 1, None)
    elif spell == POISON:
        if v[0] is not None and v[2] is not None:
            _unstamp(world, v[2], POISON, x, y)
    elif spell == DARKNESS:
        if v[4] is not None:
            a, b = v[5], v[4]
            if a is not None:
                _unstamp(world, a, DARKNESS, x, y)
            _unstamp(world, b, LIGHT, x, y)
    elif spell == LIGHT:
        if v[5] is not None:
            a, b = v[4], v[5]
            if a is not None:
                _unstamp(world, a, LIGHT, x, y)
            _unstamp(world, b, DARKNESS, x, y)


def _damage_spread(world, c):
    """The carrier's effect is an `Effect_DirectDamage` with spread' (`+0x5c`) != 0 (the scorch / interaction flag)."""
    if c.effect is not None:
        return False
    return (world.spell_table.get(c.spell).scaled(c.level).damage_spread & 0xFF) != 0


def _stamp_cell(world, c, x, y, dmg):
    """`FUN_005184bf`: not on a structure cell whose static block has bit 4; Wall of Earth only on a cell without a ground occupant; else the
    carrier takes the cell's slot, then the interactions (the scorch of a damage carrier only marks the ground: not modelled)."""
    from engine.cellslots import pack
    if not (0 <= x < world.width and 0 <= y < world.height):
        return
    if any(world.objects[i].kind != "object" for i in world.objects_at(x, y)) and world.block[y, x] & 4:
        return
    if c.spell == WALL_OF_EARTH:
        if world.slots.occ[0].get(pack(x, y)) is None:
            world.set_cell_fx(x, y, _slot(c.spell), c.uid)
        return
    world.set_cell_fx(x, y, _slot(c.spell), c.uid)
    if c.spell == WALL_OF_FIRE:
        world.scorch(x, y)                                  # the client flag of spell 3 sets the burnt-ground tile bit once (`FUN_0041c18c`)
    _interact(world, c.spell, x, y)


def _stamp(world, c):
    """`FUN_00518024`: the wall (`distribution == 4`, `FUN_005182b6`) or the diamond `|dx| + |dy| <= r + 1` of the square (`FUN_005183a2`)."""
    spell = world.spell_table.get(c.spell)
    dmg = _damage_spread(world, c)
    if spell.distribution == spelldefs.DIST_WALL:
        for x, y in spelldefs.wall_cells(c.centre, c.direction):
            _stamp_cell(world, c, x & 0xFF, y & 0xFF, dmg)
    else:
        r = c.radius
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if abs(dx) + abs(dy) <= r + 1:
                    _stamp_cell(world, c, (c.centre[0] + dx) & 0xFF, (c.centre[1] + dy) & 0xFF, dmg)
    c.stamped = True


def _square(c):
    cx, cy = c.centre
    r = c.radius
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            yield (cx + dx) & 0xFF, (cy + dy) & 0xFF


def area_tick(world, c):
    """`FUN_00517cfe` for modes 0 and 1.  Returns True when the carrier is done."""
    if c.mode == 0:                                     # FUN_00518833: once over the square, both occupants (and the structure)
        if c.spell == FIRE_BALL:
            spawn_explosion(world, c.centre)            # FUN_005045a5(c, 1): message 0x86, projectile 13 at the centre cell, 22 ticks
        dmg = _damage_spread(world, c)
        for x, y in _square(c):
            for t in _occupants(world, x, y, True):
                if t.id in world.units:
                    reach(world, c, t)
            if dmg:
                _interact(world, c.spell, x, y)
        return True
    if not c.stamped:
        _stamp(world, c)
        return False
    if c.life == 0:                                     # FUN_00518594: unstamp the square
        for x, y in _square(c):
            _unstamp(world, c.uid, c.spell, x, y)
        return True
    c.life = s16(c.life - 1)
    if (c.life & 0xF) == 0:
        for x, y in _square(c):
            if _holds(world, c, x, y):
                for t in _occupants(world, x, y, False):
                    reach(world, c, t)
    return False


def field_tick(world, c):
    """`FUN_0051806c` (Blizzard 7, Acid Stream 9; spells.md 9b): a step when the counter reads 0 (then 2 again): Blizzard one stone at
    `centre + (rand(0..5) - 2, rand(0..5) - 2)` (32 steps), Acid Stream the rows of step `+0x4f` (6 steps); each valid cell reaches both
    occupants (and the structure).  Returns True when the carrier is done."""
    s = c.life
    c.life = s16(c.life - 1)
    if s != 0:
        return False
    c.life = 2
    if c.spell == BLIZZARD:
        ox = world.rng.rand(5) - 2
        oy = world.rng.rand(5) - 2
        cells = [((c.centre[0] + ox) & 0xFF, (c.centre[1] + oy) & 0xFF)]
        total = spelldefs.BLIZZARD_STONES
    elif c.spell == ACID:
        cells = [(x & 0xFF, y & 0xFF) for x, y in spelldefs.acid_cells(c.centre, c.direction, c.step)] if c.step < spelldefs.ACID_STEPS else []
        total = spelldefs.ACID_STEPS
    else:
        cells, total = [], 0
    for x, y in cells:
        if spelldefs.cell_valid(x, y, world.width, world.height):
            for t in _occupants(world, x, y, True):
                if t.id in world.units:
                    reach(world, c, t)
    c.step = (c.step + 1) & 0xFF
    return total <= c.step


# --- the Brain side of Stone Curse (0x56dd24, 0x56dfca) -------------------------------------------------------------------------------------

def stone_check(u):
    """Pre-check (c) of the Brain tick: the Stone Curse bit with no brain order (a step in progress is the exe's brain order 3) -> order 4."""
    if u.effect_mask & STONE_BIT and u.brain_order == 0 and not u.mover.step_ticks:
        u.brain_order = BRAIN_STONE


def brain_stone(u):
    """Brain order 4: state 0x1b; when the bit has cleared, back to order 0."""
    u.state = STONE_STATE
    if not u.effect_mask & STONE_BIT:
        u.brain_order = 0


def scan_range(u, base):
    """The scan byte `+0xa5` the sight flood reads (unsigned): the template value plus the scan changes of the effects, wrapped to a byte."""
    return (base + u.fx.scan + u.fx.scan_direct) & 0xFF


# --- the client fire explosion (projectile 13, docs/mechanics/lighting.md 3, docs/formats/animation.md 4.4) -----------------------------

EXPLOSION_LIFE = 22         # message byte `0x16` of `FUN_005045a5`; `obj+0xa8` counts it down, the tick returns "remove" when it is 0 on entry
EXPLOSION_QUEUE_AGE, EXPLOSION_SCORCH_AGE = 4, 8        # `FUN_0046c1d0` case 0xd: `obj+0x9c` (age, -1 at creation, +1 per tick) == 4 / == 8


def spawn_explosion(world, cell):
    """`FUN_005045a5` for spell 2 -> client message 0x86 handler `0x414f00`-`0x4151c1`: projectile 13 at the cell centre (`cell * 256 + 128`), age -1,
    `+0xa8` = 22.  CONFIRMED (the id `+0xe` of the carrier being 13 = `2n + 9` is INFERRED, spells.md 7)."""
    from engine.world import Explosion
    world.explosions.append(Explosion(cell[0], cell[1], world.tick, EXPLOSION_LIFE))


def explosion_system(world, commands=()):
    """The client tick of every explosion after the carriers of the same tick (age 0 on the creation tick, INFERRED order): at age 4 each of the
    3 x 3 cells without tile bit `0x2000` is queued in the burning list when it holds a map object (the draw then needs its `DeadObject`, `lights.burns`)
    or is water (tile `& 0x1fff >> 6` in 8..11); at age 8 bit `0x2000` is set on every cell that is not water or holds an object (`0x46c5bf`-`0x46c871`).
    CONFIRMED `FUN_0046c1d0`."""
    if not world.explosions:
        return
    keep = []
    for e in world.explosions:
        age = world.tick - e.born
        if age == EXPLOSION_QUEUE_AGE:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    x, y = e.x + dx, e.y + dy
                    if not (0 <= x < world.width and 0 <= y < world.height) or world.cells[y, x] & 0x2000:
                        continue
                    water = 8 <= (int(world.cells[y, x]) & 0x1FFF) >> 6 < 12
                    obj = any(world.objects[i].kind == "object" for i in world.objects_at(x, y))
                    if obj or water:
                        world.burn_fx = {c: v for c, v in world.burn_fx.items() if world.tick - v[0] < 22}
                        world.burn_fx[(x, y)] = (world.tick, water)
        elif age == EXPLOSION_SCORCH_AGE:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    x, y = e.x + dx, e.y + dy
                    if not (0 <= x < world.width and 0 <= y < world.height):
                        continue
                    water = 8 <= (int(world.cells[y, x]) & 0x1FFF) >> 6 < 12
                    obj = any(world.objects[i].kind == "object" for i in world.objects_at(x, y))
                    if not water or obj:
                        world.scorch(x, y, burn=False)
        if age <= e.life:                           # the view draws ages 0 .. life - 1; kept one tick longer so the last frame is still drawn
            keep.append(e)
    world.explosions = keep
