"""J1 panels and dialogs drawn from the pure `engine.ui` readers (docs/engine/ui-layout.md 11): info panel with portrait, command bar
overlays, modal frames and buttons.  `Panels` owns the keyed art, the portrait cache and the cached dialog frames."""

import numpy as np
import pygame

from allods2.formats import itemdefs as idefs
from allods2.graphics import Canvas, SpriteFile, paperdoll
from allods2.graphics.bmp import load_bmp

from engine.ui import bar, book as book_mod, info, pack as pack_mod, story, tooltip
from engine.ui.widgets import INFO_BUTTONS, cell_rect

from .text import draw_text, draw_text_exact, game_font, measure

BEVEL_LIGHT, BEVEL_DARK = (0x29, 0x45, 0x3F), (7, 0x0C, 9)        # FUN_004d571a: top / left, bottom / right (swapped while pressed)
DISABLED_ALPHA = 48                                               # a disabled button is darkened by level 3 (`FUN_004d571a` -> `FUN_004564df(rect, 3)`): dst * 13 / 16
SHADOW_ALPHA = 96                                                 # lm.256 shadow: darken level 6 = dst * 10 / 16
SOURCE = {"book": (28, 37), "pack": (28, 30), "pack_open": (32, 31), "mode": (28, 32), "menu": (32, 32)}   # 11.1 source rects (the bitmaps are a little larger)
FRAME_SPRITES = "graphics/interface/lm.256"
KEY_RGB = (8, 4, 8)                                               # RGB565 zero (colour key `0x0000`): channels below these round to 0


def _rgba(rgb, keyed):
    h, w = rgb.shape[:2]
    a = np.full((h, w, 1), 255, np.uint8)
    if keyed:
        a[(rgb[..., 0] < KEY_RGB[0]) & (rgb[..., 1] < KEY_RGB[1]) & (rgb[..., 2] < KEY_RGB[2])] = 0
    return np.concatenate([rgb, a], axis=2)


def surface_from_rgba(arr):
    s = pygame.image.frombuffer(np.ascontiguousarray(arr).tobytes(), (arr.shape[1], arr.shape[0]), "RGBA")
    return s.convert_alpha() if pygame.display.get_surface() is not None else s


class Panels:
    def __init__(self, fs, layout):
        self.fs, self.layout = fs, layout
        self._keyed, self._opaque, self._portraits, self._frames, self._items, self._masks = {}, {}, {}, {}, {}, {}
        self._twinkle = None

    # -- art -----------------------------------------------------------------------------------------------------------------------
    def keyed(self, name):
        """`graphics/interface/<name>.bmp` with the 565 colour key (black is transparent), or None."""
        if name not in self._keyed:
            try:
                self._keyed[name] = surface_from_rgba(_rgba(load_bmp("graphics/interface/%s.bmp" % name, self.fs).rgb, True))
            except (KeyError, OSError, ValueError):
                self._keyed[name] = None
        return self._keyed[name]

    def opaque(self, name):
        if name not in self._opaque:
            try:
                rgb = load_bmp("graphics/interface/%s.bmp" % name, self.fs).rgb
                s = pygame.image.frombuffer(np.ascontiguousarray(rgb).tobytes(), (rgb.shape[1], rgb.shape[0]), "RGB")
                self._opaque[name] = s.convert() if pygame.display.get_surface() is not None else s
            except (KeyError, OSError, ValueError):
                self._opaque[name] = None
        return self._opaque[name]

    # -- info panel ----------------------------------------------------------------------------------------------------------------
    def portrait_surface(self, spec):
        """The 160x240 portrait of `info.portrait` output ('doll', [paths]) or ('bmp', path), black keyed; None when nothing can be drawn."""
        if spec is None:
            return None
        key = (spec[0], tuple(spec[1]) if spec[0] == "doll" else spec[1])
        if key in self._portraits:
            return self._portraits[key]
        surf = None
        if spec[0] == "bmp":
            try:
                surf = surface_from_rgba(_rgba(load_bmp(spec[1], self.fs).rgb, True))
            except (KeyError, OSError, ValueError):
                surf = None
        else:
            canvas = Canvas(160, 240)
            for path in spec[1]:
                try:
                    if path.endswith(".bmp"):
                        rgb = load_bmp(path, self.fs).rgb
                        m = rgb.any(axis=2)
                        canvas.pix[:rgb.shape[0], :rgb.shape[1]][m] = rgb[m]
                    else:
                        f = SpriteFile.load(path, self.fs)
                        canvas.draw_256(f.sprites[0], 0, 0, f.palette)
                except (KeyError, OSError, ValueError):
                    continue                                      # a layer without a file draws nothing
            surf = surface_from_rgba(_rgba(canvas.pix, True))
        self._portraits[key] = surf
        return surf

    def draw_info(self, window, ui, world, player_id, hover, info_picture):
        """Back is drawn by the caller; this draws the portrait (picture mode), the four buttons and the text rows (text mode)."""
        p = self.layout.info_panel.rect
        kind, val = info.selection_summary(world, player_id, hover, ui.frozen)
        mode = ui.shown_mode
        if kind == "unit":
            if mode == info.MODE_PICTURE:
                surf = self.portrait_surface(info.portrait(world, val, info_picture, pack_mod.hidden_slot(ui.pack.carried, val)))
                if surf is not None:
                    window.blit(surf, (p.x, p.y + 2))
        if kind == "structure":
            if mode == info.MODE_PICTURE:
                recs = world.assets.structures_reg() if getattr(world, "assets", None) is not None else {}
                path = info.structure_picture(val, recs)
                surf = self.portrait_surface(("bmp", path)) if path else None
                if surf is not None:
                    window.blit(surf, (p.x, p.y + 2))
            else:
                for r in info.structure_rows(val, ui.main, ui.building_names.lines):
                    draw_text_exact(window, r.text, p.x + r.x, p.y + r.y, r.table, r.flags, font=2)
        self.draw_buttons(window, ui, mode)
        rows = info.text_rows(world, val, ui.main, ui.unit_names.lines, player_id, ui.hero_name, ui.know_all, ui.knowledge) \
            if kind == "unit" and mode == info.MODE_TEXT else (info.count_rows(kind, val, ui.main) if kind in ("none", "many") else ())
        for r in rows:
            draw_text_exact(window, r.text, p.x + r.x, p.y + r.y, r.table, r.flags, font=2)

    def draw_extra(self, window, ui, world, player_id, hover):
        """Window 8 (`FUN_004b0a10`, 11.8): where it is tall enough for the info panel's text (1024x768) the text of the hovered / single selected object, drawn
        like the text mode of window 7 with the origin at the text rect (the picture and the TextBack art are blitted by the caller)."""
        r = self.layout.extra_text
        if r is None:
            return
        kind, val = info.selection_summary(world, player_id, hover, ui.frozen)
        if kind == "unit":
            rows = info.text_rows(world, val, ui.main, ui.unit_names.lines, player_id, ui.hero_name, ui.know_all, ui.knowledge)
        elif kind == "structure":
            rows = info.structure_rows(val, ui.main, ui.building_names.lines)
        else:
            rows = ()
        for row in rows:
            draw_text_exact(window, row.text, r.x + row.x, r.y + row.y, row.table, row.flags, font=2)

    # -- command bar and info panel buttons ----------------------------------------------------------------------------------------
    def draw_bar(self, window, cells):
        """11.2: the CommandEmpR rectangle of a cell with a clear mask bit (disabled look), then the CommandDnR cell of the pressed one."""
        emp, down = self.opaque("CommandEmpR"), self.opaque("CommandDnR")
        for c in cells:
            r = cell_rect(self.layout, c.index)
            src = pygame.Rect(8 + (c.index & 3) * 34, 7 + (c.index >> 2) * 34, 34, 34)
            if not c.enabled and emp is not None:
                window.blit(emp, (r.x, r.y), src)
            if c.pressed and down is not None:
                window.blit(down, (r.x, r.y), src)

    def draw_tooltip(self, window, tip):
        """`FUN_00427999` (ui-layout 11.6b): a bronze-framed box over everything.  Fill and the two-pixel bevel inset 1 px from the rect (light 1st line top / left, dark 2nd; the
        bottom / right pair reversed outward), text font2 in the `tooltip` table with the 1 px shadow, line i at (left + 5, top + 4 + 14 i).  The four 4x4 corner blits of `DAT_00626cac` = `interface/Ball.bmp`
        (CONFIRMED the file and the black colour key, `FUN_00453bca` skips packed 0) come after the fill and before the lines, at (L, T), (R-3, T), (L, B-4), (R-3, B-4)."""
        q = lambda c: ((c[0] >> 3) << 3, (c[1] >> 2) << 2, (c[2] >> 3) << 3)        # packed into the 565 screen format
        fill, light, dark = q(tooltip.FILL), q(tooltip.LIGHT), q(tooltip.DARK)
        l, t, r, b = tip.x, tip.y, tip.right, tip.bottom
        window.fill(fill, (l + 1, t + 1, r - l - 1, b - t - 2))
        ball = self.keyed("Ball")
        if ball is not None:
            for cx, cy in ((l, t), (r - 3, t), (l, b - 4), (r - 3, b - 4)):
                window.blit(ball, (cx, cy), pygame.Rect(0, 0, 4, 4))
        line = lambda c, p0, p1: pygame.draw.line(window, c, p0, p1)
        line(light, (l + 3, t + 1), (r - 3, t + 1))
        line(dark, (l + 3, t + 2), (r - 3, t + 2))
        line(light, (l + 3, b - 3), (r - 3, b - 3))
        line(dark, (l + 3, b - 2), (r - 3, b - 2))
        line(light, (l + 1, t + 3), (l + 1, b - 4))
        line(dark, (l + 2, t + 3), (l + 2, b - 4))
        line(light, (r - 2, t + 3), (r - 2, b - 4))
        line(dark, (r - 1, t + 3), (r - 1, b - 4))
        for i, text in enumerate(tip.lines):
            draw_text_exact(window, text, l + tooltip.TEXT_DX, t + tooltip.TEXT_DY + i * tooltip.LINE_H, "tooltip", 0, 2, off=1)

    def draw_buttons(self, window, ui, mode):
        """The four info-panel buttons (11.1).  In a mission (client mode 1) all four are drawn whatever the selection (the previous / next hero arrows
        replace backpack and disk only in the town / hero-screen modes, `FUN_004af3bf`); the mode button is absent while window 8 holds the text."""
        p = self.layout.info_panel.rect
        book_open = getattr(getattr(ui, "book", None), "open", False)
        pack_open = getattr(getattr(ui, "pack", None), "open", False)
        art = {"book": "BookOpened" if book_open else "BookClosed", "pack": "BackPackOp" if pack_open else "BackPackCl", "mode": "TextMode" if mode == info.MODE_TEXT else "HumanMode", "menu": "diskette"}
        for name in ("book", "pack", "mode", "menu"):
            if name == "mode" and self.layout.text_in_extra:
                continue
            surf = self.keyed(art[name])
            if surf is not None:
                x, y = INFO_BUTTONS[name][0]
                if name == "book" and book_open:
                    x, y = 0, 0                                  # BookOpened is drawn at (0, 0) (11.1)
                if name == "pack" and pack_open:
                    x, y = 0, 0xD0                               # BackPackOp at (0, 0xd0), source 32 x 31 (11.1)
                window.blit(surf, (p.x + x, p.y + y), pygame.Rect(0, 0, *SOURCE["pack_open" if name == "pack" and pack_open else name]))

    # -- backpack (window 2, ui-layout 11.13) ---------------------------------------------------------------------------------------
    def item_surface(self, code):
        """The inventory picture of an item code (`graphics/inventory/<name>.16a`, 80 x 80, `.16a` alpha), None without the file."""
        key = code & 0xFFFF
        if key not in self._items:
            try:
                f = SpriteFile.load(idefs.icon_path(key), self.fs)
                self._items[key] = surface_from_rgba(f.to_rgba(0))
            except (KeyError, OSError, ValueError):
                self._items[key] = None
        return self._items[key]

    def draw_pack(self, window, ui, view, main, mouse=None):
        """`FUN_004a2cf8`: the frame (left piece, slices, 1024 caps, right end: colour-keyed blits like the info panel buttons), the arrows, then per item cell
        `backinv.bmp`, the picture, the stack count (`label`, font2) and the F-key label (`highlight`, font3); with no hero the centred line main.txt 0x33."""
        pk = ui.pack
        r = pk.rect
        for art, sx, sw, x in pk.frame_blits():
            img = self.keyed(art)
            if img is not None:
                window.blit(img, (x, r.y), pygame.Rect(sx, 0, (sw if sw else img.get_width() - sx), img.get_height()))
        if pk.unit is None:
            draw_text_exact(window, main.line(pack_mod.T_NO_HERO), pack_mod.pad(self.layout) + (r.x + r.right - 16) // 2, (r.y + r.bottom) // 2, "label", 2 | 8, 2)    # `0x4a3104`: flags 0xa
            return
        for side, art in ((view.left, pack_mod.ARROWS[:2]), (view.right, pack_mod.ARROWS[2:])):
            if side is not None:
                img = self.keyed(art[1 if side[1] else 0])
                if img is not None:
                    window.blit(img, (side[0].x, side[0].y), pygame.Rect(0, 0, pack_mod.ARROW_W, pack_mod.ARROW_H))
        back = self.opaque(pack_mod.BACK)
        for c in view.cells:
            if back is not None:
                window.blit(back, (c.rect.x, c.rect.y))
            pic = self.item_surface(c.item.code)
            if pic is not None:
                window.blit(pic, (c.rect.x, c.rect.y))
            if c.new:
                self.draw_twinkle(window, c.rect, ui.world.tick)
            if c.item.count > 1:
                draw_text_exact(window, "%d" % c.item.count, c.rect.x + pack_mod.COUNT_DX, r.bottom + pack_mod.COUNT_DY, "label", 0, 2)
            if c.key:
                draw_text_exact(window, "F%d" % c.key, c.rect.x + pack_mod.KEY_DX, r.y + pack_mod.KEY_DY, "highlight", 0, 3)

    def draw_twinkle(self, window, rect, counter):
        """`FUN_004a285a`: the "new" flag's magenta sparkle (`pack_mod.twinkle_pixels`; the counter is the tick count, the exe's per-cell counter advances once per
        server step while the item is new, INFERRED equal)."""
        if self._twinkle is None:
            self._twinkle = pack_mod.twinkle_table()
        w, h = window.get_size()
        r, g, b = pack_mod.TWINKLE_COLOUR
        for dx, dy, a in pack_mod.twinkle_pixels(counter, self._twinkle):
            x, y = rect.x + dx, rect.y + dy
            if 0 <= x < w and 0 <= y < h:
                d = window.get_at((x, y))
                window.set_at((x, y), ((255 - a) * d[0] // 255 + r * a // 255, (255 - a) * d[1] // 255 + g * a // 255, (255 - a) * d[2] // 255 + b * a // 255))

    def draw_carried(self, window, item, mouse):
        """The carried item replaces the pointer (`FUN_0048ad7b`: the inventory picture, hot spot (40, 40))."""
        pic = self.item_surface(item.code)
        if pic is not None and mouse is not None:
            window.blit(pic, (mouse[0] - 40, mouse[1] - 40))

    def doll_mask(self, world, u, hidden=0):
        """The 240 x 160 hit mask of a unit's paper doll (`FUN_004688f7` with the mask: each layer writes slot + 1, the body 0), cached per layer list."""
        layers = tuple(info.doll_mask_layers(world, u, hidden))
        if layers not in self._masks:
            self._masks[layers] = paperdoll.hit_mask(layers, self.fs)
        return self._masks[layers]

    # -- spell book (window 3, ui-layout 11.12) ------------------------------------------------------------------------------------
    def draw_book(self, window, book, views):
        """`FUN_004c6ac1`: the side caps (800 / 1024), SpellBook.bmp centred in the window, SpellBack.bmp over every disabled slot, a veil over the selected tile, then the
        labels: "F<n>" of a bound enabled slot at (8, 8) and "A" of an auto-cast slot at (8, 0x22) in tile coordinates (font3, shifted by 2 when selected)."""
        r = book.rect
        fx = r.x + book_mod.frame_dx(self.layout)
        caps = book_mod.caps(self.layout)
        if caps is not None:
            left, right = self.opaque(caps[0]), self.opaque(caps[1])
            frame = self.opaque(book_mod.FRAME)
            if left is not None:
                window.blit(left, (r.x, r.y))
            if right is not None:
                window.blit(right, (fx + (frame.get_width() if frame is not None else book_mod.FRAME_W) - book_mod.CAP_OVERLAP, r.y))
        frame = self.opaque(book_mod.FRAME)
        if frame is not None:
            window.blit(frame, (fx, r.y))
        back = self.opaque(book_mod.TILE_ART)
        for v in views:
            if not v.enabled and back is not None:
                window.blit(back, (v.rect.x, v.rect.y))
        for v in views:
            if v.selected:
                self.veil(window, v.rect, book_mod.HIGHLIGHT_LEVEL)
        for v in views:
            off = book_mod.SELECTED_SHIFT if v.selected else 0
            if v.fkey:
                draw_text_exact(window, "F%d" % v.fkey, v.rect.x + book_mod.LABEL_X + off, v.rect.y + book_mod.FKEY_Y + off, "normal", 0, book_mod.FKEY_FONT)
            if v.auto:
                draw_text_exact(window, "A", v.rect.x + book_mod.LABEL_X + off, v.rect.y + book_mod.AUTO_Y + off, "normal", 0, book_mod.AUTO_FONT)

    @staticmethod
    def veil(window, rect, level):
        """`FUN_004565cd(rect, level)`: every pixel keeps (16 - level) / 16 of its 5/6/5-bit channel values plus `(level * 16 - 1) >> (8 - bits)` (INFERRED: the darken table is
        the same `(16 - level) / 16` as `FUN_004564df`, level 3 = 13/16)."""
        clip = pygame.Rect(rect.x, rect.y, rect.w, rect.h).clip(window.get_rect())
        if clip.w <= 0 or clip.h <= 0:
            return
        a = pygame.surfarray.pixels3d(window.subsurface(clip))
        add = (level * 16 - 1)
        r5, g6, b5 = a[..., 0].astype(np.int32) >> 3, a[..., 1].astype(np.int32) >> 2, a[..., 2].astype(np.int32) >> 3
        keep = 16 - level
        r5 = np.minimum(31, r5 * keep // 16 + (add >> 3))
        g6 = np.minimum(63, g6 * keep // 16 + (add >> 2))
        b5 = np.minimum(31, b5 * keep // 16 + (add >> 3))
        a[..., 0], a[..., 1], a[..., 2] = (r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4), (b5 << 3) | (b5 >> 2)
        del a

    # -- dialogs -------------------------------------------------------------------------------------------------------------------
    def frame_surface(self, w, h):
        """RGBA of a `lm.256` frame body of w x h (11.4) plus its 8 px drop shadow (the same sprites darkened, shifted by 8): corners 1/3/6/8, edges 2/7 tiled in x,
        4/5 in y, centre 0 tiles; clipped to the rect.  Cached per size."""
        if (w, h) in self._frames:
            return self._frames[(w, h)]
        sf = SpriteFile.load(FRAME_SPRITES, self.fs)
        sp, pal = sf.sprites, sf.palette
        layers = []
        for fill in ((0, 0, 0), (255, 255, 255)):                 # two sentinels: a pixel is covered when the canvases differ
            c = Canvas(w, h, fill)
            for x in range(0x30, w - 0x30, 96):
                for y in range(0x30, h - 0x30, 64):
                    c.draw_256(sp[0], x, y, pal)
            for x in range(0x30, w - 0x30, 96):
                c.draw_256(sp[2], x, 0, pal)
                c.draw_256(sp[7], x, h - 0x30, pal)
            for y in range(0x30, h - 0x30, 64):
                c.draw_256(sp[4], 0, y, pal)
                c.draw_256(sp[5], w - 0x30, y, pal)
            for idx, (x, y) in ((1, (0, 0)), (3, (w - 0x30, 0)), (6, (0, h - 0x30)), (8, (w - 0x30, h - 0x30))):
                c.draw_256(sp[idx], x, y, pal)
            layers.append(c.pix)
        covered = (layers[0] == layers[1]).all(axis=2)
        out = np.zeros((h + 8, w + 8, 4), np.uint8)
        shadow = np.zeros((h + 8, w + 8), bool)
        shadow[8:, 8:] = covered
        out[shadow, 3] = SHADOW_ALPHA
        out[:h, :w][covered, :3] = layers[0][covered]
        out[:h, :w][covered, 3] = 255
        self._frames[(w, h)] = surface_from_rgba(out)
        return self._frames[(w, h)]

    def draw_button(self, window, b, hovered, pressed):
        """`FUN_004d571a` (CONFIRMED): no own fill (the face is the parent dialog's frame redrawn under the button), bevel: light 1 px top / left, dark 2 px bottom / right
        (swapped while pressed under the pointer), centred text (shadow 2, 4 pressed), gold only while enabled and under the pointer, else the normal table; disabled = darkened."""
        r = b.rect
        l, t, rr, bb = r.x, r.y, r.right - 1, r.bottom - 1
        light, dark = (BEVEL_DARK, BEVEL_LIGHT) if pressed else (BEVEL_LIGHT, BEVEL_DARK)
        line = lambda c, p, q: pygame.draw.line(window, c, p, q)
        line(light, (l + 2, t), (rr - 2, t))
        line(light, (l, t + 2), (l, bb - 2))
        window.set_at((l + 1, t + 1), light)
        line(dark, (rr, t + 2), (rr, bb - 2))
        line(dark, (rr - 1, t + 1), (rr - 1, bb - 1))
        line(dark, (l + 2, bb), (rr - 2, bb))
        line(dark, (l + 1, bb - 1), (rr - 1, bb - 1))
        window.set_at((rr - 2, bb - 2), dark)
        w = measure(b.label, 1)
        f = game_font(1)
        ch = f.cell_height() if f is not None else 12
        draw_text_exact(window, b.label, r.x + (r.w - w) // 2, r.y + (r.h - ch) // 2, "label" if b.enabled and hovered else "normal", 0, 1,
                        off=4 if pressed and b.enabled else 2)
        if not b.enabled:
            shade = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
            shade.fill((0, 0, 0, DISABLED_ALPHA))
            window.blit(shade, (r.x, r.y))

    def draw_dialog(self, window, d, mouse, pressed, ui=None, info_picture=None):
        """One dialog: the frame (11.4), the caption (left, `0x443238`), the text and the buttons.  A dialog with `lines` (message windows, complete) draws them one by one `d.pitch`
        apart (`FUN_0045e01d`: left at the rect's x, or centred on the rect for `align == "center"`; the justified spacing of wrapped paragraphs is not built); one without
        (story) lets `draw_text` wrap `d.text` to the rect."""
        f = d.frame
        window.blit(self.frame_surface(f.w - 8, f.h - 8), (f.x, f.y))      # body w-8 x h-8, the last 8 px hold the shadow (`FUN_004dbd5f`)
        if d.caption:
            c = d.caption_rect
            draw_text_exact(window, d.caption, c.x, c.y, d.table, 0, 1, off=1)
        if d.picture is not None:
            self.draw_story_picture(window, d, ui, info_picture)
        tr = d.text_rect
        if d.lines:
            for i, line in enumerate(d.lines):
                x, flags = (tr.x + tr.w // 2, 2) if d.align == "center" else (tr.x, 0)
                draw_text_exact(window, line, x, tr.y + i * d.pitch, d.table, flags, 1, off=1)
        elif d.text:
            draw_text(window, d.text, tr.x, tr.y, d.table, "left", font=1, width=tr.w, wrap=True)
        for i, b in enumerate(d.buttons):
            over = mouse is not None and b.rect.contains(*mouse)
            self.draw_button(window, b, over, bool(pressed and pressed[0] is d and pressed[1] == i and over))

    def draw_story_picture(self, window, d, ui, info_picture):
        """The speaker picture (`FUN_0041d48d`, 11.5): an 88x108 surface (black: INFERRED) at the widget's origin with the crop of the unit's 160x240 portrait placed at (8, 7);
        blank when the unit does not exist."""
        pw, ph = story.PICTURE_SIZE
        r = d.picture
        window.fill((0, 0, 0), (r.x, r.y, pw, ph))
        u = ui.world.units.get(d.picture_unit) if ui is not None and d.picture_unit is not None else None
        type_id = 1                                               # the dummy unit of `FUN_0041d8bb` has type 1 (default crop)
        if u is not None:
            surf = self.portrait_surface(info.portrait(ui.world, u, info_picture))
            type_id = u.type_id
        elif d.picture_npc is not None:
            path = story.dummy_doll_path(d.picture_npc)           # no living unit: the dummy's empty female-mage doll (face = id - 0x50); a missing face file = the exe's fatal error, blank here
            surf = self.portrait_surface(("doll", [path])) if self.fs.exists(path) else None
        else:
            surf = None
        if surf is None:
            return                                                # no unit: the blank surface, no background, no border (`0x41d4e2`)
        x, y, w, h = story.crop_of(type_id)
        back = self.opaque("t_back")                              # the same crop of `t_back.bmp` (opaque `+0x34`) under the keyed portrait (`+0x38`)
        if back is not None:
            window.blit(back, (r.x + 8, r.y + 7), pygame.Rect(x, y, w, h))
        window.blit(surf, (r.x + 8, r.y + 7), pygame.Rect(x, y, w, h))
        border = self.story_border()
        if border is not None:
            window.blit(border, (r.x, r.y))

    def story_border(self):
        """`t_border.256` (88x108, drawn at (0, 0) over the picture) with the exe's quirk: its sprite blit writes the top row first into the bottom-up panel, so the
        frame appears vertically mirrored (bitmaps.md, picture step 5)."""
        if "story_border" not in self._keyed:
            try:
                sf = SpriteFile.load("graphics/interface/t_border.256", self.fs)
                layers = []
                for fill in ((0, 0, 0), (255, 255, 255)):
                    c = Canvas(88, 108, fill)
                    c.draw_256(sf.sprites[0], 0, 0, sf.palette)
                    layers.append(c.pix)
                covered = (layers[0] == layers[1]).all(axis=2)
                rgba = np.zeros((108, 88, 4), np.uint8)
                rgba[..., :3] = layers[0]
                rgba[covered, 3] = 255
                self._keyed["story_border"] = surface_from_rgba(np.ascontiguousarray(rgba[::-1]))
            except (KeyError, OSError, ValueError, IndexError):
                self._keyed["story_border"] = None
        return self._keyed["story_border"]

    def draw_dialogs(self, window, ui, mouse, info_picture=None):
        for d in ui.modals.stack:
            self.draw_dialog(window, d, mouse, ui.pressed, ui, info_picture)
