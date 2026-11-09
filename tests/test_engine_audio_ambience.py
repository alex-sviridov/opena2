"""K11: ambience (docs/engine/audio.md 2.4): river / fire-wall loops, one-shot ids, night, the 5 s spacing, the object classes."""

import math
from types import SimpleNamespace

import numpy as np

from engine.audio.ambience import Ambience, hour_of, is_night, loop_mix, object_class
from engine.audio.mix import View
from engine.rng import Rng

RECS = {1: {"Phases": 7, "FireObject": -1, "DeadObject": 2}, 2: {"Phases": 7, "FireObject": -2, "DeadObject": -1},
        3: {"Phases": 1, "FireObject": -1, "DeadObject": -1}}


def world(n=60, water=(), fire=(), objs=()):
    cells = np.zeros((n, n), np.uint16)
    for x, y in water:
        cells[y, x] = 9 << 6                                   # terrain type 9: river
    by = {}
    for i, (x, y, t) in enumerate(objs):
        by.setdefault((x, y), []).append(i)
    objects = {i: SimpleNamespace(kind="object", type_id=t) for i, (_, _, t) in enumerate(objs)}
    return SimpleNamespace(width=n, height=n, cells=cells, cell_fx={c: (1, None, None, None, None, None) for c in fire}, objects=objects,
                           objects_at=lambda x, y: by.get((x, y), []), assets=SimpleNamespace(objects_reg=lambda: RECS), tick=0)


V = View(20, 20, 20, 15)


def test_object_classes_from_objects_reg_fields():
    assert object_class(RECS[1]) == 34 and object_class(RECS[2]) == 44 and object_class(RECS[3]) == 58


def test_hour_and_night():
    assert hour_of(0) == 6 and not is_night(0)
    assert hour_of(16 * 60 * 14) == 20 and is_night(16 * 60 * 14)
    assert is_night(16 * 60 * 21) and hour_of(16 * 60 * 18) == 0                     # (360 + 1080) / 60 % 24 = 0
    assert not is_night(16 * 60 * 13) and hour_of(16 * 60 * 13) == 19


def test_loop_volume_is_the_nearest_cell_and_pan_the_weighted_mean():
    cx, cy = V.x + V.w // 2, V.y + V.h // 2
    att, pan = loop_mix([(cx, cy)], V)
    assert att == 0 and pan == 0
    att, _ = loop_mix([(cx + 16, cy), (cx + 9, cy)], V)
    assert att == -int((math.exp(1) - 1) * 100) == -171                               # d = 9 -> floor(9 / 8) = 1
    att, pan = loop_mix([(cx + 40, cy)], V)
    assert att == -10000 and pan == 0                                                  # silent: a loudness weight of 0
    _, pan = loop_mix([(cx + 4, cy), (cx + 4, cy)], V)
    assert pan == 400                                                                  # (4 * 2000 / 20)


def test_river_loop_starts_updates_and_stops_with_the_source_count():
    a = Ambience(Rng(1))
    w = world(water=[(30, 30), (31, 30)])
    acts = a.update(0, w, V, 0)
    loops = [x for x in acts if x.action == "loop"]
    assert [x.sound for x in loops] == [50] and loops[0].name == "river"
    assert a.update(100, w, V, 0) == []                                               # same camera cell, timer not due: nothing
    acts = a.update(100, w, View(21, 20, 20, 15), 0)
    assert [x.action for x in acts] == ["loop"]                                       # moved: new volume / pan of the running loop
    acts = a.update(200, world(), View(22, 20, 20, 15), 0)
    assert [(x.action, x.name) for x in acts] == [("stop", "river")]


def test_fire_wall_loop_is_sound_90():
    a = Ambience(Rng(1))
    acts = a.update(0, world(fire=[(30, 28)]), V, 0)
    assert [(x.name, x.sound) for x in acts if x.action == "loop"] == [("fire", 90)]


def test_the_scan_window_is_clamped_and_covers_three_views():
    a = Ambience(Rng(1))
    w = world(n=80, water=[(5, 5), (7, 20), (8, 20), (0, 20), (60, 30), (61, 30), (72, 30)])
    river, *_ = a.scan(w, View(30, 20, 20, 15))
    assert (5, 5) not in river and (7, 20) not in river and (8, 20) not in river and (72, 30) not in river     # window x in [10, 70]
    assert (60, 30) in river and (61, 30) in river
    river, *_ = a.scan(w, V)                                                                                   # x in [8, 60]: the lower clamp is 8
    assert (8, 20) in river and (7, 20) not in river and (60, 30) in river and (61, 30) not in river


def test_one_shots_come_every_5_to_9_seconds_and_only_with_objects():
    a = Ambience(Rng(2), ids=set(range(600, 660)))
    w = world(objs=[(30, 30, 1)] * 3)
    acts = a.update(0, w, V, 0)
    shots = [x for x in acts if x.action == "oneshot"]
    assert len(shots) == 1 and 600 <= shots[0].sound < 660 and shots[0].att == 0       # SFX only, no attenuation
    assert 5000 <= a.next < 5000 + 0x7FFF // 7 + 1
    assert a.update(a.next - 1, w, View(20, 20, 20, 15), 0) == []
    assert any(x.action == "oneshot" for x in a.update(a.next, w, V, 0))
    assert Ambience(Rng(2)).update(0, world(), V, 0) == []                             # no objects, no water: silence


def test_one_shot_id_ranges_follow_the_counts_and_the_clock():
    ids = set(range(600, 660))

    def pick(n34, n58, clock, seeds=200):
        out = set()
        for s in range(seeds):
            out.add(Ambience(Rng(s), ids).oneshot_id(n34, n58, clock))
        return out
    assert pick(500, 0, 0) <= set(range(600, 610))                                     # many trees, day: forest 600-609
    assert pick(500, 0, 16 * 60 * 14) <= set(range(610, 620))                          # night adds 10
    assert pick(0, 500, 0) <= set(range(620, 630)) | set(range(640, 650))
    assert pick(0, 0, 0) <= set(range(640, 650)) and pick(0, 0, 0)


def test_missing_slots_are_rerolled_and_an_empty_table_gives_up():
    a = Ambience(Rng(1), ids={605})
    assert a.oneshot_id(500, 0, 0) == 605
    assert Ambience(Rng(1), ids={}).oneshot_id(500, 0, 0) is None
