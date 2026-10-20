"""Spell effects (phase K2): effect objects, merge, expiry, stat hooks, Stone Curse, Invisibility, point / area / field carriers, cell slots.
Synthetic worlds, always run.  Spec: docs/engine/effects.md (E§n)."""

from engine.cellslots import pack
from engine.rng import Rng
from engine.sim import CastSpell, Simulation, ai, effects, movement, spells
from engine.world import CastStarted, Damage, Effect

from spell_helpers import effect_table
from test_engine_ai import run
from test_engine_ai_casting import hero, mask, monster, world as cast_world


def world(seed=1, ai_on=False):
    w = cast_world(seed, ai_on)
    w.spell_table = effect_table()
    return w


def sp(w, n):
    return w.spell_table.get(n)


def give(w, u, n, level=30, caster=None, learned=True):
    """Build the effect of spell `n` at `level` and apply it (a point carrier's apply, E§4)."""
    e = effects.make_effect(w, sp(w, n), level, learned, u)
    if e is not None:
        e.caster = caster.id if caster is not None else None
        effects.apply(w, u, e)
    return e


def creature_pass(w, u, n=1):
    for _ in range(n):
        movement._tick_unit(w, u)


# --- the handlers (E§3) --------------------------------------------------------------------------------------------------------------

def test_handler_values_and_durations():
    w = world()
    m = monster(w, 1, 20, 20)
    e = effects.make_effect(w, sp(w, 27), 40, True, m)                         # Shield: L/10 + 3, ftol(1.1^40 * 20 * 16)
    assert (e.id, e.kind, e.flags, e.value, e.ticks) == (27, 16, 1, 7, 14482)
    e = effects.make_effect(w, sp(w, 21), 30, True, m)                         # Haste: L/15 + 1, ftol(1.1^30 * 10 * 16)
    assert (e.kind, e.value, e.ticks) == (17, 3, 2791)
    assert effects.make_effect(w, sp(w, 29), 30, True, m).value == -3        # Slow negated
    assert effects.make_effect(w, sp(w, 4), 31, True, m).value == 15          # protection L/2, kind 21
    assert effects.make_effect(w, sp(w, 4), 31, True, m).kind == 21
    b = effects.make_effect(w, sp(w, 20), 50, True, m)                         # Bless: plain, kind 0, L*4/5 + 20
    assert (b.kind, b.value) == (0, 60)
    i = effects.make_effect(w, sp(w, 12), 7, True, m)                          # Invisibility: L << 4
    assert (i.id, i.ticks) == (12, 112) and effects.make_effect(w, sp(w, 12), 0, True, m) is None
    p = effects.make_effect(w, sp(w, 6), 30, True, m)                          # Poison: ftol(-2 * (30/45 + 1)), continuous 8 -> 128 ticks
    assert (p.kind, p.flags, p.value, p.ticks) == (6, 2, -3, 128)
    assert effects.make_effect(w, sp(w, 14), 60, True, m).value == -3         # Darkness -1 - L/30
    assert effects.make_effect(w, sp(w, 15), 60, True, m).value == 3          # Light L/30 + 1
    assert effects.make_effect(w, sp(w, 17), 60, True, m).id == 0             # Wall of Earth: id 0


def test_stone_curse_ticks_learned_item_and_the_protection_draw():
    for seed in range(1, 40):
        w = world(seed)
        m = monster(w, 1, 20, 20)
        ref = Rng(seed)
        want = ref.rand(240)                                                    # 50 * 240 * 2 / 100 = 240, then rand(0..240 * 100 / 100)
        e = effects.make_effect(w, sp(w, 18), 50, True, m)
        if want == 0:
            assert e is None                                                    # a draw of 0: no effect
            continue
        assert e.ticks == want and (e.kind, e.value) == (16, 5)                # the first term only: absorption +5
        m.combat.block.prot[4] = 50
        want = ref.rand(60)                                                     # an item cast: * 1 -> 120, earth protection 50 -> rand(0..60)
        e = effects.make_effect(w, sp(w, 18), 50, False, m)
        assert (e is None) if want == 0 else e.ticks == want


# --- apply, merge, cancel, tick (E§4, E§2.1) -----------------------------------------------------------------------------------------

def test_same_spell_merges_by_max_value_and_max_time_never_stacks():
    w = world()
    m = monster(w, 1, 20, 20)
    give(w, m, 21, 30)                                                          # Haste +3
    give(w, m, 21, 15)                                                          # Haste +2, shorter
    assert len(m.effects) == 1 and m.effects[0].value == 3 and m.effects[0].ticks == 2791 and m.fx.speed == 3
    give(w, m, 29, 60)                                                          # Slow -5: another id, applies on top
    give(w, m, 29, 30)                                                          # a weaker Slow (-3) RAISES the value (signed max)
    slow = effects.find(m, 29)
    assert slow.value == -3 and m.fx.speed == 0 and movement.unit_speed(m) == 24


def test_bless_and_curse_cancel_each_other():
    w = world()
    m = monster(w, 1, 20, 20)
    give(w, m, 28, 30)
    assert m.curse == 44 and effects.active(m, 28)
    give(w, m, 20, 30)                                                          # removes the Curse, adds nothing
    assert m.curse is None and m.bless is None and not m.effects and m.effect_mask == 0
    give(w, m, 20, 30)
    assert m.bless == 44 and m.effect_mask == 1 << 20


def test_expiry_undoes_the_change_and_clears_the_bit_in_the_creature_pass():
    w = world()
    m = monster(w, 1, 20, 20)
    e = Effect(21, kind=17, flags=1, value=4, ticks=3)
    effects.apply(w, m, e)
    assert movement.unit_speed(m) == 28 and effects.active(m, 21)
    creature_pass(w, m, 2)
    assert effects.active(m, 21) and m.effects[0].ticks == 1
    creature_pass(w, m)
    assert not m.effects and m.effect_mask == 0 and movement.unit_speed(m) == 24 and m.fx.speed == 0


def test_ticks_from_0x2581_never_count_down():
    w = world()
    m = monster(w, 1, 20, 20)
    effects.apply(w, m, Effect(27, kind=16, flags=1, value=5, ticks=0x2581))
    creature_pass(w, m, 50)
    assert m.effects[0].ticks == 0x2581 and m.combat.block.absorb == 5


def test_poison_pulses_every_8_ticks_with_water_protection_and_no_undo():
    w = world()
    m = monster(w, 1, 20, 20, hp=100)
    m.combat.block.prot[2] = 50
    give(w, m, 6, 30)                                                           # value -3: ftol(3 * 50 / 100.0 + 0.5) = 2 per pulse
    assert m.hp == 100                                                          # the apply waits for the first tick (id 6)
    for _ in range(128):
        creature_pass(w, m)
    assert m.hp == 100 - 16 * 2 and not m.effects and m.effect_mask == 0       # ticks 128, 120 .. 8: 16 pulses


# --- stat hooks (E§5) ------------------------------------------------------------------------------------------------------------------

def test_shield_on_a_monster_is_direct_and_protection_changes_nothing():
    w = world()
    m = monster(w, 1, 20, 20)
    give(w, m, 27, 40)
    assert m.combat.block.absorb == 7
    m.combat = None                                                             # a rebuild (revive) keeps the effect's delta
    assert spells.__name__ and ai.cb.combat_stats(w, m).block.absorb == 7
    give(w, m, 4, 40)                                                           # Protection from Fire: the bonus word is never merged
    assert ai.cb.combat_stats(w, m).block.prot[1] == 0 and effects.active(m, 4)


def test_light_lowers_a_monsters_scan_darkness_a_humans_and_the_byte_wraps():
    w = world()
    m = monster(w, 1, 20, 20, scan=6)
    give(w, m, 15, 60)                                                          # Light +3: monsters see less
    assert ai._scan_range(m) == 3
    give(w, m, 14, 60)                                                          # Darkness: humans only
    assert ai._scan_range(m) == 3
    effects.apply(w, m, Effect(15, kind=19, flags=1, value=9, ticks=16))       # merge to 9: 6 - 9 wraps to 253 (the unsigned byte +0xa5)
    assert ai._scan_range(m) == (6 - 9) & 0xFF


def test_haste_after_the_order_does_not_change_the_group_speed():
    w = world()
    m = monster(w, 1, 20, 20)
    give(w, m, 21, 30)
    assert movement.unit_speed(m) == 27                                         # simulation.md 11.1: the group byte is not recomputed


# --- Invisibility and Stone Curse (E§7) --------------------------------------------------------------------------------------------------

def test_invisibility_hides_and_a_cast_at_another_unit_ends_it_at_the_next_pass():
    w = world()
    m = monster(w, 1, 20, 20, known=mask(1), mana=50, mind=30, skills=(30,) * 5)
    t = hero(w, 2, 22, 20)
    give(w, m, 12, 30)
    assert m.hidden and effects.active(m, 12)
    from engine.world import SpellCast
    assert spells.cast_start(w, m, SpellCast(1, target=t.id), m.combat)        # FUN_00519998: +0x42 := 1
    assert m.hidden and m.effects[0].ticks == 1
    creature_pass(w, m)
    assert not m.hidden and not m.effects


def test_stone_curse_freezes_the_unit_until_the_bit_clears():
    w = world()
    m = monster(w, 1, 20, 20)
    effects.apply(w, m, Effect(18, kind=16, flags=1, value=5, ticks=5))
    movement.set_move(w, m, 30, 20)
    for _ in range(4):
        creature_pass(w, m)
        assert m.brain_order == effects.BRAIN_STONE and m.state == effects.STONE_STATE and (m.x, m.sub_x) == (20, 128)
    creature_pass(w, m)                                                         # the bit clears in the effect pass, order 4 ends
    assert m.brain_order == 0
    creature_pass(w, m, 20)
    assert m.x > 20


def test_a_stoned_target_scores_0x7f_worse():
    w = world()
    me = monster(w, 1, 20, 20)
    t = hero(w, 2, 22, 20)
    s = ai.score(w, me, t)
    effects.apply(w, t, Effect(18, kind=16, flags=1, value=5, ticks=50))
    assert ai.score(w, me, t) == s + 0x7F


# --- carriers (E§6) ----------------------------------------------------------------------------------------------------------------------

def cast_unit(w, u, n, t, level=30):
    return effects.release(w, u, sp(w, n), level, t=t)


def carriers_pass(w, n=1):
    for _ in range(n):
        spells.carrier_system(w, [])


def test_point_carrier_applies_at_the_next_carrier_pass_hostile_credit():
    w = world()
    w.ai_on = True
    m = monster(w, 1, 20, 20, owner=2)
    t = hero(w, 2, 21, 20)
    c = cast_unit(w, m, 29, t)                                                  # Slow, hostile
    assert c.kind == "point" and not t.effects
    carriers_pass(w)
    assert effects.active(t, 29) and t.last_attacker == m.id and not w.carriers
    friend = monster(w, 3, 19, 20, owner=2)
    cast_unit(w, m, 21, friend)                                                 # Haste is defensive: no attacker credit
    carriers_pass(w)
    assert effects.active(friend, 21) and friend.last_attacker is None


def test_poison_cloud_stamps_a_diamond_pulses_ground_occupants_and_quadruples_the_cost():
    w = world()
    m = monster(w, 1, 10, 20)
    t = monster(w, 2, 21, 20, owner=3, hp=200)
    c = effects.release(w, m, sp(w, 6), 30, cell=(20, 20))                     # radius 2, life 5*16 + 480/10 = 128
    assert (c.kind, c.mode, c.life, c.radius) == ("area", 1, 128, 2)
    base = int(w.cost[20, 20])
    carriers_pass(w)                                                            # first visit: the stamp, no countdown
    cells = {k for k, v in w.cell_fx.items() if v[2] == c.uid}
    assert cells == {(20 + dx, 20 + dy) for dx in range(-2, 3) for dy in range(-2, 3) if abs(dx) + abs(dy) <= 3}
    assert int(w.cost[20, 20]) == (base << 2) & 0xFF and w.block_rev
    pulses = 0
    for _ in range(127):
        carriers_pass(w)
        if effects.find(t, 6) is not None and pulses == 0:
            pulses = 1
    assert effects.find(t, 6) is not None and c.life == 1
    carriers_pass(w, 2)                                                         # 0: the last pulse; then the unstamp
    assert not w.cell_fx and int(w.cost[20, 20]) == base and not w.carriers


def test_fire_removes_poison_and_light_and_darkness_cancel():
    w = world()
    m = monster(w, 1, 10, 20)
    effects.release(w, m, sp(w, 6), 30, cell=(20, 20))
    carriers_pass(w)
    assert w.cell_fx[(20, 20)][2] is not None
    effects.release(w, m, sp(w, 3), 30, cell=(20, 20))                         # Wall of Fire over it
    carriers_pass(w)
    v = w.cell_fx[(20, 20)]
    assert v[0] is not None and v[2] is None
    effects.release(w, m, sp(w, 15), 30, cell=(30, 30))
    carriers_pass(w)
    assert w.cell_fx[(30, 30)][4] is not None
    effects.release(w, m, sp(w, 14), 30, cell=(30, 30))
    carriers_pass(w)
    assert (30, 30) not in w.cell_fx                                             # both removed


def test_wall_of_earth_blocks_free_cells_only_and_unblocks_at_the_end():
    w = world()
    m = monster(w, 1, 20, 10)                                                   # south of the wall: direction 4 (down) -> rows y and y+1
    t = monster(w, 2, 20, 21)
    c = effects.release(w, m, sp(w, 17), 30, cell=(20, 20))
    assert c.direction == 4
    carriers_pass(w)
    walls = {k for k, v in w.cell_fx.items() if v[3] == c.uid}
    assert walls == {(x, y) for x, y in [(20 + i, 21) for i in range(-2, 3)] + [(20 + i, 20) for i in range(-2, 3)]} - {(20, 21)}
    assert w.blocked(19, 20) and not w.blocked(20, 21) and (20, 21) not in w.cell_fx
    c.life = 1
    carriers_pass(w, 2)
    assert not w.cell_fx and not w.blocked(19, 20)


def test_wall_shapes_by_direction():
    from allods2.formats import spelldefs
    assert set(spelldefs.wall_cells((10, 10), 0)) == {(10 + i, 9) for i in range(-2, 3)} | {(10 + i, 10) for i in range(-2, 3)}
    assert set(spelldefs.wall_cells((10, 10), 2)) == {(11, 10 + i) for i in range(-2, 3)} | {(10, 10 + i) for i in range(-2, 3)}
    assert len(spelldefs.wall_cells((10, 10), 3)) == 9 and (12, 8) in spelldefs.wall_cells((10, 10), 3)


def test_fire_ball_lands_as_a_square_hit_on_everyone_and_divides_by_size_squared():
    w = world(3)
    m = monster(w, 1, 10, 20)
    ally = monster(w, 2, 21, 21, hp=300)
    t = monster(w, 3, 20, 20, owner=3, hp=300)
    c = cast_unit(w, m, 2, t)                                                   # missile, radius 1, apply once
    assert c.kind == "missile" and c.centre == (20, 20) and c.ticks_left == (10 * 256) // 200
    carriers_pass(w, c.ticks_left)
    assert not w.carriers
    hit = {e.target for e in w.fight_log if isinstance(e, Damage)}
    assert hit == {t.id, ally.id}


def test_blizzard_32_stones_and_acid_stream_6_steps_one_every_3_ticks():
    w = world()
    m = monster(w, 1, 20, 24)
    c = effects.release(w, m, sp(w, 7), 30, cell=(20, 20))
    assert c.kind == "field"
    n = 0
    while w.carriers:
        carriers_pass(w)
        n += 1
    assert c.step == 32 and n == 1 + 31 * 3
    c = effects.release(w, m, sp(w, 9), 30, cell=(20, 20))
    n = 0
    while w.carriers:
        carriers_pass(w)
        n += 1
    assert c.step == 6 and n == 1 + 5 * 3


def test_teleport_moves_the_caster_to_a_free_cell():
    w = world()
    m = monster(w, 1, 20, 20)
    assert effects.release(w, m, sp(w, 23), 30, cell=(25, 22)) is True
    assert (m.x, m.y) == (25, 22) and w.slots.occ[0].get(pack(25, 22)) == m.id


def test_an_area_hit_from_a_neutral_owner_declares_war_only_after_11_hits():
    w = world()
    w.ai_on = True
    w.players[2].relations = (1, 18, 0) + (0,) * 13
    w.players[3].relations = (1, 0, 18) + (0,) * 13
    a = monster(w, 1, 20, 20, owner=2)
    v = monster(w, 2, 21, 20, owner=3, hp=1000)
    for k in range(11):
        ai.on_hit(w, a, v, area=True)
        assert not ai.at_war(w, 3, 2) and ai.at_war(w, 2, 3)
    ai.on_hit(w, a, v, area=True)
    assert ai.at_war(w, 3, 2)


# --- the AI no longer spams Shield; determinism (ai.md 12.5) ------------------------------------------------------------------------------

def _idle_mages(seed):
    w = world(seed)
    m = monster(w, 1, 20, 20, known=mask(24, 27), mana=200, mind=40, skills=(40,) * 5)
    hero(w, 2, 40, 40)
    sim = Simulation(w, ai=True)
    run(sim, 200)
    return w, m


def test_an_active_shield_ends_the_idle_recast_and_the_run_replays():
    w, m = _idle_mages(4)
    shields = [e for e in w.fight_log if isinstance(e, CastStarted) and e.spell == spells.SHIELD]
    # the first idle pass (tick 6) casts it; the AI cast repeats until the next pass (ai.md 12.7; the merge only refreshes), then never again
    assert shields and all(e.tick < 6 + 16 for e in shields)
    assert effects.active(m, spells.SHIELD) and m.combat.block.absorb == 50 // 10 + 3 and len(m.effects) == 1      # level 40 - 30 + 40
    w2, _ = _idle_mages(4)
    assert w.dump_hash() == w2.dump_hash()
    assert "effects" in str(w.dump())


def test_a_world_without_effects_dumps_no_effect_keys():
    w = world()
    monster(w, 1, 20, 20)
    d = w.dump()
    assert "cell_fx" not in d and all(len(u) == 21 for u in d["units"])


def test_cast_command_of_a_buff_reaches_the_target_through_the_simulation():
    w = world()
    m = monster(w, 1, 20, 20, owner=1, known=mask(21), mana=100, mind=40, skills=(40,) * 5)
    sim = Simulation(w)
    sim.step([CastSpell(1, (m.id,), 21, m.id)])
    run(sim, 40)
    assert effects.active(m, 21) and movement.unit_speed(m) == 24 + 50 // 15 + 1      # level 40 - 30 + 40


def _effect_fight(seed):
    w = world(seed)
    for k in range(3):
        monster(w, 1 + k, 20 + k, 20, squad=1, known=mask(2, 6, 18, 20, 21, 24, 27, 28, 29), mana=300, mind=40, skills=(40,) * 5, hp=60)
    for k in range(2):
        monster(w, 10 + k, 20 + k, 23, squad=2, slots=((15, 30), (6, 20), (17, 10)), power=40, mind=24)
    hero(w, 20, 26, 21)
    hero(w, 21, 27, 22)
    sim = Simulation(w, ai=True)
    seen = set()
    for _ in range(600):
        sim.step()
        seen |= {e.id for u in w.units.values() for e in u.effects}
        if w.cell_fx:
            seen.add("cells")
    return w, seen


def test_a_fight_with_effect_spells_is_deterministic_and_consistent():
    a, seen = _effect_fight(7)
    b, _ = _effect_fight(7)
    assert a.dump_hash() == b.dump_hash()
    assert a.check_consistency() == [] and not a.unbuilt_casts
    spells_cast = {e.spell for e in a.fight_log if isinstance(e, CastStarted)}
    assert len(spells_cast) >= 3 and seen, (spells_cast, seen)
