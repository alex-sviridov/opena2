# Open questions

Index of everything not yet known; each spec's "Open questions" section is
the source of truth (rules in CLAUDE.md: add a line when raised, delete it
from both places when answered).

## Animation

- Town scenes: draw code and timing are resolved ([animation §4.11](formats/animation.md)).
  Left: the hover-region numbers of the fighter/mage/shopie sprites and
  the druid `man`/`woman` variant choice.
  [animation](formats/animation.md#open-questions)
- World-map Cross: where `+0x134` is reset to 0 on a new click.
  [animation](formats/animation.md#open-questions)

## data.bin

- Human and structure fields in code (`FUN_004a65b0`, `FUN_004a65d0`
  users; column names known). [databin](formats/databin.md#open-questions)

- Unit stat table: damage kinds 1/2 → elements, protection/resistance scaling, negative damage spread
  (`0x516f6f`); hero carry-over. [units](data/units.md#open-questions)

## Progression

- Hero state between campaign maps (saves, `.a2c`). Start: `FUN_00514920`. [progression](data/progression.md#open-questions)

## Items

- None open. Related and not started: `.a2c` characters and saves, the `Scenario.dll` state machine beyond the shop table.
  [items](data/items.md#open-questions)

## Spells

- Client cast command path (range / mana / known-spell checks before messages `0x1e`/`0x1f`, `0x25`/`0x26`). Start `FUN_005702be`.
  [spells](data/spells.md#11-open-questions)
- Minion brain modes (`brain+0x20` 1 = Summon, 3 = Control Spirit). Start `FUN_005709d9`, `FUN_00570b8b`.
  [spells](data/spells.md#11-open-questions)
- Spellbook tooltip rows Speed / Sight array pairing. Start `FUN_00416615`, `FUN_004c628f`. [spells](data/spells.md#11-open-questions)

## Not started (from the reversing plan)

- `.alm` triggers (sections 7, 10–12); the server reader `FUN_00534ad4` parses all of them
  (switch on the section id). Sections 0–6, 8, 9 are done. [map](formats/map.md#open-questions)
- Part 5 leftovers: event classes of unit `behaviour` bits 1, 2, 4, section 9 per-cell payload.
  [map](formats/map.md#open-questions)
- Section 12 zones (INFERRED music) and the 8000–9999 slot codes of sections 7 and 11.
  [map](formats/map.md#open-questions)
- Unit struct: group AI, damage resolution, orders 0x16/0x18/0x19/0x1a.
  [unit-struct](engine/unit-struct.md#open-questions)
- Line of sight tables and the `FUN_00559536` gate; block-layer dynamic bits
  and per-class `movementType` (`FUN_00557a89`, vtable `+0x20`). [map](formats/map.md#open-questions)
- Dirt mark: caller of the clear `FUN_00559ce5` (the `+0x5c` byte is answered: damage spread, [spells](data/spells.md#4-effect-handlers)).
  [map](formats/map.md#open-questions)
- Structure registration at load: does a unit-made cell record exist before the structures (then
  `FUN_00559890` skips the refresh)? Do triggers name only structures? `FUN_005508a0` callers.
  [map](formats/map.md#open-questions)
- `famehall.dat`, saves (`game%d.sav`; the
  client state is a [`.reg`](formats/reg.md#writing) tree, `FUN_0048dc9f`), `.a2c`
  characters. [inventory §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)
- Text conventions of `main/text/*.txt` (line lists, `#key` sections,
  `mission%d.txt`). [inventory §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)

## Engine

- Day/night light recomputation in the engine. [architecture](engine/architecture.md#open-questions)
- Interface (G3b): how the exe clears a selection (right button `0x40f`, Esc? engine: right click);
  which bottom bar shows first; mouse-manager `+0x9c`; purpose of the 30 px top strip; `FUN_004b011e` (text vs
  human panel) and command-bar contents; hover brightness; structure pick rects; order command bytes and the squad
  voice. [ui-layout](engine/ui-layout.md#open-questions); start at `FUN_0040b2b8`, `FUN_004175c7`.
- Engine terrain scroll hitch (~27 ms per new cell row/column): pre-warm or flat-cell fast path.
  [architecture](engine/architecture.md#open-questions)
- Trigger references to world ids: section 11 is keyed by structure uid (`0x6000 + uid`, CONFIRMED),
  section 7 slots are coded numbers 8000–9999 (INFERRED class × 100 + index), section 3 cells have no exe
  id (engine ids `0x10000 + n` are ours). Left: decode section 7 (`FUN_00562745` `0x562a88`).
  [architecture](engine/architecture.md#open-questions)
- Unregistering a structure (`FUN_0055995a`) clears cells held by another structure; engine releases only
  its own cells. [architecture](engine/architecture.md#open-questions)
- [Cell effects](engine/rendering.md#open-questions) (answered: spell-area sprites, registered by [spells §4](data/spells.md#4-effect-handlers); drawing needs the spell system), unit invisibility / stone curse / hover, message 0x74 (flag 0x80); start at `FUN_004632a1`.
- [Engine object drawing](engine/rendering.md#open-questions): burnt ground, light-map lights on objects; start at `FUN_00404a2a`.
- [Engine minimap](engine/rendering.md#open-questions): final channel pass `0x4ac030`, fog background surface `DAT_00626be0`, fog gate of the unit dots; start at `FUN_004ac414`.
- Movement (H1) [simulation](engine/simulation.md#open-questions): waypoint removal and the tick an order ends after
  arrival (`FUN_00569321`, `FUN_00555dc2`); group speed and Haste/Slow in `unit_speed`; the regeneration job
  vs its `tick & 3` test (`FUN_0052bbb7`, `0x50fc5a`); the group-AI pass at `tick & 15 == 6` (`FUN_0056fe4d`).
- Pathfinding (H2) [simulation §7](engine/simulation.md#open-questions): blocker wait restart (type-0 group message, `FUN_00570087`/`FUN_00569321`; no swap exists, answered in 7.4), bit `0x10` (`FUN_00559c28`), follow-target `FUN_00557f08`/`FUN_0055574d`, class-0x12 clause `FUN_00556f56`.
- Phantom units (9 on blocked cells, never created by the server) and HP-0 units: engine keeps and draws them; decide with the phase H sim. [architecture §9](engine/architecture.md#9-world-state)
