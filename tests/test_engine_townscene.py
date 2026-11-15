"""L6 (docs/engine/town-scenes.md): the town scenes' pure model (mask reader, click table, hover, the animation state machines on a fake clock with a seeded
rng) and the scene screen over the town core.  The synthetic tests need no install; the install tests (real masks, measured frame counts, a render of every
scene to out/) skip without one."""

import random
import sys
from pathlib import Path

import numpy as np
import pytest

from engine import townscene as TS
from engine.sim import campaign as C
from helpers import GFS

needs_install = pytest.mark.skipif(GFS is None or not GFS.exists("graphics/interface/town/townmask.bmp"), reason="no install")
OUT = Path(__file__).resolve().parents[1] / "out"


def make(town, seed=1, v301=1, chapter=10, glob=None):
    vars_ = {0x301: v301, 0x300: chapter}
    st = TS.SceneState.build(TS.SceneSpec.for_town(town), random.Random(seed), glob or TS.Globals(), var=lambda n: vars_.get(n, 0))
    st.vars = vars_
    return st


def run(st, ms, dt=68, hover=None):
    """Advance `ms` of wall clock in draws of `dt`; every sound started is collected (paths)."""
    out = []
    for _ in range(ms // dt):
        if hover is not None:
            st.hover(hover)
        st.advance(dt)
        out += [p for p, _ in st.take_sounds()]
    return out


# -- the mask ------------------------------------------------------------------------------------------------------------------------------

def test_region_table_is_the_spec_s():
    assert TS.REGION_OF_BYTE == {0x80: 2, 0x90: 1, 0xa0: 8, 0xb0: 0x10, 0xc0: 4, 0x20: 0x400, 0x40: 0x800, 0x50: 0x1000, 0x60: 0x200}


def test_mask_reader_subtracts_the_origin_and_is_minus_one_outside():
    ix = np.zeros((480, 640), np.uint8)
    ix[10, 20], ix[0, 0], ix[479, 639], ix[5, 5] = 0x90, 0xa0, 0x80, 0x33
    m = TS.Mask(ix)
    assert m.region_at(20, 10) == 1 and m.region_at(0, 0) == 8 and m.region_at(639, 479) == 2
    assert m.region_at(5, 5) == -1 and m.region_at(100, 100) == -1                      # an unknown byte / the zero byte: nothing
    assert m.region_at(160 + 20, 60 + 10, origin=(160, 60)) == 1                        # 800x600: the origin is (80 ... ) subtracted
    assert m.region_at(160 + 640, 60, origin=(160, 60)) == -1 and m.region_at(159, 60, origin=(160, 60)) == -1 and m.region_at(160, 59, origin=(160, 60)) == -1
    assert m.point_of(1) is None or m.index[m.point_of(1)[1], m.point_of(1)[0]] == 0x90


def test_noise_pixels_keep_the_quirk():
    ix = np.zeros((480, 640), np.uint8)
    ix[7, 9] = 0x60
    assert TS.Mask(ix).region_at(9, 7) == 0x200


def test_stand_in_rectangles_do_not_overlap_and_are_found():
    m = TS.StandInMask()
    for region in (TS.SHOP, TS.INN, TS.LEAVE):
        x, y = m.point_of(region)
        assert m.region_at(x, y) == region and m.region_at(x + 7, y + 3, origin=(7, 3)) == region
    r = list(m.RECTS.values())
    for i, a in enumerate(r):
        for b in r[i + 1:]:
            assert a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0] or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1]


# -- click table ---------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("town", [1, 2, 3])
def test_common_clicks(town):
    st = make(town)
    assert st.press(1) == ("shop",) and st.press(2) == ("inn",) and st.press(8) == ("leave",) and st.press(0x10) == ("menu",) and st.press(-1) is None


def test_human_leave_is_reported_even_without_the_gate_var_the_core_decides():
    assert make(1, v301=0).press(8) == ("leave",)
    assert [make(1).press(r) for r in (4, 0x200, 0x400, 0x800, 0x1000)] == [None] * 5


def test_speech_clicks_use_the_chapter_variable():
    d, k = make(3, chapter=40), make(2, chapter=70)
    assert d.press(0x200) == ("speech", "druidinnkeeper40") and d.press(0x1000) == ("speech", "druidshopkeeper40") and d.press(4) is None and d.press(0x400) is None
    assert k.press(4) == ("speech", "kaargwoman70") and k.press(0x200) == ("speech", "kaargwoman70")
    assert k.press(0x400) == ("speech", "kaargman70") and k.press(0x800) == ("speech", "kaargguard70") and k.press(0x1000) is None


def test_vars_argument_overrides():
    assert make(2).press(0x800, vars=lambda n: 99) == ("speech", "kaargguard99")


# -- the human scene -----------------------------------------------------------------------------------------------------------------------

def test_stars_every_tenth_start_plays_again():
    st = make(1)
    played = []
    for start in range(25):
        st.flags |= 0x10
        sounds = 0
        while st.flags & 0x10:
            st._stars()
            sounds += sum(1 for p, _ in st.take_sounds() if p.endswith("stars.wav"))
        played.append(sounds)
    assert [i for i, n in enumerate(played) if n] == [0, 10, 20] and st.g.stars == 5       # the global counter: reset at 10, counts the starts in between
    # and the frames: 1..8 are shown, then nothing
    st2 = make(1)
    st2.flags |= 0x10
    shown = []
    while st2.flags & 0x10:
        st2._stars()
        shown.append(st2.stars_frame)
    assert shown == [1, 2, 3, 4, 5, 6, 7, 8, 0]


def test_stars_hover_region_starts_them():
    st = make(1)
    run(st, 1200, hover=0x10)
    assert st.g.stars >= 1


def test_gate_counter_closed_without_the_var():
    st = make(1, v301=0)
    sounds = run(st, 1500, hover=TS.LEAVE)
    assert st.gate == 8 and not any("gate" in p for p in sounds)


def test_gate_opens_with_one_sound_and_closes_with_one_sound():
    st = make(1)
    sounds = run(st, 1500, hover=TS.LEAVE)
    assert st.gate == 0 and [p for p in sounds if "gate" in p] == ["sfx/town/gateup.wav"]
    sounds = run(st, 1500, hover=-1)
    assert st.gate == 8 and [p for p in sounds if "gate" in p] == ["sfx/town/gatedn.wav"]


def test_guard_direction_rule():
    st = make(1, v301=0)
    n = st.count("graphics/interface/townbirds/guards/sprites.16a")
    assert st.guard_f == n - 1 and st.guard_snd == 0                                     # `+0xf0` = 0 at the load (CONFIRMED)
    sounds = run(st, 300, hover=-1)                                                     # the first step: dir +1 with the latch 0 -> Guard2 once
    assert [p for p in sounds if "guard" in p] == ["sfx/town/guard2.wav"] and st.guard_f == n - 1
    sounds = run(st, 1500, hover=TS.LEAVE)                                              # closed gate, pointer on it: dir -1, the frame falls to 0
    assert st.guard_f == 0 and [p for p in sounds if "guard" in p] == ["sfx/town/guard1.wav"]
    sounds = run(st, 1500, hover=-1)                                                    # pointer off: dir +1 up to the idle frame
    assert st.guard_f == n - 1 and [p for p in sounds if "guard" in p] == ["sfx/town/guard2.wav"]
    st = make(1, v301=1)                                                                # open gate: the guards never move
    run(st, 1500, hover=TS.LEAVE)
    assert st.guard_f == n - 1


def test_visit_kinds_are_new_every_visit_and_the_dervish_differs_from_the_baba():
    seen = set()
    for seed in range(200):
        st = make(1, seed)
        assert 0 <= st.horse_kind < 5 and 0 <= st.baba_kind < 4 and 0 <= st.dervish_kind < 4 and st.baba_kind != st.dervish_kind
        seen.add((st.horse_kind, st.baba_kind, st.dervish_kind))
    assert len(seen) > 20
    st = make(1, 3)
    ops = st.draw_ops()
    assert ("spr", st.dervish_path(), 0, *TS.Human.DERVISH_POS[st.dervish_kind]) in ops
    assert ("spr", st.horse_path(), 0, *TS.Human.HORSE_POS[st.horse_kind]) in ops       # the horse idles on frame 0


def test_dervish_loops_for_the_whole_visit():
    st = make(1)
    n = st.count(st.dervish_path())
    run(st, 67 * 2 * n + 70, dt=68)
    assert st.flags & 0x400 and 0 <= st.dervish < n


def test_baba_first_deadline_and_pause_rule():
    st = make(1, 5)
    t = 0
    while not st.flags & 0x200:
        st.advance(10)
        t += 10
        assert t < 5000
    assert 2000 < t <= 4010 and st.baba == 0 and 0 <= st.baba_set < 2
    n = st.count(st.baba_path())
    while st.flags & 0x200:
        st.advance(10)
    end = st.now
    assert st.baba == -1 and 2000 <= st.baba_delay < 7000 and st.baba_base <= end                 # the pause counts from the last animation step
    assert end - st.baba_base <= 70 and n >= 31


def test_birds_timing_group_count_and_sound():
    glob = TS.Globals()
    st = make(1, 4, glob=glob)
    d = glob.bird_delay
    assert 1000 <= d < 3000
    t = 0
    while not st.flags & 0x80:
        st.advance(10)
        t += 10
    assert d < t <= d + 10 and 1 <= st.bird_count <= 3 and 0 <= st.bird_group < 3
    snd = [p for p, _ in st.take_sounds() if "birds" in p]
    assert snd == ["sfx/town/birds1.wav" if st.bird_count == 1 else "sfx/town/birds2.wav"]
    ops = st.draw_ops()
    assert sum(1 for o in ops if o[0] == "spr" and "/birds" in o[1]) == st.bird_count and ("bmp", "graphics/interface/town/town_add.bmp", 0, 0, True) in ops
    nxt = glob.bird_delay                                                                  # re-rolled at the start for the next flight
    steps = 0
    while st.flags & 0x80:
        st.advance(68)
        steps += 1
    assert 56 <= steps <= 60
    assert not any(o[0] == "spr" and "/birds" in o[1] for o in st.draw_ops())
    t = 0
    while not st.flags & 0x80:
        st.advance(10)
        t += 10
    assert nxt < t <= nxt + 70                                                              # counted from the end of the last flight


def test_random_rolls_sign_five_percent_fluger_two_percent():
    st = make(1, 9)
    signs = flugers = 0
    for _ in range(4000):
        st.flags &= ~0x60
        st.rolls()
        signs += bool(st.flags & 0x40)
        flugers += bool(st.flags & 0x20)
    assert 150 < signs < 250 and 50 < flugers < 110


def test_tavern_hover_loops_and_shop_entry_sound_once():
    st = make(1)
    sounds = run(st, 1500, hover=TS.INN)
    assert sounds.count("sfx/town/point.wav") >= 2 and st.flags & 2
    st = make(1)
    sounds = run(st, 800, hover=TS.SHOP)
    assert sounds.count("sfx/town/shop/enter.wav") == 1
    run(st, 70, hover=-1)
    assert "sfx/town/shop/enter.wav" in run(st, 70, hover=TS.SHOP)                         # leaving the region re-arms it
    assert ("bmp", "graphics/interface/town/shop_l.bmp", 0x108, 0x108, False) in st.draw_ops()


def test_horse_sound_rule():
    st = make(1)
    st.horse_set = 2
    st.flags |= 0x100
    st.horse = 0
    heard = []
    for _ in range(20):
        st.advance(68)
        heard += [p for p, _ in st.take_sounds()]
        if not st.flags & 0x100:
            break
    assert heard.count("sfx/town/horse1.wav") == 1 and heard.count("sfx/town/horse2.wav") == 1


def test_entry_loop_sound_is_first_and_looped():
    assert make(1).take_sounds() == [("sfx/town/crowd.wav", True)]
    assert make(2).take_sounds() == [("sfx/town_kaarg/kvox1.wav", True)] and make(3).take_sounds() == [("sfx/town_druid/dforest1.wav", True)]


def test_step_runs_only_after_the_period():
    st = make(1, v301=1)
    st.advance(67)
    assert st.last_step == 0                                                                 # `> 0x43`, not >=
    st.advance(1)
    assert st.last_step == 68


# -- the druid scene -----------------------------------------------------------------------------------------------------------------------

def test_druid_hover_plays_variant_three_and_entry_sounds_once():
    st = make(3)
    st.take_sounds()
    st.hover(TS.SHOP)
    assert st.v[TS.SHOP] == 2 and st.f[TS.SHOP] == 0 and st.flags & 1                     # variant 2, frame -1 then one step now
    snd = [p for p, _ in st.take_sounds()]
    assert snd == ["sfx/town_druid/ddruid1.wav", "sfx/town_druid/denter2.wav"]
    st.hover(TS.SHOP)
    assert st.take_sounds() == []
    st.hover(-1)
    st.hover(TS.INN)
    assert st.v[TS.INN] == 2 and [p for p, _ in st.take_sounds()] == ["sfx/town_druid/ddruid2.wav", "sfx/town_druid/denter1.wav"]
    st.hover(8)
    assert [p for p, _ in st.take_sounds()] == ["sfx/town_druid/dout.wav"]
    st.hover(0x1000)
    assert st.take_sounds() == []


def test_druid_entry_latches_clear_each_other_and_every_other_region():
    """`0x4cfd58` (CONFIRMED): entering a region clears the other two latches (so shop -> inn -> shop plays Denter2 again), regions 4 / 0x200 / 0x1000 keep them, any other region
    (the stars patch, ...) clears all three and ORs its flag."""
    st = make(3)
    st.take_sounds()
    for region, name in ((TS.SHOP, "denter2.wav"), (TS.INN, "denter1.wav"), (TS.SHOP, "denter2.wav"), (8, "dout.wav")):
        st.hover(region)
        assert [p for p, _ in st.take_sounds()][-1] == "sfx/town_druid/" + name
    st.hover(0x200)
    st.hover(8)
    assert st.take_sounds() == []                                                           # 0x200 kept the "out" latch
    st.hover(0x10)
    assert st.flags & 0x10 and st.latch == set()
    st.hover(8)
    assert [p for p, _ in st.take_sounds()] == ["sfx/town_druid/dout.wav"]


def test_druid_figures_are_woman_on_the_shop_side_and_man_on_the_inn_side():
    """CONFIRMED loader `0x4ce914`: list `+0x2b0` (state `+0x2ec`, region 1) is loaded from `woman\\`, list `+0x268` (state `+0x2a4`, region 2) from `man\\`."""
    st = make(3)
    ops = [o[1] for o in st.draw_ops() if o[0] == "bmp"]
    assert any("/woman/a10001" in p for p in ops) and any("/man/a10001" in p for p in ops)
    st.hover(TS.INN)
    assert "graphics/interface/town_druid/man/a30001.bmp" in [o[1] for o in st.draw_ops() if o[0] == "bmp"]
    st.hover(TS.SHOP)
    assert ("bmp", "graphics/interface/town_druid/woman/a30001.bmp", 0x154, 0xe0, False) in st.draw_ops()


def test_druid_figure_step_end_rule_and_frame_counts():
    """The step (`0x4cfb45` / `0x4cfbf6`): ++, at the list's count -> frame 0, state -1, flag cleared; counts: shop (woman) 15 / 20 / 20, inn (man) 19 / 19 / 20."""
    st = make(3)
    for who, counts in ((TS.SHOP, (15, 20, 20)), (TS.INN, (19, 19, 20))):
        for v, n in enumerate(counts):
            st.v[who], st.f[who] = v, 0
            st.flags |= st.FLAG[who]
            for _ in range(n - 1):
                st.tick()
            assert st.v[who] == v and st.f[who] == n - 1 and st.flags & st.FLAG[who]
            st.tick()
            assert st.v[who] == -1 and st.f[who] == 0 and not st.flags & st.FLAG[who]


def test_druid_hover_variant_runs_to_its_end_and_does_not_restart_while_hovered():
    st = make(3)
    run(st, 3000, hover=TS.SHOP)
    assert st.v[TS.SHOP] == -1 and not st.flags & 1                                          # a3 has 20 frames at 100 ms
    ops = st.draw_ops()
    assert ("bmp", "graphics/interface/town_druid/woman/a30001.bmp", 0x154, 0xe0, False) in ops and st.region == TS.SHOP


def test_druid_hili_patch_only_for_hover_or_variant_two():
    st = make(3)
    st.v[TS.SHOP], st.f[TS.SHOP] = 0, 3
    assert not any("hili_shop" in o[1] for o in st.draw_ops() if o[0] == "bmp")             # `0x4cf65a`: region == 1 or state == 2
    st.v[TS.SHOP] = 2
    assert any("hili_shop" in o[1] for o in st.draw_ops() if o[0] == "bmp")


def test_druid_load_state_and_first_delays():
    """`0x4ce641` (CONFIRMED): both figure timers `rand(2000) + 2000`, the bug `rand(5000) + 7000`, every stamp = now (nothing fires on the first draw), states -1, flags 0."""
    for seed in range(20):
        st = make(3, seed)
        assert 2000 <= st.delay[TS.SHOP] < 4000 and 2000 <= st.delay[TS.INN] < 4000 and 7000 <= st.bug_delay < 12000
        assert st.v == {1: -1, 2: -1} and st.flags == 0 and st.latch == set() and st.region == -1
        assert st.bug_v == -1 and st.bug_f == -1 and st.liz_seq == -1


def test_druid_ambient_variant_is_rand2_unless_over_the_region():
    variants = set()
    for seed in range(40):
        st = make(3, seed)
        st.delay[TS.SHOP] = 100
        st.advance(200)
        variants.add(st.v[TS.SHOP])
        assert st.v[TS.SHOP] in (0, 1)
    assert variants == {0, 1}
    st = make(3)
    st.delay[TS.SHOP], st.region = 100, TS.SHOP                                               # pointer on the region without a hover call: the starter reads `+0xb4`
    st.advance(200)
    assert st.v[TS.SHOP] == 2


def test_druid_figure_timer_rearms_even_when_busy():
    st = make(3)
    st.v[TS.SHOP], st.f[TS.SHOP] = 1, 2                                                       # busy
    st.delay[TS.SHOP] = 100
    st.advance(150)
    assert st.v[TS.SHOP] == 1 and st.stamp[TS.SHOP] == 150 and 3500 <= st.delay[TS.SHOP] < 8500    # no restart, but re-armed (`0x4d00de`)


def test_druid_lizard_restarts_at_once_and_follows_the_tables():
    st = make(3, 2)
    st.advance(10)
    assert st.liz_seq in (0, 1, 2, 3) and st.flags & 0x100
    seq = st.liz_seq
    frames = []
    for _ in range(len(TS.Druid.LIZARD[seq]) + 1):
        frames.append(st.draw_ops()[-1][2] if st.liz_seq != -1 else None)
        st.advance(101)
    assert st.liz_seq == seq or st.liz_seq in (0, 1, 2, 3)                                    # idle -> a new one starts at the same draw
    assert [len(t) for t in TS.Druid.LIZARD] == [8, 11, 25, 47]


def test_druid_lizard_choice_distribution():
    counts = [0] * 4
    for seed in range(600):
        st = make(3, seed)
        st.advance(1)
        counts[st.liz_seq] += 1
    assert 12 / 15 * 600 * 0.85 < counts[0] and all(25 < c < 70 for c in counts[1:])


def test_druid_bug_first_after_seven_to_twelve_seconds_then_ten_to_twenty():
    st = make(3, 3)
    d = st.bug_delay
    assert 7000 <= d < 12000
    t = 0
    while st.bug_v == -1:
        st.advance(100)
        t += 100
    assert d < t <= d + 100 and 0 <= st.bug_v < 3 and st.flags & 0x80 and 10000 <= st.bug_delay < 20000
    assert not any(o[0] == "spr" and "bug" in o[1] for o in st.draw_ops())                    # the first run: frame -1 until the first step (`0x4cfc77`)
    st.advance(101)
    assert any(o[0] == "spr" and "bug" in o[1] and o[2] == st.bug_v * 61 for o in st.draw_ops())
    for _ in range(61):
        st.advance(101)
    assert st.bug_v == -1 and st.bug_f == 0


def test_druid_ambient_stamps_are_the_load_time_nothing_on_the_first_draw():
    """`0x4ce641` stamps `+0xb8 / +0x2f8 / +0x2fc` = now: the birds / trees fire after their (process-global) first delay, the wolf after 60 s."""
    glob = TS.Globals()
    st = make(3, 1, glob=glob)
    st.advance(1)
    assert [p for p, _ in st.take_sounds() if "dbird" in p or "dtree" in p or "dwolf" in p] == []
    assert 2000 <= glob.druid_birds < 4000 and 2000 <= glob.druid_trees < 4000
    snd = run(st, 4200, dt=100)
    assert any("dbird" in p for p in snd) and any("dtree" in p for p in snd) and not any("dwolf1" in p for p in snd)
    assert any("dwolf1" in p for p in run(st, 60000, dt=100))


# -- the Kaarg scene -----------------------------------------------------------------------------------------------------------------------

def test_kaarg_nothing_runs_until_a_timer_fires_and_first_delays():
    st = make(2, 7)
    delays = dict(st.delay)
    assert all(2000 <= delays[k] < 4000 for k in ("girl1", "girl2", "guard")) and 4000 <= delays["dervish"] < 4500
    assert st.flags == 0
    t, fired = 0, {}
    while len(fired) < 4 and t < 6000:
        st.advance(10)
        t += 10
        for k, (flag, _, _) in TS.Kaarg.NPC.items():
            if st.flags & flag and k not in fired:
                fired[k] = t
    for k, at in fired.items():
        assert delays[k] < at <= delays[k] + 10
    assert set(fired) == {"girl1", "girl2", "guard", "dervish"}


def test_kaarg_later_delays_after_a_run():
    st = make(2, 3)
    st.delay["guard"] = 100
    st.advance(200)
    assert st.v["guard"] == 0 and 7500 <= st.delay["guard"] < 12500
    st.delay["girl1"] = 100
    st.advance(200)
    assert 3500 <= st.delay["girl1"] < 8500 and st.v["girl1"] in (0, 1)
    st.delay["dervish"] = 100
    st.advance(200)
    assert 3700 <= st.delay["dervish"] < 4200


def test_kaarg_ambient_first_draw_and_kman_every_45s():
    glob = TS.Globals()
    st = make(2, 1, glob=glob)
    st.take_sounds()
    st.advance(1)
    snd = [p for p, _ in st.take_sounds()]
    assert any("kbird" in p for p in snd) and "sfx/town_kaarg/kman1.wav" in snd and any("kvox" in p for p in snd)       # the stamps `+0xb8 / +0x25c / +0x260` are never written before: all three fire at once
    t, n = 1, 0
    while t < 100000:
        st.advance(100)
        t += 100
        n += sum(1 for p, _ in st.take_sounds() if p.endswith("kman1.wav"))
    assert n == 2
    assert any("kvox" in p for p in run(make(2, 2, glob=glob), 6000))


def test_kaarg_session_stamps_and_step_clock_survive_a_reopening():
    glob = TS.Globals()
    st = make(2, 1, glob=glob)
    st.take_sounds()
    st.advance(1)
    assert st.take_sounds() and st.last_step == 0
    st2 = make(2, 5, glob=glob)                                  # the next opening: the object lives on, the loader does not re-stamp voices / birds / Kman1
    st2.take_sounds()
    st2.advance(50)
    assert [p for p, _ in st2.take_sounds() if "kman1" in p or "kbird" in p or "kvox" in p] == []
    assert st2.last_step == 50                                   # the step clock `0x628248` is a process global: the first draw runs a step
    st3 = make(2, 7)
    st3.advance(1)
    assert st3.last_step == 0


def test_kaarg_gates_follow_the_hover_with_one_sound_each_way():
    st = make(2)
    sounds = run(st, 1500, dt=101, hover=TS.LEAVE)
    assert st.gate == 10 and [p for p in sounds if "kdoor" in p] == ["sfx/town_kaarg/kdoor1.wav"]
    sounds = run(st, 1500, dt=101, hover=-1)
    assert st.gate == 0 and [p for p in sounds if "kdoor" in p] == ["sfx/town_kaarg/kdoor2.wav"]
    assert st.draw_ops()[-1] == ("bmp", "graphics/interface/town_kaarg/maingates/m0000.bmp", 152, 256, False)


def test_kaarg_guard_footsteps_by_frame():
    st = make(2, 11)
    st.v["guard"] = 0
    heard = []
    for f in list(range(0, 55)) + list(range(0, 8)):
        st.f["guard"] = f
        for _ in range(3):                                                                  # several draws on one frame: the latch fires once
            st.after_draw()
        heard += [p for p, _ in st.take_sounds()]
    steps = [p for p in heard if "ksteps" in p]
    assert len(steps) == len([f for f in list(range(0, 55)) + list(range(0, 8)) if f in (5, 13, 21, 47, 9, 17, 23, 51, 31)])
    assert all(p in ("sfx/town_kaarg/ksteps2.wav", "sfx/town_kaarg/ksteps21.wav", "sfx/town_kaarg/ksteps1.wav", "sfx/town_kaarg/ksteps11.wav", "sfx/town_kaarg/ksteps3.wav",
                     "sfx/town_kaarg/ksteps31.wav") for p in steps)
    st.f["guard"] = 55                                                                      # the dead table entries
    st.after_draw()
    assert st.take_sounds() == []
    st.v["guard"] = -1                                                                      # idle: no switch
    st.f["guard"] = 5
    st.after_draw()
    assert st.take_sounds() == []


def test_kaarg_enter_sounds():
    st = make(2)
    st.take_sounds()
    st.hover(TS.SHOP)
    st.hover(TS.SHOP)
    st.hover(TS.INN)
    assert [p for p, _ in st.take_sounds()] == ["sfx/town_kaarg/kenter2.wav", "sfx/town_kaarg/kenter1.wav"]
    st.hover(0x800)                                                                         # an NPC region returns at once
    assert st.take_sounds() == []


# -- the screen over the core (the stand-in, no install) -------------------------------------------------------------------------------------

spoken = []                                              # the voice lines `shell_in_town`'s services were asked to play


class FakeTownFS:
    """Just `main/text/town.txt` (one section) and the speech file names it needs."""

    def __init__(self, files=("speech/town/0097t000p01.wav", "speech/town/0090f040p01.wav")):
        self.files = set(files)

    def read(self, path):
        assert path == TS.TOWN_TEXT
        return (b"#plagatguard\r\n<npc=97, part=1>\r\nNo.\r\n#kaargwoman40\r\n<npc=90, iammale, iamfighter, part=1>\r\nHi.\r\n<npc=90, iamfemale, iammage, part=1>\r\nHi!\r\n")

    def exists(self, path):
        return path in self.files

    def open(self, path):                                # the scene's own files are not here: the stand-in mask / defaults
        raise KeyError(path)


def shell_in_town(town, v301=0, chapter=10):
    from engine.campaign import CampaignGame
    from engine.shell import Services, Shell
    saves, loops, sounds, music = [], [], [], []
    sh = Shell(None, services=Services(autosave=saves.append, music=music.append, loop=loops.append, sound=sounds.append, speech=spoken.append))
    sh.rng = random.Random(1)
    sh.campaign = CampaignGame()
    camp = sh.campaign.camp
    camp.available = [(C.TOWN, town)]
    camp.vars[C.CHAPTER] = chapter
    if v301:
        camp.set(0x301, v301)
    sh.start("locations")
    sys.path.insert(0, str(Path(__file__).parent))
    from shell_scenarios import map_walk
    map_walk(sh, (C.TOWN, town))
    assert sh.name == "town"
    sh.fs = FakeTownFS()                                 # only after the scene was built (the stand-in mask needs no files)
    del spoken[:]
    return sh, saves, loops, sounds


def test_human_leave_needs_var_0x301_through_the_shell():
    from shell_scenarios import click_region
    sh, saves, loops, sounds = shell_in_town(1, v301=0)
    del spoken[:]
    assert loops == ["sfx/town/crowd.wav"] or loops == []                                  # the stand-in still starts the entry loop of the spec
    click_region(sh, TS.LEAVE)
    assert sh.name == "town" and saves == [] and spoken == ["speech/town/0097t000p01.wav"]
    sh.town_core().camp.set(0x301, 1)
    click_region(sh, TS.LEAVE)
    assert sh.name == "locations" and saves == [9998] and loops[-1] is None                # leaving the scene stops the loop


def test_druid_and_kaarg_leave_without_the_gate():
    from shell_scenarios import click_region
    for town in (2, 3):
        sh, saves, loops, sounds = shell_in_town(town)
        click_region(sh, TS.LEAVE)
        assert sh.name == "locations" and saves == [9998]


def test_release_and_keys_do_nothing_in_the_scene():
    from engine.shell.events import Key, Move, Press, Release
    sh, *_ = shell_in_town(2)
    x, y = sh.current.point_of(TS.INN)
    sh.handle(Move(x, y))
    sh.handle(Release(x, y))
    sh.handle(Press(x, y, 3))
    sh.handle(Key("return"))
    assert sh.name == "town" and sh.current.menu is None
    sh.handle(Press(x, y, 1))
    assert sh.name == "inn"


def test_escape_opens_the_scene_menu_and_closes_it():
    from engine.shell.events import Key
    sh, *_ = shell_in_town(2)
    sh.fs = None
    sh.handle(Key("escape"))                                                                 # `0x484a76` -> `0x41f` (`game+0x3d4` empty)
    assert sh.current.menu is not None
    sh.handle(Key("escape"))                                                                 # the menu's ESC = Return to Game
    assert sh.current.menu is None and sh.name == "town"


def test_update_advances_the_state_and_plays_its_sounds():
    sh, saves, loops, sounds = shell_in_town(2)
    n = len(sounds)
    sh.update(5)
    assert len(sounds) > n and any("kbird" in s for s in sounds)                            # the first bird fires on the first draw


def test_scene_reentry_rebuilds_the_state():
    from shell_scenarios import click_region
    sh, *_ = shell_in_town(1, v301=1)
    first = sh.current.state
    click_region(sh, TS.INN)
    assert sh.name == "inn"
    sh.handle(__import__("engine.shell.events", fromlist=["Key"]).Key("escape"))
    assert sh.name == "town" and sh.current.state is not first


# -- the install -----------------------------------------------------------------------------------------------------------------------------

BOXES = {   # town: {region: (x0, x1, y0, y1)}, the dense boxes of town-scenes 2
    1: {2: (128, 212, 326, 411), 1: (255, 333, 262, 346), 8: (157, 244, 93, 219), 0x10: (343, 405, 290, 418), 4: (419, 582, 300, 424)},
    3: {2: (121, 167, 190, 272), 1: (376, 568, 224, 393), 8: (1, 172, 294, 372), 0x200: (167, 199, 203, 268), 0x1000: (339, 388, 254, 366)},
    2: {2: (489, 602, 217, 434), 1: (324, 369, 255, 340), 8: (158, 213, 252, 338), 0x10: (1, 148, 5, 452), 4: (262, 297, 286, 387), 0x200: (220, 248, 284, 386),
        0x800: (136, 246, 174, 221), 0x400: (420, 518, 335, 477)}}


@needs_install
@pytest.mark.parametrize("town", [1, 2, 3])
def test_real_masks_dense_regions(town):
    m = TS.Mask.load(GFS, town)
    assert m.index.shape == (480, 640)
    for region, (x0, x1, y0, y1) in BOXES[town].items():
        ys, xs = np.nonzero(m.index == TS.BYTE_OF_REGION[region])
        inside = ((xs >= x0 - 3) & (xs <= x1 + 3) & (ys >= y0 - 3) & (ys <= y1 + 3)).mean()
        assert inside > 0.95, (town, region, inside)
        assert len(xs) > 2000
        x, y = m.point_of(region)
        assert x0 <= x <= x1 and y0 <= y <= y1 and m.region_at(x, y) == region
        assert m.region_at(x + 80, y + 40, origin=(80, 40)) == region
    assert m.region_at(-1, 5) == -1 and m.region_at(640, 5) == -1 and m.region_at(5, 480) == -1


@needs_install
def test_measured_counts_match_the_spec():
    for town, expect in ((1, {"townbirds/tavern/sprites.16a": 10, "townbirds/shopie/sprites.16a": 30, "townbirds/guards/sprites.16a": 8, "townbirds/birds1/sprites.16a": 57,
                              "townbirds/horse1/a1/sprites.16a": 15, "townbirds/baba1/a1/sprites.16a": 31, "townbirds/baba1/a2/sprites.16a": 32,
                              "townbirds/dervish1/sprites.16a": 30}),
                         (3, {"town_druid/bug/sprites.16a": 183, "town_druid/lizard/sprites.16a": 42, "town_druid/man/a1": 19, "town_druid/man/a2": 19, "town_druid/man/a3": 20,
                              "town_druid/woman/a1": 15, "town_druid/woman/a2": 20, "town_druid/woman/a3": 20}),
                         (2, {"town_kaarg/girl1/g1": 31, "town_kaarg/girl1/g2": 30, "town_kaarg/girl2/g1": 31, "town_kaarg/guard/g": 55, "town_kaarg/dervish/d": 30,
                              "town_kaarg/maingates/m": 11})):
        spec, mask, real = TS.load_scene(GFS, town)
        assert real
        for k, n in expect.items():
            assert spec.counts["graphics/interface/" + k] == n, k


@needs_install
def test_missing_install_files_fall_back_to_the_stand_in():
    class Empty:
        def exists(self, p):
            return False

        def open(self, p):
            raise KeyError(p)

        read = open
    spec, mask, real = TS.load_scene(Empty(), 1)
    assert not real and isinstance(mask, TS.StandInMask)


@needs_install
@pytest.mark.parametrize("town", [1, 2, 3])
def test_every_scene_layer_resolves_and_one_frame_paints(town):
    pg = pytest.importorskip("pygame")
    from engine.backend_pygame.shell import scene_screenshot
    from engine.backend_pygame.shellkit import Painter
    from engine.shell.scene import Scene
    from engine.shell.town import ops_of
    from allods2.graphics import SpriteFile
    spec, mask, real = TS.load_scene(GFS, town)
    st = TS.SceneState.build(spec, random.Random(100 + town), TS.Globals(), var=lambda n: 10 if n == 0x300 else 1)
    seen, sprites = set(), {}
    best, best_n = None, -1
    regions = [TS.SHOP, TS.INN, TS.LEAVE, -1, 0x10]
    for i in range(6000):                                                                      # 6 minutes of draws at 60 ms, hovering the regions in turn
        st.hover(regions[(i // 40) % len(regions)])
        st.advance(60)
        ops = st.draw_ops()
        for op in ops:
            seen.add(op[:3] if op[0] == "spr" else op[:2])
        if len(ops) > best_n and st.region in (-1, 1, 2):
            best, best_n = ops, len(ops)
        st.take_sounds()
    for op in seen:
        if op[0] == "bmp":
            assert GFS.exists(op[1]), op
        else:
            n = sprites.setdefault(op[1], len(SpriteFile.load(op[1], GFS).sprites))
            assert 0 <= op[2] < n, op
    # the scene with the most layers, painted at 640x480 and at 800x600 (the black border), to look at
    OUT.mkdir(exist_ok=True)
    painter = Painter(GFS)
    from PIL import Image
    for size in ((640, 480), (800, 600)):
        ox, oy = (size[0] - 640) // 2, (size[1] - 480) // 2
        px = scene_screenshot(Scene(ops_of(best, ox, oy), cursor=False), size, painter)
        assert px.shape == (size[1], size[0], 3) and px[oy + 240, ox + 320].any()
        Image.fromarray(np.asarray(px, np.uint8)).save(OUT / ("town_scene_%s_%d.png" % (spec.race, size[0])))


# -- the scene menu (message 0x41f) -------------------------------------------------------------------------------------------------------

def _click(sh, rect):
    from engine.shell.events import Move, Press, Release
    x, y = rect.x + 5, rect.y + 5
    sh.handle(Move(x, y))
    sh.handle(Press(x, y, 1))
    sh.handle(Release(x, y, 1))


def test_menu_message_opens_the_scene_menu_and_it_is_modal():
    from engine.shell.events import Key, Move, Press, Release
    sh, *_ = shell_in_town(2)
    sh.fs = None                                                                             # the menu texts fall back to the built-in labels
    scene = sh.current
    out = scene.state.press(TS.MENU)
    assert out == ("menu",)
    scene.open_menu()
    m = scene.menu
    assert [e[0] for e in m.entries()] == ["save", "load", "sound", "abort", "return"] and [e[2] for e in m.entries()] == [False, False, True, True, True]
    assert len(sh.scene().ops) > 5
    x, y = scene.point_of(TS.INN)                                                           # a click over the INN region does not reach the scene
    sh.handle(Press(x, y, 1))
    sh.handle(Release(x, y, 1))
    assert sh.name == "town" and sh.town_core().view == "scene"
    _click(sh, m.rects()[0])                                                                 # Save: not built, disabled
    assert scene.menu is m and m.page == "menu"
    _click(sh, m.rects()[4])                                                                 # Return to Game
    assert scene.menu is None
    scene.open_menu()
    sh.handle(Key("escape"))                                                                 # ESC = Return (0x446)
    assert scene.menu is None


def test_menu_abort_game_pages_and_exits():
    from engine.shell.events import Move, Press, Release

    def click(scene, i):
        r = scene.menu.rects()[i]
        x, y = r.x + 5, r.y + 5
        out = [scene._menu_event(e) for e in (Move(x, y), Press(x, y, 1), Release(x, y, 1))]
        return [o for o in out if o]
    sh, *_ = shell_in_town(3)
    sh.fs = None                                                                             # the menu texts fall back to the built-in labels
    scene = sh.current
    scene.open_menu()
    assert click(scene, 3) == []                                                             # Abort Game -> the second window
    assert scene.menu.page == "abort" and [e[0] for e in scene.menu.entries()] == ["exit_menu", "exit_windows", "return"]
    assert click(scene, 0) == ["menu"] and scene.menu is None                                # Exit to Main Menu: 0x41e + 0x421 (the screen asks for "menu")
    scene.open_menu()
    click(scene, 3)
    click(scene, 1)                                                                          # Exit to Windows: 0x10
    assert sh.name == "quit"


def test_menu_sound_options_opens_over_the_menu_and_returns():
    from engine.shell.events import Key
    sh, *_ = shell_in_town(1)
    sh.fs = None                                                                             # the menu texts fall back to the built-in labels
    scene = sh.current
    scene.open_menu()
    _click(sh, scene.menu.rects()[2])
    assert scene.options is not None
    sh.handle(Key("return"))                                                                 # Enter = Ok of the sound page
    assert scene.options is None and scene.menu is not None


# -- the NPC voice lines ---------------------------------------------------------------------------------------------------------------------

TEXT = ("#plagatguard\r\n<npc=97, part=1>\r\nNo.\r\n#kaargwoman40\r\n<npc=90, iammale, iamfighter, part=1>\r\nA\r\n<npc=99, part=2>\r\nB\r\n"
        "<npc=90, iamfemale, iammage, part=1>\r\nC\r\n<npc=21, part=3>\r\nD\r\n#druidinnkeeper100\r\n<npc=94, part=1>\r\nE\r\n")


def test_town_voice_name_rule():
    """`FUN_004dc84c`, town branch (CONFIRMED): `speech/town/NNNNLCCCpPP.wav`, L = `t` unless the tag has an iam* condition or npc == 21, C = the key's trailing digits padded to 3."""
    assert TS.town_voice(TEXT, "plagatguard", 0) == "speech/town/0097t000p01.wav"
    assert TS.town_voice(TEXT, "kaargwoman40", 0) == "speech/town/0090f040p01.wav"                    # male fighter
    assert TS.town_voice(TEXT, "kaargwoman40", 4 | 2) == "speech/town/0090s040p01.wav"                # female mage
    assert TS.town_voice(TEXT, "kaargwoman40", 0, 2) == "speech/town/0099t040p02.wav"                 # a page without iam*: `t`
    assert TS.town_voice(TEXT, "kaargwoman40", 2, 3) == "speech/town/0021m040p03.wav"                 # npc 21 = the hero: the class letter
    assert TS.town_voice(TEXT, "druidinnkeeper100", 6) == "speech/town/0094t100p01.wav"
    assert TS.town_voice(TEXT, "druidinnkeeper100", 6, 2) is None and TS.town_voice(TEXT, "kaargman40", 0) is None
    assert TS.town_voice(TEXT, "plagatguard", 0, exists=lambda p: False) is None                      # played only if the file exists
    assert [TS.voice_letter(f) for f in (0, 2, 4, 6)] == ["f", "m", "a", "s"]


def test_click_keys_have_no_underscore_and_use_the_chapter():
    for town, names in TS.SPEECH.items():
        assert all("_" not in n and n.endswith("%d") for n in names.values())
    assert TS.click(3, 0x1000, lambda n: 60) == ("speech", "druidshopkeeper60") and TS.click(2, 0x800, lambda n: 110) == ("speech", "kaargguard110")


def test_the_shell_plays_the_voice_of_a_click():
    from engine.shell.events import Press
    sh, *_ = shell_in_town(2, chapter=40)
    scene = sh.current
    scene.mask = type("M", (), {"region_at": lambda self, x, y, origin=(0, 0): 4, "point_of": lambda self, r: (1, 1)})()    # the stand-in has no NPC regions: pointer on region 4
    sh.campaign.camp.set(0x308, 0)
    sh.handle(Press(10, 10, 1))                                                               # Kaarg region 4 = kaargwoman, chapter 40, a male fighter
    assert spoken == ["speech/town/0090f040p01.wav"] and sh.name == "town"
    sh.campaign.camp.set(0x30D, 1)
    sh.campaign.camp.set(0x308, 1)                                                            # a female mage
    del spoken[:]
    sh.handle(Press(10, 10, 1))
    assert spoken == []                                                                       # 0090s040p01 is not in the fake file list: silent, not an error


@needs_install
def test_install_every_town_voice_file_is_named_by_the_rule_and_every_rule_name_exists():
    """The rule over the install: every `speech/town` file (95) is produced by a (key, chapter 30..110, hero class, page), and no produced name is missing."""
    from allods2.text import decode_text
    text = decode_text(GFS.read(TS.TOWN_TEXT))
    files = set(GFS.listdir("speech/town"))
    keys = ["plagatguard"] + sorted({fmt % c for names in TS.SPEECH.values() for fmt in names.values() for c in range(30, 120, 10)})
    used, missing = set(), []
    for key in keys:
        for flags in (0, 2, 4, 6):
            for part in range(1, 8):
                p = TS.town_voice(text, key, flags, part)
                if p:
                    name = p.rsplit("/", 1)[1]
                    if name in files:
                        used.add(name)
                    else:
                        missing.append(p)
    assert not missing and used == files


def test_colour_key_is_the_565_zero_word_not_only_exact_black():
    """`+0x38` (CONFIRMED bitmaps.md): R < 8, G < 4, B < 8 is skipped; a slightly lighter pixel stays."""
    pg = pytest.importorskip("pygame")
    import os
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    from engine.backend_pygame.shellkit import Painter
    pg.display.init()
    pg.display.set_mode((8, 8))
    surf = pg.Surface((4, 1))
    for x, c in enumerate(((0, 0, 0), (7, 3, 7), (8, 0, 0), (0, 4, 0))):
        surf.set_at((x, 0), c)
    out = Painter.keyed(type("P", (), {"_frames": {}})(), "k", surf)
    assert [out.get_at((x, 0)).a for x in range(4)] == [0, 0, 255, 255]


# -- the REA round 2 rules -------------------------------------------------------------------------------------------------------------------

def test_a_sound_slot_that_still_plays_is_not_started_again():
    """`0x438570` (CONFIRMED): play only when the buffer is not playing; `restart` is the stop + play of the same slot."""
    st = make(1)
    st.spec.sound_ms["sfx/town/horse1.wav"] = 500
    st.take_sounds()
    st.play("sfx/town/horse1.wav")
    st.now += 100
    st.play("sfx/town/horse1.wav")
    st.play("sfx/town/horse1.wav", restart=True)
    st.now += 500
    st.play("sfx/town/horse1.wav")
    assert [p for p, _ in st.take_sounds()] == ["sfx/town/horse1.wav"] * 3


def test_horse_sound_fires_each_draw_while_the_frame_matches_but_not_while_playing():
    st = make(1)
    st.spec.sound_ms["sfx/town/horse2.wav"] = 41                                       # the install's Horse2 is 41 ms: shorter than a 67 ms step
    st.horse_set, st.horse = 0, 14
    st.take_sounds()
    for _ in range(5):                                                                 # five draws of 16 ms on one frame
        st.now += 16
        st.after_draw()
    assert len(st.take_sounds()) == 2                                                  # t = 16 and t = 64 (the first play ended at 57)


def test_idle_baba_is_drawn_at_frame_zero():
    st = make(1, 3)
    assert st.baba == -1
    assert any(o[0] == "spr" and "baba" in o[1] and o[2] == 0 for o in st.draw_ops())


def test_kaarg_latches_clear_each_other_and_other_regions_or_their_flag():
    st = make(2)
    st.take_sounds()
    for r in (TS.SHOP, TS.INN, TS.SHOP, 8, TS.SHOP):
        st.hover(r)
    assert [p for p, _ in st.take_sounds()] == ["sfx/town_kaarg/kenter2.wav", "sfx/town_kaarg/kenter1.wav", "sfx/town_kaarg/kenter2.wav", "sfx/town_kaarg/kenter2.wav"]
    st.hover(4)
    st.hover(0x10)
    assert st.flags & 0x10 and st.latch == set()


@needs_install
def test_install_measures_the_scene_sound_lengths():
    spec = TS.SceneSpec.for_town(1).measure(GFS)
    assert 30 <= spec.sound_ms["sfx/town/horse2.wav"] <= 60 and spec.sound_ms["sfx/town/shop/enter.wav"] > 500
    druid = TS.SceneSpec.for_town(3).measure(GFS).sound_ms
    assert "sfx/town_druid/dforest1.wav" in druid and "sfx/town_druid/ddruid1.wav" not in druid       # the install has no Ddruid1/2 and no Dlizard1..4: those slots stay empty (silent)


# -- the stops of the slots (REA round 3: every `0x4385b0` / `0x438480` call of the three scenes) ------------------------------------------------

STOP = TS.STOP


def events(st):
    return st.take_events()


def test_human_shop_enter_stops_school_point_then_plays_shop_enter():
    """`0x4cdbea` (CONFIRMED): entering the shop (latch `+0xac` clear): stop `+0x98` (School\\Point), play `+0x94` (Shop\\enter); once per entry."""
    st = make(1)
    events(st)
    st.hover(TS.SHOP)
    ev = [e for e in events(st)]
    assert ev == [(TS.SCHOOL_POINT, STOP), (TS.SHOP_ENTER, False)]
    st.hover(TS.SHOP)
    assert events(st) == []
    st.hover(-1)                                                                           # leaving the pointer off every region re-arms it
    st.hover(TS.SHOP)
    assert events(st) == [(TS.SCHOOL_POINT, STOP), (TS.SHOP_ENTER, False)]


def test_human_tavern_door_stops_the_shop_enter_and_school_point_sounds_at_frame_zero():
    """`0x4ccfbf` (CONFIRMED): at the tavern counter 0 stop `+0x94` and `+0x98`, then play `+0x90` (Point.wav); not on the later frames."""
    st = make(1)
    st.hover(TS.SHOP)
    events(st)
    st.flags |= 2
    st.guard_dir = 0                                                                       # keep the guards' own sounds out of the list
    st.tick()
    assert events(st) == [(TS.SHOP_ENTER, STOP), (TS.SCHOOL_POINT, STOP), ("sfx/town/point.wav", False)]
    st.tick()
    assert events(st) == []


def test_human_gate_reload_cuts_the_other_gate_file():
    """`0x4cd0ea` (CONFIRMED): GateUp / GateDn share slot `+0x78`; the reload (`FUN_004384f0`) frees the old buffer first, the new one always plays."""
    st = make(1, v301=1)
    st.guard_dir = 0
    events(st)
    st.region = TS.LEAVE
    st.tick()
    assert events(st) == [("sfx/town/gateup.wav", False)]
    st.region = -1
    st.tick()
    assert events(st) == [("sfx/town/gateup.wav", STOP), ("sfx/town/gatedn.wav", False)]


def test_kaarg_gate_reload_cuts_the_other_door_file():
    """`0x4d2c2c` (CONFIRMED): Kdoor1 / Kdoor2 share slot `+0x78`, same reload."""
    st = make(2)
    events(st)
    st.region = TS.LEAVE
    st.tick()
    st.region = -1
    st.tick()
    assert events(st) == [("sfx/town_kaarg/kdoor1.wav", False), ("sfx/town_kaarg/kdoor1.wav", STOP), ("sfx/town_kaarg/kdoor2.wav", False)]


def test_human_guards_free_their_slot_at_the_clamp():
    """`0x4cce81` (CONFIRMED): after the frame update a frame < 0 or >= n frees `+0x7c` (stop + free): the first step (idle frame n-1, dir +1) plays Guard2 and cuts it at once;
    hovering the gate with `Var(0x301) == 0` (dir -1) plays Guard1 and the guard sound is cut when the frame reaches 0."""
    st = make(1, v301=0)
    n = st.guard_f + 1
    events(st)
    st.guard_dir = 1
    st._guards()
    assert events(st) == [("sfx/town/guard2.wav", False), ("sfx/town/guard2.wav", STOP)]
    st._guards()                                                                           # dir is 1 again only after the hover; here 0: nothing
    st.guard_dir = -1
    for _ in range(n - 1):
        st._guards()
    assert events(st) == [("sfx/town/guard1.wav", False)] and st.guard_f == 0
    st._guards()                                                                           # frame -1: clamp, release
    assert events(st) == [("sfx/town/guard1.wav", STOP)] and st.guard_dir == 0
    st._guards()
    assert events(st) == []                                                                # an empty slot: no stop


def test_druid_enter_sounds_stop_the_others():
    """`0x4cfd58` (CONFIRMED): shop entry stops Denter1 (`+0x254`) and Dout (`+0x258`) then plays Denter2; inn entry stops Denter2 / Dout, plays Denter1; the way out stops both
    Denters, plays Dout; each once per latch."""
    st = make(3)
    events(st)
    st.hover(TS.SHOP)
    ev = events(st)
    assert ev[-3:] == [("sfx/town_druid/denter1.wav", STOP), ("sfx/town_druid/dout.wav", STOP), ("sfx/town_druid/denter2.wav", False)]
    st.hover(-1)
    st.hover(TS.INN)
    ev = events(st)
    assert ev[-3:] == [("sfx/town_druid/denter2.wav", STOP), ("sfx/town_druid/dout.wav", STOP), ("sfx/town_druid/denter1.wav", False)]
    st.hover(8)
    assert events(st) == [("sfx/town_druid/denter2.wav", STOP), ("sfx/town_druid/denter1.wav", STOP), ("sfx/town_druid/dout.wav", False)]
    st.hover(8)
    assert events(st) == []


def test_druid_figure_sounds_restart_with_a_stop_first():
    """`0x4cfd58` / `0x4d00de` (CONFIRMED): the figure's Ddruid1 / Ddruid2 is `stop` then `play` of the same slot (the starter and the hover variant)."""
    st = make(3)
    events(st)
    st.hover(TS.SHOP)
    ev = events(st)
    assert ev[:2] == [("sfx/town_druid/ddruid1.wav", STOP), ("sfx/town_druid/ddruid1.wav", False)]
    st.v[TS.INN] = -1
    st.now = st.stamp[TS.INN] + st.delay[TS.INN] + 1
    st.starters()
    ev = events(st)
    assert [("sfx/town_druid/ddruid2.wav", STOP), ("sfx/town_druid/ddruid2.wav", False)] == [e for e in ev if "ddruid2" in e[0]]


def test_kaarg_enter_sounds_stop_each_other_and_the_gate_stops_both():
    """`0x4d244e` (CONFIRMED): shop entry stops Kenter1 (`+0x230`) then plays Kenter2 (`+0x22c`); inn entry stops Kenter2, plays Kenter1; the gate region (once, latch `+0x254`)
    stops both and plays nothing."""
    st = make(2)
    events(st)
    st.hover(TS.SHOP)
    assert events(st) == [("sfx/town_kaarg/kenter1.wav", STOP), ("sfx/town_kaarg/kenter2.wav", False)]
    st.hover(TS.INN)
    assert events(st) == [("sfx/town_kaarg/kenter2.wav", STOP), ("sfx/town_kaarg/kenter1.wav", False)]
    st.hover(8)
    assert events(st) == [("sfx/town_kaarg/kenter2.wav", STOP), ("sfx/town_kaarg/kenter1.wav", STOP)]
    st.hover(8)
    assert events(st) == []


def test_take_sounds_leaves_the_stops_out():
    st = make(2)
    st.take_sounds()
    st.hover(TS.SHOP)
    assert [p for p, _ in st.take_sounds()] == ["sfx/town_kaarg/kenter2.wav"]


def test_a_stop_event_reaches_the_shell_service():
    """`engine/shell/town.py` hands a stop event to `Services.stop` (the backend cuts the sound), a play to `Services.sound`."""
    from engine.shell import Services, Shell
    stopped, played = [], []
    sh = Shell(None, services=Services(stop=stopped.append, sound=played.append))
    sh.stop("sfx/town/shop/enter.wav")
    sh.play("sfx/town/point.wav")
    assert stopped == ["sfx/town/shop/enter.wav"] and played == ["sfx/town/point.wav"]


# -- the close hook (REA round 4: `0x4caaed` = vtable +0x84 -> release-all +0x8c) ------------------------------------------------------------------

def test_release_all_stops_every_started_path_once_and_forgets_them():
    """`0x4caaed` (CONFIRMED): the close calls the release-all, which stops and frees every slot, the looped entry sound and the one-shots alike."""
    for town in (1, 2, 3):
        st = make(town)
        run(st, 6000, hover=TS.SHOP)
        st.take_events()
        started = list(st.heard)
        assert st.spec.entry_loop in started
        st.release_all()
        assert events(st) == [(p, STOP) for p in started]
        st.release_all()
        assert events(st) == [] and st.heard == [] and st.slot == {}


def test_release_all_includes_the_slot_files_chosen_at_play_time():
    st = make(1)
    st.take_events()
    st.reload("gate", "gateup.wav")
    st.release_all()
    ev = events(st)
    assert ("sfx/town/gateup.wav", STOP) in ev and (st.spec.entry_loop, STOP) in ev


def test_leaving_the_scene_through_the_shell_releases_the_slots():
    """The scene screen's `exit` runs the close hook: the stops reach `Services.stop`."""
    from engine.shell import Services, Shell
    from engine.shell.town import TownScene
    stopped, loops = [], []
    sh = Shell(None, services=Services(stop=stopped.append, loop=loops.append))
    sc = TownScene(sh)
    sc.state = make(3)
    sc.state.take_events()
    sc.state.play("sfx/town_druid/denter1.wav")
    sc.exit()
    assert "sfx/town_druid/denter1.wav" in stopped and sc.state.spec.entry_loop in stopped and loops[-1] is None
