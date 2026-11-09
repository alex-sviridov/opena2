"""K11: sound events never reach the world hash or a replay (docs/engine/audio.md 5, 8)."""

import json
import os

import numpy as np

from audio_scenarios import FakeAssets, fighter, world
from engine.sim import AttackUnit, Simulation, replay
from engine.sim.simulation import Simulation as Sim
from helpers import GFS, needs_data

GOLDEN = json.load(open(os.path.join(os.path.dirname(__file__), "golden.json"), encoding="ascii"))


def fight(assets, keep):
    w = world()
    w.assets = assets
    a, b = fighter(w, 1, 10, 10, 1, hp=200), fighter(w, 2, 11, 10, 2, hp=200)
    sim = Simulation(w, keep_sound_events=keep)
    sim.step([AttackUnit(1, (a.id,), b.id)])
    for _ in range(150):
        sim.step()
    return w, sim


def test_the_dump_and_rng_are_the_same_with_sound_events_on_or_off():
    on, _ = fight(FakeAssets(), True)
    off, _ = fight(None, False)
    assert on.sound_events and not off.sound_events
    assert on.dump_hash() == off.dump_hash() and on.rng.state == off.rng.state          # the sim never draws for sound
    assert "sound" not in json.dumps(on.dump())


def test_a_replay_gives_the_same_hash_and_the_same_events():
    w1, s1 = fight(FakeAssets(), True)
    w2 = world()
    w2.assets = FakeAssets()
    fighter(w2, 1, 10, 10, 1, hp=200), fighter(w2, 2, 11, 10, 2, hp=200)
    sim = Sim(w2, keep_sound_events=True)
    replay(sim, s1.log, 151)
    assert w2.dump_hash() == w1.dump_hash()
    assert [(e.tick, e.kind, e.sound) for e in w2.sound_events] == [(e.tick, e.kind, e.sound) for e in w1.sound_events]


@needs_data
def test_real_map_world_goldens_are_unchanged_by_the_event_list():
    from allods2.assets import AssetCache
    from allods2.cli import open_map
    from engine.world import World
    for m in ("10", "20"):
        w = World.from_map(open_map(m, GFS), AssetCache(GFS))
        assert w.sound_events == [] and w.dump_hash() == GOLDEN[m]
