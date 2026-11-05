"""The viewer's knowledge of unit types (docs/engine/ui-layout.md 11.1): the table behind the info panel's detail level.

The exe keeps one byte per unit type id (0..0x9ff) per player (`player+0x44`, mirrored in the client at `+0x3f70`; it is the
`0x55555555` settings chunk of the character file, saves.md 3.5).  A hero's kill of a unit of type `id` adds 1 to the byte while it is
below 14 (`FUN_0052b459`, `0x52b87d`..); the panel's detail level is `byte >> 1`, 0..7.  No pygame, no world state: the table is fed from the
sim's `Killed` fight-log entries."""

TABLE_SIZE = 0xA00
CAP = 14                # the byte stops at 14 (detail 7)
LEVEL_MAX = 7


def knowledge_id(u):
    """The unit's `+0x14c` / client `+0x1dc`: the template server id, a human's reduced above 10000 (`(v / 10) % 1000`, units.md)."""
    v = u.server_id
    return (v // 10) % 1000 if u.human and v > 10000 else v


def raw_id(server_id, human):
    return (server_id // 10) % 1000 if human and server_id > 10000 else server_id


class Knowledge:
    """`table[id]` bytes; `feed(world, player_id)` reads the new `Killed` entries of `world.fight_log` (read, not consumed)."""

    def __init__(self, blob=None):
        self.table = bytearray(TABLE_SIZE)
        if blob:
            self.table[:len(blob)] = bytes(blob[:TABLE_SIZE])
        self._last = None               # the last log entry already counted (identity)

    def level(self, id_):
        """`FUN_0046aa1d`: 0 for id 0 or >= 0xa00, else `byte >> 1`."""
        if not 0 < id_ < TABLE_SIZE:
            return 0
        return self.table[id_] >> 1

    def credit(self, id_):
        """One credited kill of type `id_`: `byte += 1` while `byte < 14` (the exe also skips id 0 and ids >= 0xa00)."""
        if 0 < id_ < TABLE_SIZE and self.table[id_] < CAP:
            self.table[id_] += 1
            return True
        return False

    def feed(self, world, player_id):
        """Count the `Killed` entries (of kills by `player_id`'s heroes) added to `world.fight_log` since the last call; returns how many.
        Call it before anything drains the log."""
        from engine.world import Killed
        log = world.fight_log
        start = 0
        if self._last is not None:
            for i in range(len(log) - 1, -1, -1):
                if log[i] is self._last:
                    start = i + 1
                    break
        n = 0
        for e in log[start:]:
            if isinstance(e, Killed) and e.killer_owner == player_id and self.credit(raw_id(e.server_id, e.human)):
                n += 1
        if log:
            self._last = log[-1]
        return n

    def to_blob(self):
        """The 0xa00 bytes of the character file's settings chunk."""
        return bytes(self.table)
