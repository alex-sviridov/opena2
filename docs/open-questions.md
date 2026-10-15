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

## Graphics: sprites and palettes

- What bit `8` of the per-player relation word means (`FUN_00420660`);
  gates drawing units with effect `0x20`. [sprites](formats/sprites.md#open-questions)
- Which sprite list the inventory indicator with the level-8 drop shadow
  comes from (`FUN_004b9a42`). [sprites](formats/sprites.md#open-questions)
- Effect id → spell mapping (0x20, 0x2c); needs `data.bin`.
  [palettes](formats/palettes.md#open-questions)
- Which UI elements use which text-colour table (`0x5fb97c…0x5fb990`, §6).
  [palettes](formats/palettes.md#open-questions), [fonts](formats/fonts.md#open-questions)
- Why 391 smoothing overlays embed an all-zero palette (INFERRED unused).
  [palettes](formats/palettes.md#open-questions)
- The 24 → 16-bit conversion of the "Bitmap 64k" class (`0x5d53f0`).
  [bitmaps](formats/bitmaps.md#open-questions)

## Fonts

- What sets `DAT_0062c9c4` (cp866 remap) and whether the English build
  turns it on. [fonts](formats/fonts.md#open-questions)
- Why a2mgr maps 0xC1 to glyph 0x80 (`Ordinal_26`). [fonts](formats/fonts.md#open-questions)
- Which callers pass which colour tables and alignment flags.
  [fonts](formats/fonts.md#open-questions)
- What `font5.ttf` is used for (a2mgr SDL_ttf). [fonts](formats/fonts.md#open-questions)

## PNG / paper doll (a2mgr)

- Which exe routine draws the 12 doll layers and in what order (after
  0x46e21b); how `.256` and PNG layers mix. [png](formats/png.md#open-questions)
- Straight vs premultiplied alpha from GDI+ (`FUN_1000f220`, `FUN_1000fa90`).
  [png](formats/png.md#open-questions)
- Size/format rules for locale PNGs (a2mgr menu code). [png](formats/png.md#open-questions)

## Terrain and lighting

- Height-displaced tile blit `FUN_0045c8ce` and the vertex table at view
  `+0xb4`; a2mgr `Ordinal_65` hooks the row loop at 0x40529d.
  [terrain](formats/terrain.md#open-questions)
- How `.alm` altitudes (u8) become the runtime signed height map at `+0x10`
  (reader `FUN_0053ea3a`). [lighting](mechanics/lighting.md#open-questions)
- Who calls `FUN_0047b899` and with which mask; `DAT_00625778 & 2`
  (`terrain.3d`). [terrain](formats/terrain.md#open-questions)
- `DAT_005fb974` (water animation option) and the rate of `view+0xa88`.
  [terrain](formats/terrain.md#open-questions)
- Tiles bits 14–15 (`0xc000`), masked but never set. [terrain](formats/terrain.md#open-questions)
- What object virtuals `+0x38` / `+0x40` stamp as lights (torches, fires).
  [lighting](mechanics/lighting.md#open-questions)
- Where static map lights come from and what drives their phase.
  [lighting](mechanics/lighting.md#open-questions)
- What `+0xa0` / `+0xa4` hold (INFERRED fog of war; `FUN_004040e2`,
  `FUN_00406981`). [lighting](mechanics/lighting.md#open-questions)

## Units and registries

- Unit states 2 and 4 and the full state list (`obj+0x78`).
  [units](formats/units.md#open-questions)
- Sequence tick rate and `obj+0x74` during dying. [units](formats/units.md#open-questions)
- Meaning of `Index`, `TileSize`, `Z`, `ShootOffset`, the selection rect;
  how `Palette > 1` picks a palette (`FUN_00473010`). [units](formats/units.md#open-questions)
- Facing direction sense (clockwise or not); only "sprite direction 0 =
  seen from behind" is INFERRED. [units](formats/units.md#facing)
- `structures.reg` / `objects.reg` loaders and frame layout.
  [units](formats/units.md#open-questions)
- `.reg` writers (`FUN_004eae80`, `FUN_004ed9f0`, `FUN_004edd03`); whether
  `.res` uses the same container. [reg](formats/reg.md#open-questions)
- `.reg` header `+0x14` and entry `+0`. [reg](formats/reg.md#open-questions)

## Not started (from the reversing plan)

- `.alm` sections 0 and 3–12 (general info, objects, structures, units,
  triggers, …). [inventory §5.2](inventory.md#52-alm-maps-m7r0)
- `world/data/data.bin`, `itemname.bin` / `.pkt`, `famehall.dat`, saves.
  [inventory §5.3, §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)
- Locale `.txt` conventions. [inventory §6](inventory.md#6-plan-custom-formats-to-reverse-in-order)
- a2mgr's mapping of `.res` paths onto loose `data/` files (INFERRED).
  [inventory §4](inventory.md#4-a2mgrdll-allods2eu-client-patch)
