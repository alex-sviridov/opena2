"""The options windows (docs/engine/shell.md 5): game options apply on OK only, the sound sliders act live, the values persist in the settings file across restarts
and reach the game's draw options; the in-game menu opens them (no way from the main menu)."""

import os

import pytest

from helpers import GFS, needs_graphics

pygame = pytest.importorskip("pygame")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from allods2.common import as_fs  # noqa: E402
from engine.audio import settings as S  # noqa: E402
from engine.shell import Key, Move, Press, Release  # noqa: E402
from engine.shell.options import NOT_BUILT, OptionsPages, load_texts  # noqa: E402
from shell_scenarios import Recorder  # noqa: E402

pytestmark = needs_graphics
TEXTS = None


def make(page, settings=None, rec=None, size=(640, 480)):
    global TEXTS
    TEXTS = TEXTS or load_texts(as_fs(GFS))
    rec = rec or Recorder()
    return OptionsPages(TEXTS, size, settings or S.Settings(), rec.services, page), rec


def widget(pg, key):
    return next(w for w in pg.widgets() if w.key == key)


def centre(pg, key):
    r = pg.screen_rect(widget(pg, key))
    return r.x + r.w // 2, r.y + r.h // 2


def click(pg, pos):
    pg.event(Move(*pos))
    pg.event(Press(*pos))
    pg.event(Release(*pos))


def slider_at(pg, key, fraction):
    r = pg.screen_rect(widget(pg, key))
    return r.x + 12 + int((r.w - 24) * fraction), r.y + 8


def test_frames_follow_the_dialog_size_rule_and_are_centred():
    g, _ = make("game")
    s, _ = make("sound")
    assert (g.frame().w, g.frame().h) == (584, 360) and (g.frame().x, g.frame().y) == (28, 60)
    assert (s.frame().w, s.frame().h) == (488, 360) and (s.frame().x, s.frame().y) == (76, 60)
    from engine.shell.options import snap
    assert snap(600, 480) == (584, 424) and snap(540, 420) == (488, 360)       # the exe's constructor sizes (0x4417c3, 0x43cacb)
    big, _ = make("game", size=(1024, 768))
    assert (big.frame().x, big.frame().y) == (220, 204)


def test_game_options_apply_on_ok_only():
    pg, rec = make("game")
    s = pg.settings
    assert s.shadows and s.game_speed == 4
    click(pg, centre(pg, "shadows"))
    click(pg, centre(pg, "show_health"))
    pg.event(Press(*slider_at(pg, "game_speed", 1.0)))
    pg.event(Release(*slider_at(pg, "game_speed", 1.0)))
    assert (s.shadows, s.show_health, s.game_speed) == (True, False, 4) and rec.saved == [] and not pg.done      # nothing yet
    click(pg, centre(pg, "ok"))
    assert pg.done and pg.result == "ok"
    assert (s.shadows, s.show_health, s.game_speed) == (False, True, 8)
    assert len(rec.saved) == 1 and rec.saved[0]["game_speed"] == 8


def test_cancel_and_escape_discard_the_game_page():
    pg, rec = make("game")
    click(pg, centre(pg, "smoothing"))
    click(pg, centre(pg, "cancel"))
    assert pg.done and pg.result == "cancel" and pg.settings.smoothing and rec.saved == []
    pg, rec = make("game", pg.settings)
    click(pg, centre(pg, "smoothing"))
    pg.event(Key("escape"))
    assert pg.done and pg.result == "cancel" and pg.settings.smoothing and rec.saved == []


def test_enter_is_the_default_button():
    pg, rec = make("game")
    click(pg, centre(pg, "day_night"))
    pg.event(Key("return"))
    assert pg.result == "ok" and pg.settings.day_night is False
    sd, rec = make("sound")
    sd.event(Key("return"))
    assert sd.result == "return" and len(rec.saved) == 1


def test_animation_off_forces_lighting_off():
    pg, _ = make("game")
    click(pg, centre(pg, "animation"))
    click(pg, centre(pg, "ok"))
    assert (pg.settings.animation, pg.settings.lighting) == (False, False)      # `0x442fb7`


def test_game_speed_slider_range_is_zero_to_eight():
    pg, _ = make("game")
    for f, v in ((0.0, 0), (1.0, 8), (0.5, 4), (0.26, 2)):
        pg.event(Press(*slider_at(pg, "game_speed", f)))
        pg.event(Release(*slider_at(pg, "game_speed", f)))
        assert pg.draft.game_speed == v
    pg.event(Press(*slider_at(pg, "game_speed", 0.5)))                          # drag beyond the ends clamps
    pg.event(Move(0, 0))
    assert pg.draft.game_speed == 0
    pg.event(Move(639, 0))
    assert pg.draft.game_speed == 8


def test_sound_sliders_are_live_and_saved_when_the_page_is_left():
    pg, rec = make("sound")
    pg.event(Press(*slider_at(pg, "music", 0.25)))
    assert pg.settings.music == 25 and rec.applied[-1]["music"] == 25 and rec.saved == []      # live, nothing written yet
    pg.event(Move(*slider_at(pg, "music", 0.5)))
    pg.event(Release(*slider_at(pg, "music", 0.5)))
    assert pg.settings.music == 50 and 100 not in rec.sounds                    # no test sound for the music slider
    pg.event(Press(*slider_at(pg, "sfx", 0.9)))
    pg.event(Release(*slider_at(pg, "sfx", 0.9)))
    assert pg.settings.sfx == 90 and rec.sounds[-1] == 100                      # `0x474`: the SFX test sample on the release
    pg.event(Key("escape"))                                                     # leaving does not revert the sliders (CONFIRMED) and writes the file
    assert pg.done and pg.settings.music == 50 and rec.saved[-1]["music"] == 50 and rec.saved[-1]["sfx"] == 90


def test_play_and_stop_toggle_the_music_and_buttons_click():
    pg, rec = make("sound")
    click(pg, centre(pg, "stop"))
    assert pg.settings.music_enabled is False and rec.applied[-1]["music_enabled"] is False
    click(pg, centre(pg, "play"))
    assert pg.settings.music_enabled is True and rec.music == ["menu"]
    assert rec.sounds.count(2) == 2                                             # every text-button press makes the dialog click


def test_options_persist_across_restarts(tmp_path, monkeypatch):
    monkeypatch.setenv(S.ENV, str(tmp_path / "settings.json"))
    rec = Recorder()
    rec.services.save_settings = lambda s: S.save(s)
    pg, _ = make("game", S.load(), rec)
    click(pg, centre(pg, "lighting"))
    click(pg, centre(pg, "day_night"))
    pg.event(Press(*slider_at(pg, "game_speed", 0.0)))
    pg.event(Release(*slider_at(pg, "game_speed", 0.0)))
    click(pg, centre(pg, "ok"))
    sd, _ = make("sound", pg.settings, rec)
    sd.event(Press(*slider_at(sd, "speech", 0.3)))
    sd.event(Release(*slider_at(sd, "speech", 0.3)))
    sd.event(Key("escape"))
    again = S.load()                                                            # a new process
    assert (again.lighting, again.day_night, again.game_speed, again.speech) == (False, False, 0, 30)
    pg2, _ = make("game", again)
    assert pg2.draft.game_speed == 0 and not pg2.draft.lighting and not pg2.draft.day_night
    sd2, _ = make("sound", again)
    assert sd2.value(widget(sd2, "speech")) == 30


def test_stored_options_reach_the_game():
    from engine.backend_pygame.window import game_options
    from engine.view import DrawOptions
    s = S.Settings(shadows=False, smoothing=False, animation=True, lighting=True, show_health=True, flying_damage=False)
    o = game_options(DrawOptions(), s)
    assert (o.shadows, o.smoothing, o.animate, o.lights, o.health_bars, o.flying_damage) == (False, False, True, True, True, False)
    assert game_options(DrawOptions(), S.Settings(animation=False)).lights is False


def test_checked_and_unchecked_boxes_look_different():
    from engine.backend_pygame import shell as backend
    pg, _ = make("game")
    p = backend.Painter(as_fs(GFS))
    on = backend.scene_screenshot(pg.scene(), (640, 480), p)
    pg.draft.smoothing = False
    off = backend.scene_screenshot(pg.scene(), (640, 480), p)
    r = pg.screen_rect(widget(pg, "smoothing"))
    assert (on[r.y:r.y + 24, r.x:r.x + 28] != off[r.y:r.y + 24, r.x:r.x + 28]).any()
    assert (on[:r.y] == off[:r.y]).all()                                        # nothing else changed


def test_the_widgets_not_built_are_the_ones_listed():
    pg, _ = make("game")
    keys = {w.key for w in pg.widgets() if w.key}
    assert not keys & set(NOT_BUILT) and {"game_speed", "shadows", "ok", "cancel"} <= keys
