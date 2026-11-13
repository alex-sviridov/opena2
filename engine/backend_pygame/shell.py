"""The shell's window and loop (docs/engine/shell.md 5): pygame events -> `engine.shell` events, the screen's `Scene` painted with the game's
bitmaps, fonts and cursor, the music / sound services on the audio backend, and the in-game screen's loop handed to `window.run`.

`render_scene(surface, scene, art, ...)` paints one scene (also used headless by the goldens: `screenshot`)."""

import argparse
import logging
import sys

import pygame

from engine.audio import settings as settings_mod
from engine.shell import Services, Shell
from engine.ui import CursorState

from .cursor import CursorSprites, draw_cursor, hide_os_cursor
from .shellkit import KEY_NAMES, Painter, key_event, render_scene, to_shell_event  # noqa: F401
from .window import ensure_display

log = logging.getLogger("allods2.shell")


def screenshot(shell, painter=None, cursor=None, mouse=None):
    """The (h, w, 3) pixels of the shell's current screen, headless: what the window would show (the cursor only when `cursor` sprites and a `mouse` are given)."""
    return scene_screenshot(shell.scene(), shell.size, painter or Painter(shell.fs), cursor, mouse)


def scene_screenshot(scene, size, painter, cursor=None, mouse=None):
    """The (h, w, 3) pixels of `scene` on a black screen of `size` (the options pages use it too)."""
    from .render import surface_rgb
    surf = ensure_display(*size)
    render_scene(surf, scene, painter)
    if scene.cursor and cursor is not None and mouse is not None:
        draw_cursor(surf, cursor, CursorState.DEFAULT, mouse, 0)
    return surface_rgb(surf)


def make_services(a, audio, settings, parser_args=None):
    """The shell's services on the audio device (or none) and the settings file."""
    def sound(path):
        if audio is not None:
            audio.ui(path)

    def music(name):
        if audio is not None:
            audio.set_playlist(name)

    def apply(s):
        if audio is not None:
            audio.apply_settings(s.override(mute=True if getattr(a, "mute", False) else None))

    def save(s):
        settings_mod.save(s)
        apply(s)
    return Services(sound=sound, music=music, log=log.info, apply_settings=apply, save_settings=save)


class ShellGame:
    """What the game screen runs: a `PlaySession` with a World, played to its end."""

    def __init__(self, play, audio):
        self.play, self.audio, self.world = play, audio, play.world

    def run(self):
        play = self.play
        try:
            play.run()
        except KeyboardInterrupt as e:
            play.crash(e)
            return "quit"
        except Exception as e:                      # noqa: BLE001  a crashed mission goes back to the menu; the session files keep the traceback
            play.crash(e)
            return "menu"
        finally:
            play.finish()
            if self.audio is not None:
                self.audio.end_mission()
        if play.exit in (None, "windows"):
            return "quit"
        return play.exit if play.exit in ("victory", "defeat") else "menu"


def run(a, parser, PlaySession, make_audio, audio_settings):
    """`python -m engine`: the shell loop."""
    from allods2.assets import AssetCache
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    from engine.ui import Layout
    try:
        Layout.for_size(*a.size)
    except ValueError as e:
        parser.error(str(e))
    assets = AssetCache(a.install)
    stored = settings_mod.load()
    audio = make_audio(a, assets)
    screen = ensure_display(*a.size)
    pygame.display.set_caption("Allods 2")
    hide_os_cursor()
    services = make_services(a, audio, stored)

    def start_game(params):
        ns = argparse.Namespace(**vars(a))
        camp = params.get("campaign")
        if camp is not None:                                # a campaign mission: the carried party, the campaign's variables (campaign.md)
            ns.map, ns.difficulty, ns.seed = str(params["mission"]), camp.difficulty, camp.seed
            ns.hero_name = camp.roster[0].spec.name if camp.roster and camp.roster[0].spec and camp.roster[0].spec.name else a.hero_name
            ns.campaign_snapshot = camp.snapshot()                  # before the mission starts: the session files can replay it
            ns.prebuilt = camp.start_mission(params["mission"])
        else:
            ns.map, ns.difficulty = params["map"], params["difficulty"]
            ns.hero_name = params.get("name") or a.hero_name
        ns.speed, ns.settings = a.speed, stored             # None = the settings file's game speed
        play = PlaySession(ns, parser, assets, audio, in_shell=True)
        play.option_services = services
        log.info("new game: map %s, difficulty %s, hero %s (%s)", ns.map, ns.difficulty, params.get("hero"), ns.hero_name)
        return ShellGame(play.start(), audio)
    services.start_game = start_game
    shell = Shell(assets.fs, a.size, stored, services)
    painter, cursors = Painter(assets.fs), CursorSprites(assets.fs)
    clock = pygame.time.Clock()
    shell.start("startup" if a.start == "startup" else "menu")
    while not shell.done:
        dt = clock.tick(60)
        for ev in pygame.event.get():
            if audio is not None and audio.handle_event(ev):
                continue
            if ev.type == pygame.QUIT:
                shell.close_window()
                break
            se = to_shell_event(ev)
            if se is not None:
                shell.handle(se)
        if shell.done:
            break
        shell.update(dt)
        cur = shell.current
        if cur.driven:
            shell.apply(cur.run())
            continue
        mouse = pygame.mouse.get_pos() if pygame.mouse.get_focused() else None
        render_scene(screen, shell.scene(), painter)
        if shell.scene().cursor:
            draw_cursor(screen, cursors, CursorState.DEFAULT, mouse, pygame.time.get_ticks())
        pygame.display.flip()
    if audio is not None:
        audio.close()
    pygame.quit()
    return 0
