# `.reg`: registry files (signature 0x31415926)

Code: `allods2/reg.py` (`load_reg(path, fs)`). Tools: `tools/validate_reg.py`
(all 17 files: 5 in `graphics.res`, 8 in `video.res`, 2 in `world.res`,
`sfx.res` and `scenario.res` one each).

A tree of named entries: sections hold a contiguous run of children;
leaves are ints, floats, strings or int arrays whose payload is in a blob
after the directory. Used by `units.reg`, `structures.reg`, `objects.reg`,
`projectiles.reg`, `material.reg`, `sfx.reg`, `map.reg`, `ai.reg`,
`scenario/npc.reg` and the `video/*/NN.reg` fade scripts.

## Layout

Little-endian u32s:

| Offset | Size | Field |
|---|---|---|
| 0x00 | 4 | signature `0x31415926` (`26 59 41 31`, "&YA1"), else "bad signature" |
| 0x04 | 12 | **root entry** value and type: first child index, child count, type (always `0x11`) |
| 0x10 | 4 | N directory entries |
| 0x14 | 4 | 0 in all files (read, unused here) |
| 0x18 | 32·N | entries |
| … | 4 | D, blob size |
| … | D | blob |

Entry (32 bytes): `+0` 0; `+4` 8-byte value by type; `+12` type (low 4
bits kind, `0x10` = children sorted); `+16` name, 16 bytes NUL-padded (≤ 15
compared).

| Kind | Count | Value at +4 / +8 | Getter |
|---|---:|---|---|
| 0 string | 1,767 | blob offset, byte length (cp1251, NUL-terminated) | `FUN_004e69c2` |
| 1 section | 512 (+17 roots) | first child index, child count | — |
| 2 int (3 also accepted) | 5,001 | i32 | `FUN_004e6f9f`: `(type & 0xe) == 2`, else "not an int associated with specified key" |
| 4 float | 22 | f64 (e.g. `startfade`, `endfade`) | — |
| 6 int array | 436 | blob offset, byte length of i32s (e.g. `AnimationTime`) | `FUN_004e7589` |

- CONFIRMED (`FUN_004e488c`): reads 16 bytes (signature + root), N and the
  next u32, `32·N` directory bytes, then D and the blob.
- CONFIRMED (all 17 files): `0x18 + 32·N + 4 + D` = file size; every child
  and blob range in bounds; only the roots carry the sorted flag.
- INFERRED (data): float and string/array value layouts (sensible values
  everywhere: `startfade` 0.5, paths, frame lists).

## Lookup: `FUN_004e918e(section, key)`

CONFIRMED. A path like `Unit5/MovePhases` is resolved one level at a time:
in a **sorted** section (the root) the key is cut to 15 chars
(`FUN_004e3620`) and binary-searched with `strcmp` (`FUN_004e941a`,
case-sensitive); otherwise a linear `_strnicmp(key, name, 15)`
(`FUN_005859c0`, case-insensitive). Missing → caller's default (for
unit file names the empty string at `0x626d34`). Consequence: a name with
leading or trailing spaces can never be found; `tools/validate_reg.py`
lists such names, and no shipped file has one (CONFIRMED, all 17 files).

The `.res` archives use the same entry layout with a different header
(directory offset + count, directory at the end): [res](res.md).

## Worked example

`units.reg` starts `26 59 41 31 | 00 00 00 00 | 3f 00 00 00 | 11 00 00 00 |
55 06 00 00 …`: 63 top-level sections (`Files`, `Global`, `Unit0` … `Unit60`, in
`strcmp` order: `Unit10` before `Unit2`). `Unit0/MovePhases` is an int
entry whose +4..+7 hold 8. `projectiles.reg` has 32 (`Global`,
`Projectile0`–`Projectile30`).

## Open questions

- The writers `FUN_004e4bb0` and `FUN_004e4ec3` (they store the
  signature at `0x4e4c40` / `0x4e51bf`); `FUN_004e2040`, the third routine
  that holds it, is the `.res` opener ([res](res.md)).
- The meaning of header `+0x14` and entry `+0`.
