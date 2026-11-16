"""L7 (docs/engine/town-inn.md, town-hero.md): the Inn window's pure model (word lookup, the four handlers, the chapter-keyed texts, the hero arrows, the ambient scheduler,
the dialogue pages and voices), the equivalence with `CampaignGame.visit_towns`, and the screen driven by clicks.  The synthetic tests need no install; the install tests
(every person's sprite exists, a render of each inn to out/) skip without one."""

import random
import sys
from pathlib import Path

import numpy as np
import pytest

from engine import inn as I
from engine.campaign import CampaignGame
from engine.sim import campaign as C
from engine.ui import story
from helpers import GFS

needs_install = pytest.mark.skipif(GFS is None or not GFS.exists("graphics/interface/inn/centerarea.bmp"), reason="no install")
OUT = Path(__file__).resolve().parents[1] / "out"


def game(town=2, chapter=60, marks=None):
    """A campaign without an install, in `chapter` at `town`; `marks` = {mercenary number: (mark, town)}."""
    g = CampaignGame()
    g.new_game(visit=False)
    camp = g.camp
    camp.vars[C.CHAPTER] = chapter
    camp.available = [(C.TOWN, town)]
    camp.enter((C.TOWN, town))
    for n, (mark, t) in (marks or {}).items():
        camp.vars[C.MERC_MARK + n - 1] = mark
        camp.vars[C.MERC_TOWN + n - 1] = t
    return g


def inn(g, town=2):
    return I.InnState(g, town, types=None)


# -- geometry -----------------------------------------------------------------------------------------------------------------------------

def test_cell_grid_is_three_rows_of_six_from_the_bottom():
    assert I.cell_rect(0) == (176, 416, 48, 64)
    assert I.cell_rect(5) == (176 + 5 * 48, 416, 48, 64)
    assert I.cell_rect(6) == (176, 352, 48, 64) and I.cell_rect(17) == (176 + 5 * 48, 288, 48, 64)
    assert I.cell_at(200, 450, 3) == 0 and I.cell_at(200 + 48, 450, 3) == 1 and I.cell_at(200 + 3 * 48, 450, 3) is None


def test_buttons_hit_in_order_and_rects_are_the_exes():
    assert I.BUTTONS == ((484, 44, 140, 46), (484, 91, 140, 46), (484, 138, 140, 46))
    assert [I.button_at(500, y) for y in (44, 89, 90, 91, 136, 137, 138, 183, 184)] == [0, 0, None, 1, 1, None, 2, 2, None]
    assert I.button_at(483, 60) is None


def test_word_lookup_takes_the_first_word_with_the_low_16_bits():
    words = [0x300a0205, 0x10000001, (3 << 28) | (31 << 16) | 0x205]
    assert I.word_index(words, 0x205) == 0 and I.word_index(words, 1) == 1 and I.word_index(words, 9) == -1


# -- the person strip -------------------------------------------------------------------------------------------------------------------

def test_strip_is_mercenaries_then_npcs_and_the_first_is_selected():
    g = game(2, 60, {6: (1, 2), 1: (2, 2)})
    s = inn(g)
    kinds = [p.kind for p in s.persons]
    assert kinds == ["merc", "merc", "npc", "npc"] and s.mercs == 2 and s.sel == 0
    assert [p.a for p in s.persons[:2]] == [1, 6]                    # the word order: k = 0.. ascending
    assert s.persons[2].a == 0x7D6 and s.persons[3].a == 0x83D


def test_empty_inn_selects_nobody_and_buttons_do_nothing():
    g = game(1, 20)
    s = inn(g, 1)
    assert s.count == 0 and s.sel == -1 and s.caption(0) is None
    assert s.hire_button() == [] and s.talk_button() == [] and s.figure_release(0) == []


def test_captions_follow_the_selected_person():
    g = game(2, 60, {6: (1, 2)})
    s = inn(g)
    assert [s.caption(i) for i in range(3)] == [I.MAIN_HIRE, I.MAIN_TALK, I.MAIN_EXIT]
    s.accept()
    assert s.caption(0) == I.MAIN_FIRE and s.taken(0)
    s.select(1)                                                           # an NPC: the Hire caption is empty
    assert s.caption(0) is None and not s.taken(1)


# -- the four handlers ------------------------------------------------------------------------------------------------------------------

def test_accept_sets_bit_31_then_talk_to_then_add_sound_with_the_chapter_key():
    g = game(2, 60, {6: (1, 2)})
    calls = []
    real = g.camp.talk_to
    g.camp.talk_to = lambda w: (calls.append(w), real(w))
    s = inn(g)
    eff = s.hire_button()
    assert [(e.kind, e.value) for e in eff] == [("text", "npc6accept60"), ("talk_to", 0x10000006 | I.TAKEN), ("sound", "add")]
    assert calls == [0x10000006 | I.TAKEN] and g.camp.get(C.MERC_HIRED + 5) == 1 and s.word_of(0)[1] & I.TAKEN
    g.camp.vars[C.CHAPTER] = 70                                            # the text variant is chosen by the chapter, not by the word's B
    s2 = inn(game(2, 70, {6: (1, 2)}))
    assert s2.accept()[0].value == "npc6accept70"


def test_dismiss_clears_bit_31_and_toggles_again_with_the_noadd_sound_and_no_text():
    g = game(2, 60, {6: (1, 2)})
    s = inn(g)
    s.hire_button()
    eff = s.hire_button()
    assert [(e.kind, e.value) for e in eff] == [("talk_to", 0x10000006), ("sound", "noadd")]
    assert g.camp.get(C.MERC_HIRED + 5) == 0 and not s.word_of(0)[1] & I.TAKEN


def test_a_type_2_person_shows_reject_plays_add_and_changes_nothing():
    g = game(2, 60, {1: (2, 2)})
    s = inn(g)
    before = dict(g.camp.vars)
    eff = s.hire_button()
    assert [(e.kind, e.value) for e in eff] == [("text", "npc1reject60"), ("sound", "add")]
    assert g.camp.vars == before and not s.word_of(0)[1] & I.TAKEN
    assert s.hire_button()[0].value == "npc1reject60"                      # again: the same, still bit 31 clear


def test_talk_uses_the_words_own_b_and_calls_talk_to_unmodified_each_click():
    g = game(2, 60)
    s = inn(g)
    npc = next(i for i, p in enumerate(s.persons) if p.a == 0x7D6)
    s.select(npc)
    eff = s.talk_button()
    assert [(e.kind, e.value) for e in eff] == [("text", "npc2006talk61"), ("talk_to", (3 << 28) | (61 << 16) | 0x7D6), ("sound", "talk")]
    assert (C.MISSION, 61) in g.camp.available
    assert len(s.talk_button()) == 3                                       # repeat clicks repeat the call


def test_about_is_the_inline_handler_of_a_mercenary_without_talk_to():
    g = game(2, 60, {6: (1, 2)})
    s = inn(g)
    eff = s.talk_button()
    assert [(e.kind, e.value) for e in eff] == [("text", "npc6about"), ("sound", "talk")]


def test_figure_click_selects_then_acts_like_the_buttons():
    g = game(2, 60, {6: (1, 2)})
    s = inn(g)
    npc = next(i for i, p in enumerate(s.persons) if p.kind == "npc")
    eff = s.figure_release(npc)
    assert s.sel == npc and eff[0].value.startswith("npc") and "talk" in eff[0].value
    eff = s.figure_release(0)
    assert s.sel == 0 and eff[0].value == "npc6accept60"


def test_sound_slots_name_the_files():
    assert I.SLOTS["add"] == "sfx/add.wav" and I.SLOTS["noadd"] == "sfx/noadd.wav" and I.SLOTS["talk"] == "sfx/talk.wav" and I.SLOTS["out"] == "sfx/out.wav"
    assert I.ENTER == {1: "sfx/town/inn/enter.wav", 2: "sfx/town_kaarg/inn/kin1.wav", 3: "sfx/town_druid/inn/din1.wav"}


# -- the hero arrows --------------------------------------------------------------------------------------------------------------------

def test_hero_arrows_wrap_both_ways_and_a_single_hero_stays():
    g = game(2, 60)
    s = inn(g)
    s.heroes = [0x15, 0x16, 0x17]
    assert [s.hero_next() for _ in range(4)] == [1, 2, 0, 1]
    assert [s.hero_prev() for _ in range(3)] == [0, 2, 1]
    s.heroes, s.hero = [0x15], 0
    assert s.hero_next() == 0 and s.hero_prev() == 0


# -- the dialogue (story) window ----------------------------------------------------------------------------------------------------------

TEXT = ("#npc2006talk61\r\n<npc=2006, part=1>\r\nFirst page.\r\n<npc=2006, part=2>\r\nSecond.\r\n"
        "#npc6accept60\r\n<npc=6, iammage, part=1>\r\nMage page\r\n<npc=21, iamfighter, part=1>\r\nFighter page\r\n#npc6about\r\n<npc=6, part=1>\r\nAbout.\r\n")


def test_dialogue_pages_advance_with_ok_and_close_after_the_last():
    d = I.Dialogue(TEXT, "npc2006talk61", 0)
    assert d.text == "First page." and d.wide and d.npc == 2006 and d.n == 1
    assert d.advance() and d.text == "Second." and d.n == 2
    assert not d.advance()


def test_missing_section_shows_nothing_to_say():
    d = I.Dialogue(TEXT, "npc9talk9", 0)
    assert d.text == story.NOTHING_TO_SAY and d.page is None


def test_hero_class_selects_the_page_and_the_voice_letter():
    files = {"speech/accept/0021f060p01.wav", "speech/accept/0006m060p01.wav", "speech/talk/2006t061p01.wav", "speech/talk/2006t061p02.wav", "speech/about/0006t000p01.wav"}
    d = I.Dialogue(TEXT, "npc6accept60", story.hero_flags(False, False), files.__contains__)
    assert d.text == "Fighter page" and d.voice == "speech/accept/0021f060p01.wav"
    d = I.Dialogue(TEXT, "npc6accept60", story.hero_flags(False, True), files.__contains__)
    assert d.text == "Mage page" and d.voice == "speech/accept/0006m060p01.wav"      # an iam tag: the class letter (`m`)
    d = I.Dialogue(TEXT, "npc6accept60", story.hero_flags(False, True), lambda p: False)
    assert d.voice is None                                                  # the exe plays only existing files
    d = I.Dialogue(TEXT, "npc2006talk61", 0, files.__contains__)
    assert d.voice == "speech/talk/2006t061p01.wav" and d.advance() and d.voice == "speech/talk/2006t061p02.wav"
    assert I.Dialogue(TEXT, "npc6about", 0, files.__contains__).voice == "speech/about/0006t000p01.wav"


def test_voice_folder_by_key():
    assert [I.voice_folder(k) for k in ("npc1talk3", "npc1accept4", "npc1reject4", "npc1about", "kaargwoman30", "druidinnkeeper100", "plagatguard", "event1")] == \
        ["talk", "accept", "reject", "about", "town", "town", "town", None]


# -- the ambient scheduler --------------------------------------------------------------------------------------------------------------

class Rng:
    def __init__(self, *vals):
        self.vals = list(vals)

    def randrange(self, n):
        return self.vals.pop(0) % n if self.vals else 0


def run(a, ms, dt=40):
    out = []
    for _ in range(ms // dt):
        a.advance(dt)
        out += a.take_events()
    return out


def test_human_steam_comes_after_ten_seconds_and_the_loop_is_water():
    a = I.Ambient(1, Rng(16 * 100), {})
    assert a.loop == "sfx/town/inn/water.wav"
    assert I.Ambient(3, random.Random(1)).loop == I.DRUID_LOOP == "sfx/town_druid/inn/dforest2.wav"          # `FUN_004a0ff0(+0x15c)` at the end of the load
    assert I.Ambient(2, random.Random(1)).loop == I.KAARG_LOOP == "sfx/town_kaarg/inn/kvox5.wav"            # `+0x158`
    assert "sfx/town/inn/steam.wav" not in run(a, 9960)
    assert run(a, 120).count("sfx/town/inn/steam.wav") == 1


def test_idle_event_even_delay_is_the_breath_animation_with_chair_and_breath_sounds():
    a = I.Ambient(1, Rng(16 * 200 + 8), {"breath": 5})                    # D = 3200 + 0 (8 / 16 = 0): even
    assert a.delay == 3200
    ev = run(a, 3400)
    assert ev[:2] == ["sfx/town/inn/chair.wav", "sfx/town/shop/breath.wav"] and a.kind in (0, 2)


def test_idle_event_odd_delay_is_the_drink_animation_forward_then_back_then_glotok():
    a = I.Ambient(1, Rng(16 * 201 + 3, 16 * 300), {"drink": 33})           # D = 3201: odd
    assert a.delay == 3201
    ev = run(a, 3300, 20)
    assert a.kind == 1 and a.tender_ops().startswith("graphics/interface/inn/tender/drink/dr")
    seen = []
    for _ in range(400):
        a.advance(100)
        seen += a.take_events()
        if a.kind == 0:
            break
    assert a.kind == 0 and seen[-1] == "sfx/town/inn/glotok.wav" and "sfx/town/inn/drink.wav" in (ev + seen)
    assert seen.count("sfx/town/inn/drink.wav") + ev.count("sfx/town/inn/drink.wav") == 2       # frame 30 on the way forward and back


def test_candle_and_cauldron_step_every_over_100_ms():
    a = I.Ambient(1, Rng(0), {"candle": 4, "cauldron": 3})
    for _ in range(5):
        a.advance(101)
    assert (a.candle, a.cauldron) == (1, 2)


class Seq:
    """rng whose `randrange(32768)` returns the given raw `rand()` values in order (then 0)."""
    def __init__(self, *vals):
        self.vals = list(vals)

    def randrange(self, n):
        assert n == 32768
        return self.vals.pop(0) if self.vals else 0


def drain(a, ms, dt=10):
    out = []
    for _ in range(ms // dt):
        a.advance(dt)
        out += a.take_events()
    return out


def mk(town, *rands, delay=10 ** 9):
    """An Ambient whose constructor draws are out of the way: the timers far away, then `rng` replays `rands` (raw `rand()` values; 0 after)."""
    a = I.Ambient(town, random.Random(1), {})
    a.delay = delay
    a.voice_delay = a.timer_delay = 10 ** 9
    a.rng = Seq(*rands)
    return a


def test_druid_water_object_steps_every_100_ms_and_plays_a_drop_at_frame_zero():
    a = mk(3, 0)
    a.advance(101)                                              # the first step: frame 0 -> the sound (pick ((0 * 4) // 0x7fff) % 4 = 0), frame 1
    assert a.take_events() == [I.DRUID_DROPS[0]] and a.drop == 1
    ev = drain(a, 909, 101)                                     # nine more steps wrap to 0 without a sound
    assert ev == [] and a.drop == 0
    a.rng = Seq(32767)                                          # ((32767 * 4) // 0x7fff) % 4 == 0: the odd 0x7fff divisor
    a.advance(101)
    assert a.take_events() == [I.DRUID_DROPS[0]]
    a.drop, a.rng = 0, Seq(16000)                               # (16000 * 4) // 32767 = 1
    a.drop_at = -1000
    a.advance(1)
    assert a.take_events() == [I.DRUID_DROPS[1]]
    assert a.objects()[0] == ("graphics/interface/inn_druid/waterdrop/d0002.bmp", 0xA8, 0x90)


def test_druid_event_kinds_sounds_frames_and_delays():
    a = mk(3, delay=3200)                                       # D & 3 = 0 -> state 1
    a.advance(3201)
    assert a.state == 1 and a.take_events()[-1:] == [I.DRUID_EVENTS[1]]           # Ddruid4 at the start
    assert a.objects()[-1] == ("graphics/interface/inn_druid/taverner/a10002.bmp", 0x28, 0x80)       # frame 0 is drawn, then the same draw steps (the stamp is old)
    seen = []
    for _ in range(60):
        a.advance(101)
        seen += a.take_events()
        if a.state == -1:
            break
    assert a.state == -1 and a.obj == 0 and seen.count(I.DRUID_FRAME30) == 1       # Ddruid41 once at frame 30; the object ends at frame 39
    assert a.delay == 3200                                      # rand 0 -> 3200 + 0
    b = mk(3, delay=3201)                                       # state 2: a2 (30 frames), DDruid3
    b.advance(3202)
    assert b.state == 2 and b.take_events()[-1:] == [I.DRUID_EVENTS[2]]
    n, ev = 0, []
    while b.state == 2:
        b.advance(101)
        n += 1
        ev += b.take_events()
    assert n == 29 and I.DRUID_FRAME30 not in ev                # frame 0 -> 1 already in the start draw; 28 steps to frame 29, one more ends it
    c = mk(3, 16 * 7, delay=3203)                               # 3203 & 3 = 3 -> 4 -> 3: the static a30001, no sound
    c.drop_at = 10 ** 9                                         # keep the water sound from taking the rand value
    c.advance(3204)                                             # the start draw already steps (the stamp is old): state 3 -> 4, D = rand / 16 + 1000
    assert c.state == 4 and c.delay == 1000 + 7 and c.take_events() == []
    assert c.objects()[-1] == ("graphics/interface/inn_druid/taverner/a30001.bmp", 0x68, 0x98)      # states 3 and 4 draw the same static picture
    c.advance(50)                                               # < 100 ms since the stamp: the step waits
    assert c.state == 4
    c.advance(60)
    assert c.state == -1 and len(c.objects()) == 1


def test_bird_voices_are_a_second_timer_of_2000_plus_rand_2000_ms():
    a = mk(3, 0)
    a.voice_delay = 2000
    a.drop_at = 10 ** 9                                          # no water sound in the way
    a.advance(2001)
    assert a.take_events() == [I.DRUID_VOICES[1]]                # ((0 * 3) // 0x7fff) % 3 + 1 = 1 -> Dbird4 (+0x160)
    assert a.voice_delay == 2000 and a.voice_at == 2001
    a.rng = Seq(32767, 32767 * 1999 // 2000)
    a.advance(2001)                                              # ((32767 * 3) // 0x7fff) % 3 = 0 -> again voice 1; next delay 2000 + (32767 * 2000 // 0x7fff) % 2000
    assert a.take_events() == [I.DRUID_VOICES[1]] and 2000 <= a.voice_delay < 4000


def test_kaarg_has_no_idle_pause_and_picks_its_state_from_rand_20_plus_1():
    # r = ((rand * 21) >> 15) + 1: 1, 2, 5 -> state r; 3, 4, 6 -> 3; 7..21 -> 4
    got = {}
    for r in range(1, 22):
        a = mk(2, (r - 1) * 32768 // 21 + 1)
        a.advance(1)
        got[r] = a.state
        assert a.take_events() == ([I.KAARG_EVENTS[r]] if r in (1, 2) else [])
    assert [got[r] for r in range(1, 8)] == [1, 2, 3, 3, 5, 3, 4] and {got[r] for r in range(7, 22)} == {4}
    assert I.KAARG_EVENTS == {1: "sfx/town_kaarg/inn/kman3.wav", 2: "sfx/town_kaarg/inn/kman2.wav"}
    a = mk(2, 0)
    a.advance(1)
    assert a.state == 1 and a.objects() == [("graphics/interface/inn_kaarg/taverner/a10001.bmp", 0x48, 0x58)]
    for _ in range(14):
        a.advance(101)
    assert a.state == 1 and a.obj == 14                        # 15 frames: the last is index 14
    a.advance(101)
    assert a.state == -1 and a.obj == 0
    a.advance(1)                                               # the next event starts in the next draw, no pause
    assert a.state in (1, 2, 3, 4, 5)


def test_kaarg_a5_walks_the_frame_table_and_a4_files_are_zero_based():
    assert len(I.KAARG_A5_FRAMES) == 94 and I.KAARG_A5_FRAMES[:6] == (0, 1, 2, 3, 4, 4) and I.KAARG_A5_FRAMES[-1] == 28
    a = mk(2, 4 * 32768 // 21 + 1)
    a.advance(1)
    assert a.state == 5 and a.objects() == [("graphics/interface/inn_kaarg/taverner/a50000.bmp", 0x58, 0x54)]
    a.advance(101)
    assert a.objects()[0][0].endswith("a50001.bmp")
    for _ in range(93):
        a.advance(101)
    assert a.state == -1                                       # index 94 = the table's -1
    a.state, a.obj = 4, 3
    assert a.objects() == [("graphics/interface/inn_kaarg/taverner/a40003.bmp", 0xC8, 0x88)]
    a.state, a.obj = 3, 2
    assert a.objects() == [("graphics/interface/inn_kaarg/taverner/a30003.bmp", 0x70, 0x70)]


def test_kaarg_drop_and_voice_timers_are_independent():
    a = mk(2, 0, 0)
    a.voice_delay = a.timer_delay = 2000
    a.state, a.step_at = 1, 10 ** 9                             # an event runs and never steps in this test
    ev = drain(a, 2100, 50)
    assert sum(p in I.KAARG_DROPS for p in ev) == 1 and sum(p in I.KAARG_VOICES.values() for p in ev) == 1


# -- the equivalence with visit_towns -----------------------------------------------------------------------------------------------------

POLICIES = {"none": lambda words, camp: (), "all": lambda words, camp: [w & 0xFFFF for w in words]}
STATES = [(10, 1), (30, 2), (40, 3), (50, 2), (60, 2), (60, 3), (70, 2), (70, 3), (80, 2), (90, 2), (90, 3), (100, 2), (100, 3), (110, 2)]


def marked(chapter, town, mark_of):
    marks = {n: (mark_of(n), 2 if n % 2 else 3) for n in range(1, 8)}
    if chapter == 60:
        marks[6] = (1, town)
    marks[3] = (1, town)
    marks[1] = (2, town)
    marks[7] = (1, town)
    return game(town, chapter, marks)


def click_everyone(g, town, policy):
    """The scripted player: talk to every NPC (the order of the strip), then press Hire on the mercenaries the policy picks, all through the figure clicks."""
    s = inn(g, town)
    for i in range(s.mercs, s.count):
        s.figure_release(i)
    offers = [w for w in s.words if I.word_type(w) in (1, 2)]
    for n in policy(offers, g.camp):
        for i in range(s.mercs):
            if s.persons[i].a == n:
                s.figure_release(i)
    return s


@pytest.mark.parametrize("policy", sorted(POLICIES))
@pytest.mark.parametrize("chapter,town", STATES)
def test_a_scripted_click_sequence_equals_visit_towns(chapter, town, policy):
    a, b = marked(chapter, town, lambda n: 1), marked(chapter, town, lambda n: 1)
    a.hire = POLICIES[policy]
    log_a, log_b = [], []
    for g, log in ((a, log_a), (b, log_b)):
        real = g.camp.talk_to
        g.camp.talk_to = (lambda real, log: lambda w: (log.append(w), real(w)))(real, log)
    a.visit_towns()
    click_everyone(b, town, POLICIES[policy])
    b.camp.leave()
    assert [w & 0x7FFFFFFF for w in log_a] == [w & 0x7FFFFFFF for w in log_b]      # the bit 31 of the window's own copy is the only difference (TalkTo ignores it)
    assert a.camp.vars == b.camp.vars and a.camp.available == b.camp.available
    assert [(e.number, e.server_id) for e in a.roster] == [(e.number, e.server_id) for e in b.roster]


# -- the screen -------------------------------------------------------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent))


def shell_in_inn(town=2, chapter=60, marks=None, fs=None):
    from engine.shell import Services, Shell
    from engine import town as T
    rec = {"sounds": [], "speech": [], "loops": [], "music": [], "log": []}
    sh = Shell(fs, services=Services(sound=rec["sounds"].append, speech=rec["speech"].append, loop=rec["loops"].append, music=rec["music"].append, log=rec["log"].append))
    sh.rng = random.Random(2)
    sh.campaign = game(town, chapter, marks)
    core = sh.town_core()
    core.send(T.MSG_ENTER)
    core.send(T.MSG_INN)
    sh.start("inn")
    return sh, rec


def click(sh, pos):
    from engine.shell.events import Move, Press, Release
    for ev in (Move(*pos), Press(*pos), Release(*pos)):
        sh.handle(ev)


def test_entering_plays_the_enter_sound_and_starts_the_ambient_loop_and_leaving_stops_it():
    sh, rec = shell_in_inn(1, 10)
    assert rec["sounds"] == ["sfx/town/inn/enter.wav"] and rec["loops"] == ["sfx/town/inn/water.wav"]
    click(sh, sh.current.point_of("button", 2))
    assert sh.name == "town" and None in rec["loops"] and rec["loops"].index(None) > 0          # the inn stops its loop; the scene starts its own
    assert rec["sounds"][1] == "sfx/out.wav"                             # the press plays Out.wav at once
    assert sh.town_core().view == "scene" and sh.town_core().mask == 0


def test_exit_by_escape_and_by_the_button_go_back_through_the_core():
    from engine.shell.events import Key
    for how in ("esc", "button"):
        sh, rec = shell_in_inn(2, 60)
        if how == "esc":
            sh.handle(Key("escape"))
        else:
            click(sh, sh.current.point_of("button", 2))
        assert sh.name == "town" and sh.town_core().mask == 0, how


def test_hire_button_hires_and_the_caption_flips_the_label_and_dismiss_undoes_it():
    sh, rec = shell_in_inn(2, 60, {6: (1, 2)})
    cur = sh.current
    click(sh, cur.point_of("button", 0))
    assert cur.dialogue is not None and cur.dialogue.key == "npc6accept60"
    assert "sfx/add.wav" in rec["sounds"] and sh.campaign.camp.get(C.MERC_HIRED + 5) == 1
    from engine.shell.events import Key
    sh.handle(Key("return"))                                             # Ok: no page 2 here (no install text): the window closes
    sh.handle(Key("return")) if cur.dialogue is not None else None
    assert cur.dialogue is None and cur.state.taken(0)
    click(sh, cur.point_of("button", 0))                                 # now Fire
    assert "sfx/noadd.wav" in rec["sounds"] and sh.campaign.camp.get(C.MERC_HIRED + 5) == 0 and cur.dialogue is None


def test_the_dialogue_is_modal_and_escape_closes_the_whole_window():
    from engine.shell.events import Key
    sh, rec = shell_in_inn(2, 60, {6: (1, 2)})
    cur = sh.current
    click(sh, cur.point_of("button", 0))
    assert cur.dialogue is not None
    click(sh, cur.point_of("button", 2))                                 # a click under the dialogue reaches nothing
    assert sh.name == "inn" and rec["sounds"].count("sfx/out.wav") == 0
    sh.handle(Key("escape"))
    assert cur.dialogue is None and sh.name == "inn"


def test_figure_click_in_the_screen_selects_and_acts_and_the_arrows_change_the_hero():
    sh, rec = shell_in_inn(2, 60, {6: (1, 2)})
    cur = sh.current
    npc = next(i for i, p in enumerate(cur.state.persons) if p.kind == "npc")
    click(sh, cur.point_of("figure", npc))
    assert cur.state.sel == npc and cur.dialogue is not None and "talk" in cur.dialogue.key
    assert rec["sounds"][-1] == "sfx/talk.wav"
    cur.dialogue = None
    cur.state.heroes = [0x15, 0x16]
    click(sh, cur.point_of("arrow", 1))
    assert cur.state.hero == 1
    click(sh, cur.point_of("arrow", 1))
    assert cur.state.hero == 0
    click(sh, cur.point_of("arrow", 0))
    assert cur.state.hero == 1


def test_a_release_away_from_the_pressed_button_does_nothing():
    sh, rec = shell_in_inn(2, 60, {6: (1, 2)})
    cur = sh.current
    from engine.shell.events import Move, Press, Release
    x, y = cur.point_of("button", 0)
    for ev in (Move(x, y), Press(x, y), Release(*cur.point_of("button", 1))):
        sh.handle(ev)
    assert cur.dialogue is None and sh.campaign.camp.get(C.MERC_HIRED + 5) == 0


def test_the_scene_draws_every_panel_and_the_hired_label():
    sh, rec = shell_in_inn(2, 60, {6: (1, 2)})
    cur = sh.current
    paths = [getattr(op, "path", None) for op in cur.scene().ops]
    for need in ("leftstats.bmp", "leftpicture.bmp", "buttonsarea.bmp", "manback.bmp", "tavernmain.bmp", "HumanBackR.bmp", "ar1.bmp", "ar2.bmp", "luover.bmp", "ldover.bmp", "ruover.bmp", "HumanBackL.bmp"):
        assert any(p and p.lower().endswith(need.lower()) for p in paths), need
    cur.state.accept()
    assert any(type(op).__name__ == "Text" and op.table == "red" for op in cur.scene().ops)           # the HIRED label (font table 0x620ea0) over the taken mercenary


def test_without_a_person_the_sheet_shows_the_two_lines():
    sh, rec = shell_in_inn(1, 20)
    ops = sh.current.scene().ops
    assert sh.current.state.count == 0 and not any(getattr(o, "path", "").endswith("manback.bmp") for o in ops)


# -- the install ----------------------------------------------------------------------------------------------------------------------------

@needs_install
def test_every_person_of_every_inn_has_a_sprite_and_a_template():
    from allods2.assets import AssetCache
    from allods2.common import INSTALL
    types = AssetCache(INSTALL).unit_stats()
    seen = set()
    for chapter in range(10, 120, 10):
        for town in (1, 2, 3):
            marks = {n: (1 + n % 2, town) for n in range(1, 8)}
            g = game(town, chapter, marks)
            g.camp.vars.update({0x306: 1, 0x302: 1, 0x303: 1})
            g.camp.vars[C.MISSION_DONE_BASE + 53] = 1
            s = I.InnState(g, town, types=types)
            for p in s.persons:
                seen.add(p.sprite)
                assert GFS.exists(p.sprite), (chapter, town, p)
                assert p.template is not None, (chapter, town, p)
    assert len(seen) >= 10


@needs_install
@pytest.mark.parametrize("town", [1, 2, 3])
def test_render_each_inn_and_play_the_dialogue_with_the_real_text(town):
    pytest.importorskip("pygame")
    from allods2.common import as_fs
    from engine.backend_pygame.shell import scene_screenshot
    from engine.backend_pygame.shellkit import Painter
    from PIL import Image
    fs = as_fs(GFS)
    marks = {n: (1 + n % 2, town) for n in range(1, 8)}
    sh, rec = shell_in_inn(town, 60 if town != 1 else 10, marks, fs=fs)
    cur = sh.current
    assert cur.state.count >= 1
    for _ in range(40):
        sh.update(100)
    npc = next((i for i, p in enumerate(cur.state.persons) if p.kind == "npc"), None)
    if npc is not None:
        click(sh, cur.point_of("figure", npc))
        d = cur.dialogue
        assert d is not None and d.text != story.NOTHING_TO_SAY, d.key
    OUT.mkdir(exist_ok=True)
    painter = Painter(GFS)
    px = scene_screenshot(cur.scene(), (640, 480), painter)
    assert px.shape == (480, 640, 3) and px[300, 300].any()
    Image.fromarray(np.asarray(px, np.uint8)).save(OUT / ("inn_%d.png" % town))
    cur.dialogue = None
    click(sh, cur.point_of("figure", 0))
    px = scene_screenshot(cur.scene(), (640, 480), painter)
    Image.fromarray(np.asarray(px, np.uint8)).save(OUT / ("inn_%d_sel.png" % town))
    cur.info_text = True                            # the info panel's text mode: the hero's rows (name, attributes, Sight, Weight ...)
    ops = cur.scene().ops
    assert any(getattr(o, "text", "") == "Sight" for o in ops)
    px = scene_screenshot(cur.scene(), (640, 480), painter)
    Image.fromarray(np.asarray(px, np.uint8)).save(OUT / ("inn_%d_text.png" % town))


def test_shell_draws_the_druid_and_kaarg_objects_and_the_figure_release_does_not_need_its_press():
    from engine.shell.events import Move, Press, Release
    sh, rec = shell_in_inn(3, 40)
    cur = sh.current
    paths = [getattr(op, "path", "") for op in cur.scene().ops]
    assert any(p.endswith("inn_druid/waterdrop/d0001.bmp") for p in paths)
    assert rec["loops"] == ["sfx/town_druid/inn/dforest2.wav"]
    sh2, rec2 = shell_in_inn(2, 60, {6: (1, 2)})
    cur2 = sh2.current
    cur2.ambient.state, cur2.ambient.obj = 4, 2
    assert any(getattr(op, "path", "").endswith("inn_kaarg/taverner/a40002.bmp") for op in cur2.scene().ops)
    assert rec2["loops"] == ["sfx/town_kaarg/inn/kvox5.wav"]
    # `0x49a197`: the release re-runs the hit test at its own point; a press on empty space (or another figure) before it does not matter
    npc = next(i for i, p in enumerate(cur2.state.persons) if p.kind == "npc")
    other = next(i for i, p in enumerate(cur2.state.persons) if i != npc)
    x, y = cur2.point_of("figure", other)
    sh2.handle(Move(x, y))
    sh2.handle(Press(x, y))
    sh2.handle(Release(*cur2.point_of("figure", npc)))
    assert cur2.state.sel == npc and cur2.dialogue is not None


# -- the NPC story window over the town scene --------------------------------------------------------------------------------------------

@needs_install
def test_scene_npc_click_opens_a_modal_story_window_with_ok_pages():
    from allods2.common import as_fs
    from engine.shell.events import Key
    sh, rec = shell_in_inn(2, 60, fs=as_fs(GFS))
    sh.current.exit()
    sh.start("town")
    scene = sh.current
    click(sh, scene.point_of(4))                         # the Kaarg woman: `FUN_0041d15e("kaargwoman<Var 0x300>")`
    w = scene.story
    assert w is not None and w.dialogue.key.startswith("kaargwoman") and w.dialogue.text
    ops = scene.scene().ops
    assert any(type(o).__name__ == "Button" for o in ops)
    first = w.dialogue.n
    sh.handle(Key("return"))                             # Ok: the next page, or the window closes
    assert scene.story is None or scene.story.dialogue.n == first + 1
    if scene.story is not None:
        sh.handle(Key("escape"))                         # ESC closes the window, not the scene
        assert scene.story is None and scene.menu is None


@needs_install
def test_left_sheet_shows_every_detail7_row_for_every_person_world_free():
    """Town-inn 6: the owner is player 0 -> detail 7: Sight / Speed / Dmg / Attack / Absorb / Defence / resistances / skills (and Weight / XP only for a hero unit)."""
    from allods2.assets import AssetCache
    from allods2.common import INSTALL
    from engine.ui.orders import MainText
    assets = AssetCache(INSTALL)
    types = assets.unit_stats()
    main = MainText.load(GFS, "main/text/main.txt")
    names = MainText.load(GFS, "main/text/unitname.txt")
    items, spells = assets.items(), assets.spells()
    seen = 0
    for chapter in (10, 60, 110):
        for town in (1, 2, 3):
            g = game(town, chapter, {n: (1 + n % 2, town) for n in range(1, 8)})
            g.camp.vars.update({0x306: 1, 0x302: 1, 0x303: 1})
            for p in I.InnState(g, town, types=types).persons:
                rows = I.person_rows(p, main, names, items, spells)
                ys = {(r[1], r[2]) for r in rows}
                assert (6, 0x7A) in ys and (0x4A, 0x7A) in ys, (chapter, town, p)       # skills and resistances (detail > 5)
                assert (0x28, 200) in ys and (0x28, 0xD2) in ys                           # Sight, Speed
                assert (0x4A, 0x58) in ys and (0x4A, 0x62) in ys                          # Absorb, Defence
                assert (6, 0x2C) in ys and (0x73, 0x2C) in ys                             # attributes, Health
                assert ((0x48, 0x12) in ys) == (p.kind == "merc"), (chapter, town, p.kind, p.a, p.template.kind, p.template.name)
                seen += 1
    assert seen > 20


def test_info_panel_mode_button_toggles_text_mode_with_the_click_sound():
    from engine.shell.events import Move, Press, Release
    sh, rec = shell_in_inn(2, 60)
    scr = sh.current
    assert scr.info_text is False
    x, y, w, h = I.MODE_BUTTON
    ox, oy = scr.origin
    for ev in (Move(ox + x + 5, oy + y + 5), Press(ox + x + 5, oy + y + 5, 1), Release(ox + x + 5, oy + y + 5, 1)):
        scr.event(ev)
    assert scr.info_text is True
    scr.scene()                                     # draws without an install too
    for ev in (Press(ox + x + 5, oy + y + 5, 1), Release(ox + x + 5, oy + y + 5, 1)):
        scr.event(ev)
    assert scr.info_text is False


@needs_install
def test_hero_text_rows_show_name_and_every_stat_row():
    from allods2.assets import AssetCache
    from allods2.common import INSTALL
    from engine.ui.orders import MainText
    assets = AssetCache(INSTALL)
    g = game(2, 60)
    rows = I.hero_rows(assets, g.roster[0], MainText.load(GFS, "main/text/main.txt"), MainText.load(GFS, "main/text/unitname.txt"))
    ys = {(r[1], r[2]) for r in rows}
    assert (0x48, 0x12) in ys and (6, 0x2C) in ys and (0x28, 200) in ys and (0x10, 0xAE) in ys      # name, attributes, Sight, Weight (the hero rows)
