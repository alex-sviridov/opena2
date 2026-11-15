"""Mission saves: `World` <-> `game%d.sav` with the loaded flag 1 (docs/engine/save.md L10e-B, docs/formats/saves.md 6.12 / 7).  Pure: no pygame.

Two layers share one file:

* **the exe's view** (the server stream, `allods2.formats.serverstream`): every player with its groups and units (position, facing, HP / mana, orders, mover,
  brain, effects, items, books, pools), structures, ground sacks, spell carriers, hidden casters, the cell records, the script state, the tick counters.  This is
  what the original writes and reads; `build_stream` writes it from a `World`, `world_from_stream` rebuilds a `World` from it the way the exe rebuilds its own
  state (derived state: footprint slots, fog seen bits, the compiled script, AI wake map ...).
* **the engine extension** (`Engine/Blob` in the client tail's `.reg` tree, DECISION): the engine holds state the exe either does not store (the script's
  stage / pass counters sit in an unsaved gap of the runner object, the RNG state, the effect caster ids, the cell-slot tables ...) or stores only in raw blocks
  we do not model.  Writing it beside the stream makes save -> load -> N ticks equal N ticks without a save, bit for bit.  The original game ignores the
  key (INFERRED: the loader reads named keys, so a foreign key is skipped; VERIFY IN GAME); a save the original wrote has no blob and loads through the stream.

`world_to_save(world, campaign, client_state, description)` and `world_from_save(save, assets, ...)` are the two directions.
"""

import base64
import json
import struct
import zlib
from collections import Counter
from dataclasses import dataclass, fields, is_dataclass
from types import SimpleNamespace

import numpy as np

from allods2.formats import saves as S
from allods2.formats import serverblocks as B
from allods2.formats import serverstream as SS
from engine import world as W
from engine.rng import Rng

PTR_BASE, PTR_STEP = 0x00B00000, 0x40
RNG_MAGIC = 0x32474E52          # "RNG2": the engine's LCG state in the last 8 bytes of the 400-byte debug block (DECISION, saves.md 7)
BLOB_VERSION = 1
SCRATCH_SLOTS = 12


# --- the generic state codec (engine extension) ---------------------------------------------------------------------------------------------------

def _qual(cls):
    return "%s.%s" % (cls.__module__.rsplit(".", 1)[-1], cls.__name__)


def _registry():
    from allods2.formats import unitstats
    from engine.sim import campaign, combatstats, spells, traps
    reg = {}
    for mod in (W, combatstats, spells, campaign, unitstats, S):
        for name, obj in vars(mod).items():
            if isinstance(obj, type) and is_dataclass(obj):
                reg[_qual(obj)] = obj
    reg["CasterStats"] = traps.CasterStats
    return reg


_REG = None
SKIP = {("Mover", "last_plan"), ("Mover", "last_hop"), ("Mover", "last_hop_goal")}


class Encoder:
    """Python state -> JSON-able.  Dataclass instances are memoised so shared objects stay shared (a unit in `script.phased` and in a group)."""

    def __init__(self, stats_of=None):
        self.memo = {}
        self.stats_of = stats_of

    def enc(self, o):
        t = type(o)
        if o is None or t in (bool, int, float, str):
            return o
        if t is tuple:
            return {"t": [self.enc(x) for x in o]}
        if t is list:
            return [self.enc(x) for x in o]
        if t is dict:
            return {"d": [[self.enc(k), self.enc(v)] for k, v in o.items()]}
        if t is set or t is frozenset:
            return {"s": [self.enc(x) for x in sorted(o, key=repr)]}
        if t is Counter:
            return {"C": [[self.enc(k), v] for k, v in o.items()]}
        if t in (bytes, bytearray):
            return {"b": bytes(o).hex(), "ba": t is bytearray}
        if isinstance(o, np.ndarray):
            return {"a": base64.b64encode(zlib.compress(np.ascontiguousarray(o).tobytes(), 6)).decode(), "dt": str(o.dtype), "sh": list(o.shape)}
        if isinstance(o, (np.integer,)):
            return int(o)
        if t is SimpleNamespace:
            return {"ns": [[k, self.enc(v)] for k, v in vars(o).items()]}
        if t is Rng:
            return {"rng": o.state}
        if t.__name__ == "CasterStats":
            return {"cs": [[k, self.enc(v)] for k, v in o.items()]}
        if is_dataclass(o):
            n = self.memo.get(id(o))
            if n is not None:
                return {"r": n}
            n = self.memo[id(o)] = len(self.memo)
            out = {}
            for f in fields(o):
                if (t.__name__, f.name) in SKIP:
                    continue
                v = getattr(o, f.name)
                if t is W.Unit and f.name == "stats" and v is not None and self.stats_of is not None:
                    ref = self.stats_of(o)
                    if ref is v:
                        out[f.name] = {"ut": [v.kind, v.index]}
                        continue
                out[f.name] = self.enc(v)
            return {"o": _qual(t), "i": n, "f": out}
        raise TypeError("cannot save %r (%s)" % (o, t.__name__))


class Decoder:
    def __init__(self, unit_type=None):
        global _REG
        if _REG is None:
            _REG = _registry()
        self.objs = {}
        self.unit_type = unit_type

    def dec(self, d):
        t = type(d)
        if d is None or t in (bool, int, float, str):
            return d
        if t is list:
            return [self.dec(x) for x in d]
        if "t" in d:
            return tuple(self.dec(x) for x in d["t"])
        if "d" in d:
            return {self.dec(k): self.dec(v) for k, v in d["d"]}
        if "s" in d:
            return {self.dec(x) for x in d["s"]}
        if "C" in d:
            return Counter({self.dec(k): v for k, v in d["C"]})
        if "b" in d:
            raw = bytes.fromhex(d["b"])
            return bytearray(raw) if d.get("ba") else raw
        if "a" in d:
            raw = inflate(base64.b64decode(d["a"]))
            return np.frombuffer(raw, dtype=np.dtype(d["dt"])).reshape(d["sh"]).copy()
        if "ns" in d:
            return SimpleNamespace(**{k: self.dec(v) for k, v in d["ns"]})
        if "rng" in d:
            return Rng(d["rng"])
        if "cs" in d:
            return _REG["CasterStats"]({k: self.dec(v) for k, v in d["cs"]})
        if "ut" in d:
            return self.unit_type(*d["ut"])
        if "r" in d:
            return self.objs[d["r"]]
        if "o" in d:
            cls = _REG[d["o"]]
            obj = cls.__new__(cls)
            self.objs[d["i"]] = obj
            have = {f.name: f for f in fields(cls)}
            for name, f in have.items():
                if name in d["f"]:
                    object.__setattr__(obj, name, self.dec(d["f"][name]))
                else:
                    from dataclasses import MISSING
                    if f.default is not MISSING:
                        object.__setattr__(obj, name, f.default)
                    elif f.default_factory is not MISSING:
                        object.__setattr__(obj, name, f.default_factory())
                    else:
                        object.__setattr__(obj, name, None)
            return obj
        raise ValueError("bad state node %r" % list(d)[:3])


# --- what the extension holds -------------------------------------------------------------------------------------------------------------------------

# World attributes copied as they are (generic codec); everything else is rebuilt by `World.from_map` (static) or derived
STATE = ("tick", "seed", "rng", "players", "units", "items", "corpses", "groups", "carriers", "_next_pile", "_next_carrier", "_next_group", "_next_seq",
         "ai_on", "ai_sleep", "ai_groups", "cell_effects", "cell_fx", "_fx_saved", "transients", "light_vertices", "light_version", "cells_version",
         "fog", "fog_viewer", "fog_cells", "fog_rev", "mission_complete", "mission_ended", "defeat_latch", "unbuilt_casts", "burn_start", "burn_fx",
         "block_rev", "use_clicked", "report", "_block", "_cost", "cells", "terrain")
STRUCT_FIELDS = ("x", "y", "sub_x", "sub_y", "variant", "owner", "hp", "hp_max", "flags", "known", "indestructible", "sight")
SCRIPT_STATE = ("values", "fired", "stage", "stage2", "complete", "fail", "passes", "gold", "scenario_vars", "phased", "errors", "unsupported", "unbuilt")


def _stats_lookup(world):
    types = world.assets.unit_stats() if world.assets is not None else None

    def of(u):
        return types.lookup(u.human, u.server_id) if types is not None else None
    return of


INFLATE_LIMIT = 1 << 29                 # 512 MB: a damaged / hostile blob never expands past this (zlib bomb guard)


def inflate(blob, limit=INFLATE_LIMIT):
    """`zlib.decompress` with a size cap: `ValueError` when the stream is damaged or would expand past `limit`."""
    try:
        d = zlib.decompressobj()
        out = d.decompress(bytes(blob), limit + 1)
    except zlib.error as e:
        raise ValueError("engine extension damaged (%s)" % e) from None
    if len(out) > limit or d.unconsumed_tail:
        raise ValueError("engine extension too large")
    return out


def capture(world):
    """The engine extension of a world as a JSON-able dict (see the module text)."""
    e = Encoder(_stats_lookup(world))
    out = {"v": BLOB_VERSION, "map": world.map_arg}
    for name in STATE:
        out[name] = e.enc(getattr(world, name))
    out["net_ids"] = sorted(world.net_ids.used)
    out["slots"] = e.enc({"stamp": list(world.slots.stamp), "occ": list(world.slots.occ)})
    out["structs"] = {str(o.id): {f: e.enc(getattr(o, f)) for f in STRUCT_FIELDS} for o in world.objects.values() if o.kind != "object"}
    out["cost_owned"] = world._cost is not None and world._cost_owner is world._cost
    sc = world.script
    if sc is not None:
        out["script"] = {k: e.enc(getattr(sc, k)) for k in SCRIPT_STATE}
        out["tgroups"] = [[[m.uid, og] for m, og in g.members] for g in _trigger_groups(sc)]
    return out


def _trigger_groups(script):
    """The compiled `TriggerGroup`s in a stable order (first reference in the compiled records)."""
    seen, out = set(), []
    for c in list(script.instants) + list(script.checks):
        for g in (c.group, c.second):
            if g is not None and hasattr(g, "members") and id(g) not in seen:
                seen.add(id(g))
                out.append(g)
    return out


def blob_bytes(world):
    raw = json.dumps(capture(world), sort_keys=True, separators=(",", ":")).encode()
    return zlib.compress(raw, 9)


def restore(world, blob, m, assets):
    """Overlay the extension on a fresh `World.from_map(m, assets, populate=False)`: all state first, then the compiled script (it resolves its units and
    groups against that state), then the script's saved counters."""
    d = json.loads(inflate(blob))
    if d.get("v") != BLOB_VERSION:
        raise ValueError("engine extension version %r" % d.get("v"))
    table = assets.unit_stats()
    by_index = {(t.kind, t.index): t for t in table.types}
    dec = Decoder(lambda kind, index: by_index[(kind, index)])
    for name in STATE:
        setattr(world, name, dec.dec(d[name]))
    world.net_ids.used = set(d["net_ids"])
    sl = dec.dec(d["slots"])
    world.slots.stamp, world.slots.occ = tuple(sl["stamp"]), tuple(sl["occ"])
    for key, vals in d["structs"].items():
        o = world.objects.get(int(key))
        if o is not None:
            for f, v in vals.items():
                setattr(o, f, dec.dec(v))
    world._cost_owner = world._cost if d.get("cost_owned") else None
    world._view = world._block.view()
    world._view.flags.writeable = False
    world._ucells, world._icells = {}, {}
    for u in world.units.values():
        world._index_add(world._ucells, u)
    for it in world.items.values():
        world._index_add(world._icells, it)
    world.assets = assets
    if world.cell_effects:
        from engine.sim import traps
        world.slots.on_enter = lambda u, idx: traps.on_enter(world, u, idx)
    return d, dec


def restore_script(world, m, d, dec, assets):
    """The map script: compiled against the restored units / groups (the exe recompiles at load, `FUN_00562745(map, 0)`, saves.md 6.2), then the saved
    state (values, fired flags, counters, phased units, variables) is put back."""
    from engine.sim import triggers
    if "script" not in d:
        return None
    extra = [u for u in world.corpses.values()] + list(dec.dec(d["script"]["phased"]).values())
    keep = dict(world.units)
    for u in sorted(extra, key=lambda x: x.seq):        # every creature is in its list at the exe's recompile, the dead and the phased-out included
        world.units.setdefault(u.id, u)
    world.units = dict(sorted(world.units.items(), key=lambda kv: kv[1].seq))
    scenario = m.scenario
    awake = {k: g.keep_awake for k, g in world.ai_groups.items()}
    world.script = triggers.compile_scenario(world, scenario)
    for k, v in awake.items():                          # the compile flags the squads the script names; a suspend instant (39) may have cleared them since
        world.ai_groups[k].keep_awake = v
    world.units = keep
    world.pointers = {p.uid: triggers.S.runtime_instant_index(scenario.instants, p.instant) for p in getattr(m, "section11", ((), (), ()))[2]
                      if p.enabled and p.instant < len(scenario.instants)}
    for k, v in d["script"].items():
        setattr(world.script, k, dec.dec(v))
    for g, saved in zip(_trigger_groups(world.script), d.get("tgroups", [])):
        by_uid = {u.uid: u for u in list(world.units.values()) + list(world.corpses.values()) + list(world.script.phased.values())}
        g.members = [(by_uid[uid], og) for uid, og in saved if uid in by_uid]
    return world.script


# --- the exe's view: World -> server stream -----------------------------------------------------------------------------------------------------------

MODE_OF = (("mode_attack", 5), ("mode_cast", 8), ("mode_cell", 9), ("mode_go", 1), ("mode_follow", 4), ("mode_loot", 12), ("mode_pick", 7), ("mode_use", 15), ("mode_look", 0xB))
SQUAD_TAG, GROUP_TAG = 0, 0x8000        # `group+0x1c`: a squad group holds its squad number, a command group 0x8000 + its id (DECISION: how the loader tells them apart)
BRAIN_MARK_CELL, BRAIN_MARK_AGE, BRAIN_ALERT = 0x58, 0x5A, 0x54
BRAIN_SPELL_MARK, BRAIN_SPELL_TICK, BRAIN_AREA_HITS = 0xA4, 0xA8, 0xAC
SUMMONED = 8                            # `Unit.behaviour` bit 8 (map.md part 5): the packed word's `+0x1a0 != 0` byte


class _Ptr:
    def __init__(self):
        self.n = PTR_BASE

    def __call__(self):
        self.n += PTR_STEP
        return self.n


def pack_cell(c):
    return ((c[1] & 0xFF) << 8) | (c[0] & 0xFF) if c is not None else 0


def unpack_cell(v):
    return (v & 0xFF, (v >> 8) & 0xFF)


def _s(v, lo=-0x8000, hi=0x7FFF):
    return max(lo, min(hi, int(v)))


class _Out:
    """The pointer keys of one save: one per unit / structure / carrier / player (any unique non-zero values, saves.md 6.12)."""

    def __init__(self, world):
        self.world = world
        self.ptr = _Ptr()
        self.unit = {}
        self.struct = {}
        self.player = {pid: self.ptr() for pid in sorted(world.players)}
        for u in list(world.units.values()) + list(world.corpses.values()) + list(getattr(world.script, "phased", {}).values() if world.script else ()):
            self.unit.setdefault(u.id, self.ptr())
        for o in world.objects.values():
            if o.kind != "object":
                self.struct[o.id] = self.ptr()

    def target(self, uid):
        return self.unit.get(uid, 0) if uid is not None else 0


def _item_obj(it, table, holder, out):
    if it is None or not it.code:
        return None
    from engine import savegame
    return savegame.item_object(it, table, holder, out.ptr)


def _effect_objs(effects, out, holder):
    objs = []
    for e in effects:
        base = SS.Base(bytes(12), 0, _s(e.id), 0, 0, 0, 0, out.ptr(), holder)
        objs.append(SS.Effect(base, e.kind & 0xFF, e.flags & 0xFF, (e.value & 0xFFFF) | ((e.ticks & 0xFFFF) << 16), _s(e.id)))
    return objs


def _mode(u):
    if u.mover.waiting:
        return 10
    for attr, m in MODE_OF:
        if getattr(u, attr):
            return m
    return 0


def unit_object(world, u, out, table, owner_ptr, off_map=False):
    """The stream `Unit` / `Humanoid` of an engine unit (field map: `serverblocks.UNIT_MAP`; saves.md 7 "L10e-B")."""
    from engine import party as PT
    from engine.sim import effects as FX
    m = u.mover
    mover = B.MOVER.encode(
        facing=u.facing, target_facing=m.target_facing if m.target_facing is not None else u.facing, b05=0x41, b08=5,
        step_target=pack_cell(m.step_target) if m.step_target else 0, consumed=m.consumed, turn_rate=m.turn_rate,
        step_from=pack_cell(m.step_from) if m.step_from else 0, dest=pack_cell(m.dest) if m.dest else 0, tail=pack_cell(m.tail) if m.tail else 0,
        since_hop=m.since_hop, follow_ptr=out.target(m.follow), stamp_cell=m.stamp_cell, follow_len=m.static_len,
        follow_cell=pack_cell(m.follow_cell) if m.follow_cell else 0, arrived=int(m.arrived), failed=int(m.failed), turn_done=m.turn_done,
        turning=int(m.turning), turn_ticks=m.turn_ticks, step_len=m.step_len, step_ticks=m.step_ticks, steps=m.steps, step_dir=m.step_dir, dx=m.dx, dy=m.dy)
    ai = u.ai
    wimpy = u.wimpy_hp if u.wimpy_hp is not None else 0
    withdraw = u.withdraw_hp if u.withdraw_hp is not None else 0
    brain = bytearray(B.BRAIN.encode(
        anchor=pack_cell(u.anchor) if u.anchor else 0, patrol_wp=pack_cell(u.patrol_wp) if u.patrol_wp else 0, patrol_walk=int(u.patrol_walk), mode=_mode(u),
        order=u.brain_order, dest=pack_cell(m.goal if m.goal else u.pick_cell or u.use_dest or u.cast_cell or (0, 0)),
        target_ptr=out.target(u.target), leader_ptr=out.target(u.leader), range=u.range, retry=u.swing_count, w16=_s(ai.stamp - 0x10000 if ai.stamp >= 0x8000 else ai.stamp),
        approach_ptr=out.target(u.follow_target), pool_ptr=out.target(ai.target), cast_target_ptr=out.target(u.cast_target),
        cast_cell=pack_cell(u.cast_cell) if u.cast_cell else 0, withdraw=withdraw, wimpy=wimpy, stopped=int(u.stopped), idle_gate=ai.alerted,
        spell_valid=int(u.ai_cast), struct_ptr=out.struct.get(u.use_obj, 0) if u.use_obj is not None else 0, follow_dist=u.follow_range,
        see_invis=1, auto_spell=u.auto_spell, last_caster=out.target(ai.hit_by), cast_tick=ai.hit_tick, cast_cell2=ai.hit_cell, teleport=u.teleport_to))
    struct.pack_into("<HH", brain, BRAIN_MARK_CELL, ai.mark_cell & 0xFFFF, ai.mark_age & 0xFFFF)
    struct.pack_into("<III", brain, BRAIN_SPELL_MARK, ai.spell_mark & 0xFFFFFFFF, ai.spell_tick & 0xFFFFFFFF, ai.area_hits & 0xFFFFFFFF)
    skills = tuple(u.skills) if u.skills else (0,) * 6
    a6 = struct.pack("<h6h", 0, *skills).ljust(0x18, b"\0")
    b114 = bytearray(0x18)
    for k in range(1, 6):
        struct.pack_into("<H", b114, 4 + 2 * (k - 1), skills[k])
    bd4 = B.BLK_D4.encode(hp_regen_bonus=u.fx.hp_regen & 0xFFFF, mana_regen_bonus=u.fx.mana_regen & 0xFFFF)
    be = B.BLK_BE.encode(defence=0)
    attrs = (0, 0, 0, 0)
    if u.human and u.stats is not None:
        from allods2.formats import progression as prog
        attrs = tuple(prog.attributes(u.stats))
    uptr = out.unit[u.id]
    items_in = list(u.equipment) + [None] * SS.SLOTS
    slots = [_item_obj(it, table, uptr, out) for it in items_in[:SS.SLOTS]] if u.human else [None] * SS.SLOTS
    pack_items = [_item_obj(it, table, uptr, out) for it in u.pack]
    if not u.human and u.carried:
        pack_items = [_item_obj(S.Item(c, 1, 0, tuple(u.carried_mods[i]) if u.carried_mods else ()), table, uptr, out) for i, c in enumerate(u.carried)]
    pack_items = [p for p in pack_items if p is not None]
    flags = (2 if u.spellbook is not None else 0) | (4 if u.mana_max > 0 else 0) | (8 if off_map else 0)
    spells = SS.Spellbook.from_mask(u.spellbook, 0) if u.spellbook else None
    book_ptr = {}
    if spells is not None:
        for sp in spells.spells:
            if sp is not None:
                sp.ptr = book_ptr[sp.number] = out.ptr()
    wrapper = u.cast_wrapper
    brain = bytearray(brain)
    if wrapper is not None:
        struct.pack_into("<I", brain, 0x30, book_ptr.get(wrapper.number, 0))
    wrapper_word = (0x80000000 | (wrapper.number & 0xFF) | (((wrapper.item_count + 1) & 0xFFFF) << 8 if wrapper.item_count is not None else 0)) if wrapper is not None else 0
    cast = u.cast
    effect_mask = u.effect_mask
    dead = u.state == W.DEAD
    number = PT.hero_number(u) if u.human else u.server_id
    tpl_index = u.stats.index if u.stats is not None and hasattr(u.stats, "index") else 0
    obj = SS.Unit(
        base=SS.Base(B.position_raw(u.x, u.y, u.sub_x, u.sub_y), u.net_id, tpl_index, _s(u.type_id), u.uid, 0, 0, uptr, owner_ptr),
        effects=_effect_objs(u.effects, out, uptr), list1c8=[pack_cell(c) for c in m.static_path], list1e4=[pack_cell(c) for c in u.path],
        blk_a6=a6, blk_be=be, blk_114=bytes(b114), blk_d4=bd4, mover=mover, brain=bytes(brain), brain_list=[pack_cell(c) for c in u.patrol],
        b49=1, b4a=u.move_type & 0xFF, b4b=u.face & 0xFF, b4c=flags,
        r50=struct.pack("<I", u.order), r54=struct.pack("<I", u.state), r58=struct.pack("<I", u.phase),
        b60=(cast.cell[0] if cast and cast.cell else 0), b61=(cast.cell[1] if cast and cast.cell else 0), b6c=u.timer & 0xFF,
        weapon=slots[0], second=slots[1], name=u.name,
        words=(attrs[0], attrs[1], attrs[2], attrs[3], (u.gear_speed or 0) & 0xFFFF, 0, 0, 0, _s(u.hp) & 0xFFFF, _s(u.hp_max) & 0xFFFF, 100,
               _s(u.mana) & 0xFFFF, _s(u.mana_max) & 0xFFFF, 50),
        b_a2=u.hp_acc & 0xFF, b_a3=u.mana_acc & 0xFF, w_a0=0, w_a4=0, b12c=1, d130=u.xp_total,
        b134=(u.combat.windup if u.combat is not None and hasattr(u.combat, "windup") else 8) & 0xFF,
        b135=(u.combat.recovery if u.combat is not None and hasattr(u.combat, "recovery") else 4) & 0xFF, b136=int(u.done),
        d138=u.step_end & 0xFFFFFFFF, b13c=int(u.death_seen),
        packed=(number & 0xFFFF) | ((1 << 24) if u.behaviour & SUMMONED else 0), d144=effect_mask & 0xFFFFFFFF,
        pack=SS.Pack(pack_items, u.pack_index, 0) if (u.human or pack_items) else None, spells=spells,
        d5c=out.target(u.swing_target), d64=0, d44=wrapper_word, d40=out.target(u.last_attacker), b48=0)
    if u.human:
        obj.hum = SS.Humanoid(struct.pack("<6I", u.best_school, *(tuple(u.xp) + (0,) * 5)[:5]), slots)
        obj.held = None
        obj.weapon, obj.second = slots[0], slots[1]
    return obj


def _group_ai(order, centre=0, spread=0, reach=0, radius=0, base=0, seen=0, passes=0, speed=0, awake=True, keep_awake=False, target=(0, 0), counter=0):
    raw = bytearray(0x50)
    struct.pack_into("<B", raw, 0x20, order & 0xFF)
    struct.pack_into("<H", raw, 0x28, centre & 0xFFFF)
    raw[0x2A], raw[0x2C], raw[0x2D], raw[0x38], raw[0x30], raw[0x34] = spread & 0xFF, reach & 0xFF, radius & 0xFF, base & 0xFF, seen & 0xFF, passes & 0xFF
    raw[0x44], raw[0x45], raw[0x48] = speed & 0xFF, int(awake), int(keep_awake)
    struct.pack_into("<H", raw, 0x0A, pack_cell(target))
    raw[0x15] = counter & 0xFF
    return bytes(raw)


def build_stream(world, campaign=None, rng_state=None):
    """The `ServerStream` (loaded flag 1) of a running mission."""
    table = world.item_table
    out = _Out(world)
    script = world.script
    phased = dict(script.phased) if script is not None else {}
    stream = SS.ServerStream(tick=world.tick, block=(world.tick + 1) >> 4, map_name=world.name, scenario=int(getattr(world, "mission_id", 0) or 0),
                             difficulty=campaign.difficulty if campaign is not None else 2, loaded=1)
    by_owner = {pid: [] for pid in world.players}
    objs = {}
    for u in list(world.units.values()) + list(world.corpses.values()) + list(phased.values()):
        objs[u.id] = unit_object(world, u, out, table, out.player.get(u.owner, 0), off_map=u.id in phased)
    placed = set()
    # command groups first (every player command makes one), then the squads, then whatever is left
    for g in world.groups.values():
        mem = [objs[i] for i in g.members if i in objs and i not in placed]
        placed.update(i for i in g.members if i in objs)
        if g.owner in by_owner:
            by_owner[g.owner].append(SS.Group(ai=_group_ai(g.order, g.centre, g.spread, g.reach, g.radius, g.base, g.seen, g.passes, g.speed, True, False, g.target, g.counter),
                                              units=mem, d1c=GROUP_TAG + g.id))
    for key, g in world.ai_groups.items():
        mem = [objs[i] for i in g.members if i in objs and i not in placed]
        placed.update(i for i in g.members if i in objs)
        by_owner.setdefault(g.owner, []).append(SS.Group(ai=_group_ai(g.order, g.centre, g.spread, g.reach, g.radius, g.base, g.seen, g.passes, g.speed, g.awake,
                                                                      g.keep_awake, g.target, g.counter), units=mem, d1c=SQUAD_TAG + key[1]))
    rest = {}
    for uid, o in objs.items():
        if uid not in placed:
            owner = next((x for x in (world.units.get(uid) or world.corpses.get(uid) or phased.get(uid),) if x is not None)).owner
            rest.setdefault((owner, (world.units.get(uid) or world.corpses.get(uid) or phased.get(uid)).squad), []).append(o)
    for (owner, squad), mem in rest.items():
        by_owner.setdefault(owner, []).append(SS.Group(ai=_group_ai(0xFF), units=mem, d1c=SQUAD_TAG + squad))
    for pid, p in sorted(world.players.items()):
        main = world.find_unit(p.main_hero) if p.main_hero else None
        stats_block = bytearray(0x24)
        stats_block[0x20] = p.autocast & 0xFF
        stream.players.append(SS.Player(
            name=p.name, w04=p.id, d08=p.colour, b10=struct.pack("<II", p.flags & 0xFFFFFFFF, p.money & 0xFFFFFFFF), b_a44=(campaign.difficulty if campaign else 2) & 0xFF,
            d2c=0 if p.human else 1, gold=p.gold, b40=p.death_code & 0xFF, kills_monsters=p.kills_monsters, hero_deaths=p.hero_deaths, kills_players=p.kills_players,
            main_hero=main.oid if main is not None else 0, ptr=out.player[pid],
            table=bytes(campaign.knowledge) if campaign is not None and campaign.knowledge and p.human else bytes(SS.TABLE_SIZE),
            groups=by_owner.get(pid, []), stats_block=bytes(stats_block)))
    stream.container = [u for p in stream.players for g in p.groups for u in g.units]
    mission = stream.mission = SS.Mission()
    for o in world.objects.values():
        if o.kind == "object":
            continue
        mission.buildings.append(SS.BuildingObj(SS.Base(B.position_raw(o.x, o.y, o.sub_x, o.sub_y), 0, _s(o.type_id), 0, o.uid, 0, 0, out.struct[o.id], out.player.get(o.owner, 0)),
                                                bytes(0x16), 1 if o.flags == 0 else 0, _s(o.hp) & 0xFFFF, _s(o.hp_max) & 0xFFFF, o.flags & 0xFFFF, o.owner & 0xFF, 0, 0, 0, 0))
    for c in world.carriers:
        x, y = c.centre if c.centre else (c.start[0] >> 8, c.start[1] >> 8)
        mission.effects.append(SS.SpellEffectObj(SS.Base(B.position_raw(x & 0xFF, y & 0xFF), 0, _s(c.level), 0, c.uid, 0, 0, out.ptr(), out.target(c.caster)),
                                                 (1 if c.kind == "point" else 0) | (2 if c.centre else 0), c.spell & 0xFF))
    for c in world.transients:
        mission.casters.append(SS.VirtualCasterObj(SS.Base(B.position_raw(c.x, c.y), 0, 0, 0, 0, 0, 0, out.ptr(), 0), c.state & 0xFF,
                                                   B.EFFECT6.encode(spell=c.cast.spell if c.cast else 0)))
    for it in world.items.values():
        pack_items = [_item_obj(S.Item(code, 1, 0, tuple(it.mods[i]) if it.mods else ()), table, 0, out) for i, code in enumerate(it.codes)]
        mission.sacks.append(SS.SackObj(SS.Base(B.position_raw(it.x, it.y, it.sub_x, it.sub_y), it.net_id, 0, 0, it.id, 0, 0, out.ptr(), 0), it.gold,
                                        SS.Pack([p for p in pack_items if p is not None], 0x7FFF, 0)))
    layer = mission.map
    for (x, y), v in world.cell_fx.items():
        rec = bytearray(60)
        saved = world._fx_saved.get((x, y), 0)
        rec[0], rec[1] = saved & 0xFF, 0
        rec[2] = sum(1 for k in v if k is not None)
        for k, uid in enumerate(v):
            if uid is not None:
                struct.pack_into("<I", rec, 0x14 + 4 * k, uid & 0xFFFFFFFF)
        struct.pack_into("<H", rec, 0x3A, pack_cell((x, y)))
        layer.records.append((pack_cell((x, y)), bytes(rec)))
    for (x, y), eff in world.cell_effects.items():
        k = pack_cell((x, y))
        rec = next((i for i, (kk, _) in enumerate(layer.records) if kk == k), None)
        raw = bytearray(layer.records[rec][1]) if rec is not None else bytearray(60)
        raw[0x34:0x3A] = bytes(eff[:6])
        struct.pack_into("<H", raw, 0x3A, k)
        if rec is None:
            layer.records.append((k, bytes(raw)))
        else:
            layer.records[rec] = (k, bytes(raw))
    ys, xs = np.nonzero(np.asarray(world._block) & 0x10)         # dirt = block bit 0x10 (plane 2 byte > 0xf, saves.md 6.9)
    for y, x in zip(ys.tolist(), xs.tolist()):
        layer.cells.append(SS.MapLayer.cell((y << 8) | x, int(world._block[y, x]), 0))
    layer.ptr = out.ptr()
    sc = mission.script
    if script is not None:
        sc.values = struct.pack("<1000i", *[(v if -0x80000000 <= v < 0x80000000 else 0) for v in script.values])
        sc.fired = bytes(script.fired)
        sc.complete, sc.fail = script.complete & 0xFFFFFFFF, script.fail & 0xFFFFFFFF
    rel = bytearray(0x132C)
    for pid, p in world.players.items():
        for j, word in enumerate(p.relations):
            if pid < B.RELATIONS_PLAYERS and j + 1 < B.RELATIONS_PLAYERS:
                rel[pid * B.RELATIONS_PLAYERS + 8 + j + 1] = word & 0xFF
    sc.relations = bytes(rel)
    debug = bytearray(SS.DEBUG_SIZE)
    state = world.rng.state if rng_state is None else rng_state
    struct.pack_into("<II", debug, SS.DEBUG_SIZE - 8, RNG_MAGIC, state)
    stream.debug = bytes(debug)
    return stream


# --- the client state ---------------------------------------------------------------------------------------------------------------------------

def fog_runs(world):
    """`Fog/FirstState` + `Fog/Data`: run lengths of tile bit 15 (explored) over the map cells, row by row (saves.md 6.3, INFERRED encoding)."""
    if world.fog is None:
        return 0, []
    bits = ((world.fog.reshape(-1) >> 15) & 1).astype(np.int8)
    if not len(bits):
        return 0, []
    cuts = np.flatnonzero(np.diff(bits)) + 1
    edges = np.concatenate(([0], cuts, [len(bits)]))
    return int(bits[0]), [int(n) for n in np.diff(edges)]


def apply_fog_runs(fog, first, runs):
    """The inverse: set bit 15 of the tile words from the runs (other bits untouched)."""
    flat = fog.reshape(-1)
    pos, state = 0, first & 1
    for n in runs:
        if state:
            flat[pos:pos + n] |= 0x8000
        pos += n
        state ^= 1


def client_state_of(world, state=None):
    """The `ClientState` of a mission save: `state` (the UI's view / selection / groups) completed with the battle keys (in battle, fog runs)."""
    st = state if state is not None else S.ClientState()
    st = S.ClientState(**{f.name: getattr(st, f.name) for f in fields(st)})
    st.in_battle = 1
    human = next((p for _, p in sorted(world.players.items()) if p.human), None)
    if human is not None:
        st.selection = list(human.selection)
        st.options = dict(st.options)
        st.options["Formation"] = human.formation
        if not st.name or st.name == S.DEFAULT_NAME:
            hero = world.find_unit(human.main_hero) if human.main_hero else None
            st.name = hero.name if hero is not None and hero.name else S.DEFAULT_NAME
    st.fog_first_state, st.fog_data = fog_runs(world)
    return st


# --- the two directions -------------------------------------------------------------------------------------------------------------------------

@dataclass
class LoadedMission:
    """What `world_from_save` returns: the live `world` (script, AI, fog and all, ready for `Simulation(world, triggers=True, vision=True)`), its `assets`, the
    `campaign` (a `CampaignGame` rebuilt from the Scenario.dll block and the party; None for a save made without one), the `client_state` (view, selection, groups,
    options) and `mission` (the map's number / argument); `exact` is True when the engine extension was present (a save of ours), False for a save the original wrote."""
    world: object
    assets: object
    campaign: object
    client_state: object
    mission: str
    exact: bool = True


def world_to_save(world, campaign=None, client_state=None, description="", hotkeys=None):
    """A running mission as a `saves.SaveGame` (`.pack()` = the bytes of a `game%d.sav`)."""
    stream = build_stream(world, campaign)
    from engine import savemerge
    stream = savemerge.merge_stream(stream, getattr(world, "save_origin", None))      # a file the original wrote: what we do not model stays as it was
    st = client_state_of(world, client_state)
    if not st.extra:
        st.extra = dict(getattr(world, "client_extra", None) or {})          # the original's other `.reg` keys survive a load -> save
    st.engine = blob_bytes(world)
    mission = str(world.map_arg) if world.map_arg is not None else ""
    if mission.isdigit():
        stream.scenario = int(mission)
    if campaign is not None:
        from engine import savegame
        scenario = savegame.scenario_state(campaign.camp, savegame._positions(campaign))
        times = sum(campaign.camp.times)
        hot = list(hotkeys or campaign.hotkeys or [])
    else:
        scenario, times, hot = S.ScenarioState(), 0, list(hotkeys or [])
    tail = S.ClientTail.new(description, st, (), (times & 0xFFFFFFFF, 0), scenario, hot or None)
    return S.SaveGame(stream.pack(), tail)


@S.damaged
def world_from_save(save, assets=None, install=None, campaign=None, seed=None):
    """`saves.SaveGame` (or file bytes) -> `LoadedMission`.  A save with the engine extension resumes bit for bit; one without it (the original's) is
    rebuilt from the stream (`world_from_stream`)."""
    from allods2.assets import AssetCache
    from allods2.cli import open_map
    if isinstance(save, (bytes, bytearray, memoryview)):
        save = S.parse_save(save)
    stream = SS.ServerStream.parse(save.stream)
    if not stream.loaded or stream.mission is None:
        raise ValueError("not a mission save (loaded flag %d)" % stream.loaded)
    st = save.tail.state
    assets = assets or (campaign.assets if campaign is not None else AssetCache(install))
    d = json.loads(inflate(st.engine)) if st.engine else None
    mission = d["map"] if d is not None and d.get("map") else str(stream.scenario)
    m = open_map(mission, install)
    world = W.World.from_map(m, assets, seed=1, difficulty=stream.difficulty, populate=False)
    world.map_arg, world.difficulty = mission, stream.difficulty
    if d is not None:
        d, dec = restore(world, st.engine, m, assets)
        restore_script(world, m, d, dec, assets)
        exact = True
    else:
        world_from_stream(world, stream, st, m, assets, seed)
        exact = False
    game = campaign_of(save, stream, world, assets, install, mission, campaign)
    if world.script is not None and game is not None:
        if exact:
            game.camp.vars = world.script.scenario_vars     # the saved array as it was (explicit zeros included): one array, as `CampaignGame.start_mission` binds it
        else:
            world.script.scenario_vars = game.camp.vars
    world.client_extra = st.extra
    world.save_origin = (build_stream(world, game), stream)      # (what the engine builds from the fresh load, the file's own stream): `savemerge`
    return LoadedMission(world, assets, game, st, mission, exact)


# --- the exe's view: server stream -> World (the loader of a save without the engine extension) --------------------------------------------------------

def _signed16(v):
    return v - 0x10000 if v & 0x8000 else v


def _cell_or_none(v):
    return unpack_cell(v) if v else None


def unit_from_object(world, su, assets, owner, by_index, uid_of_ptr):
    """An engine `Unit` from a stream unit (the inverse of `unit_object`): identity from the template index and the scenario number, position / facing /
    vitals / orders / mover / brain from the raw blocks, items and the book from the item objects, effects with their ticks.  Engine fields the exe does not
    store take the values its constructors give (`Unit` defaults), derived state (`stats`, `combat`, the cell slots, the effect mask) is rebuilt."""
    from engine import savegame
    from engine import party as PT
    from allods2.formats import progression as prog
    from engine.sim import effects as FX, gear
    from engine.sim.spells import Wrapper
    human = su.hum is not None
    tpl = by_index.get(("human" if human else "monster", su.base.w0c))
    if tpl is None:
        return None
    pos = su.base.pos
    uid = su.base.d08
    u = W.Unit(W.UNIT_ID_BASE + uid, su.base.w0e, owner, pos["cell_x"], pos["cell_y"], pos["sub_x"], pos["sub_y"], B.MOVER.get(su.mover, "facing"), W.IDLE, 0,
               _signed16(su.words[8]), _signed16(su.words[9]), uid, tpl.server_id, human, 8 if su.packed >> 24 & 1 else 0,
               su.b4a - 256 if su.b4a > 127 else su.b4a, (su.b4b & 0x7F) if human else su.b4b, 0, 0,
               assets.unit_set(su.base.w0e) is not None, stats=tpl)
    u.net_id = su.base.id
    if human and tuple(su.words[0:4]) != tuple(prog.attributes(tpl)):          # a hero with trained / bonus attributes: the template with his own
        from dataclasses import replace
        f = dict(tpl.fields)
        f.update(zip(PT.ATTRS, su.words[0:4]))
        u.stats = replace(tpl, fields=f)
    mv = u.mover
    G = lambda n: B.MOVER.get(su.mover, n)         # noqa: E731
    mv.target_facing, mv.turn_rate = G("target_facing"), G("turn_rate")
    mv.step_target, mv.step_from = _cell_or_none(G("step_target")), _cell_or_none(G("step_from"))
    mv.dest, mv.tail = _cell_or_none(G("dest")), _cell_or_none(G("tail"))
    mv.consumed, mv.since_hop, mv.stamp_cell, mv.static_len = G("consumed"), G("since_hop"), G("stamp_cell"), G("follow_len")
    mv.follow_cell = _cell_or_none(G("follow_cell"))
    mv.arrived, mv.failed, mv.turn_done, mv.turning = bool(G("arrived")), bool(G("failed")), G("turn_done"), bool(G("turning"))
    mv.turn_ticks, mv.step_len, mv.step_ticks, mv.steps, mv.step_dir, mv.dx, mv.dy = (G("turn_ticks"), G("step_len"), G("step_ticks"), G("steps"),
                                                                                     G("step_dir"), G("dx"), G("dy"))
    mv.follow = uid_of_ptr(G("follow_ptr"))
    mv.static_path = [unpack_cell(c) for c in su.list1c8]
    u.path = [unpack_cell(c) for c in su.list1e4]
    g = lambda n: B.BRAIN.get(su.brain, n)         # noqa: E731
    mode = g("mode")
    u.set_mode(go=mode == 1, attack=mode == 5, look=mode == 0xB, cast=mode == 8, cell=mode == 9, follow=mode == 4)
    u.mode_loot, u.mode_pick, u.mode_use, mv.waiting = mode == 12, mode == 7, mode == 15, mode == 10
    mv.goal = _cell_or_none(g("dest")) if mode in (1, 10) else None
    u.pick_cell = _cell_or_none(g("dest")) if mode in (7, 12) else None
    u.use_dest = _cell_or_none(g("dest")) if mode == 15 else None
    u.anchor, u.patrol_wp, u.patrol_walk = _cell_or_none(g("anchor")), _cell_or_none(g("patrol_wp")), bool(g("patrol_walk"))
    u.patrol = [unpack_cell(c) for c in su.brain_list]
    u.brain_order, u.range, u.swing_count = g("order"), g("range"), g("retry")
    u.target, u.leader, u.follow_target, u.cast_target = (uid_of_ptr(g("target_ptr")), uid_of_ptr(g("leader_ptr")), uid_of_ptr(g("approach_ptr")),
                                                          uid_of_ptr(g("cast_target_ptr")))
    u.cast_cell = _cell_or_none(g("cast_cell"))
    wimpy, withdraw = g("wimpy"), g("withdraw")
    u.wimpy_hp, u.withdraw_hp = (wimpy, withdraw) if wimpy or withdraw else (None, None)
    u.stopped, u.auto_spell, u.ai_cast, u.teleport_to = bool(g("stopped")), g("auto_spell"), bool(g("spell_valid")), g("teleport")
    u.follow_range = g("follow_dist")
    u.ai.stamp = g("w16") & 0xFFFF
    u.ai.target, u.ai.hit_by = uid_of_ptr(g("pool_ptr")), uid_of_ptr(g("last_caster"))
    u.ai.hit_tick, u.ai.hit_cell, u.ai.alerted = g("cast_tick"), g("cast_cell2"), g("idle_gate")
    u.ai.mark_cell, u.ai.mark_age = struct.unpack_from("<HH", su.brain, BRAIN_MARK_CELL)
    u.ai.spell_mark, u.ai.spell_tick, u.ai.area_hits = struct.unpack_from("<III", su.brain, BRAIN_SPELL_MARK)
    u.mode_look = mode == 0xB
    u.order, u.state, u.phase = (struct.unpack("<I", b)[0] for b in (su.r50, su.r54, su.r58))
    u.timer, u.done, u.death_seen, u.step_end = su.b6c, bool(su.b136), bool(su.b13c), su.d138
    u.hp_acc, u.mana_acc, u.xp_total, u.name = su.b_a2, su.b_a3, su.d130, su.name
    u.swing_target, u.last_attacker = uid_of_ptr(su.d5c), uid_of_ptr(su.d40)
    u.mana, u.mana_max = _signed16(su.words[11]), _signed16(su.words[12])
    if su.d44 & 0x80000000:                                  # the cast wrapper: DECISION, the number (and an item cast's count) in the unknown dword `+0x44`
        count = (su.d44 >> 8) & 0xFFFF
        u.cast_wrapper = Wrapper(su.d44 & 0xFF, count - 1 if count else None)
        if u.state in (0xD, 0xE):
            u.cast = W.SpellCast(su.d44 & 0xFF, target=u.swing_target if u.state == 0xD else None,
                                 cell=(su.b60, su.b61) if u.state == 0xE else None, item_count=u.cast_wrapper.item_count)
    if su.words[4]:
        u.gear_speed = su.words[4]
    if su.spells is not None and su.spells.mask:
        u.spellbook = su.spells.mask
    if human:
        sk = struct.unpack_from("<6h", su.blk_a6, 2)
        u.skills = tuple(sk)
        pools = struct.unpack("<6I", su.hum.block)
        u.best_school, u.xp = pools[0], tuple(pools[1:])
        u.equipment = tuple(savegame.stored_item(i) for i in su.hum.slots) if any(su.hum.slots) else ()
        u.pack = tuple(savegame.stored_item(i) for i in (su.pack.items if su.pack else ()))
        u.pack_index = su.pack.d1c if su.pack else 0x7FFF
        gear.sync_carried(u)
    elif su.pack is not None and su.pack.items:
        items = [savegame.stored_item(i) for i in su.pack.items]
        u.carried = tuple(i.code & 0xFFFF for i in items)
        if any(i.mods for i in items):
            u.carried_mods = tuple(tuple(i.mods) for i in items)
    u.effects = [W.Effect(_signed16(e.tag) & 0xFFFF, e.kind, e.flags, _signed16(e.value & 0xFFFF), e.value >> 16) for e in su.effects]
    u.hp_max = _signed16(su.words[9])
    return u


def world_from_stream(world, stream, st, m, assets, seed=None):
    """Fill a `World.from_map(populate=False)` from the stream alone.  Rebuilt the way the exe's loader does (saves.md 6.2): units registered in the cell slots
    (`FUN_0052b22a` -> `FUN_0055020a`), the script recompiled against them, the fog's seen bits recomputed; the RNG is reseeded from the counters (the stream
    stores no RNG word of the original, 6.11)."""
    from engine import savegame
    from engine.sim import ai as AI, effects as FX, gear, triggers, vision
    by_index = {(t.kind, t.index): t for t in assets.unit_stats().types}
    world.tick = stream.tick
    mag, state = struct.unpack_from("<II", stream.debug, SS.DEBUG_SIZE - 8)
    world.seed = state if mag == RNG_MAGIC else (stream.tick * 2654435761 + stream.block) & 0xFFFFFFFF
    world.rng = Rng(world.seed)
    player_id = {}
    for sp in stream.players:
        p = world.players.get(sp.w04)
        if p is None:
            continue
        player_id[sp.ptr] = p.id
        p.name, p.gold, p.kills_monsters, p.kills_players, p.hero_deaths = sp.name or p.name, sp.gold, sp.kills_monsters, sp.kills_players, sp.hero_deaths
        p.death_code, p.autocast = sp.b40, sp.stats_block[0x20]
        p.formation = st.options.get("Formation", 1) or 1 if sp.human else p.formation
    rel = stream.mission.script.relations
    for p in world.players.values():
        p.relations = tuple(rel[p.id * B.RELATIONS_PLAYERS + 8 + j + 1] for j in range(len(p.relations)))
    ptr_unit = {}
    units = []
    for sp in stream.players:
        owner = player_id.get(sp.ptr)
        for g in sp.groups:
            for su in g.units:
                u = unit_from_object(world, su, assets, owner, by_index, lambda k: ptr_unit.get(k))
                if u is not None:
                    ptr_unit[su.base.ptr] = u.id
                    units.append((su, u, g))
    order_groups = {}
    for sp in stream.players:
        for g in sp.groups:
            tag = g.d1c
            members = [u for su, u, gg in units if gg is g]
            if tag >= GROUP_TAG:
                gid = tag - GROUP_TAG
                og = W.OrderGroup(gid, player_id.get(sp.ptr), [u.id for u in members if u.state != W.DEAD], g.ai[0x20], unpack_cell(struct.unpack_from("<H", g.ai, 0x0A)[0]),
                                  g.ai[0x44], struct.unpack_from("<H", g.ai, 0x28)[0], g.ai[0x2A], g.ai[0x2C], g.ai[0x2D], g.ai[0x38], g.ai[0x30], g.ai[0x34], g.ai[0x15])
                world.groups[gid] = og
                for u in members:
                    u.order_group = gid
                world._next_group = max(world._next_group, gid + 1)
            else:
                for u in members:
                    u.squad = tag
    for su, u, g in units:                                  # pointers are resolved now that every unit exists (FUN_005a11e9, saves.md 6.12)
        for attr, off in (("target", "target_ptr"), ("leader", "leader_ptr"), ("follow_target", "approach_ptr"), ("cast_target", "cast_target_ptr")):
            setattr(u, attr, ptr_unit.get(B.BRAIN.get(su.brain, off)))
        u.ai.target, u.ai.hit_by = ptr_unit.get(B.BRAIN.get(su.brain, "pool_ptr")), ptr_unit.get(B.BRAIN.get(su.brain, "last_caster"))
        u.swing_target, u.last_attacker = ptr_unit.get(su.d5c), ptr_unit.get(su.d40)
        if u.cast is not None and u.state == 0xD:
            u.cast.target = u.swing_target
        u.mover.follow = ptr_unit.get(B.MOVER.get(su.mover, "follow_ptr"))
    phased = {}
    for su, u, g in units:
        dead = u.state == W.DEAD
        if su.b4c & 8:
            phased[u.id] = u
            continue
        if dead and u.move_type <= 1:
            world.corpses[u.id] = u
            continue
        u.seq, world._next_seq = world._next_seq, world._next_seq + 1
        world.units[u.id] = u
        world._index_add(world._ucells, u)
        world.slots.place(u)
        if u.mover.step_target is not None and u.mover.stamp_cell:
            world.slots.be86(u, u.mover.stamp_cell, 0)
        for e in u.effects:
            FX._mirror_add(u, e)
            u.effect_mask |= FX.bit(e.id)
    for su, u, g in units:
        for e in u.effects:
            if FX.timed(e) and e.id != FX.POISON and u.id in world.units:
                FX._switch(world, u, e, 1) if e.kind else None
    for k, o in enumerate(stream.mission.sacks):
        pos = o.base.pos
        codes, mods = [], []
        for it in o.pack.items:
            si = savegame.stored_item(it)
            codes.append(si.code & 0xFFFF)
            mods.append(tuple(si.mods))
        pile = W.Item(o.base.d08 or W.PILE_ID_BASE + k, pos["cell_x"], pos["cell_y"], pos["sub_x"], pos["sub_y"], o.d3c, tuple(codes), mods=tuple(mods) if any(mods) else ())
        pile.net_id = o.base.id
        world.add_item(pile)
        world._next_pile = max(world._next_pile, pile.id)
    for b in stream.mission.buildings:
        ob = world.objects.get(W.STRUCTURE_ID_BASE + b.base.d08)
        if ob is not None:
            ob.hp, ob.hp_max, ob.flags = _signed16(b.w42), _signed16(b.w44), b.w46
    for key, raw in stream.mission.map.records:
        x, y = unpack_cell(key)
        slots = [struct.unpack_from("<I", raw, 0x14 + 4 * k)[0] or None for k in range(6)]
        if any(s is not None for s in slots):
            world.cell_fx[(x, y)] = slots
            world._fx_saved[(x, y)] = raw[0]
        if raw[0x34]:
            world.cell_effects[(x, y)] = tuple(raw[0x34:0x3A])
    for v in stream.mission.map.cells:
        idx, p2, p1 = SS.MapLayer.split(v)
        world._block[(idx >> 8) & 0xFF, idx & 0xFF] = p2
    world.net_ids.used |= {u.net_id for _, u, _ in units if 0 < u.net_id < 0x6000} | {i.net_id for i in world.items.values() if 0 < i.net_id < 0x6000}
    for p in world.players.values():
        if p.human:
            p.selection = tuple(i for i in st.selection if i in world.units)
    main = next((sp.main_hero for sp in stream.players if sp.human), 0)
    for _, u, _ in units:
        pl = world.players.get(u.owner)
        if pl is not None and pl.human and main and u.oid == main and u.human:
            pl.main_hero = u.id
    # the AI squads, the stand squads and the script are rebuilt by their enablers on top of this state
    world.ai_on = True
    world.ai_groups.clear()
    for sp in stream.players:
        for g in sp.groups:
            if g.d1c >= GROUP_TAG:
                continue
            pl = world.players.get(player_id.get(sp.ptr))
            if pl is None or pl.human:
                continue
            members = [ptr_unit[su.base.ptr] for su in g.units if su.base.ptr in ptr_unit and ptr_unit[su.base.ptr] in world.units]
            key = (pl.id, g.d1c)
            ag = world.ai_groups.setdefault(key, W.AiGroup(key))
            ag.members += members
            ag.order, ag.centre, ag.spread, ag.reach, ag.radius = g.ai[0x20], struct.unpack_from("<H", g.ai, 0x28)[0], g.ai[0x2A], g.ai[0x2C], g.ai[0x2D]
            ag.base, ag.seen, ag.passes, ag.speed, ag.awake, ag.keep_awake = g.ai[0x38], g.ai[0x30], g.ai[0x34], g.ai[0x44], bool(g.ai[0x45]), bool(g.ai[0x48])
            ag.target, ag.counter = unpack_cell(struct.unpack_from("<H", g.ai, 0x0A)[0]), g.ai[0x15]
    extra = list(world.corpses.values()) + list(phased.values())
    keep = dict(world.units)
    for u in extra:
        world.units.setdefault(u.id, u)
    world.units = dict(sorted(world.units.items(), key=lambda kv: kv[1].seq or 0))
    awake = {k: g.keep_awake for k, g in world.ai_groups.items()}
    world.script = triggers.compile_scenario(world, m.scenario)
    for k, v in awake.items():
        world.ai_groups[k].keep_awake = v
    world.units = keep
    world.script.phased = phased
    world.script.values = list(struct.unpack("<1000i", stream.mission.script.values))
    world.script.fired = bytearray(stream.mission.script.fired)
    world.script.complete, world.script.fail = stream.mission.script.complete, stream.mission.script.fail
    world.pointers = {p.uid: triggers.S.runtime_instant_index(m.scenario.instants, p.instant) for p in getattr(m, "section11", ((), (), ()))[2]
                      if p.enabled and p.instant < len(m.scenario.instants)}
    vision.enable(world)
    apply_fog_runs(world.fog, st.fog_first_state, st.fog_data)
    vision.vision_system(world, [])
    gear.template_speeds(world)


def campaign_of(save, stream, world, assets, install, mission, given=None):
    """The `CampaignGame` a mission save belongs to: Scenario.dll's block (variables, shop table, available list, current location), the human's gold and
    statistics, the party as the roster (the heroes' current state: `carry_over` reads the world anyway), the mission number.  None when the save was made
    without a campaign (an empty Scenario block)."""
    from engine import campaign as CG, party as PT, savegame
    sc = save.tail.scenario
    if given is None and not sc.locations and not any(sc.variables):
        return None
    game = given or CG.CampaignGame(install, seed=1, difficulty=stream.difficulty or 2, assets=assets)
    savegame.apply_scenario(game.camp, sc)
    if sc.locations and 0 <= sc.current < len(game.camp.available):
        game.camp.location = game.camp.available[sc.current]
    total = save.tail.mission_tail[0]
    game.camp.times = [total] if total else []
    human = next((p for _, p in sorted(world.players.items()) if p.human), None)
    if human is not None:
        game.gold, game.hero_deaths = human.gold, human.hero_deaths
        game.kills_monsters, game.kills_players = human.kills_monsters, human.kills_players
        game.roster = [CG.CampaignGame._entry(u, u.oid) for u in world.units.values() if CG.is_hero(u, human)]
        game.net_ids.used = {0} | {e.net_id for e in game.roster if 0 < e.net_id < 0x6000}
    game.mission = int(mission) if str(mission).isdigit() else None
    game.mercenaries = {}
    game.client_state, game.hotkeys, game.description = save.tail.state, list(save.tail.hotkeys), save.tail.description
    return game
