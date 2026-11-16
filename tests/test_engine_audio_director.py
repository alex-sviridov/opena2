"""K11: the Director (docs/engine/audio.md 3.4, 5, 7): no fog gating, the 1500 ms wound throttle, positional play, order voices, UI sounds, the audio log, replay clock."""

import io
from types import SimpleNamespace

import numpy as np

from engine.audio import events as ev
from engine.audio.audiolog import COLUMNS, AudioLog
from engine.audio.director import Director, replay_ms, view_of
from engine.audio.mix import View
from engine.audio.settings import Settings
from engine.sim.commands import AttackUnit, MoveUnits, SelectUnits

V = View(10, 10, 20, 15)
CX, CY = (10 << 8) + (20 << 7), (10 << 8) + (15 << 7)
TABLE = SimpleNamespace(ids={100: "sfx/units/sword.wav", 15: "sfx/message.wav", 220: "sfx/a.wav"}, path=lambda i: TABLE.ids.get(i))


def unit(uid, x=20, y=17, sid=10210, hp=10):
    return SimpleNamespace(uid=uid, id=uid, x=x, y=y, sub_x=128, sub_y=128, server_id=sid, stats=SimpleNamespace(name="Start_MF"), hp=hp, human=True, owner=1)


def world(units=(), fog=None):
    return SimpleNamespace(sound_events=[], units={u.id: u for u in units}, tick=7, fog=fog)


def swing(x=CX, y=CY, owner=2, tick=3, uid=5):
    return ev.SoundEvent(tick, ev.SWING, uid, x, y, 100, owner=owner)


def director(**kw):
    kw.setdefault("table", TABLE)
    kw.setdefault("duration_ms", lambda p: 500)
    kw.setdefault("banks", {"aldor": {"move": ["sfx/characters/aldor/move/1.wav"], "select": [], "attack": [], "swarm": [], "retreat": [], "pickup": [], "defend": []}})
    return Director(**kw)


def test_drain_plays_positionally_and_clears_the_list():
    d = director()
    w = world()
    w.sound_events.append(swing(CX + 8 * 256, CY))
    (p,) = d.frame(0, w, V)
    assert p.result == "played" and p.volume == -171 - 676 and p.priority == 98 and p.sound == 100
    assert w.sound_events == []


def test_buses_come_from_the_settings_and_speech_has_its_own_volume():
    d = director(settings=Settings(sfx=100, speech=0))
    w = world()
    w.sound_events += [swing(), ev.SoundEvent(3, ev.HURT, 5, CX, CY, 220, ev.SPEECH, k=1, owner=2)]
    a, b = d.frame(0, w, V)
    assert (a.volume, b.volume) == (0, -10000)


def test_unit_sounds_are_not_fog_gated():
    """CONFIRMED (audio.md 3.4): the single-player server sends every creature's messages and the view animate path has no visibility test."""
    fog = np.zeros((40, 40), np.uint16)
    d = director()
    w = world(fog=fog)
    w.sound_events += [swing(owner=2), swing(owner=1), ev.SoundEvent(3, ev.SPELL, 0, 0, 0, 100)]
    assert [p.result for p in d.frame(0, w, V)] == ["played"] * 3


def test_hurt_throttle_is_1500_ms_per_unit_for_kinds_1_and_2_only():
    d = director()
    w = world()

    def hurt(k, uid=5):
        return ev.SoundEvent(0, ev.HURT, uid, CX, CY, 220, ev.SPEECH, k=k, owner=1)
    w.sound_events += [hurt(1)]
    assert d.frame(1000, w, V)[0].result == "played"
    w.sound_events += [hurt(2)]
    assert d.frame(2499, w, V)[0].result == "dropped:cooldown"
    w.sound_events += [hurt(2, uid=6)]
    assert d.frame(2499, w, V)[0].result == "played"                                  # another unit
    w.sound_events += [hurt(1)]
    assert d.frame(2500, w, V)[0].result == "played"
    w.sound_events += [hurt(0), hurt(0)]
    assert [p.result for p in d.frame(2501, w, V)] == ["played", "played"]            # kind 0 is never throttled
    w.sound_events += [ev.SoundEvent(0, ev.DEATH, 5, CX, CY, 220, ev.SPEECH, k=3, owner=1)]
    assert d.frame(2502, w, V)[0].result == "played"


def test_skill_up_is_flat_priority_100_and_only_for_the_viewers_hero():
    d = director()
    w = world()
    w.sound_events += [ev.SoundEvent(0, ev.SKILLUP, 1, 0, 0, 15, owner=1), ev.SoundEvent(0, ev.SKILLUP, 2, 0, 0, 15, owner=2)]
    ps = d.frame(0, w, V)
    assert len(ps) == 1 and ps[0].priority == 100 and ps[0].pan == 0 and ps[0].volume == -676


def test_ui_sound_is_flat_with_priority_0xdc_and_steals_a_full_mixer():
    d = director(duration_ms=lambda p: 10 ** 6)
    w = world()
    for i in range(16):
        w.sound_events.append(ev.SoundEvent(0, ev.SPELL, 0, CX, CY, 100 + i))
    saved = dict(TABLE.ids)
    TABLE.ids.update({100 + i: "sfx/x%d.wav" % i for i in range(16)})
    try:
        d.frame(0, w, V)
        p = d.ui(15, now_ms=1)
        assert p.priority == 0xDC and p.result.startswith("stolen")
    finally:
        TABLE.ids.clear()
        TABLE.ids.update(saved)


def test_missing_files_and_null_slots_take_no_voice():
    d = director(duration_ms=lambda p: None)
    w = world()
    w.sound_events += [swing(), ev.SoundEvent(0, ev.SPELL, 0, CX, CY, 999)]
    assert [p.result for p in d.frame(0, w, V)] == ["dropped:missing"] * 2
    assert d.mixer.playing(0) == []


def test_order_voice_plays_at_the_unit_on_the_speech_bus_with_cooldown_and_ignores_ai_commands():
    h = unit(1)
    d = director()
    w = world([h])
    (p,) = d.frame(0, w, V, [MoveUnits(1, (1,), (5, 5))])
    assert p.sound == ("hero", "aldor", "move/1") and p.result == "played"
    (c,) = d.frame(1000, w, V, [MoveUnits(1, (1,), (5, 5))])
    assert c.result == "dropped:cooldown"
    assert d.frame(9000, w, V, [MoveUnits(1, (1,), (5, 5), ai=True), MoveUnits(2, (1,), (5, 5)), AttackUnit(1, (1,), 9)]) == []     # AI, another player, empty slot
    assert d.frame(20000, w, V, [MoveUnits(1, (1,), (5, 5))], skip_voice=True) == []                                               # the skip rule


def test_move_voice_is_skipped_when_the_chosen_unit_was_already_walking():
    """`0x418c99`: `view+0x78 == 1` is the unit's state at the previous animate; the skip stamps nothing."""
    h = unit(1)
    h.state = 0
    d = director()
    w = world([h])
    (p,) = d.frame(0, w, V, [MoveUnits(1, (1,), (5, 5))])
    assert p.result == "played"
    h.state = 1                                                                       # the order started it walking
    assert d.frame(100, w, V) == []                                                   # (the snapshot is taken at the end of each frame)
    assert d.frame(9000, w, V, [MoveUnits(1, (1,), (6, 6))]) == []                    # walking: no move voice, no stamp
    assert d.voices.stamp[1] == 0
    h.state = 0
    d.frame(9200, w, V)
    (q,) = d.frame(9300, w, V, [MoveUnits(1, (1,), (7, 7))])
    assert q.result == "played"


def test_audio_log_rows_and_the_header():
    out = io.StringIO()
    d = director(log=AudioLog(out, ["session x", "seed 1", "UI sounds are not in a replay"]))
    w = world([unit(1)])
    w.sound_events.append(swing(owner=2))
    d.frame(250, w, V, [SelectUnits(1, (1,))])
    d.ui(15, now_ms=300)
    lines = out.getvalue().splitlines()
    assert lines[0] == "# session x" and lines[2].startswith("# UI sounds") and lines[3] == ",".join(COLUMNS)
    rows = [l.split(",") for l in lines[4:]]
    assert rows[0][2:4] == ["sim", "swing"] and rows[0][-1] == "played" and rows[0][1] == "250"
    assert rows[-1][2] == "ui" and rows[-1][-1] == "played" and rows[-1][6] == "sfx/message.wav"
    assert len(rows[0]) == len(COLUMNS)


def test_replay_clock_and_camera_view():
    assert replay_ms(0, 16) == 0 and replay_ms(16, 16) == 1000 and replay_ms(20, 8) == 2500
    cam = SimpleNamespace(x=330.5, y=64.0, view_w=640, view_h=480)
    assert view_of(cam) == View(10, 2, 20, 15)


def test_the_audio_rng_is_separate_from_the_world_rng():
    d1, d2 = director(seed=1), director(seed=2)
    assert d1.rng is not d2.rng and d1.voices.rng is d1.rng and d1.ambience.rng is d1.rng and d1.music.rng is d1.rng


def test_speech_line_is_flat_priority_0x80_on_the_speech_bus_and_missing_files_drop():
    d = director(settings=Settings(sfx=100, speech=0), duration_ms=lambda p: 500 if p == "speech/town/0097t000p01.wav" else None)
    p = d.speech("speech/town/0097t000p01.wav", now_ms=10)
    assert p.result == "played" and p.priority == 0x80 and p.volume == -10000 and p.pan == 0              # the speech slider (0) applies, not the sfx one
    assert d.speech("speech/town/9999t000p01.wav").result == "dropped:missing"


def test_shell_services_advance_the_clock_so_voices_free_up():
    d = director(duration_ms=lambda p: 50)
    for _ in range(16):
        d.ui("sfx/a.wav")
    assert d.ui("sfx/a.wav").result.startswith("dropped")                                # a frozen clock keeps all 16 voices busy: why the backend must advance it
    d.now += 60
    assert d.ui("sfx/a.wav").result == "played"


def test_audio_backend_wall_clock_moves_the_director_clock():
    import time
    from engine.backend_pygame.audio import NullAudio
    a = NullAudio(__import__("a2res").OS)
    a._wall(None)
    t0 = a.director.now
    time.sleep(0.03)
    a._wall(None)
    assert a.director.now - t0 >= 20
    a._wall(5000)                                                                         # an explicit mission clock is left alone
    assert a.director.now - t0 < 1000


def test_stop_ui_cuts_a_playing_ui_sound_by_path_and_ignores_an_ended_or_unknown_one():
    """A town scene's slot stop (`0x4385b0`): only a sound that still plays is cut."""
    d = director()
    p = d.ui("sfx/town/shop/enter.wav", now_ms=0)
    assert p.audible
    out = d.stop_ui("sfx/town/shop/enter.wav")
    assert [(q.channel, q.result) for q in out] == [(p.channel, "stopped")] and not d.mixer.busy[p.channel]
    assert d.stop_ui("sfx/town/shop/enter.wav") == []                                  # already cut
    assert d.stop_ui("sfx/town/never.wav") == []
    d.ui("sfx/town/point.wav", now_ms=0)
    d.now = 600                                                                         # the 500 ms sound ended: nothing to stop
    assert d.stop_ui("sfx/town/point.wav") == []
