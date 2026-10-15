# Open questions

The index of everything not yet known, across all specs. Each entry links
to the spec section that holds the detail and names a starting point. The
spec's own "Open questions" section is the source of truth; this list only
collects them.

Rules (also in CLAUDE.md):
- When a spec gains an open question, add a line here in the same change.
- When a question is answered, update the spec and delete its line here
  (and from the spec's list) in the same change. Don't keep "answered"
  entries; git history keeps them.

## Fonts

- Where cp1251 locale `.txt` text is converted to cp866 for the font map
  (typed input uses `FUN_0047a0f5`; loader not found).
  [fonts](formats/fonts.md#open-questions)

## PNG / paper doll (a2mgr)

- Which exe routine draws the 12 doll layers and in what order (after
  0x46e21b); how `.256` and PNG layers mix. [png](formats/png.md#open-questions)
- Straight vs premultiplied alpha from GDI+ (`FUN_1000f220`, `FUN_1000fa90`).
  [png](formats/png.md#open-questions)
- Size/format rules for locale PNGs (a2mgr menu code). [png](formats/png.md#open-questions)

## Terrain and lighting

- Users of the vertex-table side arrays `view+0xb8` / `+0xbc` / `+0xc0`
  (`FUN_00406658`). [terrain](formats/terrain.md#open-questions)
- Who calls `FUN_0047b899` and with which mask; `DAT_00625778 & 2`
  (`terrain.3d`). [terrain](formats/terrain.md#open-questions)
- What object virtuals `+0x38` / `+0x40` stamp as lights (torches, fires).
  [lighting](mechanics/lighting.md#open-questions)
- Where static map lights come from and what drives their phase.
  [lighting](mechanics/lighting.md#open-questions)
- What `+0xa0` / `+0xa4` hold (INFERRED fog of war; `FUN_004040e2`,
  `FUN_00406981`). [lighting](mechanics/lighting.md#open-questions)

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
  spell missile speed `param[7]`, Haste/Slow (effect kind 17) strengths — data.bin (`FUN_0051aed6`,
  `FUN_00527122`). [animation](formats/animation.md#34-where-the-speeds-come-from)
- Server map fill `FUN_0055e616`: input layers `+0x10`/`+0x14`; who sets
  cell flag `0x20` (`FUN_00564137`). [animation](formats/animation.md#34-where-the-speeds-come-from)
- Meaning of `weapon+0x4a` and `unit+0x86` in the hero attack recovery
  (`FUN_00518d2f`). [animation](formats/animation.md#34-where-the-speeds-come-from)

## Not started (from the reversing plan)

- `.alm` sections 0 and 3–12 (general info, objects, structures, units,
  triggers, …). [inventory §5.2](inventory.md#52-alm-maps-m7r0)
- `world/data/data.bin`, `itemname.bin` / `.pkt`, `famehall.dat`, saves.
  [inventory §5.3, §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)
- Locale `.txt` conventions. [inventory §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)
- a2mgr's mapping of `.res` paths onto loose `data/` files (INFERRED).
  [inventory §4](inventory.md#4-a2mgrdll-allods2eu-client-patch)
