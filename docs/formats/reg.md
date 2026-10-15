# `.reg`: registry files (signature 0x31415926)

Binary: `allods2.exe` English 1.30, sha256
`2a8bdf9dc69276cc8d4fee561a7473a6b0f709cf9758abddaf2cd3b1fdfdfe43`.
Addresses were read in REA (Ghidra 12.1.4). Implementation:
`allods2/reg.py`. Validation: `tools/validate_reg.py` (all 17 files).

A `.reg` is a tree of named entries: sections hold a contiguous run of child
entries; leaves are integers, floats, strings or integer arrays whose
payload lives in a data blob after the directory. Used by `units.reg`,
`structures.reg`, `objects.reg`, `projectiles.reg`, `material.reg`,
`sfx.reg`, `map.reg`, `ai.reg`, `scenario/npc.reg` and the `video/*/NN.reg`
fade scripts.

## Layout

All integers are little-endian u32.

| Offset | Size | Field |
|---|---|---|
| 0x00 | 4 | signature `0x31415926`, else "bad signature" |
| 0x04 | 12 | the **root entry's** value and type: first child index, child count, type (always `0x11`) |
| 0x10 | 4 | N, number of directory entries |
| 0x14 | 4 | 0 in all files (read, not used here) |
| 0x18 | 32·N | directory entries |
| … | 4 | D, blob size |
| … | D | blob |

Entry, 32 bytes:

| Offset | Size | Field |
|---|---|---|
| +0 | 4 | 0 |
| +4 | 8 | value (by type, below) |
| +12 | 4 | type: low 4 bits = kind, `0x10` = children sorted |
| +16 | 16 | name, NUL-padded (at most 15 characters are compared) |

| Kind | Count | Value at +4 / +8 | Getter |
|---|---:|---|---|
| 0 string | 1,770 | blob offset, byte length (cp1251, NUL-terminated) | `FUN_004ef802` |
| 1 section | 513 (+17 roots) | first child index, child count | — |
| 2 int (3 also accepted) | 5,025 | i32 | `FUN_004efddf`: `(type & 0xe) == 2`, else "not an int associated with specified key" |
| 4 float | 22 | f64 | — |
| 6 int array | 444 | blob offset, byte length of i32s | `FUN_004f03c9` |

- **CONFIRMED** (`FUN_004ed6cc`): the reader reads 16 bytes (signature +
  root entry), then N and the next u32, then `32·N` bytes of directory,
  then D and D bytes of blob.
- **CONFIRMED** (all 17 files): `0x18 + 32·N + 4 + D` is the file size;
  every child range and blob range is in bounds; only the 17 roots carry
  the sorted flag.
- **INFERRED** (data): the float and string/array value layouts. They give
  sensible values everywhere (`startfade` 0.5, path strings, frame lists).

## Lookup: `FUN_004f1f4e(section, key)`

**CONFIRMED.** A path like `Unit5/MovePhases` is looked up one level at a
time:

- **sorted section** (`type & 0x10`, i.e. the root): the key is cut to 15
  characters (`FUN_004ec460`) and binary-searched with `strcmp`
  (`FUN_004f21da`). Case-sensitive, exact.
- **otherwise**: linear scan with `_strnicmp(key, name, 15)`
  (`FUN_0058fa60`). Case-insensitive.

A missing key returns the caller's default. Consequence, CONFIRMED by data:
three names in `units.reg` have trailing spaces and can never be found:
`Files/"File0 "`, `"DescText        "` in one unit and `"InMapEditor "` in
another. So Unit0 (ID 3, Human Swordsman) gets the default file path `""`
(the empty string at `0x630f08`) instead of `humans\swordsman\swordsman`.

## Worked example

`units.reg` starts `26 59 41 31 | 00 00 00 00 | 40 00 00 00 | 11 00 00 00 |
N …`: 64 top-level sections (`Files`, `Global`, `Unit0` … `Unit61`, in
`strcmp` order so `Unit10` comes before `Unit2`). `Unit0/MovePhases` is an
int entry whose bytes +4..+7 hold 8.

## Open questions

- The writers (`FUN_004eae80`, `FUN_004ed9f0`, `FUN_004edd03`) and whether
  `.res` archives use the same container.
- The meaning of header `+0x14` and entry `+0`.
