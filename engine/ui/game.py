"""`GameUi`: the J1 interface state that is neither the world nor the sim (docs/engine/ui-layout.md 11): the info panel mode, the modal
stack (menu, End Quest, pause, story, mission result), the message line and its sources, key / click routing for the panels.

It reads the world and produces only commands (through `OrderInput`) or UI actions; it never changes the simulation.  The backend loop
asks `frozen` before stepping (a modal window stops the server step, the message drain and the edge scroll, 11.4) and routes keys and
mouse buttons here first.  No pygame: keys arrive as names ('escape', 'pause', 'tab', 'return', a lower-case letter)."""

from engine.sim import campaign as campaign_mod, spells as spells_mod

from . import bar, info, messages as messages_mod, modal, story
from .book import SpellBookWindow
from .pack import PackWindow
from .messages import PickupWatch
from .knowledge import Knowledge
from .orders import MainText, MessageLine
from .widgets import info_button_rect

QUIT_REASONS = ("menu", "windows", "victory", "defeat")


class GameUi:
    """`main` / `dialogs` / `unit_names`: `MainText` objects (`.line(i)`, `.lines`); `mission_text`: the whole `mission<id>.txt` or None."""

    def __init__(self, layout, world, player_id, main, dialogs, unit_names, mission_text=None, trace=False, hero_name="Hero",
                 messages=None, know_all=False, knowledge=None, camp=None, wrap=None, patch=None, building_names=None):
        self.layout, self.world, self.player_id = layout, world, player_id
        self.main, self.dialogs, self.unit_names = main, dialogs, unit_names
        self.building_names = building_names if building_names is not None else MainText()      # building.txt (structure names)
        self.patch = patch if patch is not None else MainText()      # patch.txt (the network / system messages)
        self.toggles = messages_mod.OptionToggles()
        self.mission_text = mission_text
        self.wrap = wrap or modal.plain_wrap           # `wrap(text, width_px) -> lines` in font1 (the backend passes the real one)
        self.trace, self.hero_name, self.know_all = trace, hero_name, know_all
        self.knowledge = knowledge if knowledge is not None else Knowledge()     # the viewer's kill counts per type (info panel detail level)
        self.messages = messages if messages is not None else MessageLine()
        self.modals = modal.ModalStack()
        self.camp = camp or campaign_mod.Campaign()
        self.panel_mode = info.MODE_PICTURE
        self.book = SpellBookWindow(layout)        # the spell book window (bottom bar id 3), closed at the start (ui-layout 11.12)
        self.pack = PackWindow(layout)             # the backpack window (bottom bar id 2), closed at the start (ui-layout 11.13)
        self.doll_mask = None                      # (unit) -> the 240x160 hit mask of its paper doll (ids slot + 1, 0 none); the backend supplies it
        self.quit = None                        # a QUIT_REASONS value once the player left the mission
        self.queue = []                         # story numbers waiting for the modal stack to empty (exe list 0x627170)
        self.bar = bar.BarWindow()              # the command bar's highlight state and press rules (11.2)
        self.pressed = None                     # (dialog, button index) under a held left button
        self.watch = PickupWatch(world, player_id)
        self._complete_shown = self._failed_shown = False

    # -- state the loop reads ------------------------------------------------------------------------------------------------------
    @property
    def frozen(self):
        """A modal window is open: no sim step, no scroll, no world input (11.4)."""
        return self.modals.frozen

    def main_text(self, i):
        return self.main.line(i)

    def dialog_text(self, i):
        return self.dialogs.line(i)

    def patch_text(self, i):
        return self.patch.line(i)

    def option_key(self, name, now_ms):
        """A Ctrl+<name> option key with no other owner (W, N, C, U; `messages.OptionToggles`): shows its 2000 ms system line.  True when handled."""
        line = self.toggles.press(name, self.main, self.patch)
        if line is None:
            return False
        self.messages.show(line, now_ms, messages_mod.OPTION_MS)
        return True

    # -- opening dialogs -----------------------------------------------------------------------------------------------------------
    def open_menu(self):
        """ESC / the disk button (window message `0x416`): only while no modal is open (mode 1)."""
        if not self.frozen:
            self.modals.push(modal.menu_dialog(self.layout, self.dialog_text))
            return True
        return False

    def toggle_pause(self):
        """The Pause key: the notice window, closed again by the key, ESC or OK; ignored inside other dialogs (mode != 1)."""
        top = self.modals.top
        if top is None:
            self.modals.push(modal.pause_dialog(self.layout, self.main_text, self.wrap))
        elif top.kind == "pause":
            self.modals.pop()
        else:
            return False
        return True

    @property
    def shown_mode(self):
        """The info panel's mode as drawn: forced to the picture when window 8 holds the text (1024x768: `FUN_004af3bf` sets `+0x70 = 1`)."""
        return info.MODE_PICTURE if self.layout.text_in_extra else self.panel_mode

    def toggle_mode(self):
        """The panel's mode button / TAB (message `0x412`; ignored while window 8 holds the text, `FUN_004ae89e`)."""
        if self.layout.text_in_extra:
            return
        self.panel_mode = info.MODE_TEXT if self.panel_mode == info.MODE_PICTURE else info.MODE_PICTURE

    def show_story(self, sec):
        """Open the story window for the section text `sec` (11.5): the hero flags and the unit tests come from the world."""
        hero = self.world.units.get(self.world.players[self.player_id].main_hero)
        flags = story.hero_flags(info.is_female(hero), info.is_mage(hero)) if hero is not None else 0
        self.modals.push(modal.story_dialog(self.layout, self.main_text, sec, flags, self._npc_alive, self.wrap, self._npc_picture))

    @staticmethod
    def npc_id(u):
        """The exe's `+0x1dc` of a unit = its server id, reduced for humans above 10000 (`(v / 10) % 1000`: the four starting heroes are all 21)."""
        v = u.server_id
        return (v // 10) % 1000 if u.human and v > 10000 else v

    def _npc_unit(self, npc):
        for u in self.world.units.values():
            if u.hp > 0 and self.npc_id(u) == npc:
                return u
        return None

    def _npc_alive(self, npc):
        return self._npc_unit(npc) is not None

    def _npc_picture(self, npc):
        u = self._npc_unit(npc)
        return None if u is None else u.id

    # -- actions -------------------------------------------------------------------------------------------------------------------
    def apply(self, action):
        """Run a dialog action; returns the action for the caller's information."""
        if action is None or action == modal.NOOP:
            return action
        kind = action[0]
        if kind == "close":
            self.modals.pop()
        elif kind == "return":
            self.modals.clear()
        elif kind == "story_next":
            top = self.modals.top
            if top is not None and top.story is not None and not modal.advance(top):
                self.modals.pop()                   # no more pages: message 0x445 closes it (the `tips:` message 0x45b is not built)
        elif kind == "open":
            if action[1] == "endquest":
                self.modals.push(modal.endquest_dialog(self.layout, self.dialog_text, self.world.mission_complete))
        elif kind == "quit":
            self.quit = action[1]
            self.modals.clear()
        if not self.modals.frozen and self.queue:               # the queued story windows follow the last dialog
            self.show_queued()
        return action

    def show_queued(self):
        while self.queue and not self.frozen:
            self._story(self.queue.pop(0))

    # -- keys ----------------------------------------------------------------------------------------------------------------------
    def key(self, name):
        """Route a key.  Returns True when the UI consumed it (a modal open: always; ESC / Pause / TAB otherwise).  In mission mode 1 (no modal) the other
        keys are left to `OrderInput` and the loop."""
        top = self.modals.top
        if top is not None:
            if name == "pause" and top.kind == "pause":
                self.modals.pop()
            else:
                self.apply(top.key(name))
            return True
        if name == "escape":
            return self.open_menu()
        if name == "pause":
            return self.toggle_pause()
        if name in ("b", "q"):
            self.book.toggle()                  # `0x40cd29` (B / Q): message 0x40f, mission mode only
            return True
        if name in ("i", "`", "~"):
            self.toggle_pack()                  # `0x40ccb6` (I, the backquote key): message 0x40e
            return True
        if name == " ":
            self.space()                        # `0x40cd6e`: neither bar open -> both open, else the open ones close
            return True
        if name == "tab":
            self.toggle_mode()
            return True
        return False

    def toggle_pack(self):
        """Message `0x40e` (`FUN_0041adc2` open / `FUN_0041ae4f` close): the book window stacks above an open inventory."""
        self.pack.toggle()
        self.book.inventory_open = self.pack.open

    def space(self):
        if not self.pack.open and not self.book.open:
            self.pack.open_pack()
            self.book.open_book()
            self.book.inventory_open = True
            return
        if self.pack.open:
            self.toggle_pack()
        if self.book.open:
            self.book.toggle()

    # -- the pack, the carried item ----------------------------------------------------------------------------------------------------
    def sync_pack(self):
        """Per frame (`FUN_004167c2`): the pack window shows the single selected hero."""
        self.pack.set_unit(self.world, self.world.players[self.player_id].selection, self.player_id)

    def doll_slot_at(self, pos):
        """The equipment slot (0-based) whose paper-doll layer covers `pos` in the info panel's picture mode, -1 for none (`FUN_004aeabb`: the byte of the hit
        mask at `((y - P.y - 2) * 160 + x - P.x)`)."""
        u = self.pack.unit_obj(self.world)
        if u is None or self.doll_mask is None or self.shown_mode != info.MODE_PICTURE or not self.layout.info_panel.rect.contains(*pos):
            return -1
        mask = self.doll_mask(u)
        p = self.layout.info_panel.rect
        x, y = pos[0] - p.x, pos[1] - p.y - 2
        if mask is None or not (0 <= y < mask.shape[0] and 0 <= x < mask.shape[1]):
            return -1
        return int(mask[y, x]) - 1

    def item_release(self, pos, ordering=None):
        """The left release while an item is carried: over the pack window it is filed there, over the info panel it goes to the hero (worn / used / the scroll
        selected, `FUN_004aebc8`), over the open book or the command bar it returns / is dropped (`FUN_004c76bc`, `FUN_004adace`), over the map it falls at the
        hero's feet (`FUN_0040c5d1`).  Returns (handled, commands)."""
        pk = self.pack
        if pk.carried is None or self.frozen:
            return False, ()
        self.sync_pack()
        w, pid = self.world, self.player_id
        if pk.contains(pos):
            return True, pk.left_up(pos, w, pid)
        if self.book.contains(pos):
            c = pk.carried
            return True, pk.drop_in_pack(w, pid, c.index if c.kind == 2 else -1)
        if self.layout.info_panel.rect.contains(*pos):
            return True, pk.equip_carried(w, pid, ordering)
        if self.layout.bar_panel.rect.contains(*pos):
            pk.cancel_carry()
            return True, ()
        if self.layout.viewport.contains(*pos):
            u = pk.unit_obj(w)
            return True, pk.drop_on_ground(w, pid, (u.x, u.y)) if u is not None else (pk.cancel_carry(), ())[1]
        return False, ()

    def pack_mouse_move(self, pos, left, shift=False):
        """A move with the left button held: over the pack window a cell is picked up (`0x4a3a1d`), over a paper-doll layer the equipped item (`0x4af120`)."""
        if not left or self.frozen or self.pack.carried is not None:
            return False
        self.sync_pack()
        if self.pack.open and self.pack.mouse_move(pos, True, self.world, self.player_id, shift):
            return True
        slot = self.doll_slot_at(pos)
        return slot >= 0 and self.pack.pick_equipped(self.world, self.player_id, slot)

    def doll_double_click(self, pos):
        """`0x4aeabb`: the double click on an equipped item takes it off into the pack."""
        slot = self.doll_slot_at(pos)
        return self.pack.unequip(self.world, self.player_id, slot) if slot >= 0 else ()

    # -- mouse ---------------------------------------------------------------------------------------------------------------------
    def knows(self, uid, spell):
        """Whether unit `uid` has spell number `spell` in its book (the double click's cast needs it per unit)."""
        u = self.world.units.get(uid)
        return u is not None and u.hp > 0 and bool((spells_mod.known_mask(u) >> spell) & 1)

    def mouse_down(self, pos, ordering=None, cast_enabled=False, clicks=1):
        """Left press.  Returns (consumed, command); the spell book's double click returns a tuple of commands.  A modal takes every click (a dialog button
        arms, the action runs on release); otherwise the spell book (when open), the info panel's buttons and the command bar's cells."""
        self.sync_pack()
        top = self.modals.top
        if top is not None:
            i = top.button_at(pos)
            self.pressed = (top, i) if i is not None and top.buttons[i].enabled else None
            return True, None
        if self.pack.contains(pos):
            if clicks >= 2:
                return True, self.pack.double_click(pos, self.world, self.player_id, ordering)
            self.pack.left_down(pos, self.world)
            return True, None
        if self.book.contains(pos):
            if ordering is None:
                return True, None
            if clicks >= 2:
                return True, self.book.double_click(pos, ordering, self.knows)       # the double-click message replaces the second press (0x203)
            self.book.left_down(pos, ordering)
            return True, None
        if clicks >= 2 and self.pack.unit is not None:
            cmds = self.doll_double_click(pos)
            if cmds:
                return True, cmds
        if self.layout.bar_panel.rect.contains(*pos):
            return True, self.bar_press(pos, ordering, cast_enabled)
        return False, None

    def bar_press(self, pos, ordering, cast_enabled):
        """The command bar's press (`FUN_004ad8fd`, also run by a move with the left button held, `FUN_004adb35`): acts at once, never on the release.
        Nothing while an item is carried (`client+0x3f4`)."""
        if ordering is None or self.pack.carried is not None or self.frozen:
            return None
        cmd, close = self.bar.press(bar.cell_at(self.layout, pos), ordering, cast_enabled, self.book.open)
        if close:
            self.book.close()
        return cmd

    def info_release(self, pos):
        """The info panel's buttons act on the left RELEASE (`FUN_004aebc8`, vtable slot 0x58; the press `FUN_004aea97` only returns 1): the release
        must be over the button, wherever the press was; there is no armed / pressed look and no cancel.  Returns True when a button took it."""
        if self.frozen or self.pack.carried is not None:
            return False
        for name in ("mode", "menu", "pack", "book"):
            if name == "mode" and self.layout.text_in_extra:
                continue                        # no mode button while window 8 shows the text
            if info_button_rect(self.layout, name).contains(*pos):
                if name == "mode":
                    self.toggle_mode()
                elif name == "menu":
                    self.open_menu()
                elif name == "book":
                    self.book.toggle()          # message 0x40f
                elif name == "pack":
                    self.toggle_pack()          # message 0x40e
                return True
        return False

    def book_mouse_move(self, pos, left, right, ordering):
        """A move with a button held over the spell book (`0x4c77a2`)."""
        if ordering is not None:
            self.book.mouse_move(pos, left, right, ordering)

    def book_right_down(self, pos, ordering):
        """Right press: True when the open spell book took it (it clears the selected slot and keeps the view's right-button handling out)."""
        return self.book.contains(pos) and ordering is not None and self.book.right_down(pos, ordering)

    def mouse_up(self, pos):
        """Left release over a dialog: the armed button's action when the pointer is still on it.  Returns True when a modal consumed it."""
        top = self.modals.top
        armed, self.pressed = self.pressed, None
        self.book.left_up()                      # the press that began in the spell book ends
        self.pack.left_held = False
        if top is None:
            return False
        if armed is not None and armed[0] is top and top.button_at(pos) == armed[1]:
            self.apply(top.buttons[armed[1]].action)
        return True

    def world_state(self):
        sel = self.world.players[self.player_id].selection
        if not sel:
            return "none"
        return "foreign" if self.world.selection_is_foreign(self.player_id) else "own"

    # -- per frame -----------------------------------------------------------------------------------------------------------------
    def _story(self, n):
        """Script message `n`: the story window of the section `#event<n>` (an absent section gives the window with "Nothing to say")."""
        if self.mission_text is None:
            return
        self.show_story(story.section(self.mission_text, "event%d" % n))

    def poll(self, now_ms):
        """After a frame's sim steps: script messages (story windows, `message_action`), the mission-result dialogs, pickup lines.  Does not touch
        the sim.  Returns the number of new dialogs."""
        w, opened = self.world, 0
        keep = []
        from engine.sim.triggers import ScriptMessage
        for ev in w.events:
            if not isinstance(ev, ScriptMessage):
                keep.append(ev)
                continue
            for act in campaign_mod.message_action(ev.number, modal=self.frozen):
                if act[0] == "text":
                    self._story(int(act[1][5:]))
                    opened += 1
                elif act[0] == "queue":
                    self.queue.append(act[1])
                elif act[0] == "line":
                    self.messages.show(self.patch_text(act[1]), now_ms, act[2])       # patch.txt, not main.txt (CONFIRMED 0x4860b0: table 0x621878)
                elif act[0] == "defeat":
                    opened += self._open_failed()
        w.events[:] = keep
        dlg = campaign_mod.poll(w, self.camp) if (w.mission_complete or any(p.defeat_dialog for p in w.players.values())) else None
        if dlg is not None:
            if dlg.kind == "complete" and not self._complete_shown:
                self._complete_shown = True
                self._close_book_for_result()
                self.modals.push(modal.complete_dialog(self.layout, self.main_text, self.dialog_text))
                opened += 1
            elif dlg.kind == "defeat":
                opened += self._open_failed()
        for text, colour, ms in self.watch.poll(w, self.main):
            self.messages.show(text, now_ms, ms, colour)
        return opened

    def _close_book_for_result(self):
        """Messages `0x42a` (mission won, `FUN_0048aea8`) / `0x42b` (lost, `FUN_0048b885`): an open spell book is closed (`FUN_0041b077`) before the result
        dialog; the inventory window is not touched by either routine (ui-layout 11.12)."""
        if self.book.open:
            self.book.toggle()

    def _open_failed(self):
        if self._failed_shown:
            return 0
        self._failed_shown = True
        self._close_book_for_result()
        self.modals.push(modal.failed_dialog(self.layout, self.main_text, self.dialog_text, wrap=self.wrap))
        return 1

    def after_step(self):
        """Story windows queued while a dialog was open (called once the stack may have emptied)."""
        if not self.frozen and self.queue:
            self.show_queued()
