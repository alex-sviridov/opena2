# Simulation: tick, update order, unit states, movement

Phase H1. The game tick, what a server tick runs and in what order, the unit state machine, and the
rules by which a unit walks a given path, and (§7, H2) how it finds one. Code: `engine/sim/` (`clock.py`,
`simulation.py`, `movement.py`), `engine.world.Unit` / `Mover`. Facts are marked **CONFIRMED** (GOG
`allods2.exe`, sha256 in [formats/README](../formats/README.md), address given) or **INFERRED**;
engine choices are **DECISION**. Unit struct and mover offsets: [unit-struct](unit-struct.md) §2, §7,
§8; walk timing and animation: [animation §3](../formats/animation.md#3-timing).

## 1. The tick

Fixed step, one server tick per client tick (CONFIRMED, `FUN_00488aa1`, `timeGetTime` IAT `0x6cf074`):
the loop runs while `timeGetTime() >= base + period·(n+1)`, re-bases every 16 ticks, so a stall runs at
most 15 ticks back to back. `period = 1000 // rate` ms; rate by menu speed 0..8 = 8, 10, 12, 14, 16, 20,
24, 28, 32 ticks/s (default speed 4: 62 ms, 16.13/s). Changing the speed (`FUN_0048bfaa`) only resets
the block phase. Every pass calls `server.step()` (`FUN_004f08c0`, global `DAT_006044c4`), then
`client.read_messages` (`FUN_0040d9b2`), then the view tick (`FUN_0040bcd8`, view clock `+0xa88`).
The tick length does not depend on anything but the speed setting; game logic counts ticks, never
milliseconds. The G1 constants (architecture §4) are all CONFIRMED; none was INFERRED, so nothing needed
replacing: H1 adds the update order below.

Engine: `Simulation.step(commands)` is one server tick; the backend's accumulator calls it
`floor(acc / period)` times per frame (`clock.py`, `tick_period_ms`). `world.tick` is the number of
completed ticks (the exe increments its counter at the start of a tick, `FUN_004f8521` `+4`; the engine
after: DECISION, only an offset of one for display).

## 2. Update order inside a server tick

CONFIRMED, `FUN_004f08c0` → `FUN_004f8521` (`0x4f8521`), `FUN_004f04cf`:

| # | Step | Routine | Notes |
|---|---|---|---|
| 0 | tick counter `server+4` += 1 | `0x4f8521` | |
| 1 | **drain the command queue** | `FUN_004f84c6`: `FUN_00501831` pops, `FUN_004f515d(msg)` runs (message type byte at `msg+9` → order issuer, [unit-struct §9](unit-struct.md)) | every player command of the tick is applied before any unit moves; an order issued in tick T makes its unit act in tick T |
| 2 | transient objects of the list `server+0x2c`, **in list order**: vtable slot `0x18`, then delete when byte `+0x136 != 0` | `FUN_004f04cf` (`0x4f04e0`-`0x4f052c`); added by `FUN_004f06ac` (a `0x208` creature-class object with id 0 at a given cell, `0x4f06ca`-`0x4f071f`) | CONFIRMED: carriers (spell effect / projectile bodies), not units |
| 3 | area effects (`server+4` container): slot `0x18`, remove when `+0x40` set | `FUN_0052c279` | |
| 4 | **creatures**: per-player relation-bit notification, then slot `0x18` (= `FUN_0050f12c`) unless state `0x10`, then dead-unit removal | `FUN_0052b459` (`0x52b4b0`-`0x52b5c3`), list at the container's `+4`, order of creation | CONFIRMED; this is the pass the older notes called "kill credit" (the credit is its tail) |
| 5 | per-creature relation-bit notifications (`+0x1a4` vs `+0x1a6`) | `FUN_0052b321` | |
| 6 | end-of-tick message (type 100, tick number) to the client | `FUN_00504bb7` | |

Periodic extras by `tick & 15` (`FUN_004f08c0`): `== 6` `FUN_0056fe4d(DAT_0068d2c4)` = the group-AI pass
(group orders `FUN_00570087`, path-finder refresh, it prints "Stats: last turn ... average" timings);
`== 12` `FUN_0052bbb7` = creature slot `0x14` (regeneration, [unit-struct §3](unit-struct.md)) for every
creature, a loop over a second list (`FUN_005110b8`) and the delayed removal of dead objects
(`FUN_00510a70`), plus `FUN_004f0548`, `FUN_005162f6`, `FUN_00505f83`, `FUN_0052e122` and a loop that sends
change flags `0x10..0x80` (`FUN_005052d2`); `== 15` `FUN_004f8967` = per-player pass (`FUN_004f856a`) and
`server+0` += 1, the 16-tick block counter. Not needed for movement; phase I and H2/H3.

**Creatures** (the units) run their vtable slot `0x18` = `FUN_0050f12c` ([unit-struct §3, §6](unit-struct.md)):
effects list, death, then `FUN_0056dca2` (the Brain tick) which performs the movement, then the state
dispatch. Within a tick the units go **in creation order**: the exe's lists are singly linked and
appended at the tail (`FUN_0053c5c0`, called by `FUN_0052b246`, CONFIRMED); the map creates units in
record order, so the engine's `world.units` order (record order) is the exe's. Units created
later (summons) go to the end. Units do not interact in H1, so the order is observable only through
blocking (H2) and combat (I).

Engine order per tick (`Simulation.systems`): `selection_system` (commands), `movement_system` (movement
commands, then every unit in list order). Commands are logged `(tick, command)`.

## 3. Unit state machine

Three layers, all CONFIRMED ([unit-struct](unit-struct.md) §2, §6, §8, §9), each with the field that
holds it:

**Order** (`unit+0x50`; issued by player messages). 0 none, 1 move to cell, 2 go and pick up, 3 attack,
4 AI-internal move, 8/0x11 follow, 0xa patrol, 0xb stand (next cell), 0xc stand/guard, 0xd cast at
object, 0xe cast at cell, 0xf use structure, 0x10 removed/dead, 0x16..0x1a see unit-struct §9. An order
issuer first cancels (`FUN_0056dbfb`: target facing := facing, release the reserved cell, state := 0) and
then sets the order and the Brain mode.

**Brain** (`creature+0x1c4`): mode `+8` (0 none, 1 go to cell, 2 melee swing, 4/5/6 approach and attack,
7 pick up, 8/9 cast, 10 turn in place, 11 look around, 12 go and pick up, 15 go and use) and low-level
order `+9` (0 none, 1 swing, 2 cast, 3 move step in progress, 4 wait for status, 0xff hold). The Brain
tick `FUN_0056dca2` runs first in the creature tick and sets the state.

**State** (`unit+0x54`, dispatched at `0x50fc17`/`0x50fc2f`): 0 idle, 1 move step, 2 pick up item at
cell, 3 melee attack, 0xd cast at object, 0xe cast at cell, 0xf use structure, 0x10 dead/removed, 0x1b
AI wait. State 1 only notifies the client; the movement itself is in the Brain tick. Attack sub-phase
`+0x58`: 0 start, 5 wind-up, 7 recovery ([animation §3.4](../formats/animation.md)). Death: HP <= 0 sets
order 0, state 0, runs the dying countdown, state 0x10 at HP <= -10.

**Client action** (view `+0x8c`; what is drawn): 0 idle/stand, 1 move, 3 melee, 5 turn, 6 dying, 7
shoot, 8 cast ([animation §1.4](../formats/animation.md)). The server sends message `0x6d` (turn) when the
target facing changed and the position did not, and one move message per cell when a step starts
(`FUN_0050ff2d`).

Implemented in H1 (engine names): `Unit.order` (0 none, 1 move), `Unit.state` (0 idle, 1 move step),
`Unit.action` (`idle`, `move`, `turn`) and `Unit.mover`. Transitions:

```
idle --FollowPath--> order 1, state 1
order 1, at a cell centre, path non-empty, facing != target   -> action "turn"  (turn tick: no movement)
order 1, at a cell centre, path non-empty, facing == target   -> action "move"  (step starts, first move this tick)
step in progress (step_ticks > 0)                              -> advance one tick; at step_ticks snap to centre
order 1, at a cell centre, path empty (the tick after arrival) -> order 0, state 0, action "idle"
```

Not implemented (phase I; the data and routines are in the pages cited above): attack and cast
(states 3, 0xd, 0xe and their phases), pick up and use (2, 0xf), death and removal (0x10), stand/guard
scans (orders 0xb, 0xc), follow and patrol, the AI modes, and the effect list.

## 4. Movement

A unit moves from cell centre to cell centre in **steps** of one cell. Position = cell·256 + sub-cell
offset (1/256 cell, 128 = centre; `Unit.x/y/sub_x/sub_y`); facing is a byte, 0 = up, clockwise, 256 =
full circle; `dir8 = ((facing + 16) & 255) >> 5` (0 N, 1 NE, 2 E, 3 SE, 4 S, 5 SW, 6 W, 7 NW), direction
tables CONFIRMED at `0x553e4e`-`0x553f2f`.

### 4.1 Step length and duration (CONFIRMED `FUN_00559195`, re-read for this page)

```
base  = speed stat                                           # FUN_0055915a: group byte or unit +0x8c
if ground mover (movementType 1):
    dh = clamp(h[from] - h[to], -32, 32)                     # signed cell heights, map+0x944f4
    v  = base * SpeedMultiplier                              # map.reg Path Finding, 8
    v += (v*dh) >> 6   if dh >= 0   else   -((v*(-dh)) >> 6)   # downhill faster, uphill slower
    c  = ((cost[from] + cost[to]) & 255) >> 1 ; c = 8 if c == 0 # 8-bit sum, then halved
    v  = v // c
else:  v = base                                              # fliers and ghosts ignore terrain
v = clamp(v, 1, 63)                                          # mover+0xa8, units per tick
straight:  (dx, dy) = (v*sx, v*sy)                           # sx, sy in {-1, 0, 1}
diagonal:  (dx, dy) = (trunc(v*sx*0.70699), trunc(v*sy*0.70699))    # double 0x3FE69FBE76C8B439 at 0x5d1aa8
ticks_per_cell = ceil(256 / |dx or dy|)                      # mover+0xaa; 1 if the component is 0
```

On flat grass or land (cost 8) `v = speed`. Examples: speed 18 → 15 ticks straight, 22 diagonal (12 per
tick); road (cost 6) `v = 24`, 11 ticks; sand (14) `v = 10`, 26 ticks. Costs are `map.reg`
(Flowers and Savanna 8, not the code defaults 9 and 11; `AssetCache.map_reg`, `World.costs`).

**Speed stat** (`unit+0x8c`): monsters data.bin `speed`; humans the Reaction rule
`R if R < 12 else 12 + R//5` (+10 for the cavalry types 19 and 21; load penalty not modelled), plus the
Haste/Slow delta (`Unit.speed_mod`, effects are phase I) — [animation §3.4](../formats/animation.md). The
rule is integer division (`idiv` at `0x513aa5`): 30 of the 284 human templates carry a data.bin `speed`
one higher (the authors rounded: `Fighter_Hero` 20, runtime 19; `NPC11_*` and `NPC15_*` say 12 with
Reaction -1 = default 30, runtime 18). The template value is never used for humans, like `healthMax`
([progression §3](../data/progression.md)); `progression.derived_speed` is the runtime value. In
formation the group order's byte `+0x44` replaces it (phase H3).

### 4.2 One step (CONFIRMED `FUN_00555c7e` start, `FUN_00554fd2` per tick, `FUN_00555b38` end)

At a cell centre with a waypoint (peeked, `FUN_0055f0d0`):
1. target facing = `dir8 · 32` of the sign of the cell delta (`FUN_0054f618`).
2. if facing != target: **turn tick** (§4.3), no movement this tick; the step starts on the first tick
   at a centre with facing == target (the turn's last tick does not move).
3. else: compute `v`, `(dx, dy)`, `ticks_per_cell` for the cell; `steps = 0`; run tick 4 now.

Every step tick (`FUN_00554fd2`): `steps += 1`; `x16 += dx`, `y16 += dy` (16-bit, cell·256 + sub); the
corner quirk: for `dir8` 1 or 5, when both new offsets are exactly 0, `x16 -= 1`. If the cell
`(x16>>8, y16>>8)` changed, the unit leaves its cell list and enters the new one (`FUN_00550697`,
`FUN_0055020a`) and the reservation moves (`FUN_0055be86`). When `steps >= ticks_per_cell` the offset is
set to `(128, 128)` (`FUN_005551d6`) and, in the same tick, the centre check of `FUN_00555b38` clears the
step. The unit is at a centre again, so the next step starts **in the following tick: a straight
multi-cell walk has no idle tick between cells**.

**When does the unit occupy the next cell?** In the tick where the offset crosses a cell boundary, i.e.
after `k = ceil(128 / v)` ticks of the step on an axis (diagonal: `ceil(128 / |component|)`), roughly the
middle of the step; the cell is reserved for the target from the start of the step (`FUN_0055be86`
mode 0 in `FUN_00555c7e`: phase H2). The spatial index (`World.move_unit`) changes at that tick.

The path of N cells takes `Σ ticks_per_cell` ticks from the order's tick (the order's tick already does
the first move) plus the turn ticks; the unit is idle the tick after the last snap.

### 4.3 Turning (CONFIRMED `FUN_00556454`, `FUN_005551ef`)

`d` = angle between facing and target folded to 0..128, `rate = mover+0xa`: monsters data.bin
`turn_rate` (p9); **humans: the low byte of the speed stat**, copied by the recompute
(`FUN_0051366b`, `0x513ffc`-`0x514005`, CONFIRMED; the constructor default 8 of `FUN_0050ec60` and the
template value p7 are overwritten, and the templates' p7 equals their speed anyway), so a hero turns
as fast as it walks and Haste/Slow change both (`movement.turn_rate`). Not already turning and `d <= 0x20` (45°): facing := target at once (1
tick). Otherwise `FUN_005551ef` each tick: `d < rate` → target, else ± `rate` (clockwise when
`(facing + d) & 255 == target`, i.e. the short way; 180° goes clockwise), and `turn_ticks =
ceil(d / rate)` (announced to the client with message `0x6d` once, at the first call). Turning never moves
the unit; during it `action = "turn"` (the client draws the stand frame of the stepping facing).

### 4.4 Animation of the walk (D3, [animation §1.4](../formats/animation.md))

The client advances `odometer += sqrt(step_x² + step_y²)` per tick and shows
`moveSeq[(odometer // 16) mod len]`: distance-driven, 16 map units per frame. Engine: `Unit.odometer`
adds `int(hypot(dx, dy))` per step tick (the server step, DECISION: the client interpolates the
remaining distance with integer division, the sums agree to within one unit per cell);
`UnitSet.frame_at(..., odometer=)` and `drawlist.unit_frame` use it. The odometer persists across cells
and actions (it is never reset, CONFIRMED). The unit is drawn from its server position.

### 4.5 Engine mapping and decisions

- `FollowPath(unit_id, cells)` (debug order, `engine/sim/movement.py`) replaces `Unit.path`; cells must
  be adjacent to the previous one (the exe walks one cell per step); a step in progress finishes first
  (the new path starts from the cell being entered). Rejected: unknown or dead unit, empty path, off-map
  cell, gap. Rejected orders change nothing and are still logged.
- `Unit.mover` holds the fields of the exe's Mover (`+0x01, +0x06, +0x0a, +0x70, +0x9d, +0xa0, +0xa4,
  +0xa8, +0xaa, +0xac, +0xae, +0xb0, +0xb1`), names in `engine.world.Mover`.
- No dynamic blocking: the path is taken as given, cells are not tested against the block layer or
  other units (phase H2/H3). A walker can be ordered through water; that is the debug tool's contract.
- `World.dump()` appends one dict to a unit's entry only while it has movement state, so idle units and
  the goldens are unchanged; the dump hash covers path, step and turn state (replay test).
- Debug command: `python -m engine run MAP --debug-move UID X,Y [X,Y ...]` (UID = the map unit number,
  legs straight or diagonal from the unit's cell).

## 5. Exe addresses

| What | Address |
|---|---|
| main loop, timer | `FUN_00488aa1` (`0x488ab5`-`0x488b70`), speed `FUN_0048bfaa` |
| server step | `FUN_004f08c0` → `FUN_004f8521` → `FUN_004f84c6`, `FUN_004f04cf`, `FUN_0052b459`, `FUN_00504bb7` |
| command dispatch | `FUN_004f515d`, order issuers `FUN_0056d032` ... ([unit-struct §9](unit-struct.md)) |
| creature tick | `FUN_0050f12c` (vtable `0x5d0eb0` slot `0x18`), Brain `FUN_0056dca2` |
| move driver / step start / step tick / step end | `FUN_00555411` / `FUN_00555c7e` / `FUN_00554fd2` / `FUN_00555b38` |
| step length | `FUN_00559195`, speed `FUN_0055915a`, cost `FUN_0055a147`, constants `0x5d1aa8` |
| turning | `FUN_00556454`, `FUN_005551ef`, facing to cell `FUN_0054f618` |
| centre snap / check | `FUN_005551d6` / `FUN_00551383` |
| cell lists / reservation | `FUN_00550697`, `FUN_0055020a`, `FUN_0055be86` |
| client message | `FUN_0050ff2d`, `FUN_005040c4` (`0x6d` turn, move per cell) |
| search / wrapper | `FUN_0054d76e` / `FUN_0054d72d`; expanders `FUN_0055d010`/`0055d830` (static, size 1), `0055c6f0`/`0055c910` (static, sized), `0055e050`/`0055e870`, `0055cb30`/`0055cdf0` (dynamic) |
| path walk / fallback | `FUN_0054e58c`, `FUN_0054e886` / `FUN_005585f4` (rings), `FUN_00557f08` (follow, open) |
| drivers | `FUN_00555411` (move to cell), `FUN_0055574d` (follow), `FUN_00555dc2` (hop plan), `FUN_00558f64`, wrapper `0x56e4b0` in `FUN_0056dca2` |
| lists | `FUN_0055f170` push front, `FUN_0055f110` pop head, `FUN_0055f0d0`/`0055f0f0` peek head/tail, `FUN_005421b0` clear |
| layers / stamps | `FUN_0055fa70` (`+0x10000`), `FUN_0055fa20` (`+0x20000`), `FUN_0055be86`, `FUN_0055c2ce`, `FUN_0055c1fe`, `FUN_0055c440`, `FUN_0055c5a0`, `FUN_0056fc69` |

## 6. VERIFY IN GAME

1. **Straight and diagonal walk.** Take a hero with Reaction 30 (speed 18, check the info panel) on flat
   grass, default speed. Time 10 cells straight and 10 cells diagonal: predicted 150 and 220 ticks =
   9.3 s and 13.6 s at 16.13 ticks/s (ratio 1 : 1.47). Road (cost 6): 110 ticks straight.
2. **Turn time.** A hero (speed 18) facing north ordered to walk south (180°): `ceil(128 / 18)` = 8
   ticks (0.5 s) before the first step; with the constructor default 8 it would be 16 ticks (1 s) —
   this tells the two readings apart. Count the stand frames before the first walk frame. Also a 90°
   turn (4 ticks) vs a 45° turn (snaps, 1 tick).
3. **No pause between cells** on a long straight walk (matches [animation §3.6 #2](../formats/animation.md)).
4. **Hills.** A monster walking 10 cells up and down a 32-height slope: ±50 % step length (clamp).
5. **Occupying the next cell.** Order two of your units to swap places on a one-cell-wide road. Predicted
   (7.4): there is no swap; the unit the exe handles first turns to face the other and stops for good (its
   order is not restarted), the other finds no way round and stops too. Also: a hero walking directly behind
   another walking hero should halt and face it when the cell ahead is the leader's; record what the original
   does (this is the strangest consequence of the decode).
6. **Diagonal vs straight cost**: diagonal cells take `ceil(256 / trunc(v·0.707))` ticks, 1.47× a
   straight cell at v = 18 although the cell distance is 1.41×.

## 7. Pathfinding (phase H2)

Code: `engine/sim/pathfinding.py` (pure planners), `engine/sim/movement.py` (`MoveTo`, the driver). All
facts below were read in the GOG `allods2.exe` with REA unless marked **INFERRED**. The path-finder object
(`this` of `FUN_0054d76e`) owns 256x256 grids: costs at `+0x0000` (byte), **static layer** `+0x10000`,
**live layer** `+0x20000` (static + dynamic stamps), distance field `+0x30000` (u16, `0xFFFF` = unvisited),
frontier lists, and the config below. Cell index = `y * 256 + x`; the 8-cell map border is blocked in
the layers, so a plan never leaves the map.

### 7.1 The search (CONFIRMED `FUN_0054d76e`, wrapper `FUN_0054d72d`)

It is **not A\***: no heuristic, no priority queue. It is a **label-correcting wave fill** over a distance
field, then a **backward walk** from the target. `FUN_0054d72d(unit, tx, ty, mode, follow)` reads the start
cell from the unit's position (`FUN_0054ffb0/c0`) and calls `FUN_0054d76e(start, target, mode, follow)`.
`mode != 0` is the **static** plan, `mode == 0` the **dynamic** one.

```
dist = max(|dx|, |dy|)                             # Chebyshev (FUN_00551463)
start == target -> nothing (list left empty)
field[start] = 0; frontier X = [start]; it = 0
while field[target] == 0xFFFF and X non-empty and it < limit:
    Y = []; for c in X: expand(c) appending improved cells to Y     # half step 1
    X = []; for c in Y: expand(c) appending improved cells to X     # half step 2
    it += 2
expand(c): for each of the 8 neighbours n not blocked:
    new = field[c] + step(c, n)
    if new < field[n]:  field[n] = new; append n         # strict, a cell can be appended again
```

| Variant | Condition | Expander | Block layer | Order of the 8 neighbours | `limit` |
|---|---|---|---|---|---|
| static, size 1 | `mode != 0`, size (vtable `+0x1c`) == 1 | `FUN_0055d010` / `FUN_0055d830` | `+0x10000` | (-1,-1) (+1,-1) (-1,+1) (+1,+1), then (0,-1) (-1,0) (+1,0) (0,+1) | `dist + min(StaticScanAhead, dist>>2)`; **1000 (unbounded) when the owner's `+0x2c` is 0 (the human player) and `FUN_0055c440(target)` is passable** |
| static, sized | `mode != 0`, size > 1 | `FUN_0055c6f0` / `FUN_0055c910` | `+0x10000`, footprint test `FUN_0055c440` | x outer -1..+1, y inner -1..+1 (self included, never improves) | `dist + StaticScanAhead` |
| dynamic, size 1 | `mode == 0`, size 1 | `FUN_0055e050` / `FUN_0055e870` | `+0x20000` | as static size 1 | `dist + min(DynamicScanAhead, dist>>2)` |
| dynamic, sized | `mode == 0`, size > 1 | `FUN_0055cb30` / `FUN_0055cdf0` | `+0x20000` | as static sized | `dist + DynamicScanAhead` |

- Bodies of the A/B twins and of the size-1 / sized pairs are identical apart from list and layer offsets
  (compared instruction by instruction); the sized expanders were read in `FUN_0055c6f0`/`FUN_0055c910`, the
  dynamic ones are INFERRED to be the same code on the live layer (offset `+0x20000` read in `FUN_0055e050`).
- A cell is blocked when `layer[cell] & mask != 0`; `mask` = mover byte `+5` (0x41 walker, 0x44 ghost/bee, 0x82
  flyer, [map part 3](../formats/map.md)). A sized unit tests a `size x size` footprint with the neighbour as
  its top-left cell (`FUN_0055c440`: cells `(x + i, y + j)`).
- **No corner rule**: a diagonal step tests only its own target cell, so the unit may cut a corner between two
  blocked cells (CONFIRMED by the code; the walk itself does not check either).
- **Step cost**: straight `+2`, diagonal `+3`. When the unit's movement class (vtable `+0x20`, `FUN_0055f330`) is
  1 (walker) the cost layer is used instead: straight `+c`, diagonal `+c + (c >> 1)` with `c` = the cost byte of
  the **entered** cell (`map.reg` terrain costs, [map part 3](../formats/map.md)). Heights never enter.
- The field is cleared per search (a window of `limit * 257 + 512` indices around the start for size 1, the whole
  field for sized units; the window is wide enough that stale values are never read). The wave is a BFS by
  *levels* (`it` counts levels, 2 per loop), not by cost: a cheaper route found later still lowers a label
  (re-appended), but the search stops after `limit` levels. Both half steps run before `field[target]` is tested.
- **Config** (`map.reg` `[Path Finding]`, constructor `0x5543d9`-`0x5545d6`, defaults): SpeedMultiplier 8,
  StaticScanAhead 5 (`+0x58584`), DynamicScanAhead 3 (`+0x58588`), StaticRefreshRate 16 (`+0x5858c`),
  DynamicRefreshRate 32 (`+0x58590`), DynamicByStaticLookup 3 (`+0x58594`), StaticIsntNeeded 5 (`+0x58598`).

**Extracting the path** (`FUN_0054e58c` static, `FUN_0054e886` dynamic; the code is identical): starting at the
end cell `e` (the target, or the fallback below), repeat until `cur == start` (at most 1000 steps, else the plan is
dropped): look at the 9 cells `cur + (dx, dy)`, dx outer -1..+1, dy inner -1..+1, inside `[8, size + 8]`; an
unvisited one is skipped. Orthogonal or self: `cand = field[n] + (walker ? cost[cur] : 2)`, taken when
`cand <= best` (**ties go to the later cell**); diagonal: `cand = field[n] + (walker ? c + c>>1 : 3)`, taken when
`cand < best` (**strict**). `cur += step`. Cells are pushed at the head of the list (`FUN_0055f170`), the start
cell last and then popped (`FUN_0055f110`), so the list reads first step ... end cell. The tie rule decides
which of two equal routes is walked: the walk goes target -> start and prefers, among equal costs, the *last*
orthogonal neighbour in (dx, dy) order and the first-best diagonal.

**Unreachable target** (`field[target]` still `0xFFFF`): `FUN_005585f4(unit, 0, target, radius)` scans rings
`r = 1 .. radius - 1` around the target (per `o = -r .. r`: cells (+o, +r), (+o, -r), (+r, +o), (-r, +o)) for the
visited cell with the **smallest field value** (first one in scan order wins ties), stops at the first ring
that has any, returns 0 when none. So the unit walks to the reached cell *cheapest from itself* within the
first ring around the target that the wave touched, not the one nearest the target. Static: `radius = dist>>2 + 4`;
dynamic without follow target: 8; dynamic with a follow target: `FUN_00557f08` (open). No cell: the list stays
empty (the order sees `mover+0x98 = 1`). The static branch also calls `FUN_005052d2(1, 0, owner)` when the
fallback cell is more than 1 cell from the target (more than 2 when `FUN_00559bc9(target)` is non-zero: a
target cell with bit `0x20` of `+0x10000` and a record in the cell table, i.e. a building cell, returns the
record's holder): CONFIRMED it posts client message `0x92` (`FUN_00505347`), whose handler (`0x40e21d`, sub-code
1) shows text string `0x81` for 3000 ms ("can't get there" feedback, wording not looked up). It does not
change the route. A clause for unit class 0x12 on order 5 (`FUN_00556f56`, `FUN_0056ac5b`) rewrites a range
field of the brain: range logic, not routing (open).

### 7.2 Two layers: static plan, dynamic hops (CONFIRMED `FUN_00555411`, `FUN_00555dc2`)

The unit owns two lists (`+0x1c8` static, `+0x1e4` dynamic). The mover consumes the **dynamic** list
(`FUN_00555c7e` peeks it; empty = a turn step); the static list is the long plan.

Move order entry (wrapper `0x56e4b0` in the Brain function `FUN_0056dca2`): `mover+0x6c = 1`; if `mover+0x74`
(last target) != the order's target cell then `mover+9 = 0xFF` (force a re-plan); then `FUN_00555411(target, arrive)`.

`FUN_00555411` runs every tick:
1. Not at a cell centre -> `FUN_00555b38` (continue the step). Nothing else.
2. At a centre, `arrive < dist(cell, target)`: `mover+0x78 += 1` (ticks since the last hop plan), then
   **static re-plan** when `mover+0x74 != target` or `mover+9 > StaticRefreshRate`: `FUN_0054d72d(target, mode 1)`
   into the static list, `mover+0x90 = 0`, `+0x74 = target`, `+0x76` = last cell of the static list (own cell and
   `+0x98 = 1` when empty), `+9 = 0`, dynamic list cleared.
3. `cell == mover+0x76` -> `mover+0x90 = 1` (arrived; the brain ends the order, [open question 1](#open-questions)).
4. Otherwise, if the dynamic list is empty or `mover+0x78 > DynamicRefreshRate`: **hop re-plan**. `next` = the
   static list head if it is adjacent (`FUN_00558f64`). If `next` exists and its footprint is blocked in the live
   layer (`FUN_0055c5a0`, returns 1 when free), `FUN_0056fc69` decides whether to wait for the blocker (human-owned
   size-1 units only, see 7.4); a wait skips both the hop plan and step 5. Otherwise `FUN_00555dc2`: with `n` = static list length and `d` = Chebyshev distance to its head,
   goal = the static tail if `n <= StaticIsntNeeded`; else the head if `d > DynamicByStaticLookup`; else the element
   `DynamicByStaticLookup` places behind the head. `FUN_0054d72d(goal, mode 0)` fills the dynamic list; if that
   list is empty and the goal was the tail `+0x98 = 1`; if `n > 0` and `d <= DynamicByStaticLookup` the static head
   is popped. Then `mover+9 += 1`, `mover+0x78 = 0`.
5. `FUN_00555c7e`: start the next step from the dynamic list (turn first if needed, §4).
6. `arrive >= dist` and `arrive != 0` -> `FUN_00556da2` (stop); with `arrive == 0` nothing happens at dist 0.

**The dynamic list lives for one step** (CONFIRMED `FUN_00555b38`, asm `0x555c14`-`0x555c1d`: the step end
clears the list at `unit+0x1e4`; nothing else consumes it, and the only other pops are the extraction's start
cell and the static-list pop in `FUN_00555dc2`). So a hop plan is made at **every cell centre**, only its first
step is walked, `mover+9` grows by one per cell and the static list shrinks by one per cell (head popped when
within `DynamicByStaticLookup`): the static plan is renewed every 17 cells. The 32-tick `DynamicRefreshRate`
is only a fallback for a non-empty list (never so at a centre). `FUN_0054f38a` (peek/pop of the list, trims the
static list to the current cell with `FUN_005516dd`) has no caller or vtable reference in the exe (dead code).
Units entering the next cell between two centres are therefore noticed at the next centre, not mid-step: a step
is never aborted. `FUN_0055574d` is the same driver for a
follow target (re-plan every `len/3 + 1` consumed waypoints, StaticIsntNeeded gate; open).

### 7.3 Engine implementation (DECISIONS)

- `plan_static(grid, start, target, size, walker, ..., human)` and `plan_dynamic(...)` are pure functions of a
  `PathGrid` (blocked bool grid already masked for the mover, cost grid or `None`, `size`) and return a
  `PathResult(cells, searched, found, fallback)`; `searched` = the cells that received a label, in the order
  they were first labelled (debug overlay). No pygame, no world mutation.
- `blocked` for the static plan = `World.block & MOVE_MASK[move_type]`. **CONFIRMED** that the exe's static layer
  (`+0x10000`) holds the structure stamps too (see "Live layer" in 7.4): `FUN_00550a96`, `FUN_005589ab` OR `5`
  into `+0x10000` and `+0x20000` alike, so `World.block` (which includes structures) is the right static grid.
  Only the unit stamps (0x40 / 0x80) are live-only.
- Live layer for hops = the static grid plus the unit stamps of every **other** living unit, **CONFIRMED** in
  7.4: `size x size` footprint at its cell and, while it walks, at the cell it is entering; bit 0x40 (ground
  classes) is seen by walkers and ghosts, bit 0x80 (class 3) only by flyers (`engine/sim/movement.py
  live_cells`). The unit's own footprint is released before planning (`FUN_0054d76e` calls `FUN_0055be86`
  mode 2). Death/removal of a stamp for hp <= 0 is INFERRED. The exe's first-come slot per cell is not modelled.
- `MoveTo(unit_id, x, y)` is the engine-level move order (order 1); the click mapping is H3. It follows steps
  1-6 above with the unit's `Mover` carrying `dest (+0x74)`, `tail (+0x76)`, `consumed (+9)`, `since_hop (+0x78)`,
  `arrived (+0x90)`, `failed (+0x98)`, `static_path`; `Unit.path` is the dynamic list. An arrived or failed unit
  returns to order 0 / state 0 on the next centre tick (as `FollowPath` does).
- Size = `token_size` (vtable `+0x1c` = `0x542360` reads `+0x49`, CONFIRMED); movement class = `movement_type`
  (vtable `+0x20` = `0x542380` reads `+0x4a`, CONFIRMED). The hop goal "`DynamicByStaticLookup` places behind the
  head" is the 4th element (index 3): the loop fetches `lookup + 1` elements with `FUN_0055f1f0`, taken as
  MFC-style get-and-advance (INFERRED).
- A finished order clears `dest`/`static_path` (DECISION; the exe keeps `+0x74`, so a repeated order to the
  same cell would skip the static plan there: open).
- `FUN_0056fc69` is modelled for human-player size-1 units (`blocker_verdict`, `_begin_wait`, `_tick_wait`;
  `Mover.waiting` = brain mode 10, `Mover.parked` = mode 0 under a move order, dumped only when set); every
  other unit re-plans around the blocker. See 7.4.
- Performance and search statistics: see 7.5.

### 7.4 Read but not implemented (needs orders/AI of phase I)

- **Follow-target fallback** (`FUN_00557f08(unit, target unit)`, CONFIRMED read, INFERRED reading): when the dynamic
  search toward a *unit* target (`FUN_0055574d`) leaves its cell unlabelled, the routine walks a box perimeter around
  the target's footprint (`token_size`) as seen from the follower (start side from `FUN_00557cf1`, direction table
  `+0x54156`, the box grows by one cell per attempt, at most 8 attempts) and returns the labelled cell with the
  smallest label (strict `<`, first wins). Ring order uses float trig helpers (`FUN_0050d884/8c0`) not yet
  decoded; `MoveTo` has no unit target, so the engine uses the cell fallback only.
- **Blocker handling** (`FUN_0056fc69(this, unit A, next cell)`, CONFIRMED read of the whole routine and its
  caller `0x55567d`; there is **no swap**: nothing ever tells the blocker to move). Reached when the static
  head is adjacent and `FUN_0055c5a0` (1 = free, loop over the `size x size` footprint of the live layer with the
  mover mask `mover+5`) says it is not. Verdict in AL (0 = re-plan round the blocker, 1 and 2 are treated alike):
  1. A not size 1 (vtable `+0x1c`) or its owner's `+0x2c != 0` (computer player): 0. `mover+0x80 == cell`
     (the cell A itself stamps, never true for an adjacent cell at a centre): 0.
  2. `B` = the unit of the cell record (`FUN_00551edb`: needs bit `0x20` in `+0x10000`, record lookup
     `FUN_0055f3e0`, unit pointer at rec `+4`; friend or foe, no relation test). No record: `FUN_0054ec6a(cell, 1)`
     lists the units of the 3x3 around it; one whose `mover+0x70` (cell its step began on) is `cell` and that
     is off-centre (`FUN_00551383`: sub-offset bytes both 0x80 = at centre) -> 2, else 0.
  3. B with HP (`+0x94`) < 1: 0. B off-centre (mid-step): 0 if A's `mover+6` (last cell it entered) is `cell`,
     else 1. B at a centre: brain mode (`+0x1c4 -> +8`) 1 (go to cell) or 4 (approach object): 0 if A's own
     destination (`brain+0xa`) is `cell`, else 2; any other mode (idle 0, 10 turning, attacking...): 0.
  4. Non-zero verdict (`0x555692`-`0x5556eb`): `FUN_00556b2c` = facing to the cell (0, 32 ... 224, ratio rule,
     equals `facing_to` for adjacent cells). Already facing it: mode := 0. Else `FUN_00556da2` (=
     `FUN_00556454(unit, facing)`, starts the turn) and mode := **10**. `FUN_00555c7e` (the step) is skipped, the
     counters `mover+9`/`+0x78` keep running, no other state is touched.
  5. **Mode 10** has one reader, the brain dispatch `0x56e157` -> `FUN_0056e55d`: while `mover+0` (facing) !=
     `mover+1` call `FUN_00556454` again and `unit+0x54 = 1` (turning), else mode := 0, state := 0.
     Mode 10 is written only by `0x5556d8`. Mode 0 does nothing: the unit stands with order 1 and no driver.
  6. Consequences (CONFIRMED code, INFERRED play): the first unit processed (creature order) that meets a
     walking blocker waits for good; its partner then sees mode 0/10 and re-plans (a one-cell road: no way,
     it stops). A mid-step leader directly ahead also halts a human follower. No code restarts mode 1: the
     only mode-1 setter for order 1 is the order executor `FUN_00569321` (`0x569409` -> `FUN_0056c8af`),
     which is reached only from the group-message handler (`FUN_00570087` type 0 -> `0x56fe34`, run at
     `tick & 15 == 6`) and from two functions without callers (`0x56920c`, `0x56dc49`, not in any vtable).
     So a parked unit resumes only on a new command (engine: `MoveTo`/`FollowPath` clear `parked`).
     Contradicts unit-struct §9, which calls `FUN_00569321` a per-tick executor; the call graph does not.
- **Live layer** `+0x20000` and the cell-record table (CONFIRMED, GOG exe):
  - The path-finder keeps a hash map of 60-byte **cell records** at `+0x54084` (lookup `FUN_0055f3e0` copies a
    record into the scratch record at `+0x5402c`, `FUN_0055f430` writes it back, `FUN_0055f460` deletes it) for
    every cell that carries a stamp. Bit `0x20` of `+0x10000` = "this cell has a record" (set by `FUN_005508a0`,
    which creates the record from the cell's current cost byte (rec `+0`) and static byte (rec `+1`), cell
    index at rec `+0x3a`). `FUN_00559bc9` (7.1) reads it.
  - `FUN_00550a96(rec)` rebuilds one cell from its record: cost := rec`+0`, static := rec`+1` | 0x20, live :=
    static, then re-applies the contributions: rec`+0x2c` (ground unit slot) -> live |= `0x40`
    (`FUN_00550de0`); rec`+0x30` (class-3 unit slot) -> live |= `0x80` (`FUN_00550e12`); rec`+0xc` (a
    structure with a footprint bitmask at `+0x64`, width `+0x60`) -> static and live |= `5` when the cell's
    mask bit is set, else `&= 0xfa` and cost := `+0x5414b`; rec`+0x20` non-zero -> static and live |= `5`;
    each non-zero rec`+0x14 .. +0x28` entry shifts the cost byte left by 2; the `0x10` bit is preserved.
    So `+0x10000` DOES contain the structure stamps (5 = 1|4) and `0x20`; unit stamps are live only.
  - `FUN_0055c2ce(unit, cell)` stamps: make the record if needed, then take the slot (rec`+0x2c`, or
    rec`+0x30` when the unit's movement class `FUN_0055f330` is 3) **only if empty or already this unit**
    (first come, first served), then `FUN_00550a96`. `FUN_0055c1fe(unit, cell)` releases: if the cell has a
    record, clear the slot when this unit holds it, rebuild, and when the record is empty (`FUN_005513b6`)
    delete it and restore cost and static bytes (`FUN_00550966`).
  - `FUN_0055be86(unit, cell, mode)` builds an 8 x 8 table around the unit (origin = its cell - 1): the
    `(size+2)^2` square is 1 (release ring), mode 0 sets the `size^2` footprint at `cell` to 2, modes 0 and 1 set
    the footprint at the current cell to 3 (3 overwrites 2), mode 2 sets neither; then 1 -> `FUN_0055c1fe`,
    2 and 3 -> `FUN_0055c2ce`. Mode 0 also records `cell` in the unit's mover `+0x80`, mode 1 the unit's own
    cell, mode 2 zero. Sizes up to 6 fit the table.
  - Calls of `FUN_0055be86`: step start mode 2 then mode 0 with the next cell (asm `0x554f56`-`0x554f9f`,
    `0x555136`-`0x555181`, `0x555cee`-`0x555d15`), step end mode 2 then mode 1 (`FUN_00555b38`, `0x555bf4`-`0x555c0f`),
    standing units mode 1 (`0x558b7c`, `0x56a5df`), planner entry mode 2 (`FUN_0054d76e`, `0x54dd04`), removal
    `FUN_00553891` (mode 2). A walking unit thus holds its footprint at both its cell and the cell it enters.
  - Masks: walker 0x41, ghost 0x44 contain `0x40`; flyer 0x82 contains `0x80`; none contains `0x20` or
    `0x10`. So ground units block walkers and ghosts, flyers block only flyers, and a flyer ignores structures
    (bits 1 and 4 not in 0x82). Walkers and ghosts see structure stamps (1 resp. 4).
  - Other writers: `FUN_005589ab(.., w, h, mask)` ORs 5 into both layers over a w x h box for set mask bits
    (structure footprint); `FUN_00559c28` / `FUN_00559ce5` set / clear bit `0x10` in both layers (bit in no
    mover mask; meaning not decoded); `FUN_00558aab` adds a fixed 4 x 3 block at (0x3e..0x41, 0x18..0x1a)
    (static += 5, live |= 5), a leftover test stamp.
- **Unreachable feedback**: client message `0x92` (7.1), a UI matter for H3.

### 7.5 Measured

`tools/bench_pathfinding.py` (pure Python, 200 random walkable pairs per map, human unit = unbounded search,
one core of this machine): worst case **168 ms on the largest map** (`110.alm`, 256 x 256, 40,465 labelled
cells), 44-50 ms on the 144 x 144 maps, typically 2-10 ms for a 50-150 cell route (the first version of
the planner measured 444 ms and 124-160 ms). The wave labels every cell within the route's cost radius, so cost
grows with the area, not the route length. Speed-up (results bit-identical, pinned by
`tests/test_pathfinding_differential.py` against the frozen original `tests/pathfinding_reference.py`): the
sequential label-correcting order is kept (a cell reads its label when expanded, re-appends define `searched`,
so a numpy level fill cannot reproduce it); blocked / footprint-not-free cells hold label 0 in the working
field so the strict `<` rejects them with no test (the field template is cached per blocked layer and size),
the field is a list, and the 8 neighbours are source-generated and unrolled per order. About 2.6-3x faster; the rest
is the irreducible per-expansion cost (~9 expansions per labelled cell). Still one plan per order and per 17
hops; a per-tick plan budget stays a gameplay decision. Golden routes: `tests/golden.json["paths"]`
(`tests/test_pathfinding_maps.py`, regenerate with `tools/update_golden.py`).

### 7.6 VERIFY IN GAME (pathfinding)

1. **Corner cutting.** Two blocked cells touching at a corner (e.g. two trees on a diagonal): order a walker
   through the diagonal gap. Predicted: it squeezes through (no corner rule); a 2-cell-wide pair of trees at
   (x, y) and (x+1, y+1) lets a unit at (x+1, y) go to (x, y+1).
2. **Equal routes.** On open grass from (0,0) to (4,2) the predicted route (walker, uniform cost) starts
   with diagonal steps first or last: see `tests/test_pathfinding.py::test_open_ground_route` and compare the
   original; this fixes the tie rule of 7.1.
3. **Unreachable target.** Order a walk to the middle of a lake: the unit should stop on the shore cell that was
   cheapest to reach among the first ring around the target, not the cell closest to it.
4. **Search limit.** An AI (computer) unit ordered round a wall longer than `dist + min(5, dist/4)` levels stops
   short at the fallback cell; the same order for the human player's unit walks all the way (limit 1000).
5. **Re-plan.** Walk 40 cells and place a unit on the road ahead: the walker should re-route at the next cell
   centre (hop plans are made every cell), not mid-step; it may share the cell if the blocker steps in during
   the step.
6. **Standing orders.** Order the same walk twice from different spots (second time to the cell the first
   ended on): the engine plans afresh; the exe may reuse `+0x74` (see 7.3).
7. **Road preference.** Walker cost = terrain cost: a road (cost 6) beside grass (8) should attract the route
   when it adds at most a few cells.

## Open questions

1. Waypoint removal from the path list and the exact tick the order ends after arrival. Known: the
   move driver `FUN_00555411` calls `FUN_00555c7e` on every tick at a centre until `mycell == +0x76`
   (then `mover+0x90 = 1`, set on the tick after the last snap); the list is only peeked
   (`FUN_0055f0d0`). The client idles after the move message's `N` ticks regardless (§4.2), so the
   visible stop is exact. Start at `FUN_00569321` (order 1 auto-stop), `FUN_00555dc2`. H2.
2. Group speed (`+0x44`, formation) and Haste/Slow in `unit_speed`: H3 and phase I.
3. The regeneration job runs from `FUN_0052bbb7` at `tick & 15 == 12` while the slot itself tests
   `server tick & 3 == id & 3`: the interaction needs a check in phase I
   ([unit-struct §3](unit-struct.md)).
4. The group-AI pass at `tick & 15 == 6` (`FUN_0056fe4d`): phase I and H3.
5. Blocker wait (7.4): who feeds the type-0 group message that re-runs the order executor (`FUN_00570087` case 0,
   `FUN_00569321`) and whether a parked unit is ever restarted; mode 4 blockers (approach object) and the exe's
   first-come cell record (engine: first unit in list order). The meaning of live/static
   bit `0x10` (`FUN_00559c28`, callers `0x518589`, `0x51899b`) and the death-time stamp release.
6. Follow-target planning: the ring order of `FUN_00557f08` (float helpers `FUN_0050d884/8c0`, `FUN_00557cf1`) and
   the driver `FUN_0055574d` (7.4); phase I with attack orders.
7. The class-0x12 / order-5 clause of the static fallback (`FUN_00556f56`, `FUN_0056ac5b`); the text of
   string `0x81` (message `0x92`, the unreachable feedback) and whether the engine should show it (H3 UI).
