"""Hero / class voices (docs/engine/audio.md 2.3, formats/sound.md 4.2): the bank of a unit, the order -> voice slot table, the shared per-unit
cooldown and the variant draw.  Pure; the draws come from the audio layer's own `Rng` (never `World.rng`)."""

from allods2.formats.soundtable import BANKS

COOLDOWN_MS = 3000              # `now - view+0x1bc >= 3000` (CONFIRMED `0x4681c8`...)
SELECT_COOLDOWN_MS = 2000       # the select voice `0x468460`
BANK_DIR = "sfx/characters/%s/"

# command class name -> (voice category, skip rule applies).  CONFIRMED audio.md 2.3: move / swarm are skipped when the view's `+0x78 == 1`
# (asm `0x418c99`; its meaning is open: the caller passes `skip`); patrol / use-structure play move with no skip test.
COMMAND_VOICE = {
    "MoveUnits": ("move", True), "Swarm": ("swarm", True), "UseStructure": ("move", False), "AttackUnit": ("attack", False),
    "Guard": ("defend", False), "Stop": ("defend", False), "StandStill": ("defend", False), "Retreat": ("retreat", False),
    "PickUp": ("pickup", False), "PickAll": ("pickup", False), "SelectUnits": ("select", False),
}


def reduced_id(u):
    """`unit+0x1dc` = the reduced server id (`10210 -> 21`, docs/engine/unit-struct.md; the same rule as `death.remove_dead`)."""
    sid = u.server_id
    return (sid // 10) % 1000 if sid > 10000 else sid


def bank_of(u):
    """The voice bank of a unit (`FUN_00468094`), None when it has none (generic fighters: silent).  Types 1-6 = xbow, knight, druid, troll, orc, mage;
    21 = a hero by the template name `Start_<gender><class>` (INFERRED: M/F then F/M: male fighter aldor, female fighter sagita, male mage hildarius,
    female mage galinel; the exe reads flag bits `+0x1b8` 4 / 2); 22 = igles; 23 = dina."""
    if not u.human or u.stats is None:
        return None
    t = reduced_id(u)
    if 1 <= t <= 6:
        return BANKS[5 + t]
    if t == 22:
        return BANKS[4]
    if t == 23:
        return BANKS[5]
    if t == 21:
        n = u.stats.name
        female = len(n) > 6 and n.startswith("Start_") and n[6] == "F"
        mage = len(n) > 7 and n.startswith("Start_") and n[7] == "M"
        return BANKS[int(female) + 2 * int(mage)]
    return None


def is_voice_hero(u):
    """Wound and death sounds of `0x467f60` come from the voice bank for a unit with `view+0x1b8 & 0x11` or type word `+0x1dc <= 0x17` (sounds.md 4.1; the flag
    test is not modelled: heroes are covered by the type word); such a unit without a bank (types 7-20, the generic `Man_*`) is silent."""
    return bool(u.human) and 0 < reduced_id(u) <= 0x17


class Voices:
    """The seven order / select voices.  `banks` = `soundtable.hero_banks(fs)` (bank -> category -> [paths])."""

    def __init__(self, banks, rng):
        self.banks, self.rng = banks, rng
        self.stamp = {}                     # unit uid -> ms of its last voice (one stamp shared by all seven voices)

    def pick(self, units):
        """`FUN_0041da16`'s random choice (`size * rand() / 0x7fff`, drawn from the audio RNG): one alive unit with a bank; heroes (types >= 21) first,
        else the classes (INFERRED stand-in for the three flag arrays; those arrays' meaning is open)."""
        alive = [u for u in units if u.hp > 0 and bank_of(u)]
        pool = [u for u in alive if reduced_id(u) >= 21] or alive
        if not pool:
            return None
        return pool[min(len(pool) - 1, len(pool) * self.rng.rand15() // 0x7FFF)]

    def voice(self, command, units, now_ms, skip=False):
        """-> `(unit, sound or None, result)`: `result` is `ok`, `dropped:cooldown`, or `silent` (no unit / no bank sample / the move skip rule).  `command` is the
        command class name.  The stamp is written before the sample lookup, so an empty slot still starts the cooldown."""
        cat, skippable = COMMAND_VOICE[command]
        if skippable and skip:
            return None, None, "silent"
        u = self.pick(units)
        if u is None:
            return None, None, "silent"
        gap = SELECT_COOLDOWN_MS if cat == "select" else COOLDOWN_MS
        if now_ms - self.stamp.get(u.uid, -(1 << 31)) < gap:
            return u, None, "dropped:cooldown"
        self.stamp[u.uid] = now_ms
        bank = bank_of(u)
        files = self.banks.get(bank, {}).get(cat, [])
        if not files:
            return u, None, "silent"
        path = files[self.rng.rand(len(files) - 1)]
        return u, ("hero", bank, path[len(BANK_DIR % bank):-4]), "ok"


def voice_path(sound):
    """Game path of a `("hero", bank, slot)` sound."""
    return (BANK_DIR % sound[1]) + sound[2] + ".wav"
