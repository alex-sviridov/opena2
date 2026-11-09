# Picking up items by click, items in scripts (K5)

Code: `engine/ui/orders.py` (`OrderInput.release`, cursor `pickup`), `engine/sim/gear.py` (`command_pickup`, `refresh_pickup`, `pickup_tick`, `pick_up`,
script helpers `give_item` / `remove_item` / `take_all`), `engine/sim/triggers.py` (checks 12 / 16 / 17, instants 11 / 12 / 13 / 20 / 28 / 38),
`engine/ui/info.py` (`quest_items`, `quest_rows`). Tests: `tests/test_engine_pickup.py`. The pack, the pile and the server routines behind it are in
[items §15](../data/items.md#15-equip-use-pack-and-ground-items-confirmed-engine-sim-gearpy); the cursor choice is [ui-layout §6](ui-layout.md).

## 1. The flow (CONFIRMED, GOG allods2.exe)

| Step | Routine | Fact |
|---|---|---|
| cursor | `FUN_004180c6` flag `0x40` | the pointer is on a cell whose item grid entry is non-zero and fully visible (`Projection.hover_cell`, `fog.cell_visible`); `pickup` needs exactly one selected hero-type unit (ui-layout §6) |
| release | `0x4177d4` (cursor global `0x626cd8` = pickup) -> `FUN_00419d8e(view+0x9ac, view+0x9b0)` | the **click cell** (the same one a move uses) goes to the sender |
| message | `FUN_00419d8e` | builds command `0x21` (`msg+9`), player id, the cell `(+0xa, +0xc)`, the pack index `+0xe := unit +0xe4`, `+0x12 := 0`, once **per selected unit** that has a client object (`unit+0x80 != 0`, `FUN_0041eb40`); `FUN_00419d8e` takes no range or "is there a sack" test: the server does |
| intake | server `FUN_004f515d` case `0x21` | "Sack not found" (nothing happens) when `FUN_00553ab3(x, y)` finds no pile; else the **last** unit of the intake gets order 2 (`FUN_0056da98`), destination = the cell |
| approach | group pass `FUN_00569321` order 2 -> `FUN_0056c8da` | on the sack's cell: Brain mode 7; else Brain mode 1 (**a plain walk to the sack's own cell: range 0**, no "in reach" radius) |
| take | creature tick state 2 (`FUN_0050f12c` case 2) -> `FUN_005108fa` | the **whole pile**: gold to the player (`FUN_00516238`; the message `0x67` is INFERRED from ui-layout §11.5), every item through `FUN_00529e5b` into the pack while it holds fewer than `0x400` entries (**a full pack loses the rest**, the pile is deleted anyway), items flagged new, then a call to `FUN_00504b3a` (INFERRED: the item notice); no sound call in the server routine |
| after | mode 7 again | state already 2: `FUN_0056dbc6` stop -> order `0xc` |

The pile is one object per cell, so "a sack or one item" is the same thing: a single dropped item is a pile of one. Stackable entries (potions, scrolls, any
item without modifiers, [items §15](../data/items.md#15-equip-use-pack-and-ground-items-confirmed-engine-sim-gearpy)) merge into the pack entry.
**What a script sees** is only the pack: checks 12 / 17 (`0x5773aa`, `0x5775b1`) and 16 (`0x577527`) call `FUN_00529ee5(creature+0x7c, code)`, a walk over
the pack comparing the 16-bit code word (`FUN_00544160`); the equipment slots are **not** searched. There is no "picked up" event: the next trigger pass
(every 16 ticks) reads the pack. Check 16 returns the distance `FUN_00551463` from the unit to the cell `(n0, n1)` when the item is held, else `0xff`.
Instants (addresses in [triggers](triggers.md), pack routines in items §15; the checks above were re-read in the asm for K5, the instants were not): 11 take one piece (`FUN_00529f3f`: a stack gives one, a single entry
leaves the list) and file it in the second unit's pack (`FUN_00529ac2`, at the end); 12 create the item (`FUN_004fbf01`) and file it; 13 delete one
piece; 38 the same for every unit; 20 drops the pack as a pile on the unit's cell; 28 gives the whole pack to the second unit.

## 2. Engine (K5)

- **UI.** `OrderInput.release(S.PICKUP, cell, ...)` returns `PickUp(player, (selection[-1],), cell)` for an own selection; a cell outside the view issues
  nothing. The command is logged like every other (`CommandQueue`) and replays. The sim side (`gear.command_pickup`) refuses a cell without a sack.
  DECISION: `PickUp` stays **cell**-addressed (the wire format), not `(unit, item id)`.
- **Data model.** The hero's inventory is `Unit.pack` (item objects: code, count, modifiers) with the mirror `Unit.carried` / `carried_mods`; a ground
  item is a `world.items` pile found through `world.items_at` (the spatial index). A pickup removes the pile (`world.remove_item`, which clears the index
  and frees the net id) and files its items in one step, so the two never disagree (`consistent()` in the tests). A unit **without an explicit
  loadout** (monsters carrying section 8 items) keeps only `carried`; the death drop reads it.
- **Script items.** Before K5 the instants edited `carried` only, so a hero's pack and `carried` drifted apart (an item given by a script vanished at the
  next `sync_carried`; a removed one stayed in the pack). They now go through `gear.give_item` / `remove_item` / `take_all`, which edit the pack and
  re-sync (`take_item` of `triggers.py` is gone). Weight and the speed penalty follow (`recompute`).
- **Info panel (ENGINE ADDITION, not in the original).** The own hero's carried quest items (special items that are no potion, scroll or book) are listed
  in sage under the stats: at most two lines from `(0x2A, 0xDC)`, `name` or `name xN` for a stack. The original shows them only in the pack window.
- **Message.** The pickup line is `PickupWatch` (ui-layout §11.5). Sound: none found in the server routine; the client sound on the item notice
  `FUN_00504b3a` was not researched (the engine has no audio): open question.

## 3. The seven maps (debug run, `tests/test_engine_pickup.py::test_quest_item_can_be_reached_and_its_checks_hold`)

Quest items by map: sacks on the ground in **21** (`Quest Treasure`, `0xe53` at (60, 18)) and **63** (`0xe54`); carried by a monster in **40** (two), **72**
(four, one per monster), **80**, **91** and **102**, so the hero has to kill the carrier first (the loot pile lands on its cell,
[combat §12.4](combat.md)). The run: build the map as `play` does (party, script, AI), kill the carrier, clear every other monster within 9 cells of the
pile (the guards of map 21 and 72 killed the unaided level-1 hero in the exploratory runs; the test keeps the hero alive), put the hero 3-7 cells away, issue `PickUp`,
run until it is in the pack, run 40 ticks. Result for all seven: the item is reached and filed, and every item check of the hero holds
(`values[check] == 1`, check 16 `!= 0xff`). Whole-trigger firing depends on the rest of the mission (map 63: the hero must also stand within 4 cells of
Xara, check 5; maps 80 and 91: triggers 2 / 6 fired right after the pickup, tick 166). **The run proves the pickup, not that the map is winnable**:
the guards were removed by hand. Coverage: **41 of 46 maps without a blocker** (was 34; 12 playable now, 29 with gameplay gaps, 5 blocked: the use-a-structure
and cell-effect maps, K6 / K7).

## 4. P: pick up all sacks in sight

Key `P` (`FUN_00419f2a`, not via the bar dispatcher `FUN_00418a02`) sends message `0x13` with the **hero-type** selected units only (`unit+0x1b8 & 1`, each also needs its
client object `+0x80`). The server intake adds every id to the group and the **last** unit gets order `0x1a` (`FUN_0056dafe`: cancel, order `0x1a`, `mover+0x90 := 0`, Brain mode 0).
The group pass runs `FUN_0056a909` for it **every pass** (no gating), which calls `FUN_00559eed(unit, 1)`:

1. a sack on the unit's own cell wins at once (`FUN_00553ad1`: cell flag `0x20` + the pile list; **no** reachability test);
2. else the square rings `r = 1 .. sight` (`sight` = the scan byte `+0xa5`; a hero's is `human_sight_word >> 8`), per ring `d = -r .. r`, the cells `(x+d, y+r)`,
   `(x+d, y-r)` and, for `|d| != r`, `(x+r, y+d)`, `(x-r, y+d)`; a cell counts when a sack lies there **and** the unit's footprint on it is free in the live layer
   (`FUN_0055a10b` = `FUN_00553ad1` + `FUN_0055cd50`); the scan stops after the first `d` that found any cell;
3. found cells are **pushed at the front** of the list (`FUN_0055f170`), and the first entry is taken (`FUN_0055f0d0`): **the last cell found is the target** (so among the
   cells of one `d` step the order above reversed: `(x-r, y+d)` first). It goes to `brain+0xa`, Brain mode := 12;
4. nothing found: the unit stands (`FUN_0056d52b`, order `0xc`) - the order ends.

Brain mode 12 (`FUN_0056eb2d`): at the cell and at its centre (`FUN_00551383`: sub-position `(0x80, 0x80)`) state := 2 (the tick files the sack, as in §1), the next time state := 0
and mode 0 (the order stays, so the next pass looks for the next sack); elsewhere the move driver `FUN_0056e4ac(unit, brain+0xa, 0)` (the same call as Brain mode 1) and state := 1.
A walk that fails clears the mode like any failure; the target is re-chosen every 16 ticks, so a nearer sack that appears (or is taken) changes it.
Engine: `OrderInput.key("p")` (`hero_fn` filters the heroes), `PickAll` (`sim/commands.py`), `gear.set_pickall`, `nearest_sack`, `refresh_pickall`, `loot_mode`, `Unit.mode_loot`,
`movement._tick_inner`. Not modelled: the 16-bit cell-word wrap at the map edge (the border cells hold no sack).

## 5. The hero on the cursor leaves the doll

`FUN_004b012f(slot)` (a doll slot picked up, [ui-layout 11.13](ui-layout.md)) sets `unit+0x1b8 |= 8` (redraw), moves the item **out of the client unit's slot** (`unit+0x188+4*slot`
:= 0) into the cursor (`client+0x3f4`), then `FUN_0046a215` (the hero's sprite-set choice, [animation 1.3](../formats/animation.md)) and message `0x46e` to the view. So the doll **and
the hero on the map are drawn without that item while it is carried** (a weapon on the cursor: unarmed set). The server slot is unchanged until the `0x22` move is sent on the drop.
Engine: `pack.hidden_slot`, `info.equipped_items(hidden=)`, `herolook.look_key(hidden=)`, `build_draw_list(hidden=)`. Message `0x46e` is relayed by the game window to its child
`+0xcc` (`0x48865e`); the view's table maps it to the default case: **no effect** (INFERRED: nothing else listens).

## VERIFY IN GAME

- `P` with a hero selected and several sacks in sight: the hero visits the nearest ring first, then the next, and stops when none is left; a sack on its own cell is taken first.
- Dragging the weapon off the doll: the hero on the map puts the weapon away at once.

- A click on a sack with the pickup cursor: the hero walks onto the cell and the line "Picked up ..." appears; a click on a sack under a unit.
- A hero with a full pack (0x400 entries, not reachable in practice) loses the rest of the pile.
- Two heroes selected: the cursor is not `pickup` (needs exactly one).

## Open questions

- The client sound for the item notice `FUN_00504b3a` and the gold message (`0x67`).
- `unit +0xe4` (the pack index the client sends in `0x21`): INFERRED to be the 0x7FFF default; the engine sends 0x7FFF.
- Two or more selected units on a pickup: the cursor forbids it, but `FUN_00419d8e` would send one message per unit; only the last of the intake walks.
- The 16-bit cell wrap of the P scan at the map edge; the window `0x4ba` that message `0x463` (Quest Documents dropped on a doll slot, map 10 only) opens (`FUN_0048b1f9`: client mode `|= 0x4000`, a modal view).
