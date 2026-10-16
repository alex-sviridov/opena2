# Paper doll: the inventory figure

Code: `allods2/graphics/paperdoll.py` (`doll_layer_order`,
`doll_mask_order`). The figure is composed from `.256` layers
([sprites](sprites.md)) under `graphics/equipment/`.

## Layer files: `FUN_004688f7`

CONFIRMED (string pushes `0x46898a`–`0x468d29`). Per slot, with `<body>`
= `mfighter\`, `mmage\`, `ffighter\`, `fmage\` (strings
`0x5f1270`…`0x5f1290`) and `name` = the item's picture name
(`FUN_00438ba1`, e.g. `0001008`):

- primary: `graphics\equipment\<body>\primary\<name>.256`
- secondary: `graphics\equipment\<body>\secondary\<name>.256`, only for
  slots 3, 8, 9, and 7 when `obj[+0x1b8] & 2` (`0x468c59`–`0x468c87`)
- body: `sprintf("%s%d.256", prefix, obj[+0x28])` (`0x5f12c0`)

Each file is loaded with the exe sprite loader `0x424559` and given shade
table mode 1, 1 level (`0x424390`, [palettes](palettes.md)). INFERRED: a
missing file stops the game with the loader's `FATAL ERROR: can't load`
([animation §1.9](animation.md)).

## Compositing

CONFIRMED (the order code from the two-handed check `0x468edc` to the
dump call `0x4696ec` was compared instruction by instruction). `FUN_004688f7` is CUnit virtual `+0x88` (vtable `0x5cd5d0`;
also CAirUnit's), args `(file, surface, mask)`. It zeroes the 16-bit
`surface` and the byte `mask`, builds the layers (primary `P0…P11`,
secondary `S…`, body `B`), then draws each layer at (0, 0) into the
surface; later layers cover earlier ones.

1. `graphics\infowindow\horse.bmp` when `obj[+0x24]` is 17…21.
2. Hero back `graphics\interface\heroback\backm.256` / `backf.256` (by
   `+0x1b8 & 4`) when `+0x1b8 & 1` and not `& 2` (globals `0x626c94/60`, loaded in the interface loader `FUN_00476a6d`).
3. Body type `+0x1b8 & 6`: 0 `mfighter`, 2 `mmage`, 4 `ffighter`,
   6 `fmage`. With `& 2` (mage):

   `P7 B P11 P9 S9 P3 S3 P6 P4 P0 P5 S7`

   otherwise (fighter), with `2h` = slot 0's item class (`FUN_00438da7`:
   `bowman`, `archer`, `xbowman`, `axeman2h`, `swordsman2h`, `mage_st`):

   `B P11 P10 P6 P3 P4 P8 P9 [P0 if not 2h] P7 S3 P5 S8 S9 (P0 if 2h else P1)`

4. If `mask`: each layer writes its id (slot + 1; body 0) where it
   covers, in the same order except: the mage list adds `P8` (id 9,
   between `P4` and `P0`) though `P8` is never drawn for mages; the
   fighter list has no `B`.
5. If `file`: `FUN_00425273` writes a 14 + 40 byte header, the pixels as
   24-bit, then the mask (INFERRED: a BMP dump).

Never drawn: `P2`, and for mages `P1`, `P8`, `P10`.

## Open questions

None.
