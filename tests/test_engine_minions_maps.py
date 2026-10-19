"""Summon and Control Spirit with the real unit tables (game files, skipped without the install; docs/data/spells.md 9b)."""

from allods2.assets import AssetCache
from allods2.cli import open_map
from allods2.formats import spelldefs
from engine.sim import CastSpell, Simulation, spawn, spells
from engine.sim.death import STAGE5_HP
from engine.world import World

from helpers import GFS, needs_data

pytestmark = needs_data


def test_every_summon_and_raise_template_exists_in_data_bin():
    a = AssetCache(GFS)
    w = World.from_map(open_map("73", GFS), a, seed=1)
    for roll in (1, 2, 3):
        for skill in (0, 25, 50, 75):
            assert spawn.template_by_name(w, spelldefs.summon_unit(skill, roll)) is not None
    for name in spelldefs.RAISE_TYPES.values():
        assert spawn.template_by_name(w, name) is not None


def hero_with_book(seed=3):
    a = AssetCache(GFS)
    w = World.from_map(open_map("73", GFS), a, seed=seed)
    hero = [u for u in w.units.values() if w.players[u.owner].human][0]
    hero.spellbook = (1 << spells.SUMMON) | (1 << spells.CONTROL_SPIRIT)
    hero.mana = hero.mana_max = 500
    return w, hero


def test_the_cast_makes_a_guarding_minion_that_the_cap_job_thins_out():
    w, hero = hero_with_book()
    sim = Simulation(w)
    for _ in range(3):
        sim.step([CastSpell(hero.owner, (hero.id,), spells.SUMMON, cell=(hero.x + 1, hero.y))])
        for _ in range(60):
            sim.step()
    minions = [u for u in w.units.values() if u.master == hero.id]
    assert len(minions) >= 2 and all(w.groups[m.order_group].order == 1 and m.order == 0xB for m in minions)
    assert all(m.owner == hero.owner and m.behaviour & 8 for m in minions)
    for _ in range(16 * 400):
        sim.step()
    assert 1 <= len([u for u in w.units.values() if u.master == hero.id]) <= len(minions)       # the cap job may thin them out, never the last
    assert w.check_consistency() == []


def test_control_spirit_raises_a_fallen_monster_as_a_stand_ground_zombie():
    w, hero = hero_with_book()
    victim = next(u for u in w.units.values() if not w.players[u.owner].human and not u.human and u.move_type == 1)
    victim.hp = -15                                          # death stage 2
    victim.state = 0x10
    w.remove_unit(victim.id)
    victim.x, victim.y = hero.x + 2, hero.y                   # a body next to the caster (the cast needs no walk)
    w.corpses[victim.id] = victim
    sim = Simulation(w)
    cell = (victim.x, victim.y)
    sim.step([CastSpell(hero.owner, (hero.id,), spells.CONTROL_SPIRIT, cell=cell)])
    for _ in range(400):
        sim.step()
    raised = [u for u in w.units.values() if u.stats is not None and u.stats.name == "F_Zombie.1" and u.owner == hero.owner]
    assert raised and victim.hp == STAGE5_HP
    assert w.groups[raised[0].order_group].order == 3 and raised[0].master == 0
