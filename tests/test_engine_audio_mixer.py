"""K11: the 16-voice mixer model (docs/engine/audio.md 3.1): strict priority stealing, drops, the 16 duplicates, the UI priority."""

from engine.audio.mix import UI_PRIORITY
from engine.audio.mixer import LOOP, VoiceMixer


def fill(m, prio=50, dur=1000, now=0):
    return [m.play(now, "s%d" % i, dur, prio) for i in range(16)]


def test_sixteen_voices_then_equal_priority_is_dropped():
    m = VoiceMixer()
    ps = fill(m)
    assert [p.channel for p in ps] == list(range(16)) and all(p.result == "played" for p in ps)
    p = m.play(0, "new", 1000, 50)
    assert (p.result, p.channel) == ("dropped:voices", -1)             # equal priority never steals
    assert m.play(0, "new", 1000, 40).result == "dropped:voices"


def test_a_higher_priority_steals_the_lowest_first_index():
    m = VoiceMixer()
    for i in range(16):
        m.play(0, "s%d" % i, 1000, 30 + (i % 4))
    p = m.play(0, "x", 1000, 31)                                         # lowest priority 30 sits on channels 0, 4, 8, 12: the first is cut
    assert p.result == "stolen:0" and p.channel == 0 and p.audible
    assert m.snd[0] == "x"
    p = m.play(0, "y", 1000, 31)
    assert p.result == "stolen:4"


def test_strictness_a_voice_of_the_same_priority_survives():
    m = VoiceMixer()
    fill(m, 70)
    assert m.play(0, "x", 1000, 70).result == "dropped:voices"
    assert m.play(0, "x", 1000, 71).result == "stolen:0"


def test_a_finished_voice_is_free_again():
    m = VoiceMixer()
    fill(m, 50, dur=100)
    assert m.play(99, "late", 10, 10).result == "dropped:voices"
    p = m.play(100, "late", 10, 10)
    assert p.result == "played" and p.channel == 0


def test_the_17th_copy_of_one_sound_is_dropped_busy():
    m = VoiceMixer(voices=32)
    for _ in range(16):
        assert m.play(0, "same", 1000, 50).result == "played"
    p = m.play(0, "same", 1000, 99)
    assert p.result == "dropped:busy" and p.channel == -1               # even a high priority: no free duplicate
    assert m.play(0, "other", 1000, 50).result == "played"
    assert m.play(1000, "same", 1000, 50).result == "played"            # the duplicates end with the sound


def test_busy_is_decided_before_the_voice_claim():
    m = VoiceMixer()
    for _ in range(16):
        m.play(0, "same", 1000, 10)
    assert m.play(0, "same", 1000, UI_PRIORITY).result == "dropped:busy"


def test_the_ui_priority_always_gets_a_voice():
    m = VoiceMixer()
    fill(m, 100)
    p = m.play(0, "click", 200, UI_PRIORITY)
    assert p.result.startswith("stolen") and UI_PRIORITY > 100


def test_a_silent_play_still_occupies_a_voice_and_loops_run_until_stopped():
    m = VoiceMixer()
    p = m.play(0, "quiet", 500, 0, volume=-10000)
    assert p.audible and m.playing(0) == [(0, "quiet", 0)]
    lp = m.play(0, "river", LOOP, 40)
    assert lp.loop and m.playing(10 ** 9) == [(lp.channel, "river", 40)]
    m.stop(lp.channel)
    assert m.playing(0) == [(0, "quiet", 0)]


def test_drops_are_counted_and_the_run_is_deterministic():
    def run():
        m = VoiceMixer()
        out = []
        for i in range(60):
            out.append(m.play(i * 10, "s%d" % (i % 5), 400, (i * 37) % 90).result)
        return out, m.drops
    a, b = run(), run()
    assert a == b and a[1] > 0
