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
| 0x14 | 4 | G, garbage: blob bytes no longer referenced (0 in all files) |
| 0x18 | 32·N | entries |
| … | 4 | D, blob size |
| … | D | blob |

Entry (32 bytes): `+0` 0 (CONFIRMED written 0 by `FUN_004e8ed0`; no
reader seen in the registry routines, INFERRED padding); `+4` 8-byte
value by type; `+12` type (low 4 bits kind, `0x10` = children sorted);
`+16` name, 16 bytes NUL-padded (≤ 15 compared).

| Kind | Count | Value at +4 / +8 | Getter |
|---|---:|---|---|
| 0 string | 1,767 | blob offset, byte length (cp1251, NUL-terminated) | `FUN_004e69c2` |
| 1 section | 512 (+17 roots) | first child index, child count | — |
| 2 int (3 also accepted) | 5,001 | i32 | `FUN_004e6f9f`: `(type & 0xe) == 2`, else "not an int associated with specified key" |
| 4 float | 22 | f64 (e.g. `startfade`, `endfade`) | — |
| 6 int array | 436 | blob offset, byte length of i32s (e.g. `AnimationTime`) | `FUN_004e7589` |
| 8 string list | 0 | blob offset, byte length (u32 count + strings) | (§ Writing) |
| `0xa` float array | 0 | blob offset, byte length of f64s | (§ Writing) |

- CONFIRMED (`FUN_004e488c`): reads 16 bytes (signature + root), N and
  G, `32·N` directory bytes, then D and the blob.
- CONFIRMED (writer `FUN_004e4a86`): sorts (below), then writes signature,
  root, N, G, the directory, D and the blob, the same order. G counts
  the blob bytes freed when a string or array value is replaced or its
  entry removed (`FUN_004e92f5`, `FUN_004e6e2d`); nothing compacts them.
- CONFIRMED (all 17 files): `0x18 + 32·N + 4 + D` = file size; every child
  and blob range in bounds; only the roots carry the sorted flag.
- CONFIRMED (`FUN_004e4ec3`, § Writing): f64 at `+4` for floats; blob
  offset and byte length for strings (length counts the NUL) and arrays.

## Lookup: `FUN_004e918e(section, key)`

CONFIRMED. A path like `Unit5/MovePhases` is resolved one level at a time:
in a **sorted** section (the root) the key is cut to 15 chars
(`FUN_004e3620`) and binary-searched with `strcmp` (`FUN_004e941a`,
case-sensitive); otherwise a linear `_strnicmp(key, name, 15)`
(`FUN_005859c0`, case-insensitive). Missing → caller's default (for
unit file names the empty string at `0x626d34`). Consequence: a name with
leading or trailing spaces can never be found; `tools/validate_reg.py`
lists such names, and no shipped file has one (CONFIRMED, all 17 files).

## Writing

CONFIRMED. `FUN_004e4bb0` builds an empty registry (root type 1, room
for 4 entries, a 32-byte blob). `FUN_004e8ed0` adds a key to a section:
an existing key of that name is marked `0x40000000` (removed), the
section's run is moved to the end of the table if it is not already the
last one (`FUN_004e8b28`), and the new entry is appended with `+0` = 0;
the section loses its sorted flag. The setters (`FUN_004e6e2d` strings and
the others next to it) reuse the old blob slot when the new value fits.

Before writing, `FUN_004e8e26` sorts a section's children with `qsort` and
`strcmp` (`FUN_004e941a`) and sets `0x10`. It means to recurse into
subsections first, but its loop tests entry `first + count` (one past the
run) on every pass instead of entry `first + i`. So subsections are
sorted only if that entry happens to be a section, which is what makes
roots the only sorted sections (CONFIRMED, all 17 files: the entry after
the root's run is a leaf in each). Match it when writing files the game
reads.

Users: the save writer `FUN_0048dc9f` (keys `GameOptions`, `SpellBook`,
`Objects/Group%d`, `Projectiles/Prj%d`, …: the client state of a save
is a `.reg` tree)
and the other `FUN_004e4bb0` callers.

`FUN_004e4ec3` compiles an INI text file into a `.reg` (it has no
callers; a leftover of the build tools): `[section]` at line start,
`key=value` (key ≤ 15 chars, trailing blanks cut, `;` comment lines).
Values classify as: int (2) if all digits, with an optional leading
`-`; float (4) with `.`, `e` or `E`; int array (6) / float array (`0xa`)
with commas; anything else a string (0). A repeated string key becomes a
string list (type 8: u32 count + NUL-separated strings) if the repeats
are adjacent; other duplicates are errors.

The `.res` archives use the same entry layout with a different header
(directory offset + count, directory at the end): [res](res.md).

## Worked example

`units.reg` starts `26 59 41 31 | 00 00 00 00 | 3f 00 00 00 | 11 00 00 00 |
55 06 00 00 …`: 63 top-level sections (`Files`, `Global`, `Unit0` … `Unit60`, in
`strcmp` order: `Unit10` before `Unit2`). `Unit0/MovePhases` is an int
entry whose +4..+7 hold 8. `projectiles.reg` has 32 (`Global`,
`Projectile0`–`Projectile30`).

## Open questions

- None.
