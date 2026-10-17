# Allods 2 engine

The recreated game, built on the core library (`allods2/`, `a2res/`).

| Document | Contents | Status |
|---|---|---|
| [architecture.md](architecture.md) | layers, import rules, coordinate systems, tick, main loop, terrain drawing, CLI | G1 skeleton done |
| [rendering.md](rendering.md) | draw list and backend: pass order, placement, shadows, light rows, smoothing, culling, debug overlays, timings, interface / cursor / picking / marker (§14) | G2b, G3b done |
| [ui-layout.md](ui-layout.md) | screen layout per mode, cursors, picking, selection, marker, info panel (REA facts) | G3b done |
| [unit-struct.md](unit-struct.md) | runtime unit struct of the exe: classes, sizes, allocation sites, field table, per-tick behaviour, client mirror | CONFIRMED / INFERRED / UNKNOWN per field |

Design specs: [../superpowers/specs/](../superpowers/specs/). Format and
mechanics specs the engine follows: [../formats/](../formats/README.md),
[../mechanics/](../mechanics/README.md). Open questions:
[../open-questions.md](../open-questions.md).
