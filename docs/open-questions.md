# Open questions

Index of everything not yet known; each spec's "Open questions" section is
the source of truth (rules in CLAUDE.md: add a line when raised, delete it
from both places when answered).

## Fonts

- Where cp1251 locale `.txt` text is converted to cp866 (typed input:
  `FUN_0047a0f5`; loader not found). [fonts](formats/fonts.md#open-questions)

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

- Sight mask algorithm (a2mgr Ordinal_93 → `FUN_10023720`, callbacks
  `0x10033cc0`/`0x10033c60`). [animation](formats/animation.md#16-visibility-gates)
- Data-driven speeds: monster speed, turn rate, monster attack bytes,
  spell missile speed `param[7]`, Haste/Slow (effect kind 17) strengths —
  data.bin (`FUN_0051aed6`, `FUN_00527122`). [animation](formats/animation.md#34-where-the-speeds-come-from)
- Server map fill `FUN_0055e616`: input layers `+0x10`/`+0x14`; who sets
  cell flag `0x20` (`FUN_00564137`). [animation](formats/animation.md#34-where-the-speeds-come-from)
- UI sequence timing (chrgen cube, Blind, map flags) and the inn pictures'
  loader (`FUN_004313db`, `FUN_004364c3`, `FUN_00474320`).
  [animation](formats/animation.md#49-other-ui-sequences)
- `weapon+0x4a` and `unit+0x86` in the hero attack recovery
  (`FUN_00518d2f`). [animation](formats/animation.md#34-where-the-speeds-come-from)

## Not started (from the reversing plan)

- `.alm` sections 0 and 4–12 (general info, structures, units, triggers,
  …). [inventory §5.2](inventory.md#52-alm-maps-m7r0)
- `world/data/data.bin`, `itemname.bin` / `.pkt`, `famehall.dat`, saves.
  [inventory §5.3, §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)
- Locale `.txt` conventions. [inventory §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)
- a2mgr's mapping of `.res` paths onto loose `data/` files (INFERRED).
  [inventory §4](inventory.md#4-a2mgrdll-allods2eu-client-patch)
