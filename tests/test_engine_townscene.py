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
    assert d.press(0x200) == ("speech", "druidinnkeeper_40") and d.press(0x1000) == ("speech", "druidshopkeeper_40") and d.press(4) is None and d.press(0x400) is None
    assert k.press(4) == ("speech", "kaargwoman_70") and k.press(0x200) == ("speech", "kaargwoman_70")
    assert k.press(0x400) == ("speech", "kaargman_70") and k.press(0x800) == ("speech", "kaargguard_70") and k.press(0x1000) is None


def test_vars_argument_overrides():
    assert make(2).press(0x800, vars=lambda n: 99) == ("speech", "kaargguard_99")


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
    assert st.guard_f == n - 1
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
    assert st.man_v == 2 and st.flags & 1
    snd = [p for p, _ in st.take_sounds()]
    assert snd == ["sfx/town_druid/ddruid1.wav", "sfx/town_druid/denter2.wav"]
    st.hover(TS.SHOP)
    assert st.take_sounds() == []
    st.hover(-1)
    st.hover(TS.INN)
    assert st.wom_v == 2 and [p for p, _ in st.take_sounds()] == ["sfx/town_druid/ddruid2.wav", "sfx/town_druid/denter1.wav"]
    st.hover(8)
    assert [p for p, _ in st.take_sounds()] == ["sfx/town_druid/dout.wav"]
    st.hover(0x1000)
    assert st.take_sounds() == []


def test_druid_hover_variant_runs_to_its_end_and_does_not_restart_while_hovered():
    st = make(3)
    run(st, 3000, hover=TS.SHOP)
    assert st.man_v == -1 and not st.flags & 1                                               # a3 has 20 frames at 100 ms
    ops = st.draw_ops()
    assert ("bmp", "graphics/interface/town_druid/man/a30001.bmp", 0x154, 0xe0, False) in ops and st.region == TS.SHOP


def test_druid_ambient_variant_is_rand2_unless_over_the_region():
    variants = set()
    for seed in range(40):
        st = make(3, seed)
        st.man_delay = 100
        st.advance(200)
        variants.add(st.man_v)
        assert st.man_v in (0, 1)
    assert variants == {0, 1}
    st = make(3)
    st.man_delay, st.region = 100, TS.SHOP                                                    # pointer on the region without a hover call: the starter reads `+0xb4`
    st.advance(200)
    assert st.man_v in (2,) or st.man_v == -1


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


def test_druid_bug_every_ten_to_twenty_seconds():
    st = make(3, 3)
    d = st.bug_delay
    assert 10000 <= d < 20000
    t = 0
    while st.bug_v == -1:
        st.advance(100)
        t += 100
    assert d < t <= d + 100 and 0 <= st.bug_v < 3 and st.flags & 0x80
    f0 = st.draw_ops()
    assert any(o[0] == "spr" and "bug" in o[1] and o[2] == st.bug_v * 61 for o in f0)
    for _ in range(61):
        st.advance(101)
    assert st.bug_v == -1


def test_druid_ambient_first_draw_and_globals():
    glob = TS.Globals()
    st = make(3, 1, glob=glob)
    st.advance(1)
    snd = [p for p, _ in st.take_sounds()]
    assert any("dbird" in p for p in snd) and any("dtree" in p for p in snd) and any("dwolf1" in p for p in snd)
    assert 2000 <= glob.druid_birds < 4000 and 2000 <= glob.druid_trees < 4000


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
    assert any("kbird" in p for p in snd) and "sfx/town_kaarg/kman1.wav" in snd and not any("kvox" in p for p in snd)
    t, n = 1, 0
    while t < 100000:
        st.advance(100)
        t += 100
        n += sum(1 for p, _ in st.take_sounds() if p.endswith("kman1.wav"))
    assert n == 2
    assert any("kvox" in p for p in run(make(2, 2, glob=glob), 6000))


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
    for f in range(1, 40):
        st.f["guard"] = f
        st.after_draw()
        heard += [p for p, _ in st.take_sounds()]
    steps = [p for p in heard if "ksteps" in p]
    assert len(steps) == len([f for f in range(1, 40) if f in (5, 13, 21, 9, 17, 23, 31)])
    assert all(p in ("sfx/town_kaarg/ksteps2.wav", "sfx/town_kaarg/ksteps21.wav", "sfx/town_kaarg/ksteps1.wav", "sfx/town_kaarg/ksteps11.wav", "sfx/town_kaarg/ksteps3.wav",
                     "sfx/town_kaarg/ksteps31.wav") for p in steps)


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

def shell_in_town(town, v301=0, chapter=10):
    from engine.campaign import CampaignGame
    from engine.shell import Services, Shell
    saves, loops, sounds, music = [], [], [], []
    sh = Shell(None, services=Services(autosave=saves.append, music=music.append, loop=loops.append, sound=sounds.append))
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
    return sh, saves, loops, sounds


def test_human_leave_needs_var_0x301_through_the_shell():
    from shell_scenarios import click_region
    sh, saves, loops, sounds = shell_in_town(1, v301=0)
    assert loops == ["sfx/town/crowd.wav"] or loops == []                                  # the stand-in still starts the entry loop of the spec
    click_region(sh, TS.LEAVE)
    assert sh.name == "town" and saves == [] and "speech:plagatguard" in sounds
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
    for k in ("escape", "return"):
        sh.handle(Key(k))
    assert sh.name == "town"
    sh.handle(Press(x, y, 1))
    assert sh.name == "inn"


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
