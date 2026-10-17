# Simulation: tick, update order, unit states, movement

Phase H1. The game tick, what a server tick runs and in what order, the unit state machine, and the
rules by which a unit walks a given path (no path finding yet: H2). Code: `engine/sim/` (`clock.py`,
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
5. **Occupying the next cell.** Order two units to swap places on a one-cell-wide road: they should
   collide at about the middle of a step (needs H2 blocking; record the observation then).
6. **Diagonal vs straight cost**: diagonal cells take `ceil(256 / trunc(v·0.707))` ticks, 1.47× a
   straight cell at v = 18 although the cell distance is 1.41×.

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
