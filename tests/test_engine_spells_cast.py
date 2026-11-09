"""Spell casts (I4a): the cast order, Brain mode 8, the phase machine, mana, carriers and damage.  Synthetic worlds, always run.
Spec: docs/data/spells.md 9c (CONFIRMED routines in the comments), docs/engine/combat.md 14."""

import pytest

from engine.sim import AttackUnit, CastSpell, Simulation, Stop, replay
from engine.world import CastReleased, CastStarted, Damage, Died
from spell_helpers import FIRE_ARROW, spell_table
from test_engine_combat import fighter, run, world as base_world

FIRE_ARROW_BIT = 1 << FIRE_ARROW


def world():
    w = base_world()
    w.spell_table = spell_table()
    return w


def caster(w, uid, x, y, mana=10, owner=1, windup=5, recovery=4, rng=1, book=FIRE_ARROW_BIT):
    """A mage that knows Fire Arrow (level 0: no skills, so 5..10 damage, range 7)."""
    u = fighter(w, uid, x, y, owner=owner, hp=100, windup=windup, recovery=recovery, rng=rng)
    u.combat.mage = True
    u.mana = u.mana_max = mana
    u.spellbook = book
    return u


def events(w, kind):
    return [e for e in w.fight_log if isinstance(e, kind)]


def until(sim, cond, limit=300):
    for _ in range(limit):
        if cond():
            return
        sim.step()
    raise AssertionError("condition never met")


def cast(sim, c, t, player=1):
    sim.step([CastSpell(player, (c.id,), FIRE_ARROW, t.id)])


def test_timeline_order_start_release_flight_delivery():
    w = world()
    sim = Simulation(w)
    c, t = caster(w, 1, 10, 15), fighter(w, 2, 17, 15, owner=2, hp=1000)      # 7 cells east, in range at once
    cast(sim, c, t)
    run(sim, 40)
    (started,), (released,), (hit,) = events(w, CastStarted), events(w, CastReleased), events(w, Damage)
    assert started.tick == 7                        # the group pass at tick & 15 == 6 makes mode 8; the cast starts on the next tick (stop, then order 2)
    assert released.tick - started.tick == 5        # windup byte +0x134
    assert hit.tick - released.tick == 8            # 1792 // 200 flight ticks: the carrier first ticks one tick after the release
    assert started.flight == 8 and released.carrier == 1
    assert 5 <= 1000 - t.hp <= 10 and c.mana == 7 and not w.carriers


def test_cast_at_a_two_cell_target_starts():
    """Map 96 crashed in `cast_start` for a target with a 2 x 2 footprint: the footprint centre was read from the unit, not from its `Foot`."""
    from allods2.formats.unitstats import MONSTER, UnitType
    w = world()
    sim = Simulation(w)
    c, t = caster(w, 1, 10, 15), fighter(w, 2, 17, 15, owner=2, hp=1000)
    t.stats = UnitType(MONSTER, 1, "big", 1, 1, {"token_size": 2}, (), ())
    cast(sim, c, t)
    run(sim, 40)
    assert len(events(w, CastStarted)) == 1 and len(events(w, CastReleased)) == 1


def test_mana_exact_spends_all_and_one_short_never_starts():
    w = world()
    sim = Simulation(w)
    c, t = caster(w, 1, 10, 15, mana=3), fighter(w, 2, 17, 15, owner=2, hp=1000)
    cast(sim, c, t)
    run(sim, 30)
    assert c.mana == 0 and len(events(w, CastStarted)) == 1
    w2 = world()
    sim2 = Simulation(w2)
    c2, t2 = caster(w2, 1, 10, 15, mana=2), fighter(w2, 2, 17, 15, owner=2, hp=1000)
    cast(sim2, c2, t2)
    run(sim2, 120)                                  # FUN_00519998 returns 0: a silent retry loop, nothing spent, no carrier, no event
    assert c2.mana == 2 and not events(w2, CastStarted) and not w2.carriers and t2.hp == 1000


def test_unknown_spell_and_foreign_commands_do_nothing():
    w = world()
    sim = Simulation(w)
    c, t = caster(w, 1, 10, 15, book=0), fighter(w, 2, 17, 15, owner=2, hp=1000)
    cast(sim, c, t)                                 # not in the book: only the group cancel
    run(sim, 40)
    assert not events(w, CastStarted) and t.hp == 1000
    c.spellbook = FIRE_ARROW_BIT
    cast(sim, c, t, player=2)                       # another player's command: no group (intake)
    run(sim, 40)
    assert not events(w, CastStarted)


def test_out_of_range_walks_into_range_first():
    w = world()
    sim = Simulation(w)
    c, t = caster(w, 1, 10, 15), fighter(w, 2, 31, 15, owner=2, hp=1000)      # 20 cells: range 7
    cast(sim, c, t)
    run(sim, 400)
    (started,) = events(w, CastStarted)
    assert started.tick > 40 and c.x > 10            # it moved first
    assert t.hp < 1000


def test_cast_in_progress_is_not_interrupted_by_stop():
    w = world()
    sim = Simulation(w)
    c, t = caster(w, 1, 10, 15), fighter(w, 2, 17, 15, owner=2, hp=1000)
    cast(sim, c, t)
    until(sim, lambda: events(w, CastStarted))
    sim.step([Stop(1, (c.id,))])                    # brain order 2 runs before any mode (FUN_0056dca2)
    run(sim, 30)
    assert events(w, CastReleased) and t.hp < 1000


@pytest.mark.parametrize("order", ["move", "stop", "guard", "still", "attack", "cast"])
def test_no_new_order_interrupts_a_cast_in_progress(order):
    """Stop (`FUN_0056dbc6`, T) and every other order: `FUN_0056d969` / `FUN_0056d52b` write only state 0, order 0xc, the anchor and Brain mode 0 (never brain `+9`, `+0x15`,
    the target `+0x5c` or the wrapper `+0x64`), and the creature tick runs the Brain (`0x50f357`) before the state switch, whose order 2 puts state 0xd back (spells.md 9c.2)."""
    from engine.sim import Guard, MoveUnits, StandStill
    w = world()
    sim = Simulation(w)
    c, t, other = caster(w, 1, 10, 15), fighter(w, 2, 17, 15, owner=2, hp=1000), fighter(w, 3, 10, 12, owner=2, hp=1000)
    cast(sim, c, t)
    until(sim, lambda: events(w, CastStarted))
    cmd = {"move": MoveUnits(1, (c.id,), (10, 20)), "stop": Stop(1, (c.id,)), "guard": Guard(1, (c.id,)), "still": StandStill(1, (c.id,)),
           "attack": AttackUnit(1, (c.id,), other.id), "cast": CastSpell(1, (c.id,), FIRE_ARROW, other.id)}[order]
    mana = c.mana
    sim.step([cmd])
    assert c.brain_order == 2 and c.state == 0xd                # the cast stays in progress, state restored by the Brain in the same tick
    until(sim, lambda: events(w, CastReleased))
    run(sim, 30)
    assert t.hp < 1000                                           # released at the original target
    if order == "cast":                                          # the new cast waits for the old one (stored in brain +0x28 / +0x30) and then pays its own mana
        assert c.mana == mana - 3 and other.hp < 1000 and len(events(w, CastStarted)) == 2
    else:
        assert c.mana == mana and len(events(w, CastStarted)) == 1


def test_recovery_adds_the_complication():
    w = world()
    sim = Simulation(w)
    c, t = caster(w, 1, 10, 15), fighter(w, 2, 17, 15, owner=2, hp=1000)
    cast(sim, c, t)
    until(sim, lambda: events(w, CastReleased))
    # the release tick already ran phase 5: timer = recovery 4 + rand(0..3) + complication 3
    assert c.phase == 7 and 4 + 3 <= c.timer <= 4 + 3 + 3
    assert c.step_end == events(w, CastStarted)[0].tick


def test_target_removed_before_delivery_no_crash_no_damage():
    w = world()
    sim = Simulation(w)
    c, t = caster(w, 1, 10, 15), fighter(w, 2, 17, 15, owner=2, hp=1000)
    cast(sim, c, t)
    until(sim, lambda: w.carriers)
    w.units.pop(t.id)                               # the id is freed (stage 5 / a flyer's removal)
    run(sim, 20)
    assert not w.carriers and not events(w, Damage)


def test_dying_target_is_hit_again_like_a_melee_blow():
    w = world()
    sim = Simulation(w)
    c, t = caster(w, 1, 10, 15), fighter(w, 2, 17, 15, owner=2, hp=100)
    cast(sim, c, t)
    until(sim, lambda: w.carriers)
    t.hp = -3                                       # nothing in the chain tests the target's HP (9c.3)
    until(sim, lambda: not w.carriers)
    assert events(w, Damage) and t.hp < -3


def test_caster_removed_after_release_the_missile_still_hits_without_credit():
    w = world()
    sim = Simulation(w)
    c, t = caster(w, 1, 10, 15), fighter(w, 2, 17, 15, owner=2, hp=1000)
    cast(sim, c, t)
    until(sim, lambda: w.carriers)
    w.bury(c.id)                                    # the caster leaves the world (its object's +0x14 is 0)
    run(sim, 20)
    assert t.hp < 1000 and t.last_attacker is None


def test_kill_logs_died_and_credit_target():
    w = world()
    sim = Simulation(w)
    c, t = caster(w, 1, 10, 15), fighter(w, 2, 17, 15, owner=2, hp=4)
    cast(sim, c, t)
    run(sim, 40)
    assert events(w, Died) and t.hp <= 0 and t.last_attacker == c.id


def test_replay_gives_the_same_hash():
    def go():
        w = world()
        sim = Simulation(w)
        c, t = caster(w, 1, 10, 15), fighter(w, 2, 17, 15, owner=2, hp=1000)
        cast(sim, c, t)
        run(sim, 60)
        return w.dump_hash(), sim.log
    h1, log = go()
    w2 = world()
    c2, t2 = caster(w2, 1, 10, 15), fighter(w2, 2, 17, 15, owner=2, hp=1000)
    replay(Simulation(w2), log, 60)
    assert w2.dump_hash() == h1


def test_dump_has_no_cast_keys_until_a_cast_exists():
    w = world()
    c = caster(w, 1, 10, 15)
    c.spellbook = None
    assert "carriers" not in w.dump()
    assert "cast" not in str(w.dump()["units"][0])


def staff_mage(w, uid, x, y, count=1, rng=7):
    u = caster(w, uid, x, y, mana=0, rng=rng, book=0)
    u.combat.has_weapon = True
    u.combat.weapon_spell = (FIRE_ARROW, count)
    return u


def test_staff_attack_casts_for_free_at_the_item_level():
    w = world()
    sim = Simulation(w)
    c, t = staff_mage(w, 1, 10, 15), fighter(w, 2, 17, 15, owner=2, hp=1000)
    sim.step([AttackUnit(1, (c.id,), t.id)])
    run(sim, 60)
    hit = events(w, Damage)[0]                      # the attack order repeats the swing: more casts follow
    assert c.mana == 0 and 5 <= hit.amount <= 10 and events(w, CastReleased)[0].level == 1
    assert hit.attacker == c.id and not any(e.tick == 0 for e in events(w, CastStarted))


def test_staff_cast_reads_the_swing_target_at_every_start():
    from engine.sim import combat
    w = world()
    c, t = staff_mage(w, 1, 10, 15), fighter(w, 2, 17, 15, owner=2, hp=1000)
    c.cast = combat.SpellCast(FIRE_ARROW, target=0xDEAD, item_count=1)      # stale from an earlier swing
    c.swing_target, c.phase = t.id, 0
    combat.swing_tick(w, c)
    assert c.cast.target == t.id and c.phase == 5


def test_second_cast_waits_for_the_first_one_to_finish():
    w = world()
    sim = Simulation(w)
    c, t = caster(w, 1, 10, 15, mana=10), fighter(w, 2, 17, 15, owner=2, hp=1000)
    cast(sim, c, t)
    until(sim, lambda: events(w, CastStarted))
    cast(sim, c, t)                                 # ordered during the windup: brain order 2 runs first, the new order waits
    run(sim, 200)
    starts = events(w, CastStarted)
    assert len(starts) == 2 and starts[1].tick - starts[0].tick >= 5 + 4 + 3        # windup + recovery + complication at least
    assert c.mana == 10 - 6 and len(events(w, CastReleased)) == 2


def test_carrier_records_start_and_flight():
    w = world()
    sim = Simulation(w)
    c, t = caster(w, 1, 10, 15), fighter(w, 2, 17, 15, owner=2, hp=1000)
    cast(sim, c, t)
    until(sim, lambda: w.carriers)
    (m,) = w.carriers
    assert m.kind == "missile" and m.flight == 8 and m.start == (10 * 256 + c.sub_x, 15 * 256 + c.sub_y) and m.born == events(w, CastReleased)[0].tick


def test_cast_start_plays_the_attack_animation():
    w = world()
    sim = Simulation(w)
    c, t = caster(w, 1, 10, 15), fighter(w, 2, 17, 15, owner=2, hp=1000)
    cast(sim, c, t)
    until(sim, lambda: events(w, CastStarted))
    assert c.action == "attack" and c.action_start_tick == events(w, CastStarted)[0].tick
