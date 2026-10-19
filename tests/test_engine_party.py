"""The party at map start (docs/engine/triggers.md section 9, engine/party.py): synthetic worlds, always run."""

from types import SimpleNamespace

from allods2.formats import unitstats as U
from engine import party as PT
from engine.sim import triggers as T
from engine.world import World

from test_engine_ai import unit, world
from test_progression import human


class Types:
    def __init__(self):
        self.t = {10210: human("Start_MF", 10210, skill_blade=20, movement_type=1, face=1), 10220: human("Fighter_Hero", 10220, skill_blade=25, movement_type=1, face=1),
                  10230: human("Mage_Hero", 10230, skill_blade=25, mana_max=70, gender=1, movement_type=1, face=1)}

    def lookup(self, human_, sid):
        return self.t.get(sid) if human_ else None


class Assets:
    def __init__(self):
        self.types = Types()

    def unit_stats(self):
        return self.types

    def unit_set(self, type_id):
        return object()


def test_spread_is_max_5_and_sqrt_n_plus_4_truncated():
    assert [PT.spread(n) for n in (1, 2, 5, 6, 9, 16, 25)] == [5, 5, 6, 6, 7, 8, 9]


def test_one_drop_cell_draws_nothing_and_the_main_hero_stands_on_it():
    w = world()
    before = w.rng.state
    placed = PT.place_party(w, Assets(), [(20, 24)])
    assert [(u.x, u.y) for u in placed] == [(20, 24)]
    assert w.rng.state == before                                    # r = 0 and rand(0) draw nothing
    assert w.players[1].main_hero == placed[0].id and placed[0].owner == 1 and placed[0].human
    assert (placed[0].server_id // 10) % 1000 == 21                 # +0x14c 0x15 = scenario hero 10001


def test_cell_is_drawn_from_the_list_with_one_rand_of_len_minus_one():
    w = world(seed=7)
    r2 = type(w.rng)(7)
    k = r2.rand(2)
    placed = PT.place_party(w, Assets(), [(10, 10), (20, 20), (30, 30)])
    assert (placed[0].x, placed[0].y) == [(10, 10), (20, 20), (30, 30)][k]


def test_others_stand_in_the_radius_and_never_on_an_occupied_cell():
    w = world()
    placed = PT.place_party(w, Assets(), [(24, 24)], count=3)
    assert len(placed) == 3 and len({(u.x, u.y) for u in placed}) == 3
    assert (placed[0].x, placed[0].y) == (24, 24)
    r = PT.spread(3)
    assert all(abs(u.x - 24) <= r and abs(u.y - 24) <= r for u in placed[1:])
    assert [(u.server_id // 10) % 1000 for u in placed] == [21, 22, 23]


def test_main_hero_on_an_occupied_cell_falls_back_to_the_radius():
    w = world()
    unit(w, 5, 24, 24, 2)
    placed = PT.place_party(w, Assets(), [(24, 24)])
    assert (placed[0].x, placed[0].y) != (24, 24) and abs(placed[0].x - 24) <= PT.spread(1)


def test_zero_coordinate_or_no_drop_uses_the_random_fallback_cell():
    w = world(seed=3)
    r2 = type(w.rng)(3)
    x, y = r2.rand(0x46) + 0x1E, r2.rand(0x46) + 0x1E
    assert PT.drop_cell(w, []) == (x, y)
    w2 = world(seed=3)
    assert PT.drop_cell(w2, [(0, 12)]) == (x, y)


def test_a_world_with_a_main_hero_is_left_alone():
    w = world()
    h = unit(w, 5, 24, 24, 1)
    w.players[1].main_hero = h.id
    assert PT.place_party(w, Assets(), [(30, 30)]) == []
    assert len(w.units) == 1


def test_enable_places_the_party_before_compiling_and_the_hero_references_resolve():
    from test_engine_triggers import const, rec, script
    from allods2.formats import scenario as S
    w = world()
    drop = rec(S.CONSTANT, 1, (S.K_X, 30), (S.K_Y, 31))
    check = rec(1, 1, (S.K_UNIT, 10001), (S.K_UNIT, 10002))
    sc = script(instants=[drop], checks=[check])
    T.enable(w, sc, assets=Assets())
    assert w.script.drops == [(30, 31)]
    assert w.players[1].main_hero in w.units
    assert w.script.errors == []                                    # 10001 and (named by the script) 10002 both resolve
    assert len([u for u in w.units.values() if u.owner == 1]) == 2


def test_enable_without_drop_cells_places_nobody():
    w = world()
    T.enable(w, SimpleNamespace(instants=(), checks=(), triggers=()), assets=Assets())
    assert w.units == {} and w.players[1].main_hero == 0
