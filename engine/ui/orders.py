"""Order input (research docs/engine/click-to-move-research.md 1.2-1.7): the pure, pygame-free part that turns
clicks, hotkeys and minimap clicks into commands.  The pending target mode is `view+0x9b4`.

A left release with a click on a non-empty selection dispatches on the cursor chosen at the release (R 1.2);
the pending mode is reset after every such dispatch, also when nothing was ordered."""

from engine.sim import AttackUnit, CastSpell, Guard, MoveUnits, SelectUnits, SetFormation, StandStill, Stop, Swarm
from allods2.text import decode_text

from .cursor import CursorState as S
from .selection import drag_threshold

# pending target modes (button numbers of FUN_00418a02)
ATTACK, MOVE, DEFEND, CAST, SWARM, PATROL = 1, 2, 4, 5, 6, 8
HOTKEYS = {"a": ATTACK, "m": MOVE, "d": DEFEND, "s": SWARM}       # arm a mode (R 1.4: buttons 1, 2, 4, 6)
FORMATION_TEXT = 0x61                                              # main.txt 0x61 + mode (R 4.1)
NO_WAY_TEXT = 0x81                                                 # main.txt (R 6.3)
NO_WAY_MS = 3000
LEVEL_UP_TEXT = 0x81                                              # main.txt 0x81 + school (fighters), 0x86 + school (mages)
LEVEL_UP_MAGE_TEXT = 0x86                                         # (R combat.md 12.7, `FUN_0040d9b2` case 0x92 sub 2)
LEVEL_UP_MS = 3000
HEALTH_TEXT = 0x64                                                 # main.txt 0x64 + show-health flag (Ctrl+H, FUN_0041f0e0)
FORMATION_MS = 2000                                                # CONFIRMED: `push 0x7d0` before FUN_004021fe at 0x40cf3e (Ctrl+F), 0x40ced7 (Ctrl+W), 0x40cf86 (Ctrl+H)
RIGHT_SCROLL_DIV = 8


def right_drag_cells(d):
    """`(d + ((d >> 31) & 7)) >> 3` of `FUN_0040c7dd`: delta pixels / 8, truncating toward zero."""
    return (d + ((d >> 31) & 7)) >> 3


class OrderInput:
    """`selection_fn()` -> the player's selection tuple; `state_fn()` -> 'none' | 'own' | 'foreign';
    `formation` the player's current client mode."""

    def __init__(self, player_id, screen_w, selection_fn, state_fn, formation=1, spell_fn=None):
        self.player_id, self.screen_w = player_id, screen_w
        self.selection_fn, self.state_fn = selection_fn, state_fn
        self.spell_fn = spell_fn            # () -> the spell number the selection can cast now, 0 for none (`castable_spell`)
        self.spell = 0                      # the spell armed by `C` (the exe's selected spellbook entry, FUN_0041f370)
        self.pending = 0
        self.formation = formation
        self.right_dragged = False          # view+0xd8
        self._had_selection = False

    # -- pending mode -------------------------------------------------------------------------------------
    def clear_pending(self):
        self.pending = 0

    def update(self):
        """Per frame: a selection that became empty (its objects died) clears the mode (0x40be67, INFERRED trigger)."""
        has = bool(self.selection_fn())
        if self._had_selection and not has:
            self.pending = 0
        self._had_selection = has

    def key(self, name, ctrl=False):
        """Hotkey `name` (lower-case letter).  Returns (command or None, formation_text_mode or None).
        Mode keys need no Ctrl, a non-empty own non-structure selection (FUN_0040c8a0 gating, CONFIRMED)."""
        if ctrl:
            if name == "f":                 # Ctrl+F cycles 0 -> 1 -> 2 -> 0 (FUN_0041f040) and sends cmd 0x46/2
                self.formation = (self.formation + 1) % 3
                return SetFormation(self.player_id, self.formation), self.formation
            return None, None
        if self.state_fn() != "own" or not self.selection_fn():
            return None, None
        if name in HOTKEYS:
            self.pending = HOTKEYS[name]    # mask 0xef: buttons 1, 2, 4, 6 enabled
            return None, None
        if name == "c":                     # btn 5: enabled only when the selection has a castable spell (view+0x148 / 0x150, mask 0x10)
            n = self.spell_fn() if self.spell_fn else 0
            if n:
                self.pending, self.spell = CAST, n      # the spellbook window (J) is replaced by a fixed spell slot (DECISION)
            return None, None
        if name == "t":                     # stand ground, immediate (btn 7): cmd 0x18, mode cleared
            self.pending = 0
            return Stop(self.player_id, tuple(self.selection_fn())), None
        if name == "g":                     # guard, immediate (btn 3): cmd 0x17, mode cleared
            self.pending = 0
            return Guard(self.player_id, tuple(self.selection_fn())), None
        if name == "l":                     # stand still (FUN_00419ffd, a key, not via FUN_00418a02): cmd 0x12; the pending mode is left alone
            return StandStill(self.player_id, tuple(self.selection_fn())), None
        return None, None

    # -- left button --------------------------------------------------------------------------------------
    def is_order_click(self, corner, pos):
        """True when the release is handled as an order dispatch rather than a selection (R 1.2): a click (not a
        drag) with a non-empty selection (`view+0x140 != 0`)."""
        if corner is None or not self.selection_fn():
            return False
        t = drag_threshold(self.screen_w)
        return abs(pos[0] - corner[0]) <= t and abs(pos[1] - corner[1]) <= t

    def release(self, cursor, cell, hover_unit):
        """The dispatch on the cursor chosen at the release.  Returns ('select', None) when the cursor is `select`
        (the caller runs the selection), else ('order', command or None).  `cell`: target cell or None;
        `hover_unit`: the object under the pointer, its entity id (an int) or just True / False; the attack cursor over an
        id orders an attack (`AttackUnit`, cmd 0x19), over nothing a walk.  Own non-structure selection only (the
        cursor guarantees it for move/swarm/attack; checked again here).  Resets the pending mode."""
        if cursor is S.SELECT:
            self.pending = 0
            return "select", None
        cmd = None
        sel = tuple(self.selection_fn())
        movable = self.state_fn() == "own" and sel and cell is not None
        if cursor is S.MOVE or (cursor is S.ATTACK and not hover_unit):
            if movable:
                cmd = MoveUnits(self.player_id, sel, cell)
        elif cursor is S.ATTACK and isinstance(hover_unit, int) and not isinstance(hover_unit, bool):
            if self.state_fn() == "own" and sel:
                cmd = AttackUnit(self.player_id, sel, hover_unit)
        elif cursor is S.SWARM and movable:         # cmd 0x1a at the cell under the pointer, also over a unit (R 1.3)
            cmd = Swarm(self.player_id, sel, cell)
        elif cursor is S.CAST:                      # cmd 0x1e on the hovered unit (FUN_004195fa); a cell cast (0x1f) is phase K
            if self.spell and self.state_fn() == "own" and sel and isinstance(hover_unit, int) and not isinstance(hover_unit, bool):
                cmd = CastSpell(self.player_id, sel, self.spell, hover_unit)
        # patrol, defend, pickup, town: phases J/K, no order yet
        self.pending = 0
        return "order", cmd

    # -- right button -------------------------------------------------------------------------------------
    def right_press(self):
        pass                                # 0x40c50a: sets a window flag only

    def right_move(self, dx, dy):
        """Mouse moved with the right button held: the camera scroll in cells (FUN_0040c7dd), sets view+0xd8."""
        self.right_dragged = True
        return right_drag_cells(dx), right_drag_cells(dy)

    def right_release(self):
        """0x40c53a: without a drag since the press -> FUN_00416388: cancel the pending mode (selection kept), else
        deselect everything.  Returns the command or None."""
        dragged, self.right_dragged = self.right_dragged, False
        if dragged:
            return None
        if self.pending:
            self.pending = 0
            return None
        return SelectUnits(self.player_id, ())

    # -- minimap ------------------------------------------------------------------------------------------
    def minimap_left(self, cell):
        """Left press / drag move over the minimap image with the cell under the pointer.  Own selection: the
        action follows the minimap cursor (R 1.6): smove -> MoveUnits, pending modes: attack/swarm, defend, patrol,
        cast issue nothing yet; the mode is reset.  Returns ('order', cmd) or ('camera', None)."""
        if self.state_fn() != "own" or not self.selection_fn():
            return "camera", None
        sel = tuple(self.selection_fn())
        cmd = MoveUnits(self.player_id, sel, cell) if self.pending in (0, MOVE, 3, 7) else None
        self.pending = 0
        return "order", cmd


def minimap_move_cell(cell_x, row, view_y):
    """Target of a minimap move order (R 1.6, CONFIRMED `FUN_00418bc3`): the column is the minimap cell `cell_x`; the
    exe ignores its row argument and sends `FUN_00417f31(mouse) + view+0x60`, `row` being that finder's result for
    the mouse over the right panel (`Projection.exe_row`) and `view_y` the camera's top cell.  The server clamp
    [8, size - 9] (and the `& 0xff` wrap) applies afterwards, as for any move."""
    return cell_x, row + view_y


def target_cell(mx, camera_cell_x, row):
    """Normal click target (R 1.7): `(mx >> 5) + view+0x5c`, `row + view+0x60`; no fog, passability or range test."""
    return (mx >> 5) + camera_cell_x, row


class MessageLine:
    """The view's message list (`FUN_004021fe` add, `FUN_00402585` ageing, `FUN_0040261a` draw; CONFIRMED).  A queue of lines, each with its own
    colour table and lifetime, drawn top-down from (8, 8) of the view in font1 with the `0x5f17f4` table (`0x61fa80`, the grey 17i ramp), one line
    every `font height + 2` pixels.  `show` wraps the text to the view width (`wrap`), appends its lines (when the queue was empty the clock
    starts: `last = now`, `age = 0`) and drops the oldest lines beyond `max_lines` (`(view height / (font height + 2)) / 2`).  The ageing runs
    once per frame: `age += now - last`; only the FIRST line has a clock, it is removed when `age > its lifetime` and `age` restarts at 0 for the
    next one, so a second message lives its own time after the first has gone.  "No way", the formation / retreat / health / flying-damage
    texts and the level-up lines all use it (`ui-layout.md`, `click-to-move-research.md` 6.3)."""

    def __init__(self, max_lines=None, wrap=None):
        self.queue = []                         # [text, lifetime ms, colour] oldest first (the exe's three lists)
        self.last = self.age = 0                # +0x40 time of the last ageing, +0x44 age of the first line
        self.max_lines, self.wrap = max_lines, wrap

    def show(self, text, now_ms, duration_ms, colour=None):
        if not text:
            return
        if not self.queue:
            self.last, self.age = now_ms, 0
        for line in (self.wrap(text) if self.wrap else [text]):
            self.queue.append([line, duration_ms, colour])
        while self.max_lines is not None and len(self.queue) > self.max_lines:
            del self.queue[0]

    def tick(self, now_ms):
        """`FUN_00402585`."""
        if not self.queue:
            return
        self.age += now_ms - self.last
        self.last = now_ms
        if self.age > self.queue[0][1]:
            self.age = 0
            del self.queue[0]

    def lines(self, now_ms):
        """The live lines after this frame's ageing, oldest (top) first."""
        self.tick(now_ms)
        return tuple(q[0] for q in self.queue)

    def current(self, now_ms):
        """The first (oldest) live line or None."""
        lines = self.lines(now_ms)
        return lines[0] if lines else None


class MainText:
    """`main.txt` lines (cp1251, one string per line); '' when absent."""

    def __init__(self, lines=()):
        self.lines = list(lines)

    @classmethod
    def load(cls, fs):
        try:
            return cls(decode_text(fs.read("main/text/main.txt")).split("\r\n"))
        except (OSError, KeyError, FileNotFoundError):
            return cls()

    def line(self, i):
        return self.lines[i] if 0 <= i < len(self.lines) else ""


def drain_no_way(world, player_id, messages, now_ms, text):
    """Consume `NoWay` events of `world.events`: the local player's ones show the message, the others (computer
    players) are dropped.  CONFIRMED routing: the server (`0x6831a8`, host flag +0x18b0 = 1) posts message 0x92 with
    `+7` = owner player id (`FUN_00505347`); `FUN_0050164f` delivers it only to the connection whose player id is
    `+7` (`FUN_0050155f`; none = dropped; `+7 == 0` = every connection); the client handler `0x40e266` has no
    filter of its own.  Other event types stay."""
    from engine.world import NoWay
    keep, shown = [], False
    for ev in world.events:
        if isinstance(ev, NoWay):
            shown = shown or ev.player_id in (player_id, 0)
        else:
            keep.append(ev)
    world.events[:] = keep
    if shown:
        messages.show(text.line(NO_WAY_TEXT), now_ms, NO_WAY_MS)
    return shown


def level_up_messages(world, player_id, messages, now_ms, text, name_fn=None):
    """Show the skill-up line for the `LevelUp` entries of `world.fight_log` (read, not consumed) whose hero belongs to the
    local player.  CONFIRMED (`FUN_0040d9b2` case 0x92 sub 2, `0x40e2a3`-`0x40e65c`): the line is `main.txt[0x81 + school]`
    ("<School> skill improved"), `[0x86 + school]` when the hero is a mage (`+0x1b8 & 2`, INFERRED = template mana_max > 0),
    followed by " (<hero name>)" in a game; 3000 ms in the message line.  The exe's skill-up sound is not played."""
    from engine.world import LevelUp
    shown = False
    for ev in world.fight_log:
        if not isinstance(ev, LevelUp):
            continue
        hero = world.find_unit(ev.unit)
        if hero is None or hero.owner != player_id:
            continue
        mage = hero.stats is not None and hero.stats.get("mana_max", -1) > 0
        line = text.line((LEVEL_UP_MAGE_TEXT if mage else LEVEL_UP_TEXT) + ev.school)
        if line and name_fn is not None:
            line += " (%s)" % name_fn(hero)
        if line:
            messages.show(line, now_ms, LEVEL_UP_MS)
            shown = True
    return shown


PROTOTYPE_SPELLS = (1, 5, 16)       # Fire Arrow, Ice Missile, Diamond Dust: the same parameter row, the default missile draw (spells.md 9); Lightning etc. need their own draw


def castable_spell(world, player_id):
    """The spell the selection can cast now: the lowest-numbered prototype spell (the unit-target missile kind the cast code and the view run) in the book of a selected,
    living unit that can pay its mana (INFERRED: the exe's button mask `+0x148` follows the spellbook and the mana, spells.md 9c.1); 0 for none."""
    from engine.sim import combat, spells
    from allods2.formats import spelldefs
    table = world.spell_table
    p = world.players.get(player_id)
    if table is None or p is None:
        return 0
    best = 0
    for uid in p.selection:
        u = world.units.get(uid)
        if u is None or u.hp <= 0:
            continue
        mask, mage = spells.known_mask(u), combat.combat_stats(world, u).mage
        for d in table:
            if (d.number in PROTOTYPE_SPELLS and (mask >> d.number) & 1 and d.targets_unit and d.has_damage and d.distribution == spelldefs.DIST_SINGLE
                    and (not mage or u.mana >= d.mana_cost) and (not best or d.number < best)):
                best = d.number
    return best
