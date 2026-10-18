"""The interface frame: panel blits from the `Layout`, the info panel, bars of the minimap column
(docs/engine/ui-layout.md sections 1-4, 10)."""

import numpy as np
import pygame

from allods2.graphics.bmp import load_bmp

from .render import draw_frame, draw_numbers
from .text import draw_text

INFO_TEXT = (255, 255, 255)
MESSAGE_COLOUR = (192, 192, 192)    # text slot 0x5f17f4 = table 0x61fa80 "grey 17i": INFERRED RGB
MESSAGE_POS = (8, 8)
BALL = "graphics/interface/Ball.bmp"


def selection_state(world, player_id):
    """'none' | 'own' | 'foreign' for the player's selection (view+0x140 / +0x144)."""
    if not world.players[player_id].selection:
        return "none"
    return "foreign" if world.selection_is_foreign(player_id) else "own"


def rgb_surface(rgb):
    h, w = rgb.shape[:2]
    return pygame.image.frombuffer(np.ascontiguousarray(rgb).tobytes(), (w, h), "RGB")


class InterfaceArt:
    """Panel bitmaps of the game file system as surfaces, loaded on first use (no colour key)."""

    def __init__(self, fs):
        self.fs = fs
        self._d = {}

    def get(self, path):
        if path not in self._d:
            try:
                surf = rgb_surface(load_bmp(path, self.fs).rgb)
                if pygame.display.get_surface() is not None:
                    surf = surf.convert()
            except (KeyError, OSError, ValueError):
                surf = None
            self._d[path] = surf
        return self._d[path]


class Interface:
    """Black window, viewport, strips and panels from `layout`.  `draw` renders one frame;
    the cursor is drawn by the caller afterwards."""

    def __init__(self, layout, art):
        self.layout, self.art = layout, art
        self.view = pygame.Surface((layout.viewport.w, layout.viewport.h))

    def blit(self, window, rect, path):
        img = self.art.get(path)
        if img is not None:
            window.blit(img, (rect.x, rect.y))

    def draw(self, window, caches, terrain_items, items, camera, world, player_id, minimap=None, panel=None,
             unit_title=None, message=None, numbers=()):
        """Compose the whole window.  `minimap`: engine.view.Minimap (image drawn at `panel`'s
        position), `unit_title(unit) -> str` for the info panel."""
        lay = self.layout
        if caches.ball is None:
            caches.ball = self.art.get(BALL)
        window.fill((0, 0, 0))
        draw_frame(self.view, caches, terrain_items, items, camera)
        if numbers:
            draw_numbers(self.view, numbers)                # floating damage: over the units, under the panels
        window.blit(self.view, (lay.viewport.x, lay.viewport.y))
        state = selection_state(world, player_id)
        for strip in lay.strips:
            path = strip.graphics[0]
            if strip is lay.strip_b:
                path = lay.bar_graphics(state)[0]
            self.blit(window, strip.rect, path)
        self.blit(window, lay.crystal.rect, lay.crystal.graphics[0])
        self.blit(window, lay.bar_panel.rect, lay.bar_graphics(state)[1])
        self.blit(window, lay.info_panel.rect, lay.info_panel.graphics[0])
        if lay.extra_panel:
            self.blit(window, lay.extra_panel.rect, lay.extra_panel.graphics[0])
        if minimap is not None and panel is not None:
            img = minimap.image(camera)
            window.blit(rgb_surface(img), (panel.left, panel.top))
        self.draw_info(window, world, player_id, unit_title)
        if message:
            self.draw_message(window, *message)

    def draw_message(self, window, text, colour=MESSAGE_COLOUR):
        """The message line: top strip of the view (0, 0, W-160, 30), purpose INFERRED (ui-layout.md section 1)."""
        draw_text(window, text, MESSAGE_POS[0], MESSAGE_POS[1], colour)

    def draw_info(self, window, world, player_id, unit_title=None):
        """Info panel texts (ui-layout.md section 10; DECISIONs in the design spec)."""
        sel = world.players[player_id].selection
        r = self.layout.info_panel.rect
        if not sel:
            return
        if len(sel) > 1:
            draw_text(window, "%d units" % len(sel), r.x + r.w - 88, r.y + 0x1c, INFO_TEXT, "center")
            return
        u = world.units[sel[0]]
        title = unit_title(u) if unit_title else "unit %d" % u.type_id
        draw_text(window, title, r.x + r.w - 88, r.y + 0x1c, INFO_TEXT, "center")
        draw_text(window, "HP", r.x + 0x73, r.y + 0x2c, INFO_TEXT)
        draw_text(window, "%d/%d" % (u.hp, u.hp_max), r.x + 0x73, r.y + 0x36, INFO_TEXT)
        owner = world.players.get(u.owner)
        if owner is not None:
            draw_text(window, owner.name, r.x + 6, r.y + 0xe0, INFO_TEXT)


def unit_title_fn(assets):
    """Unit title: the units.reg `DescText` key until text tables exist (DECISION)."""
    def title(u):
        t = assets.unit_types().get(u.type_id)
        return str(t.values.get("DescText") or "unit %d" % u.type_id) if t is not None else "unit %d" % u.type_id
    return title


def screenshot_window(terrain_view, camera, layout, tick, dest, assets, options=None, debug=None,
                      select=(), player_id=1, minimap=True):
    """Render the whole interface window headless (no cursor), save a PNG when `dest`, return the
    (h, w, 3) pixels.  `select`: unit ids selected through the selection system before drawing."""
    import os

    from allods2.common import as_fs
    from allods2.graphics import write_png
    from allods2.minimap import load_color_table, load_dot_colors
    from engine.sim import SelectUnits, selection_system
    from engine.view import Minimap, build_draw_list, build_terrain_items

    from .render import Caches, surface_rgb
    from .sprites import SpriteCache
    from .surfaces import SurfaceCache
    from .window import ensure_display
    world = terrain_view.world
    window = ensure_display(*layout.size)
    if select:
        selection_system(world, [SelectUnits(player_id, tuple(select))])
    items = build_draw_list(world, camera, tick, assets, options, debug, world.players[player_id].selection)
    fs = as_fs(assets.fs)
    mm = panel = None
    if minimap:
        from engine.ui import MinimapPanel
        mm = Minimap(world, load_color_table(fs), load_dot_colors(fs))
        panel = MinimapPanel.from_layout(mm.geometry, layout)
    ui = Interface(layout, InterfaceArt(assets.fs))
    caches = Caches(SurfaceCache(terrain_view), SpriteCache(assets))
    ui.draw(window, caches, build_terrain_items(terrain_view, camera, tick), items, camera, world, player_id,
            mm, panel, unit_title_fn(assets))
    rgb = surface_rgb(window)
    if dest:
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        write_png(dest, rgb)
    return rgb
