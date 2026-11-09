"""K11 slice 1: the simulation's sound events (docs/engine/audio.md 2, 5, 8).  Synthetic scenarios always run; the game-file part skips without the install."""

import json
import os

import pytest

from audio_scenarios import SCENARIOS, FakeAssets, digest, fighter, world
from engine.audio import events as ev
from engine.sim import Simulation, sounds
from helpers import GFS, needs_data

GOLDEN = json.load(open(os.path.join(os.path.dirname(__file__), "golden.json"), encoding="ascii"))["audio"]


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_scenario_events_match_the_golden(name):
    assert digest(SCENARIOS[name]()) == GOLDEN[name]


def test_a_pickup_and_a_switch_use_make_no_sound_event():
    assert SCENARIOS["pickup"]() == [] and SCENARIOS["switch"]() == []


def test_melee_sequence():
    evs = SCENARIOS["melee"]()
    sw = [e for e in evs if e.kind == ev.SWING]
    assert sw[0].sound == 100 and sw[0].bus == ev.SFX and sw[0].tick == 11 and sw[0].owner == 1
    hurts = [e for e in evs if e.kind == ev.HURT]
    assert [e.k for e in hurts[:3]] == [1, 1, 1] and hurts[3].k == 2            # easy while the new HP is at least half, then hard
    assert {e.sound for e in hurts} == {220, 221} and all(e.bus == ev.SPEECH and not e.hero for e in hurts)
    deaths = [e for e in evs if e.kind == ev.DEATH]
    assert len(deaths) == 1 and deaths[0].sound == 240 and deaths[0].k == 3     # once, at the start of the dying animation
    assert all(e.x // 256 in (10, 11) for e in evs)


def test_hero_victim_uses_the_voice_bank_on_the_speech_bus():
    evs = SCENARIOS["hero_melee"]()
    voices = [e for e in evs if e.kind in (ev.HURT, ev.DEATH)]
    assert [e.sound for e in voices[:2]] == [("hero", "aldor", "easy"), ("hero", "aldor", "hard")]
    assert voices[-1].sound == ("hero", "aldor", "dead") and all(e.hero and e.bus == ev.SPEECH for e in voices)


def test_cast_makes_the_spell_object_then_the_cast_frame():
    evs = SCENARIOS["cast"]()
    assert [e.kind for e in evs[:2]] == [ev.SPELL, ev.CAST]
    assert evs[0].sound == 510 and evs[1].sound == 501 and evs[0].tick < evs[1].tick      # 500 + 2n + 8 at the message, 500 + n at the cast frame


def test_blow_without_hp_change_plays_the_blow_slot_never_throttled_kind():
    w = world()
    u = fighter(w, 1, 10, 10, 1)
    sounds.hurt(w, u, 40, 40)
    (e,) = w.sound_events
    assert (e.kind, e.k, e.sound, e.bus) == (ev.HURT, 0, 200, ev.SFX)


def test_no_hurt_sound_when_the_new_hp_is_minus_10_or_less_and_the_heal_counts():
    w = world()
    u = fighter(w, 1, 10, 10, 1)
    sounds.hurt(w, u, 5, -10)
    assert w.sound_events == []
    sounds.hurt(w, u, 5, 30)
    assert w.sound_events[0].k == 1


def test_spell_object_skips_id_23_and_the_blizzard_is_id_523():
    w = world()
    sounds.spell_object(w, 1, 2, 23)
    assert w.sound_events == []
    sounds.spell_object(w, 1, 2, 13)
    sounds.blizzard(w, 5, 6)
    assert [(e.kind, e.sound) for e in w.sound_events] == [(ev.SPELL, 513), (ev.BLIZZARD, 523)]


def test_a_unit_without_data_or_an_empty_slot_emits_nothing():
    w = world()
    u = fighter(w, 1, 10, 10, 1)
    w.assets = None
    sounds.swing(w, u)
    assert w.sound_events == []
    w.assets = FakeAssets()
    w.sound_sets.clear()
    w.assets.unit_types = lambda: {1: type("T", (), {"values": {"Sound": [0, 0, 0, 0, 0]}})()}
    sounds.swing(w, u)
    assert w.sound_events == []


def test_skill_up_emits_the_message_sound_for_the_hero():
    from test_engine_death import hero
    from test_engine_death import world as dworld
    from engine.sim import xp
    w = dworld()
    w.assets = FakeAssets()
    h = hero(w, 1, 10, 10)
    xp.award(w, h, 10 ** 6, 1)
    ups = [e for e in w.sound_events if e.kind == ev.SKILLUP]
    assert ups and ups[0].sound == 15 and ups[0].uid == h.id and ups[0].owner == h.owner


def test_the_simulation_drops_unread_events_unless_asked_to_keep_them():
    w = world()
    a, b = fighter(w, 1, 10, 10, 1, hp=4000), fighter(w, 2, 11, 10, 2, hp=4000)
    from engine.sim import AttackUnit
    sim = Simulation(w)
    sim.step([AttackUnit(1, (a.id,), b.id)])
    peak = 0
    for _ in range(400):
        sim.step()
        peak = max(peak, len(w.sound_events))
    assert peak <= 4                                    # one tick's worth, however long the headless run
    w2 = world()
    a, b = fighter(w2, 1, 10, 10, 1, hp=4000), fighter(w2, 2, 11, 10, 2, hp=4000)
    sim2 = Simulation(w2, keep_sound_events=True)
    sim2.step([AttackUnit(1, (a.id,), b.id)])
    for _ in range(400):
        sim2.step()
    assert len(w2.sound_events) > 20


@needs_data
def test_real_unit_data_resolves_sound_slots_that_exist_in_the_table():
    from allods2.assets import AssetCache
    from allods2.cli import open_map
    from allods2.formats import soundtable
    from engine.audio.voices import bank_of
    from engine.world import World
    from allods2.common import as_fs
    assets = AssetCache(GFS)
    table = soundtable.load(as_fs(GFS))
    w = World.from_map(open_map("10", GFS), assets)
    seen = 0
    for u in w.units.values():
        for i in range(5):
            s = sounds.unit_slot(w, u, i)
            assert s == 0 or s in table.ids or s in table.missing
            seen += s > 0
    assert seen > 20
    t = {x.name: x for x in assets.unit_stats().types}
    u = next(iter(w.units.values()))
    u.human = True
    for name, bank in (("Start_MF", "aldor"), ("Start_FF", "sagita"), ("Start_MM", "hildarius"), ("Start_FM", "galinel"),
                       ("Fighter_Hero", "igles"), ("Mage_Hero", "dina")):
        u.stats, u.server_id = t[name], t[name].server_id
        assert bank_of(u) == bank
