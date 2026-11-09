"""K11: the music state machine (docs/engine/audio.md 4.1)."""

from engine.audio.music import MusicState, nearest_theme
from engine.rng import Rng

MISSION = ["music/b%02d.wav" % i for i in range(17)]


def state(seed=1, enabled=True):
    return MusicState(Rng(seed), enabled)


def test_a_mission_starts_at_a_random_track_and_runs_in_order_with_wrap():
    starts = set()
    for seed in range(40):
        m = state(seed)
        d = m.start_mission()
        assert d.action == "play" and d.path == MISSION[d.index] and not d.gapless
        starts.add(d.index)
    assert len(starts) > 8
    m = state(3)
    i = m.start_mission().index
    for k in range(1, 40):
        d = m.track_ended()
        assert d.index == (i + k) % 17 and not d.gapless                  # sequential, wraps b16 -> b00, never loops one track


def test_screen_playlists_and_the_one_track_repeat():
    m = state()
    for name, path in (("menu", "music/menu.wav"), ("map", "music/map.wav"), ("chrgen", "music/chrgen.wav"), ("credit", "music/credit.wav")):
        d = m.set_playlist(name)
        assert d.path == path
        assert m.track_ended().path == path                               # a one-track playlist repeats through (i + 1) % n
    m.set_playlist("town")
    seq = [m.playlist[m.index]] + [m.track_ended().path for _ in range(3)]
    n = ["music/b14.wav", "music/b16.wav", "music/b15.wav"]
    k = n.index(seq[0])
    assert seq == [n[(k + j) % 3] for j in range(4)]


def test_zone_roll_every_16_ticks_stores_the_theme_without_interrupting():
    zones = [(100 << 8, 100 << 8, 20 << 8, (4, -1, -1, -1))]
    m = state()
    m.start_mission(zones)
    cur = m.index
    for t in range(1, 16):
        assert m.tick(t, (100 << 8, 100 << 8)) is None and m.theme == -1   # only ticks with tick & 15 == 0 roll
    assert m.tick(16, (100 << 8, 100 << 8)) is None and m.theme == 4 and m.index == cur
    d = m.track_ended()
    assert d.index == 4 and d.gapless and d.path == MISSION[4]            # the track end opens the theme gaplessly


def test_the_theme_is_never_cleared_and_outside_every_zone_nothing_is_written():
    zones = [(100 << 8, 100 << 8, 20 << 8, (7, -1, -1, -1))]
    m = state()
    m.start_mission(zones)
    m.tick(0, (100 << 8, 100 << 8))
    assert m.theme == 7
    m.tick(16, (500 << 8, 500 << 8))                                      # far outside: the old value stays
    assert m.theme == 7
    for _ in range(3):
        d = m.track_ended()
        assert d.index == 7 and d.gapless                                 # repeats at every later track end
    m.zones = (((300 << 8), (300 << 8), 10 << 8, (2, 2, 2, 2)),)
    m.tick(32, (300 << 8, 300 << 8))
    assert m.theme == 2 and m.track_ended().index == 2


def test_a_zone_theme_at_the_mission_start_switches_at_once():
    zones = [(100 << 8, 100 << 8, 20 << 8, (9, 9, 9, 9))]
    d = state().start_mission(zones, (100 << 8, 100 << 8))
    assert d.index == 9 and d.path == MISSION[9]
    assert state().start_mission(zones, (0, 0)).index != -1                # outside: the random start


def test_nearest_zone_skips_empty_and_origin_zones_and_rolls_until_not_minus_one():
    zones = [(0, 0, 999 << 8, (1, 1, 1, 1)), (50 << 8, 50 << 8, 30 << 8, (-1, -1, -1, -1)),
             (60 << 8, 60 << 8, 30 << 8, (-1, 5, -1, 6)), (55 << 8, 55 << 8, 30 << 8, (3, 3, 3, 3))]
    r = Rng(1)
    assert nearest_theme(zones, 55 << 8, 55 << 8, r) == 3                 # nearest valid zone
    got = {nearest_theme(zones[:3], 60 << 8, 60 << 8, Rng(s)) for s in range(60)}
    assert got == {5, 6}
    assert nearest_theme(zones, 200 << 8, 200 << 8, r) is None


def test_victory_stop_and_defeat_none():
    m = state()
    m.start_mission()
    d = m.stop()
    assert d.action == "stop" and not m.playing and m.track_ended() is None      # a stopped player has no playlist left to continue
    m2 = state()
    m2.start_mission()
    idx = m2.index
    assert m2.tick(0, (0, 0)) is None and m2.playing and m2.index == idx   # the defeat dialog does nothing: the music continues


def test_music_off_fades_and_on_restarts_a_disabled_state_never_plays():
    m = state()
    d0 = m.start_mission()
    f = m.set_enabled(False)
    assert f.action == "fade" and f.fade_ms == 2000 and not m.playing
    assert m.track_ended() is None
    on = m.set_enabled(True)
    assert on.action == "play" and m.playing
    off = state(enabled=False)
    assert off.start_mission() is None and not off.playing and off.set_playlist("menu") is None
    assert off.set_enabled(True).action == "play"


def test_the_music_uses_only_its_own_rng():
    from engine.sim.rng import Rng as SimRng
    assert SimRng is Rng                                                    # the class is shared; the instances are not
    a, b = Rng(1), Rng(1)
    MusicState(a).start_mission()
    assert a.state != b.state
