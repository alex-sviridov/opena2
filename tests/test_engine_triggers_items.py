"""The item, teleport, spell and defence instants and the checks 22, 25, 26 (docs/engine/triggers.md 3, 4).  Synthetic, always run."""

from allods2.formats import scenario as S
from engine.sim import triggers as T
from engine.sim.combat import combat_stats

from test_engine_triggers import TRUE, rec, script, setup

ITEM = S.ITEM_BASE


def item(i):
    return (S.K_ITEM, i)


def run1(w, i=0):
    T.run_instant(w, w.script, i)


def test_add_take_give_and_remove_items():
    sc = script([rec(12, 1, (S.K_UNIT, 2), item(5)), rec(11, 2, (S.K_UNIT, 2), (S.K_UNIT, 3), item(5)), rec(13, 3, (S.K_UNIT, 3), item(5)),
                 rec(28, 4, (S.K_UNIT, 2), (S.K_UNIT, 3)), rec(38, 5, item(5))], TRUE, [])
    w, sim, h, a, b = setup(sc)
    code = 5 + ITEM
    a.carried = (7,)
    run1(w, 0)
    assert a.carried == (7, code)
    run1(w, 1)                                              # FUN_00529f3f then FUN_00529ac2: one piece from a to b
    assert a.carried == (7,) and b.carried == (code,)
    run1(w, 2)
    assert b.carried == ()
    b.carried = (code, 9)
    run1(w, 3)                                              # Give All: a's whole pack to b, a keeps an empty one
    assert a.carried == () and b.carried == (code, 9, 7)
    a.carried = (code,)
    run1(w, 4)                                              # remove from everybody (first piece of each pack)
    assert a.carried == () and b.carried == (9, 7)
    run1(w, 1)                                              # nothing to give: no change
    assert b.carried == (9, 7)


def test_drop_all_makes_a_pile_on_the_units_cell():
    w, sim, h, a, b = setup(script([rec(20, 1, (S.K_UNIT, 2))], TRUE, []))
    a.carried = (3, 4)
    run1(w)
    assert a.carried == () and w.items_at(a.x, a.y)
    pile = w.items[next(iter(w.items_at(a.x, a.y)))]
    assert pile.codes == (3, 4)


def test_teleport_unit_moves_stands_and_a_computer_unit_re_anchors():
    w, sim, h, a, b = setup(script([rec(27, 1, (S.K_UNIT, 2), (S.K_X, 36), (S.K_Y, 30))], TRUE, []))
    run1(w)
    assert (a.x, a.y, a.sub_x, a.sub_y) == (36, 30, 128, 128) and a.id in w.units_at(36, 30) and not w.units_at(30, 24) - {b.id}
    assert a.order == 0xB and a.anchor == (36, 30)            # FUN_0056d4ba for a computer-owned unit
    assert not w.script.unsupported


def test_teleport_to_an_occupied_cell_does_nothing():
    w, sim, h, a, b = setup(script([rec(27, 1, (S.K_UNIT, 2), (S.K_X, 31), (S.K_Y, 24))], TRUE, []))
    run1(w)
    assert (a.x, a.y) == (30, 24)


def test_check_22_teleports_the_unit_standing_on_a_cell_and_reports_it():
    chk = rec(22, 1, (S.K_X, 30), (S.K_Y, 24), (S.K_X, 36), (S.K_Y, 30))
    w, sim, h, a, b = setup(script([], [chk], []))
    T.eval_check(w, w.script, w.script.checks[0])
    assert w.script.values[0] == 1 and (a.x, a.y) == (36, 30)
    T.eval_check(w, w.script, w.script.checks[0])
    assert w.script.values[0] == 0                            # nobody on (30, 24) any more


def test_set_unit_parameter_15_and_16_write_the_defence_and_the_absorption():
    sc = script([rec(34, 1, (S.K_UNIT, 2), (S.K_INT, 15), (S.K_INT, 77)), rec(34, 2, (S.K_UNIT, 2), (S.K_INT, 16), (S.K_INT, 9)),
                 rec(34, 3, (S.K_UNIT, 2), (S.K_INT, 3), (S.K_INT, 9))], TRUE, [])
    w, sim, h, a, b = setup(sc)
    run1(w, 0)
    run1(w, 1)
    run1(w, 2)                                                # any other parameter: only the client refresh
    blk = combat_stats(w, a).block
    assert (blk.defence, blk.absorb) == (77, 9) and not w.script.unsupported


def test_set_formation_writes_the_server_byte():
    w, sim, h, a, b = setup(script([rec(7, 1, (S.K_PLAYER, 1), (S.K_INT, 0)), rec(7, 2, (S.K_PLAYER, 1), (S.K_INT, 2)), rec(7, 3, (S.K_PLAYER, 1), (S.K_INT, 1))],
                                    TRUE, []))
    for i, mode in enumerate((0, 1, 2)):                      # server 0 off, 2 auto, 1 on -> client 0 / 1 / 2
        run1(w, i)
        assert w.players[1].formation == mode


def test_scripted_casts_make_hidden_casters_and_instant_25_sets_a_trap():
    sc = script([rec(21, 1, (S.K_X, 10), (S.K_Y, 10), (S.K_X, 12), (S.K_Y, 12), (S.K_INT, 7), (S.K_INT, 100)),
                 rec(24, 2, (S.K_X, 10), (S.K_Y, 10), (S.K_UNIT, 2), (S.K_INT, 18), (S.K_INT, 100)),
                 rec(25, 3, (S.K_INT, 23), (S.K_INT, 255), (S.K_X, 12), (S.K_Y, 12)),
                 rec(29, 4, (S.K_X, 12), (S.K_Y, 12), (S.K_INT, 7), (S.K_INT, 1)), rec(30, 5, (S.K_UNIT, 2), (S.K_INT, 18), (S.K_INT, 1))],
                [rec(25, 1, (S.K_X, 12), (S.K_Y, 12), (S.K_INT, 1)), rec(26, 2, (S.K_UNIT, 2), (S.K_INT, 12)), rec(26, 3, (S.K_UNIT, 2), (S.K_INT, 4))], [])
    w, sim, h, a, b = setup(sc)
    for i in range(5):
        run1(w, i)
    assert not w.unbuilt_casts and not w.script.unsupported
    assert not w.script.unbuilt                              # instants 29 / 30 act on a cell record / the unit's effects (sim/effects.py); none here
    c21, c24 = w.transients                                 # sim/traps.py: FUN_004f086f / FUN_004f0832
    assert (c21.x, c21.y, c21.state, c21.cast.spell, c21.cast.cell, c21.stats.get("spell_power")) == (10, 10, 0xE, 7, (12, 12), 100)
    assert (c24.x, c24.y, c24.state, c24.cast.spell, c24.cast.target, c24.stats.get("spell_power")) == (10, 10, 0xD, 18, a.id, 100)
    assert w.cell_effects == {(12, 12): (23, 255, 12, 12, 12, 12)}            # FUN_0057847e with n4 == 0
    a.hidden = True
    for c in w.script.checks:
        T.eval_check(w, w.script, c)
    assert w.script.values[0] == 0 and w.script.values[1] == 1 and w.script.values[2] == 0      # bit 12 is Invisibility, bit 4 (a protection) is not active


def test_instants_31_and_14_have_nothing_to_change():
    w, sim, h, a, b = setup(script([rec(31, 1, (S.K_INT, 1), (S.K_INT, 5)), rec(14, 2, (S.K_UNIT, 2))], TRUE, []))
    run1(w, 0)
    run1(w, 1)
    assert not w.script.unsupported and not w.script.errors
