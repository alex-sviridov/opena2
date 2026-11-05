"""The spell book window (bottom bar id 3, class `FUN_004c61e7`; docs/engine/ui-layout.md 11.12).  Pure state and hit rects: the backend draws it
(`Panels.draw_book`), `GameUi` routes the mouse, `OrderInput` keeps the selected slot (`panel+0x60`) and the cast mode.  No pygame.

The window is a child of the game view that exists only while it is open (open = `FUN_0041af4a`, close = `FUN_0041b077`, "is open" = `FUN_0041aef1`)."""

from typing import NamedTuple

from . import spellbook
from .layout import Rect

COLS, ROWS, SLOTS = 12, 2, 24
PITCH = 38                              # `FUN_004c6ac1`: slot k at (6 + (k % 12) * 38, 6 + (k / 12) * 38), a 36x36 tile
TILE = 36
DRAW_ORIGIN = 6
HIT_ORIGIN = 5                          # `FUN_004c6fe0`: the point is moved by (-5, -5) and by the centring offset, then x < 0x1c8, y < 0x4b
HIT_W, HIT_H = 0x1C8, 0x4B
FRAME_W = 480                           # SpellBook.bmp 480x85
LABEL_X, FKEY_Y, AUTO_Y, SELECTED_SHIFT = 2, 2, 28, 2   # labels at (8, 8) / (8, 0x22) from the cell origin = (2, 2) / (2, 28) from the tile; a selected slot's labels move by (2, 2)
FKEY_FONT, AUTO_FONT = 3, 3             # the font object `DAT_00620e30` = font3 (fonts.md), colour table 0x620928 ("normal")
HIGHLIGHT_LEVEL = 4                     # `FUN_004565cd(l, t, l + 36, t + 36, 4)`: a veil over the selected tile
FRAME, TILE_ART = "SpellBook", "SpellBack"
CAPS = {(800, 600): ("spb800l", "spb800r"), (1024, 768): ("spb1024l", "spb1024r")}   # none at 640x480
CAP_OVERLAP = 16                        # the right cap starts at frame x + 480 - 16 and the frame is drawn over it
L_OPEN, L_CLOSE = 8, 9                  # main.txt: "Open Spellbook <Q>,<B>" / "Close Spellbook <Q>,<B>" (the info panel button's tooltip)
CAST = 5                                # pending mode 5 (cast): opening it opens the book, leaving it closes the book


class SlotView(NamedTuple):
    slot: int
    rect: Rect
    enabled: bool       # the bit is in `view+0x148 | view+0x150`; a disabled slot is covered with SpellBack.bmp
    selected: bool      # `panel+0x60`, drawn only for an enabled slot
    fkey: int           # the F-key (4..12) bound to the slot (the last table entry wins), 0 for none; drawn only for an enabled slot
    auto: bool          # `view+0x14c`: the auto-cast spell of a selected unit (Ctrl+A), label "A"


def frame_dx(layout):
    """`DAT_00621420` = (W - 640) / 2: the frame is centred in the window, the caps fill the sides (0 at 640x480)."""
    return (layout.size[0] - 640) // 2


def caps(layout):
    return CAPS.get(layout.size)


class SpellBookWindow:
    def __init__(self, layout):
        self.layout = layout
        self.open = False
        self.inventory_open = False         # window 2 (not built): the book then sits above it
        self.left_held = self.right_held = False

    # -- geometry ------------------------------------------------------------------------------------------------------------------
    @property
    def rect(self):
        return self.layout.book_rect(self.inventory_open)

    def contains(self, pos):
        return self.open and pos is not None and self.rect.contains(*pos)

    def tile_rect(self, slot):
        r = self.rect
        return Rect(r.x + frame_dx(self.layout) + DRAW_ORIGIN + (slot % COLS) * PITCH, r.y + DRAW_ORIGIN + (slot // COLS) * PITCH, TILE, TILE)

    def slot_at(self, pos):
        """`FUN_004c6fe0`: the slot under `pos`, -1 outside the 12x2 grid.  A cell spans 38 px from 5 px before the tile (the 2 px gap belongs to the left cell)."""
        r = self.rect
        x, y = pos[0] - r.x - HIT_ORIGIN - frame_dx(self.layout), pos[1] - r.y - HIT_ORIGIN
        if x < 0 or y < 0 or y >= HIT_H or x >= HIT_W:
            return -1
        return (y // PITCH) * COLS + x // PITCH

    # -- open / close --------------------------------------------------------------------------------------------------------------
    def open_book(self):
        self.open = True

    def close(self):
        self.open = False
        self.left_held = self.right_held = False

    def toggle(self):
        """Message `0x40f` (B / Q, the info panel's book button, Space): close when open, else open."""
        self.close() if self.open else self.open_book()

    def pending_changed(self, old, new):
        """`FUN_00418a02` / `FUN_00416388` / `FUN_004175c7`: leaving the cast mode (any other mode, the release, the right click) closes an open book."""
        if old == CAST and new != CAST and self.open:
            self.close()

    # -- drawing data --------------------------------------------------------------------------------------------------------------
    def views(self, mask, selected, hotkeys=(), auto_mask=0):
        """The 24 `SlotView`s.  `mask` = `view+0x148 | 0x150`, `selected` = `panel+0x60`, `hotkeys` = the F4..F12 table (bound slot or None), `auto_mask` = `view+0x14c`."""
        out = []
        for s in range(SLOTS):
            en = bool((mask >> s) & 1)
            fk = 0
            for i, h in enumerate(hotkeys):
                if h == s:
                    fk = i + 4
            out.append(SlotView(s, self.tile_rect(s), en, en and selected == s, fk if en else 0, bool((auto_mask >> s) & 1)))
        return out

    # -- mouse (vtable +0x4c .. +0x64 of the window) ---------------------------------------------------------------------------------
    def left_down(self, pos, ordering):
        """`0x4c7580`: the slot under the pointer becomes the selection only when it is enabled (`+0x148 | +0x150`).  The press is always consumed."""
        self.left_held = True
        ordering.select_slot(self.slot_at(pos))
        return True

    def left_up(self):
        """`0x4c76bc`: only drops a carried backpack item (not built); the press ends here."""
        self.left_held = False

    def double_click(self, pos, ordering, knows):
        """`0x4c7604`: an enabled slot whose spell needs no target (`spellbook.INSTANT`) is cast at once: every selected unit that has it casts it on itself
        (`FUN_00419a54`, command `0x1e` with the unit as its own target, one message per unit; the scroll branch needs the backpack: not built).  Then the
        slot is selected as by a press.  Returns the commands."""
        slot = self.slot_at(pos)
        cmds = ()
        if slot >= 0 and ordering.slot_enabled(slot) and spellbook.INSTANT[slot]:
            cmds = ordering.instant_cast(slot, knows)
        self.left_down(pos, ordering)
        return cmds

    def mouse_move(self, pos, left, right, ordering):
        """`0x4c77a2`: a move over the window with the left button held (pressed in it) selects the slot under it, with the right button deselects."""
        if not self.contains(pos):
            return
        if left and self.left_held:
            ordering.select_slot(self.slot_at(pos))
        if right and self.right_held:
            ordering.deselect_slot()

    def right_down(self, pos, ordering):
        """`0x4c75e8` / `0x4c7786`: the selected slot becomes -1.  The press is consumed: the right release does not reach the view (no cancel, no deselect)."""
        self.right_held = True
        ordering.deselect_slot()
        return True

    def right_up(self):
        self.right_held = False

    # -- tooltip -------------------------------------------------------------------------------------------------------------------
    def tooltip_text(self, pos, world, selection, mask, lines, labels, frozen=False):
        """`FUN_004c628f`: the text of the slot under `pos`: only for a slot in the unit mask `view+0x148` (a scroll-only slot has none), in the mission mode."""
        if frozen or not self.contains(pos):
            return ""
        slot = self.slot_at(pos)
        if slot < 0 or not (mask >> slot) & 1:
            return ""
        for e in spellbook.spellbook(world, selection, lines):
            if e.slot == slot:
                return spellbook.tooltip(e, labels)
        return ""


def button_text(open_, main):
    """`FUN_004ae232` (window 7 tooltip hook): the info panel's book button shows main.txt 8 (closed) or 9 (open)."""
    return main.line(L_CLOSE if open_ else L_OPEN)


def draw_views(window, ordering, world, selection, own=True):
    """The slot views of an open book for the player's selection (`own`: the selection is the player's own, else nothing is enabled and no unit has an auto-cast)."""
    auto = spellbook.auto_slot_mask(world, selection) if own else 0
    return window.views(ordering.slot_mask() if own else 0, ordering.slot, ordering.hotkeys, auto)
