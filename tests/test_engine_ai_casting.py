"""AI casting (phase K): special-attack rolls, computer mages, the idle heal / Shield / friend casts, Brain modes 8 / 9 for AI casts, the cell
cast order 0xe, Heal, Drain Life and the unbuilt-effect stubs.  Synthetic worlds, always run.  Spec: docs/engine/ai.md 12 (A§12.x), docs/data/spells.md."""

from allods2.formats.unitstats import MONSTER, UnitType
from engine.rng import Rng
from engine.sim import AttackUnit, CastSpell, Simulation, Stop, ai, spells
from engine.sim.combatstats import ArmourBlock, AttackRecord, CombatStats
from engine.world import UNIT_ID_BASE, CastReleased, CastStarted, Damage, Healed, Unit

from spell_helpers import full_table
from test_engine_ai import EAST, hero, run, world as ai_world

SLOT = 0x147


def world(seed=1, ai_on=True):
    w = ai_world(seed=seed)
    w.spell_table = full_table()
    w.ai_on = ai_on                     # the direct calls below need the AI fields; `Simulation(ai=True)` worlds start with it off (enable)
    return w


def template(mind=10, slots=(), known=-1, mana=0, power=-1, skills=(-1,) * 5, scan=6, hp_regen=10):
    f = {"scan_range": scan, "mind": mind, "token_size": 1, "movement_type": 1, "speed": 24, "turn_rate": 32, "known_spells": known,
         "mana_max": mana, "spell_power": power, "hp_regen": hp_regen, "mana_regen": 10}
    for i in range(3):
        n, p = slots[i] if i < len(slots) else (-1, -1)
        f["spell_%d" % (i + 1)], f["probability_%d" % (i + 1)] = n, p
    for k, name in enumerate(("skillfire", "skillwater", "skillair", "skillearth", "skillastral")):
        f[name] = skills[k]
    return UnitType(MONSTER, 1, "Test", 1, 1, f, (), ())


def monster(w, uid, x, y, owner=2, squad=0, hp=40, rng=1, **kw):
    t = template(**kw)
    u = Unit(UNIT_ID_BASE + uid, 1, owner, x, y, uid=uid, hp=hp, hp_max=hp, facing=EAST, squad=squad, stats=t)
    u.mover.turn_rate = 32
    mage = t.get("known_spells") not in (0, -1)
    u.combat = CombatStats(AttackRecord(skill=500, lo=3, sp=0), ArmourBlock(0, 0), windup=6, recovery=4, range=rng, mage=mage)
    if t.get("mana_max", 0) > 0:
        u.mana = u.mana_max = t.get("mana_max")
    w.add_unit(u)
    return u


def emitted(w):
    out = list(w.ai_emitted)
    w.ai_emitted.clear()
    return out


def mask(*ns):
    return sum(1 << n for n in ns)


# --- set-up (A§12.1) -----------------------------------------------------------------------------------------------------------

def test_the_slots_become_the_book_and_the_probabilities_are_scaled_by_0x147():
    t = template(slots=((5, 10), (18, 1), (27, 3)), power=30)
    assert spells.monster_slots(t) == ((5, 10 * SLOT), (18, SLOT), (27, 3 * SLOT))
    assert spells.monster_slots(template(slots=((29, 10),))) == ((29, 10 * SLOT), (0, 0), (0, 0))
    w = world()
    m = monster(w, 1, 20, 20, slots=((5, 10), (18, 1), (27, 3)), power=30, mind=24)
    assert spells.known_mask(m) == mask(5, 18, 27)
    assert spells.unit_level(m, w.spell_table.get(5)) == 30 - 30 + 24          # spell_power for every school, mind from the template


def test_a_mage_template_gets_its_mask_and_its_school_skills():
    w = world()
    m = monster(w, 1, 20, 20, known=mask(1, 24, 27), mana=150, mind=20, skills=(20, 30, 40, 50, 60), power=99)
    assert spells.known_mask(m) == mask(1, 24, 27) and ai.is_mage(w, m)
    assert spells.unit_level(m, w.spell_table.get(1)) == 20 - 30 + 20        # skillfire, not spell_power
    assert spells.unit_level(m, w.spell_table.get(24)) == 60 - 30 + 20       # skillastral
    melee = monster(w, 2, 22, 20)
    assert spells.known_mask(melee) == 0 and not ai.is_mage(w, melee)


# --- the slot roll (A§12.2) ----------------------------------------------------------------------------------------------------

def test_one_rand15_per_used_slot_in_order_and_the_last_passing_slot_wins():
    for seed in range(1, 60):
        w = world(seed)
        m = monster(w, 1, 20, 20, slots=((1, 40), (5, 30), (16, 20)))
        h = hero(w, 2, 23, 20)
        ref = Rng(seed)
        rolls = [ref.rand15() for _ in range(3)]
        expect = 0
        for (n, p), r in zip(((1, 40), (5, 30), (16, 20)), rolls):
            if r < p * SLOT:
                expect = n
        ai.engage(w, m, h)
        (cmd,) = emitted(w)
        assert w.rng.state == ref.state                                        # exactly three draws
        if expect:
            assert isinstance(cmd, CastSpell) and cmd.ai and cmd.spell_id == expect and cmd.target_id == h.id
            assert m.mode_cast and m.cast_target == h.id and m.ai_cast and h.ai.spell_mark == expect
        else:
            assert isinstance(cmd, AttackUnit) and m.mode_attack


def test_unused_slots_draw_nothing_and_a_monster_without_slots_draws_nothing():
    w = world(7)
    m = monster(w, 1, 20, 20, slots=((1, 0),))                                 # probability 0: one draw, never passes
    h = hero(w, 2, 23, 20)
    ref = Rng(7)
    ref.rand15()
    ai.engage(w, m, h)
    assert w.rng.state == ref.state and isinstance(emitted(w)[0], AttackUnit)
    plain = monster(w, 3, 20, 22)
    s = w.rng.state
    ai.engage(w, plain, h)
    assert w.rng.state == s


def test_teleport_only_when_the_target_is_more_than_two_cells_away():
    w = world()
    m = monster(w, 1, 20, 20, slots=((23, 100),))                              # 100 * 0x147 = 32700: passes unless rand15 > 32699
    near = hero(w, 2, 22, 20)
    ai.engage(w, m, near)
    assert [type(c) for c in emitted(w)] == [AttackUnit]                       # within 2 cells: falls through to mode 5
    far = hero(w, 3, 26, 20)
    ai.engage(w, m, far)
    (cmd,) = emitted(w)
    assert isinstance(cmd, CastSpell) and cmd.cell == (25, 19)                 # the first free cell of the 3 x 3 round the target, row by row


# --- target kinds of FUN_0056a981 (A§12.3) ---------------------------------------------------------------------------------------

def test_special_attack_targets_by_spell_number():
    w = world()
    h = hero(w, 2, 26, 20)
    cases = {1: ("unit", "enemy"), 18: ("unit", "enemy"), 6: ("cell", (26, 20)), 14: ("cell", (26, 20)), 27: ("unit", "self"),
             20: ("unit", "self"), 9: ("cell", (21, 20)), 22: (None, None)}
    for k, (n, (kind, where)) in enumerate(cases.items()):
        m = monster(w, 10 + k, 20, 20, slots=((n, 10),))
        ai.special_attack(w, m, h, n)
        cmds = emitted(w)
        assert m.ai_cast                                                       # brain+0x60 := 1 for every number, even 22 (no case)
        if kind is None:
            assert cmds == []
        elif kind == "cell":
            assert cmds[0].cell == where and cmds[0].target_id is None and m.mode_cell and m.cast_cell == where
        else:
            assert cmds[0].target_id == (h.id if where == "enemy" else m.id) and m.mode_cast
        w.units.pop(m.id)
        w._ucells.get((20, 20), set()).discard(m.id)


def test_a_slot_spell_missing_from_the_book_does_nothing():
    w = world()
    m = monster(w, 1, 20, 20, slots=((1, 10),))
    m.spellbook = 0
    ai.special_attack(w, m, hero(w, 2, 24, 20), 1)
    assert emitted(w) == [] and not m.ai_cast and not m.mode_cast


# --- computer mages engaging (A§12.4) ---------------------------------------------------------------------------------------------

def test_a_mage_picks_a_random_affordable_offensive_spell_one_draw():
    w = world(3)
    m = monster(w, 1, 20, 20, known=mask(1, 2, 24, 27, 29), mana=20, mind=20)  # Fire Ball costs 30 > 20, Heal / Shield defensive, 29 never listed
    h = hero(w, 2, 24, 20)
    ref = Rng(3)
    k = ref.rand15() * 1 // 0x8000
    ai.engage(w, m, h)
    (cmd,) = emitted(w)
    assert k == 0 and cmd.spell_id == 1 and cmd.target_id == h.id and w.rng.state == ref.state


def test_a_mage_with_nothing_to_pay_draws_once_and_melees():
    w = world(3)
    m = monster(w, 1, 20, 20, known=mask(2, 24), mana=20, mind=20)
    h = hero(w, 2, 24, 20)
    ref = Rng(3)
    ref.rand15()
    ai.engage(w, m, h)
    assert [type(c) for c in emitted(w)] == [AttackUnit] and w.rng.state == ref.state


def test_a_clever_mage_rethinks_in_30_percent_of_the_passes_and_ends_in_mode_5():
    seen = set()
    for seed in range(1, 80):
        seed *= 100003                                                         # the CRT LCG's first output is nearly linear in small seeds
        w = world(seed)
        m = monster(w, 1, 20, 20, known=mask(1, 5), mana=50, mind=60)
        h = hero(w, 2, 24, 20)
        ref = Rng(seed)
        draws = []
        while True:                                                            # the recursion of FUN_0057a769 -> FUN_0056acc8
            r = ref.rand15() * 100 // 0x8000
            draws.append(r)
            if r > 29:
                k = ref.rand15() * 2 // 0x8000
                break
        ai.engage(w, m, h)
        cmds = emitted(w)
        assert w.rng.state == ref.state
        assert cmds[0].spell_id == (1, 5)[k]
        if len(draws) > 1:                                                     # every outer level ends in mode 5
            assert [type(c) for c in cmds] == [CastSpell] + [AttackUnit] * (len(draws) - 1) and m.mode_attack
            seen.add("melee")
        else:
            assert len(cmds) == 1 and m.mode_cast
            seen.add("cast")
    assert seen == {"melee", "cast"}


# --- the idle mage (A§12.5) -----------------------------------------------------------------------------------------------------

def test_idle_mage_heals_itself_then_the_first_wounded_ally_then_shields_itself():
    w = world()
    m = monster(w, 1, 20, 20, known=mask(24, 27), mana=50, mind=40, skills=(0,) * 5)
    ally = monster(w, 2, 22, 20, hp=40)
    other = monster(w, 3, 18, 20, hp=40)
    w.players[2].relations = (1, 18) + (0,) * 14
    m.hp = 30
    ai.idle(w, m)
    assert [(type(c), c.spell_id if isinstance(c, CastSpell) else None) for c in emitted(w)] == [(Stop, None), (CastSpell, 24)]
    assert m.cast_target == m.id
    m.hp = 40
    ally.hp, other.hp = 39, 1                                                   # (int)(39/40) == (int)(1/40) == 0: ring order decides
    ai.idle(w, m)
    cmds = [c for c in emitted(w) if isinstance(c, CastSpell)]
    first = [o for o in ai.ring_cells((20, 20), 6) if o in ((22, 20), (18, 20))][0]
    assert cmds[0].target_id == (ally.id if first == (22, 20) else other.id)
    ally.hp = other.hp = 40
    ai.idle(w, m)
    (cmd,) = [c for c in emitted(w) if isinstance(c, CastSpell)]
    assert cmd.spell_id == 27 and cmd.target_id == m.id
    m.mana = 10                                                                 # mana must be above 10
    ai.idle(w, m)
    assert not [c for c in emitted(w) if isinstance(c, CastSpell)]


def test_idle_mage_without_shield_buffs_a_random_friend_at_full_mana_and_the_curse_quirk():
    w = world(5)
    m = monster(w, 1, 20, 20, known=mask(20, 24), mana=50, mind=40)
    friend = monster(w, 2, 21, 20)
    ref = Rng(5)
    ai.mage_idle(w, m)
    k = ref.rand15() * 2 // 0x8000                                             # the friend draw over [m, friend] (ring order: centre first)
    ref.rand15()                                                                # the spell draw over [20]
    (cmd,) = emitted(w)
    assert cmd.spell_id == 20 and cmd.target_id == (m.id, friend.id)[k] and w.rng.state == ref.state
    w2 = world(5)
    n = monster(w2, 1, 20, 20, known=mask(24, 28), mana=50, mind=40)          # no defensive spell but 24 / 27: the leftover lookup is Curse
    ai.mage_idle(w2, n)
    (cmd,) = emitted(w2)
    assert cmd.spell_id == 28
    w3 = world(5)
    p = monster(w3, 1, 20, 20, known=mask(20, 24), mana=50, mind=40)
    p.mana = 49                                                                 # not at full mana: nothing
    ai.mage_idle(w3, p)
    assert emitted(w3) == []


# --- AI casts in the Brain (A§12.7) ------------------------------------------------------------------------------------------------

def test_an_ai_cast_repeats_until_the_next_pass_and_a_player_cast_does_not():
    w = world()
    m = monster(w, 1, 20, 20, known=mask(1), mana=50, mind=30, skills=(30,) * 5)
    h = hero(w, 2, 25, 20)
    sim = Simulation(w, systems=[__import__("engine.sim.spells", fromlist=["x"]).carrier_system,
                                 __import__("engine.sim.movement", fromlist=["x"]).movement_system])
    ai.cast_at(w, m, h, 1)
    emitted(w)
    run(sim, 40)
    starts = [e for e in w.fight_log if isinstance(e, CastStarted)]
    assert len(starts) >= 2 and m.mode_cast and m.mana == 50 - 3 * len(starts)


def test_cell_cast_order_mode_9_approaches_turns_and_casts_with_an_unbuilt_effect():
    w = world()
    m = monster(w, 1, 12, 20, known=mask(6), mana=60, mind=30, skills=(30,) * 5)
    sim = Simulation(w, systems=[__import__("engine.sim.movement", fromlist=["x"]).movement_system])
    ai.cast_cell(w, m, (24, 20), 6)                                            # Poison Cloud, range 6 + 30 / 30 = 7
    emitted(w)
    run(sim, 120)
    starts = [e for e in w.fight_log if isinstance(e, CastStarted)]
    assert starts and starts[0].target is None and m.x == 24 - 7 and w.unbuilt_casts.get(6, 0) >= 1
    assert m.mana == 60 - 30 * len(starts)


def test_player_cell_cast_command_0x1f():
    w = world()
    m = monster(w, 1, 20, 20, owner=1, known=mask(6, 1), mana=60, mind=30, skills=(30,) * 5)
    sim = Simulation(w)
    sim.step([CastSpell(1, (m.id,), 1, None, cell=(22, 20))])                 # Fire Arrow targets a unit: refused (FUN_0051941a)
    assert m.order != spells.CELL_ORDER
    sim.step([CastSpell(1, (m.id,), 6, None, cell=(22, 20))])
    assert m.order == spells.CELL_ORDER and m.cast_cell == (22, 20)
    run(sim, 40)
    assert [e for e in w.fight_log if isinstance(e, CastStarted)] and w.unbuilt_casts.get(6) == 1   # a player's cast stops after one


# --- Heal and Drain Life (spells.md 4) -----------------------------------------------------------------------------------------------

def test_heal_amount_cap_war_and_regeneration_gates():
    w = world(9)
    m = monster(w, 1, 20, 20, known=mask(24), mana=50, mind=30, skills=(30,) * 5)
    t = monster(w, 2, 21, 20, hp=100)
    t.hp = 50
    sp = w.spell_table.get(24)
    ref = Rng(9)
    sc = sp.scaled(30)
    amount = sc.damage_min + ref.rand(sc.damage_spread - 1) + 1
    spells.heal_release(w, m, t, sp, 30)
    assert t.hp == 50 + amount and w.rng.state == ref.state
    t.hp = 99
    spells.heal_release(w, m, t, sp, 30)
    assert t.hp == 100                                                         # capped at maxHP - HP
    enemy = hero(w, 3, 22, 20)
    enemy.hp = 10
    spells.heal_release(w, m, enemy, sp, 30)                                   # the caster's owner is at war with it
    assert enemy.hp == 10
    dry = monster(w, 4, 19, 20, hp_regen=0)
    dry.hp = 1
    spells.heal_release(w, m, dry, sp, 30)                                     # +0x98 == 0: no effect
    assert dry.hp == 1


def test_heal_revives_a_dying_unit():
    w = world()
    m = monster(w, 1, 20, 20, known=mask(24), mana=50, mind=30, skills=(30,) * 5)
    t = monster(w, 2, 21, 20, hp=100)
    t.hp, t.death_seen, t.death_tick = -5, True, 3
    spells.heal_release(w, m, t, w.spell_table.get(24), 30)
    assert t.hp > 0 and not t.death_seen and t.done and any(isinstance(e, Healed) for e in w.fight_log)


def test_drain_life_protection_cap_attacker_and_caster_heal():
    w = world(4)
    m = monster(w, 1, 20, 20, known=mask(26), mana=50, mind=30, skills=(30,) * 5, hp=100)
    m.hp = 50
    t = hero(w, 2, 21, 20)
    t.combat.block.prot[5] = 50
    sp = w.spell_table.get(26)
    ref = Rng(4)
    sc = sp.scaled(30)
    raw = sc.damage_min + ref.rand(sc.damage_spread - 1) + 1
    amount = int(raw * 50 / 100)
    spells.drain_release(w, m, t, sp, 30)
    assert t.hp == 500 - amount and m.hp == 50 + amount and t.last_attacker == m.id
    assert any(isinstance(e, Damage) and e.amount == amount for e in w.fight_log)
    t.hp = -8                                                                  # capped at HP + 10 = 2
    before = m.hp
    spells.drain_release(w, m, t, sp, 30)
    assert t.hp == -10 and m.hp == min(before + 2, m.hp_max)


def test_unbuilt_releases_are_counted_not_guessed():
    w = world()
    m = monster(w, 1, 20, 20, known=mask(18), mana=50, mind=30, skills=(30,) * 5)
    t = hero(w, 2, 21, 20)
    from engine.world import SpellCast
    spells.cast_release(w, m, SpellCast(18, target=t.id), m.combat)
    assert w.unbuilt_casts == {18: 1} and t.hp == 500
    assert not [e for e in w.fight_log if isinstance(e, CastReleased)]


# --- determinism with the AI on ------------------------------------------------------------------------------------------------------

def _fight(seed):
    w = world(seed, ai_on=False)
    for k in range(3):
        monster(w, 1 + k, 20 + k, 20, squad=1, known=mask(1, 24, 27), mana=100, mind=40, skills=(40,) * 5, hp=40)
    for k in range(2):
        monster(w, 10 + k, 20 + k, 22, squad=2, slots=((5, 30), (27, 5)), power=30, mind=24)
    hero(w, 20, 26, 21)
    sim = Simulation(w, ai=True)
    run(sim, 400)
    return w, sim


def test_casting_squads_are_deterministic_and_replay_regenerates_the_same_casts():
    a, sa = _fight(11)
    b, _ = _fight(11)
    assert a.dump_hash() == b.dump_hash()
    assert any(isinstance(c, CastSpell) for _, c in sa.log)
    assert [e for e in a.fight_log if isinstance(e, CastStarted)]
