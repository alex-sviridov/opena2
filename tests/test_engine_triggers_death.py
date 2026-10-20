"""Death and the trigger runtime (docs/engine/combat.md 16.4): a dying unit still counts as a group member and as alive; it leaves at the removal tick."""

from allods2.formats import scenario as S
from engine.sim import triggers as T
from engine.world import DEAD
from test_engine_triggers import rec, script, setup
from test_engine_ai import run


def test_group_counts_and_alive_follow_the_removal_not_the_hp():
    sc = script([], [rec(1, 1, (S.K_GROUP, 1)), rec(5, 2, (S.K_UNIT, 2)), rec(8, 3, (S.K_PLAYER, 2)), rec(6, 4, (S.K_UNIT, 1), (S.K_UNIT, 2))], [])
    w, sim, h, a, b = setup(sc)

    def values():
        for c in w.script.checks:
            T.eval_check(w, w.script, c)
        return [w.script.values[c.index] for c in w.script.checks]

    assert values() == [2, 1, 2, 10]
    a.hp = -20                                            # dying: the HP <= 0 branch runs, the body stays a member and alive
    sim.step()
    assert a.id in w.units and a.state != DEAD
    assert values() == [2, 1, 2, 10]
    for _ in range(60):
        sim.step()
        if a.state == DEAD:
            break
    assert a.state == DEAD and a.id not in w.units         # the removal tick: group count, player count, alive and distance all change at once
    assert values() == [1, 0, 1, 0xFF]
