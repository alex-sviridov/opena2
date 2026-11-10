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


def drag_to(pg, key, value, release=True):
    """Press on the thumb, move to the x that `0x4da4a1` maps to `value`, release (the slider's only way to a given value)."""
    w = widget(pg, key)
    r = pg.screen_rect(w)
    y = r.y + 8
    pg.event(Press(pg.thumb_left(w) + 8, y))
    x = r.x + 2 + 24 + -(-value * pg.usable(r) // w.maximum)             # the smallest x whose value is `value`
    pg.event(Move(x, y))
    assert pg.value(w) == value
    if release:
        pg.event(Release(x, y))


def test_frames_follow_the_dialog_size_rule_and_are_centred():
    g, _ = make("game")
    s, _ = make("sound")
    assert (g.frame().w, g.frame().h) == (584, 424) and (g.frame().x, g.frame().y) == (28, 28)
    assert (s.frame().w, s.frame().h) == (488, 360) and (s.frame().x, s.frame().y) == (76, 60)
    from engine.shell.options import snap
    assert snap(600, 480) == (584, 424) and snap(540, 420) == (488, 360)       # the exe's constructor sizes (0x4417c3, 0x43cacb)
    big, _ = make("game", size=(1024, 768))
    assert (big.frame().x, big.frame().y) == (220, 172)


def test_game_options_apply_on_ok_only():
    pg, rec = make("game")
    s = pg.settings
    assert s.shadows and s.game_speed == 4
    click(pg, centre(pg, "shadows"))
    click(pg, centre(pg, "show_health"))
    drag_to(pg, "game_speed", 8)
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
    for v in (0, 8, 4, 2, 7):
        drag_to(pg, "game_speed", v)
        assert pg.draft.game_speed == v
    w = widget(pg, "game_speed")
    pg.event(Press(pg.thumb_left(w) + 8, pg.screen_rect(w).y + 8))              # drag beyond the ends clamps
    pg.event(Move(0, 0))
    assert pg.draft.game_speed == 0
    pg.event(Move(639, 0))
    assert pg.draft.game_speed == 8


def test_slider_geometry_and_clicks_beside_the_thumb_step_by_a_sixteenth():
    pg, _ = make("sound")
    w = widget(pg, "music")
    r = pg.screen_rect(w)
    assert pg.usable(r) == r.w - 52 and pg.step(w) == 6 and pg.step(widget(make("game")[0], "game_speed")) == 1       # `max >> 4`, at least 1
    pg.settings.music = 50
    tl = pg.thumb_left(w)
    assert tl == r.x + 20 + (r.w - 52) * 50 // 100
    pg.event(Press(tl - 10, r.y + 8))                                           # left of the thumb: -6
    assert pg.settings.music == 44 and pg.side == "left"
    pg.event(Release(tl - 10, r.y + 8))
    pg.event(Press(pg.thumb_left(w) + 16 + 3, r.y + 8))                         # right of it: +6
    assert pg.settings.music == 50 and pg.side == "right"
    pg.event(Release(0, 0))
    pg.settings.music = 3
    pg.event(Press(r.x + 1, r.y + 8))                                           # clamps at 0
    assert pg.settings.music == 0
    pg.settings.music = 98
    pg.event(Press(r.right - 2, r.y + 8))
    assert pg.settings.music == 100
    assert pg.slider_value(w, r.x + 26) == 0 and pg.slider_value(w, r.x + 26 + pg.usable(r)) == 100 and pg.slider_value(w, r.x) == 0


def test_slider_drawing_uses_the_confirmed_frames_and_shadows():
    pg, _ = make("sound")
    w = widget(pg, "music")
    r = pg.screen_rect(w)
    sprites = [o for o in pg.scene().ops if hasattr(o, "frame") and r.y <= o.y <= r.y + 8 and r.x <= o.x <= r.right + 5 and o.path.endswith("scrlbars.256")]
    plain = [o.frame for o in sprites if not o.shadow]
    assert plain[0] == 0 and plain[-1] == 10 and set(plain[1:-1]) <= {7, 8} and plain.count(8) == 1       # left end, rail tiles, right end, the thumb last
    assert all(o.shadow == 4 for o in sprites if o.shadow)
    pg.event(Press(r.x + 1, r.y + 8))                                           # the held end region shows its pressed frame
    assert 3 in [o.frame for o in pg.scene().ops if hasattr(o, "frame") and o.path.endswith("scrlbars.256") and not o.shadow]
    pg.event(Release(r.x + 1, r.y + 8))
    pg.event(Press(r.right - 2, r.y + 8))
    assert 11 in [o.frame for o in pg.scene().ops if hasattr(o, "frame") and o.path.endswith("scrlbars.256") and not o.shadow]


def test_sound_sliders_are_live_and_saved_when_the_page_is_left():
    pg, rec = make("sound")
    drag_to(pg, "music", 25, release=False)
    assert pg.settings.music == 25 and rec.applied[-1]["music"] == 25 and rec.saved == []      # live, nothing written yet
    w = widget(pg, "music")
    r = pg.screen_rect(w)
    pg.event(Move(r.x + 2 + 24 + pg.usable(r) // 2, r.y + 8))
    pg.event(Release(r.x + 2 + 24 + pg.usable(r) // 2, r.y + 8))
    assert pg.settings.music == 50 and 100 not in rec.sounds                    # no test sound for the music slider
    drag_to(pg, "sfx", 90)
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
    drag_to(pg, "game_speed", 0)
    click(pg, centre(pg, "ok"))
    sd, _ = make("sound", pg.settings, rec)
    drag_to(sd, "speech", 30)
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


def test_every_widget_of_the_original_is_built():
    pg, _ = make("game")
    keys = {w.key for w in pg.widgets() if w.key}
    assert NOT_BUILT == () and {"game_speed", "shadows", "tips", "message_colours", "autocast_own", "autocast_allies", "autocast_neutral",
                                "formation", "retreat", "autocast_mode", "ok", "cancel"} <= keys
    assert sum(1 for w in pg.widgets() if w.kind == "radio") == 9           # three groups of three


def radio(pg, key, i):
    w = next(w for w in pg.widgets() if w.key == key and w.kind == "radio" and w.maximum == i)
    r = pg.screen_rect(w)
    return r.x + 30, r.y + r.h // 2


def test_party_options_start_at_the_registry_defaults_and_apply_on_ok():
    pg, rec = make("game")
    s = pg.settings
    assert (s.formation, s.retreat, s.autocasting, s.tips) == (1, 0, 0x19, True)       # Auto, Never, AutoCasting 0x19, Tips on
    assert pg.value(widget(pg, "autocast_own")) and not pg.value(widget(pg, "autocast_allies"))
    assert [pg.value(w) for w in pg.widgets() if w.key == "formation" and w.kind == "radio"] == [False, True, False]
    assert [pg.value(w) for w in pg.widgets() if w.key == "autocast_mode" and w.kind == "radio"] == [False, True, False]   # 0x19 has 0x10: Average
    click(pg, radio(pg, "formation", 2))
    click(pg, radio(pg, "retreat", 1))
    click(pg, radio(pg, "autocast_mode", 2))
    click(pg, centre(pg, "autocast_neutral"))
    click(pg, centre(pg, "tips"))
    assert (s.formation, s.retreat, s.autocasting, s.tips) == (1, 0, 0x19, True)         # a draft until OK
    click(pg, centre(pg, "ok"))
    assert (s.formation, s.retreat, s.autocasting, s.tips) == (2, 1, 0x3D, False)         # 8 | 0x30 | own | neutral
    assert rec.saved and rec.saved[-1]["autocasting"] == 0x3D


def test_party_options_persist_and_are_clamped(tmp_path):
    p = str(tmp_path / "s.json")
    s = S.Settings(formation=2, retreat=1, autocasting=0x2D, tips=False)
    S.save(s, p)
    assert S.load(p) == s
    open(p, "w").write('{"formation": 9, "retreat": -3, "autocasting": 999, "tips": "no"}')
    t = S.load(p)
    assert (t.formation, t.retreat, t.autocasting, t.tips) == (2, 0, 0x3F, True)
