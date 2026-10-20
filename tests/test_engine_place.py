"""The placement search FUN_00510089 and its free-cell test FUN_005563ca / FUN_0055c5a0 (docs/engine/triggers.md section 10;
engine/sim/place.py).  Synthetic worlds, always run."""

from types import SimpleNamespace

from engine import party as PT
from engine.rng import Rng
from engine.sim import place, spawn, triggers as T

from test_engine_ai import unit, world
from test_engine_party import Assets


def mover(move=1, size=1):
    return SimpleNamespace(move_type=move, stats=SimpleNamespace(token_size=size))


def fill(w, cells, uid0=100, **kw):
    for k, (x, y) in enumerate(cells):
        unit(w, uid0 + k, x, y, 2, **kw)


def square(cx, cy, h):
    return [(x, y) for x in range(cx - h, cx + h + 1) for y in range(cy - h, cy + h + 1)]


class Zero:
    """A rng whose every rand(n) is 0 (the random tries always hit the corner (x - r/2, y - r/2))."""
    def rand(self, n):
        return 0


def test_a_free_cell_is_free_and_a_unit_stamp_blocks_it():
    w = world()
    assert place.cell_free(w, mover(), 20, 20)
    unit(w, 1, 20, 20, 2)
    assert not place.cell_free(w, mover(), 20, 20)
    assert place.cell_free(w, mover(), 21, 20)


def test_a_unit_without_a_stamp_does_not_block_only_the_stamp_slots_are_read():
    w = world()
    u = unit(w, 1, 20, 20, 2)
    w.slots.stamp[0].clear()                        # a first-come loser holds no stamp (simulation.md 7.4)
    assert place.cell_free(w, mover(), 20, 20)
    assert w.units_at(20, 20)                       # the unit is still there: the old rule would have refused the cell


def test_ground_stamps_block_walkers_and_ghosts_flyer_stamps_block_flyers():
    w = world()
    w.slots.stamp[0][(20 << 8) | 20] = 99           # a ground stamp on (20, 20)
    w.slots.stamp[1][(20 << 8) | 22] = 99           # a flyer stamp on (22, 20)
    assert not place.cell_free(w, mover(1), 20, 20) and not place.cell_free(w, mover(2), 20, 20)
    assert place.cell_free(w, mover(3), 20, 20)     # the flyer mask 0x82 does not hold bit 0x40
    assert place.cell_free(w, mover(1), 22, 20) and not place.cell_free(w, mover(3), 22, 20)


def test_terrain_block_bits_follow_the_mover_mask():
    w = world()
    w._block[20, 20] = 0x04                         # bit 4: a ghost / bee mask (0x44) holds it, a walker (0x41) does not
    assert place.cell_free(w, mover(1), 20, 20)
    assert not place.cell_free(w, mover(2), 20, 20)
    w._block[21, 21] = 0x01
    assert not place.cell_free(w, mover(1), 21, 21)


def test_a_sized_creature_needs_the_whole_footprint_from_its_top_left_cell():
    w = world()
    unit(w, 1, 21, 21, 2)
    assert not place.cell_free(w, mover(1, 2), 20, 20)      # the 2 x 2 footprint covers (21, 21)
    assert place.cell_free(w, mover(1, 2), 22, 20)
    assert place.cell_free(w, mover(1, 1), 20, 20)


def test_positions_are_clamped_into_the_playable_rectangle():
    w = world(n=48)
    assert place.clamp(w, 0, 0) == (8, 8) and place.clamp(w, 47, 47) == (39, 39)
    assert place.clamp(w, 250, 3) == (39, 8)                # bytes: 250 is above the rectangle
    assert place.find_place(w, mover(), 0, 0, 0) == (8, 8)


def test_radius_zero_has_two_tries_and_draws_nothing():
    w = world()
    before = w.rng.state
    assert place.find_place(w, mover(), 20, 20, 0) == (20, 20)
    assert w.rng.state == before
    unit(w, 1, 20, 20, 2)
    assert place.find_place(w, mover(), 20, 20, 0) is None


def test_a_crowded_square_fails_after_exactly_r2_over_2_plus_2_tries_of_two_draws():
    w = world(seed=5)
    fill(w, square(24, 24, 2))                              # r = 4: the tries and the scan cover [22, 26]
    ref = Rng(5)
    for _ in range((4 * 4) // 2 + 2):
        ref.rand(4)
        ref.rand(4)
    assert place.find_place(w, mover(), 24, 24, 4) is None
    assert w.rng.state == ref.state


def test_the_last_free_cell_of_a_crowded_square_is_found_by_the_scan():
    for seed in range(1, 6):
        w = world(seed=seed)
        fill(w, [c for c in square(24, 24, 2) if c != (22, 26)])
        assert place.find_place(w, mover(), 24, 24, 4) == (22, 26)


def test_the_scan_runs_x_major_from_the_low_corner():
    w = world()
    w.rng = Zero()
    fill(w, [c for c in square(24, 24, 2) if c not in ((23, 26), (25, 23))])
    assert place.find_place(w, mover(), 24, 24, 4) == (23, 26)      # x first, then y: (23, 26) comes before (25, 23)


def test_party_members_fill_a_crowded_drop_area_without_sharing_cells():
    w = world()
    fill(w, [c for c in square(24, 24, 5) if c not in ((24, 24), (29, 29), (19, 19))])      # r = 5 for one hero
    placed = PT.place_party(w, Assets(), [(24, 24)], count=3)
    assert [(u.x, u.y) for u in placed][0] == (24, 24)
    assert {(u.x, u.y) for u in placed[1:]} <= {(29, 29), (19, 19)} and len({(u.x, u.y) for u in placed}) == len(placed)


def test_a_hero_with_no_free_cell_stays_off_the_map():
    w = world()
    fill(w, square(24, 24, 6))
    assert PT.place_party(w, Assets(), [(24, 24)]) == []


def test_summon_placement_uses_the_same_rule():
    w = world()
    fill(w, [c for c in square(24, 24, 2) if c != (22, 22)])
    tpl = SimpleNamespace(movement_type=1, unit_type=1, server_id=1)
    spot = place.find_place(w, SimpleNamespace(move_type=tpl.movement_type, stats=tpl), 24, 24, 4)
    assert spot == (22, 22)
    assert spawn.find_place is place.find_place and T.find_place is place.find_place
