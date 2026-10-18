# H3: click to move, close-out of phase H (design)

Goal: the player orders the selected units to walk with the mouse; units walk as in the exe; phase H is verified and
documented. Rule from the user: **reproduce the exe 1:1, even where it is not optimal.** Facts and routine addresses:
[click-to-move-research](../../engine/click-to-move-research.md) (REA, GOG exe; "R§" below = its sections). Single player only.

## 1. Where the research changed the brief

| Brief | Exe (CONFIRMED, R§) | Spec decision |
|---|---|---|
| "Stop(player, ids)" | no Stop message; four stand commands `0x17 G`, `0x18 T`, `0x12 L`, `0x14 R` (R§5) | `Stop` = cmd `0x18` (T, stand ground: cancel + order `0xc`, anchor own cell). G, L, R are phase I |
| group move "formation or nearest free cell" | per-player Formation mode (Off / Auto / On); formation = rigid translation of the group shape around the truncated centroid; no leader, no free-cell search; Off = all aim at one cell and the pathfinder fallbacks spread them (R§4) | implement exactly; `SetFormation` command |
| click marker | none; feedback = cursor, unit voice, "No way" text (R§6) | no marker; "No way" text event; voice out of scope (no sound engine) |
| right click | deselect (or cancel the pending mode); right drag = camera scroll (R§1.5) | implement both |
| order replaces path | step is never aborted; replan from the next centre (R§3.4) | implement the timeline table |
| arrival | order 1 stays until the group pass (`tick & 15 == 6`), then order `0xc`; parked units restart there (R§4.4) | implement the group pass |

## 2. Units

1. **Commands** (`engine/sim/commands.py`, frozen dataclasses like `SelectUnits`; logged by `Simulation.log`, replayable):
   - `MoveUnits(player_id, unit_ids, cell)` = exe cmd `0x16`; `cell = (x, y)` in map cells (border included).
   - `Stop(player_id, unit_ids)` = cmd `0x18`.
   - `SetFormation(player_id, mode)`, client modes 0 Off, 1 Auto (default), 2 On; stored on `Player.formation`, mapped to the
     server mode (0, 2, 1) (R§4.1). Dumped only when not the default (old goldens stay valid).
2. **Order system** (`engine/sim/orders.py`, new, runs first in `Simulation.systems`): at the start of a step, when
   `world.tick & 15 == 6`, the **group pass** (R§4.4) runs *before* the command drain; then the drain applies commands in log
   order. Intake (R§3.1): command rejected unless it names >= 1 id and the **first** id is a living unit of the claimed player;
   later invalid ids are skipped; at most 253 ids. Every command creates a **new group** (`World.groups`, `Unit.group`; the unit
   leaves its old group, empty groups are deleted at the next command of that player). Move: formation test and centroid
   (R§3.2, §4.1), per member cancel (R§3.4) then `order := 1`, destination = `((x + off) & 0xff)` clamped to `[8, W-9]` /
   `[8, H-9]` per axis (R§3.3 incl. the wrap quirk), `mover.arrived = False`, Brain mode 1; group order 4, group target
   unclamped, group speed (min speed, only when the formation is active; feeds `unit_speed`). Stop: cancel + order `0xc` +
   mode 0 (R§5).
3. **Movement changes** (`engine/sim/movement.py`): `MoveTo` stays the executor and is called by the order system; the H2
   behaviour "arrived or failed returns to order 0" is replaced by the exe's: failure (`mover.failed`) -> cancel + order `0xc`
   at once; arrival waits for the group pass (order stays 1, `arrived` set). Cancel = R§3.4 (target facing := facing; release a
   reservation only at a centre; never abort a step; at the snap tick no new step starts, the plan starts next tick). The
   pass restarts parked units (R§4.4) and applies the blocked-group-target stop. Unit orders in the engine become the exe's
   numbers (0, 1, 0xc).
4. **"No way"** (R§6.3): the static planner reports "fallback end > 1 cell from the target (> 2 for a building cell)" ->
   `World.events` gets `NoWay(player_id, tick)`; events are not part of `dump()`/the hash; the UI shows "No way" (main.txt
   line `0x81`) for 3000 ms in the message line.
5. **UI** (`engine/ui/`): `OrderInput` beside `SelectionInput`.
   - Left release with a click (not a drag) and a non-empty selection of own non-structure units: dispatch on the cursor
     chosen at release (R§1.2): **move** -> `MoveUnits`; **attack over ground/structure** -> `MoveUnits`; attack over a unit,
     swarm, patrol, defend, pickup, town, cast -> no order yet (phases I/J/K), but the pending mode is still reset.
   - `choose_cursor` completed for the no-pending-mode table (R§1.3: move, attack, swarm, select, pickup, town cursor) and the
     pending-mode cursors; modifiers Ctrl / Alt read from the backend.
   - Pending mode (R§1.4): hotkeys `M` (2), `A` (1), `D` (4), `S` (6) arm it (cursor only for 1/4/6 until phase I); `T` -> `Stop`;
     `Ctrl+F` cycles the formation (-> `SetFormation`, message text lines `0x61`..`0x63`).
   - Right release without a right drag: cancel the pending mode if armed, else `SelectUnits(())`; right drag scrolls the camera
     `delta/8` cells per move (R§1.1).
   - Minimap left click with own units selected = `MoveUnits` (R§1.6). DECISION: the exe sends the wrong row (it re-reads the
     mouse over the right panel); the engine uses the minimap's own row until the in-game check; listed in VERIFY IN GAME.
   - Target cell of a normal click: `(mx >> 5) + camera.x`, `Projection.hover_cell` row (R§1.7). No fog / passability test.
   - No marker. The F4 paths overlay stays behind its debug toggle.
6. **Docs**: apply the corrections of R§10 to ui-layout, simulation, unit-struct, animation; link the research page from
   docs/engine/README.md; update architecture.md (commands, systems order); "Handoff to combat" in simulation.md (section 3 below).

## 3. Close-out

- **Integration** (`tests/test_engine_orders_maps.py`, game-file test, skipped without the install; marked slow with a small default subset): on every
  one of the 46 maps, every unit is ordered (in groups, formation off and on) to a seeded random reachable cell; after N ticks each
  unit is at its target, on the documented fallback cell (first ring around an unreachable target, simulation §7.1), or parked
  by a documented blocker rule; none is mid-step without progress (odometer or order change within a window); spatial index
  and live-layer stamps consistent (`World` consistency check added if none exists).
- **Determinism**: a recorded session (selection + orders + formation + stop) replays to the same `dump_hash` when the tick loop
  is driven the way the backend does at 30 and at 60 fps (accumulator, `clock.py`), and when replayed in one batch.
- **Performance** (`tools/bench_orders.py`): 20 units moving at once on the largest map: ms per tick, and ms per frame with
  rendering (SDL dummy); numbers recorded in simulation.md section 8.
- **Goldens**: 3 scripted scenarios in `tests/golden.json["orders"]` (single walk with a mid-walk re-order; group in formation
  Off vs On crossing a blocker; unreachable target with "No way"); regenerated by `tools/update_golden.py`. The H2 `paths`
  goldens change because of the arrival rule; regenerate them in the same commit and say why in the message.
- **Handoff to combat** (simulation.md section 9): moving into attack range and the follow-target planner (`FUN_00557f08`,
  `FUN_0055574d`, R§9), the attack/cast states of H1 step 2, orders `0x17`..`0x1d`, `0x19` attack / `0x1b` follow / swarm group
  handlers, hotkeys, cursor rows still stubbed, voice, and the remaining VERIFY IN GAME items (H1 section 6, H2 7.6, R list).

## 4. Assumptions and risks

- Server tick counter starts at 0 so that the engine's `world.tick` at step start equals the exe's counter before the increment
  (INFERRED); a different phase shifts only when arrival ends (<= 16 ticks).
- Loop-back latency of the command (R open question 1) is taken as zero: the command is applied on the next tick, as the brief says.
- Only the human player's units are ordered; AI orders (and the computer players' branch of the group pass) are phase I.
- Open: group handlers for orders 1, 3, 5, `0x13`, the retreat post pass `FUN_00573713`, voice unit selection (R§9).

## 5. Order of work

1. docs corrections + this spec + research (commit). 2. commands, order system, group pass, movement changes, tests.
3. UI (`OrderInput`, cursors, pending mode, right button, minimap, "No way"). 4. close-out tests, bench, goldens.
5. simulation.md handoff, CLAUDE.md ("H done", Next "I1: melee attack"), open-questions.md, commit.
