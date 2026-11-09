"""World state: map cells and heights, entities, spatial index, block layer.

Spec: docs/superpowers/specs/2026-10-16-world-state-design.md (cited as "spec");
rules from docs/formats/map.md parts 3 and 4.  Layer 3: knows nothing of view,
ui or pygame.

`MapObject` here is the engine entity; `allods2.formats.objects.MapObject` (the
parsed section 3 record) is imported under the alias `PlacedObject`.
"""

import zlib
import hashlib
import json
from dataclasses import dataclass, field

import numpy as np

from allods2.formats import entities as fent
from allods2.formats.itemdefs import mods_from_effects
from allods2.formats import objects as fobj
from allods2.formats import passability as pas
from allods2.formats import progression as prog
from allods2.formats.objects import MapObject as PlacedObject

from .cellslots import CellSlots, pack
from .netids import NetIds
from .rng import DEFAULT_SEED, Rng

STRUCTURE_ID_BASE = 0x6000      # spec decision 2: runtime object id = 0x6000 + uid (CONFIRMED map.md part 4)
OBJECT_ID_BASE = 0x10000        # spec decision 2: section 3 cells (ours, the file has no ids)
UNIT_ID_BASE = 0x6000           # unit id = 0x6000 + uid: the exe's client view +4, the id space of structures
                                # (CONFIRMED map.md part 5; uids never collide with structure uids in the 46 maps)
ITEM_ID_BASE = 0x30000          # ground piles: 0x30000 + index of the section 8 group (ours; the file has no id)
PILE_ID_BASE = 0x38000          # piles created at run time (loot): ours, above any section 8 group index
DEFAULT_DIFFICULTY = 2          # `[0x6044c4+0xd8]` set by the server ctor 0x4e97bf: normal, no tweak (ai.md section 10)
DEAD = 0x10                     # unit state / order 0x10: removed from the world after the dying countdown (combat.md section 12)
UNIT_ANGLE_MIN, UNIT_ANGLE_SPAN = 0x40, 128     # creature ctor: angle = 0x40 + rand(128) (CONFIRMED map.md part 5)
IDLE = "idle"                   # logical action of a unit that does nothing; the view picks idle or stand
DEFAULT_HP = 1000               # healthMax 0 -> 1000 (map.md part 4)
FLAG_DESTROYED = 1

KINDS = ("object", "structure", "bridge")
_SOLID, _CLEAR = fobj.SOLID, fobj.CLEAR


@dataclass
class MapObject:
    """A world entity from a map (spec "MapObject").  `footprint` lists the
    BuildingPresent cells row-major as (dx, dy, solid); `seq` is the stamp
    order (assigned on add, later wins), not serialised."""
    id: int
    kind: str                   # "object" | "structure" | "bridge"
    type_id: int                # objects.reg / structures.reg ID (bridge 0x21)
    x: int
    y: int
    sub_x: int = 128            # 1/256 cell, 128 = centre
    sub_y: int = 128
    variant: int = 0
    owner: int = 0
    hp: int = 0
    hp_max: int = 0
    flags: int = 0
    uid: int = 0
    footprint: tuple = ((0, 0, True),)
    known: bool = True
    seq: int = 0
    size: tuple = None          # (w, h) cells of a sized bridge (section 4), else None
    indestructible: bool = False    # data.bin healthMax 0 (server structure +0x44 == 0): FUN_005201b2 returns 0 damage
    sight: int = 0              # client sight word `obj+0x10a` (8.8): data.bin `scanRange << 8` (vision.md)


@dataclass
class Player:
    """Section 5 record (map.md part 5).  `id` is the 1-based record number, the value
    `Unit.owner` and `MapObject.owner` hold.  `colour` = row of humans/human.pal."""
    id: int
    colour: int
    name: str = ""
    flags: int = 0
    money: int = 0
    relations: tuple = ()           # 16 words, toward player j + 1 (1 war, 2 alliance, 0x10 vision)
    human: bool = False             # single player: record 1 only (map.md part 5)
    selection: tuple = ()           # selected unit ids, command order (sim/selection.py)
    formation: int = 1              # client option [GameOptions] Formation: 0 off, 1 auto (default), 2 on (R 4.1)
    main_hero: int = 0              # unit id of the owner's main hero (exe owner+0x38; 0 = none); INFERRED: the first hero of the human at load
    hero_deaths: int = 0            # exe owner+0xa54: +1 when the main hero reaches state 0x10 (a statistics counter, in the saves)
    gold: int = 0                   # exe owner+0x3c: the player's gold (trigger instant 23; the character file's stats +0x10)
    kills_monsters: int = 0         # exe owner+0xa48 (statistics, character file stats +0x00)
    kills_players: int = 0          # exe owner+0xa4c (stats +0x04)
    death_code: int = 0             # exe owner+0x40 (byte): `server_id - 0x13` of the last hero of the human that died (message 0xb4)
    defeat_dialog: bool = False     # the client opens the hero-died dialog (combat.md 12.3a); the UI clears it
    autocast: int = 0               # the party-AI byte (player `+0x34` record `+0x20`, message 0x46 sub 3): bits 8 / 0x10 / 0x20 = auto-cast levels (heal, buffs, protections), 1 / 2 / 4 = friend kinds (own, allied, neutral); docs/engine/ai.md 12.8


@dataclass
class OrderGroup:
    """The exe's command group (`FUN_0052b06f`, 0x50 bytes + record at +0x3c): every player command makes a
    new one.  `order` = record+0x20 (0 cancelled, 3 stand ground, 4 group move), `target` = record+0xa (x, y),
    unclamped, `speed` = record+0x44 (non-zero only when the formation was active), `members` in packet order."""
    id: int
    owner: int
    members: list = field(default_factory=list)
    order: int = 0
    target: tuple = (0, 0)
    speed: int = 0
    # the AI fields of the group record (docs/engine/ai.md 2, 14): used by the group orders 1, 2, 5, 0x11, 0x12, 0x13
    centre: int = 0                 # +0x28 packed cell word of the centroid
    spread: int = 0                 # +0x2a
    reach: int = 0                  # +0x2c
    radius: int = 0                 # +0x2d pool radius in cells
    base: int = 0                   # +0x38
    seen: int = 0                   # +0x30
    passes: int = 0                 # +0x34
    counter: int = 0                # +0x15 wander pass counter (byte)

    def ai_dump(self):
        """The AI fields, [] while they are all zero (a plain move / stand group keeps the old hash layout)."""
        d = [self.centre, self.spread, self.reach, self.radius, self.base, self.seen, self.passes, self.counter]
        return d if any(d) else []


@dataclass
class Effect:
    """A spell effect object (class `0x5d1178`, docs/engine/effects.md 2): `id` = `+0xc` (the spell number, mask bit `1 << id`),
    `kind` = `+0x3c` (stat index, 0 = none), `flags` = `+0x3d` (1 duration, 2 continuous, 4 charges, 8 single use, 0x80 finished),
    `value` = `+0x40`, `ticks` = `+0x42` (u16, >= 0x2581 never counts down), `caster` = `+0x44` (unit id or None)."""
    id: int
    kind: int = 0
    flags: int = 0
    value: int = 0
    ticks: int = 0
    caster: int = None

    def copy(self):
        return Effect(self.id, self.kind, self.flags, self.value, self.ticks, self.caster)

    def dump(self):
        return [self.id, self.kind, self.flags, self.value, self.ticks, self.caster]


@dataclass
class EffectStats:
    """What the active effects changed (docs/engine/effects.md 5): monsters' direct fields as deltas (`speed` = `+0x8c`, `absorb` =
    `+0xc0`, `defence` = `+0xbe`, `scan` = `+0xa4 >> 8`), humans' bonus words (`speed` = `+0xd8`, `absorb` = `+0x100`, `defence` = `+0xfe`,
    `scan` = `+0xe4 >> 8`, `prot` = `+0x102..+0x10c`); `scan_direct` = the part Darkness adds to a human's `+0xa4` until the next recompute."""
    speed: int = 0
    absorb: int = 0
    defence: int = 0
    scan: int = 0
    scan_direct: int = 0
    prot: list = field(default_factory=lambda: [0] * 6)
    hp_regen: int = 0               # humans' bonus words +0xde / +0xe2 (percent, effect kinds 8 / 11: the regeneration potions)
    mana_regen: int = 0

    def any(self):
        return bool(self.speed or self.absorb or self.defence or self.scan or self.scan_direct or any(self.prot) or self.hp_regen or self.mana_regen)

    def dump(self):
        return [self.speed, self.absorb, self.defence, self.scan, self.scan_direct, list(self.prot)] + ([self.hp_regen, self.mana_regen] if self.hp_regen or self.mana_regen else [])


@dataclass
class AiState:
    """Per-unit AI fields of the Brain (docs/engine/ai.md 3, 8): `stamp` = `brain+0x16` (the follow planner's failure stamp, a block
    counter word; ctor 0xffdc), `target` = `+0x20` (the group scan's choice), `hit_by`/`hit_tick`/`hit_cell` = `+0x94/+0x98/+0x9c` (the hit
    reaction `FUN_0056e6b8`; `hit_cell` is a packed cell word `y << 8 | x`), `mark_cell`/`mark_age` = `+0x58/+0x5a` (the attacker's cell
    revealed to the group), `alerted` = `+0x54` (a hit turns the idle look-around at once)."""
    stamp: int = 0xFFDC
    target: int = None
    hit_by: int = None
    hit_tick: int = 0
    hit_cell: int = 0
    mark_cell: int = 0
    mark_age: int = 0
    alerted: int = 0
    spell_mark: int = 0             # brain+0xa4: number of the last spell an AI / player cast aimed at this unit (`FUN_0056c72b`), read by `FUN_0056bc7b`
    spell_tick: int = 0             # brain+0xa8: the server tick of that cast order
    area_hits: int = 0              # brain+0xac: area hits taken from neutral owners (FUN_0057977a with area = 1; docs/engine/effects.md 6.3)

    def dump(self):
        d = [self.stamp, self.target, self.hit_by, self.hit_tick, self.hit_cell, self.mark_cell, self.mark_age, self.alerted]
        if self.spell_mark or self.area_hits:                                   # old AI goldens keep their layout
            d += [self.spell_mark, self.spell_tick]
        return d + [self.area_hits] if self.area_hits else d


@dataclass
class AiGroup:
    """A squad of one computer-owned player under group order `0x12` (docs/engine/ai.md 2): the group record fields the handler reads."""
    key: tuple                      # (owner, squad)
    members: list = field(default_factory=list)     # unit ids in list (creation) order
    order: int = 0x12
    centre: int = 0                 # +0x28 packed cell word of the centroid
    spread: int = 0                 # +0x2a max member distance to the centroid
    reach: int = 0                  # +0x2c max (distance + scan range)
    radius: int = 0                 # +0x2d pool radius in cells
    base: int = 0                   # +0x38
    seen: int = 0                   # +0x30 set after the first pass
    passes: int = 0                 # +0x34
    awake: bool = True              # GroupAI record +0x45, recomputed at every group pass (ai.wake, docs/engine/ai.md 15)
    keep_awake: bool = False        # GroupAI record +0x48: never sleeps (set by triggers.enable for squads the map script names)
    target: tuple = (0, 0)          # +0x0a group destination (x, y) of the orders 2, 5, 0x11
    speed: int = 0                  # +0x44 group speed of a formation (orders 4, 5)
    counter: int = 0                # +0x15 wander pass counter (byte)

    @property
    def owner(self):
        return self.key[0]

    def dump(self):
        d = [list(self.key), list(self.members), self.order, self.centre, self.spread, self.reach, self.radius, self.base,
             self.seen, self.passes]
        d = d if self.awake else d + [0]                # a sleeping squad changes the hash; an awake one keeps the old layout
        if self.order != 0x12:                          # a squad a script re-ordered (ai.set_group_order)
            d += [list(self.target), self.speed, self.counter]
        return d


@dataclass(frozen=True)
class Damage:
    """Fight log entry: one resolved blow (`World.fight_log`, never in the dump).  `amount` 0 for a miss or an absorbed hit; `hp` is the
    target's HP after it; `roll` the `rand(200) - 100` of the exe (0 when nothing was drawn)."""
    tick: int
    attacker: int
    target: int
    amount: int
    hp: int
    roll: int = 0
    hit: bool = False


@dataclass(frozen=True)
class Healed:
    """Fight log entry: `FUN_00510484` raised the HP of `target` by `amount` (Heal 24, the caster of Drain Life 26; spells.md 4); `hp` after it."""
    tick: int
    caster: int
    target: int
    amount: int
    hp: int


@dataclass(frozen=True)
class Died:
    """Fight log entry: a unit's HP fell to 0 or below (the dying countdown starts at its next creature tick, combat.md 12.1)."""
    tick: int
    unit: int
    by: int


@dataclass(frozen=True)
class Removed:
    """Fight log entry: the unit reached state 0x10 (footprint released, loot dropped, kill credit paid)."""
    tick: int
    unit: int


@dataclass(frozen=True)
class Killed:
    """Fight log entry: a kill that the exe's creature loop (`FUN_0052b459`, `0x52b709`-`0x52b84a`) credits to a hero-type unit with HP >= 0: the
    killer's owner learns about the victim's type (`player+0x44[victim +0x14c]`, ui-layout 11.1).  `server_id` / `human` are the victim's raw
    template key and class (the UI reduces them like `+0x14c`); `killer_owner` is the killer's owner at that moment.  Log only: no world state."""
    tick: int
    unit: int
    server_id: int
    human: bool
    killer: int
    killer_owner: int


@dataclass(frozen=True)
class CastStarted:
    """Fight log entry: the cast passed its first tick (`FUN_00519998` returned non-zero: mana spent for a learned spell, the client message `0x86`
    sent); `flight` is the client's projectile time (`sim/spells.client_flight_ticks`)."""
    tick: int
    caster: int
    target: int
    spell: int
    flight: int


@dataclass(frozen=True)
class CastReleased:
    """Fight log entry: the windup ended and the effect was built (`FUN_00519db8`): `level` of the cast, `carrier` the missile carrier id (0: none)."""
    tick: int
    caster: int
    target: int
    spell: int
    level: int
    carrier: int


@dataclass
class SpellCast:
    """The cast in progress (unit `+0x5c` target, `+0x60/+0x61` cell, `+0x64` wrapper, `+0x68` item): `item_count` is the `castSpell=Name:N`
    count of a cast from the wielded weapon (`+0x68 != 0`, free of mana, level N), None for a learned spell."""
    spell: int
    target: int = None              # unit id (state 0xd); None for a cell cast
    cell: tuple = None              # state 0xe
    item_count: int = None
    chain: tuple = None             # Prismatic Spray: the unit ids of the chain list sent in message 0x8a (target first), set at the cast start


@dataclass
class Bolt:
    """A client Lightning / Prismatic Spray projectile (projectile id 28 / 30, `FUN_0046707e`; docs/engine/effects.md 11): spawned by the caster's cast
    action at the unit type's ShootDelay frame, 13 ticks of life, phase by the ping-pong table.  `targets`: Lightning the one target (view `+0x8e`), the
    Spray the list of message 0x8a (view `+0xb0`).  `origin` is the projectile's start in 1/256 cell (the caster's ShootOffset point; the cell centre for
    the hidden caster's 0x8c form); `born` may lie in the future (the cast action's ShootDelay tick); `age0` is -1 for the message-created form.
    Client only, not dumped."""
    pid: int
    caster: int
    targets: tuple
    origin: tuple
    born: int
    life: int = 13
    age0: int = 0


@dataclass
class Explosion:
    """A client fire-explosion object (projectile 13, `FUN_0046c1d0` case 0xd): created by message 0x86 (the cell form, `FUN_005045a5` of a Fire Ball
    area carrier's first visit) at the cell centre, `life` = 22 ticks (the message's lifetime byte), age -1 at creation.  Client only, not dumped."""
    x: int
    y: int
    born: int
    life: int = 22


@dataclass
class Carrier:
    """A spell carrier of the active list (`server+0x7c`, `FUN_0052c279`): kind "missile" (`FUN_00518d1e`, counts `ticks_left` down and then appends
    its point carrier) or "point" (`FUN_005178d4`, applies the effect on its first visit).  Docs: spells.md 9c.3."""
    uid: int
    kind: str
    caster: int
    target: int
    spell: int
    level: int
    ticks_left: int = 0
    born: int = 0
    hostile: bool = True            # carrier +0x41: attacker credit and AI alert
    start: tuple = (0, 0)           # caster position (x, y) in 1/256 cell at the release: the view derives the missile position from it
    flight: int = 0                 # ticks the missile was created with (view only)
    aim: tuple = (0, 0)             # target position (x, y) in 1/256 cell at the release: the missile's line when the target vanishes (view only)
    # effect and area carriers (docs/engine/effects.md 6); defaults = a damage carrier of phase I
    effect: object = None           # Effect template of a point / area carrier (None: the spell's damage effect)
    centre: tuple = None            # area / field carrier: centre cell (x, y); a missile with a centre lands as an area carrier
    radius: int = 0                 # +0x4d
    mode: int = 0                   # +8: 0 apply once, 1 lifetime pulse, 2 field
    life: int = 0                   # +0x50 (s16)
    stamped: bool = False           # +0x4c
    direction: int = 0              # +0x4e (8-way)
    step: int = 0                   # +0x4f

    def area_dump(self):
        if self.effect is None and self.centre is None:
            return []
        return [self.effect.dump() if self.effect is not None else None, list(self.centre) if self.centre else None, self.radius, self.mode,
                self.life, int(self.stamped), self.direction, self.step]


@dataclass(frozen=True)
class HeroDied:
    """Fight log entry: message `0xb4` (`FUN_00510a70` step 8): a hero unit of the human player reached state 0x10.  `code` = `server_id - 0x13`
    (owner+0x40); `main` = it was the owner's main hero (HP := -50, `hero_deaths` + 1).  The client opens the modal "load / quit" dialog (combat.md 12.4)."""
    tick: int
    unit: int
    code: int
    main: bool


@dataclass(frozen=True)
class LevelUp:
    """Fight log entry: school `school` (1..5) of a hero rose to `skill` (`FUN_005128cb`)."""
    tick: int
    unit: int
    school: int
    skill: int


@dataclass(frozen=True)
class Loot:
    """Fight log entry: a pile was dropped (or merged) on cell (x, y) by a dying unit."""
    tick: int
    unit: int
    x: int
    y: int
    gold: int
    codes: tuple


def death_stage(hp):
    """The client's death stage (animation.md 3.3, `obj+0x184`): 0 alive, 1 dying / corpse, 2..4 bones 1..3, 5 not drawn."""
    if hp > 0:
        return 0
    return 1 if hp >= -10 else 2 if hp >= -20 else 3 if hp >= -40 else 4 if hp >= -600 else 5


@dataclass(frozen=True)
class NoWay:
    """Event: the static planner of one of `player_id`'s units ended far from its target (message `0x92`,
    text "No way").  Lives in `World.events`, never in the dump or the hash."""
    player_id: int
    tick: int


@dataclass
class Mover:
    """Movement state of a unit: the exe's Mover object (creature +0x1c0, 0xb4 bytes),
    docs/engine/unit-struct.md section 7.  Facing and the sub-cell offset live on the Unit
    (mover[0] and the Position object); everything else of a step is here.  Steps are in 1/256
    cell."""
    turn_rate: int = 16             # +0x0a facing units per tick (data.bin turn rate; ctor default 0x10)
    target_facing: int = -1         # +0x01 (-1: equal to the unit's facing, as the ctor sets both)
    step_target: tuple = None       # +0x06 cell being entered (x, y) while a step is in progress
    step_from: tuple = None         # +0x70 cell where the step began
    steps: int = 0                  # +0xac ticks done in the step
    step_ticks: int = 0             # +0xaa ticks the step takes (ceil(256 / larger component))
    step_len: int = 0               # +0xa8 length per tick, 1..63
    step_dir: int = 0               # +0xae dir8 of the step (0 N, 1 NE, 2 E ... 7 NW)
    dx: int = 0                     # +0xb0 signed per-tick offset, x
    dy: int = 0                     # +0xb1 y
    turning: bool = False           # +0xa0 a multi-tick turn is in progress
    turn_ticks: int = 0             # +0xa4 ticks the current turn takes
    turn_done: int = 0              # +0x9d turn ticks done
    # path-finding state (docs/engine/simulation.md section 7); the exe's offsets in brackets
    goal: tuple = None              # target cell of the move order (the brain's argument of FUN_00555411)
    dest: tuple = None              # +0x74 target cell the static plan was made for
    tail: tuple = None              # +0x76 last cell of the static plan (own cell when it failed)
    consumed: int = 0               # +0x09 hop plans since the static plan (0xFF = force a re-plan)
    since_hop: int = 0              # +0x78 ticks since the last hop plan
    arrived: bool = False           # +0x90 the unit stands on `tail`
    failed: bool = False            # +0x98 a plan came out empty
    static_path: list = field(default_factory=list)     # the static list (+0x1c8); Unit.path is the dynamic one
    follow: int = None              # +0x7c the unit id the follow driver last planned for (0 after a cancel / arrival at the hop goal)
    follow_cell: tuple = None       # +0x8c the target cell the follow plan was made for
    static_len: int = 0             # +0x8a length of the static list after the last follow re-plan (0xFF = forced)
    waiting: bool = False           # brain mode 10 (`FUN_00556b2c`/`00555411`): turning to face the blocker
    parked: bool = False            # brain mode 0 under a move order after a wait: no driver restarts it
    stamp_cell: int = 0             # +0x80 the cell word `FUN_0055be86` last stamped for (0 = none, mode 2); not dumped
    last_plan: object = None        # debug: PathResult of the last static plan (not dumped)
    last_hop: object = None         # debug: PathResult of the last hop plan (not dumped)
    last_hop_goal: tuple = None     # debug: the cell that hop plan aimed at (not dumped)


@dataclass
class Unit:
    """A unit or monster (section 6 record).  Field names and meanings follow the exe's
    Creature, docs/engine/unit-struct.md section 2; only what is needed now is here, the rest
    (mover, brain, order +0x50, state +0x54, stats, effects, equipment) belongs to the
    simulation phases and will be added with the systems that use it.

    Position is the cell plus a sub-cell offset in 1/256 cell (Position: cell +0/+1, sub-cell
    +4/+5, 0x80 = centre); `facing` is the mover angle byte (0 up, clockwise, 256 = full circle,
    mover[1]); the draw direction is `facing >> 4` (D2, 0..15).  `action` is the logical action
    name (`IDLE`...), `action_start_tick` the world tick it began (animation time =
    `world.tick - action_start_tick`)."""
    id: int
    type_id: int                    # units.reg ID (creature word +0x0e; the map's editor copy)
    owner: int                      # Player.id (creature +0x14)
    x: int                          # cell
    y: int
    sub_x: int = 128
    sub_y: int = 128
    facing: int = 0x80
    action: str = IDLE
    action_start_tick: int = 0
    hp: int = 0                     # +0x94
    hp_max: int = 0                 # +0x96
    uid: int = 0                    # scenario unit number (+8)
    server_id: int = 0              # data.bin serverID (template key)
    human: bool = False             # data.bin humans (0x254 object) rather than monsters (0x208)
    behaviour: int = 0              # map unit +0x50: bit 8 = summoned (no loot, no XP)
    move_type: int = 1              # +0x4a data.bin movementType: 1 walker, 2 ghost/bee, 3 flyer (mover mask)
    face: int = 1                   # +0x4b palette variant (data.bin monster `face`, 1..7; humans: skin)
    squad: int = 0                  # per-owner group number (file +44)
    group: int = 0                  # section 8 group index (1-based, 0 none): the carried items
    known: bool = True              # units.reg set and data.bin template both exist
    seq: int = 0                    # insertion order, the depth tie-break
    stats: object = None            # allods2.formats.unitstats.UnitType template (None if unknown)
    skills: tuple = ()              # humans: +0xa8..+0xb2 (general, blade, axe, bludgeon, pike, shooting); () for monsters
    xp: tuple = ()                  # humans: XP pools of skills 1..5 (+0x23c+4k), pool = thr[skill] at start
    xp_total: int = 0               # humans: +0x130, the sum of the pools
    best_school: int = 0            # +0x23c for Hero_/Start_ templates: first highest school 1..5, else 0
    mana: int = 0                   # humans: +0x9a (starts at the maximum)
    mana_max: int = 0               # humans: +0x9c, derived like the max HP (0 for fighters)
    speed_mod: int = 0              # a fixed offset added to the speed stat (+0x8c): tests and debug tools (Haste / Slow are `fx.speed`, sim/effects.py)
    order: int = 0                  # +0x50 order id (0 none, 1 move to cell); sim/movement.py
    state: int = 0                  # +0x54 state (0 idle, 1 move step); sim/movement.py
    path: list = field(default_factory=list)    # cells still to enter, front first (the exe's list at +0x1c8)
    mover: Mover = field(default_factory=Mover)
    odometer: int = 0               # client walk counter obj+0x9c: map units moved, 16 per walk frame
    order_group: int = 0            # id of the OrderGroup the unit belongs to (unit+0x70), 0 none
    hidden: bool = False            # +0x144 & 0x1000: the Invisibility effect (id 12); mirrored by sim/effects.py
    invis_ending: bool = False      # an Invisibility effect (kind 12) got `+0x42 := 1` at a swing start (FUN_00516b2f); the effect pass of the next creature tick ends it
    bless: int = None               # chance 0..100 of the Bless effect (spell 20, effect `+0x40`; `+0x144` bit 20), None when absent (FUN_00516f6f via FUN_005106d2/5106f4); mirrored by sim/effects.py
    curse: int = None               # same for Curse (spell 28, bit 28)
    stopped: bool = False           # brain+0x50: set by the stop routine FUN_0056dbc6, cleared by every cancel
    mode_go: bool = False           # Brain mode 1 (go to brain+0xa, mover.goal): the move order and the group-pass restart
                                    # (FUN_0056c8af) set it, the stand orders (FUN_0056d52b) and a failure under another order clear it
    anchor: tuple = None            # brain anchor cell of the stand orders 0xb/0xc
    # fight state (docs/engine/combat.md; sim/combat.py): the exe's offsets in brackets
    combat: object = None           # sim.combatstats.CombatStats, built on first use from `stats` and the item table
    target: int = None              # brain+0xc id of the attack target (order 3, Brain mode 5)
    mode_attack: bool = False       # Brain mode 5 (attack with approach)
    range: int = 1                  # brain+0x14 attack / approach range in cells
    brain_order: int = 0            # brain+0x9: 1 = swing in progress (a step in progress is `mover.step_ticks`)
    swing_count: int = 0            # brain+0x15 ticks into the swing
    phase: int = 0                  # +0x58 swing phase: 0 start, 5 wind-up, 7 recovery
    timer: int = 0                  # +0x6c byte countdown of the phase
    done: bool = True               # +0x136 the swing has finished (set when the recovery ends)
    swing_target: int = None        # +0x5c target of the swing in progress
    last_attacker: int = None       # +0x40 whoever hit this unit last
    # death, regeneration and XP (docs/engine/combat.md section 12; sim/death.py, vitals.py, xp.py)
    death_seen: bool = False        # +0x13c the HP <= 0 branch ran once (never reset: a revived unit skips it the next time)
    death_tick: int = None          # world tick of that first run (`T0`); the dying animation starts there
    step_end: int = 0               # +0x138 tick at which the last move step ends (the regeneration rest test)
    hp_acc: int = 0                 # +0xa2 hundredths of an HP carried between regeneration steps
    mana_acc: int = 0               # +0xa3 likewise for mana
    carried: tuple = ()             # item codes of the section 8 group the unit carries (dropped at death)
    kill_list: list = field(default_factory=list)       # +0x1a8 repeat-kill list of a hero: up to 5 [server_id, count]
    ai: AiState = field(default_factory=AiState)        # Brain AI fields (sim/ai/, docs/engine/ai.md)
    mode_look: bool = False         # Brain mode 0xb: the idle look-around (`FUN_0056e5bc`) of a computer-owned unit
    wimpy_hp: int = None            # brain+0x44 / +0x40 set by the retreat mode message (`SetRetreatMode`); None = the template values (data.bin p35 / p34)
    withdraw_hp: int = None
    tweak: int = 0                  # difficulty mode applied at load (`FUN_00561bf9` 0x561e20): 0 none, 1 easy, 3 hard (docs/engine/ai.md 10)
    # spell casting (docs/data/spells.md 9c; sim/spells.py)
    mode_cast: bool = False         # Brain mode 8 (cast with approach, `FUN_0056ebc0`)
    cast_target: int = None         # brain+0x28 target of the cast order / mode
    cast_wrapper: object = None     # brain+0x30 the `spells.Wrapper` of the cast order
    cast: object = None             # `SpellCast` of the cast in progress (unit +0x5c/+0x64/+0x68)
    spellbook: int = None           # unit+0x140 learned-spell bit mask (bit n = spell n); None: derived from the template (`spells.known_mask`)
    teleport_to: int = 0            # brain+0xb0: a pending teleport target `y << 8 | x` set by a Teleport cell record (sim/traps.py), 0 = none
    auto_spell: int = 0             # brain+0x78: the unit's selected spell (Ctrl+A, message 0x46 sub 4; docs/engine/ai.md 12.8): the attack range and the human cast decision `FUN_0056b059` read it
    ai_cast: bool = False           # brain+0x60: the cast was set by the AI (`FUN_0056a981` & co.): Brain mode 8 / 9 stays after the cast starts; cleared by every cancel
    mode_cell: bool = False         # Brain mode 9 (cast at a cell with approach, `FUN_0056ec3f`)
    cast_cell: tuple = None         # brain+0x3c target cell (x, y) of the cell cast order 0xe / mode 9
    name: str = ""                  # +0x80 CString: set only for heroes (hero name setters 0x4ead6b, 0x4f2b4c); the by-name hero look-up reads it (triggers.md 9.5); not dumped
    net_id: int = 0                 # +0x04 the exe object id of a unit made at run time (`engine/netids.py`: a hero, a summoned minion); 0 = a map unit (id `0x6000 + uid`)
    master: int = 0                 # +0x148 the summoner's id (Summon spell; 0 = none): the minion cap job reads it (sim/spells.py `minion_job`)
    # follow / patrol orders and Brain mode 4 (docs/engine/ai.md 14.2; sim/follow.py)
    leader: int = None              # brain+0x10 the object being followed / defended (orders 8, 0x11)
    follow_range: int = 0           # brain+0x70 follow distance (default 3)
    mode_follow: bool = False       # Brain mode 4 (approach brain+0x18 within brain+0x14, `FUN_0056ea52`)
    follow_target: int = None       # brain+0x18 the mode-4 target
    patrol: list = field(default_factory=list)      # brain+0xb4 the waypoint list of order 0xa (cell tuples)
    patrol_wp: tuple = None         # brain+2 the waypoint being walked to
    patrol_walk: bool = False       # brain+4 the previous pass left a walk running
    equipment: tuple = ()           # humans with an explicit loadout (a character record, or after an item command): the 12 equipped items in slot order
                                    # (saves.Item, index = creature slot - 1: weapon, second hand, armour slots 3..12; empty slot = code 0); () = the template strings
    pack: tuple = ()                # humans loaded from a character record: the backpack items (saves.Item); `carried` holds their codes
    pack_index: int = 0x7FFF        # pack +0x1c: where the next item filed in the pack goes (0x7fff = the end); set by item messages (sim/gear.py)
    mode_loot: bool = False         # Brain mode 12 (`FUN_0056eb2d`): walk to the sack chosen by order 0x1a (`brain+0xa`), then pick it up (sim/gear.py)
    mode_pick: bool = False         # Brain mode 7 (`FUN_0056ea24`): file the sack on the own cell (state 2)
    pick_cell: tuple = None         # brain +0xa of the pickup order 2: the sack's cell
    gear_speed: int = None          # the speed stat +0x8c of a human with an explicit loadout (load penalty, equipment bonus); None: the Reaction rule
    skill_bonus: tuple = ()         # bonus words +0xe8 + 2k of the equipment, added to the school skills (sim/gear.py); () = none
    attr_bonus: tuple = ()          # equipment bonus (body, reaction, mind, spirit) on top of the template's capped attribute; () = none
    carried_mods: tuple = ()        # parallel to `carried`: the modifier records (kind, a, b) of each carried item (sim/gear.py); () = none carries any
    # spell effects (docs/engine/effects.md; sim/effects.py)
    effects: list = field(default_factory=list)     # +0x20 the effect list (Effect), list order
    effect_mask: int = 0            # +0x144 bit 1 << id of every active effect
    fx: EffectStats = field(default_factory=EffectStats)    # the stat changes of the effects

    def set_mode(self, go=False, attack=False, look=False, cast=False, cell=False, follow=False):
        """Assign all six Brain-mode flags at once (an omitted flag is cleared)."""
        self.mode_go, self.mode_attack, self.mode_look = go, attack, look
        self.mode_cast, self.mode_cell, self.mode_follow = cast, cell, follow

    @property
    def has_mode(self):
        """Any of go / attack / look / cast / cell is set (mode_follow is not counted)."""
        return self.mode_look or self.mode_go or self.mode_attack or self.mode_cast or self.mode_cell

    @property
    def idle_mode(self):
        """Only the idle look-around mode is set (go / attack / cast / cell clear; mode_follow is not tested)."""
        return self.mode_look and not (self.mode_go or self.mode_attack or self.mode_cast or self.mode_cell)

    @property
    def oid(self):
        """The exe object id `+0x04`: the free id of a unit made at run time, else `0x6000 + uid` (= `id`)."""
        return self.net_id or self.id

    def __post_init__(self):
        if self.mover.target_facing < 0:
            self.mover.target_facing = self.facing      # the ctor writes mover[0] and mover[1] together


@dataclass
class Item:
    """A pile on the ground (a section 8 group no unit carries; the exe's backpack,
    `FUN_005299b3` pack + `FUN_0052ab07` placement).  `gold` is the pile's gold (file `extra`);
    `codes` the item codes of the members (`entities.decode_item`); one pile per cell."""
    id: int
    x: int
    y: int
    sub_x: int = 128
    sub_y: int = 128
    gold: int = 0
    codes: tuple = ()
    groups: tuple = ()              # section 8 group indices merged into this pile
    seq: int = 0
    mods: tuple = ()                # parallel to `codes`: the modifier records (kind, a, b) of each item (the exe's pile holds the item objects with their
                                    # effect lists, combat.md 12.11); () = no item has any.  Not dumped (static once built; piles keep the dump of codes)
    net_id: int = 0                 # +0x04 the pile's free id (`FUN_0052a780`, engine/netids.py); not dumped


@dataclass
class BuildReport:
    """What `World.from_map` found (spec "world.report")."""
    unknown: list = field(default_factory=list)     # (kind, type_id, x, y)
    ignored_outside_window: int = 0
    counts: dict = field(default_factory=dict)      # (kind, type_id) -> n
    unknown_units: list = field(default_factory=list)   # (uid, type_id, server_id, x, y): kept, known=False
    units_on_blocked: int = 0       # units whose cell is blocked for their mover: the exe server never creates them (FUN_00510089, r = 0); kept here
    units_sharing_cell: int = 0     # cells with more than one unit


def unit_angle(uid, facing=None):
    """The creature constructor's start angle `0x40 + rand(128)` (map.md part 5, CONFIRMED
    0x50e2ac); the file has no facing.  DECISION: the random draw is replaced by a hash of the
    uid so loading is deterministic.  An int `facing` overrides it."""
    if facing is not None:
        return facing & 255
    return UNIT_ANGLE_MIN + ((uid * 2654435761) >> 11) % UNIT_ANGLE_SPAN


def structure_footprint(s, stats):
    """(footprint, known, hp_max) of a section 4 record (spec decision 4).
    Present cells only, solid = Passability bit (map.md part 4, FUN_00550a96).
    A type missing in data.bin gets the single cell, solid, hp_max 1000."""
    if s.size is None and not 1 <= s.type <= len(stats):
        return ((0, 0, True),), False, DEFAULT_HP
    w, h, solid, present = fobj.footprint(s, stats)
    sol, pre = fobj.mask_cells(w, h, solid), fobj.mask_cells(w, h, present)
    fp = tuple((c, r, bool(sol[r, c])) for r in range(h) for c in range(w) if pre[r, c])
    hp_max = stats[s.type - 1].params[3] if 1 <= s.type <= len(stats) else 0
    return fp, True, hp_max or DEFAULT_HP


class World:
    """`cells` (h, w) uint16 runtime tile values, `heights` (h, w) int8 (one
    signed byte per vertex, 1 px each), `terrain` the raw Tiles (dirt bit kept)
    the block layer reads (default `cells`).  Campaign maps are square (spec
    decision 8); other shapes are accepted here for the view tests (the exe's
    grid of a non-square map is 256 wide, FUN_00553b30, not modelled)."""

    def __init__(self, cells, heights, name="", terrain=None, seed=DEFAULT_SEED):
        self.cells = np.asarray(cells, np.uint16)
        self.heights = np.asarray(heights).astype(np.int8)
        if self.cells.shape != self.heights.shape:
            raise ValueError("cells and heights differ in shape")
        self.height, self.width = self.cells.shape
        self.terrain = self.cells if terrain is None else np.asarray(terrain, np.uint16)
        if self.terrain.shape != self.cells.shape:
            raise ValueError("terrain and cells differ in shape")
        self.name = name
        self.light_vertices = {}    # (x, y) vertex -> light value written by Light / Darkness cell flags (`light_write`)
        self.light_version = 0
        self.cells_version = 0      # bumped when a tile bit changes at run time (burnt ground): terrain surface caches drop
        self.tick = 0
        self.seed = seed & 0xFFFFFFFF   # the game's RNG seed (docs/engine/simulation.md section 10)
        self.rng = Rng(seed)            # the one generator of the simulation, drawn in update order
        self.objects = {}           # id -> MapObject
        self.units = {}             # id -> Unit, in map record order
        self.items = {}             # id -> Item (ground piles), in section 8 order
        self.corpses = {}           # id -> Unit in state 0x10 (ground units after the dying countdown), in removal order
        self._next_pile = PILE_ID_BASE
        self.net_ids = NetIds()     # the server's free-id bitmap (`DAT_006c9628`): piles, new heroes, summoned units; not dumped
        self.players = {}           # id (1-based record) -> Player
        self.groups = {}            # id -> OrderGroup, in creation order (sim/orders.py)
        self.events = []            # NoWay ...: for the UI, not part of dump()/the hash
        self.fight_log = []         # Damage / Died entries (sim/combat.py), drained by the UI, not part of the dump
        self.item_table = None      # allods2.formats.itemdefs.ItemTable (from_map); combat stats read it
        self.spell_table = None     # allods2.formats.spelldefs.SpellTable (from_map); the cast code reads it
        self.assets = None          # the AssetCache of from_map: units created at run time (Summon, Control Spirit) are built from its tables
        self.carriers = []          # Carrier, in creation order (sim/spells.py); part of dump() only while non-empty
        self._next_carrier = 1
        self._next_group = 1
        self.ai_sleep = True        # server+0xbbe8 == 0: squads far from every human unit sleep (sim/ai/ `wake`, ai.md 15)
        self.ai_on = False          # sim/ai/ `enable`: the squads are in `ai_groups` and the state is part of dump()
        self.ai_groups = {}         # (owner, squad) -> AiGroup, in creation order
        self.ai_emitted = []        # AI commands since the last drain by `Simulation.step` (the log), not part of dump()
        self.unbuilt_casts = {}     # spell number -> releases whose effect handler is not built (sim/spells.py `stub_release`), not part of dump()
        self.script = None          # sim/triggers.py `Script` once `triggers.enable` compiled the map's section 7; dumped only then
        self.fog = None             # (h, w) uint16 tile words with the exe's fog bits (allods2.vision), None = no fog; sim/vision.py `enable`
        self.fog_viewer = 1         # the player whose units reveal cells (FUN_0041e860: only the viewer's own)
        self.fog_rev = 0            # bumped whenever the tile words change (overlay / minimap cache key), not dumped
        self.fog_cells = {}         # entity id -> (x, y) last revealed cell (`obj+0xc8/+0xcc`), not dumped
        self._fog_masks = {}        # (x, y, sight word) -> list of mask cells (allods2.vision.sight_mask), not dumped
        self._sight = {}            # (x, y, scan) -> frozenset of visible cells (the heights never change), not part of dump()
        self.report = BuildReport()
        self._cells = {}            # (x, y) -> set of ids over present footprint cells
        self._claim = {}            # (x, y) -> id of the structure registered there (first wins)
        self._ucells = {}           # (x, y) -> set of unit ids   (never part of the block layer)
        self._icells = {}           # (x, y) -> set of item ids
        self._next_seq = 1
        self.mission_complete = False  # message 0xb5 arrived (window message 0x430, sim/campaign.py); not dumped
        self.mission_ended = False      # client latch win+0x3e4: the result dialog / end of mission handled
        self.defeat_latch = False       # client latch win+0x3e8: the defeat dialog was opened once
        self.dialog = None              # sim/campaign.Dialog on screen, None otherwise
        self.slots = CellSlots()    # occupant and stamp slots of the cell records (simulation.md 7.4); not dumped
        self.cell_effects = {}      # (x, y) -> the record's 6-byte effect (spell, power, sx, sy, tx, ty): traps (sim/traps.py, which hooks `slots.on_enter`); dumped while non-empty
        self.transients = []        # the list server+0x2c: hidden casters (sim/traps.py), ticked in step 2; dumped while non-empty
        self.burn_start = {}        # (x, y) -> tick of the first Wall of Fire flag: the client's burning-cell list `view+0xa94` (client only, not dumped; lights.py)
        self.bolts = []             # `Bolt`s of the client (projectiles 28 / 30); client only, not dumped (sim/effects.py `bolt_system`)
        self.explosions = []        # `Explosion`s of the client (projectile 13); client only, not dumped (sim/effects.py `explosion_system`)
        self.burn_fx = {}           # (x, y) -> (tick, water): the fire explosion's burning-list entries (`SetAt` at age 4, view+0xa94); client only
        self.cell_fx = {}           # (x, y) -> [6 carrier uids or None]: the cell records' effect slots (effects.md 6.4); dumped while non-empty
        self._fx_saved = {}         # (x, y) -> the cost byte the record saved at creation
        self.costs = pas.DEFAULT_COSTS      # map.reg [Terrain] Cost<name> (from_map loads the install's)
        self.speed_multiplier = 8           # map.reg [Path Finding] SpeedMultiplier (CONFIRMED 8)
        self._cost = None
        self.block_rev = 0                  # bumped whenever a block cell is recomputed (path-grid cache key)
        self._base = pas.terrain_base(self.terrain)         # computed once
        self._block = self._base.copy()
        self._border()
        self._view = self._block.view()
        self._view.flags.writeable = False

    # --- views ---------------------------------------------------------------

    @property
    def cost(self):
        """(h, w) uint8 terrain movement cost (FUN_0055494d / FUN_0055a147), cached."""
        if self._cost is None:
            c = pas.cost_layer(self.terrain, self.costs)
            for (x, y), v in self.cell_fx.items():      # FUN_00550a96 over the effect cells of a rebuilt layer
                self._fx_saved[(x, y)] = int(c[y, x])
                c[y, x] = self._fx_cost(x, y, v)
            self._cost = c
        return self._cost

    _cost_owner = None              # the cost array set_cell_fx copied (and may write)

    WALL_SLOT = 3                   # FUN_00518ba3: Wall of Earth's slot of the cell record

    def _fx_cost(self, x, y, v):
        """FUN_00550a96: the saved cost byte `<<= 2` (u8) once per used effect slot."""
        b = self._fx_saved[(x, y)]
        for k in v:
            if k is not None:
                b = (b << 2) & 0xFF
        return b

    def set_cell_fx(self, x, y, slot, uid):
        """`FUN_0055a37a` (uid) / `FUN_0055a533` (None) on one slot of the cell record, then `FUN_00550a96`: the cost and the block of the cell are
        rebuilt; the record saved the cost at creation (`FUN_005508a0`) and restores it when it empties (`FUN_00550966`; effects.md 6.4)."""
        c = self.cost
        if self._cost_owner is not c:               # never write into an array another world or a test may share
            c = self._cost = self._cost_owner = np.array(c, np.uint8)
        v = self.cell_fx.get((x, y))
        if v is None:
            if uid is None:
                return
            v = self.cell_fx[(x, y)] = [None] * 6
            self._fx_saved[(x, y)] = int(c[y, x])
        v[slot] = uid
        if any(k is not None for k in v):
            c[y, x] = self._fx_cost(x, y, v)
        else:
            c[y, x] = self._fx_saved.pop((x, y))
            del self.cell_fx[(x, y)]
        self._refresh([(x, y)])
        if slot in (4, 5) and 0 <= x < self.width and 0 <= y < self.height:
            self.light_write(x, y, uid is not None, 0x50 if slot == 5 else 0)

    def light_write(self, x, y, on, value):
        """Client light flags 15 (Light, `value` 0) / 14 (Darkness, `value` 0x50), `FUN_0041c18c`: setting writes `value` into the terrain light of
        the cell's four vertices and nothing recomputes it (CONFIRMED); clearing calls `FUN_004a5dd2(x, y, 2, 2)`, which rebuilds the same four
        vertices from the heights (a neighbour's still-active write on a shared vertex is lost too).  `TerrainView._apply` (a full recompute) drops
        them all.  Client state: `light_vertices` {(vx, vy): value} and `light_version`."""
        for v in ((x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)):
            if on:
                self.light_vertices[v] = value
            else:
                self.light_vertices.pop(v, None)
        self.light_version += 1

    def scorch(self, x, y, burn=True):
        """Burnt ground: the client sets tile bit `0x2000` of a cell the first time a Wall of Fire flag (message 0x87, spell 3) reaches it and
        never clears it (`FUN_0041c18c` `0x41c44f`; drawn as `dirt.bmp`, ignored on water by the terrain draw).  Client state only: the block layer
        reads `terrain`, not `cells`."""
        if 0 <= x < self.width and 0 <= y < self.height and not self.cells[y, x] & 0x2000:
            self.cells[y, x] |= 0x2000
            self.cells_version += 1
            if burn:                                    # the Wall of Fire flag also queues the list entry; the explosion's age-8 pass only sets the bit
                self.burn_start = {c: t for c, t in self.burn_start.items() if self.tick - t < 22}      # drop the finished entries (BURN_TICKS)
                self.burn_start[(x, y)] = self.tick

    def set_costs(self, costs):
        """Install a terrain cost table (index = terrain type, `passability.costs_from_reg`)."""
        self.costs, self._cost = tuple(costs), None

    @property
    def block(self):
        """(h, w) uint8 block layer, read-only view."""
        return self._view

    def walkable(self, mover=1):
        """(h, w) bool: cells a mover of that movementType may enter."""
        return pas.walkable(self._block, mover)

    def blocked(self, x, y, mover=1):
        """True if the cell is blocked for `mover`; cells outside the map are."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            return True
        return bool(self._block[y, x] & pas.MOVE_MASK[mover])

    def objects_at(self, x, y):
        """Ids of the entities with a present footprint cell at (x, y)."""
        return frozenset(self._cells.get((x, y), ()))

    # --- block layer -----------------------------------------------------------

    def _border(self):
        b, n = pas.BORDER, self._block
        n[:b, :] = n[-b:, :] = n[:, :b] = n[:, -b:] = pas.B_BORDER

    def _cell_value(self, x, y):
        """Block value of one cell from base + index (spec "Block layer" 1-4)."""
        ids = self._cells.get((x, y), ())
        o = self.objects
        v = int(self._base[y, x])
        if any(o[i].kind == "object" for i in ids):
            v = pas.B_GROUND | pas.B_OBJECT
        b = pas.BORDER
        if x < b or y < b or x >= self.width - b or y >= self.height - b:
            v = pas.B_BORDER
        i = self._claim.get((x, y))
        if i is not None:
            ob = o[i]
            solid = next(s for dx, dy, s in ob.footprint if (ob.x + dx, ob.y + dy) == (x, y))
            v = v | _SOLID if solid else v & _CLEAR
        fx = self.cell_fx.get((x, y))
        if fx is not None and fx[self.WALL_SLOT] is not None:      # FUN_00550a96: a Wall of Earth slot blocks like an object (| 5)
            v |= pas.B_GROUND | pas.B_OBJECT
        return v

    def _refresh(self, cells):
        """Recompute exactly `cells` (local recompute, spec)."""
        self.block_rev += 1
        for x, y in cells:
            if 0 <= x < self.width and 0 <= y < self.height:
                self._block[y, x] = self._cell_value(x, y)

    def rebuild_block(self):
        """From-scratch block layer from base + entities, vectorised for objects
        (equals repeated `_refresh`, tested).  Returns a new array."""
        blk = self._base.copy()
        ys, xs = [], []
        for ob in self.objects.values():
            if ob.kind == "object":
                ys.append(ob.y)
                xs.append(ob.x)
        if xs:
            blk[ys, xs] = pas.B_GROUND | pas.B_OBJECT
        b = pas.BORDER
        blk[:b, :] = blk[-b:, :] = blk[:, :b] = blk[:, -b:] = pas.B_BORDER
        claim = {}
        for ob in sorted(self.objects.values(), key=lambda o: o.seq):
            if ob.kind != "object":
                self._register(ob, claim)
        for (x, y), i in claim.items():
            ob = self.objects[i]
            solid = next(s for dx, dy, s in ob.footprint if (ob.x + dx, ob.y + dy) == (x, y))
            blk[y, x] = blk[y, x] | _SOLID if solid else blk[y, x] & _CLEAR
        for (x, y), v in self.cell_fx.items():
            if v[self.WALL_SLOT] is not None:
                blk[y, x] |= pas.B_GROUND | pas.B_OBJECT
        return blk

    def _register(self, ob, claim):
        """FUN_005599df: claim the present cells in row-major order; the first
        cell already held by another structure ends the registration, the rest
        of this structure's cells stay unregistered (FUN_00559890 fails, the
        caller returns 0).  Cells outside the map are skipped."""
        for c in self._present(ob):
            if c in claim:
                break
            claim[c] = ob.id

    def _resolve(self, seed):
        """Re-run the registration for the connected group of structures that
        touch the cells `seed` (local: groups are independent), then refresh
        the cells concerned."""
        group, stack, cells = set(), list(seed), set(seed)
        while stack:
            for i in self._cells.get(stack.pop(), ()):
                if i not in group and self.objects[i].kind != "object":
                    group.add(i)
                    for c in self._present(self.objects[i]):
                        if c not in cells:
                            cells.add(c)
                            stack.append(c)
        for c in cells:
            self._claim.pop(c, None)
        for i in sorted(group, key=lambda i: self.objects[i].seq):
            self._register(self.objects[i], self._claim)
        self._refresh(cells)

    # --- entities ----------------------------------------------------------------

    def _present(self, ob):
        """Map cells of the object's footprint (outside cells dropped)."""
        out = []
        for dx, dy, _ in ob.footprint:
            x, y = ob.x + dx, ob.y + dy
            if 0 <= x < self.width and 0 <= y < self.height:
                out.append((x, y))
        return out

    def _check(self, ob):
        if ob.kind not in KINDS:
            raise ValueError("unknown kind %r" % (ob.kind,))
        if not (0 <= ob.x < self.width and 0 <= ob.y < self.height):
            raise ValueError("entity %#x at (%d, %d) is outside the map" % (ob.id, ob.x, ob.y))

    def _insert(self, ob, seq=None):
        if seq is None:
            seq, self._next_seq = self._next_seq, self._next_seq + 1
        ob.seq = seq
        self.objects[ob.id] = ob
        cells = self._present(ob)
        for c in cells:
            self._cells.setdefault(c, set()).add(ob.id)
        return cells

    def _detach(self, oid):
        ob = self.objects.pop(oid)
        cells = self._present(ob)
        for c in cells:
            s = self._cells[c]
            s.discard(oid)
            if not s:
                del self._cells[c]
        return ob, cells

    def add_object(self, ob):
        """Add an entity; returns its id.  ValueError (world unchanged) on a
        duplicate id or an anchor cell outside the map."""
        if ob.id in self.objects:
            raise ValueError("duplicate entity id %#x" % ob.id)
        self._check(ob)
        self._resolve(self._insert(ob))
        return ob.id

    def remove_object(self, oid):
        """Remove an entity (KeyError if absent) and recompute its cells."""
        if oid not in self.objects:
            raise KeyError(oid)
        _, cells = self._detach(oid)
        self._resolve(cells)

    def move_object(self, oid, x, y):
        """Remove + re-add at (x, y) with the same id and seq."""
        if oid not in self.objects:
            raise KeyError(oid)
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError("target (%d, %d) is outside the map" % (x, y))
        ob, old = self._detach(oid)
        ob.x, ob.y = x, y
        self._resolve(old + self._insert(ob, ob.seq))

    # --- units, items, players ------------------------------------------------------
    # Units and items are indexed per cell but never enter the block layer: the static block
    # layer is what the exe's path finder derives from terrain and objects (FUN_00554626,
    # FUN_00550a96).  The exe stamps occupancy of units in the same grid at run time
    # (FUN_0055be86, unit-struct.md 7.4); that dynamic blocking is simulation (phase H).

    def units_at(self, x, y):
        """Ids of the units whose cell is (x, y)."""
        return frozenset(self._ucells.get((x, y), ()))

    def items_at(self, x, y):
        """Ids of the ground piles on cell (x, y)."""
        return frozenset(self._icells.get((x, y), ()))

    def entities_at(self, x, y):
        """Ids of everything on a cell: footprint entities, units, ground piles."""
        return self.objects_at(x, y) | self.units_at(x, y) | self.items_at(x, y)

    def _index_add(self, index, ent):
        index.setdefault((ent.x, ent.y), set()).add(ent.id)

    def _index_del(self, index, ent):
        s = index[(ent.x, ent.y)]
        s.discard(ent.id)
        if not s:
            del index[(ent.x, ent.y)]

    def _check_cell(self, ent):
        if not (0 <= ent.x < self.width and 0 <= ent.y < self.height):
            raise ValueError("entity %#x at (%d, %d) is outside the map" % (ent.id, ent.x, ent.y))

    def add_unit(self, u):
        """Add a unit; ValueError (world unchanged) on a duplicate id or a cell outside the map."""
        if u.id in self.units or u.id in self.objects:
            raise ValueError("duplicate entity id %#x" % u.id)
        self._check_cell(u)
        u.seq, self._next_seq = self._next_seq, self._next_seq + 1
        self.units[u.id] = u
        self._index_add(self._ucells, u)
        self.slots.place(u)                                 # FUN_0055020a: occupant slots (first come) and the own stamp
        return u.id

    def next_carrier_id(self):
        n = self._next_carrier
        self._next_carrier += 1
        return n

    def find_unit(self, uid):
        """A unit by id, living or dead (the exe's object lookup: a ground corpse keeps its id until its death stage 5)."""
        u = self.units.get(uid)
        return u if u is not None else self.corpses.get(uid)

    def pile_blocked(self, x, y):
        """`FUN_005538c7`: a cell cannot hold a pile when it is outside the map or bit 0 of the live layer is set (water, mountain, building
        ground, structure stamps, the map border; trees (bit 2 only) and unit stamps do not count).  C§12.4."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            return True
        return bool(self._block[y, x] & 1)

    def place_pile(self, x, y, gold, codes, pile_id=None, sub=(128, 128), mods=(), **kw):
        """`FUN_0052ab07(cell, bag, gold)`: merge into the pile on the cell (even on a blocked cell), else register a new pile when the cell
        can hold one (`pile_blocked`); there is no search for a neighbouring cell.  Returns the pile, or None when the pile (gold and items) is
        deleted.  C§12.4."""
        codes = tuple(codes)
        mods = tuple(tuple(m) for m in mods) if mods else ()
        for i in sorted(self.items_at(x, y)):
            pile = self.items[i]
            pile.gold += gold
            if mods or pile.mods:
                pile.mods = tuple(pile.mods or ((),) * len(pile.codes)) + (mods or ((),) * len(codes))
            pile.codes = tuple(pile.codes) + codes
            return pile
        if self.pile_blocked(x, y):
            return None
        it = Item(self.new_pile_id() if pile_id is None else pile_id, x, y, sub[0], sub[1], gold, codes, mods=mods, **kw)
        it.net_id = self.net_ids.alloc()
        self.add_item(it)
        return it

    def new_pile_id(self):
        self._next_pile += 1
        return self._next_pile

    def bury(self, uid):
        """The release at state 0x10 (`FUN_0051618e`, `FUN_00553891`): out of the spatial index, the group and every selection.  A ground
        unit stays findable as a corpse (the object is never deleted); a flyer or ghost loses its id (combat.md 12.3)."""
        u = self.units[uid]
        self.remove_unit(uid)
        if u.move_type <= 1:
            self.corpses[uid] = u
        else:
            self.net_ids.free(u.net_id)         # `FUN_0052b459` 0x52bb87: a ghost or flyer (`+0x4a > 1`) frees its id at the removal
        return u

    def remove_unit(self, uid):
        u = self.units.pop(uid)
        self._index_del(self._ucells, u)
        self.release(u)
        g = self.groups.get(u.order_group)
        if g is not None and uid in g.members:
            g.members.remove(uid)
        for p in self.players.values():
            if uid in p.selection:
                p.selection = tuple(i for i in p.selection if i != uid)

    def selection_is_foreign(self, player_id):
        """True when the player's selection is a unit of another owner (info only)."""
        sel = self.players[player_id].selection
        return bool(sel) and self.units[sel[0]].owner != player_id

    def release(self, u):
        """`FUN_00553891`: the release of a unit leaving the world (removal, phase-out): `FUN_0055be86(unit, 0, 2)` (its stamps in the ring),
        then `FUN_00550697` (the occupant slots, whatever unit holds them)."""
        self.slots.be86(u, 0, 2)
        self.slots.lift(u)

    def move_unit(self, uid, x, y, sub_x=128, sub_y=128, crossing=False):
        """Put a unit on cell (x, y); the block layer is untouched.  A change of cell is the exe's sequence of `FUN_00554fd2` (0x555136): release
        the ring (`FUN_0055be86` mode 2), lift the occupant slots, move, place (`FUN_0055020a`, with the own stamp); `crossing` (a step border,
        not a teleport) then stamps the old cell again (`FUN_0055be86(unit, old cell, 0)`, held until the step end)."""
        u = self.units[uid]
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError("target (%d, %d) is outside the map" % (x, y))
        self._index_del(self._ucells, u)
        if (u.x, u.y) != (x, y):
            old = pack(u.x, u.y)
            self.release(u)
            u.x, u.y, u.sub_x, u.sub_y = x, y, sub_x, sub_y
            self.slots.place(u)
            if crossing:
                self.slots.be86(u, old, 0)
        else:
            u.sub_x, u.sub_y = sub_x, sub_y
        self._index_add(self._ucells, u)

    def add_item(self, it):
        if it.id in self.items:
            raise ValueError("duplicate item id %#x" % it.id)
        self._check_cell(it)
        it.seq, self._next_seq = self._next_seq, self._next_seq + 1
        self.items[it.id] = it
        self._index_add(self._icells, it)
        return it.id

    def remove_item(self, iid):
        it = self.items.pop(iid)
        self._index_del(self._icells, it)
        self.net_ids.free(it.net_id)            # the pile's destructor `FUN_0052a7fc` -> `FUN_004f8d3d`

    # --- loading -------------------------------------------------------------------

    @classmethod
    def from_map(cls, m, assets, facing=None, seed=DEFAULT_SEED, difficulty=DEFAULT_DIFFICULTY):
        """From an `allods2.formats.Map` and an `AssetCache` (spec "World").
        Structures first in record order, then section 3 cells row-major;
        bulk-added, then one full block build; then players, units and ground piles in
        record order.  `facing`: None gives each unit the exe's start angle 0x40 + [0, 128)
        (the exe's rand, here a fixed hash of the uid so a map always loads the same);
        an int puts every unit at that angle byte (0x80 = front view, as `map render`).
        `difficulty`: the game option `[0x6044c4+0xd8]` (1 easy, 2 normal = the ctor default of `0x4e97bf`, 3 hard); see `_load_units`."""
        w = cls(m.runtime_terrain(), m.heights_i8, m.name, terrain=m.terrain, seed=seed)
        if hasattr(assets, "map_reg"):                  # test doubles keep the defaults
            costs, w.speed_multiplier = assets.map_reg()
            w.set_costs(costs)
        if hasattr(assets, "items"):
            w.item_table = assets.items()
        if hasattr(assets, "spells"):
            w.spell_table = assets.spells()
        w.assets = assets
        stats = assets.databin().structures
        reg = assets.objects_reg()
        rep = w.report

        def count(kind, tid):
            rep.counts[(kind, tid)] = rep.counts.get((kind, tid), 0) + 1

        for s in m.structures:
            fp, known, hp_max = structure_footprint(s, stats)
            kind = "bridge" if s.is_bridge else "structure"
            ob = MapObject(STRUCTURE_ID_BASE + s.uid, kind, s.type, s.x, s.y, owner=s.owner,
                           hp=hp_max if s.intact else 0, hp_max=hp_max,
                           flags=0 if s.intact else FLAG_DESTROYED, uid=s.uid, footprint=fp,
                           known=known, size=s.size,
                           indestructible=known and 1 <= s.type <= len(stats) and not stats[s.type - 1].params[3],
                           sight=(stats[s.type - 1].params[2] << 8) if known and s.size is None and 1 <= s.type <= len(stats) else 0)
            if ob.id in w.objects:
                raise ValueError("duplicate structure id %#x (uid %d)" % (ob.id, s.uid))
            w._check(ob)
            w._insert(ob)
            count(kind, s.type)
            if not known:
                rep.unknown.append((kind, s.type, s.x, s.y))
        placed = m.placed_objects()
        for n, p in enumerate(placed):
            known = p.id in reg
            w._insert(MapObject(OBJECT_ID_BASE + n, "object", p.id, p.x, p.y, known=known))
            count("object", p.id)
            if not known:
                rep.unknown.append(("object", p.id, p.x, p.y))
        rep.ignored_outside_window = int(np.count_nonzero(m.objects)) - len(placed)
        w._resolve(list(w._cells))
        w._load_players(m)
        w._load_units(m, assets, facing, difficulty)
        w._load_items(m)
        return w

    def _load_players(self, m):
        for p in m.players:
            self.players[p.index] = Player(p.index, p.colour, p.name, p.flags, p.money,
                                           tuple(p.relations), human=p.index == 1)

    def _load_units(self, m, assets, facing, difficulty=DEFAULT_DIFFICULTY):
        """Section 6 in record order.  Unknown types (no units.reg set or no data.bin record)
        are kept with `known=False` and listed in `report.unknown_units`; an owner that is not
        a section 5 record is an error (the exe logs "Can't resolve player" and skips the unit,
        never the case in the 46 maps).

        Difficulty tweak (`FUN_00561bf9` 0x561e20-0x561f0b, CONFIRMED; ai.md section 10): for every unit whose record flag 0x10 is clear
        (monsters), only when the mode is not 2 and the map is a single-player map (`field_84 <= 1`, settings `+0x74 == 0`):
        mode 1: template max HP = trunc(x 0.5), the wimpy threshold `>>= 1`; any other mode (3): to-hit and defence +50, max HP =
        trunc(x 1.5).  It acts on the template value, so a map HP override is not scaled."""
        types = assets.unit_stats()
        tweak_on = difficulty != 2 and getattr(m, "field_84", 1) <= 1
        rep = self.report
        for rec in m.units:
            if rec.owner not in self.players:
                raise ValueError("unit uid %d: owner %d is not a player" % (rec.uid, rec.owner))
            tpl = types.lookup(rec.is_human, rec.server_id)
            hp, hp_max = rec.hp, rec.max_hp
            if rec.is_human and hp_max != fent.NO_HP and hp_max == hp:
                hp = hp_max = fent.NO_HP                    # FUN_00561bf9 0x562013: a human at full HP = default = the recomputed maximum
            base = tpl.hp_max if tpl is not None else 0     # map overrides replace the template value
            tweak = 0
            if tweak_on and not rec.is_human:
                tweak = 1 if difficulty == 1 else 3
                base = int(base * (0.5 if tweak == 1 else 1.5))     # fild * 0x5d1b00 / 0x5d1b08, ftol truncates
            mana_max = 0
            if rec.is_human and tpl is not None:            # FUN_0051366b: a human never uses the template healthMax
                base, mana_max = prog.derived_vitals(tpl)
            face = tpl.face if tpl is not None else 1
            move = tpl.movement_type if tpl is not None else 1
            hp_max = base if hp_max == fent.NO_HP else hp_max
            hp = hp_max if hp == fent.NO_HP else hp
            known = tpl is not None and assets.unit_set(rec.type) is not None
            u = Unit(UNIT_ID_BASE + rec.uid, rec.type, rec.owner, rec.x >> 8, rec.y >> 8,
                     rec.x & 255, rec.y & 255, unit_angle(rec.uid, facing), IDLE, 0, hp, hp_max,
                     rec.uid, rec.server_id, rec.is_human, rec.behaviour, move, face, rec.squad, rec.group, known,
                     stats=tpl)
            u.tweak = tweak
            if tpl is not None and not rec.is_human:
                u.mover.turn_rate = max(1, tpl.turn_rate)       # mover+0xa: monster p9; humans: the speed stat (sim/movement.py)
                if (tpl.get("mana_max", -1) or 0) > 0:          # FUN_005114f3 0x511586-0x5115a5: +0x9c := manaMax, +0x9a := +0x9c (ai.md 12.1);
                    u.mana = u.mana_max = tpl.mana_max          # -1 / 0 (every non-mage) stay 0 here: nothing reads a non-mage's mana
            if rec.is_human and tpl is not None:        # docs/data/progression.md section 4: no award logic yet
                u.skills = prog.skills_of(tpl)
                u.mana = u.mana_max = mana_max
                u.xp, u.xp_total = prog.start_pools(u.skills)
                u.best_school = prog.best_school(u.skills) if prog.is_hero_name(tpl.name) else 0
                pl = self.players.get(rec.owner)
                if pl is not None and pl.human and pl.main_hero == 0 and prog.is_hero_name(tpl.name):
                    pl.main_hero = u.id                 # INFERRED: the exe's owner+0x38 writer is not traced
            if 0 < rec.group <= len(m.item_groups):         # the carried pack (section 8): dropped at death
                members = m.item_groups[rec.group - 1].members
                u.carried = tuple(mem.code & 0xFFFF for mem in members)
                mods = tuple(self._member_mods(m, mem) for mem in members)      # the section 9 records: the objects keep their effects
                if any(mods):
                    u.carried_mods = mods
            self.add_unit(u)
            if not known:
                rep.unknown_units.append((rec.uid, rec.type, rec.server_id, u.x, u.y))
        rep.units_sharing_cell = sum(1 for s in self._ucells.values() if len(s) > 1)
        rep.units_on_blocked = sum(1 for u in self.units.values()
                                   if self.blocked(u.x, u.y, u.move_type if u.move_type in pas.MOVE_MASK else 1))

    def _member_mods(self, m, mem):
        """The modifier records `(kind, a, b)` of a section 8 member: its section 9 record's pairs and the `c` field (castSpell / teachSpell) as effects
        (`FUN_00564072`, items.md 5: `ItemTable.pair_effects`), or () for a member without a record or an unknown code."""
        table = self.item_table
        if table is None or not mem.record or mem.record > len(m.item_records):
            return ()
        rec = m.item_records[mem.record - 1]
        ic = fent.decode_item(mem.code)
        d = table.lookup(ic) if ic is not None else None
        if d is None or not rec.props and not rec.c:
            return ()
        return mods_from_effects(table.pair_effects(rec.props, rec.c & 0xFFFF, rec.c >> 16, book=d.kind == "special" and d.subtype == 5))

    def _load_items(self, m):
        """Ground piles: the section 8 groups no unit's `group` points at (`Map.ground_groups`).
        Groups on one cell merge into one pile, gold added and items stacked (`FUN_0052ab07`,
        CONFIRMED map.md part 5); the pile takes the id of its first group,
        `ITEM_ID_BASE + group index` (0-based, file order); a blocked cell (`pile_blocked`) loses the pile, as in the exe (no install map has one)."""
        used = {u.group for u in m.units if u.group}
        at = {}
        for n, g in enumerate(m.item_groups):
            if n + 1 in used:
                continue
            cell = (g.x >> 8, g.y >> 8)
            codes = tuple(mem.code & 0xFFFF for mem in g.members)
            mods = tuple(self._member_mods(m, mem) for mem in g.members)
            if cell in at:
                it = at[cell]
                it.gold += g.extra
                if any(mods) or it.mods:
                    it.mods = tuple(it.mods or ((),) * len(it.codes)) + mods
                it.codes += codes
                it.groups += (n,)
                continue
            if self.pile_blocked(*cell):        # same routine as the death drop (`FUN_0052ab07`): a cell that cannot hold a pile deletes it
                continue
            at[cell] = Item(ITEM_ID_BASE + n, cell[0], cell[1], g.x & 255, g.y & 255, g.extra, codes,
                            groups=(n,), mods=mods if any(mods) else ())
            at[cell].net_id = self.net_ids.alloc()
            self.add_item(at[cell])

    # --- consistency ---------------------------------------------------------------

    def check_consistency(self):
        """Internal invariants of the indexes and of the movement state; returns a list of problem strings (empty =
        consistent).  Checked: the per-cell unit/item index equals the entities' cells, every position is inside the
        map with a sub-cell byte, a step in progress holds a reservation (`step_target`, adjacent to `step_from`,
        the unit standing on one of the two: the live layer is derived from exactly these), groups and selections
        refer to living entries, a unit is in at most the one group it names."""
        bad = []
        for name, table, index in (("unit", self.units, self._ucells), ("item", self.items, self._icells)):
            want = {}
            for e in table.values():
                want.setdefault((e.x, e.y), set()).add(e.id)
                if not (0 <= e.x < self.width and 0 <= e.y < self.height):
                    bad.append("%s %#x outside the map at (%d, %d)" % (name, e.id, e.x, e.y))
            if want != index:
                bad.append("%s index differs from the entities' cells" % name)
        for u in self.units.values():
            m = u.mover
            if not (0 <= u.sub_x < 256 and 0 <= u.sub_y < 256):
                bad.append("unit %#x sub-cell (%d, %d)" % (u.id, u.sub_x, u.sub_y))
            if bool(m.step_ticks) != (m.step_target is not None):
                bad.append("unit %#x: step_ticks %d but step_target %s" % (u.id, m.step_ticks, m.step_target))
            if m.step_target is not None:
                t, f = tuple(m.step_target), tuple(m.step_from) if m.step_from else None
                if f is None or max(abs(t[0] - f[0]), abs(t[1] - f[1])) != 1:
                    bad.append("unit %#x: step %s -> %s is not one cell" % (u.id, f, t))
                elif (u.x, u.y) not in (t, f):
                    bad.append("unit %#x at (%d, %d) is on neither end of its step %s -> %s" % (u.id, u.x, u.y, f, t))
                if not (0 <= t[0] < self.width and 0 <= t[1] < self.height):
                    bad.append("unit %#x reserves %s outside the map" % (u.id, t))
            if u.order_group:
                g = self.groups.get(u.order_group)
                if g is None or u.id not in g.members:
                    bad.append("unit %#x names group %d which does not list it" % (u.id, u.order_group))
        for h in self.slots.holders():
            if h not in self.units:
                bad.append("a cell record slot is held by missing unit %#x" % h)
        seen = {}
        for g in self.groups.values():
            for i in g.members:
                if i not in self.units:
                    bad.append("group %d lists missing unit %#x" % (g.id, i))
                elif self.units[i].order_group != g.id:
                    bad.append("group %d lists unit %#x which names group %d" % (g.id, i, self.units[i].order_group))
                if i in seen:
                    bad.append("unit %#x is in groups %d and %d" % (i, seen[i], g.id))
                seen[i] = g.id
        for p in self.players.values():
            for i in p.selection:
                if i not in self.units:
                    bad.append("player %d selects missing unit %#x" % (p.id, i))
        return bad

    # --- dump ----------------------------------------------------------------------

    def dump(self):
        """Deterministic plain-int dict of the world (spec "CLI" world-dump)."""
        objs = []
        for i in sorted(self.objects):
            o = self.objects[i]
            objs.append({"id": o.id, "kind": o.kind, "type_id": o.type_id, "x": o.x, "y": o.y,
                         "sub_x": o.sub_x, "sub_y": o.sub_y, "variant": o.variant,
                         "owner": o.owner, "hp": o.hp, "hp_max": o.hp_max, "flags": o.flags,
                         "uid": o.uid, "known": int(o.known),
                         "footprint": [[dx, dy, int(s)] for dx, dy, s in o.footprint]})
        r = self.report
        return {"name": self.name, "width": self.width, "height": self.height,
                "report": {"unknown": [list(u) for u in r.unknown],
                           "unknown_units": [list(u) for u in r.unknown_units],
                           "units_on_blocked": r.units_on_blocked,
                           "units_sharing_cell": r.units_sharing_cell,
                           "ignored_outside_window": r.ignored_outside_window,
                           "counts": {"%s:%d" % k: v for k, v in sorted(r.counts.items())}},
                "objects": objs,
                "players": [[p.id, p.colour, p.name, p.flags, p.money, list(p.relations), int(p.human)]
                            + self._player_extra(p)
                            for _, p in sorted(self.players.items())],
                "units": [[u.id, u.type_id, u.owner, u.x, u.y, u.sub_x, u.sub_y, u.facing, u.action,
                           u.action_start_tick, u.hp, u.hp_max, u.uid, u.server_id, int(u.human),
                           u.behaviour, u.move_type, u.face, u.squad, u.group, int(u.known)]
                          + self._mover_dump(u)
                          for _, u in sorted(self.units.items())],
                "items": [[i.id, i.x, i.y, i.sub_x, i.sub_y, i.gold, list(i.codes), list(i.groups)]
                          for _, i in sorted(self.items.items())],
                "block": [bytes(row).hex() for row in self._block],
                **({"groups": [[g.id, g.owner, list(g.members), g.order, list(g.target), g.speed] + g.ai_dump()
                               for g in self.groups.values()]} if self.groups else {}),
                **({"corpses": [[u.id, u.x, u.y, u.sub_x, u.sub_y, u.facing, u.hp, u.type_id, u.owner, u.death_tick]
                                for _, u in sorted(self.corpses.items())]} if self.corpses else {}),
                **({"carriers": [[c.uid, c.kind, c.caster, c.target, c.spell, c.level, c.ticks_left, c.born, int(c.hostile), list(c.start), c.flight, list(c.aim)]
                                  + c.area_dump() for c in self.carriers]} if self.carriers else {}),
                **({"cell_fx": [[x, y, list(v)] for (x, y), v in sorted(self.cell_fx.items())]} if self.cell_fx else {}),
                **({"cell_effects": [[x, y, list(v)] for (x, y), v in sorted(self.cell_effects.items())]} if self.cell_effects else {}),
                **({"transients": [[c.x, c.y, c.state, c.cast.spell if c.cast else None, c.cast.target if c.cast else None,
                                    list(c.cast.cell) if c.cast and c.cast.cell else None, c.stats.get("spell_power"), c.phase, c.timer, int(c.done)]
                                   for c in self.transients]} if self.transients else {}),
                **({"thresholds": [[u.id, u.wimpy_hp, u.withdraw_hp] for _, u in sorted(self.units.items()) if u.wimpy_hp is not None]}
                   if any(u.wimpy_hp is not None for u in self.units.values()) else {}),
                **({"ai": self._ai_dump()} if self.ai_on else {}),
                **({"fog": int(zlib.crc32(self.fog.tobytes()))} if self.fog is not None else {}),
                **({"script": self.script.dump()} if self.script is not None else {}),
                **({"rng": self.rng.state} if self.rng.state != self.seed else {})}

    def _ai_dump(self):
        """AI state: the squads and the per-unit Brain fields, only once the AI is enabled (old goldens stay valid)."""
        return {"groups": [g.dump() for g in self.ai_groups.values()],
                "units": [[u.id, u.mode_look] + u.ai.dump() for _, u in sorted(self.units.items())
                          if u.ai != AiState() or u.mode_look]}

    @staticmethod
    def _player_extra(p):
        """Optional trailing dict of a player entry: only non-default state (old goldens stay valid)."""
        d = {}
        if p.selection:
            d["selection"] = list(p.selection)
        if p.formation != 1:
            d["formation"] = p.formation
        if p.autocast:
            d["autocast"] = p.autocast
        if p.hero_deaths or p.death_code or p.defeat_dialog:        # main_hero is derived at load, not dumped
            d["hero"] = [p.hero_deaths, p.death_code, int(p.defeat_dialog)]
        return [d] if d else []

    @staticmethod
    def _mover_dump(u):
        """Movement state, only for a unit that has any (idle units keep the short entry)."""
        m = u.mover
        fight = World._fight_state(u)
        death = World._death_state(u)
        cast = World._cast_state(u)
        if fight is None and death is None and cast is None and World._follow_state(u) is None and not u.master and not u.auto_spell and not u.teleport_to and not (u.order or u.state or u.path or u.odometer or m.steps or m.turning or u.order_group
                                  or u.stopped or m.waiting or m.parked or m.target_facing != u.facing
                                  or u.effects or u.effect_mask or u.fx.any() or u.equipment or u.pack or u.order == 2):
            return []
        d = {"order": u.order, "state": u.state, "path": [list(c) for c in u.path],
             "odometer": u.odometer, "target_facing": m.target_facing,
             "step": [list(m.step_target) if m.step_target else None, m.steps, m.step_ticks,
                      m.step_len, m.step_dir, m.dx, m.dy],
             "turn": [int(m.turning), m.turn_ticks, m.turn_done]}
        if m.goal is not None or m.dest is not None or m.static_path:      # only planned orders
            d["plan"] = [list(m.goal) if m.goal else None, list(m.dest) if m.dest else None,
                         list(m.tail) if m.tail else None, m.consumed, m.since_hop, int(m.arrived),
                         int(m.failed), [list(c) for c in m.static_path]]
        if m.waiting or m.parked:                                           # only after a blocker wait
            d["wait"] = [int(m.waiting), int(m.parked)]
        if u.order_group or u.stopped or u.anchor:                          # only after a player command
            d["cmd"] = [u.order_group, int(u.stopped), list(u.anchor) if u.anchor else None]
        if u.hidden:                                                        # only under an Invisibility effect
            d["hidden"] = 1
        if u.mode_go and u.order != 1:                                      # a restarted unit under the stand order
            d["mode"] = 1
        if fight is not None:
            d["fight"] = fight
        if death is not None:
            d["death"] = death
        if cast is not None:
            d["cast"] = cast
        follow = World._follow_state(u)
        if follow is not None:
            d["follow"] = follow
        if u.master:
            d["master"] = u.master
        if u.equipment or u.pack:                                           # only a hero with a loadout (sim/gear.py)
            d["gear"] = [[[it.code, it.count, [list(r) for r in it.mods]] for it in u.equipment],
                         [[it.code, it.count, [list(r) for r in it.mods]] for it in u.pack], u.pack_index]
        if u.auto_spell:
            d["auto_spell"] = u.auto_spell
        if u.teleport_to:                                                   # only while a Teleport cell record's target is pending
            d["teleport_to"] = u.teleport_to
        if u.effects or u.effect_mask or u.fx.any():                       # only under a spell effect (sim/effects.py)
            d["effects"] = [[e.dump() for e in u.effects], u.effect_mask, u.fx.dump()]
        return [d]

    @staticmethod
    def _follow_state(u):
        """Follow / patrol state as a list, None while the unit never had such an order (old goldens stay valid)."""
        if u.leader is None and not u.mode_follow and u.follow_target is None and not u.patrol and u.patrol_wp is None and not u.patrol_walk:
            return None
        return [u.leader, u.follow_range, int(u.mode_follow), u.follow_target, [list(c) for c in u.patrol],
                list(u.patrol_wp) if u.patrol_wp else None, int(u.patrol_walk)]

    @staticmethod
    def _death_state(u):
        """Death, regeneration and XP state as a list, None while all of it is at its start value (old goldens stay valid)."""
        if not (u.death_seen or u.hp_acc or u.mana_acc or u.kill_list or u.mana != u.mana_max
                or u.state == DEAD):
            return None
        return [int(u.death_seen), u.death_tick, u.step_end, u.hp_acc, u.mana_acc, u.mana, list(u.skills),
                list(u.xp), u.xp_total, [list(k) for k in u.kill_list]]

    @staticmethod
    def _cast_state(u):
        """Spell-cast state as a list, None while the unit never cast or got a cast order (old goldens stay valid)."""
        c, w = u.cast, u.cast_wrapper
        if (c is None and w is None and not u.mode_cast and u.cast_target is None and u.spellbook is None and not u.ai_cast and not u.mode_cell
                and u.cast_cell is None):
            return None
        d = [int(u.mode_cast), u.cast_target, [w.number, w.item_count] if w is not None else None,
             [c.spell, c.target, list(c.cell) if c.cell else None, c.item_count] if c is not None else None, u.spellbook]
        if u.ai_cast or u.mode_cell or u.cast_cell is not None:          # AI / cell casts only: the I4 goldens keep their layout
            d += [int(u.ai_cast), int(u.mode_cell), list(u.cast_cell) if u.cast_cell else None]
        return d

    @staticmethod
    def _fight_state(u):
        """Fight state as a dict, None for a unit that never fought (old goldens stay valid)."""
        m = u.mover
        if (u.target is None and not u.mode_attack and not u.brain_order and not u.phase and u.done and not u.timer
                and not u.swing_count and u.last_attacker is None and u.swing_target is None and m.follow is None
                and m.follow_cell is None):
            return None
        return {"target": u.target, "mode": int(u.mode_attack), "range": u.range, "brain": u.brain_order,
                "count": u.swing_count, "phase": u.phase, "timer": u.timer, "done": int(u.done),
                "swing": u.swing_target, "by": u.last_attacker,
                "follow": [m.follow, list(m.follow_cell) if m.follow_cell else None, m.static_len]}

    def dump_json(self):
        return json.dumps(self.dump(), sort_keys=True, separators=(",", ":"))

    def dump_hash(self):
        return hashlib.sha256(self.dump_json().encode("ascii")).hexdigest()
