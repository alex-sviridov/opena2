# `.reg`: registry files (signature 0x31415926)

Code: `allods2/reg.py`. Tools: `tools/validate_reg.py` (all 17 files).

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
| 0 string | 1,770 | blob offset, byte length (cp1251, NUL-terminated) | `FUN_004ef802` |
| 1 section | 513 (+17 roots) | first child index, child count | — |
| 2 int (3 also accepted) | 5,025 | i32 | `FUN_004efddf`: `(type & 0xe) == 2`, else "not an int associated with specified key" |
| 4 float | 22 | f64 (e.g. `startfade`, `endfade`) | — |
| 6 int array | 444 | blob offset, byte length of i32s (e.g. `AnimationTime`) | `FUN_004f03c9` |

- CONFIRMED (`FUN_004ed6cc`): reads 16 bytes (signature + root), N and the
  next u32, `32·N` directory bytes, then D and the blob.
- CONFIRMED (all 17 files): `0x18 + 32·N + 4 + D` = file size; every child
  and blob range in bounds; only the roots carry the sorted flag.
- INFERRED (data): float and string/array value layouts (sensible values
  everywhere: `startfade` 0.5, paths, frame lists).

## Lookup: `FUN_004f1f4e(section, key)`

CONFIRMED. A path like `Unit5/MovePhases` is resolved one level at a time:
in a **sorted** section (the root) the key is cut to 15 chars
(`FUN_004ec460`) and binary-searched with `strcmp` (`FUN_004f21da`,
case-sensitive); otherwise a linear `_strnicmp(key, name, 15)`
(`FUN_0058fa60`, case-insensitive). Missing → caller's default.
Consequence (CONFIRMED by data): three `units.reg` names with trailing
spaces are unreachable: `Files/"File0 "`, `"DescText        "` in one unit,
`"InMapEditor "` in another; so Unit0 (ID 3, Human Swordsman) gets the
default path `""` (empty string at `0x630f08`) instead of
`humans\swordsman\swordsman`.

## Worked example

`units.reg` starts `26 59 41 31 | 00 00 00 00 | 40 00 00 00 | 11 00 00 00 |
N …`: 64 top-level sections (`Files`, `Global`, `Unit0` … `Unit61`, in
`strcmp` order: `Unit10` before `Unit2`). `Unit0/MovePhases` is an int
entry whose +4..+7 hold 8. `projectiles.reg` has 32 (`Global`,
`Projectile0`–`Projectile30`).

## Open questions

- The writers (`FUN_004eae80`, `FUN_004ed9f0`, `FUN_004edd03`, which also
  hold the signature) and whether `.res` archives use the same container.
- The meaning of header `+0x14` and entry `+0`.
