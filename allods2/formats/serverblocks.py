"""Field layouts of the raw blocks inside the server stream of a saved game (docs/formats/saves.md 6.8-6.12; step L10e-A).

The serialisers copy these blocks as raw bytes (`FUN_005aa981(ptr, n)`), so a block is kept as `bytes` and these tables only name the fields
the engine needs when it resumes a mission.  `Layout.get / set` read and write one field and leave every other byte alone, so a parsed
block written back is exact; bytes that no field covers stay what the file had.

Every field carries a tag: `C` = CONFIRMED (a routine of allods2.exe reads or writes the offset, cited in docs/engine/unit-struct.md,
ai.md or the saves.md table), `I` = INFERRED (code shape or analogy).  Offsets are relative to the start of the block (the object the
exe's serialiser is called on), and `abs` names the offset in the owning struct where that helps.
"""

import struct
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class Field:
    name: str
    off: int
    fmt: str            # struct code: B b H h I i
    tag: str = "I"      # C / I
    note: str = ""

    @property
    def size(self):
        return struct.calcsize("<" + self.fmt)


class Layout:
    """A raw block of `size` bytes with named fields (little endian)."""

    def __init__(self, name: str, size: int, fields: Iterable[Field]):
        self.name = name
        self.size = size
        self.fields: Dict[str, Field] = {}
        for f in fields:
            if f.name in self.fields:
                raise ValueError("%s: duplicate field %s" % (name, f.name))
            if f.off + f.size > size:
                raise ValueError("%s.%s runs past the block" % (name, f.name))
            self.fields[f.name] = f

    def blank(self):
        return bytes(self.size)

    def _check(self, raw):
        if len(raw) != self.size:
            raise ValueError("%s block: %d bytes, expected %d" % (self.name, len(raw), self.size))

    def get(self, raw, name):
        f = self.fields[name]
        self._check(raw)
        return struct.unpack_from("<" + f.fmt, raw, f.off)[0]

    def set(self, raw, **values):
        """A copy of `raw` with the named fields replaced."""
        self._check(raw)
        out = bytearray(raw)
        for name, v in values.items():
            f = self.fields[name]
            if f.fmt in "BHI":
                v &= (1 << (8 * f.size)) - 1
            struct.pack_into("<" + f.fmt, out, f.off, v)
        return bytes(out)

    def decode(self, raw) -> Dict[str, int]:
        return {n: self.get(raw, n) for n in self.fields}

    def encode(self, base=None, **values):
        return self.set(base if base is not None else self.blank(), **values)

    def overlaps(self) -> List[Tuple[str, str]]:
        fs = sorted(self.fields.values(), key=lambda f: f.off)
        return [(a.name, b.name) for a, b in zip(fs, fs[1:]) if a.off + a.size > b.off]


F = Field

# --- Position: the first 0xc raw bytes of every game object (`FUN_0052cf8d` calls `FUN_0054ffd1` with ECX = *(object + 0x10)) -------------------------
POSITION = Layout("Position", 12, [
    F("cell_x", 0, "B", "C", "cell x (FUN_0054ffb0)"),
    F("cell_y", 1, "B", "C", "cell y (FUN_0054ffc0)"),
    F("packed", 2, "H", "C", "(y << 8) + x (FUN_0054ff9e)"),
    F("sub_x", 4, "B", "C", "sub-cell x, 0x80 = centre (FUN_00551383)"),
    F("sub_y", 5, "B", "C", "sub-cell y"),
    F("world", 8, "I", "C", "stale pointer to the map object (0x670e48 when written); not remapped by the loader (INFERRED harmless)"),
])


def position_raw(cell_x, cell_y, sub_x=0x80, sub_y=0x80, world=0):
    """The 12 bytes of a Position: cell, packed cell word, sub-cell offsets (full coordinate = cell * 256 + sub), world pointer."""
    return POSITION.encode(cell_x=cell_x, cell_y=cell_y, packed=(cell_y << 8) + cell_x, sub_x=sub_x, sub_y=sub_y, world=world)


# --- Mover: `*(unit + 0x1c0)`, 0xb4 bytes (docs/engine/unit-struct.md 7.1) ---------------------------------------------------------------------------
MOVER = Layout("Mover", 0xB4, [
    F("facing", 0x00, "B", "C", "current facing 0..255 clockwise from up; engine Unit.facing"),
    F("target_facing", 0x01, "B", "C", "engine Mover.target_facing"),
    F("b05", 0x05, "B", "C", "ctor 0x41"),
    F("step_target", 0x06, "H", "C", "packed cell being entered; engine Mover.step_target"),
    F("b08", 0x08, "B", "C", "ctor 5"),
    F("consumed", 0x09, "B", "C", "waypoints consumed since the plan, 0xff = re-plan; engine Mover.consumed"),
    F("turn_rate", 0x0A, "B", "C", "engine Mover.turn_rate"),
    F("d6c", 0x6C, "I", "C", "set 1 by mode 1, never read"),
    F("step_from", 0x70, "H", "C", "cell where the step began; engine Mover.step_from"),
    F("eff_speed", 0x72, "H", "I", "FUN_0055687d result"),
    F("dest", 0x74, "H", "C", "planned destination cell; engine Mover.dest"),
    F("tail", 0x76, "H", "C", "last cell of the plan; engine Mover.tail"),
    F("since_hop", 0x78, "B", "C", "ticks waited at a centre; engine Mover.since_hop"),
    F("follow_ptr", 0x7C, "I", "C", "followed object: raw pointer remapped by FUN_00559681 on load; engine Mover.follow"),
    F("stamp_cell", 0x80, "H", "C", "cell word last stamped by FUN_0055be86; engine Mover.stamp_cell"),
    F("follow_len", 0x8A, "H", "I", "engine Mover.static_len"),
    F("follow_cell", 0x8C, "H", "I", "engine Mover.follow_cell"),
    F("arrived", 0x90, "I", "C", "1 = position == tail; engine Mover.arrived"),
    F("follow_target", 0x94, "H", "I", ""),
    F("follow_mine", 0x96, "H", "I", ""),
    F("failed", 0x98, "I", "C", "path request / exhausted flag; engine Mover.failed"),
    F("b9c", 0x9C, "B", "C", ""),
    F("turn_done", 0x9D, "B", "C", "engine Mover.turn_done"),
    F("turning", 0xA0, "I", "C", "multi-tick turn in progress; engine Mover.turning"),
    F("turn_ticks", 0xA4, "B", "C", "engine Mover.turn_ticks"),
    F("step_len", 0xA8, "H", "C", "engine Mover.step_len"),
    F("step_ticks", 0xAA, "H", "C", "engine Mover.step_ticks"),
    F("steps", 0xAC, "H", "C", "ticks done in the step; engine Mover.steps"),
    F("step_dir", 0xAE, "H", "C", "dir8; engine Mover.step_dir"),
    F("dx", 0xB0, "b", "C", "engine Mover.dx"),
    F("dy", 0xB1, "b", "C", "engine Mover.dy"),
])

# --- Brain: `*(unit + 0x1c4)`, 0xb8 bytes (unit-struct.md 8.1; ai.md) -------------------------------------------------------------------------------
BRAIN = Layout("Brain", 0xB8, [
    F("anchor", 0x00, "H", "C", "home cell, packed; engine Unit.anchor"),
    F("patrol_wp", 0x02, "H", "C", "engine Unit.patrol_wp"),
    F("patrol_walk", 0x04, "I", "C", "engine Unit.patrol_walk"),
    F("mode", 0x08, "B", "C", "AI mode 0..15 (the engine's mode_* flags)"),
    F("order", 0x09, "B", "C", "low-level order: 0 none, 1 swing, 2 cast, 3 step, 4 wait; engine Unit.brain_order"),
    F("dest", 0x0A, "H", "C", "destination cell, packed; engine Mover.goal / pick_cell / use_dest"),
    F("target_ptr", 0x0C, "I", "C", "attack target: raw pointer remapped by FUN_00576d00; engine Unit.target"),
    F("leader_ptr", 0x10, "I", "C", "follow leader (remapped); engine Unit.leader"),
    F("range", 0x14, "B", "C", "engine Unit.range"),
    F("retry", 0x15, "B", "C", "engine Unit.swing_count"),
    F("w16", 0x16, "h", "C", "ctor 0xffdc"),
    F("approach_ptr", 0x18, "I", "C", "mode 4 object (remapped); engine Unit.follow_target"),
    F("pool_ptr", 0x20, "I", "C", "group pass: chosen pool unit (remapped; ai.md 3 step 4)"),
    F("cast_target_ptr", 0x28, "I", "C", "remapped; engine Unit.cast_target"),
    F("spell_ptr", 0x30, "I", "C", "remapped; engine Unit.cast_wrapper"),
    F("cast_cell", 0x3C, "H", "C", "engine Unit.cast_cell"),
    F("withdraw", 0x40, "I", "C", "engine Unit.withdraw_hp"),
    F("wimpy", 0x44, "I", "C", "engine Unit.wimpy_hp"),
    F("thr_class", 0x4C, "B", "C", "always 0"),
    F("stopped", 0x50, "I", "C", "engine Unit.stopped"),
    F("idle_gate", 0x54, "I", "C", "mode 11 gate"),
    F("cast_kind", 0x5C, "I", "C", "1 = object target, 0 = cell"),
    F("spell_valid", 0x60, "I", "C", "engine Unit.ai_cast"),
    F("struct_ptr", 0x68, "I", "C", "structure / sack object of order 0xf (remapped); engine Unit.use_obj"),
    F("follow_dist", 0x70, "B", "C", "engine Unit.follow_range"),
    F("see_invis", 0x71, "B", "C", "ctor 1; data.bin p36"),
    F("auto_spell", 0x78, "B", "C", "engine Unit.auto_spell"),
    F("special1", 0x7C, "I", "I", "special-attack spell ids"),
    F("special2", 0x80, "I", "I", ""),
    F("special3", 0x84, "I", "I", ""),
    F("prob1", 0x88, "I", "I", "their probabilities"),
    F("prob2", 0x8C, "I", "I", ""),
    F("prob3", 0x90, "I", "I", ""),
    F("last_caster", 0x94, "I", "C", "spell bookkeeping"),
    F("cast_tick", 0x98, "I", "C", ""),
    F("cast_cell2", 0x9C, "H", "C", ""),
    F("teleport", 0xB0, "H", "C", "pending teleport target (y << 8 | x); engine Unit.teleport_to"),
    F("patrol_list_ptr", 0xB4, "I", "C", "stale pointer of the patrol CList; the stream's CList<u16> follows the block and replaces it on load"),
])

# --- the unit's embedded sub-blocks (docs/engine/unit-struct.md 2) ----------------------------------------------------------------------------------
BLK_A6 = Layout("BlkA6", 0x18, [F("tohit", 0x00, "h", "C", "+0xa6: attack skill / to-hit (monster param 14; humans 0)")]
                + [F("skill%d" % k, 2 + 2 * k, "H", "C", "+0xa8 + 2k: general, five school / weapon skills (human params 10-15)") for k in range(6)]
                + [F("dmg_lo", 0x0E, "B", "C", "+0xb4 physical minimum (bit 7: stored / 15)"), F("dmg_sp", 0x0F, "B", "C", "+0xb5 spread"),
                   F("kind", 0x10, "B", "C", "+0xb6 attack type 0..5 (the weapon's school)"), F("dmg_lo2", 0x11, "B", "C", "+0xb7 second part minimum"), F("dmg_sp2", 0x12, "B", "C", "+0xb8"),
                   F("elem_lo", 0x13, "B", "C", "+0xb9 elemental minimum"), F("elem_sp", 0x14, "B", "C", "+0xba"), F("elem", 0x15, "B", "C", "+0xbb element 1..5")])
BLK_114 = Layout("Blk114", 0x18, [F("skill%d" % k, 2 + 2 * k, "H", "C", "+0x116 + 2k: copy of the skills 0..5 (FUN_00514ea1)") for k in range(6)])
# the armour block (unit-struct 11): `+0xbe` the unit's own, `+0xfe` the item bonus copy
BLK_BE = Layout("BlkBE", 0x16, [F("defence", 0x00, "h", "C", "+0xbe: defence (human param 9; monster 15), halved at death"), F("absorb", 0x02, "h", "C", "+0xc0 absorption")]
                + [F("prot%d" % k, 0x04 + 2 * k, "h", "C", "+0xc2 + 2k protection phys (never read), fire, water, air, earth, astral") for k in range(6)]
                + [F("res%d" % k, 0x10 + k, "B", "C", "+0xce + k resistance 0, blade, axe, bludgeon, pike, shooting (percent)") for k in range(6)])
BLK_D4 = Layout("BlkD4", 0x40, [F("attr%d" % k, k, "B", "C", "+0xd4 + k running attribute totals body, reaction, mind, spirit") for k in range(4)]
                + [F("speed_bonus", 0x04, "h", "C", "+0xd8"), F("hp_max_bonus", 0x08, "h", "C", "+0xdc"),
                   F("hp_regen_bonus", 0x0A, "H", "C", "+0xde percent (0x50fd27)"), F("mana_max_bonus", 0x0C, "h", "C", "+0xe0"),
                   F("mana_regen_bonus", 0x0E, "H", "C", "+0xe2 percent (0x50fe1b)"), F("scan_bonus", 0x10, "h", "C", "+0xe4 scan range x 256"), F("tohit_bonus", 0x12, "h", "C", "+0xe6")]
                + [F("skill_bonus%d" % k, 0x14 + 2 * k, "h", "C", "+0xe8 + 2k skill bonuses (general, five)") for k in range(6)]
                + [F("dmg_min_bonus", 0x20, "B", "C", "+0xf4"), F("dmg_max_bonus", 0x21, "B", "C", "+0xf5"),
                   F("elem_min_bonus", 0x25, "B", "C", "+0xf9"), F("elem_max_bonus", 0x26, "B", "C", "+0xfa"), F("elem_bonus", 0x27, "B", "C", "+0xfb element 1..5")])
# +0xfe..+0x113 inside BLK_D4 (offset 0x2a, 0x16 bytes) is a second armour block (the equipped items' sum)
BLK_D4_ARMOUR = 0x2A

# --- the group's AI record `*(group + 0x3c)`, 0x50 bytes (ai.md 2) -------------------------------------------------------------------------------------
GROUP_AI = Layout("GroupAI", 0x50, [
    F("home", 0x00, "H", "C", ""),
    F("order", 0x20, "B", "C", "group order 0 / 1 guard / 2 hold / 3 stand / 5 swarm / 0x11 wander / 0x12 AI / 0x13 still / 0xff empty (ai.md 14)"),
    F("centroid", 0x24, "I", "C", "(cy16 << 16) + cx16"),
    F("centroid_cell", 0x28, "H", "C", ""),
    F("radius_max", 0x2A, "B", "C", ""),
    F("scan_max", 0x2B, "B", "C", ""),
    F("reach", 0x2C, "B", "C", ""),
    F("pool_radius", 0x2D, "B", "C", ""),
    F("seen_once", 0x30, "B", "C", ""),
    F("passes", 0x34, "B", "C", ""),
    F("pool_base", 0x38, "B", "C", ""),
    F("speed", 0x44, "B", "C", "group speed (formation)"),
    F("active", 0x45, "B", "C", "awake flag, default 1"),
    F("awake", 0x48, "B", "C", "kept awake by a script (ai.md 15)"),
])

# --- the cell record of `map + 0x54084`, 0x3c bytes (effects.md 6.4, unit-struct.md "Cell record effect") ------------------------------------------------
CELL_RECORD = Layout("CellRecord", 0x3C, [
    F("saved_cost", 0x00, "B", "C", "cost byte saved at creation (FUN_005508a0)"),
    F("saved_block", 0x01, "B", "C", "block byte saved at creation"),
    F("slots_used", 0x02, "B", "C", "used-slot count"),
    F("slot0", 0x14, "I", "C", "Wall of Fire carrier (raw pointer of a SpellEffect; INFERRED remapped by the loader)"),
    F("slot1", 0x18, "I", "C", ""),
    F("slot2", 0x1C, "I", "C", "Poison Cloud"),
    F("slot3", 0x20, "I", "C", "Wall of Earth"),
    F("slot4", 0x24, "I", "C", "Light"),
    F("slot5", 0x28, "I", "C", "Darkness"),
    F("trap_spell", 0x34, "B", "C", "scripted trap effect id (0x17 = Teleport)"),
    F("trap_dest_x", 0x38, "B", "C", "Teleport destination x"),
    F("trap_dest_y", 0x39, "B", "C", "y"),
    F("index", 0x3A, "H", "C", "the cell's index word"),
])

# --- the 6-byte "effect6" of a VirtualCaster (+0x40 sub-object) = cell record +0x34..+0x39 (INFERRED same type, FUN_0055b978) -----------------------------------
EFFECT6 = Layout("Effect6", 6, [
    F("spell", 0, "B", "I", "spell id"),
    F("dest_x", 4, "B", "C", "cell record +0x38"),
    F("dest_y", 5, "B", "C", "cell record +0x39"),
])

# --- the script runner block of FUN_0057468d (docs/engine/triggers.md) --------------------------------------------------------------------------------
RELATIONS_PLAYERS = 70          # the 0x132c block = 8 header bytes + 70 x 70 relation bytes ([a * 0x46 + 8 + b], ai.md 4: CONFIRMED arithmetic)


def relation(block, a, b):
    """Relation byte of player `a` toward `b` in the 0x132c script-state block (bit 1 = war)."""
    if len(block) != 0x132C:
        raise ValueError("relation block is 0x132c bytes")
    return block[a * RELATIONS_PLAYERS + 8 + b]


def set_relation(block, a, b, v):
    out = bytearray(block)
    out[a * RELATIONS_PLAYERS + 8 + b] = v
    return bytes(out)


# --- cell-record hash order (INFERRED: standard MFC CMap, 17 buckets, hash = key >> 4, new entries at the head of the chain) -------------------------------
CMAP_BUCKETS = 17


def cmap_order(keys):
    """The order in which `CMap<u16, 60 bytes>::Serialize` (`FUN_0055f6b0`) walks entries inserted in `keys` order (unique keys)."""
    buckets = [[] for _ in range(CMAP_BUCKETS)]
    for k in keys:
        buckets[(k >> 4) % CMAP_BUCKETS].insert(0, k)
    return [k for b in buckets for k in b]


# --- stream field -> engine Unit field (the mapping for the next step, L10e-B) -------------------------------------------------------------------------------
UNIT_MAP = (
    ("base.raw12 cell_x / cell_y", "Unit.x / Unit.y"),
    ("base.raw12 sub_x / sub_y", "Unit.sub_x / Unit.sub_y"),
    ("mover.facing", "Unit.facing"),
    ("base.id (+4)", "Unit.net_id (0 for a map unit: the exe id is the object table key; engine id = 0x6000 + uid from base.d08 +8)"),
    ("base.d08 (+8)", "Unit.uid"),
    ("base.w0c (+0xc)", "template index (UnitType.index)"),
    ("base.w0e (+0xe)", "Unit.type_id"),
    ("base.link (+0x14)", "Unit.owner (Player.ptr key)"),
    ("effects", "Unit.effects (Effect list: id, kind, value, ticks)"),
    ("list1c8 / list1e4", "Mover.static_path / Unit.path (packed cells, front first)"),
    ("words[8..13] (+0x94..)", "Unit.hp, hp_max, (regen), mana, mana_max, (regen)"),
    ("b_a2 / b_a3", "Unit.hp_acc / Unit.mana_acc"),
    ("b4a / b4b (+0x4a, +0x4b)", "Unit.move_type / Unit.face"),
    ("b4c (+0x4c)", "creature flags (bit 4 mage, 8 off the map)"),
    ("r50 / r54 / r58", "Unit.order / Unit.state / Unit.phase"),
    ("b60 / b61", "target cell of state 0xe (Unit.cast_cell)"),
    ("b6c", "Unit.timer"),
    ("d5c / d64 / d44 / d40", "Unit.swing_target / carrier ptr / (+0x44) / Unit.last_attacker"),
    ("b134 / b135 / b136", "windup / recovery / Unit.done"),
    ("d138", "Unit.step_end (rest clock, absolute tick)"),
    ("b13c", "Unit.death_seen"),
    ("packed low word", "Unit.hero_no / server_id"),
    ("d144", "effect mask (derived: Unit.effects)"),
    ("d130", "Unit.xp_total"),
    ("brain.*", "see BRAIN field notes (Unit.mode_*, target, range, ...)"),
    ("mover.*", "see MOVER field notes (Mover.*)"),
)
