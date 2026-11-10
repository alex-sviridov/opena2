"""The shell's options screens (docs/engine/shell.md 5): game options apply on OK only, the sound sliders act live, the values persist in the settings file
across restarts and reach the game's draw options."""

import os

import pytest

from helpers import GFS, needs_graphics

pygame = pytest.importorskip("pygame")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from engine.audio import settings as S  # noqa: E402
from engine.shell import Key, Move, Press, Release, Services, Shell  # noqa: E402
from shell_scenarios import Recorder, click, make_shell, to_menu  # noqa: E402

pytestmark = needs_graphics


def widget(sh, key=None, text=None, kind=None):
    o = sh.current
    for w in o.widgets():
        if (key is None or w.key == key) and (text is None or w.text == text) and (kind is None or w.kind == kind):
            return w
    raise KeyError((key, text))


def centre(sh, w):
    r = sh.current.screen_rect(w)
    return r.x + r.w // 2, r.y + r.h // 2


def to_page(sh, page):
    to_menu(sh)
    sh.handle(Key("o"))
    assert sh.name == "options" and sh.current.page == "top"
    sh.handle(Key({"game": "o", "sound": "n"}[page]))
    assert sh.current.page == page


def slider_at(sh, w, fraction):
    r = sh.current.screen_rect(w)
    return r.x + 12 + int((r.w - 24) * fraction), r.y + 8


def test_top_page_buttons_open_the_pages_and_leave():
    sh, rec = make_shell(GFS)
    to_menu(sh)
    sh.handle(Key("o"))
    click(sh, centre(sh, widget(sh, "game")))
    assert sh.current.page == "game"
    click(sh, centre(sh, widget(sh, "cancel")))
    assert sh.current.page == "top"
    click(sh, centre(sh, widget(sh, "sound")))
    assert sh.current.page == "sound"
    sh.handle(Key("escape"))
    assert sh.current.page == "top" and sh.name == "options"
    click(sh, centre(sh, widget(sh, "back")))
    assert sh.name == "menu"
    assert rec.sounds.count(2) == 4                                   # every text-button press makes the dialog click


def test_game_options_apply_on_ok_only():
    sh, rec = make_shell(GFS)
    to_page(sh, "game")
    assert sh.settings.shadows and sh.settings.game_speed == 4
    click(sh, centre(sh, widget(sh, "shadows")))
    click(sh, centre(sh, widget(sh, "show_health")))
    sh.handle(Press(*slider_at(sh, widget(sh, "game_speed"), 1.0)))
    sh.handle(Release(*slider_at(sh, widget(sh, "game_speed"), 1.0)))
    assert (sh.settings.shadows, sh.settings.show_health, sh.settings.game_speed) == (True, False, 4)      # nothing yet
    assert rec.saved == []
    click(sh, centre(sh, widget(sh, "ok")))
    assert sh.current.page == "top"
    assert (sh.settings.shadows, sh.settings.show_health, sh.settings.game_speed) == (False, True, 8)
    assert len(rec.saved) == 1 and rec.saved[0]["game_speed"] == 8


def test_cancel_and_escape_discard_the_game_page():
    sh, rec = make_shell(GFS)
    to_page(sh, "game")
    click(sh, centre(sh, widget(sh, "smoothing")))
    click(sh, centre(sh, widget(sh, "cancel")))
    assert sh.settings.smoothing and rec.saved == []
    sh.handle(Key("o"))
    click(sh, centre(sh, widget(sh, "smoothing")))
    sh.handle(Key("escape"))
    assert sh.settings.smoothing and rec.saved == []
    sh.handle(Key("o"))
    assert sh.current.draft.smoothing                                 # the draft starts from the stored values again


def test_animation_off_forces_lighting_off():
    sh, _ = make_shell(GFS)
    to_page(sh, "game")
    click(sh, centre(sh, widget(sh, "animation")))
    click(sh, centre(sh, widget(sh, "ok")))
    assert (sh.settings.animation, sh.settings.lighting) == (False, False)      # `0x442fb7`


def test_game_speed_slider_range_is_zero_to_eight():
    sh, _ = make_shell(GFS)
    to_page(sh, "game")
    w = widget(sh, "game_speed")
    for f, v in ((0.0, 0), (1.0, 8), (0.5, 4), (0.26, 2)):
        sh.handle(Press(*slider_at(sh, w, f)))
        sh.handle(Release(*slider_at(sh, w, f)))
        assert sh.current.draft.game_speed == v
    sh.handle(Press(*slider_at(sh, w, 0.5)))                          # drag beyond the ends clamps
    sh.handle(Move(0, 0))
    assert sh.current.draft.game_speed == 0
    sh.handle(Move(639, 0))
    assert sh.current.draft.game_speed == 8


def test_sound_sliders_are_live_and_saved_when_the_page_is_left():
    sh, rec = make_shell(GFS)
    to_page(sh, "sound")
    w = widget(sh, "music")
    sh.handle(Press(*slider_at(sh, w, 0.25)))
    assert sh.settings.music == 25 and rec.applied[-1]["music"] == 25 and rec.saved == []      # live, nothing written yet
    sh.handle(Move(*slider_at(sh, w, 0.5)))
    sh.handle(Release(*slider_at(sh, w, 0.5)))
    assert sh.settings.music == 50 and 100 not in rec.sounds             # no test sound for the music slider
    w = widget(sh, "sfx")
    sh.handle(Press(*slider_at(sh, w, 0.9)))
    sh.handle(Release(*slider_at(sh, w, 0.9)))
    assert sh.settings.sfx == 90 and rec.sounds[-1] == 100            # `0x474`: the SFX test sample on the release
    sh.handle(Key("escape"))                                          # leaving does not revert the sliders (CONFIRMED) and writes the file
    assert sh.settings.music == 50 and rec.saved[-1]["music"] == 50 and rec.saved[-1]["sfx"] == 90


def test_play_and_stop_toggle_the_music():
    sh, rec = make_shell(GFS)
    to_page(sh, "sound")
    click(sh, centre(sh, widget(sh, "stop")))
    assert sh.settings.music_enabled is False and rec.applied[-1]["music_enabled"] is False
    n = len(rec.music)
    click(sh, centre(sh, widget(sh, "play")))
    assert sh.settings.music_enabled is True and rec.music[n:] == ["menu"]


def test_options_persist_across_restarts(tmp_path, monkeypatch):
    path = str(tmp_path / "settings.json")
    monkeypatch.setenv(S.ENV, path)
    rec = Recorder()
    rec.services.save_settings = lambda s: S.save(s)
    sh, _ = make_shell(GFS, settings=S.load(), rec=rec)
    to_page(sh, "game")
    click(sh, centre(sh, widget(sh, "lighting")))
    click(sh, centre(sh, widget(sh, "day_night")))
    sh.handle(Press(*slider_at(sh, widget(sh, "game_speed"), 0.0)))
    sh.handle(Release(*slider_at(sh, widget(sh, "game_speed"), 0.0)))
    click(sh, centre(sh, widget(sh, "ok")))
    sh.handle(Key("n"))
    sh.handle(Press(*slider_at(sh, widget(sh, "speech"), 0.3)))
    sh.handle(Release(*slider_at(sh, widget(sh, "speech"), 0.3)))
    sh.handle(Key("escape"))
    del sh
    again = S.load()                                                  # a new process
    assert (again.lighting, again.day_night, again.game_speed, again.speech) == (False, False, 0, 30)
    sh2, _ = make_shell(GFS, settings=again)
    to_page(sh2, "game")
    assert sh2.current.draft.game_speed == 0 and not sh2.current.draft.lighting
    sh2.handle(Key("escape"))
    sh2.handle(Key("n"))
    w = widget(sh2, "speech")
    assert sh2.current.value(w) == 30


def test_stored_options_reach_the_game():
    from engine.__main__ import game_options
    from engine.view import DrawOptions
    s = S.Settings(shadows=False, smoothing=False, animation=True, lighting=True, show_health=True, flying_damage=False)
    o = game_options(DrawOptions(), s)
    assert (o.shadows, o.smoothing, o.animate, o.lights, o.health_bars, o.flying_damage) == (False, False, True, True, True, False)
    assert game_options(DrawOptions(), S.Settings(animation=False)).lights is False


def test_checked_and_unchecked_boxes_look_different():
    from engine.backend_pygame import shell as backend
    sh, _ = make_shell(GFS)
    to_page(sh, "game")
    p = backend.Painter(sh.fs)
    on = backend.screenshot(sh, p)
    sh.current.draft.smoothing = False
    off = backend.screenshot(sh, p)
    r = sh.current.screen_rect(widget(sh, "smoothing"))
    assert (on[r.y:r.y + 24, r.x:r.x + 28] != off[r.y:r.y + 24, r.x:r.x + 28]).any()
    assert (on[:r.y] == off[:r.y]).all()                              # nothing else changed
