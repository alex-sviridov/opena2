"""Modal windows (docs/engine/ui-layout.md 11.4, 11.5): the menu, End Quest, pause, story and mission-result dialogs as data.

A `Dialog` is a frame rect, an optional text and a list of `DButton`s (rect, label, enabled, action).  `ModalStack` is the
UI layer's one object the backend loop reads: while it is not empty every dialog freezes the simulation (the exe's mode bit 8).
Actions are tuples: ("close",) the top dialog, ("return",) every dialog (Return to Game), ("open", kind), ("quit", reason),
("noop",).  No pygame here."""

import re
from dataclasses import dataclass, field

from . import story as story_mod
from .layout import Rect
from .widgets import FONT1_PITCH, button_rect, centred, complete_window, failed_window, text_window, widget_rect

# dialogs.txt ids (single-player entries of the menu) and main.txt ids
D_SAVE, D_LOAD, D_OPTIONS, D_SOUND, D_OBJECTIVES, D_ENDQUEST, D_RETURN = 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28
D_VICTORY, D_EXIT_MENU, D_EXIT_WINDOWS, D_CONTINUE = 0x2B, 0x2C, 0x2D, 0x9A
M_OK, M_PAUSED, M_COMPLETE, M_FAILED = 0x4D, 0x77, 0x8C, 0x8D

CLOSE, RETURN, NOOP = ("close",), ("return",), ("noop",)


@dataclass(frozen=True)
class DButton:
    rect: Rect
    label: str
    enabled: bool
    action: tuple
    key: str = ""                   # hotkey letter (the `~x` of the label), lower case


@dataclass
class Dialog:
    kind: str                       # "menu" | "endquest" | "pause" | "story" | "complete" | "failed"
    frame: Rect
    buttons: tuple
    text: str = ""
    text_rect: Rect = None
    lines: tuple = ()               # the text wrapped to `text_rect.w` (text windows; empty = the backend wraps `text` itself)
    caption: str = ""               # a text window's caption line (`0x443238`), drawn left at `caption_rect`
    caption_rect: Rect = None
    align: str = "center"           # "left" for the text widget of the message windows (`FUN_0045e01d`), "center" for the old story drawing
    table: str = "normal"           # colour table name of text and caption
    pitch: int = FONT1_PITCH        # line pitch of `lines` (font height + 2)
    escape: tuple = CLOSE           # the action of ESC (the dialog's key handler: message 0x446 = Return to Game)
    enter: tuple = None             # the action of Enter (our DECISION: the single button of a notice window)
    story: object = None            # `StoryState` of a story window
    picture: Rect = None            # the story window's speaker picture widget (None = the layout without `npc`)
    picture_unit: int = None        # engine id of the unit whose portrait it shows (None = blank)

    def button_at(self, pos):
        """Index of the enabled-or-not button under `pos`, or None."""
        for i, b in enumerate(self.buttons):
            if b.rect.contains(*pos):
                return i
        return None

    def click(self, pos):
        """The left click: the action of the enabled button under `pos`, else None (clicks never pass through a modal)."""
        i = self.button_at(pos)
        if i is not None and self.buttons[i].enabled:
            return self.buttons[i].action
        return None

    def key(self, name):
        """A key name ('escape', 'return' or a lower-case letter): the action it triggers, or None."""
        if name == "escape":
            return self.escape
        if name == "return":
            return self.enter
        for b in self.buttons:
            if b.enabled and b.key == name:
                return b.action
        return None


def split_label(label):
    """('Save Game', 's') from the `~Save Game` hotkey syntax: the text keeps the `~` (the font draws the underline), the key is the letter after it."""
    m = re.search(r"~(.)", label)
    return label, (m.group(1).lower() if m else "")


def _buttons(frame, entries):
    """`entries`: (label, enabled, action) in stack order -> DButtons with the dialog button rule (x 0x28.., pitch 0x1e)."""
    out = []
    for k, (label, enabled, action) in enumerate(entries):
        text, key = split_label(label)
        out.append(DButton(button_rect(frame, k), text, enabled, action, key))
    return tuple(out)


def menu_dialog(layout, dialogs):
    """The in-game menu (message `0x416`): Save, Load, Options, Sound, Objectives, End Quest, Return.  Entries whose window is not built (phase K) are
    disabled (DECISION: the exe enables them; they would do nothing)."""
    frame = widget_rect(layout, "menu.frame")
    entries = [(dialogs(D_SAVE), False, NOOP), (dialogs(D_LOAD), False, NOOP), (dialogs(D_OPTIONS), False, NOOP),
               (dialogs(D_SOUND), False, NOOP), (dialogs(D_OBJECTIVES), False, NOOP),
               (dialogs(D_ENDQUEST), True, ("open", "endquest")), (dialogs(D_RETURN), True, RETURN)]
    return Dialog("menu", frame, _buttons(frame, entries), escape=RETURN)


def endquest_dialog(layout, dialogs, mission_complete):
    """End Quest (`0x41c`): Victory! (only after the mission is complete), Exit to Main Menu, Exit to Windows, Return.  Both exits end the program in J1."""
    frame = widget_rect(layout, "endquest.frame")
    entries = [(dialogs(D_VICTORY), bool(mission_complete), ("quit", "victory")),
               (dialogs(D_EXIT_MENU), True, ("quit", "menu")),
               (dialogs(D_EXIT_WINDOWS), True, ("quit", "windows")),
               (dialogs(D_RETURN), True, RETURN)]
    return Dialog("endquest", frame, _buttons(frame, entries), escape=RETURN)


def plain_wrap(text, width):
    """The default `wrap` (no font, synthetic tests): one line per paragraph."""
    return text.split("\n")


def _rect(frame, r):
    return Rect(frame.x + r[0], frame.y + r[1], r[2], r[3])


def _place(layout, tw):
    x, y = centred(layout, tw.w, tw.place_h)
    return Rect(x, y, tw.w, tw.h)


def pause_dialog(layout, main, wrap=plain_wrap):
    """The Pause key's notice (`FUN_00444243`, text `main 0x77`, no caption): the message window of `FUN_00443238` (CONFIRMED) with its one centred Ok button (`dialogs 0`, same text
    as `main 0x4d`); `wrap(text, width)` = the font1 line breaker.  Its height follows the text (one line at 640x480: 488x168)."""
    text = main(M_PAUSED)
    tw = text_window((576, 384), lambda w: len(wrap(text, w)), False, 1)
    frame = _place(layout, tw)
    ok = _rect(frame, tw.buttons[0])
    tr = _rect(frame, tw.text)
    return Dialog("pause", frame, (DButton(ok, main(M_OK), True, CLOSE, "o"),), text, tr, tuple(wrap(text, tr.w)), align="left", escape=CLOSE, enter=CLOSE)


NEXT = ("story_next",)


class StoryState:
    """The story window's script state (`+0x68` page counter, `+0x74` section text): `sec` the section text, `flags` the hero flags (`story.hero_flags`), `alive(npc)` the
    unit test of the `npcalive:` / `npcdead:` conditions, `speaker` the current page's `story.Page` (None before the first)."""

    def __init__(self, sec, flags, alive=lambda npc: True, wrap=None, picture_of=lambda npc: None):
        self.sec, self.flags, self.alive, self.wrap, self.picture_of = sec, flags, alive, wrap or plain_wrap, picture_of
        self.n = 0
        self.page = None
        self.tips = 0


def story_dialog(layout, main, sec="", flags=0, alive=lambda npc: True, wrap=plain_wrap, picture_of=lambda npc: None):
    """The script-message story window (`FUN_0041d15e` + `FUN_004dc63f`, 11.5): 488x232 frame, text widget (id 10, table highlight, left, font1; (48,36)-(428,172), or
    (128,36)-(428,172) when the section contains `npc`), the speaker picture widget (id 12, (30,54)-(118,168)) only in that case, one Ok button (200,172)-(280,198) = message
    `0x470` = the next page (`advance`).  The first page is made at once (`FUN_004dc810`); a section without a qualifying page 1 shows "Nothing to say"."""
    frame = widget_rect(layout, "story.frame")
    ok = widget_rect(layout, "story.ok")
    wide = story_mod.has_speaker_layout(sec)
    d = Dialog("story", frame, (DButton(ok, main(M_OK), True, NEXT, "o"),), story_mod.NOTHING_TO_SAY,
               widget_rect(layout, "story.text_npc" if wide else "story.text"), escape=CLOSE, enter=NEXT, table="highlight", align="left",
               story=StoryState(sec, flags, alive, wrap, picture_of), picture=widget_rect(layout, "story.picture") if wide else None)
    d.lines = tuple(wrap(d.text, d.text_rect.w))
    advance(d)
    return d


def advance(d):
    """Message `0x470` (`FUN_004dc754` -> `FUN_004dc84c`): the page counter goes up and the page's text replaces the widget's; the speaker picture is replaced only by a page with
    `npc=`.  Returns False when no page qualifies (the window closes; `story.tips` is then the `tips:` value for message `0x45b`)."""
    st = d.story
    st.n += 1
    pg = story_mod.page(st.sec, st.n, st.flags, st.alive)
    if pg is None:
        return False
    st.page = pg
    d.text = pg.text.replace("\r\n", "\n").rstrip("\n")
    d.lines = tuple(st.wrap(d.text, d.text_rect.w))
    if pg.tips:
        st.tips = pg.tips
    if pg.has_npc and d.picture is not None:
        d.picture_unit = st.picture_of(pg.npc)
    return True


def complete_dialog(layout, main, dialogs):
    """Mission complete (`0x430`, chapter var < 0x78; CONFIRMED `FUN_0044da0f` / `FUN_0044da55`): a menu-class dialog 296x168 with the label `main 0x8c`, `Victory!` (message `0x41d`: ends the
    mission; J1 ends the program) and `Continue` (`dialogs 0x9a`, message `0x446`: closes the window, play goes on).  ESC = Continue (INFERRED: the common dialog key handler), Enter does nothing (DECISION)."""
    tw = complete_window()
    frame = _place(layout, tw)
    victory = DButton(_rect(frame, tw.buttons[0]), dialogs(D_VICTORY), True, ("quit", "victory"), "v")
    cont = DButton(_rect(frame, tw.buttons[1]), dialogs(D_CONTINUE), True, RETURN, "c")
    return Dialog("complete", frame, (victory, cont), main(M_COMPLETE), _rect(frame, tw.text), (main(M_COMPLETE),), escape=RETURN, enter=None, align="center")


def failed_dialog(layout, main, dialogs, reason="", wrap=plain_wrap):
    """Mission failed (`0x431`; CONFIRMED `FUN_0044d1e2` / `FUN_0044d237`): a text window with caption `main 0x8d`, the mission's reason text `reason` (the exe takes it from the string list
    `0x6227b0`; J1 has none: empty) and two stacked buttons, `Exit to Main Menu` (ends the program in J1) and `Load Game` (disabled: no saves in J1).  The window is centred with its
    height before the `+0x40` the failed class adds, so it sits 32 px low.  No ESC / Enter action (DECISION)."""
    tw = failed_window((576, 280), lambda w: len(wrap(reason, w)) if reason else 0, True)
    frame = _place(layout, tw)
    entries = [(dialogs(D_EXIT_MENU), True, ("quit", "defeat")), (dialogs(D_LOAD), False, NOOP)]
    rows = []
    for (lbl, en, act), r in zip(entries, tw.buttons):
        text, key = split_label(lbl)
        rows.append(DButton(_rect(frame, r), text, en, act, key))
    tr = _rect(frame, tw.text)
    return Dialog("failed", frame, tuple(rows), reason, tr, tuple(wrap(reason, tr.w)) if reason else (), main(M_FAILED), _rect(frame, tw.caption), "left", escape=None, enter=None)


class ModalStack:
    """The open dialogs, bottom first; any open dialog freezes the simulation (mode bit 8 of the exe, 11.4)."""

    def __init__(self):
        self.stack = []

    @property
    def top(self):
        return self.stack[-1] if self.stack else None

    @property
    def frozen(self):
        return bool(self.stack)

    def push(self, dialog):
        self.stack.append(dialog)

    def pop(self):
        return self.stack.pop() if self.stack else None

    def clear(self):
        self.stack.clear()

    def kinds(self):
        return tuple(d.kind for d in self.stack)
