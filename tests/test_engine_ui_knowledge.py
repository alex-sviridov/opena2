"""The viewer's knowledge of unit types and the info panel's detail level (ui-layout 11.1).  Synthetic, always run."""

import pytest

from engine.sim import Simulation
from engine.ui import MainText
from engine.ui import info as I
from engine.ui.knowledge import CAP, TABLE_SIZE, Knowledge, knowledge_id
from engine.world import Killed, Removed

from test_engine_death import hero, mon, run, unit, world

TEXTS = MainText(["t%02x" % i for i in range(0x100)])
NAMES = ["n%d" % i for i in range(80)]


def ys(w, u, know):
    return {r.y for r in I.text_rows(w, u, TEXTS, NAMES, 1, know_all=False, knowledge=know)}


def foe(w, sid=77, n=1):
    m = unit(w, n, 5, 5 + n, owner=2)
    m.server_id = sid
    return m


def test_level_is_the_byte_shifted_right_and_zero_for_unusable_ids():
    k = Knowledge()
    k.table[77] = 5
    assert [k.level(i) for i in (0, 77, TABLE_SIZE, 5000)] == [0, 2, 0, 0]
    for b, d in ((0, 0), (1, 0), (2, 1), (3, 1), (13, 6), (14, 7)):
        k.table[78] = b
        assert k.level(78) == d


def test_credit_adds_one_per_kill_and_stops_at_14():
    k = Knowledge()
    assert [k.credit(9) for _ in range(CAP + 2)] == [True] * CAP + [False] * 2
    assert k.table[9] == 14 and k.level(9) == 7
    assert not k.credit(0) and not k.credit(TABLE_SIZE) and k.table[0] == 0


def test_blob_round_trip_is_the_0xa00_settings_chunk():
    k = Knowledge()
    k.credit(3), k.credit(3), k.credit(500)
    blob = k.to_blob()
    assert len(blob) == 0xA00 and blob[3] == 2 and blob[500] == 1
    assert Knowledge(blob).level(3) == 1


def test_a_human_victims_id_is_reduced_above_10000():
    w = world()
    h = hero(w, 1, 6, 6)
    h.server_id = 10213
    assert knowledge_id(h) == 21
    m = foe(w, 55, 2)
    assert knowledge_id(m) == 55


@pytest.mark.parametrize("d, rows", [(0, set()), (1, {0x2C, 0x36, 0x40, 0x4A}), (2, {200, 0xD2}), (3, {0x58, 0x62}),
                                     (5, {0x2C, 0x36}), (6, {0x70, 0x7A}), (7, {0x70, 0x7A})])
def test_rows_that_appear_at_each_level(d, rows):
    w = world()
    m = foe(w)
    k = Knowledge()
    k.table[77] = d * 2
    got = ys(w, m, k)
    assert rows <= got
    assert I.detail(w, 1, m, knowledge=k) == d


def test_each_row_group_needs_its_threshold():
    w = world()
    m = foe(w)
    k = Knowledge()
    seen = []
    for d in range(8):
        k.table[77] = d * 2
        seen.append({(r.text, r.y) for r in I.text_rows(w, m, TEXTS, NAMES, 1, know_all=False, knowledge=k)})
    for lo, hi in zip(seen, seen[1:]):
        assert lo <= hi                                                # more knowledge never hides a row
    names = lambda d, t: any(x[0] == t for x in seen[d])
    assert not names(0, "t13") and names(1, "t13")                     # Health, Mana: d > 0
    assert not names(1, "t15") and names(2, "t15")                     # Sight, Speed: d > 1
    assert not names(2, "t17") and names(3, "t17")                     # Dmg, Attack: d > 2
    assert not names(3, "t18") and names(4, "t18")                     # Absorb, Defense: d > 3
    assert not names(4, "t0f") and names(5, "t0f")                     # Body..Spirit: d > 4
    assert not names(5, "t29") and names(6, "t29")                     # resistances: d > 5
    assert ("t1c", 0x70) in seen[6] and ("t1b", 0x70) not in seen[6]   # Resistance header: d > 5
    assert not any(r.x == 6 and r.y == 0x70 for r in I.text_rows(w, m, TEXTS, NAMES, 1, know_all=False, knowledge=_at(k, 6)))
    assert any(r.x == 6 and r.y == 0x70 and r.text == "t1c" for r in I.text_rows(w, m, TEXTS, NAMES, 1, know_all=False, knowledge=_at(k, 7)))   # skills header, d > 6: a non-human gets text 0x1c
    assert {x[0] for x in seen[0]} <= {"n1"}                           # only the name line at d == 0


def _at(k, d):
    k.table[77] = d * 2
    return k


def test_own_allied_and_owner_zero_are_always_level_7_and_the_cheat_flag_too():
    w = world()
    own = unit(w, 2, 6, 5, owner=1)
    m = foe(w)
    assert I.detail(w, 1, own) == 7 and I.detail(w, 1, m) == 0
    assert I.detail(w, 1, m, know_all=True) == 7
    w.players[2].relations = (2, 0)                                    # owner 2 allied toward player 1
    assert I.detail(w, 1, m) == 7
    w.players[2].relations = (0, 0)
    w.players[1].relations = (0, 0x10)                                 # the viewer shares vision with player 2
    assert I.detail(w, 1, m) == 7
    w.players[1].relations = (0, 0)
    m.owner = 0
    assert I.detail(w, 1, m) == 7


def test_unknown_unit_without_a_table_shows_level_0():
    w = world()
    assert I.detail(w, 1, foe(w), knowledge=None) == 0
    m = foe(w, 0, 2)                                                    # id 0: never known
    k = Knowledge()
    k.table[0] = 14
    assert I.detail(w, 1, m, knowledge=k) == 0


def test_a_hero_kill_credits_the_killers_owner_through_the_killed_entry():
    w = world()
    h = hero(w, 1, 10, 10)
    sim = Simulation(w)
    k = Knowledge()
    for n in range(3):
        v = unit(w, 10 + n, 11, 11 + n, owner=2, hp=-20, stats=mon(xp=10, dying_time=0))
        v.server_id = 77
        v.last_attacker = h.id
        run(sim, 2)
    ev = [e for e in w.fight_log if isinstance(e, Killed)]
    assert len(ev) == 3 and all((e.server_id, e.killer, e.killer_owner) == (77, h.id, 1) for e in ev)
    assert k.feed(w, 1) == 3 and k.table[77] == 3 and k.level(77) == 1
    assert k.feed(w, 1) == 0                                            # already counted
    v = unit(w, 20, 12, 12, owner=2, hp=-20, stats=mon(xp=10, dying_time=0))
    v.server_id, v.last_attacker = 77, h.id
    run(sim, 2)
    assert k.feed(w, 1) == 1 and k.table[77] == 4 and k.level(77) == 2
    w.fight_log[:] = []                                                 # a drained log: only new entries count
    assert k.feed(w, 1) == 0
    assert Knowledge().feed(w, 2) == 0                                  # another owner learns nothing from this log


def test_only_a_living_hero_killer_counts_and_summoned_victims_still_do():
    w = world()
    h = hero(w, 1, 10, 10)
    plain = unit(w, 3, 12, 10, owner=1, hp=50)
    s = unit(w, 4, 11, 10, owner=2, hp=-20, stats=mon(xp=10, dying_time=0), behaviour=8)
    s.server_id, s.last_attacker = 40, h.id                             # summoned victim: the exe still counts it
    d = unit(w, 5, 11, 11, owner=2, hp=-20, stats=mon(xp=10, dying_time=0))
    d.server_id, d.last_attacker = 41, plain.id                         # plain unit killer: no credit
    e = unit(w, 6, 11, 12, owner=2, hp=-20, stats=mon(xp=10, dying_time=0))
    e.server_id, e.last_attacker = 42, h.id
    h.hp = -1                                                           # the killer is dying itself
    run(Simulation(w), 3)
    assert not [x for x in w.fight_log if isinstance(x, Killed)]
    assert len([x for x in w.fight_log if isinstance(x, Removed)]) == 3
