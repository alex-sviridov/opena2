"""Shell scenes for the goldens (`golden.json["shell"]`) and the tests: a headless `Shell` driven by scripted events, one screenshot per screen.
Shared by `tools/update_golden.py` and `tests/test_engine_shell*.py`."""

import hashlib

import numpy as np

from allods2.common import as_fs
from engine.shell import Move, Press, Release, Services, Shell



def hash_rgb(rgb):
    return hashlib.sha256(np.ascontiguousarray(rgb).tobytes()).hexdigest()


class Recorder:
    """The services of a headless run: every sound, playlist, log line and saved settings object is kept."""

    def __init__(self):
        self.sounds, self.music, self.lines, self.saved, self.starts, self.applied = [], [], [], [], [], []
        self.services = Services(sound=self.sounds.append, music=self.music.append, log=self.lines.append,
                                 save_settings=lambda s: self.saved.append(vars(s).copy()), apply_settings=lambda s: self.applied.append(vars(s).copy()), start_game=self.start_game)

    def start_game(self, params):
        self.starts.append(params)
        return FakeGame()


class FakeGame:
    world = None

    def run(self):
        return "menu"


def make_shell(install, size=(640, 480), settings=None, rec=None):
    rec = rec or Recorder()
    return Shell(as_fs(install), size, settings, rec.services), rec


def button_centre(shell, n):
    """A screen point inside main-menu button `n` (the middle pixel of its hit-mask region)."""
    menu = shell.screens["menu"]
    menu._load()
    ys, xs = np.where(menu.mask == 0x80 + 0x10 * n)
    ox, oy = menu.origin
    return ox + int(np.median(xs)), oy + int(np.median(ys))


def click(shell, pos):
    shell.handle(Move(*pos))
    shell.handle(Press(*pos))
    shell.handle(Release(*pos))


def mask_centre(shell, mask, value):
    ys, xs = np.where(mask == value)
    ox, oy = shell.current.origin
    return ox + int(np.median(xs)), oy + int(np.median(ys))


def to_menu(shell):
    shell.start()
    shell.update(16)
    assert shell.name == "menu"


def shell_golden(install):
    """{name: sha256} of the shell's screens at 640x480 (and the menu at 800x600): every picture the shell shows without a game."""
    from engine.backend_pygame import shell as backend
    out = {}
    sh, rec = make_shell(install)
    art = backend.Painter(sh.fs)
    shot = lambda name: out.__setitem__(name, hash_rgb(backend.screenshot(sh, art)))
    sh.start()
    shot("startup")
    sh.update(16)
    shot("menu")
    sh.handle(Move(*button_centre(sh, 0)))
    shot("menu_hover_new")
    sh.handle(Press(*button_centre(sh, 0)))
    shot("menu_held_new")
    sh.handle(Move(*button_centre(sh, 4)))
    sh.handle(Release(*button_centre(sh, 4)))
    shot("menu_disabled_load")
    sh.handle(Move(*button_centre(sh, 7)))
    shot("menu_hover_exit")
    sh.go("newgame")
    shot("newgame")
    mask = sh.current.mask
    sh.handle(Move(*mask_centre(sh, mask, 100)))
    shot("newgame_hero_hover")
    click(sh, mask_centre(sh, mask, 100))
    click(sh, mask_centre(sh, mask, 60))
    shot("newgame_hero_hard")
    sh.handle(Move(*mask_centre(sh, mask, 180)))
    shot("newgame_ok_hover")
    sh.go("chargen", difficulty=2, hero=0, hero_code=0, name="Aldor")
    shot("chargen")
    for who, i in (("minus", 0), ("plus", 3), ("minus", 1)):
        click(sh, chargen_centre(sh, who, i))
    sh.handle(Move(*chargen_centre(sh, "plus", 2)))
    shot("chargen_changed")
    sh.go("newgame")
    sh.go("chargen", difficulty=2, hero=3, hero_code=0x40, name="Gildarius")
    sh.handle(Move(*chargen_centre(sh, "class", 2)))
    click(sh, chargen_centre(sh, "class", 2))
    shot("chargen_mage_air")
    sh.go("newgame")
    sh.go("menu")
    from engine.audio.settings import Settings
    from engine.shell.options import OptionsPages, load_texts
    texts = load_texts(sh.fs)
    pages = OptionsPages(texts, sh.size, Settings(), rec.services, "game")
    shotp = lambda name: out.__setitem__(name, hash_rgb(backend.scene_screenshot(pages.scene(), sh.size, art)))
    shotp("options_game")
    pages.draft.smoothing, pages.draft.game_speed = False, 7
    pages.event(Move(*opt_centre(pages, "lighting")))
    shotp("options_game_hover")
    pages = OptionsPages(texts, sh.size, Settings(), rec.services, "sound")
    shotp("options_sound")
    sh2, _ = make_shell(install, (800, 600))
    sh2.start()
    sh2.update(16)
    sh2.handle(Move(*button_centre(sh2, 3)))
    out["menu_800_hover_credits"] = hash_rgb(backend.screenshot(sh2, art))
    return out


def chargen_centre(shell, kind, i):
    """A screen point on the character generator's stat button (`plus` / `minus`, row i) or on class column i."""
    from engine.shell import chargen as cg
    ox, oy = shell.current.origin
    if kind == "class":
        return ox + cg.MASK[shell.current.kind][i][1] + 20, oy + cg.MASK[shell.current.kind][i][2] + 12
    x = cg.PLUS_X if kind == "plus" else cg.MINUS_X
    return ox + x + 10, oy + cg.ROW_Y + 32 * i + 10


def opt_centre(pages, key):
    """Centre of the options widget with settings field / action `key` on the page shown."""
    w = next(w for w in pages.widgets() if w.key == key)
    r = pages.screen_rect(w)
    return r.x + r.w // 2, r.y + r.h // 2
