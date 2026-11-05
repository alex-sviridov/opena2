"""Message sources of the on-screen line that the sim does not announce itself (docs/engine/ui-layout.md 11.5): gold and item pickups.

The server sends message `0x67` (gold) and an item notice; the engine's sim logs neither, so `PickupWatch` reads the world each frame:
the player's gold rising, and a hero's pack gaining items that carry the `new` flag (set only by the pickup, `gear.pick_up`).
Texts: `"%s %d %s"` = main 0x58 "Picked up", the amount, 0x59 "gold"; `"%s %s"` = 0x55 "Picked up" + the item name, with
`" (%s %d %s)"` = 0x56 "now", N, 0x57 "pieces" when the stack holds more than one.  Slot: log (normal table), lifetime 3000 ms."""

from engine.sim import gear as gear_mod

LOG = "normal"                  # message colour slot `0x5f17f8` = table `0x620928`
SYSTEM = None                   # slot `0x5f17f4` = table `0x61fa80` (the MessageLine default)
PICKUP_MS = 3000
T_GOLD, T_GOLD_WORD, T_ITEM, T_NOW, T_PIECES = 0x58, 0x59, 0x55, 0x56, 0x57


class PickupWatch:
    """Per frame: the new gold and pack items of the local player.  `poll(...)` returns `[(text, colour, ms)]`."""

    def __init__(self, world, player_id):
        self.player_id = player_id
        self.gold = world.players[player_id].gold
        self.new = self._new_counts(world)

    def _new_counts(self, world):
        out = {}
        for u in world.units.values():
            if u.owner != self.player_id or not u.pack:
                continue
            for it in u.pack:
                if it.new:
                    k = (u.id, it.code, it.mods)
                    out[k] = out.get(k, 0) + it.count
        return out

    def poll(self, world, text):
        msgs = []
        p = world.players[self.player_id]
        if p.gold > self.gold:
            msgs.append(("%s %d %s" % (text.line(T_GOLD), p.gold - self.gold, text.line(T_GOLD_WORD)), LOG, PICKUP_MS))
        self.gold = p.gold
        now = self._new_counts(world)
        for k, n in sorted(now.items()):
            if n > self.new.get(k, 0):
                msgs.append((self._item_line(world, k, n, text), LOG, PICKUP_MS))
        self.new = now
        return msgs

    @staticmethod
    def _item_line(world, key, n, text):
        _, code, mods = key
        table = world.item_table
        name = None
        if table is not None:
            name = table.display_name(code, gear_mod.effects_of(mods))
        line = "%s %s" % (text.line(T_ITEM), name or "item %#x" % code)
        if n > 1:
            line += " (%s %d %s)" % (text.line(T_NOW), n, text.line(T_PIECES))
        return line


# -- the other lines of the message list that occur in single player (ui-layout 11.5) ---------------------------------------------------------
OPTION_MS = 2000                # every Ctrl+ option toggle (`push 0x7d0` at 0x40ced7 ... 0x40d1da)
SCRIPT_MS = 30000               # script message `0xfa` (`push 0x7530` at 0x4860a2)
RETREAT_TEXT, DAY_NIGHT_TEXT, SMOOTHING_TEXT = 0x5E, 0x68, 0x6A         # main.txt base ids (+ state)
P_COLOURS, P_AUTOCAST, P_NEW_MISSION = 0x55, 0x73, 0x61                 # patch.txt ids: colours + state, autocast + level, "You've got a new mission!"


class OptionToggles:
    """The state of the Ctrl+ option keys of `FUN_0040c8a0` that the engine has no other home for, and their message lines (system slot, 2000 ms).
    `press(name, main, patch)` returns the line text or None for an unknown key.
    W retreat mode `view+0xab4` cycles 0 -> 1 -> 2 -> 0 (`FUN_0041f090`, CONFIRMED), text `main 0x5e + mode` (the argument of the text call is
    `FUN_0041f160`, INFERRED = that mode); the exe also sends the mode to the sim (`FUN_0041a4ef`, message `0x46` sub 1): the window queues `SetRetreatMode` after this
    press; the mode is kept here.  N day / night `0x622770` flips, text `main 0x68 + new`; the tint it controls (lighting.md) is not built.  C message
    colours `0x622818` flips, text `patch 0x55 + new` ("Standard / Alternative message colors"); the alternative tables `0x61fb08` / `0x61fba8` are not decoded,
    the line keeps the standard tables.  U auto-cast level: `0x62277c & 0x38` cycles 0x08 -> 0x18 -> 0x38 -> 0x08 (`FUN_0041a54a`, CONFIRMED), text
    `patch 0x73 + level` with level 1 when bit 0x10, 2 when bit 0x20 (CONFIRMED); the start value 0x08 is the registry default (INFERRED, ai.md 14); the byte is
    not sent to the sim here (the sim's party-AI byte is its own)."""

    def __init__(self):
        self.retreat, self.day_night, self.colours, self.autocast = 0, True, 0, 0x08

    def press(self, name, main, patch):
        if name == "w":
            self.retreat = (self.retreat + 1) % 3
            return main.line(RETREAT_TEXT + self.retreat)
        if name == "n":
            self.day_night = not self.day_night
            return main.line(DAY_NIGHT_TEXT + int(self.day_night))
        if name == "c":
            self.colours = 1 - self.colours
            return patch.line(P_COLOURS + self.colours)
        if name == "u":
            low = self.autocast & 0x38
            self.autocast = (self.autocast & 7) | {0x08: 0x18, 0x18: 0x38, 0x38: 0x08}.get(low, low)
            level = 2 if self.autocast & 0x20 else 1 if self.autocast & 0x10 else 0
            return patch.line(P_AUTOCAST + level)
        return None
