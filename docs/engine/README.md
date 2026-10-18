# Allods 2 engine

The recreated game, built on the core library (`allods2/`, `a2res/`).

| Document | Contents | Status |
|---|---|---|
| [architecture.md](architecture.md) | layers, import rules, coordinate systems, tick, main loop, terrain drawing, CLI | G1 skeleton done |
| [rendering.md](rendering.md) | draw list and backend: pass order, placement, shadows, light rows, smoothing, culling, debug overlays, timings, interface / cursor / picking / marker (§14) | G2b, G3b done |
| [ui-layout.md](ui-layout.md) | screen layout per mode, cursors, picking, selection, marker, info panel (REA facts) | G3b done |
| [simulation.md](simulation.md) | tick, update order inside a server tick, unit state machine, movement formulas (step length, turning, cell occupancy), pathfinding (§7), orders (§8), handoff (§9), RNG (§10), exe addresses, VERIFY IN GAME | H1, H2, H3 sim side, I1 RNG done |
| [click-to-move-research.md](click-to-move-research.md) | REA research for phase H3: mouse input to order message, server intake, groups, formation, group pass, stop commands, "No way", VERIFY IN GAME | CONFIRMED / INFERRED per fact |
| [combat.md](combat.md) | phase I1: the attack order (cmd `0x19`), approach (follow driver), swing timeline, hit resolution `FUN_00516f6f` as math with worked examples, stat building (monster = template + weapon, human recompute), client damage numbers, VERIFY IN GAME | I1 done, CONFIRMED / INFERRED per fact |
| [unit-struct.md](unit-struct.md) | runtime unit struct of the exe: classes, sizes, allocation sites, field table, per-tick behaviour, client mirror | CONFIRMED / INFERRED / UNKNOWN per field |

Design specs: [../superpowers/specs/](../superpowers/specs/). Format and
mechanics specs the engine follows: [../formats/](../formats/README.md),
[../mechanics/](../mechanics/README.md). Open questions:
[../open-questions.md](../open-questions.md).
