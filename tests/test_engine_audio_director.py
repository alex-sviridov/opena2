"""K11: the Director (docs/engine/audio.md 3.4, 5, 7): fog gating, the 1500 ms wound throttle, positional play, order voices, UI sounds, the audio log, replay clock."""

import io
from types import SimpleNamespace

import numpy as np

from engine.audio import events as ev
from engine.audio.audiolog import COLUMNS, AudioLog
from engine.audio.director import SEEN, Director, replay_ms, view_of
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


def test_fog_gates_unit_events_of_other_players_only():
    fog = np.zeros((40, 40), np.uint16)
    d = director()
    w = world(fog=fog)
    w.sound_events += [swing(owner=2), swing(owner=1)]
    a, b = d.frame(0, w, V)
    assert a.result == "dropped:fog" and b.result == "played"                         # own units are always seen
    fog[CY >> 8, CX >> 8] |= SEEN
    w.sound_events.append(swing(owner=2))
    assert d.frame(0, w, V)[0].result == "played"
    w.sound_events.append(ev.SoundEvent(3, ev.SPELL, 0, 0, 0, 100))
    assert d.frame(0, w, V)[0].result == "played"                                     # spell objects are never fog gated


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
    TABLE.ids.update({100 + i: "sfx/x%d.wav" % i for i in range(16)})
    try:
        d.frame(0, w, V)
        p = d.ui(15, now_ms=1)
        assert p.priority == 0xDC and p.result.startswith("stolen")
    finally:
        for i in range(16):
            TABLE.ids.pop(100 + i, None)


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


def test_audio_log_rows_and_the_header():
    out = io.StringIO()
    d = director(log=AudioLog(out, ["session x", "seed 1", "UI sounds are not in a replay"]))
    w = world([unit(1)])
    w.sound_events.append(swing(owner=2))
    w.fog = np.zeros((40, 40), np.uint16)
    d.frame(250, w, V, [SelectUnits(1, (1,))])
    d.ui(15, now_ms=300)
    lines = out.getvalue().splitlines()
    assert lines[0] == "# session x" and lines[2].startswith("# UI sounds") and lines[3] == ",".join(COLUMNS)
    rows = [l.split(",") for l in lines[4:]]
    assert rows[0][2:4] == ["sim", "swing"] and rows[0][-1] == "dropped:fog" and rows[0][1] == "250"
    assert rows[-1][2] == "ui" and rows[-1][-1] == "played" and rows[-1][6] == "sfx/message.wav"
    assert len(rows[0]) == len(COLUMNS)


def test_replay_clock_and_camera_view():
    assert replay_ms(0, 16) == 0 and replay_ms(16, 16) == 1000 and replay_ms(20, 8) == 2500
    cam = SimpleNamespace(x=330.5, y=64.0, view_w=640, view_h=480)
    assert view_of(cam) == View(10, 2, 20, 15)


def test_the_audio_rng_is_separate_from_the_world_rng():
    d1, d2 = director(seed=1), director(seed=2)
    assert d1.rng is not d2.rng and d1.voices.rng is d1.rng and d1.ambience.rng is d1.rng and d1.music.rng is d1.rng
