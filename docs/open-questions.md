# Open questions

Index of everything not yet known; each spec's "Open questions" section is
the source of truth (rules in CLAUDE.md: add a line when raised, delete it
from both places when answered).

## Archives and registries

- `.res`: confirm absolute entry offsets in the file reader; what writes
  flags `0x40000000` / bit 31 (`FUN_004e2040` write mode, `FUN_004e9153`
  callers). [res](formats/res.md#open-questions)
- `.res` archive-name case: `FUN_004e9046` compares case-sensitively, but
  paths like `SFX\Add.wav` exist; find the lower-casing (manager
  `0x6682b0`). [res](formats/res.md#open-questions)
- `update.lst` and the CD `Allods\` directory mount (`FUN_004e2a1d`,
  `FUN_004e2963`). [res](formats/res.md#open-questions)
- `.reg` writers `FUN_004e4bb0`, `FUN_004e4ec3`.
  [reg](formats/reg.md#open-questions)
- `.reg` header `+0x14` and entry `+0`. [reg](formats/reg.md#open-questions)

## Animation

- Town scenes `interface/townbirds/*`, `interface/town_druid/bug`,
  `lizard`: draw code and timing (string refs to `townbirds`,
  `town_druid`). [animation](formats/animation.md#open-questions)
- World-map Cross state (`FUN_0046fdd5` `0x470279`–`0x47040a`).
  [animation](formats/animation.md#open-questions)

## data.bin

- Human and structure fields in code (`FUN_004a65b0`, `FUN_004a65d0`
  users; column names known), item-class i16s, special-item byte,
  `castSpell`/`damage*` modifier values (`FUN_0051f1c3`, `FUN_0051f072`).
  [databin](formats/databin.md#open-questions)

## Not started (from the reversing plan)

- `.alm` sections 0 and 4–12 (general info, structures, units, triggers,
  …); the server reader `FUN_00534ad4` parses all of them (switch on the
  section id); 46 campaign maps in `scenario.res`.
  [inventory §5.2](inventory.md#52-alm-maps-m7r0)
- `itemname.bin` / `.pkt`, `famehall.dat`, saves (`game%d.sav`), `.a2c`
  characters. [inventory §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)
- Text conventions of `main/text/*.txt` (line lists, `#key` sections,
  `mission%d.txt`). [inventory §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)
