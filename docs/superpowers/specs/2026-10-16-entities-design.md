# Map entities (players, units, items) and the runtime unit struct

## Goal
Decode everything alive or pickable on a `.alm` map plus the player setup, and map the exe's
runtime unit struct, as the base for engine units (G3a).

## Scope
- In: sections 5 (players), 6 (units, 48 B), 7 and 8 (expected items/sacks; confirmed in
  `FUN_00534ad4` before documenting), unit inventories, type id -> AnimationSet, player ->
  team colour (C4 `human.pal`), loader defaults vs overrides, facing -> D2 direction numbering,
  runtime unit struct (size, allocation site, per-field offset/type/meaning).
- Out: triggers (sections 9-12; only references from unit records are noted), item
  definitions (phase F), multiplayer.

## Assumptions
- Header counts `player_count`, `n_sec6`, `n_sec7`, `n_sec8` size sections 5-8.
- No new dependencies. No game data enters the repo.

## Design
1. RE (REA, GOG allods2.exe): `FUN_00534ad4` cases 5-8, the unit/item creation calls, then
   the loader's writes into the runtime struct and the action/animation/path code that reads
   it. Every fact CONFIRMED or INFERRED; unknown fields stay UNKNOWN.
2. Decoder: `allods2/formats/entities.py` (frozen dataclasses `Player`, `UnitRecord`,
   `ItemRecord`, same pattern as `objects.py`); lazy `Map.players/.units/.items`.
3. Render: `anim/scene.py` and `map render --layers all` (+ `units`, `items`): idle frame,
   facing, team colour, item markers.
4. Tests `tests/test_entities.py`: synthetic layout tests; install-wide: every record parses,
   type ids resolve (or documented exclusions), owners reference existing players, counts
   match section sizes.
5. Docs: map.md part 5 "Players, units, items", `docs/engine/unit-struct.md`, "Handoff to
   game data" (id tables for phase F), open-questions, CLAUDE.md (Next: G3a).

## Open questions
Recorded in map.md and docs/open-questions.md as they arise.
