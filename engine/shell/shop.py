"""The shop window (L8, docs/engine/town-shop.md; `engine.shop` is the pure model): the stock panel with the shown shelf, the shopkeeper picture whose four shelves are clicked, the
table, the shown hero's pack, the buttons panel (Cancel / Buy / Sell / Exit with the gold and the two totals) and the unit info panel with the hero's paper doll and its two arrows,
all at the 640x480 window origin `O`.

Input as the exe's: a press on an item cell takes one piece (Shift: the stack) into the cursor, the release over a region drops it (refused drops return it with the nofit sound), a
button acts on the release over the pressed one (Cancel / Exit also play their sound on the press), a click on a shelf of the picture shows it, ESC = Exit (the table is returned).

CONFIRMED in the L8 REA round (town-shop 9): the grids' cell rects and scroll arrows, the shelf rects, the buttons panel (the picture holds the buttons, `ShopButtonN` only while held, a caption and a
number per button), Shift = the whole stack.  DECISIONs (INFERRED, town.md 5 "L8 as built"): (shopkeeper animations, highlights, tooltips and the doll drop were built later: shop-rea2, town-shop 11), the druid / Kaarg shops use their own art directories."""

from types import SimpleNamespace

from allods2.formats import itemdefs as idefs
from allods2.text import decode_text

from engine import inn as I
from engine import shop as P
from engine import townscene as TS
from engine.ui.orders import MainText

from engine import shopkeeper as K

from .events import Key, Move, Press, Release
from engine.ui import pack as UP
from engine.ui.tooltip import TooltipTimer

from .chargen import measure_font2
from .scene import Image, Portrait, Scene, Sprite, Text, Tooltip
from .screen import Screen
from .tipswin import TipsWindow

BASE = "graphics/interface/"
ART = {1: BASE, 2: BASE + "shop_kaarg/", 3: BASE + "shop_druid/"}
MAIN_PIC = {1: BASE + "shopanim/shopmain.bmp", 2: BASE + "shop_kaarg/shopmain.bmp", 3: BASE + "shop_druid/shopmain.bmp"}
HERO_BACK = "graphics/interface/HumanBackR.bmp"
ARROW_FILES = ("graphics/interface/ar1.bmp", "graphics/interface/ar2.bmp")
INV_ARROWS = ("graphics/interface/InvArrow1.bmp", "graphics/interface/InvArrow2.bmp")
INV_FRAME = "graphics/interface/InvFrame.bmp"
TOWN_SOUND = {1: "sfx/town/", 2: "sfx/town_kaarg/shop/", 3: "sfx/town_druid/shop/"}
SOUNDS = {"nofit": "sfx/town/shop/nofit.wav", "buy": "sfx/town/buy.wav", "sell": "sfx/town/sell.wav", "undo": "sfx/undo.wav", "out": "sfx/out.wav"}      # `0x4b995b` slots
ENTER = {1: "sfx/town/shop/enter.wav", 2: "sfx/town_kaarg/shop/kin2.wav", 3: "sfx/town_druid/shop/din2.wav"}      # `+0xac`; CONFIRMED by the load strings' order (nofit, depart, buy, sell, enter, start, 2nd, loop, Out, Undo; Kin2 is missing in the install: silent)
DEPART = {1: "sfx/town/shop/depart.wav", 2: "sfx/town_kaarg/shop/kotdel.wav", 3: "sfx/town_druid/shop/dotdel.wav"}
AMBIENT = {1: "sfx/town/shop/inshop.wav", 2: "sfx/town_kaarg/inn/kvox5.wav", 3: "sfx/town_druid/inn/dforest2.wav"}     # `+0xbc` the InShop loop (CONFIRMED order of the druid / Kaarg load strings: the loop is the 8th sound, `Dforest2` / `Kvox5`)
CLICK_UI = 1
TIPS_RECT = (0, 162, 312, 136)                             # `0x4b8cbe`: SetRect (0, 0xa2, 0x138, 0x12a) = 312 x 136
TIPS_TABLE = 4                                             # `#tips4` the first time an item lies on the table (`0x4b9144`)
HOLD_AT = 40                                               # the carried item's hot spot (40, 40)


class Shop(Screen):
    name, view = "shop", "shop"
    music = None                                    # the scene's playlist keeps playing (town-shop 6)

    def __init__(self, shell):
        super().__init__(shell)
        self.state = None
        self.hover = self.pressed = None
        self.clip = None
        self.pointer = None
        self.tip_timer = TooltipTimer()

    @property
    def core(self):
        return self.shell.town_core()

    # -- enter / exit ---------------------------------------------------------------------------------------------------------------
    def enter(self, **params):
        sh = self.shell
        core = self.core
        fs = sh.fs
        self.main = MainText.load(fs) if fs is not None else MainText()
        self.town_lines = []
        if fs is not None:
            try:
                self.town_lines = decode_text(fs.read(TS.TOWN_TEXT)).split("\r\n")
            except (KeyError, OSError):
                pass
        self.assets = None
        if fs is not None:
            try:
                self.assets = sh.campaign.assets
            except Exception:                           # noqa: BLE001  no install behind the campaign: no pictures
                self.assets = None
        table = self.assets.items() if self.assets is not None else None
        stock = P.open_stock(core, sh.campaign, core.town, sh.rng)
        self.state = P.ShopState(sh.campaign, core.town, stock, table)
        self.hover = self.pressed = self.clip = None
        self.keeper = K.Keeper(core.town, sh.rng)
        self.art = ART[core.town]
        self.portrait_cache, self.mask_cache = {}, {}
        self.tips_shown_table = False
        self.hint = sh.settings.tips and sh.campaign is not None       # `+0x5d8 == 2`: the campaign
        self.tips_key = 3
        self.tips_win = TipsWindow(TIPS_RECT, self.main, self._tips_wrap, self._tips_measure)
        sh.play(ENTER[core.town])
        if core.town in AMBIENT:
            sh.services.loop(AMBIENT[core.town])

    def exit(self):
        self.shell.services.loop(None)
        if self.state is not None:
            self.state.leave()

    def _tips_wrap(self, text, width):
        if self.shell.fs is None:
            return text.split("\n")
        from .chargen import wrap_font2
        return wrap_font2(self.shell, text, width)

    def _tips_measure(self, text):
        if self.shell.fs is None:
            return 7 * len(text)
        from .chargen import measure_font2
        return measure_font2(self.shell, text)

    def tips_text(self):
        key = "#tips%d" % self.tips_key
        for i, line in enumerate(self.town_lines):
            if line.strip().lower() == key:
                return self.town_lines[i + 1] if i + 1 < len(self.town_lines) else ""
        return ""

    # -- geometry / hit testing (window-relative points) ----------------------------------------------------------------------------
    def _local(self, x, y):
        ox, oy = self.origin
        return x - ox, y - oy

    def doll_slot(self, x, y):
        """The equipment slot index under a point of the info panel (the doll's hit mask: id = slot + 1, the body 0), None for none."""
        entry = self.state.entry()
        if entry is None or entry.state is None or self.assets is None:
            return None
        ix, iy, _, _ = P.INFO_PANEL
        mx, my = x - ix, y - iy - 2
        if not (0 <= mx < 160 and 0 <= my < 240):
            return None
        key = (entry.number, tuple(i.code for i in entry.state.equipment))
        if key not in self.mask_cache:
            try:
                from allods2.graphics import paperdoll
                from engine.ui import info
                t = self.assets.unit_stats().lookup(True, entry.server_id)
                layers = info.doll_mask_layers(SimpleNamespace(item_table=self.assets.items()), I._unit_of(t, entry))
                self.mask_cache[key] = paperdoll.hit_mask(layers, self.shell.fs)
            except Exception:                           # noqa: BLE001  no mask: the doll is not a source
                self.mask_cache[key] = None
        mask = self.mask_cache[key]
        if mask is None:
            return None
        v = int(mask[my][mx])
        return v - 1 if v >= 1 else None

    def hit(self, x, y):
        x, y = self._local(x, y)
        st = self.state
        if self.hint:
            h = self.tips_win.hit(x, y)
            if h:
                return (h,)
        for i, r in enumerate(P.BUTTONS):
            if P.rect_has(r, x, y):
                return ("button", i)
        for k, r in enumerate(P.ARROWS):
            if P.rect_has(r, x, y):
                return ("arrow", k)
        if P.rect_has(P.INFO_PANEL, x, y):
            s = self.doll_slot(x, y)
            return ("cell", P.KIND_EQUIP, s) if s is not None else ("region", P.KIND_EQUIP)
        px, py, pw, ph = P.STOCK_PANEL
        if P.rect_has(P.STOCK_PANEL, x, y):
            for k, r in enumerate(P.STOCK_ARROWS):
                if P.rect_has(r, x, y):
                    return ("sarrow", k)
            for i in range(P.STOCK_COLS * P.STOCK_ROWS):
                if P.rect_has(P.stock_cell(i), x, y):
                    return ("cell", P.KIND_SHELF + st.shelf, st.scroll["stock"] + i)
            return ("region", P.KIND_SHELF + st.shelf)
        for panel, kind, key in ((P.TABLE_PANEL, P.KIND_TABLE, "table"), (P.PACK_PANEL, P.KIND_PACK, "pack")):
            if P.rect_has(panel, x, y):
                for k, r in enumerate(P.STRIP_ARROWS[key]):
                    if P.rect_has((panel[0] + r[0], panel[1] + r[1], r[2], r[3]), x, y):
                        return ("tarrow", key, k)
                for k in range(P.STRIP_COLS):
                    if P.rect_has(P.strip_cell(panel, k), x, y):
                        return ("cell", kind, st.scroll[key] + k)
                return ("region", kind)
        sx, sy, _, _ = P.SHOPKEEPER_PANEL
        for i, r in enumerate(P.SHELF_RECTS_BY_TOWN[self.core.town]):
            if P.rect_has((sx + r[0], sy + r[1], r[2], r[3]), x, y) and st.shelf_open(i):       # a refused shelf (the druid's fourth) lets the test go on (`0x4bfdf1`)
                return ("shelf", i)
        return None

    def point_of(self, what, *args):
        """Screen coordinates of the middle of a button / arrow / cell / shelf (tests, scripted clicks): `point_of("button", i)`, `("arrow", k)`, `("cell", kind, k)` (k = the cell on screen
        0..), `("shelf", i)`, `("doll",)`."""
        ox, oy = self.origin
        if what == "button":
            r = P.BUTTONS[args[0]]
        elif what == "arrow":
            r = P.ARROWS[args[0]]
        elif what == "cell":
            kind, k = args
            if kind >= P.KIND_SHELF:
                r = P.stock_cell(k)
            else:
                r = P.strip_cell(P.TABLE_PANEL if kind == P.KIND_TABLE else P.PACK_PANEL, k)
        elif what == "shelf":
            sx, sy, _, _ = P.SHOPKEEPER_PANEL
            q = P.SHELF_RECTS_BY_TOWN[self.core.town][args[0]]
            r = (sx + q[0], sy + q[1], q[2], q[3])
        elif what == "stock_arrow":
            r = P.STOCK_ARROWS[args[0]]
        elif what == "strip_arrow":
            panel = P.TABLE_PANEL if args[0] == "table" else P.PACK_PANEL
            q = P.STRIP_ARROWS[args[0]][args[1]]
            r = (panel[0] + q[0], panel[1] + q[1], q[2], q[3])
        else:
            r = P.INFO_PANEL
        return ox + r[0] + r[2] // 2, oy + r[1] + r[3] // 2

    def update(self, dt_ms):
        self.keeper.update(dt_ms)
        self.tip_timer.update(dt_ms, self.pointer, self.tooltip_text, lambda t: measure_font2(self.shell, t), (640, 480))
        return None

    # -- tooltips (shop-tooltips-rea.md, CONFIRMED slot 5 of each panel) ----------------------------------------------------------------
    def _item_tip(self, item):
        if item is None or not item.code:
            return ""
        table = self.state.table
        if table is None:
            return ""
        try:
            spells = self.assets.spells() if self.assets is not None else None
            return UP.item_name(SimpleNamespace(item_table=table, spell_table=spells), item, self.main)
        except Exception:                                # noqa: BLE001  an item the text builder cannot describe shows nothing
            return ""

    def tooltip_text(self, pos):
        """The text under the screen point `pos`, '' for none.  The stock, table, pack and info panels are silent while an item is carried; the shopkeeper panel and the buttons
        (never a tooltip) are not gated on it."""
        x, y = self._local(*pos)
        st, line = self.state, self.main.line
        sx, sy, _, _ = P.SHOPKEEPER_PANEL
        if P.rect_has(P.SHOPKEEPER_PANEL, x, y):
            for i, r in enumerate(P.SHELF_RECTS_BY_TOWN[self.core.town]):          # no open test: the druid's elven shelf answers while locked
                if P.rect_has((sx + r[0], sy + r[1], r[2], r[3]), x, y):
                    return line(P.SHELF_TIP[self.core.town] + i)
            r = P.KEEPER_RECT[self.core.town]
            return line(P.T_KEEPER) if P.rect_has((sx + r[0], sy + r[1], r[2], r[3]), x, y) else ""
        if st.carried is not None:
            return ""
        if P.rect_has(P.STOCK_PANEL, x, y):
            for i in range(P.STOCK_COLS * P.STOCK_ROWS):
                if P.rect_has(P.stock_cell(i), x, y):
                    return self._item_tip(st.item_at(P.KIND_SHELF + st.shelf, st.scroll["stock"] + i))
            for k, r in enumerate(P.STOCK_ARROWS):
                if P.rect_has(r, x, y):
                    return line((P.T_UP, P.T_DOWN)[k])
            return line(P.T_STOCK)
        for panel, kind, key, other in ((P.TABLE_PANEL, P.KIND_TABLE, "table", P.T_TABLE), (P.PACK_PANEL, P.KIND_PACK, "pack", P.T_PACK)):
            if P.rect_has(panel, x, y):
                for k in range(P.STRIP_COLS):
                    if P.rect_has(P.strip_cell(panel, k), x, y):
                        return self._item_tip(st.item_at(kind, st.scroll[key] + k))
                if key == "pack":                                                   # the table's own arrows have no test: its text covers them
                    for k, r in enumerate(P.STRIP_ARROWS[key]):
                        if P.rect_has((panel[0] + r[0], panel[1] + r[1], r[2], r[3]), x, y):
                            return line((P.T_LEFT, P.T_RIGHT)[k])
                return line(other)
        for k, r in enumerate(P.ARROWS):
            if P.rect_has(r, x, y):
                return line((P.T_PREV, P.T_NEXT)[k])
        if P.rect_has(P.INFO_PANEL, x, y):
            s = self.doll_slot(x, y)
            return self._item_tip(st.item_at(P.KIND_EQUIP, s)) if s is not None else ""
        return ""

    def tooltip_op(self):
        tip = self.tip_timer.tip
        if tip is None:
            return []
        ox, oy = self.origin
        return [Tooltip(tip.lines, tip.x + ox, tip.y + oy, tip.right + ox, tip.bottom + oy)]

    # -- input -----------------------------------------------------------------------------------------------------------------------
    def event(self, ev):
        st = self.state
        if hasattr(ev, "x"):
            self.pointer = (ev.x, ev.y)
            self.tip_timer.moved(self.pointer)
        if isinstance(ev, Move):
            self.hover = self.hit(ev.x, ev.y)
        elif isinstance(ev, Press) and ev.button == 3:
            st.carried = None                            # the right button puts the carried item back (the exe's release on no region)
        elif isinstance(ev, Press) and ev.button == 1:
            self.hover = h = self.hit(ev.x, ev.y)
            self.pressed = h
            if h is None:
                return None
            if h[0] == "button" and h[1] in (P.B_CANCEL, P.B_EXIT) and st.carried is None:
                self.shell.play(SOUNDS["undo" if h[1] == P.B_CANCEL else "out"])     # `0x4bd988`: the press plays Undo / Out
            elif h[0] == "shelf":
                self._apply(st.select_shelf(h[1]))
            elif h[0] == "cell" and st.carried is None:
                st.pick(h[1], h[2], whole=bool(getattr(ev, "shift", False)))
        elif isinstance(ev, Release) and ev.button == 1:
            down, self.pressed = self.pressed, None
            self.hover = h = self.hit(ev.x, ev.y)
            if st.carried is not None:
                self._drop(h)
                return None
            if h is None or down is None:
                return None
            if h[0] == "arrow" and down[0] == "arrow":
                self.shell.play(CLICK_UI)
                st.hero_prev() if h[1] == 0 else st.hero_next()
            elif h[0] == "sarrow" and h == down:
                self._scroll("stock", -1 if h[1] == 0 else 1, P.STOCK_COLS, len(st.shelf_items()), P.STOCK_COLS * P.STOCK_ROWS)
            elif h[0] == "tarrow" and h == down:
                n = len(st.lots) if h[1] == "table" else len(st.pack())
                self._scroll(h[1], -1 if h[2] == 0 else 1, 1, n, P.STRIP_COLS)
            elif h[0] == "close" and h == down:
                self.hint = False
            elif h[0] == "tips" and h == down:
                self.shell.settings.tips = self.tips_win.toggle()
                self.shell.services.save_settings(self.shell.settings)
            elif h[0] == "button" and h == down:
                return self._button(h[1])
        elif isinstance(ev, Key) and not ev.ctrl and ev.name == "escape":
            return self.exit_window()
        return None

    def _scroll(self, key, d, step, count, shown):
        """A scroll arrow: `step` single-item moves, each guarded as the exe's (`0x4a1a78`: forward while `count > offset + cells`, back while the offset is above 0; the stock arrows
        call it twice = one row of two, so the offset may stay odd)."""
        s = self.state.scroll
        for _ in range(step):
            if d > 0 and count > s[key] + shown:
                s[key] += 1
            elif d < 0 and s[key] > 0:
                s[key] -= 1

    def _drop(self, h):
        """The release of the carried item (`0x4b25cb`): over a region its rules, anywhere else it returns."""
        st = self.state
        if h is None or h[0] not in ("cell", "region"):
            st.carried = None
            return
        kind = h[1]
        index = h[2] if h[0] == "cell" else -1
        before = len(st.lots)
        self._apply(st.drop(kind, index))
        self._clamp()
        if len(st.lots) > before and not self.tips_shown_table and self.hint:
            self.tips_shown_table = True                  # `0x4b9144`: `#tips4` the first time the table is not empty
            self.tips_key = TIPS_TABLE

    def _clamp(self):
        st = self.state
        for key, n, shown in (("table", len(st.lots), P.STRIP_COLS), ("pack", len(st.pack()), P.STRIP_COLS), ("stock", len(st.shelf_items()), P.STOCK_COLS * P.STOCK_ROWS)):
            st.scroll[key] = max(0, min(st.scroll[key], max(0, n - shown)))

    def _button(self, i):
        st = self.state
        if i == P.B_EXIT:
            return self.exit_window()
        effects = {P.B_CANCEL: st.cancel, P.B_BUY: st.buy, P.B_SELL: st.sell}[i]()
        self._clamp()
        self._apply(effects)
        return None

    def exit_window(self):
        """The Exit button / ESC (`0x4b956e`): the table is returned, `0x445` -> `0x44c`, `0x42e` at mask exactly 2 -> the scene."""
        self.state.leave()
        self.core.close_window()
        return self.shell.town_screen()

    def _apply(self, effects):
        for e in effects:
            if e.kind == "sound":
                self.shell.play(DEPART[self.core.town] if e.value == "depart" else SOUNDS[e.value])
            elif e.kind == "shelf":
                self.keeper.select(e.value)
                self.keeper.yes()                         # the press handler's Yes reaction after an accepted shelf (human only: `Keeper.yes`)
            elif e.kind == "yes":
                self.clip = e.kind
                self.keeper.yes()
            elif e.kind == "refuse":
                self.clip = e.kind
                self.keeper.no()
        if effects:
            self.shell.log("shop: " + " ".join("%s=%s" % (e.kind, e.value) for e in effects))

    # -- drawing ---------------------------------------------------------------------------------------------------------------------------------
    def _portrait(self, key, make):
        if key not in self.portrait_cache:
            try:
                self.portrait_cache[key] = make() if self.assets is not None else None
            except Exception:                           # noqa: BLE001  the picture is decoration
                self.portrait_cache[key] = None
        return self.portrait_cache[key]

    def _cell(self, ops, rect, item, back, side, ox, oy):
        """One item cell, everything one pixel below the cell top as the exe draws it (`FUN_004b18e2`): the background, the picture, the price bar (60 x 10 at the cell's right end, frame
        from the full price), the price number right-aligned on it (gold, font2, `,` per thousand, the hero's own items at half), the stack count."""
        x, y = ox + rect[0], oy + rect[1] + 1
        ops.append(Image(BASE + back + ".bmp", x, y))
        if item is None:
            return
        ops.append(Sprite(idefs.icon_path(item.code), 0, x, y))
        price = self.state.price(item)
        frame = P.price_bar_frame(price)
        if frame is not None:
            ops.append(Image(BASE + ("costs" if side == "buy" else "costm") + "%d.bmp" % (frame + 1), x + P.BAR_AT[0], y + P.BAR_AT[1], True))
            ops.append(Text(P.price_text(price if side == "buy" else (price + 1) // 2), x + CELL_H - P.PRICE_RIGHT, y, 2, "label", 1, 1))
        if item.count > 1:
            ops.append(Text(P.price_text(item.count), x + P.COUNT_AT[0], y + CELL_H + P.COUNT_AT[1], 2, "label", 0, 1))

    def scene(self):
        ox, oy = self.origin
        st = self.state
        ops = []
        # the stock panel (+0x68): the frame, the shown shelf's items in a 2 x 3 grid, the scroll arrows
        ops.append(Image(self.art + "shopinv.bmp", ox, oy))
        items = st.shelf_items()
        for i in range(P.STOCK_COLS * P.STOCK_ROWS):
            k = st.scroll["stock"] + i
            self._cell(ops, P.stock_cell(i), items[k] if k < len(items) else None, "backinvg", "buy", ox, oy)
        for k, (x, y, w, h) in enumerate(P.STOCK_ARROWS):
            ops.append(Image(self.art + "shoparrow%d.bmp" % (1 if k == 0 else 3), ox + x, oy + y, True))
        # the pack (+0x6c) and the table (+0x70): five cells each
        ops.append(Image(INV_FRAME, ox, oy + P.PACK_PANEL[1]))
        ops.append(Image(self.art + "shoptable.bmp", ox, oy + P.TABLE_PANEL[1]))
        pack = st.pack()
        for k in range(P.STRIP_COLS):
            i = st.scroll["pack"] + k
            self._cell(ops, P.strip_cell(P.PACK_PANEL, k), pack[i] if i < len(pack) else None, "backinvb", "sell", ox, oy)
            j = st.scroll["table"] + k
            lot = st.lots[j] if j < len(st.lots) else None
            self._cell(ops, P.strip_cell(P.TABLE_PANEL, k), lot.item if lot else None, "backinvb", lot.side if lot else "sell", ox, oy)
        for panel, key in ((P.TABLE_PANEL, "table"), (P.PACK_PANEL, "pack")):
            for k, (x, y, w, h) in enumerate(P.STRIP_ARROWS[key]):
                ops.append(Image(INV_ARROWS[k], ox + panel[0] + x, oy + panel[1] + y, True))
        # the shopkeeper panel (+0x74)
        sx, sy, _, _ = P.SHOPKEEPER_PANEL
        ops.append(Image(MAIN_PIC[self.core.town], ox + sx + P.PICTURE_AT[0], oy + sy + P.PICTURE_AT[1]))
        ops.append(Sprite(self.art + "shopframe.256", 0, ox + sx, oy + sy))
        if self.core.town == 3 and st.game.camp.get(P.DRUID_GATE):                      # the elven goods are part of the picture once the gate variable is set (`0x4bf908`)
            ops.append(Image(self.art + "elven.bmp", ox + sx + K.ELVEN_AT[0], oy + sy + K.ELVEN_AT[1]))
        # every keeper-panel draw (`0x4bb3d7`, `0x4bf908`, `0x4c28c6`: elven picture, highlights, keeper, brazier) blits with vtable `+0x18` = opaque (CONFIRMED, shop-rea2 3.1): no colour key
        for pic in self.keeper.highlight_pics():
            ops.append(Image(pic.path, ox + sx + pic.x, oy + sy + pic.y))
        kp = self.keeper.keeper_pic()
        ops.append(Image(kp.path, ox + sx + kp.x, oy + sy + kp.y))
        fp = self.keeper.fire_pic()
        if fp is not None:
            ops.append(Image(fp.path, ox + sx + fp.x, oy + sy + fp.y))
        # the buttons panel (+0x78): the menu picture holds the four buttons up; the `ShopButton` pictures are the pressed look (`0x4bcd05`, CONFIRMED); every button has its caption
        # and, under it, one of the four numbers (gold, minus the buy prices, the sell value, the gold after the deal)
        ops.append(Image(self.art + "shopmenu.bmp", ox + P.BUTTONS_PANEL[0], oy))
        gold, buy, sell, after = st.totals()
        numbers = (gold, buy, sell, after)
        for i, (x, y, w, h) in enumerate(P.BUTTONS):
            mine = self.hover == ("button", i)
            held = mine and self.pressed == ("button", i)
            if held:
                ops.append(Image(self.art + "shopbutton%d.bmp" % (i + 1), ox + x, oy + y, True))
            colour = "yellow" if mine else "gold"
            lx, ly = P.label_at(i, held)
            nx, ny = P.number_at(i, held)
            ops.append(Text(self.main.line(P.LABEL_LINES[i]), ox + lx, oy + ly, 4, colour, 0xA, 1))
            ops.append(Text("%d" % numbers[i], ox + nx, oy + ny, 4, colour, 0xA, 1))
        # the unit info panel (window 7)
        ix, iy, _, _ = P.INFO_PANEL
        ops.append(Image(HERO_BACK, ox + ix, oy + iy))
        entry = st.entry()
        if entry is not None:
            spec = self._portrait(("h", entry.number, id(entry.state), tuple(i.code for i in entry.state.equipment) if entry.state is not None else ()),
                                  lambda: I.hero_portrait(self.assets, entry))
            if spec is not None:
                ops.append(Portrait(spec, ox + ix, oy + iy + 2))
        for k, (x, y, w, h) in enumerate(P.ARROWS):
            ops.append(Image(ARROW_FILES[k], ox + x, oy + y, True))
        if self.hint:
            ops += self.tips_win.ops(self.tips_text(), self.hover[0] if self.hover and len(self.hover) == 1 else None,
                                     self.pressed[0] if self.pressed and len(self.pressed) == 1 else None, ox, oy)
        if st.carried is not None and self.shell.mouse is not None:
            mx, my = self.shell.mouse
            ops.append(Sprite(idefs.icon_path(st.carried.item.code), 0, mx - HOLD_AT, my - HOLD_AT))
        ops += self.tooltip_op()
        return Scene(ops)


CELL_H = P.CELL
