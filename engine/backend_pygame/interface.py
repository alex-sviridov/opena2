"""The interface frame: panel blits from the `Layout`, the info panel, bars of the minimap column
(docs/engine/ui-layout.md sections 1-4, 10)."""

import numpy as np
import pygame

from allods2.graphics.bmp import load_bmp

from .render import draw_frame, draw_numbers, surface_rgb
from .panels import Panels
from .text import draw_text, game_font

INFO_TEXT = (255, 255, 255)
MESSAGE_COLOUR = "highlight"        # text slot 0x5f17f4 = table 0x61fa80 (17i, 17i, 17i): CONFIRMED (palettes.md 6, `FUN_0040261a` list colour)
MESSAGE_POS = (8, 8)                # `FUN_0040261a` 0x402640 / 0x402647 (game mode 2; mode 3: (0, 0xdc))
MESSAGE_FONT = 1                    # `ds:0x61fac0` = font1 (fonts.md); mode 3 uses font2
MESSAGE_GAP = 2                     # pitch = font height + 2 (`FUN_0040261a` 0x40278e)
BALL = "graphics/interface/Ball.bmp"


def message_pitch():
    """Pixels between two message lines: the height of font1 plus 2 (`FUN_00402a90`, `0x40278e`)."""
    f = game_font(MESSAGE_FONT)
    return (f.cell_height() if f is not None else 15) + MESSAGE_GAP


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

    def __init__(self, layout, art, fs=None):
        self.layout, self.art = layout, art
        self.view = pygame.Surface((layout.viewport.w, layout.viewport.h))
        self._fs, self._panels = fs, None

    @property
    def panels(self):
        if self._panels is None:
            self._panels = Panels(self._fs if self._fs is not None else self.art.fs, self.layout)
        return self._panels

    def blit(self, window, rect, path):
        img = self.art.get(path)
        if img is not None:
            window.blit(img, (rect.x, rect.y))

    def draw(self, window, caches, terrain_items, items, camera, world, player_id, minimap=None, panel=None,
             unit_title=None, message=None, numbers=(), hover=None, ui=None, cells=(), mouse=None, info_picture=None, tooltip=None, book=None, pack=None):
        """Compose the whole window.  `minimap`: engine.view.Minimap (image drawn at `panel`'s position), `ui`: the `engine.ui.GameUi` (info panel
        mode, dialogs; None = no panel contents), `cells`: `engine.ui.bar.cells(...)` of the command bar, `message`: the live message entries
        (text or (text, colour)), `info_picture(unit)`: the units.reg `InfoPicture` name, `tooltip`: the shown `engine.ui.tooltip.Tip` (drawn last),
        `book`: the `SlotView`s of the open spell book (`engine.ui.book.draw_views`), None when it is closed, `pack`: the `PackView` of the open backpack
        window (`ui.pack.views`), None when it is closed."""
        lay = self.layout
        if caches.ball is None:
            caches.ball = self.art.get(BALL)
        window.fill((0, 0, 0))
        draw_frame(self.view, caches, terrain_items, items, camera, world)
        if numbers:
            draw_numbers(self.view, numbers)                # floating damage: over the units, under the panels
        window.blit(self.view, (lay.viewport.x, lay.viewport.y))
        state = selection_state(world, player_id)
        text_mode = ui is not None and ui.shown_mode == "text"
        for strip in lay.strips:
            path = strip.graphics[0]
            if strip is lay.strip_b:
                path = lay.bar_graphics(state)[0]
            elif strip is lay.strip_c and text_mode:
                path = strip.graphics[1]
            self.blit(window, strip.rect, path)
        self.blit(window, lay.crystal.rect, lay.crystal.graphics[0])
        self.blit(window, lay.bar_panel.rect, lay.bar_graphics(state)[1])
        self.blit(window, lay.info_panel.rect, lay.info_panel.graphics[1 if text_mode else 0])
        if lay.extra_panel:
            if lay.extra_text is not None:
                self.blit(window, lay.extra_text, "graphics/interface/TextBackR.bmp")
            self.blit(window, lay.extra_panel.rect, lay.extra_panel.graphics[0])
        if minimap is not None and panel is not None:
            bg = None
            if world.fog is not None:                       # unseen blocks show the panel picture under the image (vision.md 3)
                g = minimap.geometry
                bg = surface_rgb(window.subsurface((panel.left, panel.top, g.width, g.height)))
            img = minimap.image(camera, bg)
            window.blit(rgb_surface(img), (panel.left, panel.top))
        if ui is not None:
            self.panels.draw_bar(window, cells)
            self.panels.draw_info(window, ui, world, player_id, hover, info_picture)
            self.panels.draw_extra(window, ui, world, player_id, hover)
        if book is not None and ui is not None:
            self.panels.draw_book(window, ui.book, book)
        if pack is not None and ui is not None:
            self.panels.draw_pack(window, ui, pack, ui.main, mouse)
        if message:
            self.draw_message(window, message)
        if ui is not None and ui.frozen:
            self.panels.draw_dialogs(window, ui, mouse, info_picture)
        if tooltip is not None:
            self.panels.draw_tooltip(window, tooltip)

    def draw_message(self, window, lines, colour=MESSAGE_COLOUR):
        """The message list (`FUN_0040261a`): the live lines top-down from (8, 8) of the view, `font height + 2` apart, font1, shadowed.  An entry is a
        text or a `(text, colour)` pair (colour None = the default system slot)."""
        pitch = message_pitch()
        for i, line in enumerate(lines):
            text, col = (line, None) if isinstance(line, (str, bytes)) else line
            draw_text(window, text, MESSAGE_POS[0], MESSAGE_POS[1] + i * pitch, col or colour, font=MESSAGE_FONT)


def unit_title_fn(assets):
    """Unit title: the units.reg `DescText` key (kept for tools; the info panel uses unitname.txt now)."""
    def title(u):
        t = assets.unit_types().get(u.type_id)
        return str(t.values.get("DescText") or "unit %d" % u.type_id) if t is not None else "unit %d" % u.type_id
    return title


def info_picture_fn(assets):
    """`unit -> units.reg InfoPicture name or None` (`graphics/infowindow/<name>[face].bmp`, ui-layout 11.1)."""
    def pic(u):
        t = assets.unit_types().get(u.type_id)
        v = t.values.get("InfoPicture") if t is not None else None
        return str(v) if v else None
    return pic


def message_line(layout):
    """The view's message list: wrapped to the view width in font1, at most `(view height / (font height + 2)) / 2` lines
    (`FUN_0040212b` 0x40219e-0x4021c3)."""
    from allods2.text import font_bytes

    from engine.ui import MessageLine
    font, rect = game_font(1), layout.viewport
    wrap = None if font is None else (lambda t: font.wrap(font_bytes(t), rect.w))       # lines are font bytes: draw_text takes them as they are
    return MessageLine(max_lines=(rect.h // message_pitch()) // 2, wrap=wrap)


def font1_wrap():
    """`wrap(text, width_px) -> [font bytes]` in font1 for the dialog text windows (None without an install: the UI then counts paragraphs)."""
    from allods2.text import font_bytes
    font = game_font(1)
    return None if font is None else (lambda text, width: font.wrap(font_bytes(text), width))


def make_game_ui(assets, layout, world, player_id=1, mission_id=None, trace=False, hero_name="Hero", messages=None):
    """The `engine.ui.GameUi` of a game: main.txt, dialogs.txt, unitname.txt and the map's `mission<id>.txt` read from the install."""
    from allods2.common import as_fs
    from allods2.text import decode_text

    from engine.ui import GameUi, MainText
    fs = as_fs(assets.fs)
    mission = None
    if mission_id is not None:
        try:
            mission = decode_text(fs.read("main/text/mission%s.txt" % mission_id))
        except (OSError, KeyError, FileNotFoundError):
            mission = None
    return GameUi(layout, world, player_id, MainText.load(fs), MainText.load(fs, "main/text/dialogs.txt"),
                  MainText.load(fs, "main/text/unitname.txt"), mission, trace, hero_name,
                  messages if messages is not None else message_line(layout), wrap=font1_wrap(),
                  patch=MainText.load(fs, "patch/patch.txt"), building_names=MainText.load(fs, "main/text/building.txt"))


def screenshot_window(terrain_view, camera, layout, tick, dest, assets, options=None, debug=None,
                      select=(), player_id=1, minimap=True, ui=None, now_ms=0, hover=None, mouse=None, tooltip=None, cast_enabled=False, book=None, pack=None):
    """Render the whole interface window headless (no cursor), save a PNG when `dest`, return the
    (h, w, 3) pixels.  `select`: unit ids selected through the selection system before drawing.  `ui`: a prepared `GameUi` (panel mode, open
    dialogs, messages; default a fresh one); `now_ms`: the clock of the message line; `hover`: the hovered unit id, `tooltip`: a `engine.ui.tooltip.Tip` to draw, `book`: the open spell book's `SlotView`s, `pack`: the open backpack's `PackView`."""
    import os

    from allods2.common import as_fs
    from allods2.graphics import write_png
    from allods2.minimap import load_color_table, load_dot_colors, load_structure_sizes
    from engine.sim import SelectUnits, selection_system
    from engine.ui import bar
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
        mm = Minimap(world, load_color_table(fs), load_dot_colors(fs), load_structure_sizes(fs))
        panel = MinimapPanel.from_layout(mm.geometry, layout)
    ui = ui or make_game_ui(assets, layout, world, player_id)
    iface = Interface(layout, InterfaceArt(assets.fs))
    caches = Caches(SurfaceCache(terrain_view), SpriteCache(assets))
    state = selection_state(world, player_id)
    iface.draw(window, caches, build_terrain_items(terrain_view, camera, tick, items.lights), items, camera, world, player_id,
               mm, panel, None, ui.messages.entries(now_ms), (), hover, ui,
               bar.cells(state, cast_enabled, 0), mouse, info_picture_fn(assets), tooltip, book, pack)
    rgb = surface_rgb(window)
    if dest:
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        write_png(dest, rgb)
    return rgb
