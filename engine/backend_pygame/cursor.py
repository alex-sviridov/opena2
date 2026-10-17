"""The game's cursors: frames of `allods2.anim.load_cursor_set`, hidden OS cursor, drawn last."""

import numpy as np
import pygame


class CursorSprites:
    """`fs`: the game file system.  `surface_at(name, ms)` -> (Surface, hot x, hot y), or None."""

    def __init__(self, fs):
        self.fs = fs
        self._sets = {}
        self._frames = {}

    def _set(self, name):
        if name not in self._sets:
            from allods2.anim import load_cursor_set
            try:
                self._sets[name] = load_cursor_set(name, self.fs)
            except (KeyError, OSError):
                self._sets[name] = None
        return self._sets[name]

    def surface_at(self, name, ms):
        cs = self._set(name)
        if cs is None:
            return None
        ref = cs.frame_at("cursor", 0, ms)
        key = (name, ref.index)
        if key not in self._frames:
            sf = cs.sprites(ref.source)
            if sf is None or not 0 <= ref.index < len(sf):
                self._frames[key] = None
            else:
                rgba = sf.to_rgba(ref.index)
                h, w = rgba.shape[:2]
                surf = pygame.image.frombuffer(np.ascontiguousarray(rgba).tobytes(), (w, h), "RGBA")
                if pygame.display.get_surface() is not None:
                    surf = surf.convert_alpha()
                self._frames[key] = surf
        surf = self._frames[key]
        return None if surf is None else (surf, *cs.hot)


def hide_os_cursor():
    pygame.mouse.set_visible(False)


def draw_cursor(surface, sprites, state, mouse, ms):
    """Blit the cursor of `state` (a CursorState) at `mouse - hotspot`; nothing when the pointer is outside."""
    if mouse is None:
        return
    got = sprites.surface_at(state.cursor_name, ms)
    if got is not None:
        img, hx, hy = got
        surface.blit(img, (mouse[0] - hx, mouse[1] - hy))
