"""Fog of war rules (docs/engine/vision.md): sight mask, refresh, explored cells, view filtering."""

import numpy as np

from allods2 import vision as v
from engine.sim import vision as sv
from engine.world import World, Unit  # noqa: F401


def flat(n=40, h=0):
    return np.full((n, n), h, np.int8)


def test_flat_mask_is_a_round_blob():
    hts = flat()
    cells = set(v.sight_mask(hts, 40, 40, 20, 20, 5 << 8))
    assert (20, 20) in cells and (25, 20) not in cells or (24, 20) in cells   # radius about the sight in cells
    assert (20, 24) in cells and (24, 24) not in cells or (23, 23) in cells
    straight = max(x - 20 for x, y in cells if y == 20)
    diag = max(x - 20 for x, y in cells if y - 20 == x - 20)
    assert straight > diag >= 3                                               # 128 per straight step, 181 per diagonal step
    assert all(7 <= x < 33 and 7 <= y < 33 for x, y in cells)                 # 7-cell border


def test_zero_sight_sees_nothing():
    assert v.sight_mask(flat(), 40, 40, 20, 20, 0) == []


def test_hill_shortens_and_valley_lengthens():
    base = len(v.sight_mask(flat(), 40, 40, 20, 20, 5 << 8))
    hill = flat()
    hill[:, 23:] = 60                                  # a wall of high ground east of the observer
    low = flat()
    low[:, 23:] = -20
    assert len(v.sight_mask(hill, 40, 40, 20, 20, 5 << 8)) < base < len(v.sight_mask(low, 40, 40, 20, 20, 5 << 8))


def test_high_ground_blocks_and_a_thin_ridge_does_not():
    plateau = flat()
    plateau[:, 23:] = 127                              # the height step is charged against the observer's height on every cell
    cells = set(v.sight_mask(plateau, 40, 40, 20, 20, 4 << 8))
    assert (22, 20) in cells and (23, 20) in cells and (24, 20) not in cells and (26, 20) not in cells    # the face is seen, nothing behind it
    assert (24, 20) in set(v.sight_mask(flat(), 40, 40, 20, 20, 4 << 8))
    assert (17, 20) in cells                           # the other side is untouched
    ridge = flat()
    ridge[18:23, 23] = 127                             # one cell wide: M(parent) is kept, so the cells behind it are seen again (formula quirk)
    cells = set(v.sight_mask(ridge, 40, 40, 20, 20, 8 << 8))
    assert (23, 20) in cells and (26, 20) in cells


def test_reveal_sets_both_bits_in_2x2_tiles_and_refresh_keeps_explored():
    fog = v.new_fog(40, 40)
    v.reveal(fog, [(10, 10)])
    assert fog[10, 10] == fog[11, 11] == v.IN_SIGHT and fog[12, 12] == 0
    v.begin_refresh(fog)
    assert fog[10, 10] == v.EXPLORED and not v.cell_in_sight(fog, 10, 10)


def test_structure_state():
    fog = v.new_fog(40, 40)
    cells = [(10, 10), (11, 10)]
    assert v.structure_state(fog, cells) == 2
    v.reveal(fog, [(10, 10)])
    v.begin_refresh(fog)
    assert v.structure_state(fog, cells) == 1
    v.reveal(fog, [(11, 10)])
    assert v.structure_state(fog, cells) == 0


# --- the vision system ---------------------------------------------------------------------------------------------------

from engine.sim import Simulation                       # noqa: E402
from engine.world import Player, UNIT_ID_BASE            # noqa: E402
from allods2.formats.unitstats import MONSTER, UnitType  # noqa: E402


def syn(n=48, scan=5, owner=1, at=(24, 24)):
    w = World(np.zeros((n, n), np.uint16), np.zeros((n, n), np.int8), "syn")
    w._cost = np.full((n, n), 8, np.uint8)
    w.players[1] = Player(1, 0, human=True)
    w.players[2] = Player(2, 1)
    t = UnitType(MONSTER, 1, "M", 1, 1, {"token_size": 1, "scan_range": scan}, (), ())
    u = Unit(UNIT_ID_BASE + 1, 1, owner, at[0], at[1], uid=1, hp=50, hp_max=50, facing=64, move_type=1, stats=t, server_id=1)
    w.add_unit(u)
    sv.enable(w, 1)
    return w, u


def test_fog_starts_black_and_the_first_pass_reveals_around_own_units():
    w, u = syn()
    assert not w.fog.any()
    sv.vision_system(w, [])
    assert v.cell_in_sight(w.fog, 24, 24) and v.cell_in_sight(w.fog, 28, 24) and not v.cell_in_sight(w.fog, 33, 24)
    assert w.fog_rev == 2                                # enable + the first reveal


def test_enemy_units_reveal_nothing():
    w, u = syn(owner=2)
    sv.vision_system(w, [])
    assert not w.fog.any()


def test_explored_cells_stay_explored_and_seen_follows_the_unit():
    w, u = syn()
    sim = Simulation(w, systems=[sv.vision_system])
    sim.step()
    assert v.cell_in_sight(w.fog, 24, 24)
    u.x = 14                                              # moved: reveals at once, the old area keeps its SEEN bit until the refresh
    sim.step()
    assert v.cell_in_sight(w.fog, 14, 24) and v.cell_in_sight(w.fog, 24, 24)
    while w.tick < 32:
        sim.step()                                        # the refresh at clock 32 (tick 31) clears SEEN
    assert v.cell_in_sight(w.fog, 14, 24)
    assert not v.cell_in_sight(w.fog, 24, 24) and w.fog[24, 24] & v.EXPLORED


def test_dead_bodies_stop_revealing_at_stage_three():
    w, u = syn()
    u.hp = -30
    sv.vision_system(w, [])
    assert not w.fog.any()


def test_sim_hash_is_unchanged_without_fog_and_deterministic_with_it():
    w1, _ = syn()
    w2, _ = syn()
    for w in (w1, w2):
        s = Simulation(w, systems=[sv.vision_system])
        for _ in range(70):
            s.step()
    assert w1.dump()["fog"] == w2.dump()["fog"]
    w3, _ = syn()
    w3.fog = None
    assert "fog" not in w3.dump()
