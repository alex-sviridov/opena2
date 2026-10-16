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
  users; column names known), item-class i16s, special-item byte,
  `castSpell`/`damage*` modifier values (`FUN_0051f1c3`, `FUN_0051f072`).
  [databin](formats/databin.md#open-questions)

## Not started (from the reversing plan)

- `.alm` triggers (sections 7, 10–12); the server reader `FUN_00534ad4` parses all of them
  (switch on the section id). Sections 0–6, 8, 9 are done. [map](formats/map.md#open-questions)
- Part 5 leftovers: event classes of unit `behaviour` bits 1, 2, 4, section 9 per-cell payload,
  gold pickup vs `Player.money`, item `+0x1c`. [map](formats/map.md#open-questions)
- Section 12 zones (INFERRED music) and the 8000–9999 slot codes of sections 7 and 11.
  [map](formats/map.md#open-questions)
- Unit struct: path finder `FUN_0054d76e`, group AI, damage resolution, orders 0x16/0x18/0x19/0x1a.
  [unit-struct](engine/unit-struct.md#open-questions)
- Line of sight tables and the `FUN_00559536` gate; block-layer dynamic bits
  and per-class `movementType` (`FUN_00557a89`, vtable `+0x20`); the search
  `FUN_0054d76e` (phase H). [map](formats/map.md#open-questions)
- Meaning of effect byte `+0x5c` (spell dirt mark, `FUN_00559c28`), caller of the clear `FUN_00559ce5`.
  [map](formats/map.md#open-questions)
- Structure registration at load: does a unit-made cell record exist before the structures (then
  `FUN_00559890` skips the refresh)? Do triggers name only structures? `FUN_005508a0` callers.
  [map](formats/map.md#open-questions)
- `itemname.bin` / `.pkt`, `famehall.dat`, saves (`game%d.sav`; the
  client state is a [`.reg`](formats/reg.md#writing) tree, `FUN_0048dc9f`), `.a2c`
  characters. [inventory §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)
- Text conventions of `main/text/*.txt` (line lists, `#key` sections,
  `mission%d.txt`). [inventory §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)

## Engine

- View scroll limits, scroll speed and edge-scroll zone of the exe (engine uses
  chosen values); day/night light recomputation in the engine.
  [architecture](engine/architecture.md#open-questions)
- Engine terrain scroll hitch (~27 ms per new cell row/column): pre-warm or flat-cell fast path.
  [architecture](engine/architecture.md#open-questions)
- Trigger references to world ids: section 11 is keyed by structure uid (`0x6000 + uid`, CONFIRMED),
  section 7 slots are coded numbers 8000–9999 (INFERRED class × 100 + index), section 3 cells have no exe
  id (engine ids `0x10000 + n` are ours). Left: decode section 7 (`FUN_00562745` `0x562a88`).
  [architecture](engine/architecture.md#open-questions)
- Unregistering a structure (`FUN_0055995a`) clears cells held by another structure; engine releases only
  its own cells. [architecture](engine/architecture.md#open-questions)
- [Cell effects `FUN_0040af69`, unit shadow `FUN_00464487`](formats/map.md#open-questions): what the two effect passes draw; start at `FUN_0040af69`.
- [Engine object drawing](engine/rendering.md#open-questions): window origin vs. relief, structure `ShadowY` +-20000, shadows of destroyed/flat structures, burnt ground, light-map lights on objects; start at `FUN_00406f43`, `FUN_00461890`.
- [Engine minimap](engine/rendering.md#open-questions): final channel pass `0x4ac030`, fog background surface `DAT_00626be0`, minimap objects (units); start at `FUN_004ac414`.
