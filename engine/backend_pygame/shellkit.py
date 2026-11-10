"""What the shell and the in-game options window draw and read with (docs/engine/shell.md): pygame events -> shell events, `Painter`, `render_scene`.
No window handling here (`engine.backend_pygame.shell` owns the loop)."""

import numpy as np
import pygame

from allods2.graphics import SpriteFile
from engine.shell import Button, Fill, Frame, Image, Key, Move, Press, Release, Sprite, Text
from engine.ui.layout import Rect
from engine.ui.modal import DButton

from .interface import InterfaceArt
from .panels import Panels, surface_from_rgba
from .text import draw_text_exact

KEY_NAMES = {pygame.K_ESCAPE: "escape", pygame.K_RETURN: "return", pygame.K_KP_ENTER: "return", pygame.K_TAB: "tab",
             pygame.K_LEFT: "left", pygame.K_RIGHT: "right", pygame.K_UP: "up", pygame.K_DOWN: "down", pygame.K_SPACE: "space",
             pygame.K_BACKSPACE: "backspace"}


def key_event(ev):
    """pygame KEYDOWN -> `Key`; None for a key the shell has no name for."""
    name = KEY_NAMES.get(ev.key) or (chr(ev.key) if 32 < ev.key < 127 else "")
    char = getattr(ev, "unicode", "") or ""
    if char and (ord(char[0]) < 32 or ord(char[0]) == 127):
        char = ""
    return Key(name, bool(ev.mod & pygame.KMOD_CTRL), char[:1]) if (name or char) else None


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

    def __init__(self, fs):
        self.art = InterfaceArt(fs)
        self.panels = Panels(fs, None)
        self.fs = fs
        self._files, self._frames = {}, {}

    def sprite(self, path, frame, shadow=0):
        key = (path, frame, shadow)
        if key not in self._frames:
            if path not in self._files:
                self._files[path] = SpriteFile.load(path, self.fs)
            rgba = np.array(self._files[path].to_rgba(frame))
            if shadow:
                rgba[..., :3] = 0
                rgba[..., 3] = (rgba[..., 3].astype(np.int32) * shadow // 16).astype(np.uint8)       # black at `level / 16` = the darken blit's `dst * (16 - level) / 16`
            self._frames[key] = surface_from_rgba(rgba)
        return self._frames[key]


def render_scene(surface, scene, painter, clear=True):
    """Paint `scene` on `surface` (black first unless `clear` is False: a window over a backdrop) with `painter`: bitmaps, frames, buttons, sprites and the game's fonts."""
    if clear:
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
            surface.blit(painter.sprite(op.path, op.frame, op.shadow), (op.x, op.y))
