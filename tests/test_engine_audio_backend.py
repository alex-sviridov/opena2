"""K11 slice 2: the pygame audio backend, the UI sound queue, the settings flags and `replay --audio-log` (docs/engine/audio.md 5-9).  Headless (dummy SDL drivers)."""

import io
import json
import os
import struct
import time

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pytest

from engine import __main__ as cli
from engine.audio import settings as S
from engine.audio.audiolog import COLUMNS
from engine.audio.music import MusicState
from engine.backend_pygame import audio as A
from engine.rng import Rng
from engine.ui import GameUi, Layout, MainText
from engine.ui.widgets import info_button_rect
from helpers import GFS, needs_data
from test_engine_death import world


def wav(ms=100, rate=22050, channels=1):
    n = rate * ms // 1000
    data = struct.pack("<%dh" % (n * channels), *([1000] * (n * channels)))
    fmt = struct.pack("<HHIIHH", 1, channels, rate, rate * 2 * channels, 2 * channels, 16)
    body = b"WAVEfmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


class DictFS:
    def __init__(self, files):
        self.files = files

    def read(self, p):
        return self.files[p]

    def exists(self, p):
        return p in self.files


def test_wav_duration_from_the_headers_and_empty_files_have_none():
    assert A.wav_duration_ms(wav(100)) == 100
    assert A.wav_duration_ms(wav(250, 44100, 2)) == 250
    assert A.wav_duration_ms(wav(0)) is None and A.wav_duration_ms(b"junk") is None


def test_music_player_streams_a_synthetic_wav_and_asks_the_state_for_the_next_track():
    fs = DictFS({"music/menu.wav": wav(150), "music/map.wav": wav(150)})
    st = MusicState(Rng(3))
    pl = None
    try:
        import pygame
        pygame.mixer.init(22050, -16, 2, 512)
        pl = A.MusicPlayer(fs, st, S.Settings())
        pl.apply(st.set_playlist("menu"))
        assert pl.current == "music/menu.wav" and pygame.mixer.music.get_busy()
        assert abs(pygame.mixer.music.get_volume() - 10 ** (S.Settings().bus_mb("music") / 2000)) < 0.02
        deadline = time.time() + 3
        while pygame.mixer.music.get_busy() and time.time() < deadline:
            time.sleep(0.02)
        assert not pygame.mixer.music.get_busy()                        # the dummy driver plays in real time: the track is over
        assert pl.handle_event(pygame.event.Event(pl.end_event))        # the end event: the next track (a stale one is ignored)
        assert not pl.handle_event(pygame.event.Event(pl.end_event))
        assert pl.opened == ["music/menu.wav", "music/menu.wav"]        # a one-track playlist repeats (`(i + 1) % n`)
        pl.apply(st.set_enabled(False))                                 # music off: fade 2000 ms, no track change
        assert pl.current is None
        pl.apply(st.stop())
        assert not pygame.mixer.music.get_busy()
    finally:
        import pygame
        pygame.mixer.quit()


def test_music_player_a_missing_file_is_silence_and_mute_never_loads():
    import pygame
    pygame.mixer.init(22050, -16, 2, 512)
    try:
        pl = A.MusicPlayer(DictFS({}), MusicState(Rng(1)), S.Settings())
        pl.apply(pl.state.set_playlist("map"))
        assert pl.current is None and pl.opened == []
        fs = DictFS({"music/map.wav": wav(100)})
        pl = A.MusicPlayer(fs, MusicState(Rng(1)), S.Settings(mute=True))
        pl.apply(pl.state.set_playlist("map"))
        assert pl.opened == [] and pl.gain() == 0.0
    finally:
        pygame.mixer.quit()


@needs_data
def test_audio_plays_ui_sounds_loops_and_stops_and_mute_is_silent():
    from allods2.common import as_fs
    a = A.Audio(as_fs(GFS), S.Settings())
    try:
        assert a.ok
        p = a.ui(2)                                                      # click01
        assert p.audible and a.busy_channels() == [p.channel]
        a.director.mixer.stop_all()
        a.pg.mixer.stop()
        assert a.busy_channels() == []
        a.ui(999)                                                        # an id the table does not hold: silent, no error
        assert a.busy_channels() == []
        a.set_playlist("map")
        assert a.music.current == "music/map.wav"
    finally:
        a.close()
    m = A.Audio(as_fs(GFS), S.Settings(mute=True))
    try:
        m.ui(2)
        m.set_playlist("map")
        assert m.busy_channels() == [] and m.music.opened == []
    finally:
        m.close()


@needs_data
def test_null_audio_runs_the_model_with_no_device():
    from allods2.common import as_fs
    a = A.NullAudio(as_fs(GFS))
    p = a.ui(2)
    assert p.audible and not hasattr(a, "pg")
    a.set_playlist("map")
    assert [d.path for d in a.decisions] == ["music/map.wav"]
    assert a.duration_ms("sfx/nothing.wav") is None and a.duration_ms("music/map.wav") > 10000


def test_no_device_is_silence_not_an_error(monkeypatch):
    monkeypatch.setenv("SDL_AUDIODRIVER", "no-such-driver")
    a = A.Audio(DictFS({}), S.Settings())
    assert not a.ok
    a.ui(2)
    a.set_playlist("map")
    a.close()


# -- UI sounds ---------------------------------------------------------------------------------------------------------------------------

def ui_of():
    w = world()
    return GameUi(Layout.for_size(640, 480), w, 1, MainText(), MainText(), MainText()), w


def test_the_ui_queues_sounds_for_the_backend():
    ui, w = ui_of()
    assert ui.take_sounds() == []
    ui.key("i")
    ui.key("b")
    assert ui.take_sounds() == [(7, 0xDC), (7, 0xDC)] and ui.sounds == []
    r = info_button_rect(ui.layout, "mode")
    assert ui.info_release((r.x + 2, r.y + 2)) and ui.take_sounds() == [(1, 0xDC)]
    r = info_button_rect(ui.layout, "book")
    ui.info_release((r.x + 2, r.y + 2))
    assert ui.take_sounds() == [(1, 0xDC), (7, 0xDC)]
    ui.chat_key("", "h", 0)
    ui.open_chat()
    ui.send_chat("hi", 0)
    assert ui.take_sounds() == [(15, 0x64)]


def test_script_messages_play_their_ui_sounds_and_the_dialogs_theirs():
    from engine.sim.triggers import ScriptMessage
    ui, w = ui_of()
    w.events += [ScriptMessage(1, 0xFE), ScriptMessage(1, 0xFD), ScriptMessage(1, 0xFA)]
    ui.poll(0)
    assert ui.take_sounds() == [(0x10, 0xDC), (0xE, 0xDC), (0xE, 0xDC)]
    ui.mouse_down((0, 0))
    assert ui.take_sounds() == []                                        # no dialog: nothing
    ui.open_menu()
    b = next(b for b in ui.modals.top.buttons if b.enabled)
    ui.mouse_down((b.rect.x + 2, b.rect.y + 2))
    assert ui.take_sounds() == [(2, 0xDC)]                               # a generic button press


# -- settings and flags ------------------------------------------------------------------------------------------------------------------

def test_flags_parse_and_override_the_settings_for_the_run_only(tmp_path, monkeypatch):
    f = tmp_path / "s.json"
    S.save(S.Settings(sfx=40, speech=50, music=60), str(f))
    before = f.read_bytes()
    monkeypatch.setenv(S.ENV, str(f))
    p = cli.build_parser()
    for cmd in ("run", "play"):
        a = p.parse_args([cmd, "32", "--mute", "--sfx-volume", "10", "--music-volume", "200", "--speech-volume", "0", "--no-audio"])
        assert a.mute and a.no_audio and (a.sfx_volume, a.music_volume, a.speech_volume) == (10, 200, 0)
        s = cli.audio_settings(a)
        assert (s.mute, s.sfx, s.music, s.speech) == (True, 10, 100, 0)                 # clamped to 0..100
        assert cli.make_audio(a, None) is None
    s = cli.audio_settings(p.parse_args(["run", "32"]))
    assert (s.mute, s.sfx, s.speech, s.music) == (False, 40, 50, 60)
    assert f.read_bytes() == before                                      # never written
    a = p.parse_args(["replay", "x", "--audio-log", "out/a.csv"])
    assert a.audio_log == "out/a.csv"


# -- the run loop ------------------------------------------------------------------------------------------------------------------------

@needs_data
def test_the_play_loop_drives_the_audio_and_starts_the_mission_playlist():
    import numpy as np
    import pygame
    from allods2.assets import AssetCache
    from allods2.common import as_fs
    from engine.backend_pygame import window
    from engine.view import Camera, DrawOptions, TerrainView
    from engine.world import UNIT_ID_BASE, Player, Unit, World
    w = World(np.zeros((40, 40), np.uint16), np.zeros((40, 40), np.int8), "arena")
    w.players[1] = Player(1, 0, human=True)
    w.add_unit(Unit(UNIT_ID_BASE + 1, 1, 1, 10, 10, hp=50, hp_max=50))
    assets = AssetCache(GFS)
    au = A.NullAudio(as_fs(GFS))
    lay = window.Layout.for_size(640, 480)
    v = lay.viewport
    cam = Camera(v.w, v.h, w.width, w.height, 8 * 32, 8 * 32, border=256)
    window.run(w, TerrainView(w, assets.tileset()), cam, lay, speed=8, assets=assets, options=DrawOptions(), max_frames=40,
               audio=au, music_zones=[])
    pygame.display.quit()
    assert [d.action for d in au.decisions] == ["play"] and au.decisions[0].path.startswith("music/b")
    assert w.sound_events == []


# -- replay --audio-log ------------------------------------------------------------------------------------------------------------------

@needs_data
def test_replay_audio_log_writes_the_csv_and_leaves_the_hash_alone(tmp_path, capsys):
    from engine import session
    from engine.sim import MoveUnits, SelectUnits, Simulation
    d = tmp_path / "sess"
    d.mkdir()
    w, _ = session.build_game("32", None, seed=7, difficulty=2, vision=True)
    sim = Simulation(w, triggers=True, vision=True)
    rec = session.Recorder(str(d), "32", 7, 2)
    rec.attach(sim)
    hero = w.units[w.players[1].main_hero]
    for t in range(120):
        sim.step([SelectUnits(1, (hero.id,))] if t == 2 else [MoveUnits(1, (hero.id,), (hero.x + 5, hero.y + 3))] if t == 20 else [])
    final = rec.finish("quit")
    csv_path = tmp_path / "out" / "audio_log.csv"
    assert cli.main(["replay", str(d), "--verify"]) == 0
    plain = capsys.readouterr().out
    assert cli.main(["replay", str(d), "--verify", "--audio-log", str(csv_path)]) == 0
    logged = capsys.readouterr().out
    assert final["hash"] in plain and final["hash"] in logged and "verified" in logged
    lines = csv_path.read_text().splitlines()
    heads = [x for x in lines if x.startswith("#")]
    body = [x for x in lines if not x.startswith("#")]
    assert len(heads) == 2 and "UI sounds are not in a replay" in heads[1]
    assert tuple(body[0].split(",")) == COLUMNS and len(body) > 1
    rows = [r.split(",") for r in body[1:]]
    assert all(len(r) == len(COLUMNS) for r in rows)
    assert any(r[2] == "cmd" and r[3] == "SelectUnits" for r in rows)
    assert [int(r[0]) for r in rows] == sorted(int(r[0]) for r in rows)
