"""J1 interface against the install (skipped without it): the worked example of ui-layout 11.7, headless screenshot goldens (`golden.json["ui"]`),
and the main loop: ESC = menu, End Quest leaves, a dialog freezes the simulation without a catch-up burst, the command bar acts.

The goldens draw all text with the game's own fonts, so unlike the old stand-in they do not depend on the pinned pygame-ce font; they do depend on
the interface art, the fonts, and the 3x3 rules of the layout.  Regenerate with `tools/update_golden.py --only interface,ui` after an intended change."""

import hashlib
import importlib.util
import json
import os

import pytest

from helpers import GFS, needs_graphics

pygame = pytest.importorskip("pygame")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from allods2.assets import AssetCache  # noqa: E402
from allods2.cli import open_map  # noqa: E402
from engine.backend_pygame import window  # noqa: E402
from engine.backend_pygame.interface import make_game_ui, screenshot_window  # noqa: E402
from engine.sim import SelectUnits, selection_system, triggers  # noqa: E402
from engine.ui import Layout, info  # noqa: E402
from engine.ui.widgets import cell_rect, widget_rect  # noqa: E402
from engine.view import Camera, DrawOptions, TerrainView  # noqa: E402
from engine.world import World  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pytestmark = needs_graphics


@pytest.fixture(scope="module")
def game():
    assets = AssetCache(GFS)
    m = open_map("10", GFS)
    w = World.from_map(m, assets)
    triggers.enable(w, m, assets=assets, party=0)
    hero = next(u for u in w.units.values() if u.human and u.owner == 1)
    return assets, w, hero, TerrainView(w, assets.tileset())


def camera(w, hero, lay):
    v = lay.viewport
    return Camera(v.w, v.h, w.width, w.height, hero.x * 32 - v.w // 2, hero.y * 32 - v.h // 2, border=256)


def test_worked_example_text_mode_rows(game):
    """ui-layout 11.7: Hero, 116/116, attributes, Dmg 12-19, Attack 78, Absorb 4, Defense 43, skills, resistances, Weight 23.6, XP 10, Sight 6.4, Speed 19."""
    assets, w, hero, _ = game
    ui = make_game_ui(assets, Layout.for_size(640, 480), w, 1, "10")
    rows = {(r.text, r.y): r for r in info.text_rows(w, hero, ui.main, ui.unit_names.lines, 1, "Hero")}
    px, py = 480, 238
    at = lambda text, y: (px + rows[(text, y)].x, py + rows[(text, y)].y, rows[(text, y)].flags)
    assert at("Hero", 0x12) == (552, 256, info.CENTRE)
    assert at("Body", 0x2C)[:2] == (486, 282) and at("40", 0x2C) == (560, 282, info.RIGHT) and at("36", 0x36)[0] == 560
    assert at("Health", 0x2C) == (595, 282, info.CENTRE) and at("116/116", 0x36) == (595, 292, info.CENTRE)
    assert at("Mana", 0x40)[:2] == (595, 302) and at("0/0", 0x4A)[:2] == (595, 312)
    assert at("Dmg", 0x58)[:2] == (486, 326) and at("12-19", 0x58) == (550, 326, info.RIGHT) and at("78", 0x62)[0] == 550
    assert at("Absorb", 0x58)[0] == 554 and at("4", 0x58) == (620, 326, info.RIGHT) and at("43", 0x62)[0] == 620
    assert at("Skills", 0x70)[:2] == (486, 350) and rows[("Skills", 0x70)].table == "header" and at("Resistance", 0x70)[0] == 554
    assert [at(n, 0x7A + 10 * k)[1] for k, n in enumerate(("Blade", "Axe", "Bludgeon", "Pike", "Shooting"))] == [360, 370, 380, 390, 400]
    assert rows[("20", 0x7A)].x == 0x46 and at("Fire", 0x7A)[0] == 554 and at("Astral", 0x7A + 40)[1] == 400
    assert at("Weight", 0xAE)[:2] == (496, 412) and at("23.6", 0xAE) == (607, 412, info.RIGHT)
    assert at("XP", 0xBA)[:2] == (496, 424) and at("10", 0xBA)[0] == 607
    assert at("Sight", 200)[:2] == (520, 438) and at("6.4", 200)[0] == 586 and at("Speed", 0xD2)[1] == 448 and at("19", 0xD2)[0] == 586
    assert not any(r.text == "Level" for r in rows.values())


def test_worked_example_portrait_layers(game):
    assets, w, hero, _ = game
    kind, files = info.portrait(w, hero)
    names = [f.rsplit("/", 1)[-1][:-4] for f in files]
    assert kind == "doll" and names == ["backm", "32", "0012030", "1107015", "0009022", "0010026", "0001004", "0008019", "0009022", "0010026"]
    assert [f.split("/")[-2] for f in files[2:]] == ["primary"] * 6 + ["secondary"] * 2
    assert all(GFS.exists(f) for f in files)


def test_text_draw_places_by_the_exact_measure():
    from engine.backend_pygame import text
    surf = lambda: pygame.Surface((200, 30))
    m = text.measure("Health", 2)
    a, b, c, d = surf(), surf(), surf(), surf()
    text.draw_text_exact(a, "Health", 100, 4, "label", text.RIGHT, 2)
    text.draw_text_exact(b, "Health", 100 - m, 4, "label", text.LEFT, 2)
    text.draw_text_exact(c, "Health", 100, 4, "label", text.CENTRE, 2)
    text.draw_text_exact(d, "Health", 100 - m // 2, 4, "label", text.LEFT, 2)
    assert pygame.image.tobytes(a, "RGB") == pygame.image.tobytes(b, "RGB") != pygame.image.tobytes(c, "RGB")
    assert pygame.image.tobytes(c, "RGB") == pygame.image.tobytes(d, "RGB")
    assert text.measure("~Ok", 1) == text.measure("Ok", 1)                  # a lone `~` counts 0


def test_ui_golden():
    spec = importlib.util.spec_from_file_location("update_golden", os.path.join(ROOT, "tools", "update_golden.py"))
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    gold = json.load(open(os.path.join(ROOT, "tests", "golden.json")))["ui"]
    got = tool.ui_hashes(GFS)
    assert got == gold, "UI changed: %s; run tools/update_golden.py --only interface,ui" % [k for k in gold if got.get(k) != gold[k]]
    assert len(set(got.values())) == len(got)                                # every scenario looks different


def test_screens_differ_where_they_should_and_the_portrait_is_painted(game):
    assets, w, hero, tv = game
    lay = Layout.for_size(640, 480)
    cam = camera(w, hero, lay)
    shots = {}
    for name in ("pic", "text", "menu", "pause"):
        ui = make_game_ui(assets, lay, w, 1, "10")
        if name == "text":
            ui.toggle_mode()
        elif name == "menu":
            ui.open_menu()
        elif name == "pause":
            ui.toggle_pause()
        shots[name] = screenshot_window(tv, cam, lay, 0, None, assets, DrawOptions(), None, (hero.id,), ui=ui)
    p = widget_rect(lay, "info.portrait")
    panel = lambda s: s[p.y:p.bottom, p.x:p.right]
    assert panel(shots["pic"]).any(axis=2).mean() > 0.5                      # the paper doll fills the panel
    assert (panel(shots["pic"]) != panel(shots["text"])).any()
    mf = widget_rect(lay, "menu.frame")
    assert (shots["menu"][mf.y:mf.bottom, mf.x:mf.right] != shots["pic"][mf.y:mf.bottom, mf.x:mf.right]).mean() > 0.2
    assert (shots["pause"] != shots["menu"]).any()
    cmd = widget_rect(lay, "bar.back")
    assert shots["pic"][cmd.y:cmd.bottom, cmd.x:cmd.right].any()             # the bar is drawn for an own selection (not the Heads panel)


# --- the main loop ---------------------------------------------------------------------------------------------------------------

def world_hash(w):
    return hashlib.sha256(w.dump_json().encode()).hexdigest()


def fresh(game):
    assets = AssetCache(GFS)
    m = open_map("10", GFS)
    w = World.from_map(m, assets, seed=7)
    triggers.enable(w, m, assets=assets, party=0)
    hero = next(u for u in w.units.values() if u.human and u.owner == 1)
    lay = Layout.for_size(640, 480)
    return assets, w, hero, TerrainView(w, assets.tileset()), lay, camera(w, hero, lay)


def post(kind, **kw):
    pygame.event.post(pygame.event.Event(kind, **kw))


def key(k):
    post(pygame.KEYDOWN, key=k, mod=0)


def click(pos):
    post(pygame.MOUSEBUTTONDOWN, pos=pos, button=1)
    post(pygame.MOUSEBUTTONUP, pos=pos, button=1)


def run_loop(game, hook, frames, **kw):
    assets, w, hero, tv, lay, cam = fresh(game)
    seen = []
    window.ensure_display(*lay.size)

    def wrapped(f, ui, world):
        seen.append(f)
        hook(f, ui, world, hero, lay)
    sim = window.run(w, tv, cam, lay, assets=assets, max_frames=frames, frame_hook=wrapped, **kw)
    return sim, w, seen


def test_pause_freezes_the_world_and_resume_does_not_burst(game):
    ticks, hashes, frozen = {}, {}, {}

    def hook(f, ui, w, hero, lay):
        ticks[f], hashes[f], frozen[f] = w.tick, world_hash(w), ui.frozen
        if f == 6:
            key(pygame.K_PAUSE)
        if f == 40:
            key(pygame.K_PAUSE)

    sim, w, seen = run_loop(game, hook, 90)
    paused = [f for f in range(7, 41) if frozen[f]]
    assert paused == list(range(7, 41)) and not frozen[41] and not frozen[5]
    assert len({hashes[f] for f in paused}) == 1 and len({ticks[f] for f in paused}) == 1       # N frames, the world dump does not change
    assert hashes[89] != hashes[40] and ticks[89] > ticks[40]                                     # and it moves again after the resume
    assert max(ticks[f + 1] - ticks[f] for f in range(41, 89)) <= 3                               # acc was reset: no catch-up burst of the 34 frozen frames
    assert sim.ui.modals.kinds() == ()


def test_escape_opens_the_menu_instead_of_quitting_and_end_quest_exit_leaves(game):
    state = {}

    def hook(f, ui, w, hero, lay):
        if f == 3:
            key(pygame.K_ESCAPE)
        if f == 5:
            state["menu"] = ui.modals.kinds()
            eq = ui.modals.top.buttons[5].rect
            click((eq.x + 4, eq.y + 4))
        if f == 8:
            state["eq"] = ui.modals.kinds()
            b = ui.modals.top.buttons[2].rect                      # Exit to Windows
            click((b.x + 4, b.y + 4))

    sim, w, seen = run_loop(game, hook, 60)
    assert state == {"menu": ("menu",), "eq": ("menu", "endquest")}
    assert sim.ui.quit == "windows" and max(seen) < 20            # the loop ended long before max_frames


def test_escape_twice_returns_to_the_game_and_the_window_close_still_quits(game):
    def hook(f, ui, w, hero, lay):
        if f in (3, 6):
            key(pygame.K_ESCAPE)
        if f == 30:
            post(pygame.QUIT)

    sim, w, seen = run_loop(game, hook, 80)
    assert max(seen) <= 31 and sim.ui.quit is None and not sim.ui.frozen


def test_keys_and_clicks_do_not_reach_the_world_while_a_dialog_is_open(game):
    ids = []

    def hook(f, ui, w, hero, lay):
        if f == 2:
            ids.append(hero.id)
            selection_system(w, [SelectUnits(1, (hero.id,))])
            key(pygame.K_PAUSE)
        if f == 4:
            key(pygame.K_g)
            c = cell_rect(lay, 3)
            click((c.x + 5, c.y + 5))
            click((100, 100))
            key(pygame.K_t)

    sim, w, seen = run_loop(game, hook, 20)
    assert [c for _, c in sim.log if not getattr(c, "ai", False)] == [] and w.players[1].selection == (ids[0],) and not sim.ui.world_state() == "none"


def test_command_bar_buttons_act_like_the_hotkeys_and_tab_toggles_the_mode(game):
    def hook(f, ui, w, hero, lay):
        if f == 2:
            selection_system(w, [SelectUnits(1, (hero.id,))])
        if f == 4:
            c = cell_rect(lay, 2)                                   # Guard acts at once
            click((c.x + 5, c.y + 5))
            key(pygame.K_TAB)
        if f == 8:
            c = cell_rect(lay, 0)                                   # Attack arms the pending mode
            click((c.x + 5, c.y + 5))

    sim, w, seen = run_loop(game, hook, 14)
    assert [type(c).__name__ for _, c in sim.log if not getattr(c, "ai", False)] == ["Guard"]
    assert sim.ui.panel_mode == "text"


def test_no_way_line_only_with_trace(game):
    from engine.world import NoWay

    def hook(f, ui, w, hero, lay):
        if f == 2:
            w.events.append(NoWay(1, w.tick))

    sim, w, _ = run_loop(game, hook, 6)
    assert sim.ui.messages.queue == [] and w.events == []
    sim, w, _ = run_loop(game, hook, 6, trace=True)
    assert [q[0] for q in sim.ui.messages.queue] and sim.ui.messages.queue[0][0].startswith(b"No way")


# --- Panels pieces: frame_surface, draw_bar, draw_buttons (ui-layout 11.1, 11.2, 11.4) ------------------------------------------------

def make_panels():
    from engine.backend_pygame.panels import SHADOW_ALPHA, Panels
    return Panels(GFS, Layout.for_size(640, 480)), SHADOW_ALPHA


def test_frame_surface_is_the_body_plus_an_8_px_darkened_shadow_cached_per_size():
    panels, shadow = make_panels()
    s = panels.frame_surface(288, 160)                                  # the 296 x 168 dialog body (w' - 8, h' - 8)
    assert s.get_size() == (296, 168) and panels.frame_surface(288, 160) is s and panels.frame_surface(288, 224) is not s
    alpha = pygame.surfarray.array_alpha(s)                              # [x, y]
    assert alpha[148, 80] == 255 and alpha[0x30 + 5, 0x30 + 5] == 255   # centre tiles / body
    assert alpha[292, 100] == shadow and alpha[100, 164] == shadow       # the shadow strips right of and below the body are the darken level 6 (alpha 96)
    assert alpha[292, 2] == 0 and alpha[2, 164] == 0                     # the shadow starts 8 px down / right of the frame origin
    assert shadow == round(255 * 6 / 16)                                 # dst * 10 / 16


def test_draw_bar_blits_the_empty_cell_when_disabled_and_the_down_cell_when_pressed():
    from engine.ui.bar import Cell
    panels, _ = make_panels()
    win = pygame.Surface((640, 480))
    win.fill((1, 2, 3))
    panels.draw_bar(win, [Cell(0, True, False), Cell(1, False, False), Cell(2, True, True)])
    emp, down = panels.opaque("CommandEmpR"), panels.opaque("CommandDnR")
    cell = lambda i: cell_rect(panels.layout, i)
    src = lambda i: pygame.Rect(8 + (i & 3) * 34, 7 + (i >> 2) * 34, 34, 34)
    grab = lambda surf, r: pygame.image.tobytes(surf.subsurface(r), "RGB")
    r0, r1, r2 = cell(0), cell(1), cell(2)
    assert grab(win, pygame.Rect(r0.x, r0.y, 34, 34)) == grab(win, pygame.Rect(0, 0, 34, 34))                 # an enabled idle cell is not touched
    assert grab(win, pygame.Rect(r1.x, r1.y, 34, 34)) == grab(emp, src(1))
    assert grab(win, pygame.Rect(r2.x, r2.y, 34, 34)) == grab(down, src(2))


def test_draw_buttons_draws_all_four_whatever_the_selection_and_follows_the_panel_mode():
    panels, _ = make_panels()
    p = panels.layout.info_panel.rect

    class Ui:
        def __init__(self, state):
            self.state = state

        def world_state(self):
            return self.state

    def paint(state, mode):
        win = pygame.Surface((640, 480))
        win.fill((1, 2, 3))
        panels.draw_buttons(win, Ui(state), mode)
        return win

    def touched(win, x, y, w, h):
        return pygame.image.tobytes(win.subsurface(pygame.Rect(p.x + x, p.y + y, w, h)), "RGB") != pygame.image.tobytes(win.subsurface(pygame.Rect(0, 0, w, h)), "RGB")
    own, foreign = paint("own", info.MODE_PICTURE), paint("foreign", info.MODE_PICTURE)
    assert all(touched(own, *r) for r in ((0, 4, 28, 37), (1, 0xC9, 28, 30), (0x80, 4, 28, 32), (0x7E, 0xCE, 32, 32)))
    assert foreign.get_buffer().raw == own.get_buffer().raw                                                        # the selection does not matter in a mission
    assert paint("own", info.MODE_TEXT).get_buffer().raw != own.get_buffer().raw                                  # TextMode art instead of HumanMode
