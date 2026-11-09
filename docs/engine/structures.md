# Using structures (switches, wells, signposts, altars, graves)

How the hero uses a structure, what each usable class does, and what the scripts see. Tags: CONFIRMED = read in the GOG
`allods2.exe` (sha256 in [formats/README](../formats/README.md)) at the routine / address given; INFERRED = code shape, data pattern or
analogy. Server object `DAT_0066832c`; creature = server unit ([unit-struct](unit-struct.md)); structure = server building (`+0xe` type
word, `+0x40` type byte, `+0x42` s16 HP, `+0x44` max HP, `+0x10` position object, `+0x14` owner, `+0x60/+0x61` footprint W/H,
`+0x6c` signpost instant). Commands: [click-to-move-research](click-to-move-research.md); script side: [triggers](triggers.md).
Everything in this file is single player.

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
| server intake | `FUN_004f515d` case `0x24` (`0x4f563f`): structure by id (`FUN_0052bfa3` over the building list `[0x6044c4+0x7c]`); unknown id logs and drops; else `FUN_0056d22b(unit, structure)` with the **unit of the last id** resolved in the list (the client sends one id for the `town` cursor; INFERRED effect of several ids). **No test of class, owner, hero, level, distance, items or money** | CONFIRMED |
| order | `FUN_0056d22b`: `FUN_0056dbfb` (cancel: state 0, facing), **unit order `+0x50 = 0xf`**, brain `+0x68 = structure`, brain mode `+8 = 0`, destination `brain+0xa` = the structure's `+0x10` cell word, then by the footprint width `W = structure+0x60`: W 1-2: dist 1, dest unchanged; W 3-4: dist 2, dest `+(1,1)`; W >= 5: dist 3, dest `+(2,2)` (`brain+0x14` = dist). Only caller: `0x4f5663` (player command). The AI never uses structures | `0x56d22b` (CONFIRMED) |
| group pass | order `0xf` is re-armed by the group executor (`FUN_00569321` case -> `FUN_0056af23`: brain mode `0xf`, `+0x68`) | `0x56af23` (CONFIRMED) |
| executor | brain mode 15 = `FUN_0056ecbc`, run every tick while brain order `+9 == 0` (jump table `0x56e470`): `FUN_0055539a(unit, brain+0xa, brain+0x14)` = **facing equals the facing to the destination cell** (`FUN_00556b2c`) **and Chebyshev(unit cell, dest) <= dist** (`FUN_00558fe9`). True: state `+0x54 = 0xf` (first tick) or, when the state already is `0xf`, `FUN_0056dbc6` (stop). False: walk / turn with `FUN_0056e4ac` (`FUN_00555411(unit, dest, dist)`, state 1) | `0x56ecbc` (CONFIRMED) |

So: no distance beyond "within dist of the destination cell and turned towards it"; a path that cannot get there just ends like any move.
**Duration (CONFIRMED by the flow):** tick T: the brain (`FUN_0056dca2`, called first in `FUN_0050f12c`) sets state `0xf` and the
**same tick's** `switch` runs case `0xf` once (§3); tick T+1: mode 15 sees state `0xf` and calls `FUN_0056dbc6`: state 0, brain `+0x50 = 1`,
order `0xc` (stand at the own cell, `FUN_0056d52b`), mode 0. The effect therefore happens **once per command**; there is no use
animation time, no cooldown, no one-shot flag, no "already used" test. A new command in the tick between cancels nothing that matters
(any order issuer resets the state).

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
| `0xf` (Well 2) | healing well | if HP (`+0x42`, charges) `> 0`: HP -= 1, `FUN_00503672` (message `0x82`), create item "Potion Big Healing" (`FUN_00522fab`), `unit->vtable[0x44](item)`: use the potion on the unit and hand over the rest (`FUN_00510883`: item `vtable+0x38` = use, [items §use](../data/items.md), then the inventory add and the client refresh): **health +100** (capped at max HP; data.bin item `Potion Big Healing`, effect `health=+100`) |
| `0x10` (Well 3) | mana well | same with "Potion Big Mana": **mana +100** |
| other | - | nothing |

* Wells hold **3 charges** (healthMax 3); at 0 nothing happens (no message). Not per hero, not per time: three uses by anyone, then empty. Class,
  level, items, gold and mana are never tested. The charges survive because the well is Indestructible on the client (its art never switches to "destroyed").
* **Graves (King's Grave 1 / 2): no server effect** (CONFIRMED: no code tests types `0x27`/`0x28`; the only `+0xe` readers of this family are the four
  switch / altar ids at `0x50f9d4`-`0x50f9fe`, and graves are not wells). The walk, the stop and the turn are all that happens. Sounds / messages on use: none in case `0xf`.
* Altars: identical to the switches (HP 0 <-> 1, art intact <-> destroyed); no script in the install reads them.
* Facing, voices and animation of the unit while in state `0xf` are the client's (no message is sent by the case itself): open question.

**Lookup quirk and its consequences (code CONFIRMED, effect on data INFERRED).** Because A searches near `(x-1, y-1)` of the hero's cell, the first
structure of the list within 2 cells wins, not the one the player clicked. A hero standing on a neighbour cell of a 1x1 switch always finds
*some* structure, but another switch two cells away that comes earlier in the file captures the use (§6, map 103). A well enclosed by other
structures (map 52 uid 38, inside a Stonehenge ring: the four ring pieces are earlier in the list) is never found by lookup B. The
engine should apply the same rule (spec "match the game exactly"), with a debug switch to use the clicked structure instead.

## 4. Switch state, graphics, passability

| Item | Fact |
|---|---|
| State field | **HP `+0x42`** (s16), the field check 21 reads and instant 26 writes (CONFIRMED `0x5776d7`, `0x57855f`). Values: **1 = start / "intact"** (map entry `intact != 0`: HP = healthMax = 1), **0 = destroyed** (`intact == 0`, or one use). Use: `0 -> 1`, any other value `-> 0` (instant 26 may store any value; then the next use gives 0). Max HP `+0x44` = 1 |
| Client message | `FUN_00503672(structure, 0, 0)`: for every human player (or the owner) sends message type `0x82` (`+7` player, `+0xa` structure id, `+0xc` HP) through the hub `0x50164f`; it sends **nothing when max HP `+0x44` is 0** (indestructible). The client stores `msg+0xc` in the object's HP `obj+0x104` (`0x410b13` / `0x412ade`, one of the two is the `0x82` case: INFERRED) and posts window message `0x408` when the structure is the selected object |
| Graphics | no animation, no frame field: the draw (`FUN_00461649`, [animation §4.2](../formats/animation.md)) picks the **destroyed block** (the last `W·FH` frames) when `obj+0x104 < 1` and the record is not Indestructible; else the intact block. Switch 1 / 2 art = 4 frames (1 x 2 pieces, `FullHeight` 2): intact 2, destroyed 2 (lever up / down; which is which is a data matter). The info panel (text mode) shows `Health  hp/max` (ui-layout) |
| Passability | **unchanged**. The stamp of `Passability` / `BuildingPresent` is made once in the constructor (`FUN_005599df` at `0x5200ab`); the use code only writes `+0x42` and calls `FUN_00503672`; `FUN_00550a96` / `FUN_00559890` are not reached ([combat §5.4](combat.md): a destroyed structure keeps its stamps). The switch's single cell stays blocked (params 1, 1); there are no gates or doors in the usable set |
| Links | none. A switch does not flip another structure; the only reader is the script (check 21 by uid). The map record has no link list |

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
| 93 | Firewall puzzle: checks 25 (spell on tile, layer 0, cells (121..125, 69) and (121..125, 75)) set v70 / v71, then instant 25 "Fire teleporter" (115,72) -> (100,104) and sub-objective; K7 (check 25) |
| 94 | Stonewall puzzle: 9 check-25 cells in layer 3 (63..67, 113..117) -> "Earth teleporter" (66,107) -> (122,124); K7 |
| 95 | Fog puzzle: instants 21 (make spell effect, spell 6) at (66,25), (69,27), checks 25 layer 2 on 9 cells, instant 29 Tile Spell Duration, "Water teleporter" (68,37) -> (20,19); K7 |
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

**Lookup effect in 103 (INFERRED data, CONFIRMED rule, hero standing on one of the 8 neighbour cells of the target, list = file order = uid order):** the rule of §3 returns the
structure the player clicked only in these cases; otherwise the uid shown toggles instead.

| Target | Hit when the hero stands | Else toggles |
|---|---|---|
| 1, 2, 3, 4, 5, 6, 12, 13-16 | on any neighbour | - |
| 7 (25,73) | east side (x = 26) | 6 |
| 8 (28,75) | **never** | 1 |
| 9 (28,81) | only SE (29,82) | 2 (N, W, NW, NE...) or 3 (SW, S) |
| 10 (22,81) | east side (x = 23) | 4 |
| 11 (19,78) | **never** | 5 |

The set of required toggles stays reachable (4 and 6 from anywhere, 7 from the east, 9 from the SE neighbour; 8 and 11 must stay off and cannot even be reached),
which fits the solution; whether the designers meant this is unknown. In maps 93-96 and 75 the pair/the two switches are alone (75: the switches are not read by any script;
uid 10 (81,106) is hit from W and N sides, uid 11 (94,101) from the east neighbour only partly because other structures lie within 2).

## 7. Other classes (for K8)

| Class | Behaviour | Formula / state |
|---|---|---|
| Well 2 (15) | +100 health per use, 3 uses | HP 3 -> 0 on `+0x42`; potion "Potion Big Healing" through the item use path ([items](../data/items.md)); empty well just stops |
| Well 3 (16) | +100 mana per use, 3 uses | "Potion Big Mana" |
| Signposts (70-75) | run instant at `+0x6c` when `> 0` (message 2 -> `0x433` story text) | repeatable; map.md section 11 `enabled`, `n` |
| Altars (76, 77) | toggle HP 0 / 1 and the picture | cosmetic; no script reads them |
| King's Graves (39, 40) | no effect | 18 + 37 placements; hover cursor, walk, stop |
| Shops / inns / church | multiplayer; not reached in the campaign | messages `0x83`, `0x84` |

## 8. Engine design notes (what to implement now)

1. **Command / order `use`**: unit order `0xf`, destination = top-left cell + (0, 0) / (1, 1) / (2, 2) by W (1-2 / 3-4 / 5+), range 1 / 2 / 3; arrival = facing equals the facing to the
   destination (the existing turn state) and Chebyshev <= range; on arrival tick T: run the use once, tick T+1: stand (order `0xc`). Hero-only is a **client** rule (cursor `town`
   with a single hero selected); the server accepts any unit and structure.
2. **Use step** `use_structure(unit)`: lookup A (`(x-1, y-1)`, first structure of creation order within Chebyshev 2) -> pointer: run instant `+0x6c` if `> 0`; type 28 / 29 / 76 / 77: `hp = 0 if hp else 1`, send the HP to the view;
   then lookup B (own cell): type 15 / 16 with HP > 0: HP -= 1, apply health / mana +100 (capped).
3. **View**: HP is the only state (`MapObject.hp`); draw destroyed art for `hp < 1` of a non-Indestructible structure (existing logic). No restamp, no pathing change.
4. **Scripts**: check 21 / instant 26 already exist; K6 needs only the writer. Instant 26 does not tell the view (keep that).
5. **Tests**: the pair on maps 93-96 (use both -> trigger 1 fires within 16 ticks, teleporter trap placed); map 103 puzzle A + B (checks of §6), wells (3 uses, +100 capped, 4th nothing), signpost (instant each time), altar toggle, grave no-op, lookup quirk (a unit next to switch 8 toggles uid 1).
6. Coverage keys: `use.scripted`, `use.switch`, `use.altar` are K6 (the altar is the same toggle); `use.well`, `use.pointer`, `use.grave` K8 (grave = hover and walk only).

## Open questions

* The client side of state `0xf` (the use animation / sound / facing of the hero): not seen in `FUN_0050f12c`; check the unit draw and message `0x7a` for state `0xf`.
* Which of the two client writers `0x410b13`, `0x412ade` is the `0x82` handler (and whether the other is the combat HP message `0x73`).
* The meaning of `FUN_0044fff0(0x68f628) == 4` for the "Saving Place" branch (probably a game-type value) and the `FUN_0050155f` chain (save UI); no campaign map has the type.
* `FUN_00522fab` / item `vtable+0x38` and `FUN_00510883` in detail: what happens when the inventory is full or the potion's use returns null (the code adds the item to the inventory only when the use returns non-null: INFERRED).
* Real hero stop cells (pathfinder end of a move with range 1 to a blocked cell) decide which switch the lookup of §3 hits in map 103; check against the engine's own planner and, if possible, in game.
* Several selected units with command `0x24` (the order goes to the last id resolved in the loop; the client sends one hero).
