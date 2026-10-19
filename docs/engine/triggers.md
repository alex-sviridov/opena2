# Scenario triggers (map section 7 at run time)

The map's script: **checks** compute numbers, **triggers** compare pairs of them and run up to four
**instants** (actions). File layout: [map part 6](../formats/map.md#part-6-scenario-triggers-repop-inns--shops--signposts-music).
Engine: `engine/sim/triggers.py` (§8). Tags: CONFIRMED = read in the GOG `allods2.exe` at the routine
given; INFERRED = names from the editor's `Description Checks.ini` / `Description Instants.ini` (install
root) or data patterns. Server object = `DAT_0066832c` (`S` below).

## 1. Overview (CONFIRMED)

| Step | When | Routine |
|---|---|---|
| compile section 7 into runtime checks, instants, triggers | map start (`FUN_005606aa` `0x560c53`, also resets the squads' group orders) and save load (`0x4ecef2`, no reset) | `FUN_00562745(_, reset)` |
| evaluate every check, then every trigger, run the instants of those that hold | the group pass `FUN_0056fe4d` at `tick & 15 == 6` (every 16 ticks), **after** the awake recompute `FUN_0055b5f1` and **before** the group handlers `FUN_00570087` | `FUN_0057485b`: `S+0xd720 += 1`, `FUN_00574899` (checks), `FUN_00574ba1` (triggers), `FUN_0057b2b0` (clears the write-only event list `S+0xbbec`, [ai §8](ai.md#8-hit-reaction-fun_0056e6b8attacker-victim-0-confirmed)) |
| victory / defeat of the human | end of the step whose counter after the increment is `15 mod 16` | `FUN_004f8967` -> `FUN_004f8922` -> `FUN_004f856a(player)` (§6) |
| a signpost's instant | when a unit uses it (state `0xf`) | `FUN_0050f12c` `0x50f944` -> `FUN_00574f3f` |
| a repop record's instant | scripted squad creation | `FUN_00560d9b` `0x561219` |

State (all in `S`, saved by `FUN_0057468d`): `+0xc784` **values**, 1000 × i32 (check results, constants and
script variables share it); `+0xe6c4` **fired** flags, 1000 bytes (one per trigger); `+0xbe0c` mission
complete counter, `+0xbe10`, `+0xbe14` mission fail cause; `+0xc710`, `+0xd59c` stage counters; `+0xd724`
the variable-reference table (only read, never written: §2.3).

## 2. Compilation at map start (`FUN_00562745`)

### 2.1 Look-up tables (CONFIRMED `0x5627ac`-`0x562a58`)

Maps built first: structures by `+8` (the uid) from the compiler object's `[this+0x24]` list; creatures by `+8`
(scenario uid) from the creature manager `0x68d2dc`, `[this+0x24]+0xc` and every player's unit list `+0x24`; players by `+8` from the
player manager `0x68d2c4`; **groups by `+0x1c` = squad number** from every player's group list `+0x28` (a
later player overwrites an earlier one's equal number; no install map shares a number). With `reset` and in
single player each squad of player 1 (`group+0x44` -> id 1, the human) gets `FUN_00570f2b` (stand ground) and every
other squad `FUN_00570aba(g, 0)` (order `0x12`, [ai §2](ai.md#2-group-record-and-set-up-confirmed)).

Resolution (each failure logs and makes the record fail, §2.4):

| Kind | Resolver | Rule |
|---|---|---|
| 4 unit | `FUN_00562274` | `< 10001`: creature map by uid ("Can't resolve unit %d"); `10001..11000`: hero `k = id - 10001` = `FUN_00562518(k)`: only in single player, only when the local player has a main hero (`+0x38`), the first unit of the player's list (`+0x24`) with `(u16)(+0x14c) - 0x15 == k`, else the same test over all creatures whose name `+0x80` is non-empty (`FUN_004029a0` = `CString::GetLength` of `creature+0x80`; every named non-matching creature also makes the loop skip the next creature, see §9.5) ("Can't resolve hero %d"); `>= 11001`: a name from the table at `0x5f42f4` (`FUN_0056236c`, unused) |
| 2 group | `FUN_005626bc` | group map ("Can't resolve group %d") |
| 3 player | `FUN_00562633` | player map ("Can't resolve player %d") |
| 9 building | inline | structure map ("Can't resolve building %d.") |
| 8 item | inline | `+0x6c` (u16) := value + `0xe18` (special item, class 14, index value + `0x18`) |

`+0x14c` is the human's reduced server id (`(v / 10) % 1000`, [units](../data/units.md)): `Start_*` 21 ->
hero 10001 (the main hero), `Fighter_Hero` 22 -> 10002, `Mage_Hero` 23 -> 10003 (CONFIRMED arithmetic;
the party is placed at map start, not in the map file, §9).

### 2.2 Runtime record (instants and checks share it, CONFIRMED by the writes)

| Off | Meaning |
|---|---|
| +0x00 | runtime index (instants: position among compiled instants; checks: the value slot) |
| +0x04 | type |
| +0x08 | 10 × i32 numeric arguments **packed**: every argument of a kind other than 2, 3, 4, 8, 9 (so also the empty kind-0 slots) is appended in slot order |
| +0x30 | 10 kind bytes (slot order) |
| +0x3a, +0x44, +0x4e, +0x58 | variable references: per slot 1 (`8xyy`) / 2 (`9xyy`), `x`, `yy`; count |
| +0x5c / +0x60 / +0x64 | first unit / group / player |
| +0x68 | the **second** object of any of these kinds (shared slot) |
| +0x6c | u16 item code |
| +0x70 | building |
| +0x74 | checks: file `+0x318` (default 1); not read by any trigger routine (bounded search `0x573000`-`0x57c600`) |
| +0x78 | checks: number of trigger pairs naming it (written by the trigger pass of the compiler); no reader found |

Side effect (CONFIRMED `0x5632b0`-`0x563157`, `0x5639a5`-`0x563a3b`): the squad of the first resolved group
argument, else of the second; and the squad (`creature+0x70`) of the first resolved unit, else of the second,
get GroupAI record `+0x48 := 1` (**kept awake**, [ai §15.1](ai.md#151-the-awake-map-confirmed)), for every
instant and for every check **except check type 1**.

### 2.3 Variable references (CONFIRMED, unused)

A group / player / unit argument with value 8000..9999 is not resolved; at run time `FUN_00574f3f` replaces the
object with `S+0xd724[yy]` (first group -> `+0x60`, else `+0x68`; first player -> `+0x64`; first unit ->
`+0x5c`). Nothing writes `+0xd724`, and `FUN_00574899` **never evaluates a check with a variable reference**
(`+0x58 != 0`). No shipped map uses one.

### 2.4 Indices and failures (CONFIRMED)

* Instants: records of type `0x10002` ("Drop Location") are not instants: `CWordArray::Add(this+0x28, y << 8 | x)`
  (a list of party drop cells; consumer `FUN_004f2c83`, §9). Other records get consecutive runtime indices; the map
  `id -> index` is set only on success, so a trigger naming a failed (or missing) instant gets the default
  **index 0** of the `CMap` (runs instant 0 instead: quirk).
* Checks: every record gets the slot = its position counter; a constant (`0x10002`) only stores `values[slot] =
  value` and counts; a failed check maps its id to **slot 0** and does not advance the counter, so the next
  check takes its slot.
* Triggers: an element with first check id 0 is skipped; else each pair `k` with both ids non-zero becomes
  `(slot a, slot b, op k)`, each non-zero instant id `(> 5000` logs "Reference to suspicious instant")`
  its runtime index, plus the `once` flag and the element's position (the fired-flag index).

## 3. Checks (`FUN_00574955`, value into `values[slot]`)

`n[i]` = packed numeric argument `i` (`+0x08 + 4i`), `u` = unit `+0x5c`, `u2` = second unit `+0x68`, `d(a, b)` =
`FUN_00551463` = **Chebyshev** `max(|dx|, |dy|)` of the cells (a byte). State `0x10` = removed (dead after the
dying countdown, [combat §12.3](combat.md)). All CONFIRMED at the routine; names INFERRED from the editor.

| Kind | Editor name | Routine | Value |
|---|---|---|---|
| 1 | How many units contains this group | `576fc8` | group member count (`FUN_0044fc20` = list `+0xc`); a unit leaves at its removal, when the player gives it a command (a new group) or when its owner changes |
| 2 | Is unit in a box | `577030` | `n0 <= x <= n2 and n1 <= y <= n3` -> 1, else 0 |
| 3 | Is unit in a circle | `5770d1` | `d(u, (n0, n1)) <= n2` -> 1, else 0 (a Chebyshev square) |
| 4 | Get unit parameter | `5771a8` | `n0 == 6`: HP (`+0x94`, s16); any other parameter: the slot keeps its value |
| 5 | Is unit alive? | `576fef` | 0 if state `0x10`, else 1 (a dying unit, HP <= 0, is alive) |
| 6 | Distance between units | `577268` | `d(u, u2)`, `0xff` if either is in state `0x10` |
| 7 | Distance from point to unit | `57714d` | `d(u, (n0, n1))` |
| 8 | How many units this player have | `5771e4` | members of all groups of the player (`+0x28`) |
| 9 | Is unit make attack | `577300` | Brain mode (`brain+8`) 5: the target's uid (`(brain+0xc)+8`), else 0 |
| 10 | Get diplomacy | `577359` | `M[p1][p2] & 3` (`S+0xa8c4 + id1 * 0x46 + id2`: 1 war, 2 alliance) |
| 11, 13 | - | `57739d`, `5773f9` | nothing (the slot keeps its value) |
| 12, 17 | Item in inventory | `5773aa`, `5775b1` | 1 if the unit's inventory (`+0x7c`, `FUN_00529ee5`) holds an item with code `+0x6c` (item `+0x40`), else 0 |
| 14 | Get sack | `577406` | 1 if a sack (cell record `+0x10`, cell flag `0x20`) lies on `(n0, n1)` |
| 15 | Distance to nearest units of player | `57745b` | min `d((n0, n1), m)` over the members of all the player's groups; `0xff` none |
| 16 | Item to point | `577527` | the unit holds the item: `d(u, (n0, n1))`, else `0xff` |
| 18 | VIP | `577600` | no value: if `u` is in state `0x10`, the fail cause `S+0xbe14 += 1` (every evaluation, so the cause grows by 1 per 16 ticks) |
| 19 | Return value of variable | `57762e` | `values[n0]` |
| 20 | How many buildings this player have | `57765c` | objects of the list `[0x6044c4+0x7c]` with owner `+0x14` = player and HP (`+0x42`, s16) > 0 |
| 21 | Health of building | `5776d7` | building HP `+0x42` (s16) |
| 22 | Teleportation | `5776fd` | a unit standing on `(n0, n1)` (cell record `+4`) is moved to `(n2, n3)` (`FUN_0055a96c`) -> 1, else 0: a check with a side effect, unused |
| 23 | Get Scenario Variable | `57777b` | `ScenarioGetVar(n0)` (Scenario.dll ordinal 1, `[0x62729c]`) |
| 24 | Get Subobjective | `5777a4` | `ScenarioGetVar(n0 + 0x2f0)` |
| 25 | Spell on Tile | `5777d3` | 1 if the cell `(n0, n1)` has an area effect in layer `n2` (cell record `+0x14`, 6 layers) |
| 26 | Spell on Unit | `577857` | 1 if `u+0x144` bit `n0` (effect kind) is set (bit 12 = Invisibility) |
| 27 | Centered on Tile | `5778ad` | `x == n1 and y == n2` and at the cell centre (sub-cell 128, 128) -> 1: the routine reads `n1`, `n2` although X, Y are packed as `n0`, `n1`, so it tests `x == Y and y == 0` and is never true (quirk; unused) |
| `0x10002` | Constant / TRUE / FALSE | compiler | `values[slot] = value` once |

Order: `FUN_00574899` walks the compiled checks in file order and evaluates those without a variable reference.
Scenario.dll's `ScenarioGetVar` / `ScenarioSetVar` (ordinals 1, 2) read / write an i32 array at `0x10036028`
(CONFIRMED, `objdump` of `Scenario.dll`: `mov eax, [eax*4+0x10036028]`); its initial values and campaign use
(`ScenarioNewGame`, `ScenarioLoad`, `ScenarioSave`) are not decoded. Another writer: the client sets variable `0x213 + server id` to 0
when a unit of server id `< 0x15` reaches death stage 2 (`0x41050f`, [combat §12](combat.md)); not modelled.

## 4. Instants (`FUN_00574f3f`)

`n[i]`, `u`, `u2` as in §3; `g` = group `+0x60`, `p` = player `+0x64`. All CONFIRMED at the routine.

| Kind | Editor name | Routine | Effect |
|---|---|---|---|
| 1 | Increment mission stage | `57792a` | `S+0xc710 += 1`, `S+0xd59c += 1` (no other reference than the server ctor: scan of both offsets) |
| 2 | Send message | `577c48` | server message `0xb6` value `n0` (`FUN_00505204`): the client posts window message `0x433` with `wParam = n0` ([combat §12.3a](combat.md)); `0xff` would open the defeat dialog |
| 3 | Set value to variable | `577c6a` | `values[n0] = n1` |
| 4 | Force "Mission Complete" state | `577cb0` | `S+0xbe0c += 1` |
| 5 | Force "Mission Fail" state | `577cd2` | `S+0xbe14 = n0` (the cause) |
| 6 | Group Command | `577cee` | sub-command `n0` on `g`, below |
| 7 | Set formation | `577c8d` | `FUN_005737ba(p, n0)` (not traced; unused) |
| 8 | Increment variable | `577c18` | `values[n0] += 1` |
| 9 | - | `577e9f` | nothing |
| 10 | Change diplomacy | `577eac` | `M[n0][n1] = (M[n0][n1] & 0xfc) + n2` (byte, **one direction**: players are numbers, not objects), then `FUN_00504e87(pl)` (client relation update) for every player `n0` or `n1` |
| 11 | Give item from one unit to another | `577f8d` | take item `+0x6c` from `u` (`FUN_00529f3f`), send `u`'s inventory; if found give it to `u2` (`FUN_00529ac2`) and send |
| 12 | Add item to unit's inventory | `57800b` | create item `+0x6c` (`FUN_004fbf01`), add to `u`, send |
| 13 | Remove item from unit's inventory | `578066` | delete item `+0x6c` of `u`, send |
| 14, 15 | - | `5781c4`, `5781f1` | `FUN_00502d67(u, owner, 0xffb)` (client object refresh; unused) |
| 16 / 17 | Phase out / in unit | `57821e` / `578236` | out (`FUN_005102a3`, only if `+0x4c & 8` is clear): leave the cell, `+0x4c |= 8`, leave the creature list (no ticks), clients told; the unit stays in its group and the owner's list. In (`FUN_005103ae`, **no test of the flag**): place it with `FUN_00510089(own cell, r = 0)`, else `r = 3` ("Unit can't return to map - no free place"), append to the creature list (end of the update order), clear the flag |
| 18 | Polymorph unit | `57824e` | phase out `u`, then put `u2` with `FUN_00510318(u's cell, r = 3)` (`FUN_00510089`, creature list, flag cleared) |
| 19 | Change unit's owner | `578291` | `FUN_004f0568(u, p)`: leave group and owner list, owner := p, new group (0x50, `FUN_0052ae43`) with the unit, `FUN_00570f2b` (cancel + stand ground), vision bits `+0x18` of both players cleared, `+0x204 = 1` |
| 20 | Drop all | `578330` | `FUN_005109f5` drops `u`'s inventory, a new empty one (0x24 bytes) |
| 21 | Make spell effect | `5783be` | `FUN_004f086f(n0, n1, n2, n3, spell n4, power n5 or 99 when 0)`: a spell from cell to cell |
| 22 | Change group's owner | `5782ba` | instant 19 for every member of `g` (the loop removes the current member from the list it walks) |
| 23 | Give money to player | `57830f` | `p+0x3c += n0` (the player's gold), message `0x67` to the client (`FUN_00516238`) |
| 24 | Cast spell to unit | `578440` | `FUN_004f0832(n0, n1, u, spell n2, power n3)` |
| 25 | Set trap | `57847e` | cell `(n2, n3)` gets record `{n0, n1, sx, sy, tx, ty}` (`FUN_0055ba36`; with `n4 == 0` source and target = the trigger cell) |
| 26 | Set building's health | `57855f` | building `+0x42 = n0` |
| 27 | Teleport unit | `57857d` | `FUN_0055a96c(u, n0, n1)`; a computer-owned unit re-anchors (`FUN_0056d4ba`) |
| 28 | Give All | `5785cb` | `u`'s whole inventory goes to `u2` (`FUN_00529e5b`), `u` gets an empty one, both sent |
| 29 | Tile Spell Duration | `578696` | the area effects of spell `n2` on `(n0, n1)` get duration `+0x50 = n3` |
| 30 | Unit Spell Duration | `57871f` | the effects of spell `n0` on `u` (`+0x20` list) get duration `+0x42 = n1` |
| 31 | Repop Delay | `57877d` | objects with `+0xac == n0` (outposts) get `+0xb4 = n1` |
| 32 / 33 | Phase Out / In Group | `5787f2` / `578836` | 16 / 17 for every member of `g` |
| 34 | Set Unit Parameter | `57887a` | `n0`: 6 HP `+0x94`, 15 defence `+0xbe`, 16 absorption `+0xc0` := `n1`; then the client update |
| 35 | Set Scenario Variable | `577961` | `ScenarioSetVar(n0, n1)` |
| 36 | Set Subobjective | `577b16` | sub-objective `v = Get(n0 + 0x2f0)`: `n1 == 1`: if `v == 0` set 1; `n1 == 2`: unless `v == 4`, message `0xfd` when `v & 2 == 0`, set 3; `n1 == 4`: message `0xfe`, set 5; other: set `n1` |
| 38 | Remove item from everybody's inventory | `5780de` | item `+0x6c` deleted from every unit of the list `[S+0xa50]+0xa456c` that has it |
| 39 | Suspend group | `5781a7` | GroupAI record `+0x48 := 0` (the squad may sleep again) |
| 37, others | Set music node, … | default | "Script: Bad instant %d." (logged, no effect) |

**Group commands** (instant 6, `FUN_00577cee`; `n1`, `n2` after the constant; [ai §14](ai.md)):

| `n0` | Editor | Setter | Group order |
|---|---|---|---|
| 1 | Guard | `5709d9(g, n1)` | 1, radius `n1` |
| 2 | Swarm | `5708bc(g, n1, n2)` | 2 go and hold |
| 3 | Stand Ground | `570b8b(g)` | 3 |
| 4 | Move | `5703c0(g, n1, n2)` | 4 |
| 5 | Swarm 2 | `57063e(g, n1, n2)` | 5 |
| 10 | Attack | `570946(g, u)` | 0: members whose score `FUN_005711ea` is not `0xffffff` attack `u` (`FUN_0056d1be`), the others are stopped |
| 11 | Defend | `570c84(g, u, n1)` | 0: members follow `u` at range `n1` (`FUN_0056d5b9`, unit order 8) |
| 14 | Patrol | `570d26(g, n1, n2)` | 0: members `FUN_0056d6b7(m, n1, n2)` |
| 15 | Follow | `570cd5(g, u, n1)` | 0: members `FUN_0056d638(m, u, n1)` |
| 17 | Roam | `5708ff(g)` | `0x11` wander |
| 18 | Dwell | `570aba(g, n1)` | `0x12`, radius `n1` |

Every setter first cancels the members (`FUN_00570e83`). Install use: 1 ×1, 3 ×8, 4 ×20, 5 ×32, 10 ×1, 11 ×7,
14 ×19, 15 ×14.

## 5. Triggers (`FUN_00574ba1`)

For each compiled trigger in file order (CONFIRMED):

1. if `once` and `fired[i]`: skip;
2. `fired[i] := 0`; the pairs are tested in order with `values[a] op values[b]` (signed); an unknown operator
   is false; the first false pair ends the test;
3. all true (also when the trigger has no complete pair): `fired[i] := 1`, debug line "Script: Trigger %d
   ( %d ifs, %d instants )." when the option is on, then the instants in slot order.

So `once` triggers fire at the first pass their condition holds; the others fire at **every** pass (each 16
ticks) while it holds. Instants run immediately, so a later trigger in the same pass sees variables an earlier
one set, but check values are those computed at the start of the pass.

## 6. Victory and defeat (`FUN_004f856a`, CONFIRMED)

For every player with `+0x41 != 0` (INFERRED "in the game": written 1 at `0x4f2109` in the map-start routine `FUN_004f1d9c`)
and `+0x2c == 0` (human), when the mission
state byte `+0x40 < 2`:

1. no main hero (`+0x38 == 0`) or the main hero's death flag (`+0x13c`: its HP <= 0 branch has run) ->
   `+0x40 := 2`, message `0xb4` (value 2): the defeat dialog;
2. else if `S+0xbe14 >= 1` (fail cause) -> log "Logic - Mission Failed", message `0xb4` with the cause,
   `+0x40 := cause` (byte);
3. else if `S+0xbe0c != 0` and `+0x40 != 1` -> log "Logic - Mission Complete", message `0xb5`, `+0x40 := 1`.

`+0x40` is the same byte the hero death writes (`server_id - 0x13`, [combat §12.3a](combat.md)). A failure is
therefore checked before a completion, and a completed mission (`+0x40 == 1`) can still fail afterwards. The
client: `0xb4` (any value) = the modal "load / quit" dialog (combat §12.3a); `0xb5` -> window message `0x430`
(`0x486ddb`): if `ScenarioGetVar(0x300) > 0x77` it posts `0x41d` at once, else it opens a modal text dialog
(text entry `0x8c`, the defeat one is `0x8d`; registered with `FUN_0048b33b`, so the simulation freezes) and
plays sound 14 / `0xdc`. What `0x41d` and the dialog's buttons lead to (the next mission / world map) is not
decoded.

## 7. Answers to the old questions

* **"Unit attacked / killed / group attacked"**: there is no attacked condition. Scripts read creature state:
  **killed** = state `0x10` (checks 5, 6, 18: set when the dying countdown has run out and the body is removed,
  [combat §12](combat.md); a dying unit is still "alive"), **group dead** = member count 0 (check 1, the count
  drops at the removal), **attacked** = the HP (check 4, parameter 6) or "is unit make attack" (check 9 = Brain
  mode 5 with its target). The event list `S+0xbbec` is not used (CONFIRMED).
* **8000-9999 slot codes** of section 7: variable references (§2.3), unused. Section 11 is keyed by structure uid.
* **Do triggers name only structures?** No: units by scenario uid (or hero index), groups by squad number, players
  by record number, structures by uid (kind 9: checks 21, instants 26), items by special-item index.
* **Victory / defeat**: §6.

## 8. Engine (`engine/sim/triggers.py`)

`triggers.enable(world, map)` compiles `Map.scenario` like §2 into `world.script` (a `Script`) after `ai.enable`
(the squads and their map-start orders are part of the exe's compiler); `Simulation(world, triggers=True)`
(implies `ai=True`) runs it. Off by default: no system, no state, the dump and every golden are unchanged.

* **Pass**: `ai.ai_system` calls `triggers.run_pass(world)` between `ai.wake` and the squad handlers at
  `tick & 15 == 6`; `triggers.mission_system` (the last system of the step) runs §6 when `(tick + 1) & 15 == 15`.
* **References** are the objects resolved at map start, as the exe's pointers: `Unit` objects (a removed unit
  keeps `state == DEAD`), `TriggerGroup` (the squad's units at map start; a member counts while it is not `DEAD`,
  still in the command group it had at map start (a player command or an owner change moves it out) and of the
  same owner; phased-out members still count), `Player`, the structure `MapObject`. `Script.values` / `fired`
  are the 1000 slots, `Script.errors` the compiler's messages, `Script.trace` the fired triggers and run instants.
* **Implemented** checks: 1-21 (11 and 13 do nothing), 23, 24 (`Script.scenario_vars`, empty at map start), 26 for bit 12
  (`Unit.hidden`), 27 and the constants; the item checks read `Unit.carried` (the section 8 pack: the engine's
  only inventory, INFERRED equal to the exe's until pickup and give exist). Instants: 1-6 (group sub-commands
  1-5, 17, 18 through `ai.set_group_order`), 8, 9, 10, 16-19, 22, 23 (`Script.gold`), 26, 32, 33, 34 for
  parameter 6, 35, 36, 39; unknown kinds log "Bad instant"; drop locations go to `Script.drops`.
* **Not implemented** (counted in `Script.unsupported`; `enable(..., strict=True)` raises `NotImplementedError`):
  checks 22, 25 and 26 for other bits; instants 7, 11-15, 20, 21, 24, 25, 27-31, 34 for parameters 15 / 16, 38;
  group sub-commands 10, 11, 14, 15; variable references; units by name (`>= 11001`).
* **Phase out / in**: the unit leaves `world.units`, the spatial index, its command group / squad record and the
  selections into `Script.phased` and stays a `TriggerGroup` member; phase-in draws the `FUN_00510089` tries
  from `world.rng` (radius 0 draws nothing), puts the unit at the cell centre with no step in progress, appends
  it to `world.units` (the update order) and back into its group in creation order; "free" = not blocked for its
  mover and no unit on the cell (INFERRED: `FUN_005563ca` -> `FUN_0055c5a0` not decoded). Phase-in of a unit on
  the map (the exe inserts it into the creature list twice) is logged and skipped (DECISION).
* **Owner change**: `triggers.change_owner` = `FUN_004f0568` with a new `OrderGroup` under stand ground (the exe
  allocates the group without deleting the owner's empty ones); the unit leaves every selection (INFERRED).
* **Mission**: `Player.death_code` is the `+0x40` byte; §6 sets it, `Player.defeat_dialog` (message `0xb4`) and
  appends `MissionFailed` / `MissionComplete` (`0xb5`) to `world.events`; instant 2 and the sub-objective
  messages append `ScriptMessage`. No dialog or message text is drawn yet.
* **The campaign maps have no party**: heroes 10001-10003 come from the player's roster, placed at the drop cell at map start (§9).
  `enable(world, m, assets=...)` runs `engine.party.place_party` first when the map has a drop cell and the human has no main hero
  (`engine run --triggers` passes the assets; `--party N`, default 0 = as many heroes as the script names, DECISION: the save that
  carries the recruited heroes is not read). Without the party a record naming a missing hero fails and maps to slot / instant 0 (§2.4),
  which made some conditions true at once (maps 52, 80, 102 reported a mission complete within 200 ticks); a fresh start with only
  the main hero (`party=1`) still does that on maps whose scripts name 10002 / 10003, as in the exe.
* Tests: `tests/test_engine_triggers.py` (synthetic, one per rule), `tests/test_engine_party.py` (synthetic, the placement),
  `tests/test_engine_triggers_maps.py` (the 46 scripts compile with the placed party; no fake completion on maps 52, 80, 102; map 10
  sends message 1 at tick 6 and replays; `needs_data`).

## 9. The party at map start (`FUN_004f2c83`)

Reconstructed from the GOG exe (sha256 in [formats/README](../formats/README.md)); the map file holds no hero of the human.

### 9.1 Chain (CONFIRMED unless noted)

1. `FUN_005606aa` (map load, caller `0x4eba14`) loads the map, runs `FUN_00561bf9` (the map's units: placed by `FUN_00510089(x, y, 0)`,
   added to the owner's list; difficulty tweak, [progression](../data/progression.md)), `FUN_00562745` (script compile: the drop cells
   go into the word array `game+0xc0` = scenario object `+0x28`, `CWordArray::Add(y << 8 | x)`, §2.4) and `FUN_00564072`.
2. The human's **roster** is the player's unit list `player+0x24` and the main hero `player+0x38`, both built *before* the map load
   (hero refs of §2.1 search that list, so the scripts compile against units that are not yet on the map): from the campaign player
   record (`FUN_004ea472` -> `FUN_004ea6ab`, writer `0x4eab4a`) or, for a fresh character, `FUN_004f254b` (§9.3).
3. The ready message (net message type **4**, jump table `0x4f82da` index 1 = `0x4f7ea3`; posted by `FUN_0041c50d(flag)`, the UI window
   routine `FUN_0048c8a3`) calls `FUN_004f1d9c(player, flag = (msg+0xa == 0))`: no main hero is an error ("Oops ... no main hero",
   `0x5fca60`); with `flag` set and `player+0x41 == 0` it calls **`FUN_004f2c83(player)`**, then sets `+0x41 = 1`. Single player runs through
   the same message queue (`0x6831a8`); the exact SP poster of the type-4 message and its tick are not traced (INFERRED: before the first
   simulation tick).

### 9.2 `FUN_004f2c83(player)` (CONFIRMED, disassembly `0x4f2c83`-`0x4f3127`)

* Groups: the player needs a group (`player+0x28`, "Oops, player has no groups" creates one); empty leading groups are removed
  while more than one remains.
* **Cell**: single player (`game+0x74 == 0`): `n = size(game+0xc0)`; if `n > 0`: `i = rand(n - 1)` (`FUN_0051fa25`, uniform `0..n-1`,
  no draw when `n == 1`), `(x, y) = (word & 0xff, word >> 8)`; empty list: `x = y = 0`. A zero coordinate (`x * y == 0`) logs a warning and
  uses `x = rand(0x46) + 0x1e`, `y = rand(0x46) + 0x1e`. One cell for the whole party. (Multiplayer: `player+0xa6c` or the list.)
* **Radius** `r = ftol(max(5.0, sqrt(n) + 4.0))`, `n` = count of the player's unit list `player+0x24` (map-placed units included;
  constants `0x5d0830` = 4.0, `0x5d0838` = 5.0): 5 for n <= 3, 6 for n = 4..8, 7 for n = 9..15, ...
* For every unit of the list: skipped when it already stands on the map (`FUN_0055641c(map, unit+0x10) == unit`); else its position
  record is set to the cell (`FUN_0054f9b9`), then **the main hero** (`unit == player+0x38`) tries `FUN_00510089(x, y, 0)` (exact cell);
  every other unit, and the main hero when that failed, `FUN_00510089(x, y, r)` ([§8 `find_place`](#8-engine-enginesimtriggerspy)); a
  failure logs an error and the unit stays off the map. Then `FUN_0052b22a(unit)` (creature manager, update order), new brain objects
  (`+0x1c0` `FUN_00551346`, `+0x1c4` `FUN_00569003`, keeping the byte `+0x78`) and `FUN_00570f2b` (stand ground). Facing is not touched
  (the constructor's random angle stays; the engine hashes the uid, `unit_angle`).
* The order in the roster is the placement order: main hero first (it is created first), then the loaded heroes and units.

### 9.3 A fresh character `FUN_004f254b(player, str, dex, mind, spirit, school, flags)` (CONFIRMED)

Only when `player+0x38 == 0`. `flags & 0x40` clear/set and `flags & 0x80` clear/set pick the template: (clear, clear) **`Start_MF`**,
(clear, set) `Start_FF`, (set, clear) `Start_MM`, (set, set) `Start_FM` (the same map as the loader `0x4ea6ab`: `byte(+0x2c) & 0xc0` =
0 / 0x80 / 0x40 / 0xc0 -> MF / FF / MM / FM); `flags & 0x3f` is the name index (`FUN_00439eb0`). The four attributes `+0x84, +0x86, +0x88, +0x8a`
(body, reaction, mind, spirit) are the arguments when the point budget holds: `0x8c - sum(cost(v)) >= 0` with
`cost(v) = trunc(0.349 * (v - 1) ^ 1.15 + 0.5)` (`FUN_004f250e`, constants `0x5d0820`, `0x5d0828`), else all four are 25 (`0x19`). `FUN_00514f59(school, 20)`
then clears the five school skills, sets skill[school] = 20 and the shooting skill `+0xb2` = 10, recomputes the pools (`FUN_00513497`), sets the
best school `+0x23c` and replaces the weapon: school 1 Iron Long Sword, 2 Iron Axe, 3 Iron Mace, 4 Iron Pike, 5 Uncommon Wood Long Bow;
a mage gets a "Wood Staff" / "Uncommon Wood Staff" `{castSpell=<Fire Arrow | Ice Missile | Lightning | Diamond Dust | Drain Life>:1}`.
HP and mana start at the maxima; `unit+4` = a free network id (`FUN_004f8d90`, lowest free bit of the table `0x6c9628`), `unit+0x14` = the
player, a new command group (`FUN_0052ae43`), `player+0x38 := unit`, and **in single player (`game+0x74 == 0`) `+0x14c := 0x15`**, which makes it
scenario hero **10001**. `Fighter_Hero` / `Mage_Hero` (10002 / 10003) get `0x16` / `0x17` from their templates' reduced server id (units.md).
Callers: the creation message (type `0x48`, `0x4f6af6`), the multiplayer "invalid character" fallback (25 25 25 25, school 1; `0x4f7b2c`).

### 9.4 What the engine does (`engine/party.py`)

`place_party(world, assets, drops, count, start)` builds `count` heroes of the human (`Start_MF` unless `start`, then `Fighter_Hero`, `Mage_Hero`:
the templates as the maps use them, DECISION: the attributes of the creation screen are not modelled, so the template's own attributes
stand in for the player's choice), draws the cell as §9.2, places the main hero at radius 0 then 5.., the others at `r`, sets
`Player.main_hero`; uids `max(uid) + 1 + k` (DECISION; the exe's id is a free network id). `stand ground` is not issued (a human unit with no
order is idle either way, INFERRED). Fresh start = one hero; the recruited ones come from the save (open question).

### 9.5 The hero look-up filter (`FUN_00562518`, CONFIRMED `0x562518`-`0x562632`)

First loop: the player's list, `(u16)(+0x14c) - 0x15 == k`. Second loop (the exe's fallback for a hero that is not in the list, e.g. map 40's
`Mage_Hero` owned by player 3 until a script gives it to the human): all creatures with a non-empty name (`FUN_004029a0` is
`CString::GetLength(creature + 0x80)`; the list iterator is advanced once more after every named non-match, so the creature after it is
skipped). The engine searches the human's units only ([§8](#8-engine-enginesimtriggerspy)); the fallback is not modelled (INFERRED that the
campaign maps do not need it: scripts that name a hero not in the party change its owner first).

## Open questions

* `FUN_005563ca` / `FUN_0055c5a0` (the free-cell test of `FUN_00510089`).
* The party roster of a later map (hero state, recruited heroes, companions): the player record read by `FUN_004ea472` -> `FUN_004ea6ab`
  (blob parser `FUN_004ee7cb`), writer `0x4eab4a`; and the creation screen that sends message `0x48` (§9.3: default attributes, school, name).
* Where single player posts the ready message (type 4, `FUN_0041c50d` <- UI window `FUN_0048c8a3`) relative to the first tick; the "already on
  the map" test `FUN_0055641c` / `FUN_00551edb` of §9.2; the second loop of `FUN_00562518` for units by name (§9.5).
* The window message `0x41d` and the mission-complete dialog's buttons (`0x486ddb`); Scenario variable `0x300`.
* The text shown for message `0xb6` values (`0x433` handler, `event_%d`).
* Scenario.dll: initial variables (`ScenarioNewGame`), which variables the campaign reads (towns, missions).
* The loop of instant 22 over a list it modifies (`FUN_004f0568` removes the member): which members change owner.
