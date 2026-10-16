# Open questions

Index of everything not yet known; each spec's "Open questions" section is
the source of truth (rules in CLAUDE.md: add a line when raised, delete it
from both places when answered).

## PNG / paper doll (a2mgr)

- Which exe routine draws the 12 doll layers and in what order (after
  `0x46e21b`); how `.256` and PNG layers mix. [png](formats/png.md#open-questions)
- Straight vs premultiplied GDI+ alpha (`FUN_1000f220`, `FUN_1000fa90`).
  [png](formats/png.md#open-questions)
- Size/format rules for locale PNGs (a2mgr menu code). [png](formats/png.md#open-questions)

## Terrain and lighting

- How the view draw turns fog levels (`view+0xa0`) into drawn fog
  (`0x40a1b3`–`0x40a420`). [lighting](mechanics/lighting.md#open-questions)

## Units and registries

- Where the server takes a monster's palette variant (`obj+0x28`, create
  message byte `DAT_0060e4c8`). [units](formats/units.md#open-questions)
- `.reg` writers (`FUN_004eae80`, `FUN_004ed9f0`, `FUN_004edd03`); whether
  `.res` uses the same container. [reg](formats/reg.md#open-questions)
- `.reg` header `+0x14` and entry `+0`. [reg](formats/reg.md#open-questions)

## Animation

- Chargen cube frame timing (`FUN_004313db` `+0x8c`) and the inn
  pictures' loader. [animation](formats/animation.md#49-other-ui-sequences)
- How the world map opens with `Flag1`/`Flag` absent while their frame
  counts drive the flags (`FUN_00474320`, `FUN_00426da9`).
  [animation](formats/animation.md#49-other-ui-sequences)

## data.bin

- Human and structure parameter maps (`FUN_004ade80`, `FUN_004adea0`
  users), item-class i16s, factor doubles, `castSpell`/`damage*` modifier
  values (`FUN_00528e94`, `FUN_00528d43`). [databin](formats/databin.md#open-questions)

## Not started (from the reversing plan)

- `.alm` sections 0 and 4–12 (general info, structures, units, triggers,
  …); the server reader `FUN_0053ea3a` parses all of them (switch on the
  section id). [inventory §5.2](inventory.md#52-alm-maps-m7r0)
- `itemname.bin` / `.pkt`, `famehall.dat`, saves.
  [inventory §5.3, §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)
- Locale `.txt` conventions. [inventory §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)
- a2mgr's mapping of `.res` paths onto loose `data/` files (INFERRED).
  [inventory §4](inventory.md#4-a2mgrdll-allods2eu-client-patch)
