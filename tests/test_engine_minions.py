"""Summon, Control Spirit and the minion cap job (docs/data/spells.md 9b; engine/sim/spells.py, spawn.py).  Synthetic worlds, always run."""

import pytest

from allods2.formats.unitstats import MONSTER, UnitTable, UnitType
from engine.rng import Rng
from engine.sim import Simulation, ai, spells
from engine.sim.combat import combat_stats
from engine.sim.death import STAGE5_HP
from engine.world import DEAD, UNIT_ID_BASE, Unit

from spell_helpers import full_table
from test_engine_ai import EAST, hero, unit, world as ai_world


def _type(name, sid, unit_type, **kw):
    f = {"body": 10, "reaction": 10, "mind": 5, "spirit": 5, "hp_max": 30, "hp_regen": 0, "scan_range": 5, "speed": 24, "turn_rate": 32,
         "damage_min": 1, "damage_max": 2, "to_hit": 10, "defence": 3, "absorption": 0, "windup": 6, "recovery": 4, "token_size": 1, "face": 1,
         "movement_type": 1, "dying_time": 5, "wimpy": 0, "withdraw": 0, "spell_power": 0, "known_spells": -1}
    f.update(kw)
    return UnitType(MONSTER, sid, name, sid, unit_type, f, (), ())


class FakeAssets:
    """The unit table `spawn` reads, with the templates the two spells name."""

    def __init__(self):
        names = ["Squirrel", "Turtle", "Foot_Animated"]
        types = [_type(n if t == 1 else "%s.%d" % (n, t), 100 + 10 * i + t, 74 + i) for i, n in enumerate(names) for t in range(1, 5)]
        types += [_type("F_Zombie.1", 200, 82), _type("F_Skeleton.1", 201, 89), _type("Ghost", 202, 69, movement_type=2)]
        self.table = UnitTable(types)

    def unit_stats(self):
        return self.table

    def unit_set(self, type_id):
        return None


def world(seed=1, ai_on=False):
    w = ai_world(seed=seed)
    w.spell_table = full_table()
    w.assets = FakeAssets()
    w.ai_on = ai_on
    return w


def caster(w, skill=0, x=20, y=20):
    u = hero(w, 1, x, y)
    u.human = True
    u.skills = (0, 0, 0, 0, 0, skill)
    return u


def test_summon_creates_one_minion_near_the_caster_with_its_master_and_a_guard_group():
    w = world(seed=5)
    c = caster(w, skill=60)                                  # tier 60 // 25 + 1 = 3
    ref = Rng(5)
    roll = ref.rand(2) + 1
    m = spells.summon_release(w, c)
    base = {1: "Squirrel", 2: "Turtle", 3: "Foot_Animated"}[roll]
    assert m.stats.name == "%s.3" % base and m.owner == c.owner and m.master == c.id
    assert m.behaviour & 8 and m.id in w.units
    assert max(abs(m.x - c.x), abs(m.y - c.y)) <= 6
    g = w.groups[m.order_group]
    assert g.members == [m.id] and g.order == ai.G_GUARD       # FUN_005709d9(group, 0): the player's G
    assert m.order == 0xB                                     # members run the guard order
    assert g.radius == ai.MIN_GUARD_RANGE


def test_summon_tier_is_clamped_to_1_4_and_tier_1_has_no_suffix():
    for skill, suffix in ((0, ""), (24, ""), (25, ".2"), (75, ".4"), (500, ".4"), (-3, "")):
        w = world(seed=2)
        m = spells.summon_release(w, caster(w, skill))
        assert m.stats.name.endswith(suffix) if suffix else "." not in m.stats.name


def test_summon_without_a_free_cell_makes_no_unit_but_the_family_roll_is_drawn():
    w = world(seed=3)
    c = caster(w)
    w.blocked = lambda x, y, mt: True
    before = len(w.units)
    assert spells.summon_release(w, c) is None
    assert len(w.units) == before and w.rng.state != 3


def test_the_cap_job_removes_one_minion_of_a_master_with_probability_n_minus_1_percent():
    removed = 0
    for seed in range(1, 400):
        w = world(seed=seed)
        c = caster(w)
        ms = [spells.summon_release(w, c) for _ in range(3)]
        ref = Rng(w.rng.state)
        roll = ref.rand(99) + 1
        w.tick = 12
        from engine.sim import vitals
        vitals.vitals_system(w, [])
        gone = [m for m in ms if m.id not in w.units]
        assert len(gone) == (1 if roll < 3 else 0)
        if gone:
            removed += 1
            assert gone[0] is ms[0] and gone[0].master == 0          # the first minion of the key, no corpse
            assert gone[0].id not in w.corpses and gone[0].hp == STAGE5_HP
    assert 0 < removed < 20


def test_a_single_minion_is_never_removed_but_the_draw_is_spent():
    w = world(seed=9)
    c = caster(w)
    m = spells.summon_release(w, c)
    s = w.rng.state
    w.tick = 12
    spells.minion_job(w)
    assert m.id in w.units and w.rng.state != s


def _corpse(w, uid, x, y, hp, type_id=60):
    u = unit(w, uid, x, y, 2, hp=40)
    u.type_id = type_id
    u.stats = _type("Orc", 7, 60, body=40, reaction=21, mind=7, spirit=9, hp_max=80, to_hit=33, defence=21)
    u.hp = u.hp_max = 80
    u.combat = None
    u.hp = hp
    u.state = DEAD
    w.remove_unit(u.id)
    w.corpses[u.id] = u
    return u


@pytest.mark.parametrize("hp,name,body,reaction,hpmax", [(-15, "F_Zombie.1", 40, 11, 80), (-25, "F_Skeleton.1", 21, 11, 40), (-45, "Ghost", 10, 11, 40)])
def test_control_spirit_raises_a_body_by_stage_with_copied_stats_and_a_stand_ground_group(hp, name, body, reaction, hpmax):
    w = world()
    c = caster(w, x=18)
    body_unit = _corpse(w, 7, 20, 20, hp)
    m = spells.raise_release(w, c, (20, 20))
    assert m.stats.name == name and (m.x, m.y) == (20, 20) and m.owner == c.owner and m.master == 0
    assert m.hp == m.hp_max == hpmax
    assert m.stats.get("reaction") == reaction
    if name != "Ghost":
        assert m.stats.get("body") == body
    assert m.stats.get("to_hit") == 33 and m.stats.get("defence") == 21
    assert body_unit.hp == STAGE5_HP and body_unit.id not in w.corpses            # consumed
    g = w.groups[m.order_group]
    assert g.order == 3 and m.order == 0xC                    # FUN_00570f2b: stand ground (group order 3, member order 0xc)


def test_control_spirit_prefers_stage_2_over_3_skips_fresh_and_zombie_types_and_other_cells():
    w = world()
    c = caster(w, x=18)
    _corpse(w, 7, 20, 20, -5)                                 # stage 1: too fresh
    _corpse(w, 8, 20, 20, -30, type_id=0x55)                  # a zombie type: skipped
    _corpse(w, 9, 21, 20, -15)                                # other cell
    assert spells.raise_release(w, c, (20, 20)) is None
    s3 = _corpse(w, 10, 20, 20, -30)
    s2 = _corpse(w, 11, 20, 20, -15)
    m = spells.raise_release(w, c, (20, 20))
    assert m.stats.name == "F_Zombie.1" and s2.hp == STAGE5_HP and s3.hp == -30


def test_a_failed_placement_still_consumes_the_body():
    w = world()
    c = caster(w, x=18)
    b = _corpse(w, 7, 20, 20, -15)
    unit(w, 30, 20, 20, 2)                                    # a unit stands on the cell
    assert spells.raise_release(w, c, (20, 20)) is None
    assert b.hp == STAGE5_HP


def test_the_release_handlers_are_used_by_the_cell_cast():
    w = world(seed=4)
    c = caster(w, skill=10)
    c.stats = _type("Mage", 5, 9)
    w.assets = FakeAssets()
    spells.summon_release(w, c)
    assert any(u.master == c.id for u in w.units.values())


# --- the CMap iteration order of the cap job (combat.md 12.11, `FUN_0052bbb7`) ----------------------------------------------

def test_cmap_order_is_bucket_ascending_newest_first_inside_a_bucket():
    # bucket = (key >> 4) % 17: 0x10 and 0x11 share bucket 1, 0x20 is bucket 2, 0x110 (= 17 * 16) wraps to bucket 0
    assert spells.cmap_order([0x10, 0x20, 0x11]) == [0x11, 0x10, 0x20]
    assert spells.cmap_order([0x20, 0x10, 0x110, 0x11]) == [0x110, 0x11, 0x10, 0x20]
    assert spells.cmap_order([]) == []


def test_the_job_draws_per_master_in_cmap_order_and_removes_in_creature_list_order(monkeypatch):
    """Three masters with ids 0x10, 0x20, 0x11 (appearance order A, B, C): the draws go C, A, B.  A scripted roll of 1 on the second draw marks
    A (count 2 -> `roll < count`); its first minion is removed, the others stay."""
    w = world(seed=3)
    minions = []
    for k, key in enumerate((0x10, 0x20, 0x11, 0x10, 0x20, 0x11)):
        m = unit(w, 40 + k, 10 + k, 10, 2)
        m.master = key
        minions.append(m)
    draws = iter([50, 1, 50])
    seen = []

    def fake(rng, n):
        seen.append(n)
        return next(draws)
    monkeypatch.setattr(spells, "_rand1", fake)
    spells.minion_job(w)
    assert seen == [100, 100, 100]
    gone = [m for m in minions if m.id not in w.units]
    assert gone == [minions[0]]                         # key 0x10 was the second draw; its first creature in list order
    assert all(m.master for m in minions if m is not minions[0])


def test_marked_keys_remove_in_creature_list_order_not_key_order(monkeypatch):
    w = world(seed=3)
    a = unit(w, 40, 10, 10, 2); a.master = 0x20          # first in the list, but its key is drawn last
    b = unit(w, 41, 11, 10, 2); b.master = 0x10
    for k, key in enumerate((0x20, 0x10)):
        m = unit(w, 50 + k, 12 + k, 10, 2); m.master = key
    monkeypatch.setattr(spells, "_rand1", lambda rng, n: 1)         # every key marked
    order = []
    from engine.sim import death
    real = death.remove_dead
    monkeypatch.setattr(death, "remove_dead", lambda world, u: (order.append(u.id), real(world, u)))
    spells.minion_job(w)
    assert order == [a.id, b.id]                                      # list order (a, b), key order would be b, a
