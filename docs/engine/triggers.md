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
| 4 unit | `FUN_00562274` | `< 10001`: creature map by uid ("Can't resolve unit %d"); `10001..11000`: hero `k = id - 10001` = `FUN_00562518(k)`: only in single player, only when the local player has a main hero (`+0x38`): first loop = the first unit of the player's list (`+0x24`) with `(u16)(+0x14c) - 0x15 == k`; second loop = the creature manager's list (`0x68d2dc + 4`, update order), see §9.5 ("Can't resolve hero %d"); `>= 11001`: a name from the table at `0x5f42f4` (`FUN_0056236c`, unused) |
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

Side effect (CONFIRMED `0x5632b0`-`0x563157`, `0x5639a5`-`0x563a3b`, re-read in `0x562f9e`-`0x5632f4`): after **each group argument** the squad of the first resolved group (`+0x60`), else of the second (`+0x68`), and after **each unit argument**
the squad (`creature+0x70`) of the second unit when the shared slot `+0x68` holds one, else of the first (`+0x5c`), get GroupAI record `+0x48 := 1` (**kept awake**, [ai §15.1](ai.md#151-the-awake-map-confirmed)), for every
instant and for every check **except check type 1**. Net effect: **every unit argument flags its squad** (the first when it is processed, the second as the slot holder), but of two group arguments **only the first** is flagged (the second is
looked at only when the first did not resolve, and the compile has failed then).

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
| 6 | Distance between units | `577268` | `d(u, u2)`, `0xff` if either is in state `0x10`; a **phased-out unit** (instant 16, `FUN_005102a3`: lifted from its cell, flag `+0x4c |= 8`, position untouched) is measured at its retained cell (CONFIRMED). Maps 93-95 phase their quest unit (27 / 51 / 50) out at the start and never in again, so the player walks to that cell ([effects §6.5](effects.md#65-script-access-check-25-instants-29-and-30-confirmed-engine-enginesimeffectspy); the tests walk the whole route to the win) |
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
| 25 | Spell on Tile | `5777d3` | 1 if slot `n2` of the cell record of `(n0, n1)` (`FUN_0055a82c(n0 + n1 * 0x100)`, 16-bit index; `+0x14 + 4k`, 6 layers: 0 Wall of Fire, 2 Poison Cloud, 3 Wall of Earth, 4 Light, 5 Darkness) holds a carrier. CONFIRMED a **live state read**: no spell or caster filter, no cast / impact event, true exactly while the carrier occupies the slot (an unstamp, a burnt cloud, a Wall of Earth that skipped an occupied cell all read 0). `n2` is not range-tested in the exe (`rec + n2 * 4`); the engine answers 0 outside 0-5 (DECISION: no map uses one) |
| 26 | Spell on Unit | `577857` | 1 if `u+0x144` bit `n0` (effect kind) is set (bit 12 = Invisibility) |
| 27 | Centered on Tile | `5778ad` | `x == n1 and y == n2` and at the cell centre (sub-cell 128, 128) -> 1: the routine reads `n1`, `n2` although X, Y are packed as `n0`, `n1`, so it tests `x == Y and y == 0` and is never true (quirk; unused) |
| `0x10002` | Constant / TRUE / FALSE | compiler | `values[slot] = value` once |

Order: `FUN_00574899` walks the compiled checks in file order and evaluates those without a variable reference.
Scenario.dll's `ScenarioGetVar` / `ScenarioSetVar` (ordinals 1, 2) read / write an i32 array at `0x10036028` (CONFIRMED, `objdump` of `Scenario.dll`:
`mov eax, [eax*4+0x10036028]`), 1024 entries. **Start values** (CONFIRMED, `ScenarioNewGame` `0x100033be`): `memset(array, 0, 0x1000)`, then variable
`0x300` (the chapter, `0x10036c28`) = 10; everything else 0 (so the 20 words at `0x214` that the DLL zeroes again are 0 too). The engine's
`Script.scenario_vars` starts with exactly `{0x300: 10}` ([§11](#11-the-end-of-the-mission-scenariodll-and-the-client-flow)); a save carries the array
([saves §6.3](../formats/saves.md)). Another writer: the client sets variable `0x213 + server id` to 0
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
| 22 | Change group's owner | `5782ba` | instant 19 for every member of `g`. **All members change** (CONFIRMED `0x5782ba`-`0x578309`: the MFC-style iterator `GetNext(POSITION&)` has already advanced to the next position when `FUN_004f0568` removes the current member, so none is skipped; every member gets a group of its own) |
| 23 | Give money to player | `57830f` | `p+0x3c += n0` (the player's gold), message `0x67` to the client (`FUN_00516238`) |
| 24 | Cast spell to unit | `578440` | `FUN_004f0832(n0, n1, u, spell n2, power n3)` |
| 25 | Set trap | `57847e` | cell `(n2, n3)` gets record `{n0, n1, sx, sy, tx, ty}` (`FUN_0055ba36`; with `n4 == 0` source and target = the trigger cell); what it does: [effects §10](effects.md#10-cell-record-effects-traps-and-the-hidden-caster-confirmed-engine-enginesimtrapspy) |
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
| 10 | Attack | `570946(g, u)` | 0: members whose score `FUN_005711ea` is not `0xffffff` attack `u` (`FUN_0056d1be`, unit order 3), the others are stopped |
| 11 | Defend | `570c84(g, u, n1)` | 0: members `FUN_0056d5b9(m, u, n1)`, unit order 8 (follow `u` within `n1`, attack what is near `u`) |
| 14 | Patrol | `570d26(g, n1, n2)` | 0: members `FUN_0056d6b7(m, n1, n2)`, unit order `0xa` (walk between the own cell and `(n1, n2)`) |
| 15 | Follow | `570cd5(g, u, n1)` | 0: members `FUN_0056d638(m, u, n1)`, unit order `0x11` (follow `u` within `n1`) |

The member orders, their executors and the engine are in [ai §14.2](ai.md#142-the-unit-orders-of-the-scripted-sub-commands-10-11-14-15-confirmed).
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
client: `0xb4` (any value) = the modal "load / quit" dialog (combat §12.3a); `0xb5` -> window message `0x430`; both dialogs, the end-of-mission
message `0x41d` and the buttons are decoded in [§11](#11-the-end-of-the-mission-scenariodll-and-the-client-flow).

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
* **Implemented** checks: 1-27 (11 and 13 do nothing; 22 teleports like instant 27; 25 reads `World.cell_fx` (`effects.tile_layer`), 26 `Unit.effect_mask`) and the constants; the item checks read `Unit.carried` (the mirror of the pack: CONFIRMED to search the pack only, [items](items.md#1-the-flow-confirmed-gog-allods2exe); K5). Instants: **all kinds of the exe** except variable references (`Script.unsupported`, T§2.3: never written) and unit names (`>= 11001`): 1-6 (group sub-commands 1-5, 10, 11, 14, 15, 17, 18 through `ai.set_group_order`, `orders.attack_group` and `follow.*`),
  7 (the player's formation byte, `Player.formation`), 8-10, 11-13 and 28 and 38 (items: `gear.give_item` / `remove_item` / `take_all`, the pack, [items](items.md)), 14 / 15 / 31 (nothing to change), 16-19, 20 (drop all: a pile on the unit's cell), 22, 23 (`Script.gold`), 26,
  27 (`teleport`: `FUN_0055a96c`), 32-36 (34 for the parameters 6, 15 defence, 16 absorption), 39; unknown kinds log "Bad instant"; drop locations go to `Script.drops`.
  21 and 24 (a scripted cast from a hidden caster, `traps.cast_at_cell` / `cast_at_unit`) and 25 (`traps.set_record`) are built ([effects §10](effects.md#10-cell-record-effects-traps-and-the-hidden-caster-confirmed-engine-enginesimtrapspy)). 29 and 30 are built (`effects.set_tile_duration` / `set_unit_duration`, [effects §6.5](effects.md#65-script-access-check-25-instants-29-and-30-confirmed-engine-enginesimeffectspy)); `Script.unbuilt` now only counts kinds with nothing to change.
* **Phase out / in**: the unit leaves `world.units`, the spatial index, its command group / squad record and the
  selections into `Script.phased` and stays a `TriggerGroup` member; phase-in draws the `FUN_00510089` tries
  from `world.rng` (radius 0 draws nothing), puts the unit at the cell centre with no step in progress, appends
  it to `world.units` (the update order) and back into its group in creation order; "free" = not blocked for its
  mover and no stamp on the cell ([§10](#10-the-placement-search-fun_00510089-and-the-free-cell-test), CONFIRMED). Phase-in of a unit on
  the map (the exe inserts it into the creature list twice) is logged and skipped (DECISION).
* **Owner change**: `triggers.change_owner` = `FUN_004f0568` with a new `OrderGroup` under stand ground (the exe
  allocates the group without deleting the owner's empty ones); the unit leaves every selection (INFERRED).
* **Mission**: `Player.death_code` is the `+0x40` byte; §6 sets it, `Player.defeat_dialog` (message `0xb4`) and
  appends `MissionFailed` / `MissionComplete` (`0xb5`) to `world.events`; instant 2 and the sub-objective
  messages append `ScriptMessage`. No dialog or message text is drawn yet.
* **Start order** (CONFIRMED, [§9.1](#91-chain-confirmed-unless-noted)): the exe compiles the script at map load (`FUN_004eb715`), posts the ready message from the
  game-start routine and the **first server step** applies it in its drain (counter 1, before the first group pass at counter 6), which places the party. The
  engine does the placement first and the compile second because the hero references need the units; nothing in the compile reads the map or draws
  from the rng, so the state at the end of `enable` equals the exe's state after the drain of step 1. `Player` "in game" (`+0x41`) is not modelled: the defeat
  pass of the engine runs for every human (the exe skips a player whose flag is 0, which only holds before step 1). The placement search and its free-cell
  test are [§10](#10-the-placement-search-fun_00510089-and-the-free-cell-test); `World.mission_complete` (message `0xb5`) feeds [§11](#11-the-end-of-the-mission-scenariodll-and-the-client-flow).
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
   (hero refs of §2.1 search that list, so the scripts compile against units that are not yet on the map): single player keeps the roster in server
   memory across the missions (`FUN_004ebd5f` at the end of each, [saves §4](../formats/saves.md#4-carry-over-between-campaign-maps-single-player-confirmed)) and
   creates the first hero with `FUN_004f254b` (§9.3, message `0x48` from the character screen); `FUN_004ea472` -> `FUN_004ea6ab` (the `.a2c` record) is the
   network path only ([saves §3.6](../formats/saves.md#36-building-a-hero-from-a-record-fun_004ea6ab-confirmed-order)).
3. The ready message (net message type **4**, jump table `0x4f82da` index 1 = `0x4f7ea3`) calls `FUN_004f1d9c(player, flag = (msg+0xa == 0))`: no main hero is an
   error ("Oops ... no main hero", `0x5fca60`); with `flag` set and `player+0x41 == 0` it calls **`FUN_004f2c83(player)`**; then always `+0x41 := 1`, `+0x43 := 1`,
   `S+0xc780 += 1` (`FUN_00573d34`, a write-only counter) and the awake recompute `FUN_0055b5f1`. **Who posts it (CONFIRMED)**: `FUN_0041c50d(flag)` has one caller, the
   game-start routine `FUN_0048c8a3(param_1)` at `0x48cb1a` (`param_1` = 0 for a new game, 1 for a loaded save, so `flag` = new game; a save restores positions
   and places nobody). Its order: server start `FUN_004eb715` (map load, script compile, counters := 0; only for a new game), UI set-up, the latches of the window
   object cleared (`0x48d886` is the tail), then `FUN_0041c50d(param_1)` and straight after it the **first server step `FUN_004f08c0`** (single player). The
   message is delivered synchronously into the server hub's queue (`FUN_0050164f`, [simulation §1.1](simulation.md)), so step 1 (`FUN_004f8521`: counter
   0 -> 1, drain `FUN_004f84c6`) handles it before anything else of that step: **the party is placed in the drain of the very first tick, after the script was
   compiled (the roster units exist but are not on the map) and before the first group pass (counter 6)**.

### 9.2 `FUN_004f2c83(player)` (CONFIRMED, disassembly `0x4f2c83`-`0x4f3127`)

* Groups: the player needs a group (`player+0x28`, "Oops, player has no groups" creates one); empty leading groups are removed
  while more than one remains.
* **Cell**: single player (`game+0x74 == 0`): `n = size(game+0xc0)`; if `n > 0`: `i = rand(n - 1)` (`FUN_0051fa25`, uniform `0..n-1`,
  no draw when `n == 1`), `(x, y) = (word & 0xff, word >> 8)`; empty list: `x = y = 0`. A zero coordinate (`x * y == 0`) logs a warning and
  uses `x = rand(0x46) + 0x1e`, `y = rand(0x46) + 0x1e`. One cell for the whole party. (Multiplayer: `player+0xa6c` or the list.)
* **Radius** `r = ftol(max(5.0, sqrt(n) + 4.0))`, `n` = count of the player's unit list `player+0x24` (map-placed units included;
  constants `0x5d0830` = 4.0, `0x5d0838` = 5.0): 5 for n <= 3, 6 for n = 4..8, 7 for n = 9..15, ...
* For every unit of the list: skipped when it already stands on the map (`FUN_0055641c(map, unit+0x10) == unit`: CONFIRMED = `FUN_00551edb(cell word of the unit's position)`,
  bit `0x20` of the static layer byte of the cell and the cell record's **ground occupant slot** (`rec+4`) equal to the unit; a flyer's slot `rec+8` is not read,
  a first-come loser holds no slot and would be placed again; engine `party.on_map`); else its position
  record is set to the cell (`FUN_0054f9b9`), then **the main hero** (`unit == player+0x38`) tries `FUN_00510089(x, y, 0)` (exact cell);
  every other unit, and the main hero when that failed, `FUN_00510089(x, y, r)` ([§10](#10-the-placement-search-fun_00510089-and-the-free-cell-test)); a
  failure logs an error and the unit stays off the map. Then `FUN_0052b22a(unit)` (creature manager, update order), new brain objects
  (`+0x1c0` `FUN_00551346`, `+0x1c4` `FUN_00569003`, keeping the byte `+0x78`) and `FUN_00570f2b` (stand ground). Facing is not touched
  (the constructor's random angle stays; the engine hashes the uid, `unit_angle`).
* The order in the roster is the placement order: main hero first (it is created first), then the loaded heroes and units.

### 9.3 A fresh character `FUN_004f254b(player, str, dex, mind, spirit, school, flags)` (CONFIRMED)

Only when `player+0x38 == 0`. `flags & 0x40` clear/set and `flags & 0x80` clear/set pick the template: (clear, clear) **`Start_MF`**,
(clear, set) `Start_FF`, (set, clear) `Start_MM`, (set, set) `Start_FM` (the same map as the loader `0x4ea6ab`: `byte(+0x2c) & 0xc0` =
0 / 0x80 / 0x40 / 0xc0 -> MF / FF / MM / FM); `flags & 0x3f` is the name index (`FUN_00439eb0`). The four attributes `+0x84, +0x86, +0x88, +0x8a`
(body, reaction, mind, spirit) are the arguments when the point budget holds: `0x8c - sum(cost(v)) >= 0` with
`cost(v) = trunc(0.349 * (v - 1) ^ 1.15 + 0.5)` (`FUN_004f250e`, constants `0x5d0820`, `0x5d0828`), else all four are 25 (`0x19`). `FUN_00514f59(unit, school, 20)`
in this order (CONFIRMED): free the old weapon, clear the skill words 1..5 (`+0xa8 + 2i`), `skill[school] = 20`, **then** the shooting skill `+0xb2` (= index 5) `= 20 / 2 = 10`
(so school 5, the bow, ends with 10, not 20; index 0 is only written by school 0), recompute the pools (`FUN_00513497`: pool[i] from skill i, 1..5), `+0x23c := school`, then the weapon by `+0x4c & 4`:
fighter (flag clear) school 1 Iron Long Sword, 2 Iron Axe, 3 Iron Mace, 4 Iron Pike, 5 Uncommon Wood Long Bow; mage (flag set) `[Uncommon ]Wood Staff {castSpell=<spell>:20}`
with the spell string (underscored, as data.bin) 1 Fire_Arrow, 2 Ice_Missile, 3 Lightning, 4 Diamond_Dust, 5 Drain_Life (all one staff, 20 charges); "Uncommon " only when the
unit type `+0xe` is 0x22 / 0x24 (`FUN_0053a5c0`: female; type = 0x21 / 0x23 + 1 for 'f', `0x514bc7`), a male mage gets the plain "Wood Staff". The preview `0x4919ff` calls the same
routine with level `0x14` (school 0 is first replaced by the template's own `+0x23c`, so the routine never sees 0); it differs from `FUN_004f254b` only in the setup: attributes are
written unchecked (no budget test, no 25 fallback) on a temporary `Start_*` unit.
HP and mana start at the maxima; `unit+4` = a free network id (`FUN_004f8d90`, lowest free bit of the table `0x6c9628`), `unit+0x14` = the
player, a new command group (`FUN_0052ae43`), `player+0x38 := unit`, and **in single player (`game+0x74 == 0`) `+0x14c := 0x15`**, which makes it
scenario hero **10001**. `Fighter_Hero` / `Mage_Hero` (10002 / 10003) get `0x16` / `0x17` from their templates' reduced server id (units.md).
Callers: the creation message (type `0x48`, `0x4f6af6`), the multiplayer "invalid character" fallback (25 25 25 25, school 1; `0x4f7b2c`).

### 9.4 What the engine does (`engine/party.py`)

`place_party(world, assets, drops, count, start)` builds `count` heroes of the human (`Start_MF` unless `start`, then `Fighter_Hero`, `Mage_Hero`:
the templates as the maps use them, DECISION: the attributes of the creation screen are not modelled, so the template's own attributes
stand in for the player's choice), draws the cell as §9.2, places the main hero at radius 0 then 5.., the others at `r`, sets
`Player.main_hero`; uids `max(uid) + 1 + k` (DECISION for the scenario uid; the exe's `unit+4` is a free id, kept in `Unit.net_id`: [combat §12.6](combat.md)). `stand ground` is not issued (a human unit with no
order is idle either way, INFERRED). Fresh start = one hero; `record=` (a decoded `.a2c`, `saves.Character`) builds the main hero from the record instead (`apply_record`, [saves §3.6](../formats/saves.md)); the recruited heroes of later maps are units that stay in the player's list (saves §4), a save restores them from the server stream (its creature serialiser is an open question).

### 9.5 The hero look-up filter (`FUN_00562518`, CONFIRMED `0x562518`-`0x562632`)

Single player only (`game+0x74 == 0`), and only with a main hero (`player+0x38`). First loop: the player's unit list `player+0x24`, `(u16)(+0x14c) - 0x15 == k`.
Second loop (the fallback for a hero that is not in the list, e.g. map 40's `Mage_Hero` owned by player 3 until a script gives it to the human): the **creature
manager's list** (`0x68d2dc + 4`, the update order). The iterator is MFC-style (`FUN_00562518` `0x53b070` / `0x53b0e0` = `GetNext(POSITION&)`): a creature
whose name `+0x80` is non-empty (`FUN_004029a0` = `CString::GetLength`) is tested; **after every named mismatch the iterator advances a second time, so the creature after
it is never looked at**; an unnamed creature is passed over without a test and without a skip. Which creatures are named (CONFIRMED by every writer of `+0x80`):
the constructor sets the empty string (`0x6ca2ac`); the hero name setters (call sites `0x4ead6b` in the .a2c loader, `0x4f2b4c` in the creation `FUN_004f254b`, `0x4f7e24` in the network handler) and the
creature copy (`0x50e81d`) assign names; the template parser `FUN_005145d1` ("Unknown" and the name tables `0x68f5f0` / `0x68d338`) writes the `+0x80` of the *unit type object*,
not of a creature. So the named creatures are the player heroes; a map unit has no name and is never found by the second loop (the campaign scripts need it only for
the cases where the first loop fails). Engine: `triggers.find_named_hero(creatures, k)` over `world.units` with `Unit.name` (set by `party.apply_record`;
a fresh `Start_*` hero has no name in the engine: the creation screen's name is not modelled).

## 10. The placement search `FUN_00510089` and the free-cell test

All CONFIRMED (disassembly `0x510089`-`0x5102a0`, `0x5563ca`, `0x55c5a0`, `0x54fca8`; engine `engine/sim/place.py`, used by the party, the summons,
phase in / polymorph and the spawns). `FUN_00510089(creature, x, y, r)`: `tries = r*r/2 + 2` rounds of

1. `y' = y - r/2 + rand(r)`, then `x' = x - r/2 + rand(r)` (y drawn first; `r/2` is the byte `r >> 1`; `rand(r)` = `FUN_0051fa25`, 0..r);
2. the position is stored by **`FUN_0054fca8(x', y')`: both bytes are clamped into the playable rectangle `[8, width - 9] x [8, height - 9]`** (`0x550d9f` / `0x550db3` =
   map width / height `+0x50000` / `+0x50004`; a coordinate below 8 becomes 8, above `width - 9` becomes `width - 9`; so the search never leaves the rectangle and
   the cell that is tested and returned is the clamped one);
3. the free test `FUN_005563ca(creature)` (the multiplayer variant skips rows below 12 only when `game+0x74 != 0`);

then, for `r > 0` and no hit, a scan `x` from `x - r/2` to `x + r/2` (outer), `y` likewise (inner), the same clamp and test; the first free cell wins. On success
`FUN_0055020a` registers the creature (occupant slots and its stamp, [simulation §7.4](simulation.md)); no free cell returns 0.

**The free test** `FUN_005563ca` = `FUN_0055c5a0(creature, cell, 0)` **and** `FUN_0055c5a0(creature, cell, 1)`. `FUN_0055c5a0` reads the creature's footprint size `n`
(vtable `+0x1c`, the token size) and the cell word `y << 8 | x`, and for `i, j` in `0..n-1` fetches the byte of cell `((x + i) & 0xff, (y + j) & 0xff)` of the **live
layer** (`+0x20000`, flag 0: `FUN_0055fa20`) or the **static layer** (`+0x10000`, flag 1: `FUN_00542dc0`) and answers 0 when `byte & mask != 0`, where `mask` is
the creature's mover byte (`brain+5`: 0x41 walker, 0x44 ghost / bee, 0x82 flyer, `FUN_0055c550` = AND). There is **no occupant or relation test**: units matter
only through the stamp bits 0x40 / 0x80 of the live layer, which are the stamp slots of the cell records ([simulation §7.4](simulation.md)); a unit that lost a first-come race
for its cell holds no stamp and does not block, and a dying unit keeps its stamps until removal. The teleport check `FUN_0055a928` (instants 27, the Teleportation
spell) uses the same `FUN_005563ca`. Engine: `place.cell_free(world, u, x, y)` (static = `World.blocked`, live = `World.slots.stamp`), `place.find_place`, `place.clamp`;
the old engine rule (any unit on the cell blocks) was INFERRED and is gone. Cells outside the map are unreachable from the search (the clamp); the grid reads 0 beyond a
square map and 0x1f in the outermost 8 rows / columns of a non-square one (`FUN_00553b30`).

## 11. The end of the mission, Scenario.dll and the client flow

CONFIRMED in `FUN_004852d8` (window procedure; messages `0x416 + k` through the byte table `0x488821` and jump table `0x488731`) and `Scenario.dll`. Engine:
`engine/sim/campaign.py` (state machine with no windows; `World.mission_complete`, `.mission_ended` = latch `+0x3e4`, `.defeat_latch` = latch `+0x3e8`, `.dialog`).

**Messages.** Server `0xb5` -> window `0x430` (`0x486ddb`): `+0x3e4 := 1`; if `ScenarioGetVar(0x300) >= 0x78` (`FUN_00493da0`) post `0x41d` at once, else open the modal
dialog (class vtable `0x5cd098`, label entry `0x8c`, sound 14 / `0xdc`, window `+0x128`, modal bit 8 freezes the sim) with two buttons: `Victory!` (`0x41d`, `0x44db9e`) and `Continue` (`0x446`, closes it) (CONFIRMED: its build slot is `FUN_0044da55`, [ui-layout 11.4](ui-layout.md#114-in-game-menu-pause-freeze)). Server `0xb4` -> `0x433` with `0xff` -> `0x431` (`0x486f7e`): the defeat dialog once (latch `+0x3e8`, mode 2): button
`0x445` = end the game (`0x41e`, `FUN_0048f2e5`) and back to the main menu (`0x421`); button `0x446` = the load-game window (`0x418`), disabled when no `game*.sav` exists
([combat §12.3a](combat.md#123a-hero-death-message-0xb4-the-dialog-and-the-game-confirmed-unless-marked-allods2exe-sha256-in-formatsreadmemd)). **Both latches are cleared at every game start (`FUN_0048c8a3`, `0x48d886`) and when a save is loaded
(`FUN_0048c2e9`, `0x48c824` / `0x48c834`)** (this was combat §12.11 item 1).

**Window message `0x433` with other wParam `n`** (script instant 2 and the sub-objective messages, server `0xb6`; `0x485f73`): `0xff` the defeat dialog; `0xfe` sound `0xdc` on
UI sound slot `0x10`; `0xfd` the same on slot `0xe`; `0xfa` sound `0xdc` on slot `0xe` plus interface text `0x61` in the message line for 30 s; **every other value shows the
section `#event<n>` of `main\text\mission<id>.txt`** (`sprintf("event%d")` at `0x5f3318`, story window `FUN_0041d15e`), or, with a modal dialog open (bit 8), queues
`n` (`0x627170`). On the 46 maps 444 of the 448 instants of kind 2 find their section (test); the other four (map 30 n 20, map 71 n 10-12) are unused numbers.
`campaign.message_action(n, modal)`.

**`0x41d`** (`0x486a68`; also posted by the quit-mission confirmation `FUN_0048e764` when the player leaves a mission by the menu): game modes 1 / 3 (non-campaign) and 0 go
elsewhere; in the campaign (mode 2): with latch `+0x3e4` clear it is "back to the main menu" (`FUN_0048f2e5` + `0x421`, no carry-over). With the latch set:
the mission time `tick >> 4` is stored (`FUN_00493b40`, list `win+0x598`), `FUN_0041c897`, `FUN_004ebd5f` (the roster carry-over, [saves §4](../formats/saves.md)),
`ScenarioLeaveLocation(&code)`, then if `Var(0x305) != 0` the hero of that number is recruited (`FUN_004f312a(server, Var(0x300), [Var(0x305)])`, a one-element list at `0x486c9a`; decoded in [11.3](#113-recruit-routines)), a cutscene `code >= 0` is played (`FUN_0048f919`), and the next screen: chapter `Var(0x300) >= 0x78` -> the ending (`0x428`); else
`ScenarioIsTownAvailable(0)` (any town in the available list) -> the town / world-map screen (`FUN_0048b419`); else `ScenarioEnterLocation(first available location)` and `0x468` (start it).
`campaign.press` returns these as `Outcome(kind, cutscene, recruit, location)`; the recruit and the roster carry-over are for the shell to apply.

**Scenario.dll** (CONFIRMED; ordinals from the exe's loader `0x4818e7`: 1 GetVar `0x62729c`, 2 SetVar, 3 TalkTo, 5 EnterLocation, 6 LeaveLocation, 7 / 8 EnterShop / LeaveShop, 9 / 10 EnterInn / LeaveInn,
11 NewGame, 12 Save, 13 Load, 14 GetAvailableLocations, 15 GetShopAssortment, 16 IsTownAvailable, 17 IsMissionAvailable, 18 GetCurrentLocation, 19 GetAllLocations):
locations are `(type, id)` objects (type 1 mission, 2 town; the towns 1-3 at `0x10035f60`, `0x10035f78`, `0x10037568`); `ScenarioNewGame` empties the available list (`0x10035f90`), adds town 1
and enters it; `ScenarioEnterLocation` zeroes the 16 variables `0x2f0..0x2ff` (the sub-objectives) and stores the location. `ScenarioLeaveLocation(&code)` (`code := -1`): no location -> 0; a town
-> leave (town 1 also leaves the available list); a mission `n` (`0x10001da5`) -> clear Var(`0x305`); the location leaves the list; `Var(0x380 + n) := 1`; unlocks (`campaign.UNLOCK`: 10 -> mission 20,
20 -> town 2 and mission 21 when `Var(0x304)` (a map-20 script variable, [11.1](#111-variable-map); an earlier draft said `0x303`), 31 -> 32, 40 -> missions 50 and 60 and `Var(0x305) := 0x17`, 50 -> town 3, 60 -> mission 80); cutscene codes 10 -> 1, 30 -> 2, 70 -> 3 when
`Var(0x309) == 0 and Var(0x30a) != 0`, 80 -> 3 when the reverse, 110 -> 4 (`Var(0x30b) == 0`) or 5; `Var(0x300) += 10` when `n % 10 == 0`; then the shop tables
([items §13](../data/items.md#13-campaign-town-shops-scenariodll)). The rest of the DLL state (variables, mercenary markers, town dialogue, the talk-offered missions) is in 11.1-11.5. Not modelled: the shop tables.

### 11.1 Variable map

CONFIRMED by the disassembly of `Scenario.dll` (every store to `0x10036c28`-`0x10036c5c`, the table loops over `0x10036824`-`0x100368e0`), by every immediate `push 0x2xx / 0x3xx` before `[0x62729c]` / `[0x627298]` in the exe
(`0x41050f`, `0x444496`, `0x486c88`, `0x487e43`-`0x487e61`, `0x4896dc`, `0x489700`, `0x48ba6f`, `0x493da3`, `0x493de3`, `0x49b8af`, `0x4bf0ba`, `0x4cad3c`, `0x4cd0fb`, `0x4cdd0a`, `0x4d07e7`, `0x4d30ed`-`0x4d3183`,
the script check / instant `0x577789` / `0x577976`), and by a scan of every instant 35 and check 23 of the 46 campaign maps. `Var(n)` is `0x10036028 + 4n`; `D(n)` = `Var(0x380 + n)` = "mission `n` completed".

| Var | Meaning | Written by | Read by |
|---|---|---|---|
| `0x200 + k` (k = 0..19) | mercenary (hero number) `k + 1` is **hired** for the next mission | `TalkTo` type 1 toggles `Var(0x1ff + A)`; every mission completion zeroes all 20 | `EnterInn` (bit 31 of the word), exe `0x487e43` (11.3) |
| `0x214 + k` | mercenary `k + 1`: 0 not on offer / dead, 1 on offer, 2 on offer again (hired for the last mission and still alive at its end) | completion cases (:= 1, below), `TalkTo` (below), completion loop (1 -> 2 when hired), the client's death hook (:= 0, [11.4](#114-hero-death-variables)) | `EnterInn`, exe `0x487e5a` |
| `0x228 + k` | town (2 or 3) that offers mercenary `k + 1` | same cases | `EnterInn` (listed only in that town) |
| `0x2f0`-`0x2ff` | sub-objectives | map scripts, zeroed by `ScenarioEnterLocation` | script check 24, exe `0x444496` |
| `0x300` | chapter `C` (10 at start, +10 per main mission) | completion | everywhere |
| `0x301` | 1 once `TalkTo` type 3 offered mission 10 (`B == 10`) | `TalkTo` | exe `0x4cad3c`, `0x4cd0fb`, `0x4cdd0a`: town-screen routines (UI, not decoded; INFERRED a first-mission tutorial gate) |
| `0x302` | 1 after mission 70; 2 after `TalkTo(0x4e02a3)` | case 70, `TalkTo` | `EnterInn`; exe `0x4bf0ba` (`FUN_004bf096` returns `Var(0x302) != 0`, always 1 outside the campaign mode; a town-3 UI gate, INFERRED) |
| `0x303` | 1 after mission 50 | case 50 | `EnterInn` (town 3: offers missions 70 and 71) |
| `0x304` | 1 when the map-20 script instant "Get mission 21" ran | **map 20** (instant 35) | case 20 (adds mission 21) |
| `0x305` | hero number the next mission end recruits | case 40 := `0x17`; cleared at the start of every completion | exe `0x486c8d` (11.3) |
| `0x306` | 1 after mission 60; 2 after `TalkTo` type 0, A = 5 | case 60, `TalkTo` | `EnterInn` (town 3, C > 60: offers word `0x4f0005`) |
| `0x307` | **never written** (exe, DLL, maps): non-zero would clear itself and rebuild the available list with about 40 towns / missions (INFERRED debug unlock) | - | DLL `0x10001dbc` |
| `0x308` / `0x30d` | hero is a mage / is female | character creation ([shell §3.3](shell.md), exe `0x4896dc` / `0x489700`) | `EnterInn` (which of the four slot missions 74-77 / 84-87 / 93-96, 11.2) |
| `0x309` / `0x30a` | mission 70 / mission 80 has been completed | **only** DLL cases 70 / 80 (no other store to `0x10036c4c` / `0x10036c50`; no exe push of `0x309` / `0x30a`; no instant of any map) | cases 70 / 80 (cutscene 3 when the *other* mission was done first); **map 80** check "Was in 70 mission" = `Var(0x309)`, **map 70** check "Was in 80 mission?" = `Var(0x30a)` |
| `0x30b` | 0 knights win / 1 druids win | **map 110** instants "Set scenario: knights / druids win" | case 110: cutscene 4 (0) or 5 (1) |
| `0x30c` | 1 = "Give 52 mission" | **map 50** instant | case 50: adds mission 52 (location `0x100373a8`, type 1, id `0x34`) |
| `0x380 + n` | `D(n)` | completion (`0x10002140`) | `EnterInn` gating |

Maps 70 / 80 use the flags for the crown: the six crown triggers of map 70 ("Hero / Knight / Dina receive crown12" vs "... crown!") and of map 80 ("Crown - hero" vs "Full crown - hero", heroes 10001-10003) are the same trigger split by
the flag test (the first crown piece with message, versus the full crown with `Mess10-12` / `Mess5-7`); whichever of the two missions is played second finds the flag set (INFERRED reading of the trigger names; the checks and writers CONFIRMED).

**Mission completion `0x10001da5(n, ...)` in order (CONFIRMED)**: (1) `Var(0x305) := 0`; (2) `Var(0x307)` block (never reached); (3) for k = 0..19: if `Var(0x214 + k) != 0` then it becomes 2 when `Var(0x200 + k) != 0` else 1, and **`Var(0x200 + k) := 0`** (every hire flag is cleared, so
a mercenary serves one mission); (4) the current location leaves the available list, current := none; (5) `Var(0x380 + n) := 1`; (6) the per-id case below (the loop of (3) ran first, so a marker created by a case is not promoted in the same call); (7) `Var(0x300) += 10` when `n % 10 == 0`; (8) the price caps ([items §13](../data/items.md#13-campaign-town-shops-scenariodll)).
Besides the unlocks and cutscenes already listed above, the cases write:

| `n` | variables written | mercenary on offer afterwards (`Var(0x214 + k) := 1`, `Var(0x228 + k)`) |
|---|---|---|
| 20 | mission 21 only when `Var(0x304)` | hero 1 crossbowman, town 2 |
| 30 | - | - |
| 40 | `Var(0x305) := 0x17` | - |
| 50 | `Var(0x303) := 1`; mission 52 when `Var(0x30c)` | hero 3 druid, town 3 |
| 60 | `Var(0x306) := 1` | hero 6 mage, town 2 |
| 70 | `Var(0x309) := 1`, `Var(0x302) := 1` | hero 4 troll, town 3 |
| 80 | `Var(0x30a) := 1` | - |
| 100 | - | hero 7 catapult, town 2 |

Hero 2 (knight, town 2) is switched on by `TalkTo(A = 0x16, B = 30)` and hero 5 (orc, town 3) by `TalkTo` type 0, A = 5 (11.2); hero 1..7 are the only mercenaries that exist ([11.3](#113-recruit-routines)); hero numbers 8..20 have no template.

### 11.2 Town dialogue: EnterInn and TalkTo

The town screens are the only callers (CONFIRMED by the xrefs of `[0x62746c]` = ordinal 3 `TalkTo`: `0x49b91d`, `0x49ba0c`, `0x49bb12` (the NPC dialogue window), `0x4b9117`, `0x4bec83`, `0x4c0995` (the three shop windows, which pass the word at `window+0x160`;
text `shop\npc31m<B>`); and of `[0x627480]` = ordinal 9 `EnterInn`: `0x48ba0f`, `0x49ae7a`, `0x49c5d5`, `0x49e6cd`). **No mission, script or in-game code calls either.** In a headless campaign the town does not exist, so the stand-in of 11.5 must call them.

**A dialogue word** (u32): `A` = bits 0-15 (the NPC: a human / monster `serverID` or a hero number), `B` = bits 16-27 (the text variant, or for type 3 the mission it offers), type `T` = bits 28-30, bit 31 = "taken" (hired / opened; set by the windows, ignored by `TalkTo`).
The window shows the text key `npc<A>talk<B>` (`0x5f43e8`), `npc<A>accept<B>` (`0x5f43c8`) / `npc<A>reject<B>` (`0x5f43d8`) for hire words; `A` of a type-3 / type-0 word also names the creature drawn in the scene (the `FUN_004f312a` call of 11.3).

**`ScenarioEnterInn(words, &count)` (`0x1000286b`, CONFIRMED; reproduced by running its instructions on every chapter, town and flag state)**: `count := 0`, then by chapter `C` (jump table `0x1000322a`) and current town `T` (`ScenarioGetCurrentLocation` id)
append, in this order (`Dk` = `D(k)`; an offer is listed only while its mission is not done):

| `C` | town | words `T<type>/A:B` | gate |
|---|---|---|---|
| 10 | all | `T0/0xcf:9`, `T0/0x83c:8`, `T3/0x205:10` | none (mission 10 is offered at every visit) |
| 20 | all | - | - |
| 30 | all | `T3/0x16:30`, `T3/0x83c:31`, `T0/0x83e:39` | 31 until D31 |
| 40 | all | `T3/0x16:40`, `T0/0x83c:48`, `T3/0x7df:41`, `T3/0x83f:42`, `T3/0x7d4:43` | 41 / 42 / 43 until their D |
| 50 | all | `T0/0x17:49`, `T3/0x7e3:53` | 53 until D53 |
| 60 | 2 | `T3/0x7d6:61`, `T3/0x83d:63` | 61, 63 until their D |
| 70 | 2 | `T3/0x7d4:73`, `T3/0x83c:72` | until their D |
| 80 | 2 | `T3/0x7d9:82` (non-mage) or `T3/0x7da:81` (mage) | until D |
| 90 | 2 / 3 | 2: `T3/0x7d4:90`; 3: `T3/0x2a9:91`, `T3/0x7d3:92` | until D |
| 100 | 2 / 3 | 2: `T3/0x7d6:100`, `T3/0x83d:102`, `T3/0x7d5:103` (when D91); 3: `T3/0x2a9:101` | until D |
| 110 | 2 | `T3/0x7d6:110` | - |
| 60-110 | 3 | `T3/0x2a8:70`, `T3/0x2a9:71` (C 60-80, when `Var(0x303)`); `T0/0x5:79` (C > 60, `Var(0x306) == 1`); `T0/0x2a3:78` (C > 60, `Var(0x302) == 1`) | 70 / 71 until D |
| >= 60 | 2 | `T3/0x16:62` when D53 and not D62 (C >= 60); the **class slot** `T3/0x7e6:B` (below) | |

Class slot (C >= 60, town 2): `B` = 74 + s while D63 and none of D74-D77; 84 + s while one of D74-D77 and none of D84-D87; 93 + s while one of D84-D87 and none of D93-D96, with `s` = 0 (not mage, not female), 1 (not mage, female), 2 (mage, female), 3 (mage, not female) (`Var(0x308)`, `Var(0x30d)`).
Then, for every k = 0..19 with `Var(0x228 + k) == T`: `Var(0x214 + k) == 1` appends `(k + 1) | 0x10000000 | (Var(0x200 + k) > 0) << 31`, `== 2` appends `(k + 1) | 0x20000000 | ...` (the mercenary offers). Town 1 is never in a mercenary table. The table lists each row's words as the routine yields them when the row's own conditions hold and every other `Dk` / variable is 0 (the emulation sweeps of all chapters x towns x flag states confirmed no other word exists).

**`ScenarioTalkTo(word)` (`0x100032c0`, CONFIRMED)**, `T = (word >> 28) & 7`:

| `T` | effect |
|---|---|
| 0 | `A == 5`: `Var(0x218) := 1`, `Var(0x22c) := 3`, `Var(0x306) := 2` (orc on offer in town 3). `A == 0x2a3 && B == 0x4e`: `Var(0x302) := 2` and town 3 block 3 flags `|= 0x80000` (quality 4 goods, [items §13](../data/items.md#13-campaign-town-shops-scenariodll)). Any other `A`: none |
| 1 | `Var(0x1ff + A) := (Var(0x1ff + A) == 0)`: toggles the hire flag of mercenary `A` (hire / dismiss; the window sets / clears bit 31 of its copy at `0x49b8fe` / `0x49b9cc`); the window only sends it for a type 1 word (hire) or a taken word (dismiss), see the hire window below |
| 3 | the offered mission `B` joins the available list when it is a known location and not yet in it (`0x1000192f`); `B == 10` sets `Var(0x301) := 1`; `A == 0x16 && B == 30`: `Var(0x215) := 1`, `Var(0x229) := 2` (knight on offer in town 2) |
| 2, 4-7 | none |

Missions offered by a type-3 word (union over all chapters, towns and flag states, run on the routine): 10, 30, 31, 40-43, 53, 61-63, 70-77, 81, 82, 84-87, 90-96, 100-103, 110; the completion cases add 20, 21, 32, 50, 52, 60, 80 and towns 2 / 3
([campaign.UNLOCK](#11-the-end-of-the-mission-scenariodll-and-the-client-flow)). **Missions 51 and 83 are named by no case and no word** (INFERRED unreachable in the shipped campaign; the maps exist). Type-0 words found: `B:A` = 8:0x83c, 9:0xcf, 39:0x83e, 48:0x83c, 49:0x17, 78:0x2a3, 79:0x5.

**The available list and who reads it (L1-1, CONFIRMED)**: `0x1000192f(id)` walks the all-locations list (`0x10037028`) for the mission object with that id and, when `0x10035f90` does not hold it yet, appends it at the **tail** (`0x10003bb0`, a plain linked list: head / tail / count); callers `0x10001da5` (completion unlocks), `ScenarioTalkTo` type 3 (`0x100032c0`) and `ScenarioLoad` (`0x10003686`, re-adds the saved list in its saved order). Nothing sorts it or inserts elsewhere, so the order is **the order of the events** (unlock order, and within a visit the order of the `TalkTo` calls). It does not follow `EnterInn` block order except through that call order. Exe readers of `ScenarioGetAvailableLocations` (`[0x62715c]`): `0x486d4f` (end of a mission with no town available: **head** -> `ScenarioEnterLocation` + `0x468`), `0x46fe69` / `0x47072e` (world-map screen set-up: the head's map point becomes the initial cursor / focus; with flag `+0x1b0` set the head is entered directly), `0x4707xx` (click: walk the list, the first location whose map point (object `+8`, `0x473a50`) the click hits (`0x472700`) is entered, `[0x627294]`) and `0x471728` (nearest location to the cursor by squared distance; strict `<`, so ties go to the earlier list entry). So the world map **places each mission at its own fixed point and the player picks by position**: the list order never reorders what is drawn; it only breaks ties between overlapping hit areas and picks the no-town start. The list is empty of towns only while town 1 has been left and no town 2 / 3 is unlocked (INFERRED from the leave rule: after mission 10 the list is just mission 20, so that start is not ambiguous). The map points of the locations are the DLL's (object `+8`, set by `0x100039e0` / `0x10003a20` tables; not decoded: only the shell needs them).

**The hire window's button (L1-2, CONFIRMED asm)**: the click handler `0x49a197` (window mode `[client+0x5d8] == 2`) reads the selected word; bit 31 clear -> `0x49b812` (Accept), set -> `0x49b989` (Dismiss). Accept: type `T = word & 0x70000000`; `T == 1`: shows `npc<A>accept<B>` (`0x5f43c8`, `B` = `GetVar(0x300)`, the chapter), sets bit 31 of the window's copy, `TalkTo(word | 1<<31)` (toggle on). Any other type (a type 2 re-offered mercenary): shows `npc<A>reject<B>` (`0x5f43d8`) and **no `TalkTo`**: a re-offered mercenary cannot be hired again. Dismiss: clears bit 31, `TalkTo(word)` (toggle off), no type check. **No price**: neither handler reads or writes gold (nor any variable besides the `TalkTo`), so the hire is free (the data.bin price has no reader here). The word's marker comes from `EnterInn` (type = `Var(0x214 + k)`, bit 31 = `Var(0x200 + k) > 0`).

**Who calls `TalkTo` (L1-1)**: the NPC window handler at `0x49ba..0x49bb12` formats the text `npc<A>talk<B>` of the clicked word (`+0xfc` array, index through `0x49ab92` from the selection `+0xb8`), shows it (`FUN_0041d15e`) and calls `TalkTo(word)` right then (CONFIRMED the call; INFERRED that it is the click handler). Hire (type 1) words go through the accept / dismiss handlers (`0x49b8a6`, `0x49b9cc`). So in the real game type 0 / 3 words are `TalkTo`'d **in the order the player clicks the NPCs, only for those he clicks** (INFERRED: no call is made on entering the inn, the handler above is the only `TalkTo` site for these words); a type-3 mission thus enters the list at the moment of the click. What only the player decides: which NPCs to talk to (a mission offer not clicked is not unlocked in that visit, nor does its marker `0x301` / `0x218` get set), the order of the clicks, which mission to start, hires.

### 11.3 Recruit routines

Two routines build units from a list of dialogue words / hero numbers; both use the low 16 bits `n` of each element. Server object in `ECX`, chapter `C` = `Var(0x300)` on the stack.

**Template choice (identical in both, CONFIRMED asm `0x4f31ca`-`0x4f3325`, `0x4f36c0`).** `H(x)` = the humans table lookup `FUN_004fd5ad(x)` (data.bin group 6 by `serverID`), `M(x)` = the monsters table `FUN_004fd62f(x)` (group 5); both return a 1-based index, 0 = none.
1. `idx = H(10000 + 10 n)`; if 0: `idx = M(10000 + 10 n)` and the unit is a *monster* (0x208-byte class, ctor `FUN_0050dd41`), else a *human* (0x254 bytes, ctor `FUN_005143e4(record, flag, 0)`).
2. *(only `FUN_004f312a`)* if `idx` is still 0: `idx = H(n)`, if 0: `idx = M(n)`, monster := true (a plain NPC such as `n = 0x83c`; `FUN_004f36c0` has no such fallback).
3. If step 1 found a record: if **any** `10000 + 10 n + j`, `j = 1..9`, exists in the same table (a *variant series*), then `v = lookup(10 n + 9998 + C / 10)` (integer division) in the same table; **when `v != 0` it replaces `idx`**.
   So the record of chapter `C` is `10000 + 10 n + (C / 10 - 2)` when it exists, else the base: `C = 10` gives `9999 + 10 n` (absent, base), `C = 20` the base itself, `C = 30` the variant `+1`. Worked example: knight (`n = 2`), `C = 50`: `20 + 9998 + 5 = 10023` = `2MercenaryKnight50` (blade 43); `C = 20`: base 10020 (blade 25).
4. The unit gets `+0x14c := n`, `unit+0x14 := the local human player` (`FUN_0053b930` of `[0x68d2c4]`), and **no map position**.

Which hero numbers exist (CONFIRMED by the data.bin records; `serverID`, variants from chapter, main skill by variant):

| `n` | role | base id | variants | what they hold |
|---|---|---|---|---|
| 1 | crossbowman (human, type 15) | 10010 | 10011-10019 = C 30-110 | HP 90; shooting 23 (C <= 30), 32, 41, 50, 59, 68, 77, 86, 95; equipment strings per variant |
| 2 | knight (human, type 5) | 10020 | 10021-10029 = C 30-110 | HP 50; blade 25, 34, 43, 52, 61, 70, 79, 88, 97 |
| 3 | druid (monster, type 100) | 10030 | 10034-10039 = C 60-110 | HP 80-130, mana 350-450, five school skills; the base (C < 60) is stronger than the C 60 variant (quirk) |
| 4 | troll (monster, 102) | 10040 | 10045-10049 = C 70-110 | HP 800-950 |
| 5 | orc (monster, 101) | 10050 | 10054-10059 = C 60-110 | HP 200-280 |
| 6 | mage (human, type 23) | 10060 | 10064-10069 = C 60-110 | HP 30, mana 70, bludgeon 50-95, pike 40-75, shooting 30-55, spell mask grows |
| 7 | catapult (monster, 26) | 10070 | 10079 = C 110 | HP 250 |
| 0x15 | the player's own hero | 10210-10213 `Start_*` | not used (see `FUN_004f254b`) | [§9.3](#93-a-fresh-character-fun_004f254bplayer-str-dex-mind-spirit-school-flags-confirmed) |
| 0x16 | Fighter_Hero ("the knight", scripts 10002) | 10220 | none (10221-10229 absent) | blade 25, shooting 10, two-handed sword, steel armour: **the same at every chapter** |
| 0x17 | Mage_Hero ("Dina", scripts 10003) | 10230 | none | mage, the record's spell mask and equipment, the same at every chapter |

(The chapter-scaled series is a data effect only: nothing in the exe levels a recruit; the map loader's difficulty tweak, [progression §6](../data/progression.md), runs for map units and not for these.) Level, XP, equipment are those of the record:
HP / mana start at the maximum (`FUN_00514cf2` tail `0x514c03`), the equipment strings are created by the constructor like those of a map unit.

**`FUN_004f312a(server, C, list)` (the story-hero recruit and the town scene).** For every word `w` of the list (`n = w & 0xffff`):
* `n` in `0x15..0x1e` (**story hero**): walk the local player's unit list (`player+0x24`); **if a unit with `+0x14c == n` is already there nothing happens**. Else the unit is created through the *human* ctor `FUN_005143e4(H record, flag = 1, 0)` (flag 1 = hero style: `+0xe := 0x21 + gender` / `0x23 + gender`, so it survives the carry-over; INFERRED link from the constructor's second argument to the flag tested at `0x514bac` in `FUN_00514cf2`, which CONFIRMED selects that `+0xe`, [saves §4](../formats/saves.md#4-carry-over-between-campaign-maps-single-player-confirmed)),
  `+0x14c := n`, `unit+4 := FUN_004f8d90()` (a free network id, [§9.3](#93-a-fresh-character-fun_004f254bplayer-str-dex-mind-spirit-school-flags-confirmed)), `unit+0x14 := player`, appended to the player's unit list (`FUN_0052b22a`), a new command group made and given the unit
  (`FUN_0052ae43`, `FUN_0053d690`, `FUN_0052af8c`), idle brain objects (`FUN_0056dba1` / `FUN_00570f2b`, which do not read their `this`: the world pointer is already 0 at that moment), and the full stat message `FUN_00502019(unit, player, -1, 0xffb)`.
  The unit is **not on the map**; the next `FUN_004f2c83` places it ([§9.2](#92-fun_004f2c83player-confirmed-disassembly-0x4f2c83-0x4f3127)), after the main hero and the units already in the list.
* any other `n` (a mercenary number, an NPC id): a transient creature with the same template rule (human ctor with flag 0, or the monster ctor) is built, given an id (`FUN_0052b246`), announced to the client (`FUN_00502019`), and **at the end of the call every such id is released** (`FUN_004f8d3d`): INFERRED, only the town scene (the portraits the dialogue shows); no roster effect.
Callers (xrefs): **(a)** the mission end `0x486c9a` with the one-element list `[Var(0x305)]` when it is non-zero: only `0x17` ever (case 40), so after mission 40 `Mage_Hero` is created **only when he is not in the player's list** (CONFIRMED test); map 40 holds one `Mage_Hero`, owner 3, which a script gives to the human ([§9.5](#95-the-hero-look-up-filter-fun_00562518-confirmed-0x562518-0x562632)), so INFERRED the recruit is the safety net for the case that he is dead or was never given;
**(b)** the inn handler `0x48ba81` (`FUN_0048b885`, game mode 2) with the whole `EnterInn` list: every `A` in `0x15..0x1e` of the list is a story hero created at the first inn visit that lists him: `0x16` Fighter_Hero at the first visit after chapter 30 begins (`T3/0x16:30`), `0x17` at C = 50 (`T0/0x17:49`).

**`FUN_004f36c0(server, C, list)` (the mercenary hire, CONFIRMED asm)**: for each `n` of the list the template rule above (no step 2), always built **without** flag 1 (human: `FUN_005143e4(record, 0, 0)`, so `+0xe` stays the template's own type 15 / 5 / 23; monsters 100 / 101 / 102 / 26: all outside `0x21..0x3f`),
`+0x14c := n`, `unit+4 := a free id`, `unit+0x14 := player`, appended to the unit list **with no duplicate test**, own command group, stat message. Caller: the **start-mission message `0x468`** (`FUN_004852d8` `0x487dea`; only when `ScenarioGetCurrentLocation` has type 1 = mission): the list
is `k + 1` for k = 0..19 ascending **where `Var(0x200 + k) != 0 and Var(0x214 + k) != 0`** (hired and alive, `0x487e43`-`0x487e6b`); when it is not empty `FUN_004f36c0(server, Var(0x300), list)` runs, then the game starts (`FUN_0048c8a3(0)`: map load, party placement of §9). The mercenaries live for one mission:
the carry-over deletes them (their `+0xe` is outside `0x21..0x3f`), `Var(0x200 + k)` was zeroed by the completion, and they have to be hired (and paid, if ever) again.

### 11.4 Hero-death variables

`Var(0x213 + id)` for `id = 1..20` is `Var(0x214 + k)`, `k = id - 1`: the "on offer / alive" marker of mercenary `id` ([11.1](#111-variable-map)).
* **Writer (CONFIRMED, exe `0x41050f`, the client's HP update of `FUN_0040d9b2`)**: the client keeps a death stage `view+0x184` from the HP word `view+0x104`: 5 below `-600`, 4 below `-40`, 3 below `-20`, 2 below `-10`, 1 when `<= 0`, else 0. While the stage is **>= 2** (HP <= -11 as the client sees it), the view's `+0x1dc` (the unit's `+0x14c`)
  is in `1..0x14`, `ScenarioSetVar(0x213 + +0x1dc, 0)` runs; there is **no owner test**, so any unit with such a hero number counts (only mercenaries have one: no campaign map unit has `serverID` 1..20 or `10010`-`10209` and the story heroes are above `0x14`; checked on the 4,212 units of the 46 maps).
  INFERRED: stage 2 is reached by the corpse decay after the removal (server removal at HP <= -10, [combat §12.1](combat.md)), so the marker is cleared a few ticks after the death, and not at all when the mission ends first.
* **Readers**: the completion loop (a 0 marker is skipped: no promotion to 2, the hire flag is cleared anyway), `EnterInn` (a 0 marker is never listed again: **a dead mercenary is gone for the campaign**), the hire list of the `0x468` handler (a hired mercenary whose marker is 0 is not created).
  **No exe routine other than these, no map script and no Scenario.dll code reads them** (scan: the only maps that read an array variable are 20 / 50 / 70 / 80 / 110 with `0x30x` and the sub-objectives).
* Story heroes (`0x15..0x1e`) and the main hero have no marker: when dead they have left the unit list (removal, [saves §4](../formats/saves.md#4-carry-over-between-campaign-maps-single-player-confirmed)). The recruit tests only `+0x14c == n` in the list, so a dead `Fighter_Hero` is created again (fresh base record, no XP) at the next inn visit whose
  `EnterInn` list contains a word with `A = 0x16` (C = 30, 40 and from 60 with D53), a dead `Mage_Hero` by `Var(0x305)` at the end of mission 40 or by `T0/0x17:49` at C = 50, otherwise not.

### 11.5 What a headless campaign needs (L1: built, [campaign.md](campaign.md))

Engine behaviours that follow from 11.1-11.4 and [saves §4](../formats/saves.md#4-carry-over-between-campaign-maps-single-player-confirmed):
1. **Carry-over** at a mission end: keep every unit with type `0x21..0x3f` (all human heroes: the main hero, `Fighter_Hero`, `Mage_Hero`) with level / XP / skills / pools / items / spells / name / hero number; HP, mana := max, death flag, orders, targets, applied effects cleared; delete every other unit (mercenaries, summons, monsters); gold, statistics and the variable array stay; the dead (removed) are gone; a dying unit still listed is revived; `player+0x41 := 0` so the next map places the roster again (`party.place_party` with the roster instead of fresh heroes).
2. **Order at a mission end**: carry-over -> `ScenarioLeaveLocation` (completion order of 11.1, which also clears `0x305` and the hire flags) -> recruit `[Var(0x305)]` if non-zero -> cutscene -> next screen.
3. **Recruit rule per chapter**: story heroes are always the base record (10220 / 10230): `Fighter_Hero` when a type-3 word `A = 0x16` is listed and he is absent (first at C = 30, again at C = 40 and from C = 60 when D53 is set and 62 not done); `Mage_Hero` at the end of mission 40 (`Var(0x305)`) and at C = 50 (`T0/0x17:49`) when absent;
   mercenaries (hero 1-7) by the variant of 11.3 for `C` at the start of every mission for which they are hired and alive, created after the roster, in ascending hero number.
4. **TalkTo stand-in** (the town does not exist): after the carry-over and `LeaveLocation`, **visit** the town(s) that `ScenarioIsTownAvailable` allows: `words = EnterInn(C, town, flags)` (the table of 11.2, reproduced by the rules, or the DLL routine re-implemented), create the story heroes among them (`A` in `0x15..0x1e`), then `TalkTo` every word with type 0 or 3
   (**DECISION** for the policy: accept every offer; the outcome only adds missions and sets the markers. The real window calls `TalkTo` per click of the player, [11.2](#112-town-dialogue-enterinn-and-talkto); the exact stand-in for "a player who talks to everyone" is every type 0 / 3 word in the window's NPC order = `EnterInn` order, and the resulting list order is then the `TalkTo` order after the completion unlocks. Only a real player's click order can differ). Type 1 words are mercenary offers: hire by `TalkTo(word)` (toggle `Var(0x1ff + A)`) according to a policy (none by default); type 2 words cannot be hired and a hire is free (L1-2, 11.2). Without the stand-in the missions 10, 30, 31, 40-43, 53, 61-63, ... can never be reached (mission 10 needs `TalkTo(0x300a0205)` before anything is available).
5. **Death hook**: when a unit with `+0x14c` in 1..20 reaches client HP <= -11 set `Var(0x213 + n) := 0` (the engine's corpse decay must reach it or the removal must set it directly: DECISION, the visible difference is only the tick).
6. **Fix the unlock table**: `campaign.py` tests `Var(0x303)` for mission 21 where the DLL tests `Var(0x304)` (written by map 20); case 50 also adds mission 52 when `Var(0x30c)` and sets `Var(0x303)`, case 60 `Var(0x306)`, case 70 `Var(0x302)`; cases 20 / 50 / 60 / 70 / 100 put the mercenary markers of 11.1.

## 12. J3: win and lose on map 32

**Map choice (DECISION).** `scenario/32.alm` is the smallest playable script of the install: 80 x 80, 20 units (wolves, an ogre, a turtle, squirrels, bats, brigands, one
`CH_SwordCarrier`), 6 triggers. Next smallest: map 10 (29 units, 16 triggers, quest instants 23 / 28 / 36), 83 (two triggers but 92 units on 144 x 144). Its win, script loss and
hero loss are each one trigger or one pass, so the three ends need no more than checks 1, 5, 7, 15, 19, the constant, and instants 2, 4, 5, 6 (sub-commands 2 / 5), 8: all built.

| End | Rule on map 32 | Engine path |
|---|---|---|
| Win | 'Swordsman alive ?' (check 5 on unit uid 8, the sword carrier) `==` 0 -> instant 4 (`complete += 1`); fires on every pass until the pass at the end of the block sets `death_code = 1`, message `0xb5` | `run_pass`, `mission_pass` |
| Script loss | 'Swordsman swarmed succesfully': check 7, distance from point (71, 13) to unit 8, `<=` 1 -> instant 5 (cause 5); the swarm starts once the brigands (squad 1) are down to 2 | same, `death_code = 5`, message `0xb4` |
| Hero loss | the main hero's death flag (T§6 step 1), no script involved: `death_code = (reduced id - 0x13)` = 2 for `Start_MF` | `death.remove_dead`, `mission_pass` |

Triggers are evaluated as in T§1 (every 16 ticks at `tick & 15 == 6`, checks before triggers, file order, a `once` trigger never again, others re-armed every pass; variables
and the 1000-slot value array are `Script.values`); the conclusion is T§6 at the end of each 16-tick block. **Fix** found by J3: `death_code` used the raw server id
(`10210 - 0x13` = 207); the exe stores the reduced `+0x14c` (21), so Start_MF gives 2 (any other value is still >= 2 = lost).

**Engine API.** `triggers.result(world)` = `"won"` / `"lost"` / `None` from the human's `death_code`; the end dialogs and the single exit (`Quit`
reasons `victory` / `defeat`, `engine/ui/game.py`) are J1's. **No start menu** (DECISION): the shell exits after the dialog; returning to a main menu needs the
new-game chain (open question "Main shell"). **Unimplemented kinds** log `not implemented: <check|instant|group> <n> (<editor name>)` once per kind and script
(`log` = `logging.getLogger("engine.sim.triggers")`, tables `CHECK_NAMES` / `INSTANT_NAMES` / `GROUP_NAMES`) and are counted in `Script.unsupported`; `Script.strict` raises.

Tests: `tests/test_engine_mission32.py` (win by attacking the sword carrier, script loss, hero loss, replay hash, no unsupported kinds, the once-only report).

**Left for phase K** (documented no-ops or absent): variable references 8000-9999 (never written in the exe), unit names `>= 11001`, instant 37 (set music) and the other unnamed kinds ("Bad instant"),
hero recruit `FUN_004f312a` / `FUN_004f36c0` and the roster carry-over (decoded, L1), the town stand-in (11.5), the start menu / new-game screen (the UI sounds of the `0xfe` / `0xfd` / `0xfa` messages are built in K11, [audio §2.5](audio.md)).

## Open questions

* L1 open questions (school-5 skill order, XP in the headless chain): [campaign 4](campaign.md#4-open-questions).

* Who sets the word `window+0x160` that the three shop windows pass to `TalkTo` (`0x4b9117`, `0x4bec83`, `0x4c0995`; text `shop\npc31m<B>`), and what the town-screen routines `0x4cad3c` / `0x4cd0ea` / `0x4cdd0a` (Var(0x301)) and `0x4bf096` (Var(0x302)) switch on. UI only; no variable is written there ([11.1](#111-variable-map)).
* The hire price: CONFIRMED none (L1-2, 11.2); the cost of a mercenary elsewhere (e.g. at the mission start) was not searched.
* The purpose of `Var(0x307)` (reset of the available list, never written by the exe, the DLL or any map; INFERRED a debug / cheat unlock) and of the exact order of the 40 locations it adds ([11.1](#111-variable-map)).
* The story window is decoded: [ui-layout 11.5](ui-layout.md#115-on-screen-messages); its UI sounds (table ids 16 / 14 / 14) are built ([audio.md](audio.md) 2.5).
