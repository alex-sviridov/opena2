"""Scenario triggers (docs/engine/triggers.md, T§ numbers): synthetic worlds and scripts, one test per rule; always run."""

import pytest

from allods2.formats import scenario as S
from engine.sim import AttackUnit, MoveUnits, Simulation
from engine.sim import ai, triggers as T
from engine.world import DEAD, MapObject
from test_engine_ai import hero, run, unit, world


def rec(t, rid, *args, name=""):
    """A section 7 record with (kind, value) arguments in slot order."""
    kinds = [k for k, _ in args] + [0] * (10 - len(args))
    vals = [v for _, v in args] + [0] * (10 - len(args))
    return S.Record(name, t, rid, 0, tuple(vals), tuple(kinds), ("<None>",) * 10)


def const(rid, v):
    return rec(S.CONSTANT, rid, (S.K_INT, v))


def trig(pairs=(), instants=(), ops=(), once=1, name="t"):
    pairs = (list(pairs) + [(0, 0)] * 3)[:3]
    return S.Trigger(name, b"", tuple(pairs), tuple((list(instants) + [0] * 4)[:4]), tuple((list(ops) + [0] * 3)[:3]), once)


def script(instants=(), checks=(), triggers=()):
    return S.Scenario(tuple(instants), tuple(checks), tuple(triggers))


def setup(sc, *, units=True, strict=False):
    """World with the human hero (uid 1, main hero), a computer squad (uids 2, 3, player 2 squad 1); compiled and simulated."""
    w = world()
    h = hero(w, 1, 20, 24)
    w.players[1].main_hero = h.id
    a = unit(w, 2, 30, 24, 2, 1) if units else None
    b = unit(w, 3, 31, 24, 2, 1) if units else None
    T.enable(w, sc, strict=strict)
    return w, Simulation(w, triggers=True), h, a, b


SET_V70 = rec(3, 1, (S.K_INT, 70), (S.K_INT, 1))
INC_V70 = rec(8, 2, (S.K_INT, 70))
TRUE = [const(1, 0), const(2, 0)]           # check ids 1, 2: 0 == 0
ALWAYS = ((1, 2),)


# --- default off and the pass timing (T§1, T§5) -------------------------------------------------------------------------------

def test_without_enable_there_is_no_script_and_the_dump_is_unchanged():
    w = world()
    hero(w, 1, 20, 24)
    Simulation(w, ai=True)
    assert w.script is None and "script" not in w.dump()
    with pytest.raises(ValueError):
        Simulation(world(), triggers=True)


def test_the_pass_runs_at_tick_6_and_every_16_ticks_a_once_trigger_fires_once():
    w, sim, *_ = setup(script([INC_V70], TRUE, [trig(ALWAYS, [2])]))
    run(sim, 6)
    assert w.script.values[70] == 0
    sim.step()                                  # tick 6: the group pass
    assert w.script.values[70] == 1 and w.script.fired[0] == 1 and w.script.passes == 1
    run(sim, 40)
    assert w.script.values[70] == 1 and w.script.passes == 3
    assert "script" in w.dump()


def test_a_repeating_trigger_fires_at_every_pass_while_true():
    w, sim, *_ = setup(script([INC_V70], TRUE, [trig(ALWAYS, [2], once=0)]))
    run(sim, 7 + 32)
    assert w.script.values[70] == 3


def test_operators_compare_signed_values_and_an_unknown_operator_is_false():
    vals = [5, -3]
    got = [T._holds(vals, 0, 1, op) for op in range(7)]
    assert got == [False, True, True, False, True, False, False]


def test_every_pair_must_hold_and_an_incomplete_pair_is_ignored():
    checks = [const(1, 4), const(2, 5)]
    w, sim, *_ = setup(script([SET_V70], checks, [trig([(1, 2), (3, 0)], [1], [3]), trig([(1, 2), (2, 1)], [1], [3, 3], name="no")]))
    run(sim, 7)
    assert w.script.fired[0] == 1 and w.script.fired[1] == 0      # 4 < 5 holds; 5 < 4 does not


def test_a_trigger_without_a_first_check_is_not_compiled():
    w, sim, *_ = setup(script([SET_V70], TRUE, [trig([(0, 2)], [1])]))
    assert w.script.triggers == []


def test_check_values_are_those_of_the_pass_start_but_variables_change_at_once():
    v70 = rec(19, 3, (S.K_INT, 70))                         # check slot 2 = v70 at the pass start
    one = const(4, 1)                                       # slot 3
    tr = [trig(ALWAYS, [1]), trig([(3, 4)], [2], name="v70 == 1?")]    # sets v70 = 1, then compares the stale check value 0
    w, sim, *_ = setup(script([SET_V70, INC_V70], TRUE + [v70, one], tr))
    run(sim, 7)
    assert w.script.values[70] == 1 and w.script.fired[1] == 0
    run(sim, 16)
    assert w.script.fired[1] == 1 and w.script.values[70] == 2


# --- compilation quirks (T§2.4) ---------------------------------------------------------------------------------------------

def test_a_failed_check_maps_to_slot_0_and_the_next_check_takes_its_slot():
    bad = rec(5, 1, (S.K_UNIT, 99))                         # no unit 99: fails
    w, sim, *_ = setup(script([], [bad, const(2, 7)], []))
    assert w.script.values[0] == 7 and w.script.checks == []
    assert any("Can't resolve unit 99" in e for e in w.script.errors)


def test_a_trigger_naming_a_missing_instant_runs_instant_0():
    w, sim, *_ = setup(script([SET_V70, INC_V70], TRUE, [trig(ALWAYS, [42])]))
    run(sim, 7)
    assert w.script.values[70] == 1                         # instant index 0 = "v70 = 1"


def test_drop_locations_are_not_instants():
    drop = rec(S.CONSTANT, 1, (S.K_X, 11), (S.K_Y, 41))
    w, sim, *_ = setup(script([drop, SET_V70], TRUE, [trig(ALWAYS, [2])]))
    assert w.script.drops == [(11, 41)] and len(w.script.instants) == 1
    run(sim, 7)
    assert w.script.values[70] == 1


def test_a_referenced_squad_is_kept_awake_except_by_check_1():
    w, sim, *_ = setup(script([], [rec(1, 1, (S.K_GROUP, 1))], []))
    assert not w.ai_groups[(2, 1)].keep_awake
    w2, *_ = setup(script([], [rec(5, 1, (S.K_UNIT, 2))], []))
    assert w2.ai_groups[(2, 1)].keep_awake


def test_every_unit_argument_flags_its_squad_but_only_the_first_group_argument_does():
    """CONFIRMED 0x563101-0x5631bc / 0x5632b0-0x56331f: the unit tail runs after each unit argument (the second one wins the shared slot, the first was
    flagged when it was processed), the group tail checks the first group slot first."""
    def build(checks):
        w = world()
        hero(w, 1, 20, 24)
        unit(w, 2, 30, 24, 2, 1)
        unit(w, 3, 34, 24, 2, 2)
        unit(w, 4, 36, 24, 3, 5)
        T.enable(w, script([], checks, []))
        return w
    w = build([rec(6, 1, (S.K_UNIT, 2), (S.K_UNIT, 3))])               # distance between two units: both squads
    assert w.ai_groups[(2, 1)].keep_awake and w.ai_groups[(2, 2)].keep_awake and not w.ai_groups[(3, 5)].keep_awake
    w = build([rec(5, 1, (S.K_UNIT, 4))])
    assert w.ai_groups[(3, 5)].keep_awake and not w.ai_groups[(2, 1)].keep_awake
    w = build([rec(5, 1, (S.K_GROUP, 1), (S.K_GROUP, 2))])             # two groups (squads 1 and 2): only the first
    assert w.ai_groups[(2, 1)].keep_awake and not w.ai_groups[(2, 2)].keep_awake


def test_hero_ids_resolve_by_the_reduced_server_id():
    w = world()
    h = hero(w, 1, 20, 24)
    h.human, h.server_id = True, 10220                      # Fighter_Hero: (10220 / 10) % 1000 = 22 -> hero 10002
    w.players[1].main_hero = h.id
    T.enable(w, script([], [rec(5, 1, (S.K_UNIT, 10002))], []))
    assert w.script.checks[0].unit is h
    w2 = world()
    hero(w2, 1, 20, 24)                                     # no main hero: heroes do not resolve
    T.enable(w2, script([], [rec(5, 1, (S.K_UNIT, 10002))], []))
    assert not w2.script.checks and "Can't resolve hero 10002" in w2.script.errors


# --- checks (T§3) ---------------------------------------------------------------------------------------------------------

def eval_one(check, **kw):
    w, sim, h, a, b = setup(script([], [check], []), **kw)
    c = w.script.checks[0]
    T.eval_check(w, w.script, c)
    return w, w.script.values[0], h, a, b


def test_check_alive_reads_state_0x10_not_the_hp():
    w, v, h, a, b = eval_one(rec(5, 1, (S.K_UNIT, 2)))
    assert v == 1
    a.hp = -5                                               # dying: still alive
    T.eval_check(w, w.script, w.script.checks[0])
    assert w.script.values[0] == 1
    a.state = DEAD
    T.eval_check(w, w.script, w.script.checks[0])
    assert w.script.values[0] == 0


def test_distances_are_chebyshev_and_a_dead_unit_gives_0xff():
    w, v, h, a, b = eval_one(rec(6, 1, (S.K_UNIT, 1), (S.K_UNIT, 2)))
    assert v == 10
    a.state = DEAD
    T.eval_check(w, w.script, w.script.checks[0])
    assert w.script.values[0] == 0xFF
    assert eval_one(rec(7, 1, (S.K_UNIT, 1), (S.K_X, 23), (S.K_Y, 30)))[1] == 6
    assert eval_one(rec(3, 1, (S.K_UNIT, 1), (S.K_X, 23), (S.K_Y, 25), (S.K_INT, 3)))[1] == 1
    assert eval_one(rec(2, 1, (S.K_UNIT, 1), (S.K_X, 18), (S.K_Y, 20), (S.K_X, 22), (S.K_Y, 23)))[1] == 0


def test_numeric_arguments_are_packed_past_the_objects():
    w, v, h, a, b = eval_one(rec(7, 1, (S.K_X, 23), (S.K_UNIT, 1), (S.K_Y, 30)))
    assert w.script.checks[0].nums[:2] == [23, 30] and v == 6


def test_centered_on_tile_reads_the_wrong_arguments_and_is_never_true():
    assert eval_one(rec(27, 1, (S.K_UNIT, 1), (S.K_X, 20), (S.K_Y, 24)))[1] == 0


def test_group_count_drops_at_the_removal_and_when_the_player_commands_a_member():
    w, v, h, a, b = eval_one(rec(1, 1, (S.K_GROUP, 1)))
    assert v == 2
    b.state = DEAD
    T.eval_check(w, w.script, w.script.checks[0])
    assert w.script.values[0] == 1
    w2, sim, h2, *_ = setup(script([], [rec(1, 1, (S.K_GROUP, 0))], []))
    assert len(w2.script.checks[0].group.live()) == 1          # the human squad 0 = the hero
    sim.step([MoveUnits(1, (h2.id,), (25, 24))])
    T.eval_check(w2, w2.script, w2.script.checks[0])
    assert w2.script.values[0] == 0


def test_unit_parameter_6_is_the_hp_and_other_parameters_keep_the_value():
    w, v, h, a, b = eval_one(rec(4, 1, (S.K_UNIT, 2), (S.K_INT, 6)))
    assert v == 40
    w, v, *_ = eval_one(rec(4, 1, (S.K_UNIT, 2), (S.K_INT, 7)))
    assert v == 0


def test_is_unit_attacking_gives_the_target_uid():
    w, sim, h, a, b = setup(script([], [rec(9, 1, (S.K_UNIT, 1))], []))
    sim.step([AttackUnit(1, (h.id,), a.id)])
    run(sim, 16)
    assert h.mode_attack
    T.eval_check(w, w.script, w.script.checks[0])
    assert w.script.values[0] == 2


def test_player_unit_count_and_nearest_distance():
    w, v, *_ = eval_one(rec(8, 1, (S.K_PLAYER, 2)))
    assert v == 2
    assert eval_one(rec(15, 1, (S.K_PLAYER, 2), (S.K_X, 30), (S.K_Y, 20)))[1] == 4
    assert eval_one(rec(15, 1, (S.K_PLAYER, 3), (S.K_X, 30), (S.K_Y, 20)))[1] == 0xFF


def test_diplomacy_check_and_the_one_way_instant():
    w, v, *_ = eval_one(rec(10, 1, (S.K_PLAYER, 1), (S.K_PLAYER, 2)))
    assert v == 1                                           # player 1 is at war with player 2
    w, sim, *_ = setup(script([rec(10, 1, (S.K_INT, 2), (S.K_INT, 1), (S.K_INT, 2))], TRUE, [trig(ALWAYS, [1])]))
    run(sim, 7)
    assert w.players[2].relations[0] == 2 and w.players[1].relations[1] == 1      # only M[2][1] changed


def test_items_in_the_pack_are_special_item_codes():
    w, sim, h, a, b = setup(script([], [rec(17, 1, (S.K_UNIT, 2), (S.K_ITEM, 3))], []))
    a.carried = (0xE18 + 3,)
    T.eval_check(w, w.script, w.script.checks[0])
    assert w.script.values[0] == 1


def test_building_health_and_count():
    w = world()
    h = hero(w, 1, 20, 24)
    w.players[1].main_hero = h.id
    w.objects[0x6000 + 5] = MapObject(0x6000 + 5, "structure", 70, 10, 10, owner=2, hp=30, hp_max=30, uid=5)
    T.enable(w, script([rec(26, 1, (S.K_BUILDING, 5), (S.K_INT, 0))], [rec(21, 1, (S.K_BUILDING, 5)), rec(20, 2, (S.K_PLAYER, 2))], []))
    for c in w.script.checks:
        T.eval_check(w, w.script, c)
    assert w.script.values[:2] == [30, 1]
    T.run_instant(w, w.script, 0)
    for c in w.script.checks:
        T.eval_check(w, w.script, c)
    assert w.script.values[:2] == [0, 0]


def test_vip_increments_the_fail_cause_at_every_evaluation():
    w, v, h, a, b = eval_one(rec(18, 1, (S.K_UNIT, 2)))
    assert w.script.fail == 0
    a.state = DEAD
    T.eval_check(w, w.script, w.script.checks[0])
    T.eval_check(w, w.script, w.script.checks[0])
    assert w.script.fail == 2


# --- instants (T§4) -----------------------------------------------------------------------------------------------------------

def test_messages_and_subobjectives():
    sub = [rec(36, i + 1, (S.K_INT, 1), (S.K_INT, v)) for i, v in enumerate((1, 2, 4))]
    w, sim, *_ = setup(script([rec(2, 9, (S.K_INT, 7))] + sub, TRUE, [trig(ALWAYS, [9, 1, 2])]))
    run(sim, 7)
    msgs = [e.number for e in w.events if isinstance(e, T.ScriptMessage)]
    assert msgs == [7, 0xFD] and w.script.scenario_vars[1 + T.SUBOBJECTIVE_BASE] == 3
    T.run_instant(w, w.script, 3)
    assert w.script.scenario_vars[0x2F1] == 5 and w.events[-1].number == 0xFE


def test_scenario_variables_are_a_plain_array():
    w, sim, *_ = setup(script([rec(35, 1, (S.K_INT, 777), (S.K_INT, 4))], [rec(23, 1, (S.K_INT, 777))], []))
    T.run_instant(w, w.script, 0)
    T.eval_check(w, w.script, w.script.checks[0])
    assert w.script.values[0] == 4


def test_group_command_move_reorders_the_squad_and_suspend_lets_it_sleep():
    move = rec(6, 1, (S.K_CONST, 4), (S.K_X, 40), (S.K_Y, 30), (S.K_GROUP, 1))
    w, sim, h, a, b = setup(script([move, rec(39, 2, (S.K_GROUP, 1))], TRUE, [trig(ALWAYS, [1])]))
    g = w.ai_groups[(2, 1)]
    assert g.keep_awake
    run(sim, 7)
    assert g.order == ai.G_MOVE and a.mover.goal is not None
    T.run_instant(w, w.script, 1)
    assert not g.keep_awake


def test_unimplemented_kinds_are_counted_or_raise_in_strict_mode():
    attack = rec(6, 1, (S.K_CONST, 6), (S.K_UNIT, 1), (S.K_GROUP, 1))          # group sub-command 6 has no setter
    w, sim, *_ = setup(script([attack, rec(20, 2, (S.K_UNIT, 8001))], TRUE, [trig(ALWAYS, [1, 2])]))      # a variable reference is never resolved
    run(sim, 7)
    assert w.script.unsupported == {("group", 6): 1, ("instant", 20): 1}
    w, sim, *_ = setup(script([attack], TRUE, [trig(ALWAYS, [1])]), strict=True)
    with pytest.raises(NotImplementedError):
        run(sim, 7)


def test_phase_out_keeps_the_squad_count_and_phase_in_appends_to_the_update_order():
    sc = script([rec(16, 1, (S.K_UNIT, 2)), rec(17, 2, (S.K_UNIT, 2))], [rec(1, 1, (S.K_GROUP, 1))], [])
    w, sim, h, a, b = setup(sc)
    T.run_instant(w, w.script, 0)
    assert a.id not in w.units and not w.units_at(30, 24) and a.id not in w.ai_groups[(2, 1)].members
    T.eval_check(w, w.script, w.script.checks[0])
    assert w.script.values[0] == 2
    T.run_instant(w, w.script, 1)
    assert list(w.units)[-1] == a.id and (a.x, a.y) == (30, 24)
    assert w.ai_groups[(2, 1)].members == [a.id, b.id]
    T.run_instant(w, w.script, 1)                       # already on the map: not modelled, logged
    assert "phase in of unit 2" in w.script.errors[-1]


def test_phase_in_searches_radius_3_when_the_own_cell_is_taken():
    w, sim, h, a, b = setup(script([rec(16, 1, (S.K_UNIT, 2)), rec(17, 2, (S.K_UNIT, 2))], [], []))
    T.run_instant(w, w.script, 0)
    w.move_unit(b.id, 30, 24)
    state = w.rng.state
    T.run_instant(w, w.script, 1)
    assert (a.x, a.y) != (30, 24) and max(abs(a.x - 30), abs(a.y - 24)) <= 2 and w.rng.state != state


def test_owner_change_makes_a_stand_ground_group_and_leaves_the_squad():
    w, sim, h, a, b = setup(script([rec(19, 1, (S.K_UNIT, 2), (S.K_PLAYER, 1))], [rec(1, 1, (S.K_GROUP, 1))], []))
    T.run_instant(w, w.script, 0)
    g = w.groups[a.order_group]
    assert a.owner == 1 and g.owner == 1 and g.order == 3 and a.id not in w.ai_groups[(2, 1)].members
    T.eval_check(w, w.script, w.script.checks[0])
    assert w.script.values[0] == 1


def test_money_goes_to_the_script_gold_of_the_player():
    w, sim, *_ = setup(script([rec(23, 1, (S.K_PLAYER, 1), (S.K_INT, 700))], [], []))
    T.run_instant(w, w.script, 0)
    T.run_instant(w, w.script, 0)
    assert w.script.gold == {1: 1400}


def test_set_unit_hp():
    w, sim, h, a, b = setup(script([rec(34, 1, (S.K_UNIT, 2), (S.K_INT, 6), (S.K_INT, 0))], [], []))
    T.run_instant(w, w.script, 0)
    assert a.hp == 0


# --- victory and defeat (T§6) ------------------------------------------------------------------------------------------------

def test_mission_complete_is_reported_at_the_end_of_tick_14_after_the_pass():
    w, sim, *_ = setup(script([rec(4, 1)], TRUE, [trig(ALWAYS, [1])]))
    run(sim, 14)
    assert not [e for e in w.events if isinstance(e, T.MissionComplete)]
    sim.step()                                          # tick 14: (14 + 1) & 15 == 15
    assert [e.tick for e in w.events if isinstance(e, T.MissionComplete)] == [14]
    assert w.players[1].death_code == 1 and not w.players[1].defeat_dialog
    run(sim, 32)
    assert len([e for e in w.events if isinstance(e, T.MissionComplete)]) == 1


def test_a_failure_wins_over_a_completion_and_opens_the_defeat_dialog():
    w, sim, *_ = setup(script([rec(4, 1), rec(5, 2, (S.K_INT, 6))], TRUE, [trig(ALWAYS, [1, 2])]))
    run(sim, 15)
    p = w.players[1]
    assert p.defeat_dialog and p.death_code == 6
    assert [e.cause for e in w.events if isinstance(e, T.MissionFailed)] == [6]


def test_no_main_hero_or_a_dying_main_hero_is_the_defeat_with_state_2():
    w, sim, h, *_ = setup(script([], TRUE, []))
    h.death_seen = True
    run(sim, 15)
    assert w.players[1].death_code == 2 and w.players[1].defeat_dialog
