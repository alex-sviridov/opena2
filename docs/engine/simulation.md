# Simulation: tick, update order, unit states, movement

Phase H1. The game tick, what a server tick runs and in what order, the unit state machine, and the
rules by which a unit walks a given path, (§7, H2) how it finds one, and (§8, H3) how the player's commands
become orders. Code: `engine/sim/` (`clock.py`, `simulation.py`, `orders.py`, `movement.py`),
`engine.world.Unit` / `Mover` / `OrderGroup`. The research behind §8: [click-to-move-research](click-to-move-research.md). Facts are marked **CONFIRMED** (GOG
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

### 1.1 Command path, latency and the counter at start (CONFIRMED, REA on the GOG exe)

- **Two hubs, cross-linked** (single player): `0x670e50` (client, flag `+0x18b0` = 0, ctor `0x501a11`) and `0x6831a8` (server,
  flag 1, ctor `0x5019d0`; ctor `FUN_0050077a`). The game start (`FUN_0040d480`, game mode `+0x5d8` 1 or 2, `0x40d4c8`-`0x40d4f0`)
  calls `FUN_00500a72` on each with the other as peer (`hub+8`): it creates one *local* connection (`hub+0x18b4`, flag
  `conn+0x29c := 1` via `FUN_00540030`). No socket, no thread.
- **Send** (`FUN_0050164f`, e.g. the move command `FUN_00418bc3`): the message is serialised (vtable slot `+8`) into the connection's
  `0xa8`-byte chunk buffer (`FUN_005000a1` appends and flushes by itself when a chunk is full); then, because the hub flag is 0 and
  the command is not type 100, `FUN_00504bb7(1)` sends an end-of-tick message (type 100, value 1) and calls `FUN_005017e6`, which
  runs the flush `FUN_0050036a` on every connection. The flush of a local connection (`conn+0x29c != 0`) moves the packet **at once**
  into the peer connection's receive queue (`FUN_0053f270` = `hub+8 -> +0x18b4`, enqueue `FUN_0050023b`, under a critical
  section). So when the send returns, the whole command is already in the server hub's queue.
- **Drain** (`FUN_004f84c6`, called only from `FUN_004f8521`, right after the counter increment): `FUN_00501831` pops until the queue
  is empty, so *every* command that arrived before the step starts is applied by that step, in arrival order.
- **Latency = 0 extra ticks.** A command sent at any moment between server step N-1 and step N (the window message pump runs
  outside `FUN_00488aa1`; the loop body is server step, `FUN_0040d9b2`, post `0x401`) is applied by the drain of step N. The engine
  maps this to: the commands handed to `Simulation.step` are applied by that step and logged with its `world.tick`; the UI puts a
  command into the next step after the click (`CommandQueue.drain`). No delay is added anywhere, nothing in the packet holds a tick.
- **The client's tick view** is not part of the path: the move message has no tick field, and the client never waits (no lock-step
  in single player). The server ends each step with `FUN_00504bb7(counter)` (`0x4f855c`, counter *after* the increment), delivered
  by the same synchronous flush; the client drains its hub in the same pass (`FUN_0040d9b2`, loop at `0x40d9f2`) and stores the
  value in `client+0x408` (type 100 handler `0x40da4b`). The client's own value-1 type-100 messages go to the server queue.
- **Counter at start**: a new game runs `FUN_004eb715` (server start): when no save is being loaded (`this+0x1ac == 0`) it stores
  `server+0 := 0` and `server+4 := 0` (`0x4eba47`/`0x4eba50`), then `server+0x94 := 1` (`0x4eba8d`, the running flag tested at the
  top of `FUN_004f08c0`) and clears the profiling counters `+0x1b4..+0x1c4`. So the first step runs the group-pass test with the counter
  at 0 and increments it to 1: the pass first runs in the 7th step (counter before increment 6), then every 16. Engine: `world.tick`
  starts at 0 = the exe's value; `Simulation.block` = `(world.tick + 1) >> 4` is `server+0` (incremented at `0x4f0ab7` after the
  step whose counter after the increment is 15 mod 16, together with the per-player pass `FUN_004f8967`). With a loaded save the
  counters come from the save: `FUN_004e9b95` -> the server stream `FUN_004ec732` reads `server+4` (tick) then `server+0` (block) as its first two words and nothing re-derives
  them ([saves §6.2](../formats/saves.md#62-the-server-stream-fun_004ec732-the-same-routine-saves-and-loads-mfc-archive-little-endian), CONFIRMED).

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
(group orders `FUN_00570087`, path-finder refresh, it prints "Stats: last turn ... average" timings; it runs
**before** the counter is incremented and before the command drain; the move-group part is §8.3);
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

Engine order per tick (`Simulation.systems`): `orders_system` (group pass when `world.tick & 15 == 6`, then the
order commands: §8), `selection_system`, `movement_system` (`FollowPath`, then every unit in list order).
`world.tick` at the start of a step is the exe's counter before its increment (CONFIRMED: the server counter starts
at 0 on a new game, 1.1). Commands are logged `(tick, command)`.

## 3. Unit state machine

Three layers, all CONFIRMED ([unit-struct](unit-struct.md) §2, §6, §8, §9), each with the field that
holds it:

**Order** (`unit+0x50`; issued by player messages). 0 none, 1 move to cell, 2 go and pick up, 3 attack,
4 AI-internal move, 8/0x11 follow, 0xa patrol, 0xb stand (next cell), 0xc stand/guard, 0xd cast at
object, 0xe cast at cell, 0xf use structure, 0x10 removed/dead, 0x16..0x1a see unit-struct §9. An order
issuer first cancels (`FUN_0056dbfb` = `FUN_0056d969` + `brain+0x50 := 0`: target facing := facing, release the
reserved cell only at a centre, state := 0; it does **not** write `unit+0x50`, the issuer overwrites that next,
[research §3.4](click-to-move-research.md)) and then sets the order and the Brain mode.

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

Implemented (engine names): `Unit.order` (0 none, 1 move, 0xc stand/guard; H3), `Unit.state` (0 idle, 1 move
step), `Unit.action` (`idle`, `move`, `turn`) and `Unit.mover`. H1 transitions of the debug order `FollowPath`
(the player's orders end differently: §8.3):

```
idle --FollowPath--> order 1, state 1
order 1, at a cell centre, path non-empty, facing != target   -> action "turn"  (turn tick: no movement)
order 1, at a cell centre, path non-empty, facing == target   -> action "move"  (step starts, first move this tick)
step in progress (step_ticks > 0)                              -> advance one tick; at step_ticks snap to centre
order 1, at a cell centre, path empty (the tick after arrival) -> order 0, state 0, action "idle"
```

Not implemented (the melee attack, death and removal 0x10 are done in I1/I2, [combat](combat.md); the rest: phase I+; the data and routines are in the pages cited above): attack and cast
(states 0xd, 0xe and their phases), pick up and use (2, 0xf), stand/guard
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
formation the group's byte `+0x44` replaces it (`movement.walk_speed`, §8.2; the turn rate keeps the stat).

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
| path walk / fallback | `FUN_0054e58c`, `FUN_0054e886` / `FUN_005585f4` (rings), `FUN_00557f08` (follow, 7.4) |
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
   (7.4): there is no swap; the unit the exe handles first turns to face the other and stops; the other finds no
   way round and stops (order 0xc) at once; the first is restarted at the next group pass (within 16 ticks) and,
   seeing an idle blocker, finds no way round either (it keeps order 1). Also: a hero walking directly behind
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
dynamic without follow target: 8; dynamic with a follow target object: `FUN_00557f08` (7.4). No cell: the list stays
empty (the order sees `mover+0x98 = 1`). The static branch also calls `FUN_005052d2(1, 0, owner)` when the
fallback cell is more than 1 cell from the target (more than 2 when `FUN_00559bc9(target)` is non-zero: a
target cell with bit `0x20` of `+0x10000` and a record in the cell table, i.e. a building cell, returns the
record's holder): CONFIRMED it posts client message `0x92` (`FUN_00505347`), whose handler (`0x40e21d`, sub-code
1) shows text string `0x81` for 3000 ms (main.txt line `0x81` = "No way", [research §6.3](click-to-move-research.md)). It does not
change the route.

**The range clause (CONFIRMED, `0x54e245..0x54e2c1`, same unreachable-static branch, after the "No way" test and
before the empty-list test).** It is not "unit class 0x12": the byte is the *group order* `((unit+0x70)+0x3c)+0x20`
(the GroupAI record, [click-to-move §4.4](click-to-move-research.md)) `== 0x12`, and the brain mode `brain+8 == 5`
(attack approach, order 3, `FUN_0056eab5`; the issue says "order 5"). Then
`gap = FUN_00556f56(fallback, target, size)` (`size` = vtable `+0x1c`; per axis `h < t ? max(0, t-h-size+1) : h-t`,
larger axis; fallback packed 0 = cell (0, 0)) and, if `gap > FUN_0056ac5b(unit)` (unsigned bytes), the unit stamps
`brain+0x16 := low word of the server tick` (`[0x6044c4]`). Nothing else changes: no route, no cell, no target.
`FUN_0056ac5b` (ECX unused): `spell = spellbook(+0x140).find(brain+0x78)` when `brain+0x78 != 0`; if found and signed
`unit+0x9a (mana) >= spell+0xc` the result is byte `spell+9` (spell range), else byte `unit+0x12c`. Group order `0x12` is
`FUN_00570aba` (default of the computer players' groups: after the map load pass `FUN_00562745` every group whose
owner `player+4 != 1` gets it, the human's groups get order 3 = stand ground; also summons `520c3e`, unit creation
`5611f8`, message `577d49`). The only reader of `brain+0x16` is the group-order-`0x12` handler `FUN_005728fa`
(`0x572a1a`, `0x572a66`; INFERRED meaning): for a damaged member (`+0x94 != +0x96`) a stamp within 30 ticks
(`abs(stamp - tick16) < 30`; 10 for an undamaged one) restarts the unit's mode with its home cell `brain+0x9c`
(`FUN_0056c8af`), i.e. a guarding monster that cannot reach its attack target goes home. Reachability: every monster
of the 46 maps starts in a group of order `0x12`, but the clause needs brain mode 5, which only attack orders create; the
engine issues none (phase I), so it is **unreachable today**. Implemented as the pure functions `footprint_gap`,
`default_range`, `fallback_stamp` in `engine/sim/pathfinding.py` (tests `tests/test_pathfinding_range_clause.py`),
not wired.

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
3. `cell == mover+0x76` -> `mover+0x90 = 1` (arrived; the brain ends the order, [§8.3](#83-cancel-timeline-group-pass-stop-r-34-44-5-7)).
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
follow target (re-plan every `len/3 + 1` consumed waypoints, StaticIsntNeeded gate; 7.4).

#### List operations, every branch (CONFIRMED, asm read: `FUN_00555dc2`, `FUN_00555411`, `FUN_0054e886`, `FUN_0054d76e`)

Both lists are MFC `CList`s (head `+4`, tail `+8`, count `+0xc`; node = next, prev, data). Ops: `FUN_0055f090` count,
`0055f0b0` empty, `0055f0d0` peek head, `0055f0f0` peek tail, `0055f110` **RemoveHead**, `0055f170` AddHead,
`0055f1d0` head position, `0055f1f0` get-next, `005421b0` RemoveAll. Config: Lookup `+0x58594` = 3, IsntNeeded
`+0x58598` = 5. Every removal in the exe:

| # | Where | Rule |
|---|---|---|
| 1 | `FUN_0054d76e` `0x54d7be`-`0x54d7c7` | mode != 0 (static plan): RemoveAll on the static list `+0x1c8` before anything else, also when start == target (returns at `0x54d817` with the list left empty). Mode 0 never clears the dynamic list. |
| 2 | `FUN_0054e58c` / `FUN_0054e886` `0x54e8a0`-`0x54e8af`, `0x54eb27`-`0x54eb41` | the walk back **AddHeads** the end cell, then each predecessor, ending with the start cell; the list is not cleared first, so a non-empty list keeps its old cells behind the new ones. |
| 3 | same, `0x54eb4b`-`0x54eb75` | after the walk: more than 1000 steps (`0x3e8`) -> RemoveAll of the whole list (stale cells too); else RemoveHead = the **start cell** (the plan never contains the own cell). Start == end at the first test: list = [start] -> popped, empty. |
| 4 | `FUN_0054d76e` `0x54e2ce` | static fallback found no cell (`FUN_005585f4` = 0): RemoveAll static list. Dynamic fallback found no cell (`0x54e36a`): return, dynamic list untouched. |
| 5 | `FUN_00555411` `0x5555b8` | static refresh (target changed or `+9 > 16`): after the static plan, `+0x76` := static tail (`0055f0f0`) or, when the plan is empty, the own cell and `+0x98 := 1` (`FUN_00556447` called twice is an empty function); `+9 := 0`; **dynamic list RemoveAll**. |
| 6 | `FUN_00555b38` `0x555c14` | every step end: dynamic RemoveAll (7.2 above). |
| 7 | `FUN_00555dc2` `0x555f51`-`0x555f7b` | **the only waypoint pop**: after the hop search, if the static count `n` (read before the search) is non-zero and `d <= Lookup`, RemoveHead of the static list. It does not depend on the goal branch. |

`FUN_00555dc2` branches (`n` = static count, `d` = Chebyshev(own cell, static head), 0 when `n == 0`; `n` and `d` are read
before the search):

| branch | test | goal | flag |
|---|---|---|---|
| 1 | `n <= IsntNeeded` (incl. `n == 0`) | static tail `+0x76` | `1` |
| 2 | else `d > Lookup` | static head | `2` |
| 3 | else (`d <= Lookup`) | element index `Lookup` (3) of the static list (`Lookup + 1` get-next calls from the head position; `n > 5` so it exists) | `3` |

Then `FUN_0054d72d(goal, mode 0)`; then, if the dynamic list **as a whole** (old cells included) is empty and the flag is 1:
`+0x98 := 1` (failure; the brain ends the order at once). Then the pop of rule 7. So: `d <= 3` pops in branches 1 and 3
(the plan shrinks by one per cell near the end and by one per cell when `n > 5`); `d > 3` (branch 2) never pops, and
`d > 3` with `n <= 5` goes to the tail without popping; an empty hop plan fails only for a tail goal; a plan that is empty
(`n == 0`) pops nothing. Arrival is not a removal: `cell == +0x76` sets `+0x90 := 1` and leaves both lists as they are
(the static list still holds the tail). `mover+0x78` is a byte and wraps (`0x55549a`).

Engine (`movement._hop_plan`, `_static_plan`, `_drive`) follows all seven rules. Fixed by this review: the hop result
used to **replace** the dynamic list; it is now pushed in front of the existing cells (rule 2), and a "too long" search empties
the list (rule 3). This only matters when the list is non-empty at a re-plan: a unit that is turning at a centre
(`path` kept, no step started) for more than `DynamicRefreshRate` (32) ticks, i.e. turn rate below ~4. `since_hop` now wraps
as a byte. Goldens unchanged.

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
  7.4: `size x size` footprint at its cell and, while it walks, at both ends of the step (the cell it is entering
  until the border crossing, the cell it left after it, until the step end); bit 0x40 (ground
  classes) is seen by walkers and ghosts, bit 0x80 (class 3) only by flyers (`engine/sim/movement.py
  live_cells`). The unit's own footprint is released before planning (`FUN_0054d76e` calls `FUN_0055be86`
  mode 2). A unit with hp <= 0 keeps its stamps until removal (CONFIRMED, 7.4 "Cell record"). The first-come
  occupant of a cell is modelled by `Unit.cell_seq` (7.4), not the stamp slot quirks.
- `MoveTo(unit_id, x, y)` is the engine-level move order (order 1); the click mapping is H3. It follows steps
  1-6 above with the unit's `Mover` carrying `dest (+0x74)`, `tail (+0x76)`, `consumed (+9)`, `since_hop (+0x78)`,
  `arrived (+0x90)`, `failed (+0x98)`, `static_path`; `Unit.path` is the dynamic list. H3 replaced the H2 rule
  "an arrived or failed unit returns to order 0": a failure ends the order at once (order 0xc), an arrival waits
  for the group pass (§8.3). `MoveTo` is now a debug command executed by `orders.py` (a one-unit group move
  without clamp).
- Size = `token_size` (vtable `+0x1c` = `0x542360` reads `+0x49`, CONFIRMED); movement class = `movement_type`
  (vtable `+0x20` = `0x542380` reads `+0x4a`, CONFIRMED). The hop goal "`DynamicByStaticLookup` places behind the
  head" is the 4th element (index 3): the loop fetches `lookup + 1` elements with `FUN_0055f1f0`, taken as
  MFC-style get-and-advance (INFERRED).
- A finished order keeps `dest`/`static_path`/`goal`, as the exe keeps `+0x74` (H3 changed the H2 DECISION that
  cleared them): a repeated order to the same cell reuses the remaining static plan (§8.4).
- `FUN_0056fc69` is modelled for human-player size-1 units (`blocker_verdict`, `_begin_wait`, `_tick_wait`;
  `Mover.waiting` = brain mode 10, `Mover.parked` = mode 0 under a move order, dumped only when set); every
  other unit re-plans around the blocker. See 7.4.
- Performance and search statistics: see 7.5.

### 7.4 Read but not implemented (needs orders/AI of phase I)

- **Follow-target fallback** (`FUN_00557f08(follower, target)`, all CONFIRMED, asm 0x557f08-0x558571, table bytes read from the
  exe; implemented as `follow_fallback` in `engine/sim/pathfinding.py`, not wired to any order yet). Reached from the planner
  `FUN_0054d76e` at `0x54e30f` only when the **dynamic** plan (mode 0) leaves its goal cell unlabelled **and** the plan carries a
  target object (`param_7 != 0`, passed by `FUN_00555dc2(unit, target)` -> `FUN_0054d72d(.., 0, target)`); without a target object
  the ring scan `FUN_005585f4(unit, 0, goal, 8)` runs. The goal is the hop goal (a static waypoint), but the fallback ring is laid
  round the *target unit*, not round the goal. The returned cell (`y << 8 | x`, 0 = none) goes to `FUN_0054e886` like the ring cell.
  The "float trig helpers" are integer: `FUN_0050d884/8c0(unit)` = `((cell << 8) + sub) + (size - 1) * 128` (16-bit; cell = mover
  `+0/+1`, sub = mover `+4/+5`, 0x80 = centre, size = vtable `+0x1c`), the unit's footprint centre in 1/256 cells; only the
  slope below is float.
  1. `FUN_00557cf1(target, follower)`: `d = centre(follower) - centre(target)`, `a = |dx|, b = |dy|` (16-bit, strict compares, `dx == 0`
     or `dy == 0` count as non-positive): `dx > 0, dy > 0`: `a > b ? (a > 2b ? 4 : 5) : (b > 2a ? 7 : 6)`; `dx > 0, dy <= 0`:
     `a > b ? (a > 2b ? 3 : 2) : (b > 2a ? 0 : 1)`; `dx <= 0, dy > 0`: `a > b ? (a > 2b ? 11 : 10) : (b > 2a ? 8 : 9)`; `dx <= 0, dy <= 0`:
     `a > b ? (a > 2b ? 12 : 13) : (b > 2a ? 15 : 14)`. Codes run clockwise from north (0), 4 east, 8 south, 12 west.
  2. `side = (((code + 2) & 12) >> 2) + 4`: 4 north (codes 14..1), 5 east (2..5), 6 south (6..9), 7 west (10..13).
  3. Slope (float32 stores, x87 core): `fx = centre_x(T) - centre_x(F)`, `fy = centre_y(T) - centre_y(F)`. East/west: `fx += 1.0` if
     `fx == 0`, `s = f32(fy / fx)`, `b = trunc(Ty - Tx * s)` (line `y = s x + b`); north/south: `s = f32(fx / fy)` (no zero guard),
     `b = trunc(Tx - Ty * s)` (line `x = s y + b`), `trunc` = `FUN_00582c0c` (FISTP, round toward zero). Every product and sum
     is exact in 53 and in 64 bits of mantissa, so the precision control does not matter; only the unguarded `fy == 0` case
     (follower on the target's centre: code 14, `0/0`) depends on the FPU exception mask (INFERRED: masked, integer indefinite,
     low dword 0).
  4. Box in cells, from the target's cell `(Tx, Ty)`, sizes `Fs`, `Ts`: `x0 = Tx - Fs`, `y0 = Ty - Fs`, `x1 = Tx + Ts`, `y1 = Ty + Ts`
     (the ring of top-left cells where the follower's footprint touches the target's). Attempt `k = 1..8`, while no cell is labelled;
     after each attempt `x0--, y0--, x1++, y1++`.
  5. Entry cell on the edge of `side` (4: row `y0`, 5: column `x1`, 6: row `y1`, 7: column `x0`): the line is evaluated at the edge's
     cell centre `(edge << 8) + 0x80` (`ftol`, then arithmetic `>> 8`). It can lie outside the edge's span (shallow lines, off-centre
     sub-offsets); it is not clamped.
  6. Two walkers start on the entry cell and make `n = (x1 - x0) + (y1 - y0) + 1` steps (cap: stops after step 100). Direction
     table at pathfinder `+0x54156` (constructor `0x5543e7`): `(dx, dy)` = E, S, W, N repeated three times (12 entries). Per step:
     read the label of walker 1 then walker 2 (`FUN_0055f970` = `+0x30000 + 2 * (y << 8 | x)`, low bytes of the 16-bit
     coordinates), keep it if **strictly** below the best (so the lowest label wins, ties go to the earlier read: walker 1 before
     walker 2, earlier step first; label 0 = the follower's own cell wins over everything). Then the corner test and the move:
     walker 1 (index `p`, starts at `side`): `p % 4` = 0: `x == x1`, 1: `y == y1`, 2: `x == x0`, 3: `y == y0` -> `p += 1`; move by
     `dir[p]` (walks the ring clockwise). Walker 2 (`q`, starts at `side`): `q % 4` = 0: `x == x0`, 1: `y == y0`, 2: `x == x1`, 3:
     `y == y1` -> `q -= 1`; move by `-dir[q]` (anticlockwise). Coordinates wrap at 16 bits and are compared unmasked to the box
     (a box edge below 0 never matches).
  7. Result: the best cell `(y << 8) + x`, or 0 after 8 attempts without any labelled cell. Consequence of 5 and 6: the two walkers
     together cover the ring only when the entry cell is on it; otherwise some ring cells (e.g. the far side) are never read.
  `MoveTo` has no unit target, so the engine's orders use the cell fallback only until the follow command exists
  (`plan_dynamic(.., follow=(follower, target))` is the hook).
- **Follow driver** (`FUN_0055574d(unit, target unit, range)`, CONFIRMED asm 0x55574d-0x555b35; callers: `FUN_0056ea52` from brain
  mode 4 (`FUN_0056dca2` case 3), mode 5 (`56eab5`, attack) and mode 8 (`56ebc0`, cast at object), always with
  `range = brain+0x14` (byte; `FUN_0056ac5b`, §9) and the pathfinder `world+0xa50`). Same two-layer driver as 7.2:
  `tcell = cell of the target` (`FUN_0054ff9e`); `d = FUN_00556dcd(unit, target)` = `max over axes of max(|centre delta| - (Fs + Ts) * 128,
  0)`, `>> 8` truncating, `+ 1` (touching = 1; implemented `follow_distance`). Not at a cell centre: `FUN_00555b38` (continue the
  step). At a centre: `d <= range` (bytes): turn towards the target (`FUN_00556d78` = `FUN_00556454(unit, FUN_005568e4(unit,
  target))`), no plan, no step. Otherwise `mover+0x78 += 1`; if `mover+0x7c` (followed object) != target: `mover+9 = 0xFF`, static
  list cleared, `mover+0x8a = 0xFF`, `mover+0x76 = mover+0x8c = tcell`. If `mover+9 > len(static) / 3 + 1`: static re-plan: when
  `mover+0x8a <= StaticIsntNeeded` the list is cleared and `FUN_00542300` is called with `mover+0x76`, else `FUN_0054d72d(unit, tcell, 1,
  target)` (**static mode, with the target object**: the static fallback is the ordinary `FUN_005585f4` ring, the object matters only
  in mode 0); then `mover+0x8a = len`, `mover+0x74 = tcell`; an empty result sets `mover+0x98 = 1` (no way), else `mover+0x76` = the
  static head, `mover+0x8c = tcell`; `mover+0x7c = target`, `mover+9 = 0`, and with `mover+0x8a > StaticIsntNeeded` the dynamic
  list is cleared. If the unit's cell == `mover+0x76` and `mover+0x8c == tcell`: `mover+9 += 1`, `mover+0x7c = 0`, return (arrived at
  its hop goal; no step). Else when the dynamic list is empty or `mover+0x78 > DynamicRefreshRate`, and facing == target facing:
  `FUN_00555dc2(unit, target)` (hop plan with the follow fallback above), `mover+0x94 = tcell`, `mover+0x96 = own cell`, `mover+9 += 1`,
  `mover+0x78 = 0`; finally `FUN_00555c7e` (the step). After the call `FUN_0056ea52` sets `unit+0x54 = 1`, and when the unit is mid-step
  (`FUN_00551383(mover) == 0`) brain order `+9 := 3` (step), `+0x15 := 0`.
- **Blocker handling** (`FUN_0056fc69(this, unit A, next cell)`, CONFIRMED read of the whole routine and its
  caller `0x55567d`; there is **no swap**: nothing ever tells the blocker to move). Reached when the static
  head is adjacent and `FUN_0055c5a0` (1 = free, loop over the `size x size` footprint of the live layer with the
  mover mask `mover+5`) says it is not. Verdict in AL (0 = re-plan round the blocker, 1 and 2 are treated alike):
  1. A not size 1 (vtable `+0x1c`) or its owner's `+0x2c != 0` (computer player): 0. `mover+0x80 == cell`
     (the cell A itself stamps, never true for an adjacent cell at a centre): 0.
  2. `B` = the **occupant** of the cell record (`FUN_00551edb`: needs bit `0x20` in `+0x10000`, record lookup
     `FUN_0055f3e0`, returns rec `+4`, the occupant slot, see "Cell record" below; friend or foe, no relation test,
     dead units too). No occupant: `FUN_0054ec6a(cell, 1)` lists the occupants (`FUN_00551edb`) of the 3x3 around
     the cell; one whose `mover+0x70` (cell its step began on) is `cell` and that is off-centre (`FUN_00551383`:
     sub-offset bytes both 0x80 = at centre) -> 2, else 0. CONFIRMED (asm `0x56fd02`-`0x56fd9d`, `0x54ec6a`).
  3. B with HP (`+0x94`) < 1: 0. B off-centre (mid-step): 0 if A's `mover+6` (last cell it entered) is `cell`,
     else 1. B at a centre: brain mode (`+0x1c4 -> +8`) 1 (go to cell) or 4 (approach object): 0 if A's own
     destination (`brain+0xa`) is `cell`, else 2; any other mode (idle 0, 10 turning, attacking...): 0.
     **Mode 4 CONFIRMED** (`0x56fdca`-`0x56fe04`): modes 1 and 4 share one branch and the compare is always
     against **A's** `brain+0xa`, never B's target. Mode 4 is dispatched by `FUN_0056dca2` case 3 -> `FUN_0056ea52`
     (follow driver `FUN_0055574d`, then `unit+0x54 := 1`); only modes 1, 9 (`FUN_0056ec3f`, target `+0x3c`),
     12 (`FUN_0056eb2d`) and 15 (`FUN_0056ecbc`) reach `FUN_00555411` through the wrapper `0x56e4b0`, so A is never
     in mode 4 and a mode-4 B is judged exactly like a mode-1 B. The model has no mode 4 (needs attack orders;
     `_mode_move` stands for 1 and 4).
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
     **Corrected in H3** ([research §4.4](click-to-move-research.md)): a move group is driven by `FUN_00573198`
     at `tick & 15 == 6`, which restarts parked units every 16 ticks (§8.3). `FUN_00569321` is the
     group-order-0 executor, not a per-tick one.
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
    mover mask; meaning: see "Bit 0x10" above); `FUN_00558aab` adds a fixed 4 x 3 block at (0x3e..0x41, 0x18..0x1a)
    (static += 5, live |= 5), a leftover test stamp.
- **Cell record, occupant slot, first come, death** (CONFIRMED, asm read; ECX from the callers):
  - The 60-byte record has **two pairs of unit slots**. (1) **Occupant** rec`+4` (ground classes 1, 2) / rec`+8`
    (class 3), written by `FUN_005503af(unit, x, y)` (`0x5503af`), cleared by `FUN_0055073f` (`0x55073f`). Loops:
    `FUN_0055020a(unit)` places the `size x size` footprint at the unit's **own current cell** (row by row, x inner)
    and finishes with `FUN_0055be86(unit, own cell, 1)`; `FUN_00550697(unit)` lifts it. (2) **Stamp slots** rec`+0x2c` /
    `+0x30` (`FUN_0055c2ce` / `FUN_0055c1fe`, above) that feed the live layer bits 0x40 / 0x80.
  - **First come, first served, per slot**: `FUN_005503af` creates the record if missing (`FUN_005508a0`, copies cost
    and static bytes, sets `0x20`), and if the slot is non-zero (any unit, also the caller itself) it neither
    writes nor rebuilds and returns 0 (`FUN_00556447` is an empty function), so `FUN_0055020a` stops at that
    cell (cells before it in the footprint stay placed). `FUN_0055c2ce` does the same for the stamp slots: a
    non-empty slot held by another unit means no stamp, no rebuild (the unit's own re-stamp is fine). The
    record keeps the unit that arrived first; list order does not enter.
  - **Release quirks**: `FUN_0055073f` zeroes the occupant slot **whatever unit holds it** (no owner test) and
    returns 0 for an empty slot, which stops `FUN_00550697`; `FUN_0055c1fe` clears a stamp slot only if this unit
    holds it. The loser of a first-come race therefore never owns a record, and when the winner lifts, the
    cell is free in the record although the loser stands on it, until the loser stamps again (its next
    `FUN_0055be86` call). `FUN_00551edb` reads rec`+4` only: a flyer (rec`+8`) is never the verdict's `B`, and a
    unit that merely stamps a cell (entering it, or leaving it after the border) is no occupant.
  - **When the occupant moves** (`FUN_00554fd2`, asm `0x555127`-`0x555186`): only when the position crosses a cell
    border mid-step: `FUN_0055be86(unit, 0, 2)` (release ring), `FUN_00550697` (lift at the old cell), move,
    `FUN_0055020a` (place at the new cell, mode 1 stamp), then `FUN_0055be86(unit, old cell, 0)`: the **old cell is
    stamped again** next to the new current cell and held until the step end (mode 2 + mode 1, `FUN_00555b38`).
    Before the border the occupant is still the start cell and the stamps are start + target cell. Other callers of
    place/lift: `FUN_0055a96c` (lift, set position `FUN_0054fbf7`, place: teleport), `FUN_0054d76e` (`0x54eee7`, lift
    around the planner), `0x554bf8`, creation `0x510089`.
  - **Engine**: occupant = among the ground-class units whose current footprint holds the cell, the one with the
    smallest `Unit.cell_seq` (set when the unit enters its cell, `World.add_unit`/`move_unit`); live layer =
    footprints at the cell, the step target and the step origin (`movement.live_cells`, `_blocker`, `_occupants`).
    The release quirks above are not modelled (the occupant table is derived, not stored).
  - **Death** (CONFIRMED): HP <= 0 (`FUN_0050f12c`) sets order 0, state 0, calls `FUN_00510745` (cancels a pending
    spell, `unit+0x68`) and runs the dying countdown; it releases **nothing**. The only release is the removal
    `FUN_00510a70` (state `0x10`, HP <= -10; for movementType > 1 HP := -1000 after the countdown): order/state :=
    0x10, then `FUN_00553891` = `FUN_0055be86(unit, 0, 2)` + `FUN_00550697`, then `FUN_005551d6`. Other callers:
    `0x5102a3`, `0x5162f6`, `FUN_0055a96c`. So a unit with HP <= 0 and state != 0x10 keeps its footprint stamps
    and its occupant slot, blocks the live layer, and is found as `B` (verdict 0 because HP < 1 -> others
    re-plan round it). Engine: `live_cells` no longer skips `hp <= 0`; `World.remove_unit` is the release.
  - **Bit 0x10** (CONFIRMED): written only by `FUN_00559c28(x, y)` (OR 0x10 into `+0x10000` and `+0x20000`), called
    from `FUN_005184bf(x, y, flag)` (`0x5184bf`, effect cell visitor; `flag != 0` after `FUN_005189b5`, the visual
    scorch/dirt mark) and `FUN_00518833` (`0x518833`, area loop over a radius `effect+0x4d` for the effect
    class `Effect_DirectDamage` when `effect+0x48 -> +0x5c != 0`, i.e. a damaging spell that scorches the ground).
    The clear `FUN_00559ce5` has no caller and no vtable reference (dead code); `FUN_00550a96` preserves the bit; it
    is in no mover mask (0x41, 0x44, 0x82), so it has **no effect on passability or path costs**: it is the
    server-side "ground marked by a spell" flag (the load-time dirt flag 13 of the file is another bit, map.md).
    A reader of the bit (e.g. for the client mark) was not found in the routines read.
    The same visitor, for effect type `0x11`, does something only when `FUN_00551edb(cell) == 0` (no occupant).
- **Unreachable feedback**: client message `0x92` (7.1): the event `NoWay`, §8.5.

### 7.5 Measured

`tools/bench_pathfinding.py` (pure Python, 200 random walkable pairs per map, human unit = unbounded search,
one core of this machine): worst case **148 ms on the largest map** (168 before the re-expansion skip below) (`110.alm`, 256 x 256, 40,465 labelled
cells), 44-50 ms on the 144 x 144 maps, typically 2-10 ms for a 50-150 cell route (the first version of
the planner measured 444 ms and 124-160 ms). The wave labels every cell within the route's cost radius, so cost
grows with the area, not the route length. Speed-up (results bit-identical, pinned by
`tests/test_pathfinding_differential.py` against the frozen original `tests/pathfinding_reference.py`): the
sequential label-correcting order is kept (a cell reads its label when expanded, re-appends define `searched`,
so a numpy level fill cannot reproduce it); blocked / footprint-not-free cells hold label 0 in the working
field so the strict `<` rejects them with no test (the field template is cached per blocked layer and size),
the field is a list, and the 8 neighbours are source-generated and unrolled per order. About 2.6-3x faster; the rest
is the irreducible per-expansion cost (~9 expansions per labelled cell). A later pass (results still bit-identical, same differential tests) skips an expansion of a cell whose label equals the label it was last expanded with (a `last` list per plan): it is a provable no-op (labels only fall, the step costs are fixed) and 29 % of the expansions were such repeats (duplicates in the frontier from cells lowered twice in one half step); and `PathResult.searched` (debug overlay only) is mapped to (x, y) lazily. A numpy level fill was re-checked and still cannot reproduce the order: with the terrain costs ~40 % of the frontier cells are lowered by an earlier cell of the same half step before their own expansion, and ~1.8 cells are lowered per expansion. Still one plan per order and per 17
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

## 8. Orders (H3)

Code: `engine/sim/commands.py` (`MoveUnits`, `Stop`, `SetFormation`), `engine/sim/orders.py`, `movement.py`
(`cancel`, `set_move`, `set_stand`, `stop_unit`, `walk_speed`), `engine.world` (`OrderGroup`, `NoWay`,
`Player.formation`). Facts and addresses: [click-to-move-research](click-to-move-research.md) ("R" below), all
CONFIRMED there unless marked here. Design: `docs/superpowers/specs/2026-10-18-click-to-move-design.md`.

### 8.1 Commands and intake (R 3.1, 3.2, 4.1)

- `MoveUnits(player_id, unit_ids, cell)` = exe cmd `0x16`, `Stop(player_id, unit_ids)` = cmd `0x18` (stand ground,
  the "stop" of the engine), `SetFormation(player_id, mode)` = cmd `0x46` sub-code 2 (client modes 0 off, 1 auto,
  2 on; `Player.formation`, default 1; other values are ignored). Frozen dataclasses, logged and replayable.
  `MoveTo` (H2) stays as a **debug** command, `FollowPath` as the H1 debug order.
- **Intake** (`orders.intake`): the player must exist, the id list is cut at 253 (the packet limit, `FUN_0050bbb8`)
  and must not be empty, and the **first** id must be a living unit of that player; any other id failing the same
  test is skipped silently. No passability, range, fog or occupancy test. DECISION: units with HP <= 0 count as
  invalid (the exe accepts them and the death tick resets the order, phase I; the observable result is the same).
- **A new group per command** (`FUN_0052b06f`): `World.groups` (id -> `OrderGroup`: `owner`, `members` in packet
  order, `order` 4 move / 3 stand, `target` = the unclamped (x, y) low bytes, `speed`), `Unit.order_group` (the
  exe's `unit+0x70`; **not** `Unit.group`, which is the section 8 item pack). A unit joins the new group at its
  tail (a repeated id moves to the tail) and leaves the old one, which keeps its order and remaining members. Empty
  groups of the owner are deleted when that owner's next command allocates a group. `World.dump()` appends
  `"groups"` only when any exists; a unit's dict gets `"cmd": [group, stopped, anchor]` when set; a player's entry
  gets `{"formation": n}` only when not 1 (old goldens stay valid).

### 8.2 Move and formation (R 3.2, 3.3, 4.1-4.3)

`orders.move_group`: cancel all members, decide the formation, cancel again, per member `set_move`, then group
order 4, target (x, y) as sent, speed.
- Mode (client -> server mapping 0 -> 0 off, 1 -> 2 auto, 2 -> 1 on, `SERVER_FORMATION`): **off** never; **on**
  always; **auto** only when every member's cell is within Chebyshev 2 of the centroid cell (`FORMATION_LIMIT`).
- **Centroid** (`FUN_0056f850`): the sums of the members' 16-bit positions (`cell * 256 + sub-cell`; mid-step
  offsets count) divided by the member count with truncating division, then `>> 8` per axis; not the mean of cells.
- Member target = `(x + (cellX - cx), y + (cellY - cy))`: a rigid translation of the shape, no leader, no free-cell
  search. **Per-member destination** (`FUN_0056d032`): `& 0xff` first (a negative result wraps to 255 and is pinned to
  the far edge: the quirk), then each axis clamped to `[8, W - 9]` / `[8, H - 9]`. Without a formation everybody
  gets the clicked cell (clamped); the pathfinder fallbacks spread them (§7.1).
- `set_move`: cancel, order 1, `mover.goal` = destination (`brain+0xa`), `arrived` and `failed` cleared, Brain mode 1
  (`waiting = parked = False`), anchor cleared. Plans, `dest`, the dynamic list, `turning` and a step in progress
  are untouched.
- **Group speed** (R 4.3): only when the formation is active, `speed` = min over the members of the low byte of the
  signed 16-bit speed stat (start 250; compared signed, stored as a byte); fixed for the group's life (Haste after
  the order changes nothing). `movement.walk_speed` (the exe's `FUN_0055915a`) = group speed if non-zero else the
  stat; `step_length` uses it, `turn_rate` does not.

### 8.3 Cancel, timeline, group pass, stop (R 3.4, 4.4, 5, 7)

- **Cancel** (`movement.cancel`): target facing := facing, state := 0, `stopped` (`brain+0x50`) := 0. A step in
  progress is never aborted; the live-layer reservation needs no release (the engine derives the layer from positions:
  a reservation exists exactly while `step_target` is set). Timeline for a move order arriving in tick T: idle at a
  centre -> static plan and first step in T; mid-step -> the old step finishes at its tick, **no new step on the snap
  tick** (state 0), the new static plan is made from the new cell in the next tick (forced when `dest != goal`; the
  same destination reuses the plan); turning -> the turn ends at the current facing, the step starts the same tick.
- **Stop** (`orders.stop_group`): every member cancelled, order `0xc` (stand/guard), anchor = own cell, Brain mode 0,
  group order 3. The step in progress finishes; plans are kept (`dest`, `static_path`). The guard scan of order 0xc
  (`FUN_0056a1fb`) needs enemies: nothing happens yet. The other stand commands (`G` 0x17, `L` 0x12, `R` 0x14) are
  phase I.
- **Failure** (`mover.failed`, set by the planners) is consumed at the end of the Brain tick: order 1 -> `fail_stop`
  (`FUN_0056dc24` = cancel + `FUN_0056dba1`: order `0xc`, anchor, mode 0, **`stopped` stays 0**, CONFIRMED asm; the older
  text and code used `FUN_0056dbc6`, which also sets `brain+0x50`) in the same tick; under any other order the event
  only sets Brain mode 0 (`0x56e320`; the target scan finds no enemy; mode `0xb` of computer players is phase I).
  `Unit.mode_go` is Brain mode 1 (the walking switch: set by `set_move` and the restart, cleared by `set_stand` and
  by that failure); the blocker verdict and the tick read it instead of the order.
- **Arrival leaves order 1** (unit at the goal, or at the end of its static plan): nothing happens in the unit's tick
  (state 0, action idle). The **group pass** (`orders.group_pass`, `world.tick & 15 == 6`, before the drain; per
  owner in id order, groups in creation order; only group order 4, `FUN_00573198`, is decoded) then, per member in
  list order: at its `goal`, at a centre and not `stopped` -> `stop_unit`, `arrived := False`; or `arrived` and
  `tail == cell` -> the same. A `stopped` member is skipped (the guard scan has no enemies yet). Otherwise
  **restart** (no test of the unit's order: a unit the failure turned into order `0xc` is restarted too, and walks again
  until it arrives): `mode_go`, `waiting = parked = False` (`FUN_0056c8af`), so a unit parked by the blocker wait (§7.4)
  moves again within 16 ticks if its blocker left; and if the footprint at the group target is not free in the live
  layer, the member's `goal` is that target and it is within Chebyshev 1 -> parked again at once (the guard scan with
  no target sets mode 0 for a human player's non-ranged unit, `FUN_0056afd9` -> `FUN_0056b025`, CONFIRMED in the
  asm; DECISION: applied to every unit, ranged `56bc7b` and the computer-player mode 0xb are phase I). So an arrived
  unit keeps order 1 for up to 16 ticks (the pass phase is CONFIRMED, 1.1). A hop plan that finds nothing in a
  blocked corridor leaves the unit spinning in order 1 (a re-plan per tick, `static_path` shrinking by one per plan
  until the final hop fails and the order ends, or forever when the unit's own cell is the best cell): see
  8.7 "Gridlock" (CONFIRMED code, INFERRED play).
- `Unit.state` follows the Brain tick: 1 while a step or turn runs, 0 at each step end and after cancel (H1/H2 kept
  1 for the whole walk).

### 8.4 DECISIONS and assumptions

- Command latency 0: a command logged for tick T is applied in the drain of T (CONFIRMED, 1.1: the loop-back is synchronous, no extra tick). Tests `test_command_is_applied_by_the_next_step_without_extra_latency`.
- `Unit.order_group` instead of `Unit.group`; `World.events` (a list of `NoWay`) is outside `dump()` and the hash.
- `MoveTo` (debug) bypasses intake validation, wrap and clamp (the H2 tests use arbitrary cells); it still makes a
  group of one so the pass ends its order.
- The pass runs the move handler for every owner including computer players (their branch is phase I).
- Not implemented: group handlers for orders 1, 3, 5, 0x13, the retreat/withdraw post step `FUN_00573713` (hook in §9), voices.
- A finished or stopped order keeps `goal`/`dest`/`static_path` (the exe keeps `+0x74`): a later order to the same cell
  reuses the old static plan (INFERRED reading of `FUN_00555411` step 2; stale-plan quirk).

### 8.5 "No way" (R 6.3)

`movement._maybe_no_way`, called by the static plan: when the target was unreachable (`reason` "fallback" or
"unreachable") and the end cell is more than 1 cell from the target (more than 2 when a structure holds the target
cell: `FUN_00559bc9` returns the cell record's structure `rec+0xc`, CONFIRMED asm `0x559bfd`; engine: the structure
registration `World._claim`) -> `World.events.append(NoWay(owner, tick))`. With no fallback cell at all the packed
end is 0, cell (0, 0) (CONFIRMED asm `0x54e1cc`). One event per static plan per unit, computer-player units
included. The UI shows main.txt line `0x81` for 3000 ms (stage B).

### 8.6 VERIFY IN GAME

The [research list](click-to-move-research.md#verify-in-game) applies; in addition: **13.** a unit stopped by the
blocked-target rule (group move onto an occupied cell) stays beside it with order 1 while a friend stands on the
target; **14.** `T` (stand ground) while a unit turns leaves it facing where it was.

### 8.7 Tests, end states, measured

**Tests** (`.venv/bin/pytest`; the whole suite takes about 5 minutes):
- `tests/test_engine_orders.py`, `test_engine_orders_ui.py` (synthetic, one test per rule above).
- `tests/test_engine_orders_maps.py` (game files): per map, a seeded sample of the units (default: at most 30; every unit
  with `ALLODS2_ALL_MAPS=1`) is ordered in groups of 1..5 (same owner and movement class; any player, the intake takes it)
  to seeded random cells of the leader's flood-filled region, formation Off, run until settled, then a second batch with
  formation On from the end state. Default run: maps 10, 32, 53 and 110 (the largest), about 40 s. **All 46 maps:**
  `ALLODS2_ALL_MAPS=1 .venv/bin/pytest tests/test_engine_orders_maps.py -s` (targets up to 80 cells away, 3000 ticks per
  batch; about 30 minutes in one process, all 46 pass, prints the end-state histogram per map). Checks: `World.check_consistency()` every 32
  ticks (unit/item index = entity cells, sub-cell range, step reservation = `step_target` adjacent to `step_from` and the
  unit on one end, groups and selections point at living entries), the live layer (`live_cells`) against an independent
  recomputation, no active unit without progress over 64 ticks, and every ordered unit in a documented end state:
  `goal`; `fallback` (stands on its static plan's end, the first ring; human size-1 units checked against an independent
  flood: no flooded cell nearer the target); `limit` (no static plan: a computer player's search is cut at `dist +
  min(5, dist/4)` levels, a sized unit's footprint may not fit; the unit stays on its cell); `blocked` / `boxed in` (the
  failure rule: the final hop plan came out empty because the plan's end cell is occupied / every route is, checked at the
  failure tick); `parked` (blocked-target rule or a blocker wait with a unit adjacent); `gridlock` (below); `queueing`
  (a crowd still moving at the cap); a unit the failure stopped (order `0xc`, `stopped` 0) counts as mode 1 again while the pass has restarted it.
- `tests/test_engine_orders_determinism.py`: a scripted session (selects, moves, mid-walk re-orders, Ctrl+F twice, T,
  right-click deselect) fed through `OrderInput` is recorded at 30 fps; replays driven like `window.run` (frame times
  against `tick_period_ms`, one `step(queue.drain())` per period, logged commands queued before the step of their tick)
  at 30, 60 and 144 fps, and `replay()` in one batch, give the same tick count and `dump_hash`; a UI-driven session at 60 fps
  replays to its own hash. Synthetic world and map 53 (player 4's walkers).
- `tests/test_engine_orders_golden.py` + `tests/orders_scenarios.py`: five synthetic scenarios against
  `tests/golden.json["orders"]` (hash, tick the walk ended, final cells, "No way" count): single walk with a mid-walk
  re-order; a square of four passing an idle blocker with the formation Off and On; the same square through a one-cell wall gap
  (`gap_jam`); an unreachable target inside a walled pocket (fallback ring 9, one `NoWay`).

**Gridlock (the stage A "spin"), CONFIRMED code, INFERRED play.** A unit whose hop plan comes out empty and is not on its
final hop keeps order 1, plans again every tick (dynamic list empty), and `FUN_00555dc2` pops the static head each time the
head is within 3 cells (**CONFIRMED** by REA: the pop `FUN_0055f110` runs whenever the static list is non-empty and
`d <= DynamicByStaticLookup`, whatever the plan returned; `mover+0x98 := 1` only for an empty plan toward the tail). So a
blocked unit eats its static list in about `len - 5` ticks, then the final hop plan fails and the order ends (`blocked` in the
tests); a unit whose own cell is the nearest labelled cell to the hop goal (a column of units in a one-wide road, or boxed in by
8 neighbours) plans empty again and again: the dynamic fallback scan sees the start cell (label 0) in the first ring that
has a labelled cell, so the result is "walk to the own cell" = nothing. The unit is not parked (mode 1) and not waiting
(the wait is human size-1 only and needs a walking or idle blocker, §7.4), so nothing but the blocker moving, a new order, or
the failure above resolves it (the pass restarts the failed unit 16 ticks later, so it tries again as soon as a way exists); in a mutual jam of computer-player units (map 110, a column through one gap, order 4)
several units stand like this for thousands of ticks. Reproduced as documented behaviour, not fixed.
Cost note: such a unit makes a hop plan per tick.

**Measured** (`tools/bench_orders.py`, AMD EPYC-Rome VM, one core, Python 3.13, pygame-ce 2.5.8, SDL dummy driver, interface on,
20 units of player 2 on `110.alm` (256 x 256), formation Auto, a walk of about 60 cells, 600 ticks = 37 s of game time):
- **Per tick (simulation only):** mean 6.0 ms, p95 13.8 ms, max 52 ms (static re-plans of several units in the same tick;
  hop plans mean 2.4 ms, max 5.6 ms; static plans mean 17 ms, max 41 ms). Tick 0, the order itself, plans all 20 units:
  **463 ms** in one tick (about 23 ms per unit, the worst-case territory of 7.5); **after the planner pass of 7.5: 352 ms** (14.6 ms
  per static plan, same machine and run; the planner micro-benchmark of the 20 plans alone: 395 -> 287 ms, best of 7).
- **Per frame with rendering** (`window.run`, the clock replaced by one that feeds the simulated frame time): 30 fps
  equivalent: mean 21.4 ms, p95 31.4, max 68 (3 % of frames over the 33 ms budget); 60 fps equivalent: mean 19.2, p95 27.6, max
  62 (70 % over the 16.7 ms budget). Frames that step the simulation cost about 24 ms, the others 17.5 ms (rendering). The first
  second (surface and sprite caches filling) costs mean 37-58 ms, max 540-560 ms.
- **Steady?** After the warm-up yes: no growth over 20 s, the frame time is dominated by drawing (17 ms), the orders add
  about 6 ms to a stepping frame; the tail (p95 28-31 ms) comes from ticks with several static re-plans. **One real spike: the tick
  that applies the order of a 20-unit group on the biggest map freezes the window for about a third of a second (was half a second)** (20 static plans
  of 7.5). The plans cannot be moved or shared without changing the result (they read the live layer at that tick, each
  starts from its own cell, and spreading them over ticks shifts the first step of the later units, which breaks 1:1), so no
  fix was applied. Options when it matters: plan in a worker thread against a copy of the layer and apply the result at the
  tick the exe would have (deterministic, but adds a frame of latency before the sim may continue), or speed up the planner
  further (7.5). At 60 fps the renderer alone exceeds the frame budget on this machine; that is not an orders cost.

## 9. Handoff to combat (phase I)

**I3 (monster AI) is done: [ai](ai.md)** - the group order `0x12` handler (`FUN_005728fa`), the guard / auto scans, the hit reaction and the flee step at the post of every pass are implemented there; the "computer players' branch of the pass" below is that handler.

**I1 (melee attack) is done: [combat](combat.md)** implements brain modes 5 and the follow driver (`movement.follow_drive`), order 3 / command `0x19`, the group
pass executor for group order 0, the swing (state 3) and the hit. What stays open below: modes 4, 6, 8 and the other group handlers, guard / swarm /
patrol / follow orders, the retreat post step, spells and the AI. The text below is the pre-I1 handoff, kept for the facts.

What phase I builds on, and what is still open. Orders now: `0` none, `1` move, `0xc` stand/guard; groups 3 (stand) and 4
(move); brain modes 0 (idle, parked), 1 (go to cell), 10 (turn to a blocker).

**Moving into attack range, brain modes 4, 5, 6** (CONFIRMED rows in [unit-struct §8.2](unit-struct.md), not implemented):
mode 4 (`56ea52`) approaches `brain+0x18` within `brain+0x14` with the follow driver `FUN_0055574d`, state 1; mode 5 (`56eab5`,
order 3 attack) swings (mode 2) when `FUN_0055532d` says in range (facing == direction to the target and distance <= range)
else approaches `brain+0xc`; mode 6 (`56eff3`) is mode 5 for AI/ranged units: a ranged unit (`53a5a0`) with range < 2 and owner
flag `+0x2c == 0` gives up (mode 0), else swings in range or steps towards the target (`56f0bb`). The range is `brain+0x14`,
written by every order issuer through `FUN_0056ac5b` (spell range when the selected special `brain+0x78` is usable, else the
creature byte `+0x12c`; structures 1..3 by footprint). Blockers of the mover see modes 1 and 4 as walking
(`blocker_verdict` here models mode 1 only).

**Following a moving target** (`FUN_0055574d`, fallback `FUN_00557f08`, CONFIRMED, full algorithm in 7.4; pure functions
`follow_distance`, `follow_compass`, `follow_fallback` and `plan_dynamic(.., follow=)` in `engine/sim/pathfinding.py`, not wired):
the driver is the 7.2 driver with the plan target a unit; range test `follow_distance <= brain+0x14` turns to the target instead of
planning; static plans use the ordinary ring fallback, only the hop plan (`FUN_00555dc2(unit, target)`) uses the box-perimeter
fallback round the target unit. Phase I still has to build the callers (brain modes 4/5/6/8 and the `0x19`/`0x1b` orders).

**Attack and cast states** (H1 §3, [unit-struct §10](unit-struct.md)): state 3 (melee, `+0x58` phases 0 start, 5 wind-up, 7
recovery, [animation §3.4](../formats/animation.md)), 0xd cast at object, 0xe cast at cell (`+0x15` counter, cast request at 3,
ends when `+0x136 != 0`), 2 pick up, 0xf use, 0x10 dead, 0x1b AI wait; brain orders 1 swing / 2 cast / 3 step / 4 wait / 0xff hold.
The tick pipeline and attack timer details are in [unit-struct §6](unit-struct.md). Death resets order and state (the intake's
HP > 0 test stands in for it, 8.1).

**Orders and group handlers still to build:** `0x17` guard (G), `0x12` (L), `0x14` (R) next to the `0x18` stand ground done here;
`0x19` attack (`+0xe`, order 3), `0x1a` swarm (formation + group order 5, handler `572e1e`), `0x1b` follow (group `570c84`, orders 8/0x11),
`0x1d` patrol (0xa). **All group handlers are decoded: [ai §14](ai.md#14-the-other-group-orders)** (1 `57275f`, 2 `572d57`, 3 `57309d`, 5 `572e1e`, `0x11`
`572ec4`, `0x13` `57311c`, `0xff` `573159`, `0x12` `5728fa`). Implemented with the AI on: order 3 (the stand-ground pass attacks hostiles it sees
that are adjacent, or in range for ranged units: a pool + score pass, not the guard scan) and the guard scan of the stopped members of a move group (order 4);
with the AI off the human units still never react (no enemies exist in those sims). Orders 1, 2, 5, `0x11`, `0x13` wait for their commands.

**The retreat/withdraw post step `FUN_00573713`** ([research §4.5](click-to-move-research.md#45-the-post-step-fun_00573713-retreat-and-withdraw),
CONFIRMED, combat-only for now): after every group handler, every 16 ticks, each member with HP <= `brain+0x44` (10 cells) or <= `brain+0x40`
(2 cells) and a hostile (war relation bit, visible) in that Chebyshev radius gets Brain mode 1 with `brain+0xa` := a cell 3 beyond itself
away from the hostiles' mean position (`FUN_00558b92`), overriding a move group's destination. The engine has none of its inputs (no
hostility/visibility test, no thresholds, no retreat option): human units have thresholds 0 in the default configuration (data
HP > 0 never satisfies it) and the engine's AI units are never ordered, so no order it can give today is affected. Phase I adds
`Unit.wimpy/withdraw` (data.bin p34/p35 for monsters, `maxHP * x / 100` with x = 0/10/30 from a `SetRetreatMode` command for the
player's units), the enemy scan and the flee cell, called after `_pass_move` for every member of every group.
The guard scan of order 0xc (`FUN_0056a1fb`) is a no-op here; arrival and the blocked-target rule already call it.

**UI still stubbed:** hotkeys G, L, R, A/D/S act only on the cursor (pending modes 1/4/6 give no order), cursor rows
attack-on-unit, swarm, patrol, defend, pickup, town, cast issue nothing (`OrderInput.release`), the minimap's pending modes,
and the voice (acknowledgement and selection voice `FUN_0041da16`; no sound engine). The message-line "No way" is
filtered by recipient (`drain_no_way`, research 6.3 CONFIRMED routing).

**Consolidated VERIFY IN GAME** (each: predicted result, so a play session can tick them off):
1. Straight/diagonal walk times (150 and 220 ticks per 10 cells at speed 18), road 110 ticks (H1 §6 item 1).
2. Turn time `ceil(128/speed)` (8 ticks for a 180 degree turn at 18), 45 degree snap (H1 §6 item 2).
3. No pause between cells; hills +-50 % step length (H1 §6 items 3, 4); diagonal cells 1.47x a straight cell (item 6).
4. Two units swapping on a one-wide road: no swap, the first handled turns and stops, the follower halts behind a walking leader
   (H1 §6 item 5, §7.4); a parked unit resumes within 16 ticks when the blocker leaves (research item 8).
5. Corner squeeze between diagonal trees; equal-cost route tie order; shore cell of an unreachable lake target (the
   cheapest of the first ring, not the nearest); AI units give up beyond the level limit while the human's walk all the way;
   re-plan at the next centre; repeated order to the same cell; road preference (H2 §7.6 items 1-7).
6. Cursor and input: right button, attack cursor over ground/unit/structure, Ctrl/Alt rows, minimap order row (expect the
   exe's wrong row), formation Off/On/Auto with a slow member's group speed, edge wrap, arrival delay of up to 16 ticks,
   re-order mid-step, "No way" for 3 s, stop commands G/T/L/R, no click marker (research VERIFY items 1-12), failed units retrying every 16 ticks and the retreat mode `Ctrl+W` (research VERIFY items 13, 14).
7. Stage B: Ctrl+Alt hover (Alt first over a unit, Ctrl first over ground); `M` then click on a hostile walks to it; `T` mid-walk
   finishes the step; formation text lifetime about 2 s and its colour; left drag on the minimap streams orders; right click
   on the bar and info panel deselects; minimap order zone on maps >= 145 cells (design spec, Stage B items a-g).
8. §8.6: a unit stopped by the blocked-target rule stays beside its occupied target with order 1; `T` while turning leaves it
   facing where it was.
9. Gridlock (8.7): send a column of computer-owned units through a one-cell gap: the units that cannot plan give up after
   about `len - 5` ticks (human units wait first); a lone unit boxed in by friends keeps order 1.
10. Order spike (8.7): ordering 20+ units over 60 cells in one click is instantaneous in the exe (native planner).
11. Combat (I1): the eight items of [combat §11](combat.md#11-verify-in-game) (monster damage = template + weapon, hero hit/miss/damage counts over 20 blows, 0-15 tick start latency, flyer refusal, reach rule, Ctrl+L numbers, absorbed hits show no number, sure-hit monsters).

## 10. RNG

**Generator (CONFIRMED, REA):** the game uses the MSVC C runtime `rand`/`srand`, not a private generator. `FUN_00583290` =
`rand()`: `state = state * 0x343FD + 0x269EC3 (mod 2^32)`, result `(state >> 16) & 0x7FFF`; `FUN_00583280` = `srand(seed)`: `state = seed`.
The state is the CRT's per-thread word (`+0x14` of the block returned by `FUN_0058a930`, `_getptd`); a fresh block holds 1
(`FUN_0058a910`), so an unseeded stream starts 41, 18467, 6334, 26500, 19169, 15724 (tested). `FUN_0051fa25(n)` is the game's
`rand(n)`: `0` when `n == 0` (**no draw**), else `(rand() * (n + 1)) >> 15`, uniform on `0..n` inclusive. 93 call sites use `FUN_0051fa25`,
39 call `FUN_00583290` directly (the latter with `rand() > 0xcc`-style comparisons against the raw 15-bit value).

**Seeds (CONFIRMED call sites):** `srand(timeGetTime())` at `0x45ae54` (client object init, function `0x45ade7`) and in `FUN_0051f9f8`
(`0x51fa02`), which both server constructors call (`0x4e97d6`, `0x4eb75d`: a new game or a loaded one); `srand(time(0))` at `0x57af92`
(function `0x57af80`, called from the order manager's constructor `0x56811b`, object `0x66832c`). The last reseed wins, so a game's
stream starts from the **wall clock**. Single player runs client and server on one thread, so the client's draws (sound variants,
idle-animation timers such as `FUN_004cae28`, text effects) are interleaved with the server's between ticks.

**Consequence:** the original is not reproducible even with a known seed, and a recorded original session cannot be replayed against ours.
**Engine (DECISION):** `engine/rng.py` (re-exported as `engine/sim/rng.py`) implements exactly this generator (`Rng(seed)`: `srand`, `rand15`, `rand(n)` with the `n == 0`
rule), one instance owned by the `World` (`World.rng`), seeded per game (default 1 = an unseeded CRT; `engine run` picks the clock and prints
it; the session log keeps it). Every system in `sim/` draws from it in update order and nowhere else (no Python `random`; a test scans the
imports); the view and backend have their own generators. So **our sequence equals the original algorithm's for the same seed; it does not
equal a recorded original session** (seed from the clock + client draws). Draw order inside a hit: [combat §5.2](combat.md#52-take_hit-fun_00516f6f-confirmed-vtable-54-of-every-creature-class).
The state is part of `World.dump()` once it differs from its initial value (old goldens unchanged).

## Open questions

1. What a unit does at a centre with an empty dynamic list after a failed hop plan (`FUN_00555c7e` empty-list "turn step" path, `0x555c7e`) beyond the failure stop; and whether the stale-list case (turn > 32 ticks) is reachable with real data.bin turn rates.
2. Haste/Slow vs the group speed byte: the byte is fixed (§8.2); the effect system is phase I.
4. Group orders 1, 2, 5, 0x11, 0x13 and the G / L / swarm commands are built ([ai §14.1](ai.md#141-implementation-and-the-asm-details-it-rests-on-confirmed-unless-marked)); the Scenario instants that would set them are missing;
   the retreat post step `FUN_00573713` is decoded (§9 hook); its spell branches and the hidden-enemy detection `FUN_00556dcd` remain.
5. The stored occupant/stamp slots with their release quirks (7.4 "Cell record"): `FUN_0055073f` clears a slot of any unit, so a first-come loser loses its record when the winner leaves; the engine derives the occupant instead. Starting routine `FUN_0055be86` callers `0x558b7c`, `0x56a5df` (how often a standing unit re-stamps, which decides how long such a cell stays unowned).
6. The x87 control word at run time (precision / exception mask) for the slope in `FUN_00557f08`: only the follower-on-target-centre case (`0/0`) depends on it (7.4 step 3). Starting routine CRT start-up before `0x557f08`; DirectDraw init.
8. `FUN_005728fa` (group order 0x12 handler, reader of `brain+0x16`): the full per-tick behaviour of guarding computer-player groups and the home-cell restart (`FUN_0056c8af`, `brain+0x9c`).
9. `FUN_004f515d` on a client type-100 message (value 1, sent after every client command by `FUN_00504bb7`): confirm that the server ignores it (nothing in the order path depends on it).
10. `FUN_0051c391` / spell record `+9`, `+0xc`: confirm that they are spell range and mana cost (used by `FUN_0056ac5b`).
