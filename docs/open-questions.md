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

- What `.alm` section 3 holds (runtime `+0x14`, copied inside an 8-cell
  border by `FUN_004abc1c`). [terrain](formats/terrain.md#open-questions)
- Users of the vertex-table side arrays `view+0xb8` / `+0xbc` / `+0xc0`
  (`FUN_00406658`). [terrain](formats/terrain.md#open-questions)
- Who calls `FUN_0047b899` and with which mask; `DAT_00625778 & 2`
  (`terrain.3d`). [terrain](formats/terrain.md#open-questions)
- Which setting controls `DAT_005fb974` (gates water and structure animation).
  [terrain](formats/terrain.md#open-questions)
- Tiles bits 14–15 (`0xc000`), masked but never set. [terrain](formats/terrain.md#open-questions)
- What object virtuals `+0x38` / `+0x40` stamp as lights (torches, fires).
  [lighting](mechanics/lighting.md#open-questions)
- Where static map lights come from and what drives their phase.
  [lighting](mechanics/lighting.md#open-questions)
- What `+0xa0` / `+0xa4` hold (INFERRED fog of war; `FUN_004040e2`,
  `FUN_00406981`). [lighting](mechanics/lighting.md#open-questions)

## Units and registries

- Unit states 2 and 4 (`obj+0x78`; others known from `FUN_0046b5ef`).
  [units](formats/units.md#open-questions)
- Meaning of `Index`, `TileSize`, `Z`, `ShootOffset`, the selection rect;
  how `Palette > 1` picks a palette (`FUN_00473010`). [units](formats/units.md#open-questions)
- Facing direction sense (clockwise or not); only "sprite direction 0 =
  seen from behind" is INFERRED. [units](formats/units.md#facing)
- `.reg` writers (`FUN_004eae80`, `FUN_004ed9f0`, `FUN_004edd03`); whether
  `.res` uses the same container. [reg](formats/reg.md#open-questions)
- `.reg` header `+0x14` and entry `+0`. [reg](formats/reg.md#open-questions)

## Animation

- Unit move-phase formula (`FUN_0046b5ef` case 1, `obj+0x24 < 0` branch).
  [animation](formats/animation.md#open-questions)
- Source of unit action durations `obj+0xa8` (server messages, `FUN_00464f02`);
  default game speed (`FUN_00492068`). [animation](formats/animation.md#open-questions)
- Nine destructible structures without a destroyed block (`FUN_004669e8`).
  [animation](formats/animation.md#open-questions)
- Hero dying/bones frames: which file the hero draw uses for `T2` (`FUN_00468640`).
  [animation](formats/animation.md#open-questions)
- `FUN_004206c0` (structure tick guard). [animation](formats/animation.md#open-questions)
- Seven burning-tree objects reference files absent from this install.
  [animation](formats/animation.md#open-questions)

## Not started (from the reversing plan)

- `.alm` sections 0 and 3–12 (general info, objects, structures, units,
  triggers, …). [inventory §5.2](inventory.md#52-alm-maps-m7r0)
- `world/data/data.bin`, `itemname.bin` / `.pkt`, `famehall.dat`, saves.
  [inventory §5.3, §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)
- Locale `.txt` conventions. [inventory §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)
- a2mgr's mapping of `.res` paths onto loose `data/` files (INFERRED).
  [inventory §4](inventory.md#4-a2mgrdll-allods2eu-client-patch)
