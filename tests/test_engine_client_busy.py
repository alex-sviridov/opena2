"""The client view's busy counter (`+0xa8`, `FUN_0046617c` counts it down once per view step): the attack / shoot / cast message handlers
(`0x71` `0x4132d2`, `0x72` `0x413427`, `0x86` `0x4151c1` busy test `0x415258`, `0x8a`) start nothing while it is non-zero; a move (`0x6b`) and a turn
(`0x6d`) set it unconditionally.  Synthetic worlds, always run.  Docs: docs/engine/rendering.md (K9 leftovers), docs/formats/animation.md 1.4."""

import types

from engine.sim import movement as mv
from test_engine_bolts import FakeAssets, FakeSet, caster, foe, start, world

LIGHTNING = 10


class LenSet(FakeSet):
    """A unit set whose AttackAnim (`T+0x68`) is `n` frames long."""

    def __init__(self, n=12, **kw):
        super().__init__(n=n, **kw)
        self.t.sequence = lambda name: list(range(n))


def cast_world(n=12, delay=3):
    w = world()
    w.assets = FakeAssets(LenSet(n, delay=delay))
    return w


def test_a_cast_sets_the_view_busy_for_the_attack_length_and_ends_exactly_then():
    w = cast_world(n=12)
    c = caster(w)
    t = foe(w, 2, 22, 20)
    w.tick = 30
    start(w, c, t, LIGHTNING)
    assert c.client_busy_until == 42
    for k, busy in ((30, True), (41, True), (42, False)):
        w.tick = k
        assert mv.client_busy(w, c) is busy          # a message of tick 30 with 12 ticks: the view is free again at the message loop of tick 42


def test_a_cast_while_the_view_is_busy_makes_no_bolt_and_no_cast_action():
    w = cast_world()
    c = caster(w)
    t = foe(w, 2, 22, 20)
    w.tick = 30
    c.client_busy_until = 35                         # an earlier move / turn / attack is still animating
    c.action, c.action_start_tick = mv.MOVE, 28
    log = len(w.fight_log)
    cast, st = start(w, c, t, LIGHTNING)
    assert w.bolts == [] and w.flashes == []         # `0x4151c1` starts nothing: no ShootDelay projectile
    assert (c.action, c.action_start_tick) == (mv.MOVE, 28) and c.client_busy_until == 35
    assert len(w.fight_log) == log + 1               # the server's cast went on (CastStarted)
    assert c.step_end == 30                          # `+0x138` is the server message's stamp


def test_the_same_cast_after_the_busy_window_works():
    w = cast_world()
    c = caster(w)
    t = foe(w, 2, 22, 20)
    w.tick = 30
    c.client_busy_until = 35
    w.tick = 35
    start(w, c, t, LIGHTNING)
    assert len(w.bolts) == 1 and c.action == mv.ATTACK and c.action_start_tick == 35


def test_two_casts_inside_one_attack_animation_make_one_bolt():
    w = cast_world(n=12)
    c = caster(w)
    t = foe(w, 2, 22, 20)
    w.tick = 30
    start(w, c, t, LIGHTNING)
    w.tick = 36
    start(w, c, t, LIGHTNING)
    assert len(w.bolts) == 1
    w.tick = 42
    start(w, c, t, LIGHTNING)
    assert len(w.bolts) == 2


def test_a_hidden_caster_has_no_view_test():
    w = cast_world()
    c = caster(w)
    c.type_id = 0                                    # the `0x8b` / `0x8c` forms are made by the message loop, no caster view
    t = foe(w, 2, 22, 20)
    w.tick = 30
    c.client_busy_until = 99
    start(w, c, t, LIGHTNING)
    assert c.action == mv.ATTACK                     # the action bookkeeping is unchanged for it


def test_a_fresh_turn_sets_the_view_busy_for_its_ticks_and_a_snap_for_one():
    w = world()
    c = caster(w)
    c.mover.turn_rate = 16
    w.tick = 10
    mv._turn_toward(w, c, (c.facing + 0x40) & 0xFF)  # 64 units at 16 per tick: 4 ticks
    assert c.mover.turn_ticks == 4 and c.client_busy_until == 14
    c.client_busy_until = 0
    w.tick = 20
    mv._turn_toward(w, c, c.facing)                  # a continuing turn sends no new `0x6d`
    assert c.client_busy_until == 0
    c.mover.turning = False
    mv._turn_toward(w, c, (c.facing + 8) & 0xFF)     # within 45 degrees: snaps, 1 tick
    assert c.client_busy_until == 21


def test_without_a_unit_set_the_attack_length_is_zero():
    w = world()
    c = caster(w)
    assert mv.attack_ticks(w, c) == 0
    w.assets = types.SimpleNamespace(unit_set=lambda tid: None)
    assert mv.attack_ticks(w, c) == 0


# --- the melee / shoot start (`0x71` / `0x72`) ---------------------------------------------------------------------------------------

def swing(busy_until):
    from engine.sim import combat
    from test_engine_arrows import fight
    w, s, t = fight()
    s.combat = types.SimpleNamespace(windup=6, recovery=4, range=6, mage=False, weapon_spell=None)
    s.swing_target, s.phase, s.client_busy_until = t.id, combat.PHASE_START, busy_until
    w.tick = 50
    combat.swing_tick(w, s)
    return w, s


def test_a_swing_start_while_the_view_is_busy_makes_no_arrow_and_no_attack_action():
    w, s = swing(busy_until=55)
    assert w.arrows == [] and s.action != mv.ATTACK and s.client_busy_until == 55


def test_a_swing_start_with_a_free_view_shoots_and_sets_the_busy_clock():
    w, s = swing(busy_until=0)
    assert len(w.arrows) == 1 and s.action == mv.ATTACK and s.action_start_tick == 50
    assert s.client_busy_until == 50 + mv.attack_ticks(w, s)
