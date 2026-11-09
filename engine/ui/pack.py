"""The backpack window (bottom bar id 2, class `FUN_004a2bba`, vtable `0x5ce978`; docs/engine/ui-layout.md 11.13).  Pure state, hit rects and the item
rules of the mouse; the backend draws it (`Panels.draw_pack`) and `GameUi` routes the mouse.  No pygame.

The window is the strip of pack cells of the single selected hero: 80x80 cells with the item picture and the stack count, a left and a right arrow that
scroll by one item.  It owns no equipment slots: those are the hit mask of the paper doll in the info panel (window 7, `FUN_004b012f` / `FUN_004b028d`);
the carried item (`client+0x3f4`) travels between the two and the view (`FUN_0040c5d1`).  Every move is the exe's message `0x22` (`MoveItem`)."""

from dataclasses import dataclass, replace
from typing import NamedTuple

from allods2.formats import itemdefs as idefs

from engine.sim import gear
from engine.sim import movement as mv
from engine.sim import spells as spells_mod
from engine.sim.commands import CastScroll, MoveItem

from .layout import INV_H, Rect

CELL_W = 0x50                   # `0x4a2cf8`: cell k at x = pad + 0x20 + k * 0x50, 80x80 `backinv.bmp` at y = top + 6
ARROW_W = 0x20
CELL_TOP, ARROW_TOP, ARROW_H = 6, 2, 0x58
COUNT_DX, COUNT_DY, KEY_DX, KEY_DY = 3, -0xE, 3, 8      # the "%d" at (cell x + 3, bottom - 14) in font2 / `label`; "F%d" at (cell x + 3, top + 8) in font3 / `highlight`
FRAME = "InvFrame"              # 480x90: the left 0x110 px, then `(W - 0x280) / 0x50` repeats of the slice [0xc0, 0xc0 + 0x110) every 0x50 px, then the right end
FRAME_W, FRAME_LEFT, FRAME_SLICE = 480, 0x110, 0xC0
CAPS = ("inv1024l", "inv1024r")  # 32 x 90 / 48 x 90, only where the side margin is not 0 and H > 600 (1024x768)
CAP_OVERLAP = 16
ARROWS = ("InvArrow1", "InvArrow3", "InvArrow2", "InvArrow4")      # left, left under the pointer, right, right under the pointer
BACK = "backinv"
KIND_SLOT, KIND_PACK, KIND_GROUND = gear.KIND_SLOT, gear.KIND_PACK, gear.KIND_GROUND
FKEYS = 9                       # F4..F12
ENTER_CAST = 10                 # `FUN_00418a02(10)`: the cast mode with a scroll selected (the book stays closed)
T_NO_HERO, T_LEFT, T_RIGHT, T_INVENTORY, T_OPEN, T_CLOSE = 0x33, 0x36, 0x37, 0x3A, 0x0A, 0x0B     # main.txt ids
T_OF, T_TAIL = 0x5A, 0x5B
QUEST, FLAG_FIGHTER, FLAG_MAGE, FLAG_SCROLL = 1, 2, 4, 0x10


def cols(layout):
    """`(W - 160) / 0x50 - 1` (`FUN_004a2bba`: `FUN_0041e250() / 0x50 - 1`, the window width; the right arrow of `0x4a2cf8` and `0x4a3706` agree)."""
    return (layout.size[0] - 160) // CELL_W - 1


def pad(layout):
    """`((W - 0xf0) % 0x50) / 2`: the margin left and right of the arrows (0 at 640 / 800, 32 at 1024)."""
    return ((layout.size[0] - 0xF0) % CELL_W) // 2


def tiles(layout):
    """Number of middle frame slices: `(W - 0x280) / 0x50`."""
    return (layout.size[0] - 0x280) // CELL_W


def caps(layout):
    return CAPS if pad(layout) and layout.size[1] > 600 else None


class Carried(NamedTuple):
    """The carried item (`client+0x3f4` item, `+0x3f8` index, `+0x3fc` kind): `kind` 1 an equipment slot (`index` = slot - 1), 2 a pack entry, `count` pieces of
    `item` (a `saves.Item` with the count of the carried part)."""
    unit: int
    kind: int
    index: int
    count: int
    item: object


class CellView(NamedTuple):
    cell: int                   # 0..cols-1
    pack_index: int
    rect: Rect                  # the 80x80 cell
    item: object                # saves.Item with the displayed count
    key: int                    # the F-key (4..12) bound to the item, 0 for none
    new: bool                   # item flag `0x20`: the "new" twinkle (`twinkle_pixels`)


class PackView(NamedTuple):
    cells: tuple
    left: object                # None or (rect, under the pointer)
    right: object


def swing_locked(u):
    """The weapon-swap lock (`FUN_004a235d`, `FUN_004b012f`, `FUN_004b028d`; CONFIRMED): the hero's client draw state `+0x78` is 3 (attack), 7 (shoot) or 8
    (cast).  The engine has one logical action for all three ("attack", the shared block), so the test is that action together with a server attack / cast state
    (INFERRED mapping: the exe's draw state ends with the action's tick counter, the engine's unit state with the swing)."""
    return u.action == mv.ATTACK and u.state in (mv.ATTACK_STATE, spells_mod.CAST_STATE, spells_mod.CELL_STATE)


TWINKLE_COLOUR = (0xFF, 0, 0xFF)
TWINKLE_TRAIL = (0x3F, 0x7F, 0xBF, 0xFF, 0xBF, 0x7F, 0x3F)     # alpha of the head (counter >> 1) and of the six positions behind it
TWINKLE_SIZE = 0x400


def twinkle_table(seed=1):
    """The two random tables of `FUN_004a147b` (`+0x94` x, `+0x1094` y): 0x400 entries each, `rand() / 0x1ff + 8` (the MSVC LCG `x * 214013 + 2531011`,
    result `(x >> 16) & 0x7fff`, `FUN_00583290`), so a point inside the 80x80 cell.  The exe's seed is the CRT's (time); cosmetic, so `seed` is fixed."""
    state, xs, ys = seed, [], []
    for _ in range(TWINKLE_SIZE):
        pair = []
        for _ in range(2):
            state = (state * 214013 + 2531011) & 0xFFFFFFFF
            pair.append(((state >> 16) & 0x7FFF) // 0x1FF + 8)
        xs.append(pair[0])
        ys.append(pair[1])
    return xs, ys


_BLOB = ((0, 0, 4, 4), (1, 0, 3, 4), (0, 1, 3, 4), (-1, 0, 3, 4), (0, -1, 3, 4), (2, 0, 1, 2), (0, 2, 1, 2), (-2, 0, 1, 2), (0, -2, 1, 2),
         (1, 1, 1, 4), (-1, 1, 1, 4), (1, -1, 1, 4), (-1, -1, 1, 4))      # (dx, dy, num, den): `FUN_0045724a` plots 13 points at alpha * num / den


def twinkle_pixels(counter, table):
    """`FUN_004a285a` for a cell whose frame counter is `counter`: the (dx, dy, alpha) of every blended point relative to the cell origin (`FUN_0045724a`: a plus
    shaped blob, centre alpha, axis neighbours 3/4, distance 2 on the axes 1/2, diagonals 1/4; `FUN_0045705c` blends `TWINKLE_COLOUR` with
    `(255 - a) * dst / 255 + col * a / 255`).  The head is table entry `(counter >> 1) & 0x3ff`, followed by the six entries before it (not below index 0)."""
    xs, ys = table
    h = counter >> 1
    out = []
    for back, a in enumerate(TWINKLE_TRAIL):
        if h - back < 0:
            break
        i = (h - back) & (TWINKLE_SIZE - 1)
        for dx, dy, num, den in _BLOB:
            out.append((xs[i] + dx, ys[i] + dy, a * num // den))
    return out


def item_class(item):
    return (item.code >> 8) & 15


def item_flags(table, item):
    """The wire flag byte `+8` of an item (items 8): class items `suitable_for << 1`; specials by the name prefix: quest 1, book 5, potion 7, scroll `0x17`."""
    r = gear.resolve(table, item)
    if r is None:
        return 0
    d = r.defn
    if d.kind == idefs.SPECIAL:
        return {3: 7, 4: 0x17, 5: 5}.get(d.subtype, QUEST)
    return int(d.fields.get("suitable_for", 0)) << 1


def usable_by(flags, mage):
    """`FUN_0046a9c2`: bit 2 serves a fighter, bit 4 a mage (the hero's `+0x1b8 & 2` is the mage flag)."""
    return bool(flags & (FLAG_MAGE if mage else FLAG_FIGHTER))


def teach_spell(item):
    """`FUN_004b10b0` = the item's property `0x2a` (teach spell): the spell number of a book, 0 for any other item."""
    for m in item.mods:
        if m[0] == idefs.STAT_TEACH:
            return m[1]
    return 0


def scroll_spell(item):
    """`FUN_0041eb20` = the property `0x29` (cast spell) of a scroll, 0 for none."""
    if item_class(item) == spells_mod.SCROLL_CLASS and item.mods and item.mods[0][0] == spells_mod.CAST_SPELL_MOD:
        return item.mods[0][1]
    return 0


class PackWindow:
    def __init__(self, layout):
        self.layout = layout
        self.open = False
        self.unit = None                    # the shown hero (`+0x84` list owner): the single selected hero, None = "No hero selected"
        self.offsets = {}                   # unit id -> the first shown pack index (the exe keeps it in the unit, `unit+0xe4`)
        self.carried = None
        self.item_keys = [None] * FKEYS     # client table `0x4dc` entries of type 2: per F4..F12 the bound (code, mods) or None
        self.left_held = False

    # -- geometry (4a2cf8, 4a35c0, 4a3706) -----------------------------------------------------------------------------------------
    @property
    def rect(self):
        w, h = self.layout.size
        return Rect(0, h - INV_H, w - 160, INV_H)

    def contains(self, pos):
        return self.open and pos is not None and self.rect.contains(*pos)

    @property
    def cols(self):
        return cols(self.layout)

    def cell_rect(self, k):
        r = self.rect
        return Rect(r.x + pad(self.layout) + ARROW_W + k * CELL_W, r.y + CELL_TOP, CELL_W, CELL_W)

    def left_arrow_rect(self):
        r = self.rect
        return Rect(r.x, r.y, pad(self.layout) + ARROW_W, r.h)

    def right_arrow_rect(self):
        r, p = self.rect, pad(self.layout)
        x = r.x + p + ARROW_W + self.cols * CELL_W
        return Rect(x, r.y, p + ARROW_W, r.h)

    def frame_blits(self):
        """`(art, source x, source width, x)` in draw order (y = the window top): the left piece, the slices, the caps (1024 only), the right end."""
        r, p = self.rect, pad(self.layout)
        out = [(FRAME, 0, FRAME_LEFT, r.x + p)]
        for i in range(tiles(self.layout)):
            out.append((FRAME, FRAME_SLICE, FRAME_LEFT, r.x + p + FRAME_LEFT + i * CELL_W))
        c = caps(self.layout)
        if c:
            out.append((c[0], 0, None, r.x))
            out.append((c[1], 0, None, r.x + r.w - p - CAP_OVERLAP))
        out.append((FRAME, FRAME_LEFT, None, r.x + r.w - p - FRAME_W + FRAME_LEFT))
        return out

    def index_at(self, pos, strict=False, count=0):
        """`FUN_004a35c0`: the pack index under `pos` (screen pixels), -1 for none.  `strict` (negative y in the exe: pick-up and double click): only a cell of the
        strip.  Else (drop): left of the first cell gives the first shown index, right of the last cell the last shown one when the pack goes on, and an index
        past the pack is -1."""
        if self.unit is None:
            return -1
        p, off, n = pad(self.layout), self.offset(), self.cols
        x = pos[0] - self.rect.x
        if strict:
            if x < p + ARROW_W or x >= p + ARROW_W + n * CELL_W:
                return -1
        else:
            if x < p + ARROW_W:
                return off
            if x >= p + ARROW_W + n * CELL_W and off + n - 1 < count:
                return off + n - 1
        i = off + (x - ARROW_W - p) // CELL_W
        return -1 if i >= count else i

    # -- the shown unit, the scroll offset -----------------------------------------------------------------------------------------
    def set_unit(self, world, selection, player_id):
        """`FUN_004167c2` (end): the pack list is the selected unit's when exactly one unit is selected and it is a hero (`+0x144 & 8`), else none."""
        uid = None
        if len(selection) == 1:
            u = world.units.get(selection[0])
            if u is not None and u.human and _hero(u):
                uid = u.id
        if uid != self.unit:
            self.unit = uid

    def unit_obj(self, world):
        return world.units.get(self.unit) if self.unit is not None else None

    def pack_of(self, world):
        """The displayed pack: the unit's with the carried pieces taken out (the exe removes them from its list at the pick-up, `FUN_004a218b`)."""
        u = self.unit_obj(world)
        if u is None:
            return []
        pack = list(u.pack)
        c = self.carried
        if c is not None and c.unit == u.id and c.kind == KIND_PACK:
            gear.pack_take(pack, c.index, c.count)
        return pack

    def offset(self):
        return self.offsets.get(self.unit, 0)

    def clamp(self, count):
        """`FUN_004a16d8` (virtual `+0x98`, after every list change): the offset never leaves `count - cols` .. 0."""
        if self.unit is None:
            return
        off = self.offset()
        if count - off < self.cols:
            off = count - self.cols
        self.offsets[self.unit] = max(off, 0)

    def scroll(self, d, count):
        """`FUN_004a1bff` (-1, only when the offset is not 0) / `FUN_004a1a78` (+1, only when the pack goes on past the last cell)."""
        off = self.offset()
        if d < 0 and off != 0:
            self.offsets[self.unit] = off - 1
        elif d > 0 and off + self.cols < count:
            self.offsets[self.unit] = off + 1

    # -- open / close ----------------------------------------------------------------------------------------------------------------
    def toggle(self):
        """Message `0x40e` (I, the backquote key, Space, the info panel's pack button): close when open, else open."""
        self.close() if self.open else self.open_pack()

    def open_pack(self):
        self.open = True

    def close(self):
        self.open = False
        self.left_held = False

    # -- drawing data ----------------------------------------------------------------------------------------------------------------
    def views(self, world, mouse=None):
        """What `0x4a2cf8` draws: the cell items with their counts and F labels, the arrows (left only when the offset is not 0, right only when the pack
        goes on) in their pointer state.  `PackView(cells=(), None, None)` for a window without a hero."""
        u = self.unit_obj(world)
        if u is None:
            return PackView((), None, None)
        pack = self.pack_of(world)
        self.clamp(len(pack))
        off, n = self.offset(), self.cols
        cells = []
        for k in range(n):
            i = off + k
            if i >= len(pack) or not pack[i].code:
                continue
            it = pack[i]
            cells.append(CellView(k, i, self.cell_rect(k), it, self.key_of(it), bool(it.new)))
        la, ra, r, p = self.left_arrow_rect(), self.right_arrow_rect(), self.rect, pad(self.layout)
        left = right = None
        if off != 0:                                # `0x4a2cf8`: the arrow art is blitted 2 px below the top, 32 x 88 px, lit while the pointer is in the arrow rect
            left = (Rect(r.x + p, r.y + ARROW_TOP, ARROW_W, ARROW_H), mouse is not None and la.contains(*mouse))
        if len(pack) > off + n:
            right = (Rect(ra.x, r.y + ARROW_TOP, ARROW_W, ARROW_H), mouse is not None and ra.contains(*mouse))
        return PackView(tuple(cells), left, right)

    def key_of(self, item):
        """The F-key whose type-2 table entry matches the item (`FUN_0041ddea`: the item code and the modifier bytes); the last match in the loop's order wins
        its break, i.e. the first."""
        for i, e in enumerate(self.item_keys):
            if e is not None and e == (item.code & 0xFFFF, tuple(item.mods)):
                return i + 4
        return 0

    # -- tooltip (FUN_004a3f0b) --------------------------------------------------------------------------------------------------------
    def tooltip_text(self, pos, world, main, mode_ok=True, frozen=False):
        """Text under the pointer: nothing while an item is carried or outside the mission mode; main.txt 0x36 over the left arrow strip, 0x37 over the right
        one, 0x3a over an empty cell or without a hero, else the item's tooltip (`item_tooltip`, `FUN_0043901f`)."""
        if frozen or not mode_ok or self.carried is not None or not self.contains(pos):
            return ""
        p, n = pad(self.layout), self.cols
        x = pos[0] - self.rect.x
        if x < p + ARROW_W:
            return main.line(T_LEFT)
        if x >= p + ARROW_W + n * CELL_W:
            return main.line(T_RIGHT)
        if self.unit is None:
            return main.line(T_INVENTORY)
        pack = self.pack_of(world)
        i = self.offset() + (x - ARROW_W - p) // CELL_W
        if i >= len(pack):
            return main.line(T_INVENTORY)
        if not pack[i].code:
            return ""
        return item_name(world, pack[i], main)

    # -- the mouse (vtable +0x4c .. +0x64 of the window) ----------------------------------------------------------------------------------
    def left_down(self, pos, world):
        """`0x4a3706`: a press on the left / right arrow scrolls one item; the press is always consumed."""
        self.left_held = True
        count = len(self.pack_of(world))
        if self.unit is not None:
            if self.left_arrow_rect().contains(*pos):
                self.scroll(-1, count)
            if self.right_arrow_rect().contains(*pos):
                self.scroll(+1, count)
        return True

    def left_up(self, pos, world, player_id):
        """`0x4a399a`: a carried item is put into the pack at the index under the pointer (`FUN_004a24e8`).  Returns the commands."""
        self.left_held = False
        c = self.carried
        if self.unit is None or c is None:
            return ()
        pack = self.pack_of(world)
        dst = self.index_at(pos, False, len(pack))
        return self.drop_in_pack(world, player_id, dst)

    def drop_in_pack(self, world, player_id, dst):
        """`FUN_004a24e8(index)`: the move `0x22` from the carried item's place to the pack at `dst`, then the cursor is cleared.  A pack item put back at the
        place it came from sends nothing (the server move would end where it began)."""
        c = self.carried
        self.carried = None
        u = self.unit_obj(world)
        if c is None or u is None:
            return ()
        if c.kind == KIND_PACK and (dst < 0 or dst == c.index):
            return ()
        return (MoveItem(player_id, u.id, c.kind, KIND_PACK, c.index, gear.APPEND if dst < 0 else dst, c.count),)

    def mouse_move(self, pos, left_held, world, player_id, shift=False):
        """`0x4a3a1d` (flag `MK_LBUTTON`, nothing carried): a cell under the pointer is picked up (`FUN_004a235d` -> the pointer shows the item): one piece, the
        whole stack with Shift (`DAT_006227dc`).  Needs the hero to be the player's own."""
        if not left_held or self.carried is not None or not self.contains(pos):
            return False
        return self.pick(pos, world, player_id, shift)

    def pick(self, pos, world, player_id, shift=False, count=None):
        u = self.unit_obj(world)
        pack = self.pack_of(world)
        i = self.index_at(pos, True, len(pack))
        if u is None or i < 0 or not pack[i].code or u.owner != player_id:
            return False
        it = pack[i]
        if item_class(it) < 2 and swing_locked(u):
            return False                            # `FUN_004a235d`: no weapon out of the pack while the hero attacks / shoots / casts
        n = it.count if shift else 1
        n = max(1, min(n if count is None else count, it.count))
        self.carried = Carried(u.id, KIND_PACK, i, n, replace(it, count=n))
        return True

    def double_click(self, pos, world, player_id, ordering=None):
        """`0x4a37f3`: the item under the pointer (a quest treasure excepted) is picked up (one piece) and put to the hero as by a release on the info panel:
        a weapon / shield / armour piece is worn, a potion or book used, a scroll selected for casting.  Returns the commands."""
        pack = self.pack_of(world)
        i = self.index_at(pos, True, len(pack))
        if i < 0 or not pack[i].code or not self.pick(pos, world, player_id):
            return ()
        return self.equip_carried(world, player_id, ordering)

    # -- the item rules of the info panel (FUN_004b028d) ------------------------------------------------------------------------------
    def equip_carried(self, world, player_id, ordering=None):
        """`FUN_004b028d(class - 1)` for the carried item: a release on the info panel, a double click on a pack cell, an F-key.  Rejected (put back, `FUN_004a24e8`)
        when the hero cannot use the item (`FUN_0046a9c2`), for a quest item and for a book the hero cannot learn (not a mage, or the spell is known:
        `FUN_004b10b0`).  A scroll goes back and becomes the cast item (`FUN_004c7143`, mode `FUN_00418a02(10)`).  Another special item (potion, book) is split to
        one piece and sent to the hero; a class item is worn.  Nothing happens (the item stays carried) for a hero that is not the player's."""
        c, u = self.carried, self.unit_obj(world)
        if c is None or u is None or u.owner != player_id:
            return ()
        table = world.item_table
        flags = item_flags(table, c.item)
        mage = gear.is_mage(u)
        bad = not usable_by(flags, mage) or (flags & 6) == 0
        if 0 <= item_class(c.item) - 1 < 2 and swing_locked(u):
            bad = True                              # `FUN_004b028d`: slot (class - 1) < 2 while the hero attacks / shoots / casts
        t = teach_spell(c.item)
        if t and (not mage or (spells_mod.known_mask(u) >> t) & 1):
            bad = True
        if bad:
            return self.drop_in_pack(world, player_id, c.index if c.kind == KIND_PACK else 0)
        cls = item_class(c.item)
        if flags & FLAG_SCROLL and flags & 1:
            index = c.index if c.kind == KIND_PACK else gear.APPEND
            cmds = self.drop_in_pack(world, player_id, c.index if c.kind == KIND_PACK else -1)
            if ordering is not None:
                pack = list(u.pack)
                if c.kind != KIND_PACK:
                    index = len(pack)               # filed at the end by the move just returned (applied next tick)
                ordering.select_scroll(index, scroll_spell(c.item), u.id)
            return cmds
        n = c.item.count
        if flags & 1 and n > 1:
            n = 1                                   # the rest returns to the pack (`FUN_00438b13` clones, the carried piece keeps 1)
        self.carried = None
        return (MoveItem(player_id, u.id, c.kind, KIND_SLOT, c.index, cls, n),)

    # -- F keys (FUN_004a3cef, message 0x417) ---------------------------------------------------------------------------------------------
    def bind_key(self, n, pos, world):
        """Ctrl+F<n> (4..12) over a pack cell: the item is bound to the key (type 2) and the key is cleared where the same item is bound elsewhere.  Returns
        whether a cell was under the pointer."""
        pack = self.pack_of(world)
        i = self.index_at(pos, True, len(pack)) if pos is not None and self.contains(pos) else -1
        if i < 0 or not pack[i].code:
            return False
        e = (pack[i].code & 0xFFFF, tuple(pack[i].mods))
        for j in range(FKEYS):
            if j != n - 4 and self.item_keys[j] == e:
                self.item_keys[j] = None
        self.item_keys[n - 4] = e
        return True

    def use_key(self, n, world, player_id, ordering=None):
        """F<n> without Ctrl with an item bound: the first pack item that matches is picked up (one piece) and put to the hero.  Returns the commands."""
        e = self.item_keys[n - 4] if 0 <= n - 4 < FKEYS else None
        u = self.unit_obj(world)
        if e is None or u is None or self.carried is not None or u.owner != player_id:
            return ()
        pack = self.pack_of(world)
        for i, it in enumerate(pack):
            if (it.code & 0xFFFF, tuple(it.mods)) == e:
                self.carried = Carried(u.id, KIND_PACK, i, 1, replace(it, count=1))
                return self.equip_carried(world, player_id, ordering)
        return ()

    # -- the view's release (FUN_0040c5d1) --------------------------------------------------------------------------------------------------
    def drop_on_ground(self, world, player_id, cell):
        """The left release in the map with an item carried: a move `0x22` to the ground at `cell` (the hero's cell, or the cell of a friendly unit within
        2 cells that is hovered), the cursor is cleared."""
        c = self.carried
        self.carried = None
        u = self.unit_obj(world)
        if c is None or u is None or u.owner != player_id:
            return ()
        return (MoveItem(player_id, u.id, c.kind, KIND_GROUND, c.index, cell[0] | cell[1] << 8, c.count),)

    def cancel_carry(self):
        self.carried = None

    # -- the doll (FUN_004af120, FUN_004aeabb) -------------------------------------------------------------------------------------------
    def pick_equipped(self, world, player_id, slot):
        """`FUN_004b012f(slot)`: a left-held move over a doll layer (hit mask id `slot + 1`) takes the equipped item into the cursor (an own hero only)."""
        u = self.unit_obj(world)
        if u is None or self.carried is not None or u.owner != player_id or not 0 <= slot < gear.SLOT_COUNT:
            return False
        if slot < 2 and swing_locked(u):
            return False                            # `FUN_004b012f`: weapon and shield stay while the hero attacks / shoots / casts
        item = (gear.slots_of(u) if u.equipment else {}).get(slot + 1)
        if item is None and not u.equipment:
            r = _template_item(world, u, slot + 1)
            item = r
        if item is None:
            return False
        self.carried = Carried(u.id, KIND_SLOT, slot, 1, item)
        return True

    def unequip(self, world, player_id, slot):
        """The double click on a doll layer: the item is taken (`FUN_004b012f`) and put into the pack at the end (`FUN_004a24e8`)."""
        if not self.pick_equipped(world, player_id, slot):
            return ()
        return self.drop_in_pack(world, player_id, -1)


def hidden_slot(carried, u):
    """The creature slot of `u` whose item is on the cursor (`FUN_004b012f` empties the client slot at the pick-up), 0 when none is."""
    return carried.index + 1 if carried is not None and carried.kind == KIND_SLOT and u is not None and carried.unit == u.id else 0


def _hero(u):
    from . import info
    return info.is_hero(u)


def _template_item(world, u, slot):
    """The `saves.Item` of a template-equipped hero's slot (the unit has no explicit loadout yet): the equip command works on `ensure_loadout`."""
    from . import info
    from engine.sim import combatstats
    r = info.equipped_items(world, u).get(slot)
    if r is None:
        return None
    from allods2.formats import saves
    return saves.Item(combatstats.item_code(r), 1)


def item_name(world, item, main):
    """The tooltip of an item (`FUN_0043901f`): `item_tooltip` when the table has the `itemname.pkt` record of the code, else the bare `ItemTable.display_name`
    (the `itemname.txt` name, then for a teachSpell / castSpell effect `" of <spell>"`, main.txt 0x5a / 0x5b)."""
    table = world.item_table
    if table is None:
        return ""
    pk = table.packets.get(item.code & 0xFFFF)
    if pk is not None and table.names.get(item.code & 0xFFFF) is not None:
        return item_tooltip(world, item.code, pk, main, item.mods)
    name = table.display_name(item.code, gear.effects_of(item.mods), None, main.line(T_OF), main.line(T_TAIL))
    return name or ""


T_CASTS, T_CASTS_TAIL, T_WEIGHT = 0x5C, 0x5D, 0xBD
T_DAMAGE, T_RANGE, T_DURATION = 0x76, 0x7B, 0x7C
TAG_PRICE, TAG_RANGE, TAG_CAST, TAG_TEACH, TAG_SCROLL, TAG_SPECIAL = 1, 0x26, 0x29, 0x2A, 0x32, 0x33
TAG_DAMAGE = (0x0D, 0x2C, 0x2D, 0x2E, 0x2F, 0x30)       # a (stat, min) pair followed by the (spread) pair: `#name min-max`
TAG_PERCENT = (0x0B, 0x08)                                # a "%" follows the `%+d` value
STONE_CURSE = 0x12


def item_tooltip(world, code, pk, main, mods=()):
    """`FUN_0043901f` over the `itemname.pkt` descriptor `pk` (CONFIRMED): the `itemname.txt` name, then one entry per payload tag (`#` = the tooltip's line
    break, `stats.txt` line `tag` = the stat name): price `01` skipped (5 bytes); `#Name +v` (`%+d`, a `%` after for tags 8 and 11); damage tags (13, 44-48)
    `#Name min-max` (the next pair's value is added, two entries); range 38 `#Name v`; 41 castSpell: class 14 `" of Spell"` else `#casts Spell`; 42 teachSpell
    `" of Spell"`; 50 (scrolls) the spell rows at that power; 51 `#Weight`-line text for a non-special item.  The spell rows use the same scaling as the
    spell book tooltip (`spellbook._helper`, `Scaled`)."""
    from . import spellbook
    table = world.item_table
    stats = table.stat_texts
    special = (code >> 8) & 15 == 14
    out = [table.names.get(code & 0xFFFF) or ""]
    pl, p, i, n = pk.payload, 0, 0, pk.header[3]
    if mods:
        extra = [b"\x33\x00"]
        for m in mods:
            extra.append(bytes((m[0] & 0xFF, m[1] & 0xFF)))
            if 44 <= m[0] <= 48:
                extra.append(bytes((m[0] & 0xFF, m[2] & 0xFF)))
        pl = pl + b"".join(extra)
        n += 1 + sum(2 if 44 <= m[0] <= 48 else 1 for m in mods)
    spell = 0

    def stat(tag):
        return stats[tag] if 0 <= tag < len(stats) else ""

    def spell_name(number):
        sp = world.spell_table.get(number) if world.spell_table is not None else None
        if sp is not None and sp.display_name:
            return sp.display_name
        return table.spells[number - 1][0] if 0 < number <= len(table.spells) else ""

    while i < n and p < len(pl):
        tag = pl[p]
        p += 1
        v = pl[p] if p < len(pl) else 0
        if tag == TAG_PRICE:
            p += 4
        elif tag in TAG_DAMAGE:
            name = stat(tag)
            p += 2
            if name:
                out.append("#%s %d" % (name, v))
            v += pl[p] if p < len(pl) else 0
            p += 1
            out.append("-%d" % v)
            i += 1
        elif tag == TAG_RANGE:
            p += 1
            if stat(tag):
                out.append("#%s %d" % (stat(tag), v))
        elif tag == TAG_CAST:
            p += 1
            spell = v
            if special:
                out.append(" %s %s%s" % (main.line(T_OF), spell_name(v), main.line(T_TAIL)))
            else:
                out.append("#%s %s%s" % (main.line(T_CASTS), spell_name(v), main.line(T_CASTS_TAIL)))
        elif tag == TAG_TEACH:
            p += 1
            out.append(" %s %s%s" % (main.line(T_OF), spell_name(v), main.line(T_TAIL)))
        elif tag == TAG_SCROLL:
            p += 1
            out.extend(_spell_rows(world, spell, v, special, main, spellbook))
        elif tag == TAG_SPECIAL:
            p += 1
            if not special:
                out.append("#" + main.line(T_WEIGHT))
        else:
            p += 1
            if stat(tag):
                out.append("#%s %+d" % (stat(tag), v))
            if tag in TAG_PERCENT:
                out.append("%")
        i += 1
    return "".join(out)


def _spell_rows(world, number, level, special, main, sb):
    """The rows of tag 50 (`0x4393xx`-`0x4397xx`): the spell `number` of the preceding castSpell tag scaled at `level` (`FUN_0051906d` / `FUN_005195b1`):
    damage (only with a spread; `lo-hi`), range (class 14 only), duration (`%5.1f` ticks / 16; spell 0x12 halves it and prints `0.0 -x`), then the one helper row."""
    sp = world.spell_table.get(number) if world.spell_table is not None else None
    if sp is None:
        return []
    sc = sp.scaled(level)
    out = []
    lo, spread = sc.damage_min & 0xFF, sc.damage_spread & 0xFF
    if spread:
        out.append("#%s: %d-%d" % (main.line(T_DAMAGE), lo, lo + spread))
    if special and sc.max_range & 0xFF:
        out.append("#%s: %d" % (main.line(T_RANGE), sc.max_range & 0xFF))
    dur = sc.duration & 0xFFFF
    if number == STONE_CURSE:
        dur >>= 1
    if dur:
        out.append(("#%s: 0.0 -%5.1f" if number == STONE_CURSE else "#%s: %5.1f") % (main.line(T_DURATION), dur / 16.0))
    h = sb._helper(number, level)
    if h is not None:
        label, val = h
        fmt = {sb.L_SPEED: "%d", sb.L_SIGHT: "%d", sb.L_RAYS: "%d", sb.L_RESISTANCE: "+%d", sb.L_MAX_PROB: "+%d%%", sb.L_MIN_PROB: "+%d%%"}.get(label)
        if fmt is not None and val != 0:           # the absorption helper has no row in the item tooltip
            out.append("#%s: %s" % (main.line(label), fmt % val))
    return out


def button_text(open_, main):
    """`FUN_004ae232` (window 7 tooltip hook): the info panel's pack button shows main.txt 0xa (closed) / 0xb (open)."""
    return main.line(T_CLOSE if open_ else T_OPEN)


def doll_tip(world, ui, slot):
    """The tooltip over a paper-doll layer: the equipped item's name (`FUN_0043901f`, only for a unit of the viewer's side: `FUN_0041e860`; the hit mask id
    `slot + 1` selects `unit +0x184 + id * 4`)."""
    u = ui.pack.unit_obj(world)
    if u is None or u.owner != ui.player_id:
        return ""
    from . import info
    r = info.equipped_items(world, u).get(slot + 1)
    if r is None:
        return ""
    from engine.sim import combatstats
    from allods2.formats import saves
    return item_name(world, saves.Item(combatstats.item_code(r), 1), ui.main)
