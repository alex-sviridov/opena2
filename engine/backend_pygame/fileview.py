"""The mission menu's Save / Load windows (docs/engine/save-ui.md; `0x41a` / `0x418`): the modal sub-loop `window.run` starts when the menu asks for one.  The game is
frozen, the last frame stays as the backdrop, the shell's `SaveDialog` / `LoadDialog` (over the shell's slot folder) is drawn over it."""

import pygame

from engine.shell import saveload as SL
from engine.ui import CursorState

from .cursor import CursorSprites, draw_cursor
from .shellkit import Painter, render_scene, to_shell_event


def run_file_dialog(kind, screen, backdrop, shell, painter=None, cursors=None, audio=None):
    """Run the `kind` ("save" / "load") window until it closes.  Returns `(result, closed)`: `result` = `("save", file, description)`, `("load", file)` or `None` (Cancel / ESC),
    `closed` True when the OS window was closed meanwhile.  A Save whose write fails keeps the window open with the notice (as the town scene's menu does)."""
    painter = painter or Painter(shell.fs)
    cursors = cursors or CursorSprites(shell.fs)
    dialog = (SL.SaveDialog if kind == "save" else SL.LoadDialog)(shell, shell.slots)
    clock = pygame.time.Clock()
    result, closed = None, False
    while True:
        dt = clock.tick(60)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return None, True
            if audio is not None and audio.handle_event(ev):
                continue
            se = to_shell_event(ev)
            if se is None:
                continue
            out = dialog.event(se)
            if out is None:
                continue
            if out[0] == "close":
                return None, closed
            if out[0] == "save":
                err = shell.save_mission(shell.mission_session, out[1], out[2], shell.mission_state())
                if err is None:
                    return out, closed
                dialog.notice(err)
            else:
                return out, closed
        dialog.update(dt)
        screen.blit(backdrop, (0, 0))
        render_scene(screen, SL.Scene(dialog.scene_ops()), painter, clear=False)
        draw_cursor(screen, cursors, CursorState.DEFAULT, pygame.mouse.get_pos() if pygame.mouse.get_focused() else None, pygame.time.get_ticks())
        pygame.display.flip()
