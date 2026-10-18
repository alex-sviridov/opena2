"""Floating damage numbers (the original's "Flying damage" option, docs/engine/combat.md section 8): the pure model."""

from engine.view.damage import LIFE_MS, FloatingDamage


def test_own_units_drift_right_foreign_left_and_everything_rises_two_pixels_per_tick():
    f = FloatingDamage()
    own = f.add(1, 7, colour=0, foreign=False, size=1, now_ms=0, stamp=10)
    foe = f.add(2, 9, colour=1, foreign=True, size=2, now_ms=0, stamp=10)
    assert (own.x, own.y) == (16, -48) and (foe.x, foe.y) == (-32, -96)
    f.advance(3)
    assert (own.x, own.y) == (19, -54) and (foe.x, foe.y) == (-35, -102)


def test_numbers_of_one_unit_in_one_tick_are_summed_later_ones_are_new():
    f = FloatingDamage()
    a = f.add(1, 4, 0, True, 1, 0, stamp=5)
    b = f.add(1, 6, 0, True, 1, 0, stamp=5)
    c = f.add(1, 3, 0, True, 1, 0, stamp=6)
    d = f.add(2, 2, 0, True, 1, 0, stamp=5)
    assert a is b and a.value == 10 and c is not a and d is not a and len(f.numbers) == 3


def test_numbers_live_one_second_of_wall_time():
    f = FloatingDamage()
    f.add(1, 4, 0, True, 1, now_ms=100, stamp=1)
    assert len(f.visible(100 + LIFE_MS)) == 1
    assert f.visible(100 + LIFE_MS + 1) == []
    f.prune(100 + LIFE_MS + 1)
    assert f.numbers == []


def test_size_zero_is_treated_as_one():
    n = FloatingDamage().add(1, 1, 0, False, 0, 0, 0)
    assert (n.x, n.y) == (16, -48)
