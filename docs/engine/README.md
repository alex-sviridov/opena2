# Allods 2 engine

The recreated game, built on the core library (`allods2/`, `a2res/`).

| Document | Contents | Status |
|---|---|---|
| [architecture.md](architecture.md) | layers, import rules, coordinate systems, tick, main loop, terrain drawing, CLI | G1 skeleton done |
| [rendering.md](rendering.md) | draw list and backend: pass order, placement, shadows, light rows, smoothing, culling, debug overlays, timings, interface / cursor / picking / marker (§14) | G2b, G3b done |
| [vision.md](vision.md) | fog of war: sight mask, tile bits, refresh, what is hidden per state, minimap fog, cheats, saves; VERIFY IN GAME | J2 |
| [ui-layout.md](ui-layout.md) | screen layout per mode, cursors, picking, selection, marker, info panel (REA facts) | G3b done |
| [simulation.md](simulation.md) | tick, update order inside a server tick, unit state machine, movement formulas (step length, turning, cell occupancy), pathfinding (§7), orders (§8), handoff (§9), RNG (§10), exe addresses, VERIFY IN GAME | H1, H2, H3 sim side, I1 RNG done |
| [click-to-move-research.md](click-to-move-research.md) | REA research for phase H3: mouse input to order message, server intake, groups, formation, group pass, stop commands, "No way", VERIFY IN GAME | CONFIRMED / INFERRED per fact |
| [combat.md](combat.md) | phase I1: the attack order (cmd `0x19`), approach (follow driver), swing timeline, hit resolution `FUN_00516f6f` as math with worked examples, stat building (monster = template + weapon, human recompute), client damage numbers, VERIFY IN GAME | I1 done, CONFIRMED / INFERRED per fact |
| [ai.md](ai.md) | phase I3: monster AI = squad group order `0x12` handler `FUN_005728fa` every 16 ticks, sight flood, pool, target score, hit reaction, flee post step, engine mapping, VERIFY IN GAME; §12 casters and special attacks (K1) | I3, K1 (AI casting) done, CONFIRMED / INFERRED per fact |
| [combat.md §14](combat.md#14-spell-casts-i4a) | phase I4a: the player's spell cast (command, order `0xd`, Brain mode 8, cast phases, carriers, damage), staff casts; REA facts in [spells §9c](../data/spells.md) | I4a done (sim); view/UI = I4b |
| [triggers.md](triggers.md) | map scripts (section 7): compilation `FUN_00562745`, the check / trigger / instant tables, pass timing (group pass, every 16 ticks), victory and defeat `FUN_004f856a`, engine `sim/triggers.py` | decoded, engine built (subset), CONFIRMED / INFERRED per fact |
| [effects.md](effects.md) | phase K2: spell effect objects (list `unit+0x20`, mask `+0x144`), apply / merge / tick / undo, the stat switch, point / area / field carriers, cell effect slots | CONFIRMED / INFERRED per fact |
| [items.md](items.md) | phase K5: picking up an item by click (cursor, command `0x21`, approach, the whole-pile take), what scripts see (checks 12 / 16 / 17, instants 11-13, 20, 28, 38), the seven quest-item maps | CONFIRMED / INFERRED |
| [unit-struct.md](unit-struct.md) | runtime unit struct of the exe: classes, sizes, allocation sites, field table, per-tick behaviour, client mirror | CONFIRMED / INFERRED / UNKNOWN per field |

Audio (K11): [audio.md](audio.md).

Design specs: [../superpowers/specs/](../superpowers/specs/). Format and
mechanics specs the engine follows: [../formats/](../formats/README.md),
[../mechanics/](../mechanics/README.md). Open questions:
[../open-questions.md](../open-questions.md).
