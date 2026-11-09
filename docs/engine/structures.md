# Using structures (switches, wells, signposts, altars, graves)

How the hero uses a structure, what each usable class does, and what the scripts see. Tags: CONFIRMED = read in the GOG
`allods2.exe` (sha256 in [formats/README](../formats/README.md)) at the routine / address given; INFERRED = code shape, data pattern or
analogy. Server object `DAT_0066832c`; creature = server unit ([unit-struct](unit-struct.md)); structure = server building (`+0xe` type
word, `+0x40` type byte, `+0x42` s16 HP, `+0x44` max HP, `+0x10` position object, `+0x14` owner, `+0x60/+0x61` footprint W/H,
`+0x6c` signpost instant). Commands: [click-to-move-research](click-to-move-research.md); script side: [triggers](triggers.md).
Everything in this file is single player.

## 0. Status per class (K6 + K8, `engine/sim/structures.py`)

| Class (IDs) | Server effect | Status | Engine | Tests |
|---|---|---|---|---|
| Switches 1 / 2 (28, 29), Altars 1 / 2 (76, 77) | HP 0 <-> 1, message `0x82`; art follows `hp < 1` | CONFIRMED `0x50f9d4`-`0x50fa1c` | `USE_A` -> `toggle` | `test_engine_structures*.py` |
| Wells (15 health, 16 mana) | lookup B: charge `-1` (3 per well), message `0x82`, potion drunk (+100 capped) | CONFIRMED `0x50fa2f`-`0x50fc09`, `FUN_00522fab`, `FUN_00523613` | `WELLS` -> `use_well` | `test_engine_structures_k8.py` |
| Usable Pointers / signposts (70-75) | instant `+0x6c` when `> 0` at every use, then the case ends (lookup B skipped) | CONFIRMED `0x50f944` | `run_pointer`, `World.pointers` (built in `triggers.enable` from section 11 list C) | same |
| King's Graves (39, 40) | none (the walk and the stop) | CONFIRMED (no code tests the types) | no handler | same |
| Shops / inns (multiplayer ids) | messages `0x83` / `0x84`, the case ends | CONFIRMED, out of scope | `SHOP_INN_TYPES` ends the case, no message | - |
| "Saving Place" (66) | client save UI | INFERRED, no campaign map has it | not built | - |

**Feedback (CONFIRMED by reading `FUN_0050f12c`, `FUN_00503672`, `FUN_00523613`, `FUN_0040d9b2` case `0x82`).** The server sends exactly one message for
a use: `0x82` (structure id and its `+0x42` word) from a toggle or a well charge; the client only stores the word. There is **no sound, no text line
and no animation** for a switch, altar, well, grave or the potion (the item use sends nothing; the attribute check `FUN_004e9e97` is not reached for
health / mana). The only text is a signpost's script instant (`Send message`, a story window). So K8 logs **no sound event**: the engine emits the
`StructureState` event (`World.events`, not hashed) for message `0x82` and nothing else. The Sound step has nothing to add for structure uses.

**Real maps (`tests/test_engine_structures_k8.py`, `ALLODS2_ALL_MAPS=1` for all 33):** per structure type, the maps that contain it (map data):
Well 2 (15): 30, 40, 52 (2), 63, 73 (2), 75 (2), 83, 100; Well 3 (16): 40 (2), 53, 60, 62, 63, 73 (2), 74, 75, 77 (2), 83, 86, 87; signposts (live = the
runtime instant index `> 0`): 10, 20 (3), 21 (3), 30, 40 (3), 50; map 76's signpost is not live (index 0, the quirk); graves: 30, 31, 42, 43, 53, 70, 73, 75, 77,
92, 102, 110. The test uses every well, grave and signpost of those maps from a neighbour cell: the expectation follows the exe's lookup (map 40's uid 4
well is captured by uid 2, the first structure within 2 of the stop cell, and gives nothing).

## 1. Which structures are usable (CONFIRMED data, `structures.reg`)

The client decides with the `Usable` flag (record `+0x8c`, [animation §1](../formats/animation.md)): hover flag `0x800` (`FUN_004180c6`,
[ui-layout §6](ui-layout.md)) -> cursor `town` when exactly one hero is selected. **The server knows no "usable" flag**: command `0x24`
is accepted for any structure; what happens is decided at the tick by the type id and the C++ class (§3). So a structure is useful only
if the §3 code knows it; every other `Usable` record (graves) just makes a walk-to-and-stop.

data.bin params `[W, H, p2, healthMax, Passability, BuildingPresent]` (`healthMax` = server max HP `+0x44`, HP starts at it, or 0 when the
map entry's `intact` is 0: `FUN_00561422` `0x5615..`, ctor `0x51fd8c` / `0x51ff33`). Counts are campaign maps (the 46 `.alm`; multiplayer
shops, inns and the church type 66 occur on none).

| ID | Editor name | Class (server) | W x H | healthMax | Frames (W·FH + destroyed) | Maps (count) |
|---|---|---|---|---|---|---|
| 15 | Well 2 | normal building, type byte `0xf` | 2x2 | 3 | Indestructible: never "destroyed" art | 30, 40, 52 (2), 63, 73 (2), 75 (2), 83, 100 |
| 16 | Well 3 | same, type byte `0x10` | 3x3 | 3 | same | 40 (2), 53, 60, 62, 63, 73 (2), 74, 75, 77 (2), 83, 86, 87 |
| 28, 29 | Switch 1, 2 | normal building, type `0x1c` / `0x1d` | 1x1 | 1 | 2 intact + 2 destroyed | 75, 93, 94, 95, 96 (1+1 each), 103 (8+8) |
| 76, 77 | Usable Altar 1, 2 | normal building, type `0x4c` / `0x4d` | 2x2 | 1 | 4 + 3 phases + 4 destroyed | 53, 62, 76, 80, 86 |
| 39, 40 | King's Grave 1, 2 | normal building | 2x2 | 0 (indestructible) | - | 30, 31, 42, 43, 53, 70, 73, 75, 77, 92, 102, 110 |
| 70-75 | Usable Pointer 1-6 (signposts) | class "Pointer" `FUN_005672c0` | 1x1 | - | - | 10, 20, 21, 30, 40, 50, 76 |
| 34, 35, 93-95, 105-107 | Multiplayer ... Shop | shop class `FUN_00520ee6` | - | - | - | none |
| 67-69, 99-101, 111-113 | Multiplayer ... Inn | inn class `FUN_0052f635` | - | - | - | none |
| 66 | Saving Place (data name "Multiplayer Church") | normal building | 4x3 | - | - | none |

Class by type: `FUN_00561422` picks the constructor by the map entry's type: shops `0x22 0x23 0x5d-0x5f 0x69-0x6b`, inns `0x43-0x45 0x63-0x65
0x6f-0x71`, Pointer `0x46-0x4b` (IDs 70-75), everything else the normal structure (CONFIRMED). Altars `0x4c / 0x4d` therefore get **no
signpost record** (map.md part 6) but do toggle (§3).

## 2. Use command and order

| Step | Fact | Routine |
|---|---|---|
| hover | structure not (Usable and Indestructible)-skipped; flags `0x20` (+ `0x800` when Usable); cursor `town` needs one selected hero-type unit; click sends the command | `FUN_004180c6`, chooser `FUN_0040b2b8` (CONFIRMED, ui-layout) |
| client send | `FUN_0041a0b5(structure id)`: command byte `0x24`, `+0xe` = the hovered structure's runtime id (`0x6000 + uid`), then the selected unit ids; then the squad voice | `0x41a0b5` (CONFIRMED) |
| server intake | `FUN_004f515d` (head `0x4f51a2`-`0x4f5292`, case `0x24` at `0x4f563f`), shared by all unit commands: the first id must resolve (`FUN_004f3a19` = player `FUN_004f3ba9` + unit `FUN_004f3a52`: the unit id must be in that player's table and **its state `+0x54` must not be `0x10`**, i.e. removed; dying units with state != `0x10`, non-heroes and summons resolve); an unresolved first id drops the whole command. A new group (`FUN_0052b06f`) takes the first unit and every later id that resolves (`FUN_0052af8c`; unresolved ids are skipped silently, no log), each joined unit gets `FUN_00510745` (cancels a pending spell). **The unit local is overwritten by every lookup, a null result included**, so case `0x24` passes the unit of the LAST id: structure by id (`FUN_0052bfa3` over the building list `[0x6044c4+0x7c]`; unknown id logs and drops); else `FUN_0056d22b(last unit, structure)`. Earlier units only join the (order-less) group and are not otherwise touched (no order, no cancel beyond the spell). If the last id does not resolve, `FUN_0056d22b(NULL)` dereferences `+0x1c4` of null (INFERRED crash; the client cannot send it). **No test of class, owner, hero, level, distance, items or money** | CONFIRMED |
| client: several units | The sender `FUN_0041a0b5` (called by the left-release dispatcher `FUN_004175c7` on the `town` cursor) puts **every selected unit id** (selection list `FUN_00420140` iteration, per-object selected flag `+0x80`) after the structure id; but the chooser tests (`0x40b6a4`-`0x40b739`: view `+0x140 == 1` selected unit and that unit's `+0x1b8 & 1` hero flag, hover `0x800`) give the `town` cursor only for **one selected hero**, so the message carries one id. With 2+ units selected the cursor is not `town`, no `0x24` is sent (the click selects / attacks instead). The last-id rule is therefore unreachable from the GOG UI; the engine's `sel[-1:]` and `intake` (last member) match | `0x41a0b5`, `0x4175c7`, `0x40b2b8` (CONFIRMED) |
| order | `FUN_0056d22b`: `FUN_0056dbfb` (cancel: state 0, facing), **unit order `+0x50 = 0xf`**, brain `+0x68 = structure`, brain mode `+8 = 0`, destination `brain+0xa` = the structure's `+0x10` cell word, then by the footprint width `W = structure+0x60`: W 1-2: dist 1, dest unchanged; W 3-4: dist 2, dest `+(1,1)`; W >= 5: dist 3, dest `+(2,2)` (`brain+0x14` = dist). Only caller: `0x4f5663` (player command). The AI never uses structures | `0x56d22b` (CONFIRMED) |
| group pass | order `0xf` is re-armed by the group executor (`FUN_00569321` case -> `FUN_0056af23`: brain mode `0xf`, `+0x68`) | `0x56af23` (CONFIRMED) |
| executor | brain mode 15 = `FUN_0056ecbc`, run every tick while brain order `+9 == 0` (jump table `0x56e470`): `FUN_0055539a(unit, brain+0xa, brain+0x14)` = **facing equals the facing to the destination cell** (`FUN_00556b2c`) **and Chebyshev(unit cell, dest) <= dist** (`FUN_00558fe9`). True: state `+0x54 = 0xf` (first tick) or, when the state already is `0xf`, `FUN_0056dbc6` (stop). False: walk / turn with `FUN_0056e4ac` (`FUN_00555411(unit, dest, dist)`, state 1) | `0x56ecbc` (CONFIRMED) |

So: no distance beyond "within dist of the destination cell and turned towards it"; a path that cannot get there just ends like any move.
**Duration (CONFIRMED by the flow):** tick T: the brain (`FUN_0056dca2`, called first in `FUN_0050f12c`) sets state `0xf` and the
**same tick's** `switch` runs case `0xf` once (§3); tick T+1: mode 15 sees state `0xf` and calls `FUN_0056dbc6`: state 0, brain `+0x50 = 1`,
order `0xc` (stand at the own cell, `FUN_0056d52b`), mode 0. The effect therefore happens **once per command**; there is no use
animation time, no cooldown, no one-shot flag, no "already used" test. A new command in the tick between cancels nothing that matters
(any order issuer resets the state).

### 2.1 The real stop cell of a use walk (Q3; CONFIRMED code, effect on map 103 measured in the engine)

* **Walk target (CONFIRMED `0x56ecbc` -> `0x56e4ac` -> `FUN_00555411`)**: the planner is called with the destination cell of 2 (`brain+0xa`: for a switch the
  structure's own, **blocked** cell) and the range `dist` as the stop distance. There is no search for a free cell next to the structure and no per-structure
  approach cell; the range is not given to the planner, only to the driver.
* **Planner (CONFIRMED `FUN_0054d76e`, mode static, [simulation 7.1](simulation.md))**: a blocked target is never labelled. The wave is **bounded**
  (`dist + min(5, dist/4)` levels; the unbounded 1000 is only for a human unit and a passable target, `0x54d9..`), so it ends at the limit, then
  `FUN_005585f4` returns the labelled cell with the **smallest field value (cheapest from the hero) of ring 1 around the target** (scan order `(+o,+r) (+o,-r)
  (+r,+o) (-r,+o)`, first wins ties). The hero walks to that cell and, with several equal ones, the 8-neighbour tie rules of the backward walk decide.
  Static re-plans every 17 hops start from the new cell and re-pick the ring cell.
* **Arrival (CONFIRMED `FUN_0055539a`, `FUN_00555411` steps 2 and 6)**: at every cell centre the driver compares Chebyshev(unit cell, dest) with `dist`; `dist >= `
  distance ends the walk (`FUN_00556da2`, stop and turn). So the hero stops on **the first cell of its path within range 1 of the structure's cell**, which is the
  ring-1 fallback cell of the planner (the path ends there; no other ring cell is passed on the way). `FUN_0055539a` then wants facing == the facing to dest; the
  unit turns on the spot (no step), then state `0xf`. A hero already within range at the command stays on his own cell (this is how a player picks the cell:
  move next to the switch on the wanted side, then click it).
* **Consequences**: (1) the stop cell is the neighbour of the target **on the side the hero comes from** (open ground: the nearest; ties by the field costs, diagonal
  neighbours cost 3 against 2); (2) a far `UseStructure` can **fail**: when the shortest route is more than about `5` levels longer than the Chebyshev distance
  the wave never touches ring 1, the fallback finds nothing, the plan is empty ("No way", message `0x92`) and the order ends without a step. Map 103: from the
  hero's start (72, 12) to switch 1 the route is 94 cells for Chebyshev 60, so the use fails until a normal move has brought the hero within ~15 cells.
* **Engine (fixed)**: `structures.set_use` used to pick "the free cell within range nearest to the unit" (`walk_goal`, a DECISION, which also made far walks succeed);
  it now plans to the destination cell itself and the range test of `use_mode` ends the walk. Tests `test_the_walk_targets_the_blocked_cell...`,
  `test_map_103_the_approach_side_decides...`, `test_map_103_a_far_use_walk...`.
* Not checked in game: the exact ring-1 cell for equal costs on real terrain (the engine port of `FUN_005585f4` / the backward walk is bit-exact to the decompile, simulation 7.1); no cost-tie case matters for the puzzle.

## 3. State `0xf` by class (`FUN_0050f12c` case `0xf`, `0x50f896`-`0x50fc09`, CONFIRMED)

**The structure is not the one clicked.** The case ignores brain `+0x68` (`FUN_0056ecbc` gets it as an argument and never reads it) and
looks the structure up by position:

* lookup A: `FUN_0052c129(unit cell)` -> `FUN_0052bfe7(point (x-1, y-1))`: the **first** object of the building list (creation order = map
  section 4 file order, `AddTail` `FUN_00545dd0`; INFERRED that the list is exactly that file order) whose position object is within
  **Chebyshev 2** of the point (`FUN_0054fb7f` = max(|dx|, |dy|), `<= 2`); the object's `+0x10` is the footprint's top-left cell. Type and owner are
  not tested.
* lookup B (after A's branches, only when A did not `break`): `FUN_0052bfe7(unit cell)`, same rule, no shift.

Branches on the result of A, in order:

| Test | Class | Effect |
|---|---|---|
| IsKindOf shop class (`0x5f90e0`) | multiplayer shops | client message `0x83` (`FUN_00505347`, type byte `+0x40`, owner `+0x14` of the unit); out of scope |
| IsKindOf inn class (`0x5f91b8`) | multiplayer inns | message `0x84` (type byte, structure `+4`, owner); out of scope |
| IsKindOf "Pointer" (`0x5f90b0`) | signposts 70-75 | `if (+0x6c > 0) FUN_00574f3f(+0x6c)` (the instant runtime index; `0` = nothing, quirk, map.md section 11). Every use runs it again; no flag. All 40 install records send message `0x433` (instant 2) |
| type word `+0xe == 0x42` and `FUN_0044fff0(0x68f628) == 4` | "Saving Place" | client save UI (`FUN_0050155f`, `FUN_00500ad9`, `FUN_0050101e`, `player+0xa50 := [[0x6044c4]]`); no campaign map has it; not analysed |
| type word `0x1c`, `0x1d`, `0x4c`, `0x4d` | **switches 1/2 and altars 1/2** | `+0x42 = (+0x42 == 0) ? 1 : 0`, then `FUN_00503672(structure, 0, 0)` (§4). No other test: any unit, any owner, no limit, **toggles back** on the next use |
| (anything else) | graves 39/40, houses | nothing |

Then lookup B on the unit's own cell, **only the first object within 2 is looked at**:

| Type byte `+0x40` | Class | Effect |
|---|---|---|
| `0xf` (Well 2) | healing well | if HP (`+0x42`, charges) `> 0`: HP -= 1, `FUN_00503672` (message `0x82`), create item "Potion Big Healing" (`FUN_00522fab`), `unit->vtable[0x44](item)`: use the potion on the unit; the item is destroyed and the pack never gets it (§7.1): **health +100** (capped at max HP; data.bin item `Potion Big Healing`, effect `health=+100`) |
| `0x10` (Well 3) | mana well | same with "Potion Big Mana": **mana +100** |
| other | - | nothing |

* Wells hold **3 charges** (healthMax 3); at 0 nothing happens (no message). Not per hero, not per time: three uses by anyone, then empty. Class,
  level, items, gold and mana are never tested. The charges survive because the well is Indestructible on the client (its art never switches to "destroyed").
* **Graves (King's Grave 1 / 2): no server effect** (CONFIRMED: no code tests types `0x27`/`0x28`; the only `+0xe` readers of this family are the four
  switch / altar ids at `0x50f9d4`-`0x50f9fe`, and graves are not wells). The walk, the stop and the turn are all that happens. Sounds / messages on use: none in case `0xf`.
* Altars: identical to the switches (HP 0 <-> 1, art intact <-> destroyed); no script in the install reads them.
* Facing, voices and animation of the unit while in state `0xf`: see 3.1 (nothing of its own).

### 3.1 Client side of state `0xf` (CONFIRMED: no client side)

State `+0x54 = 0xf` is **never seen by the client**; the hero has no use animation, sound or voice. The chain:

* The client draws a unit from its own action byte `obj+0x8c` (0 idle, 1 move, 3 attack, 5 turn, 6 dying, 7 shoot, 8 cast), set only by the server messages
  `0x6b / 0x6d / 0x71 / 0x72 / 0x86 / 0x8a / 0x6c / 0x6e-0x70` in `FUN_0040d9b2` and ticked by `FUN_0046617c` ([animation 1.4-1.5](../formats/animation.md)); there is no
  state-to-action map and no action for "use".
* Server side, `FUN_0050f12c` (`0x50f12c`) per tick: the only client traffic it can emit in the state switch is `FUN_00502019` (unit data flags; its payload carries
  position, type word, HP, mana ... and **not** the state `+0x54`) and the per-class messages of 3 (`0x82` via `FUN_00503672`, `0x83`, `0x84`); case `0xf` itself sends
  none for graves, switches, altars, wells or signposts. Message `0x7a` is the loot-pile message ([combat 12](combat.md)), unrelated.
* Hence while the server is in state `0xf` (one tick) the client keeps the action of the last step / turn message (idle once its duration ran out, idle phases of the
  type continue) and the facing the turn messages left: the server only reaches state `0xf` when its facing already equals the facing to the destination cell (2, executor).
  The next tick `FUN_0056dbc6` returns to state 0 with no message.
* Sounds: none from the state. The only voice is the squad voice sent with the command by `FUN_0041a0b5` (client send, 2). Item pickup / potion sounds of the wells
  are a different path (the item use of 3, not traced); the switch / altar change is silent (message `0x82` only changes the picture, 4).
* **Engine:** draw nothing special: state `0xf` has no action (`unit.action` stays `idle` / `move` / `turn` as the movement code leaves it); facing = facing to the
  destination, which `use_mode` already ensures before setting the state. No change needed (guard: `tests/test_engine_structures.py`
  `test_state_f_has_no_action_of_its_own_and_the_hero_faces_the_structure`).
* INFERRED: absence of any other client reader of the server state (checked: the unit-data message `FUN_00502019` and every writer of `obj+0x8c`; no full search of
  all sends of `unit+0x54` was made).

**Lookup quirk and its consequences (code CONFIRMED, effect on data INFERRED).** Because A searches near `(x-1, y-1)` of the hero's cell, the first
structure of the list within 2 cells wins, not the one the player clicked. A hero standing on a neighbour cell of a 1x1 switch always finds
*some* structure, but another switch two cells away that comes earlier in the file captures the use (§6, map 103). A well enclosed by other
structures (map 52 uid 38, inside a Stonehenge ring: the four ring pieces are earlier in the list) is never found by lookup B. The
engine should apply the same rule (spec "match the game exactly"), with a debug switch to use the clicked structure instead.

## 4. Switch state, graphics, passability

| Item | Fact |
|---|---|
| State field | **HP `+0x42`** (s16), the field check 21 reads and instant 26 writes (CONFIRMED `0x5776d7`, `0x57855f`). Values: **1 = start / "intact"** (map entry `intact != 0`: HP = healthMax = 1), **0 = destroyed** (`intact == 0`, or one use). Use: `0 -> 1`, any other value `-> 0` (instant 26 may store any value; then the next use gives 0). Max HP `+0x44` = 1 |
| Client message | `FUN_00503672(structure, 0, 0)`: for every human player (or the owner) sends message type `0x82` (`+7` player, `+0xa` structure id, `+0xc` HP) through the hub `0x50164f`; it sends **nothing when max HP `+0x44` is 0** (indestructible). Client handler (CONFIRMED, §4.1): the `0x82` case stores `msg+0xc` in the object's HP `obj+0x104` (`0x410b13`) and posts window message `0x408` when the structure is the selected object |
| Graphics | no animation, no frame field: the draw (`FUN_00461649`, [animation §4.2](../formats/animation.md)) picks the **destroyed block** (the last `W·FH` frames) when `obj+0x104 < 1` and the record is not Indestructible; else the intact block. Switch 1 / 2 art = 4 frames (1 x 2 pieces, `FullHeight` 2): intact 2, destroyed 2 (lever up / down; which is which is a data matter). The info panel (text mode) shows `Health  hp/max` (ui-layout) |
| Passability | **unchanged**. The stamp of `Passability` / `BuildingPresent` is made once in the constructor (`FUN_005599df` at `0x5200ab`); the use code only writes `+0x42` and calls `FUN_00503672`; `FUN_00550a96` / `FUN_00559890` are not reached ([combat §5.4](combat.md): a destroyed structure keeps its stamps). The switch's single cell stays blocked (params 1, 1); there are no gates or doors in the usable set |
| Links | none. A switch does not flip another structure; the only reader is the script (check 21 by uid). The map record has no link list |

### 4.1 Client message handlers (CONFIRMED)

The client message switch is `FUN_0040d9b2` (`0x40d9b2`): message type byte `msg+9`, `type - 3` indexes the byte table `0x41607f`, then the jump table `0x415fa7`.

| Type | Case | HP write | What else |
|---|---|---|---|
| `0x82` (structure state, sent by `FUN_00503672`) | `0x410ab5` | `0x410b13`: `obj+0x104 = s16(msg+0xc)` | object by id `msg+0xa` via `FUN_0041ff90` on the object table `client+0x9d0` (unknown id: drop). If the object is the selected one (`client+0x138`), posts window message `0x408` (twice: window objects `+0xe0` and `+0xe4`, vtable `+0x48`) to refresh the info panel. **Nothing else**: no sound, no frame field, no art switch call, no minimap or fog write, no flag |
| `0x73` (combat HP change) | `0x412826` | `0x412ade`: `obj+0x104 = s16(msg+0xc)` | unknown id: debug log. Before the write: with the "Flying damage" option (`client+0xabc`) and `old HP > new HP` it creates the floating number (difference, tint by the new HP against max `+0x108` / 2 and / 4); a call through the object's vtable `+0x74` with `0` (HP equals the new value), `2` / `1` (new HP in -9..max/2 or above) while the old HP > -10 (hit / death feedback; not traced); then the same `0x408` post for the selected object and `obj+0x114 = 1` |

So `0x410b13` is the `0x82` writer and `0x412ade` the `0x73` writer. Both only change the HP field; the picture is decided at draw time.

**Which graphic is drawn.** The draw routine `FUN_00461649` (per structure, per column of the footprint) chooses the destroyed block when `s16(obj+0x104) < 1` and the record's Indestructible byte (`+0x64`) is 0, else the intact block (with the phase counter of animated art): HP 0 -> destroyed (lever "down"), HP 1 -> intact. There is no separate state, no transition animation and no other reader; a switch's picture follows the last `0x82` HP exactly. The server's `0x82` is sent only when max HP `+0x44` is not 0, so the HP is the whole protocol. **Engine agrees** (CONFIRMED by comparison): `engine/sim/structures.py` toggles `obj.hp` and the FLAG_DESTROYED mirror, `engine/view/drawlist.py::_destroyed` draws the destroyed block for `hp <= 0` of a non-Indestructible set with a destroyed action. No code change. (Not checked in the exe: which of the two frames of switch art is the "up" lever; data, same as before.)

## 5. Script side

* **Only two operations name a structure** (scan of every check / instant of the 46 maps for argument kind 9 "building": check 21 on maps
  93, 94, 95, 96, 103; instant 26 on **no** map). Check 20 (count of a player's buildings with HP > 0) occurs on no map.
* Check 21 `Health of building` (`0x5776d7`): `values[slot] = s16(+0x42)`; instant 26 (`0x57855f`) writes `+0x42 = n0` **without** the client message
  (the client keeps the old picture; unused). Both already exist in `engine/sim/triggers.py` (`eval_check` kind 21: `c.building.hp`; `run_instant`
  kind 26: `c.building.hp = n0`) and `world.py` starts HP at `params[3]` (1 for switches) or 0 for `intact == 0`. What is missing is only the writer: the use.
* There is **no "object used" event**: a script cannot see that a switch was used, only that its HP is now 0 or 1 (it cannot tell two uses
  from none). Pass cadence: every 16 ticks, so the condition is evaluated on the next group pass after the toggle (up to 15 ticks late); two quick uses
  inside one pass leave no trace. Signposts are the opposite: they run a script instant directly (§3), but every install record is instant 2.
* Triggers compare with `!=`, `>`, `==`; the editor labels say "off" for `HP > 0` and "on" for `HP == 0` (map 103).

## 6. Puzzles (maps 93-96 and 103)

Initial state everywhere: all switches `intact = 100` -> **HP 1** ("off" in map 103's wording). Owners 6 / 2 (neutral), no effect on use.

**Maps 93, 94, 95, 96** (identical pair): switch uid 2 (type 28) at cell (100, 24) and uid 3 (type 29) at (110, 40). Trigger "Teleporter opens" (once): check 21 on uid 2 `!= 1`
**and** on uid 3 `!= 1`, i.e. both thrown. Instants: message 2 ("Dina about teleporter") and instant 25 Set trap: spell 23 (Teleport), power 100, cell (102, 34), target (74, 72) -> a teleporter
trap at (102, 34) leading to the central point (74, 72). **Solution: use each of the two switches once, in any order.** The two are far apart; no other structure is near, so
the lookup rule returns the right switch from every neighbour cell. The rest of each map is the other half of the puzzle and needs more than K6:

| Map | Needs beyond switches |
|---|---|
| 93 | Firewall puzzle: checks 25 (spell on tile, layer 0, cells (121..125, 69) and (121..125, 75)) set v70 / v71, then instant 25 "Fire teleporter" (115,72) -> (100,104) and sub-objective; check 25 built (K7, effects §6.5): two Wall of Fire casts solve it |
| 94 | Stonewall puzzle: 9 check-25 cells in layer 3 (63..67, 113..117) -> "Earth teleporter" (66,107) -> (122,124); K7 built: straight walls on rows 113 / 117 and a diagonal one on 115 |
| 95 | Fog puzzle: instants 21 (make spell effect, spell 6) at (66,25), (69,27), checks 25 layer 2 on 9 cells, instant 29 Tile Spell Duration, "Water teleporter" (68,37) -> (20,19); K7 built: Wall of Fire burns the clouds off rows 24 / 26 / 28 |
| 96 | "Air" puzzle without check 25: instants 24 (cast spell 18 on units 20, 21, 22) and 30 (Unit Spell Duration), check 26 (Spell on Unit, bit 12 Invisibility) on the three units every pass, then instant 25 "Air teleporter" (31,71) -> (40,39); the mission ends on a distance test to (10,135) with the item counter `v74` set by `Drop all` on unit 49 when the hero is near it |

**Map 103** ("Find the magic Oracle"): 16 switches, two independent puzzles, all pairs at 3-cell spacing.
Trigger flags `rep` recompute variables every pass (the "Start Zero" triggers set them to 0 first, so a variable is the current state with a lag of one or two passes).

| Puzzle | Switches (uid: type, cell) | Required state | Reward |
|---|---|---|---|
| A (12 switches, field x 19..28, y 73..81) | 1: 29 (28,73) · 2: 29 (28,78) · 3: 29 (25,81) · 4: 29 (19,81) · 5: 29 (19,76) · 6: 29 (22,73) · 7: 28 (25,73) · 8: 28 (28,75) · 9: 28 (28,81) · 10: 28 (22,81) · 11: 28 (19,78) · 12: 28 (19,73) | **on (HP 0): 4, 6, 7, 9**; **off (HP 1): 1, 2, 3, 5, 8, 10, 11, 12** | `once` trigger 27: instant 20 (Drop all) of unit 132 at (24, 77) |
| B (4 switches, map corners) | 13: 28 (12,20) · 14: 28 (20,131) · 15: 29 (131,116) · 16: 29 (128,13) | **on: 14, 16**; **off: 13, 15** | `once` trigger 30: Drop all of unit 131 at (75, 71) |

Both start with all switches off, so the **solution is: use 4, 6, 7, 9 (once each) and 14, 16 (once each), any order, touch nothing else (or an even number
of times)**. Group A's checks (triggers 20-27): `HP > 0` for 1, 8, 2 / 3, 10, 11 / 5, 12 and `HP == 0` for 4, 9 / 6, 7; trigger 25 needs `v74` (6, 7) and `v75` (4, 9),
trigger 26 needs `v70, v71, v72` (the off groups), trigger 27 needs `v73` and `v76`. The dropped items are the quest items the orc wants (items 62 and 63: head and stone); the stone is also picked at the house (41, 50) by triggers 9-11. Then the orc must meet the hero with both
items (triggers 12-14), walk to the waypoints and to the Oracle at (128, 72) (trigger 15, `v83`) and trigger 31 completes the mission. Other triggers: messages, and failure when the shaman (unit 30) dies or is attacked.

**Lookup effect in 103 (rule CONFIRMED, stop cells from 2.1 measured with the engine on the install's map; list = file order = uid order).** The hero ends
on the neighbour of the clicked switch on the side he comes from, and the lookup of 3 then toggles the first switch within 2 of `(x-1, y-1)` of that cell:

| Clicked | Stop cell (offset) / side of approach | Toggled |
|---|---|---|
| 1, 2, 3, 4, 5, 6, 12, 13-16 | any neighbour | itself |
| 7 (25,73) | NE / E / SE (offsets (1,-1), (1,0)) | 7 |
| 7 | N, NW, W, SW (offset (-1,-1), (0,-1), (-1,0)) | **6** |
| 8 (28,75) | any | **1** (never itself) |
| 9 (28,81) | SE and part of E / S (offset (1,1) = (29,82)) | 9 |
| 9 | N, NE, NW, E (offset (1,-1), (1,0), (1,-1)) | **2** |
| 9 | W, SW, S-west (offset (-1,1)) | **3** |
| 10 (22,81) | NE / E / SE (east side, x = 23) | 10 |
| 10 | N, NW, W, SW, S (x <= 22) | **4** |
| 11 (19,78) | any | **5** (never itself) |

Measured approach table, hero starting 8 cells away (Chebyshev) on each side of the target; the stop cell is chosen by the planner, so for a hero coming
from a side only some neighbours are ever used. `7`: from NE and SE the east side -> **7**; from N, NW, W, SW the north-west cell -> **6** (29 of 54 starts).
`9`: from SE the cell (29,82) -> **9** (16 of 63 starts; SW starts split 11 : 4 between 3 and 9), from NE / N / NW -> **2**, from W / S-west -> **3**. `4` and `6`
are hit from every side, `14` and `16` (corner pairs, no other switch near) from every side.

**Solvable by normal play.** The solution switches 4, 6, 14, 16 are hit from any side. 7 is hit when the hero comes from the east half (from the hero's start, the
north-east, a walk down the east side is natural); 9 only from the SE / east-south side. As the walk of 2.1 ends at once for a hero already in range, the player can
always choose the cell: walk to a free neighbour of the wanted switch (e.g. (26,72) or (26,73) for 7, (29,82) for 9) with a normal move, then click the switch. The
decoys 8 and 11 can never be thrown, and 1, 2, 3, 5, 10 are thrown only by a click on a wrong neighbour; they must end off, which the trigger needs (a wrongly thrown
one can be thrown back by a second use from the same side). So the puzzle stays solvable; whether the designers intended the sides is unknown. Far use clicks
fail (2.1): first walk near. In maps 93-96 and 75 the pair / the two switches are alone (75: not read by any script; uid 10 (81,106) is hit from W and N sides, uid 11 (94,101) from the east neighbour only partly because other structures lie within 2).

## 7. Other classes (for K8)

| Class | Behaviour | Formula / state |
|---|---|---|
| Well 2 (15) | +100 health per use, 3 uses | HP 3 -> 0 on `+0x42`; potion "Potion Big Healing" through the item use path ([items](../data/items.md)); empty well just stops |
| Well 3 (16) | +100 mana per use, 3 uses | "Potion Big Mana" |
| Signposts (70-75) | run instant at `+0x6c` when `> 0` (message 2 -> `0x433` story text) | repeatable; map.md section 11 `enabled`, `n` |
| Altars (76, 77) | toggle HP 0 / 1 and the picture | cosmetic; no script reads them |
| King's Graves (39, 40) | no effect | 18 + 37 placements; hover cursor, walk, stop |
| Shops / inns / church | multiplayer; not reached in the campaign | messages `0x83`, `0x84` |

### 7.1 The well potion path in detail (CONFIRMED, REA: `FUN_0050f12c` case `0xf`, `FUN_00522fab`, `FUN_00523613`, `FUN_00510883`, `FUN_00512638`)

Sequence per use (case `0xf`, lookup B `FUN_0052bfe7`, type byte `+0x40` = `0xf` / `0x10`, charges `+0x42` > 0):

1. `+0x42 -= 1`, then `FUN_00503672(well, 0, 0)` = message `0x82` (picture / charge word `+0x42` to the client). The charge is consumed **before** and independently of the potion: nothing later can refund it.
2. `FUN_00401880(0x54)` allocates the 0x54-byte item (a failed allocation would pass a null item on; not reachable in practice). `FUN_00522fab(name)` is the item constructor by data.bin name ("Potion Big Healing" `0x5fe2dc` / "Potion Big Mana" `0x5fe2f0`): vtable `0x5d1388`, count `+0x42 = 1`, weight `+0x4a = 1`, searches the data.bin item table (`FUN_0053e1c0` count, name compare `FUN_00402a00`) for the id (`+0xc`; a miss logs "Invalind Item ... no such ID" and leaves id 0), then `FUN_00523148(0xe)` fills class 14 data (type byte `+0x44` = 3 for a potion). It returns the object.
3. `unit->vtable[0x44](item)`. Human vtable `0x5d0fb8` slot `0x44` = `FUN_00512638`: item `+0x40` put (`FUN_00512573`; a potion is not weapon / shield / armour, so no class test) -> item vtable `+0x38` = `FUN_00523613` (class vtable `0x5d1388`, slot `+0x38`); a **non-null** return would be filed with `FUN_00529ac2`. Monster vtable (`0x5d0ef4` = slot `0x44` of the table at `0x5d0eb0`) = `FUN_00510883(item)` (no direct callers): `item->vtable[0x38](unit)`; non-null -> `FUN_00529ac2(unit+0x7c)` then `unit->vtable[0x5c]()` (`FUN_0051754d`, a field refresh; INFERRED that it is the weight / level refresh). Both do the same thing for a living unit.
4. `FUN_00523613(unit)` (item `+0x38`): `if (unit HP +0x94 > 0)`: every effect with flags 0 gets `|= 8`, each effect `vtable+0x3c(unit)` (the stat switch: health / mana `+100`, capped at max), unit `vtable+0x5c`, the attribute-name check (`FUN_004e9e97`, not for these two), then **the item is deleted** (`vtable+4(1)`) and **null is returned**. Only a unit with HP <= 0 gets the item back (non-null) and thus into the pack.

Answers to Q5:

* (a) `FUN_00522fab` = item constructor by name, returns the new object. Item `+0x38` for these potions = `FUN_00523613` (use; class vtable `0x5d1388`, the generic item class). `FUN_00510883` = the monster-side "use then file" method (`+0x44`); the human twin is `FUN_00512638`. Both return nothing.
* (b) **Full pack is irrelevant**: for a living unit (the only unit that can be in state `0xf`: the tick runs the state switch only when HP >= 1) the potion is applied and destroyed and never reaches the pack. Even the insert `FUN_00529ae2` has no capacity test (the 0x400 entries limit lives only in the ground pickup `FUN_00529e5b`). No drop on the ground, no refusal message; the charge is consumed.
* (c) Use returns null in the normal case (living unit): that is success, not failure. The "non-null -> add to the pack" branch is dead code for wells (needs a dead carrier). A not-found item name or a failed allocation is not a game case (both well names exist in data.bin, items §).
* (d) No load / encumbrance update: nothing is inserted, so `FUN_0050f065` / `+0x90` are untouched; the effect stat switch runs the normal recompute (vtable `+0x58`; HP / mana only clamped to the maximum, never raised past it).
* (e) Client messages: only `0x82` (charge word) from step 1; no pickup text and no sound (the "new item" flag `+8` is set only by the ground pickup `FUN_00529e5b`). The HP / mana change reaches the client through the normal unit-data refresh (`FUN_00502019`, INFERRED: not traced past the stat switch).
* (f) Charges: `+0x42` starts at healthMax 3 (CONFIRMED on the data: of the 26 well placements on the campaign maps 25 start with 3, and **map 53 uid 41 (a Well 3) has `intact = 0`, so it starts empty**: `FUN_00561422` stores HP 0 for a plain structure whose entry says 0; test `test_map_53_well_uid_41...`), counted down by every unit, never refilled, no timer; at 0 the branch is skipped silently. Per type: `0xf` -> "Potion Big Healing" health `+100`; `0x10` -> "Potion Big Mana" mana `+100`; no other kinds. No gate on level, class, HP / mana fullness (a full unit still burns a charge), items, owner or relation (also valid for enemy / neutral units that reach state `0xf`; heroes only through the client cursor rule).

## 8. Engine design notes (what to implement now)

1. **Command / order `use`**: unit order `0xf`, destination = top-left cell + (0, 0) / (1, 1) / (2, 2) by W (1-2 / 3-4 / 5+), range 1 / 2 / 3; arrival = facing equals the facing to the
   destination (the existing turn state) and Chebyshev <= range; on arrival tick T: run the use once, tick T+1: stand (order `0xc`). Hero-only is a **client** rule (cursor `town`
   with a single hero selected); the server accepts any unit and structure.
2. **Use step** `use_structure(unit)`: lookup A (`(x-1, y-1)`, first structure of creation order within Chebyshev 2) -> pointer: run instant `+0x6c` if `> 0`; type 28 / 29 / 76 / 77: `hp = 0 if hp else 1`, send the HP to the view;
   then lookup B (own cell): type 15 / 16 with HP > 0: HP -= 1, apply health / mana +100 (capped).
3. **View**: HP is the only state (`MapObject.hp`); draw destroyed art for `hp < 1` of a non-Indestructible structure (existing logic). No restamp, no pathing change.
4. **Scripts**: check 21 / instant 26 already exist; K6 needs only the writer. Instant 26 does not tell the view (keep that).
5. **Tests (K6/K8)**: the pair on maps 93-96 (use both -> trigger 1 fires within 16 ticks, teleporter trap placed); map 103 puzzle A + B (checks of §6), wells (3 uses, +100 capped, 4th nothing), signpost (instant each time), altar toggle, grave no-op, lookup quirk (a unit next to switch 8 toggles uid 1).
6. Coverage keys: `use.scripted`, `use.switch`, `use.altar` are K6 (the altar is the same toggle); `use.well`, `use.pointer`, `use.pointer_script`, `use.grave` K8, all BUILT
   (grave = hover and walk only).

### 8.1 K8 decisions and what the exe settles
* A switch / altar use **also runs lookup B**: case `0xf` falls through to it unless the Pointer / shop / inn branch broke out (tested: a switch next to a well, the
  signpost that shadows a well).
* The potion path of 7.1 is exact: the charge goes first (message `0x82`); `gear.use_item` is K4's `FUN_00523613`, so Healing / Mana, the cap, the recompute and the
  dead-carrier rule (`hp <= 0`: nothing) are not re-implemented. data.bin names "Potion Big Healing" (special 71, `health=+100`) and "Potion Big Mana" (74,
  `mana=+100`) are read from the item table; a table without them keeps the charge change and does nothing else (the exe would log "no such ID": not a game case).
* Nothing random: no `rand` is called in a use (tested), so the world RNG is untouched and a replay gives the same hash.
* Not stored per hero: charges are the structure's `+0x42`, shown by the info panel as `Health hp/max` for the selected well (existing reader).
* The info panel of a hovered well shows `hp/max` of `obj+0x104` (`structure_rows`, ui-layout 10), so it follows the charges as the `0x82` handler writes them (engine tested: `3/3` -> `2/3`). VERIFY IN GAME only that the panel redraws while hovering without a new hover event (INFERRED); the well sound heard in the original, if any, is not from the server (no sound request exists in the path read here).

## Open questions

* The meaning of `FUN_0044fff0(0x68f628) == 4` for the "Saving Place" branch (probably a game-type value) and the `FUN_0050155f` chain (save UI); no campaign map has the type.
* VERIFY IN GAME: the 2.1 stop cells on map 103 (which side hits 7 and 9), and that a far use click answers "No way".
