"""The shell's window and loop (docs/engine/shell.md 5): pygame events -> `engine.shell` events, the screen's `Scene` painted with the game's
bitmaps, fonts and cursor, the music / sound services on the audio backend, and the in-game screen's loop handed to `window.run`.

`render_scene(surface, scene, art, ...)` paints one scene (also used headless by the goldens: `screenshot`)."""

import argparse
import logging
import sys

import numpy as np
import pygame

from engine.audio import settings as settings_mod
from allods2.graphics import SpriteFile
from engine.shell import Button, Fill, Frame, Image, Key, Move, Press, Release, Services, Shell, Sprite, Text
from engine.ui import CursorState
from engine.ui.layout import Rect
from engine.ui.modal import DButton

from .cursor import CursorSprites, draw_cursor, hide_os_cursor
from .interface import InterfaceArt
from .panels import Panels, surface_from_rgba
from .text import draw_text_exact
from .window import ensure_display

log = logging.getLogger("allods2.shell")
KEY_NAMES = {pygame.K_ESCAPE: "escape", pygame.K_RETURN: "return", pygame.K_KP_ENTER: "return", pygame.K_TAB: "tab",
             pygame.K_LEFT: "left", pygame.K_RIGHT: "right", pygame.K_UP: "up", pygame.K_DOWN: "down", pygame.K_SPACE: "space",
             pygame.K_BACKSPACE: "backspace"}


def key_event(ev):
    """pygame KEYDOWN -> `Key`; None for a key the shell has no name for."""
    name = KEY_NAMES.get(ev.key) or (chr(ev.key) if 32 < ev.key < 127 else "")
    return Key(name, bool(ev.mod & pygame.KMOD_CTRL)) if name else None


def to_shell_event(ev):
    """One pygame event -> a shell event, or None."""
    if ev.type == pygame.MOUSEMOTION:
        return Move(*ev.pos)
    if ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3):
        return Press(ev.pos[0], ev.pos[1], ev.button)
    if ev.type == pygame.MOUSEBUTTONUP and ev.button in (1, 3):
        return Release(ev.pos[0], ev.pos[1], ev.button)
    if ev.type == pygame.KEYDOWN:
        return key_event(ev)
    return None


class Painter:
    """Everything `render_scene` draws with: the bitmaps (`InterfaceArt`), the dialog frames and buttons (`Panels`), `.256` sprite frames as surfaces."""

    SHADOW_ALPHA = 128

    def __init__(self, fs):
        self.art = InterfaceArt(fs)
        self.panels = Panels(fs, None)
        self.fs = fs
        self._files, self._frames = {}, {}

    def sprite(self, path, frame, shadow=False):
        key = (path, frame, shadow)
        if key not in self._frames:
            if path not in self._files:
                self._files[path] = SpriteFile.load(path, self.fs)
            rgba = np.array(self._files[path].to_rgba(frame))
            if shadow:
                rgba[..., :3] = 0
                rgba[..., 3] = rgba[..., 3] // 2
            self._frames[key] = surface_from_rgba(rgba)
        return self._frames[key]


def render_scene(surface, scene, painter):
    """Paint `scene` on `surface` (black first) with `painter`: bitmaps, frames, buttons, sprites and the game's fonts."""
    surface.fill((0, 0, 0))
    for op in scene.ops:
        if isinstance(op, Image):
            img = painter.art.get(op.path)
            if img is not None:
                surface.blit(img, (op.x, op.y))
        elif isinstance(op, Fill):
            surface.fill(op.rgb, (op.x, op.y, op.w, op.h))
        elif isinstance(op, Text):
            draw_text_exact(surface, op.text, op.x, op.y, op.table, op.flags, op.font, op.shadow)
        elif isinstance(op, Frame):
            surface.blit(painter.panels.frame_surface(op.w - 8, op.h - 8), (op.x, op.y))
        elif isinstance(op, Button):
            painter.panels.draw_button(surface, DButton(Rect(op.x, op.y, op.w, op.h), op.label, op.enabled, ("noop",)), op.hover, op.pressed)
        elif isinstance(op, Sprite):
            if op.shadow:
                surface.blit(painter.sprite(op.path, op.frame, True), (op.x + 5, op.y + 4))
            surface.blit(painter.sprite(op.path, op.frame), (op.x, op.y))


def screenshot(shell, painter=None, cursor=None, mouse=None):
    """The (h, w, 3) pixels of the shell's current screen, headless: what the window would show (the cursor only when `cursor` sprites and a `mouse` are given)."""
    from .render import surface_rgb
    surf = ensure_display(*shell.size)
    painter = painter or Painter(shell.fs)
    scene = shell.scene()
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
        return "quit" if play.exit in (None, "windows") else "menu"


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
        ns.map, ns.difficulty = params["map"], params["difficulty"]
        ns.hero_name = params.get("name") or a.hero_name
        ns.speed, ns.settings = a.speed, stored             # None = the settings file's game speed
        play = PlaySession(ns, parser, assets, audio, in_shell=True)
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
