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

- `.alm` sections 5–12 (players, units, triggers, …); the server reader
  `FUN_00534ad4` parses all of them (switch on the section id); 46 campaign
  maps in `scenario.res`. Header, terrain, objects and structures (sections
  3–4) are done. [map](formats/map.md#open-questions)
- Line of sight tables and the `FUN_00559536` gate; block-layer dynamic bits
  and per-class `movementType` (`FUN_00557a89`, vtable `+0x20`); the search
  `FUN_0054d76e` (phase H). [map](formats/map.md#open-questions)
- `.alm` header leftovers: `field_0c` (360/720), `field_84/88/8c/90`
  users; meaning of effect byte `+0x5c` (spell dirt mark, `FUN_00559c28`), caller of the clear `FUN_00559ce5`.
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
- Trigger references to world ids (map sections 5-12): structures `0x6000 + uid`, section 3 cells
  have no exe id (engine ids `0x10000 + n` are ours). Starting routine `FUN_00534ad4` cases 5-12.
  [architecture](engine/architecture.md#open-questions)
- Unregistering a structure (`FUN_0055995a`) clears cells held by another structure; engine releases only
  its own cells. [architecture](engine/architecture.md#open-questions)
- [Cell effects `FUN_0040af69`, unit shadow `FUN_00464487`](formats/map.md#open-questions): what the two effect passes draw; start at `FUN_0040af69`.
- [Engine object drawing](engine/rendering.md#open-questions): window origin vs. relief, structure `ShadowY` +-20000, shadows of destroyed/flat structures, burnt ground, light-map lights on objects; start at `FUN_00406f43`, `FUN_00461890`.
