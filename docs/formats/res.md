# `.res`: resource archives (signature 0x31415926)

Code: the stand-alone library `a2res` (`ResArchive`, `ResFS`, `DirFS`,
`ChainFS`; § Library). Tools: `tools/validate_res.py` (all 10 archives),
`python -m allods2 res ls|list|extract`.

The install keeps its game data in one archive per top-level folder
([inventory](../inventory.md)). The directory is a [`.reg`](reg.md) entry
tree: sections are folders, kind-0 entries are files whose value is an
absolute file range.

## Layout

Little-endian u32s:

| Offset | Size | Field |
|---|---|---|
| 0x00 | 4 | signature `0x31415926` ("&YA1"), else fatal error 1 |
| 0x04 | 12 | root entry value and type: first child index, child count, type |
| 0x10 | 4 | directory offset D |
| 0x14 | 4 | N directory entries |
| 0x18 | … | file data |
| D | 32·N | entries, layout as in [reg](reg.md#layout) |

File entry: `+4` absolute offset of the data in the archive, `+8` byte
length, `+12` type 0, `+16` name. Section entry: `+4` first child index,
`+8` child count, `+12` type 1 (`0x11` = children sorted).

- CONFIRMED (`FUN_004e2040`, the opener): reads the signature, the root
  entry (+4, +8, +0xc), D (+0x10) and N (+0x14). It seeks to D unless
  root type bit 31 is set, then reads `32·N` bytes. Opened for writing,
  the table gets room for `N + N/4 + 10000` entries.
- CONFIRMED (all 10 archives, `tools/validate_res.py`): `D + 32·N` = file
  size, every entry is reached exactly once from the root, and the file
  ranges tile `0x18..D` with no gap or overlap. Entry `+0` is 0
  everywhere, and the only types are 0, 1 and `0x11`.
- INFERRED: offsets are absolute (data: the first file starts at 0x18).
  Bit 31 of the root type ("directory follows the header") never occurs.

## Lookup

CONFIRMED (`FUN_004e9046` → `FUN_004e9268` → `FUN_004e918e`). The archive
name is the stem of its file name (`FUN_004e3620`, at most 15 chars; a
longer name sets type flag `0x10000000`). A path's first component must
equal that stem, compared case-sensitively character by character. The
remaining components are resolved one level at a time with the
[reg](reg.md#lookup-fun_004e918esection-key) rules: in a **sorted**
section, `bsearch` + `strcmp` on the key cut to 15 chars; otherwise
`_strnicmp(key, name, 15)`. Every step must be a section with flag
`0x40000000` clear. The result is rejected (`FUN_004e9153`) if it has
`0x40000000` or `0x10` set. `0x40000000` never occurs in the data; it
probably means "deleted" (INFERRED). In all archives every walked path
resolves back to its own entry.

## Mounting

CONFIRMED (`FUN_00481186`, the mount sequence; `FUN_004e2901` mounts one
archive into the manager at `0x6682b0`). The order is `graphics.res`,
`main.res`, `patch.res`, `world.res`, `music.res`, `video.res`, then
`sfx.res`, `movies.res`, `scenario.res`, `speech.res`. The name of the
first is pasted together from `"grap" + "hi" + "cs.res"`, so the lone `cs.res`
string is not a separate archive. `-nomusic` is
checked between the two groups. After the mounts, `update.lst` is read
line by line (`FUN_004e2a1d`). INFERRED: `FUN_004e2932` mounts the
CD-ROM `Allods\` folder (CD volume label `ROM2`) as a loose-file directory.
The GOG install ships an empty `Allods\dummy.txt`.

Game paths name the archive first, e.g. `graphics\units\units.reg`,
`main\graphics\famehall\hall.bmp`, `main\id` (CONFIRMED, exe strings).

## Library: `a2res`

Standard library only, no dependency on `allods2`. `ResArchive(path)`
memory-maps one archive and parses the directory once; `read(path)` is a
`memoryview` slice of the map (no copy), `lookup` follows § Lookup, with
one table per section built on first use (O(1) per component),
`check()` is the validation above. `ResFS(install)` mounts the archives
in mount order and routes a path by its first component (compared
case-insensitively, see the open question). `DirFS(folder)` serves a loose
tree (case-insensitive like Windows), `ChainFS(a, b, …)` layers file
systems (first hit wins, listings merged), `OS` reads plain paths. Every
FS has `read`, `read_bytes`, `open` (seekable file over the same memory,
e.g. for PIL), `isfile`, `isdir`, `listdir`, `walk`, `files`, `glob`.
`allods2.common.game_fs()` is the default install's `ResFS`; every loader
takes `(path, fs)`. Mounting all ten archives takes ~0.15 s, and reading
every file (514 MB) ~0.35 s with ~3 MB of Python heap.

## Contents (GOG)

| Archive | Files | MB | Contents |
|---|---:|---:|---|
| graphics | 4,049 | 106.8 | sprites, palettes, bitmaps, terrain, fonts, `.reg` tables, town and world-map art ([graphics overview](graphics-overview.md)) |
| main | 104 | 6.6 | locale: menu/logo/famehall bitmaps, `text/*.txt` incl. `mission*.txt`, `id` = `english 0` ([fonts](fonts.md#character-codes)) |
| patch | 1 | <0.01 | `patch.txt` (network messages) |
| world | 5 | 0.16 | `data/` `data.bin`, `itemname.bin/.pkt`, `ai.reg`, `map.reg` |
| music | 21 | 140.1 | `b00…b16.wav`, `menu`, `map`, `chrgen`, `credit` (PCM 16-bit stereo 22,050 Hz) |
| video | 16 | 121.4 | `*/01.smk` + `.reg` fade scripts, `logos/nival|publisher` |
| sfx | 446 | 18.2 | sound effects (391 PCM, 53 MS ADPCM `wFormatTag` 2) |
| movies | 156 | 5.1 | shop item pictures `shop_druid/`, `shop_kaarg/`, `shopanim/` (`.bmp`) |
| scenario | 47 | 5.5 | campaign `10.alm … 110.alm` (46), `npc.reg` |
| speech | 1,133 | 109.9 | NPC voice `.wav` (986 MS ADPCM, 147 PCM) |

## Worked example

`world.res` starts `26 59 41 31 | 00 00 00 00 | 01 00 00 00 | 01 00 00 00 |
ac 70 02 00 | 06 00 00 00`: the root holds 1 child (entry 0), unsorted. The
directory of 6 entries is at 0x270ac = 159,916, and 159,916 + 6·32 =
160,108 is the file size. Entry 0 is section `data` (children 1–5). The
first file in it, `ai.reg`, sits at 0x18: an embedded `.reg` (it starts
`&YA1` again).

## Open questions

- The file reader and the writer: confirm in code that entry `+4` is
  absolute (data says so), and find what writes flags `0x40000000` /
  bit 31 (`FUN_004e2040` write mode, callers of `FUN_004e9153`).
- How the archive-name compare treats case. `FUN_004e9046` is
  case-sensitive, yet the exe also uses paths like `SFX\Add.wav`. Find
  where paths are lower-cased before the lookup, in the caller of the
  manager at `0x6682b0`.
- `update.lst` line format, and the `Allods\` directory mount
  (`FUN_004e2a1d`, `FUN_004e2963`).
