"""The in-game options windows (docs/engine/shell.md 5): the modal sub-loop `window.run` starts when the menu asks for Game Options (`0x41b`) or Sound Options
(`0x422`).  The game is frozen (nothing steps), the last frame stays as the backdrop, the shell's `OptionsPages` is drawn over it with the game's own widgets."""

import pygame

from engine.audio import settings as settings_mod
from engine.shell import Services
from engine.shell.options import OptionsPages, load_texts
from engine.ui import CursorState

from .cursor import CursorSprites, draw_cursor
from .shellkit import Painter, render_scene, to_shell_event


def default_services(audio, mute=None):
    """Sound / apply / save on the audio backend and the settings file (the shell passes its own with the command-line overrides)."""
    def apply(s):
        if audio is not None and hasattr(audio, "apply_settings"):
            audio.apply_settings(s.override(mute=True if (mute if mute is not None else audio.settings.mute) else None))

    def save(s):
        settings_mod.save(s)
        apply(s)
    return Services(sound=(lambda x: audio.ui(x)) if audio is not None else (lambda x: None), apply_settings=apply, save_settings=save)


def run_options(page, screen, backdrop, settings, services, fs, painter=None, cursors=None, audio=None):
    """Run the `page` ("game" / "sound") window until it closes; returns `(result, closed)`: `result` ok / cancel / return, `closed` True when the OS window was closed meanwhile."""
    painter = painter or Painter(fs)
    cursors = cursors or CursorSprites(fs)
    pages = OptionsPages(load_texts(fs), screen.get_size(), settings, services, page)
    clock = pygame.time.Clock()
    closed = False
    while not pages.done:
        clock.tick(60)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                closed = True
                pages.close("cancel" if page == "game" else "return")
                break
            if audio is not None and audio.handle_event(ev):
                continue                                    # the music track ended: the next one started
            se = to_shell_event(ev)
            if se is not None:
                pages.event(se)
        screen.blit(backdrop, (0, 0))
        render_scene(screen, pages.scene(), painter, clear=False)
        draw_cursor(screen, cursors, CursorState.DEFAULT, pygame.mouse.get_pos() if pygame.mouse.get_focused() else None, pygame.time.get_ticks())
        pygame.display.flip()
    return pages.result, closed
