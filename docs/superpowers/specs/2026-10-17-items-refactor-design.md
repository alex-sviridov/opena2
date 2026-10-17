# Items refactor: smaller and clearer, same behaviour

Scope: the item system only: `allods2/formats/itemdefs.py`, `allods2/formats/itemgen.py`,
`tests/test_itemdefs.py`, `tests/test_itemgen.py`, `docs/data/items.md`, the Items paragraph of
`CLAUDE.md`. Specs: [items](../../data/items.md).

## Goal and constraints

Priority is size, then clarity and Python best practice. Hard constraints (user decision):

- Behaviour stays exe-exact: same results for the same install and the same RNG draws.
- Public API stays: module, class, function and constant names and signatures used by `assets.py`,
  `cli.py`, `tools/`, `engine/` and tests. Private helpers may change.
- `docs/data/items.md` keeps every section number and heading (other specs and
  `docs/open-questions.md` link to them).
- No new dependencies. Core stays pygame-free. `engine/world.py` `Item` (ground pile) is untouched.

## Safety net (first step)

A throwaway script (outside the repo or in gitignored `out/`, never committed, as it derives from game
data) writes `out/items-baseline.json` before any edit:

- `ItemTable.to_dict()`, `parse_packets()` output.
- `resolve()`, `display_name()`, `icon_path()`, `parse_equipment()` for every item code and equipment
  string of the install and the 46 campaign maps.
- `generate()` and `loot_item()` over a fixed grid of seeds, price windows and flag sets (GEN_ENCHANT,
  GEN_BYPASS, GEN_STOCK, GEN_STAFFS, weapons/shields/armour pools).

Every step is checked against it. Also required at the end: `pytest` green, `tools/validate_items.py`
passes, `tools/update_golden.py` leaves `tests/golden.json` unchanged.

## Changes

`itemdefs.py` (target ~450 lines, from 525)
- `dataclasses.asdict` for `to_dict` where the output is identical; keep hand-written where keys differ.
- One private loader helper replaces the three inline `as_fs` imports.
- Drop the unused `field` import and redundant helpers; name magic numbers (`0x33` marker, `<< 4` time
  shift, default quality/material indices).
- Split `parse_equipment` into small private steps; same behaviour.
- `ItemDef.__getattr__` stays (callers use `d.price`, `d.slot`).

`itemgen.py` (target ~420 lines, from 478)
- One x87 truncation helper (`_ftol`); `itemdefs.ftol` stays public.
- Inline single-use `_idiv` / `_log`; kind codes map directly to the item group; name the 0x32 / 0x19
  chances. `make_special` keeps its `rng` parameter (API), documented as unused.
- Draw order and rounding unchanged.

Tests (target ~600 lines, from 818)
- Shared fixtures in one place; repeated cases via `pytest.mark.parametrize`. Every spec rule keeps at
  least one test; the case count does not drop.

Docs
- `docs/data/items.md`: state each fact once, cross-link instead of repeating; keep all headings, VERIFY
  IN GAME and Open questions. `CLAUDE.md` Items paragraph shrinks to ~3 lines pointing at the spec.
  `docs/open-questions.md` stays consistent (no question added or lost).

## Assumptions

- Line targets are estimates; a change that risks exe-exactness is skipped, not forced.
- Merging `Item` / `GenItem` is out of scope (public types); a possible later step.

## Open questions

None.
