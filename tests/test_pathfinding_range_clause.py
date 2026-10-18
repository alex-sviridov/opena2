"""Class-0x12 / order-5 clause of the static fallback and the default range (FUN_00556f56, FUN_0056ac5b)."""

from engine.sim.pathfinding import default_range, fallback_stamp, footprint_gap


def test_gap_axis_rule_FUN_00556f56():
    assert footprint_gap((10, 10), (10, 10), 1) == 0
    assert footprint_gap((10, 10), (14, 10), 1) == 4          # target after the anchor: t - h - size + 1
    assert footprint_gap((10, 10), (14, 10), 3) == 2          # the footprint covers the near cells
    assert footprint_gap((10, 10), (11, 10), 3) == 0          # clamped at 0
    assert footprint_gap((10, 10), (6, 10), 3) == 4           # target before the anchor: h - t, size ignored
    assert footprint_gap((10, 10), (13, 7), 2) == 3           # larger axis wins


def test_default_range_FUN_0056ac5b():
    assert default_range(1) == 1                              # no special: creature byte +0x12c
    assert default_range(1, spell_range=7, mana=10, spell_cost=10) == 7
    assert default_range(1, spell_range=7, mana=9, spell_cost=10) == 1     # not enough mana
    assert default_range(1, spell_range=7, mana=-5, spell_cost=-3) == 1    # signed compare
    assert default_range(2, spell_range=None, mana=99) == 2


def test_clause_only_for_group_0x12_and_mode_5():
    kw = dict(here=(10, 10), target=(15, 10), size=1, range_=2, tick=70000)
    assert fallback_stamp(0x12, 5, **kw) == 70000 & 0xFFFF     # gap 5 > 2: stamp the low 16 bits of the tick
    assert fallback_stamp(0x03, 5, **kw) is None               # other group order
    assert fallback_stamp(0x12, 1, **kw) is None               # other brain mode
    assert fallback_stamp(0x12, 5, here=(10, 10), target=(12, 10), size=1, range_=2, tick=5) is None   # gap 2 <= 2


def test_clause_no_fallback_cell_is_origin():
    assert fallback_stamp(0x12, 5, (0, 0), (9, 0), 1, 3, 40) == 40
