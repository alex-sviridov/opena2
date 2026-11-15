"""Town saves: `CampaignGame` <-> `game%d.sav` (docs/engine/save.md L10c; layouts: docs/formats/saves.md 6).  Pure: no pygame, no window.

A town save is a saved game with the loaded flag 0 (between missions): the server stream holds the player manager (the human player with
gold and statistics, one group with the party's hero units, their items, spell books, XP pools) and no map; the client tail holds the Scenario.dll
block (variables, shop table, available locations), the mission list object (play-time sum), the hotkeys and the client's `.reg` tree.

`to_save(game, description)` builds the stream from the campaign's roster (`engine.party.RosterEntry`), `from_save(save)` rebuilds a `CampaignGame`.
Fields the engine does not model come from the constructor defaults of saves.md 6.11 (the 11 option words 0, the debug block zeros) or, where the
layout names a value the engine derives (HP = max, orders idle, attribute / skill bonuses, regeneration 100 / 50), from that rule (each INFERRED
choice is listed in saves.md 7 "L10c as built").  A hero that was never in a world (`RosterEntry.state` None) or that still has the template's
equipment strings is *materialised* first (`hero_state`): the saved file always holds explicit item objects, as the exe's objects exist from the
constructor on.

Decisions (docs/formats/saves.md 7): the loaded game rests on the world map (`camp.location` None: the DLL saves the current location as its position in
the list, 0 when there is none, so a loaded game cannot tell a town from the map); the mission times are kept as their sum (the exe's object keeps only
the running total at `+4`, `FUN_00493b40`).
"""

import struct
from dataclasses import replace
from types import SimpleNamespace

from allods2.formats import progression as prog
from allods2.formats import saves as S
from allods2.formats import serverstream as SS
from allods2.formats.itemdefs import effects_from_mods, mods_from_effects  # noqa: F401  (documented pair of the mods <-> effects mapping)
from engine import campaign as CG
from engine import party as PT
from engine.sim import campaign as C
from engine.sim import gear

MERC_TYPES = range(0x21, 0x40)         # unit type `+0xe` of the heroes the carry-over keeps (FUN_004ebd5f step 6)
PTR_BASE, PTR_STEP = 0x00A00000, 0x40  # the raw pointer keys (any unique non-zero values, saves.md 6.4)
MOVER_FACE = 0x40                       # facing bytes of a unit standing in town (the map load draws 0x40 + rand(128); INFERRED irrelevant)
BRAIN_WIMPY, BRAIN_WITHDRAW, BRAIN_AUTO = 0x44, 0x40, 0x78      # brain offsets of the retreat thresholds and the auto spell (unit-struct 8)

K_CAST, K_MINMAX = S.K_CAST_SPELL, S.K_MINMAX


# --- items ---------------------------------------------------------------------------------------------------------------------------------

def mod_value(kind, a, b):
    """The u32 `+0x40` of an Effect for a `.a2c` modifier record `(kind, a, b)`: castSpell `a | charges << 16`, min / spread kinds `a | b << 8`."""
    if kind == K_CAST:
        return (a & 0xFF) | (b & 0xFF) << 16
    if kind in K_MINMAX:
        return (a & 0xFF) | (b & 0xFF) << 8
    return a & 0xFF


def value_mod(kind, value):
    if kind == K_CAST:
        return (kind, value & 0xFF, value >> 16 & 0xFF)
    if kind in K_MINMAX:
        return (kind, value & 0xFF, value >> 8 & 0xFF)
    return (kind, value & 0xFF, 0)


class _Ptr:
    """Unique non-zero raw pointer keys."""

    def __init__(self):
        self.n = PTR_BASE

    def __call__(self):
        self.n += PTR_STEP
        return self.n


def item_object(it, table, holder, ptr):
    """The stream Item of a `saves.Item` (None for an empty slot).  `+0xc` = the class record's index (`code` low bits; INFERRED, the loader only range-checks
    it), `+0x1c` = the price, the object's flag `+8` = the item's `new` mark, `+0x44` = the group byte (engine/shop.group_of), `+0x48` / `+0x4a` = capacity /
    weight from the class stats."""
    if it is None or not it.code:
        return None
    group, cap, weight = 0, 0, 0
    if table is not None:
        from engine import shop
        group = shop.group_of(table, it)
        r = gear.resolve(table, it)
        if r is not None:
            cap, weight = r.stats.magic_cap, r.stats.weight
    effects = [SS.Effect(SS.Base(SS.raw12(SS.VT_EFFECT), 0, 0, 0, 0, 0, 0, ptr(), 0), kind, 0, mod_value(kind, a, b), 0)
               for kind, a, b in it.mods if kind != S.K_SKIPPED]
    base = SS.Base(SS.raw12(SS.VT_ITEM, 0, 1 if it.new else 0), 0, it.code & 0x1F if it.cls != 14 else it.code & 0xFF, 0, 1 if it.new else 0, 0,
                   it.price, ptr(), holder)
    return SS.Item(base, effects, it.code & 0xFFFF, it.count, group, 0, 0, cap & 0xFFFF, weight & 0xFFFF, 0)


def stored_item(obj):
    """The `saves.Item` of a stream Item (`gear.EMPTY` for a null pointer)."""
    if obj is None:
        return gear.EMPTY
    mods = tuple(value_mod(e.kind, e.value) for e in obj.effects)
    return S.Item(obj.code, obj.count, obj.base.d1c, mods, bool(obj.base.d08))


# --- heroes ---------------------------------------------------------------------------------------------------------------------------------

def scratch_world(game):
    """A one-player world on an open field, only to build a hero the way the map placement does (`party.place_party`)."""
    import numpy as np
    from engine.world import Player, World
    w = World(np.zeros((48, 48), np.uint16), np.zeros((48, 48), np.int8), "save", seed=1)
    w._cost = np.full((48, 48), 8, np.uint8)
    w.players[1] = Player(1, 0, human=True, relations=(18,) + (1,) * 15)
    try:
        w.item_table = game.assets.items()
    except Exception:           # no install / no item table: the heroes keep what they have
        w.item_table = None
    return w


def hero_state(game, entry):
    """The carried state of a roster entry as the file stores it: the entry's own `state` when it has an explicit loadout, else the hero built from its spec /
    template strings in a scratch world (equipment materialised, HP and mana at the maxima)."""
    s = entry.state
    if s is not None and (s.equipment or not entry.human):
        return s
    world = scratch_world(game)
    placed = PT.place_party(world, game.assets, [(24, 24)], roster=PT.Roster([entry], game.gold), owner=world.players[1])
    if not placed:
        raise ValueError("hero %#x could not be built for the save" % entry.number)
    u = placed[0]
    if world.item_table is not None:
        gear.ensure_loadout(world, u)
        gear.recompute(world, u)
        u.hp, u.mana = u.hp_max, u.mana_max
    return PT.capture(u)


def _attrs(state):
    """(base, bonus) attribute tuples: the template's (capped) attributes and the equipment bonus on top."""
    base = prog.attributes(state.stats) if state.stats is not None else (0, 0, 0, 0)
    bonus = tuple(state.attr_bonus) if state.attr_bonus else (0, 0, 0, 0)
    return tuple(base), bonus


def hero_unit(game, entry, state, table, owner_ptr, ptr):
    """One stream Unit (class `Humanoid` for a human) of a hero."""
    tpl = state.stats
    human = bool(entry.human)
    base_attrs, bonus = _attrs(state)
    skills = tuple(state.skills) if state.skills else (0,) * 6
    sk_bonus = tuple(state.skill_bonus) if state.skill_bonus else (0,) * 6
    eff = [min(100, a + b) for a, b in zip(base_attrs, bonus)]
    speed = state.gear_speed if state.gear_speed is not None else (prog.derived_speed(tpl, state.type_id) if tpl is not None else 0)
    mage = state.mana_max > 0
    unit_ptr = ptr()
    gender = 0x80 if tpl is not None and tpl.get("gender", 0) == 1 else 0
    # items: one object per Item (the weapon / second-hand slots are the same objects as `+0x74` / `+0x78`)
    slots = [item_object(it, table, unit_ptr, ptr) for it in (list(state.equipment) + [None] * SS.SLOTS)[:SS.SLOTS]]
    pack_items = [item_object(it, table, unit_ptr, ptr) for it in state.pack]
    spells = SS.Spellbook.from_mask(state.spellbook or 0, 0) if state.spellbook is not None or mage else None
    # raw blocks
    a6 = struct.pack("<h6h", 0, *[skills[k] + sk_bonus[k] for k in range(6)]).ljust(0x18, b"\0")
    b114 = bytearray(0x18)
    for k in range(1, 6):
        struct.pack_into("<H", b114, 4 + 2 * (k - 1), skills[k])
    d4 = bytearray(0x40)
    d4[0:4] = bytes(min(255, max(0, v)) for v in bonus)
    for k in range(6):
        struct.pack_into("<h", d4, 0x14 + 2 * k, sk_bonus[k])
    mover = bytearray(0xB4)
    mover[0] = mover[1] = MOVER_FACE
    mover[5], mover[8], mover[9], mover[0xA] = 0x41, 5, 0xFF, speed & 0xFF
    brain = bytearray(0xB8)
    struct.pack_into("<H", brain, 0x16, 0xFFDC)
    brain[0x71] = 1
    brain[BRAIN_AUTO] = state.auto_spell & 0xFF
    if state.wimpy_hp is not None:
        struct.pack_into("<II", brain, BRAIN_WITHDRAW, (state.withdraw_hp or 0) & 0xFFFFFFFF, state.wimpy_hp & 0xFFFFFFFF)
    sight = int(((eff[2] + eff[1]) / 25 + 4) * 256)
    u = SS.Unit(
        base=SS.Base(SS.raw12(SS.VT_HUMANOID if human else SS.VT_UNIT, entry.net_id, 0), entry.net_id, tpl.index if tpl is not None else 0, state.type_id,
                     0, 0, 0, unit_ptr, owner_ptr),
        blk_a6=a6, blk_114=bytes(b114), blk_d4=bytes(d4), mover=bytes(mover), brain=bytes(brain),
        b49=max(1, tpl.get("token_size", 1)) if tpl is not None else 1, b4a=state.move_type & 0xFF, b4b=(state.face & 0x7F) | gender,
        b4c=(2 if spells is not None else 0) | (4 if mage else 0),
        weapon=slots[0], second=slots[1],
        name=state.name or (tpl.name if tpl is not None else ""),
        words=(eff[0], eff[1], eff[2], eff[3], speed, 0, 0, 0, state.hp_max, state.hp_max, 100, state.mana_max, state.mana_max, 50),
        w_a4=sight, b12c=1, d130=state.xp_total, b134=8, b135=4, b136=1,
        packed=entry.number & 0xFFFF,
        pack=SS.Pack(pack_items, state.pack_index, 0) if human else None, spells=spells)
    if human:
        u.hum = SS.Humanoid(struct.pack("<6I", state.best_school, *state.xp), slots)
    return u


def hero_entry(u, types):
    """The `RosterEntry` of a stream hero (inverse of `hero_unit`).  The template comes from the unit's data.bin index `+0xc` (`types` = `AssetCache.unit_stats()`),
    the attributes are the stored words minus the bonus bytes, the skills the stored words minus the bonus words."""
    human = u.hum is not None
    tpl = next((t for t in types if t.kind == ("human" if human else "monster") and t.index == u.base.w0c), None)
    if tpl is None:
        raise ValueError("unit %#x: data.bin template index %d unknown" % (u.number, u.base.w0c))
    bonus_attr = tuple(u.blk_d4[0:4])
    attrs = tuple(max(0, w - b) for w, b in zip(u.words[0:4], bonus_attr))
    sk_bonus = struct.unpack_from("<6h", u.blk_d4, 0x14)
    stored = struct.unpack_from("<6h", u.blk_a6, 2)
    skills = tuple(w - b for w, b in zip(stored, sk_bonus))
    fields = dict(tpl.fields)
    fields.update(zip(PT.ATTRS, attrs))
    stats = replace(tpl, fields=fields)
    pack = tuple(stored_item(i) for i in (u.pack.items if u.pack is not None else ()))
    equipment = tuple(stored_item(i) for i in u.hum.slots) if human else ()
    pools = struct.unpack("<6I", u.hum.block) if human else (0,) * 6
    wimpy, withdraw = struct.unpack_from("<II", u.brain, BRAIN_WITHDRAW)[::-1]
    spellbook = (u.spells.mask or None) if u.spells is not None else None
    st = SimpleNamespace(
        server_id=tpl.server_id, type_id=u.base.w0e, human=human, move_type=(u.b4a - 256 if u.b4a > 127 else u.b4a), face=u.b4b & 0x7F, stats=stats,
        skills=skills, xp=tuple(pools[1:]), xp_total=sum(pools[1:]), best_school=pools[0], mana_max=u.words[12], hp_max=u.words[9], spellbook=spellbook,
        name="" if u.name == tpl.name else u.name, equipment=equipment, pack=pack, pack_index=u.pack.d1c if u.pack is not None else 0x7FFF,
        carried=(), carried_mods=(), skill_bonus=tuple(sk_bonus) if any(sk_bonus) else (), attr_bonus=bonus_attr if any(bonus_attr) else (),
        gear_speed=u.words[4], kill_list=[], speed_mod=0, auto_spell=u.brain[BRAIN_AUTO],
        wimpy_hp=wimpy if (wimpy or withdraw) else None, withdraw_hp=withdraw if (wimpy or withdraw) else None, hero_no=u.number)
    gear.sync_carried(st)
    return PT.RosterEntry(u.number, tpl.server_id, human, u.base.id, st)


# --- the stream ------------------------------------------------------------------------------------------------------------------------------

def build_stream(game, table="auto"):
    """The `ServerStream` of the campaign's town state: tick / block 0, scenario 0, loaded 0 (`FUN_004ebd5f` step 7 resets all of them, CONFIRMED), the 11
    option words 0 (6.11), the human player with one group holding the heroes in list order, the unit container listing them again."""
    if table == "auto":
        try:
            table = game.assets.items()
        except Exception:
            table = None
    ptr = _Ptr()
    player_ptr = ptr()
    states = [hero_state(game, e) for e in game.roster]
    units = [hero_unit(game, e, s, table, player_ptr, ptr) for e, s in zip(game.roster, states)]
    main = game.roster[0].net_id if game.roster else 0
    name = states[0].name if states else ""
    group = SS.Group(ai=bytes(0x45) + b"\1" + bytes(0x0A), units=units)
    player = SS.Player(name=name, b_a44=game.difficulty & 0xFF, gold=game.gold, kills_monsters=game.kills_monsters, hero_deaths=game.hero_deaths,
                       kills_players=game.kills_players, main_hero=main, ptr=player_ptr, table=bytes(game.knowledge or bytes(SS.TABLE_SIZE)), groups=[group])
    return SS.ServerStream(tick=0, block=0, map_name="", scenario=0, difficulty=game.difficulty, players=[player], container=list(units), loaded=0)


# --- the Scenario.dll block ------------------------------------------------------------------------------------------------------------------

def scenario_state(camp, positions=None):
    """`ScenarioState` of a `Campaign`: 1024 variables, the shop table (town t at block row t), the available list with the objects' rectangles (`name16` =
    CRect `(x, y, x, y)` of the world-map point: `0x100038e0` / `0x10003920` build `(type, id, x, y, 0, 0)` objects, CONFIRMED), the position of the current location
    (0 when there is none: `ScenarioSave` `0x10003585`)."""
    if any(not 0 <= k < 1024 for k in camp.vars):
        raise ValueError("a script variable outside 0..1023")
    variables = [0] * 1024
    for k, v in camp.vars.items():
        variables[k] = v
    shops = bytearray(S.SCENARIO_SHOP)
    for town, blocks in camp.shop.items():
        if not 0 <= town < 4:
            raise ValueError("shop town %r outside 0..3" % town)
        for b, blk in enumerate(blocks[:4]):
            struct.pack_into("<5I", shops, (town * 4 + b) * 20, *[v & 0xFFFFFFFF for v in blk])
    positions = positions or {}
    locs = []
    for kind, ident in camp.available:
        x, y = positions.get((kind, ident), (0, 0))
        locs.append(S.Location(ident, kind, struct.pack("<4i", x, y, x, y)))
    cur = camp.available.index(camp.location) if camp.location in camp.available else 0
    return S.ScenarioState(tuple(variables), bytes(shops), locs, cur)


def apply_scenario(camp, sc):
    """The inverse: fills a fresh `Campaign` (variables non-zero only, shop towns that hold any value, the available list in its saved order, location None)."""
    camp.vars = {i: v for i, v in enumerate(sc.variables) if v}
    camp.shop = {}
    for town in range(4):
        blocks = [list(sc.shop_block(town, b)) for b in range(4)]
        if any(any(blk) for blk in blocks):
            camp.shop[town] = blocks
    camp.available = [(loc.type, loc.index) for loc in sc.locations]
    camp.location = None
    return camp


def _positions(game):
    try:
        from engine import worldmap
        return worldmap.load_locations(game.install)
    except Exception:
        return {}


# --- the two directions -----------------------------------------------------------------------------------------------------------------------

def to_save(game, description="", state=None, hotkeys=None, positions=None):
    """`CampaignGame` -> `saves.SaveGame` (town save).  `state` (a `ClientState`) and `hotkeys` (nine `Hotkey`) default to the ones a loaded game kept
    (`game.client_state` / `game.hotkeys`), else the defaults (the hero's name, option words 0, nine empty records)."""
    stream = build_stream(game)
    st = state or game.client_state
    if st is None:
        st = S.ClientState(name=stream.players[0].name or S.DEFAULT_NAME)
    hot = hotkeys or game.hotkeys
    total = sum(game.camp.times)
    tail = S.ClientTail.new(description or game.description, st, (), (total & 0xFFFFFFFF, 0), scenario_state(game.camp, positions if positions is not None else _positions(game)),
                            list(hot) if hot else None)
    return S.SaveGame(stream.pack(), tail)


def from_save(save, install=None, hire=None, seed=1, assets=None, difficulty=None, resume_location=False):
    """`saves.SaveGame` (or the bytes of a file) -> `CampaignGame`.  Only town saves (loaded flag 0) load here; a mission save raises `ValueError`.
    `resume_location`: set `camp.location` to the saved position in the available list (`ScenarioLoad` does, CONFIRMED, saves.md 7); the shell uses it to
    stand in the saved town's scene (the default keeps the loaded game on the map, the L10c decision)."""
    if isinstance(save, (bytes, bytearray, memoryview)):
        save = S.parse_save(save)
    stream = SS.ServerStream.parse(save.stream)
    if stream.loaded:
        raise ValueError("a mission save (loaded flag 1) is not a town save: the world codec is a later step (saves.md 7)")
    human = next((p for p in stream.players if p.human), None)
    if human is None:
        raise ValueError("saved game without a human player")
    game = CG.CampaignGame(install, hire=hire, seed=seed, difficulty=difficulty if difficulty is not None else (stream.difficulty or 2), assets=assets)
    types = game.assets.unit_stats()
    game.roster = [hero_entry(u, types) for g in human.groups for u in g.units]
    game.gold, game.hero_deaths = human.gold, human.hero_deaths
    game.kills_monsters, game.kills_players = human.kills_monsters, human.kills_players
    game.net_ids.used = {0} | {e.net_id for e in game.roster if 0 < e.net_id < 0x6000}
    apply_scenario(game.camp, save.tail.scenario)
    total = save.tail.mission_tail[0]
    game.camp.times = [total] if total else []
    game.mission, game.mercenaries, game.log = None, {}, []
    game.client_state, game.hotkeys, game.description = save.tail.state, list(save.tail.hotkeys), save.tail.description
    game.knowledge = human.table if any(human.table) else None
    if resume_location and save.tail.scenario.locations:
        cur = save.tail.scenario.current
        if 0 <= cur < len(game.camp.available):
            game.camp.location = game.camp.available[cur]
    return game


def kind(save):
    """"mission" or "town": the loaded game's `CurrentState/InBattle` key decides (`FUN_0048c214` -> `FUN_0048c8a3(1)` resumes a mission, else the town scene, CONFIRMED,
    town-worldmap 8 / 4).  `save` = `saves.SaveGame` or file bytes."""
    if isinstance(save, (bytes, bytearray, memoryview)):
        save = S.parse_save(save)
    return "mission" if save.tail.state.in_battle & 1 else "town"


# --- mission-kind saves (L10e-B: engine/missionsave.py) ------------------------------------------------------------------------------------------
class MissionSaveCodec:
    """`Shell.mission_codec`: mission-kind saves (loaded flag 1: `game9999`, a manual save in a mission).  A thin layer over `engine.missionsave`:

    * `save(session, description, state=None, campaign=None) -> saves.SaveGame`: the running mission's world (`session.world`) as a mission save (InBattle 1);
      `state` = the UI's `ClientState` (view, groups), `campaign` = the shell's `CampaignGame` (Scenario.dll block, mission times, hotkeys);
    * `load(save, campaign=None, install=None, assets=None) -> dict`: the `start_game` parameters that resume the mission: `campaign` (rebuilt from the save),
      `mission`, `loaded` (the `missionsave.LoadedMission`: the live world, the client state)."""

    def save(self, session, description, state=None, campaign=None):
        from engine import missionsave
        return missionsave.world_to_save(session.world, campaign, state, description)

    def load(self, save, campaign=None, install=None, assets=None):
        from engine import missionsave
        lm = missionsave.world_from_save(save, assets=assets, install=install, campaign=campaign)
        return {"campaign": lm.campaign, "mission": lm.mission, "loaded": lm}


def roster_states(game):
    """`[(number, server_id, net_id, state)]` with every state materialised (`hero_state`): what two games must agree on to be the same party."""
    return [(e.number, e.server_id, e.net_id, hero_state(game, e)) for e in game.roster]


def comparable(game):
    """A plain, comparable view of the campaign state a town save keeps: variables (non-zero), available list, shop table (non-zero towns), gold and
    statistics, free ids, the mission-time sum, and per hero the materialised state fields the file stores."""
    out = {"vars": {k: v for k, v in game.camp.vars.items() if v}, "available": list(game.camp.available),
           "shop": {t: [list(b) for b in blocks] for t, blocks in game.camp.shop.items() if any(any(b) for b in blocks)},
           "gold": (game.gold, game.hero_deaths, game.kills_monsters, game.kills_players), "ids": sorted(game.net_ids.used), "time": sum(game.camp.times),
           "heroes": []}
    for number, sid, nid, s in roster_states(game):
        out["heroes"].append((number, sid, nid, s.type_id, s.face, s.skills, tuple(s.xp), s.best_school, s.hp_max, s.mana_max, s.spellbook or 0, s.name or s.stats.name,
                              [(k, i.code, i.count, i.price, tuple(i.mods), bool(i.new)) for k, i in enumerate(s.equipment) if i.code], [(i.code, i.count, i.price, tuple(i.mods), bool(i.new)) for i in s.pack],
                              s.pack_index, tuple(s.skill_bonus or ()), tuple(s.attr_bonus or ()), tuple(sorted(s.stats.fields.items())), s.auto_spell))
    return out
