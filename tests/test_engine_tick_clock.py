"""`TickClock` = the exe's tick scheduler `FUN_00488aa1` (ui-layout 11.4, architecture 4); synthetic."""
from engine.sim import TickClock

P = 62


def run(clock, t0, t1, step=1):
    n = 0
    for t in range(t0, t1 + 1, step):
        n += clock.advance(t)
    return n


def test_steady_rate_is_one_tick_per_period():
    c = TickClock(P, 0)
    assert abs(run(c, 0, P * 160) - 160) <= 1


def test_stall_at_block_start_runs_one_tick():
    c = TickClock(P, 0)
    assert c.count == 0
    assert c.advance(100000) == 1                  # the count-0 tick re-bases to now; the lag is dropped
    assert c.advance(100001) == 0


def test_stall_runs_up_to_the_block_wrap_no_cap_of_15():
    c = TickClock(P, 0)
    c.advance(P)                                   # count 0 -> 1, base = P
    assert c.count == 1
    assert c.advance(10 ** 6) == 16                # counts 1..15, then the count-0 tick: 16, not 15
    assert c.count == 1


def test_stall_mid_block_count_formula():
    c = TickClock(P, 0)
    t = 0
    while c.count != 9:
        t += P
        c.advance(t)
    assert c.advance(t + 10 ** 6) == 17 - 9


def test_resume_after_dialog_is_one_tick():
    c = TickClock(P, 0)
    t = 0
    while c.count != 9:
        t += P
        c.advance(t)
    c.resume()                                     # the block counter is zeroed, the base stays stale
    assert c.advance(t + 60000) == 1
    assert c.advance(t + 60001) == 0
