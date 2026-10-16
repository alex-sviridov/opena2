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

- CONFIRMED (`FUN_004e2040`, the opener): opens the file read-only
  (`CFile` mode `0x40`, share-deny-none; the mode word `+0x3c` is set to 0
  just before), reads the signature, the root entry (+4, +8, +0xc), D
  (+0x10) and N (+0x14), seeks to D unless root type bit 31 is set
  (then the directory follows the header), and reads `32·N` bytes. The
  writable-table branch (room for `N + N/4 + 10000` entries) is
  unreachable from this opener.
- CONFIRMED (`.res` stream, vtable `0x5d06a8`): Open `FUN_004e2fc3` asks
  the manager (`FUN_004e2b5d` → `FUN_004e2445`) for {archive file, entry
  `+4`, entry `+8`}; Read `FUN_004e329c` seeks the archive file to
  `base + pos` and clamps to the length. So `+4` is an absolute file
  offset.
- CONFIRMED (all 10 archives, `tools/validate_res.py`): `D + 32·N` = file
  size, every entry is reached exactly once from the root, and the file
  ranges tile `0x18..D` with no gap or overlap. Entry `+0` is 0
  everywhere, and the only types are 0, 1 and `0x11`. Bit 31 of the root
  type never occurs.

Entry flags (high bits of `+12`, set in memory, never in the shipped
files): `0x40000000` replaced or removed (`FUN_004e92f5`, used when a
key is re-added by `FUN_004e8ed0`; recursive for sections; freed blob
bytes go to the header `+0x14` count of [reg](reg.md#layout));
`0x20000000` overridden by a loose file (§ Mounting, `update.lst`);
`0x10000000` name longer than 15 characters (`FUN_004e3620`).

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
`0x40000000` or `0x10` set. In all archives every walked path resolves
back to its own entry.

Case: CONFIRMED (`FUN_004e26c9`). The resource manager lower-cases every
path, A–Z only (CRT `tolower`), before the lookup above and before
mounting an archive, so the stems are lower case and `SFX\Add.wav` finds
`sfx\add.wav`. The switch `DAT_005f7870` starts at 1, and its toggle
`FUN_004e26a0` has no callers. Every name in the 10 archives is lower case
(CONFIRMED, all archives), so a lowered path meets the case-sensitive
`strcmp` of sorted sections without loss. `ResFS` does the same
(`game_lower`).

## Mounting

CONFIRMED (`FUN_00481186`, the mount sequence; `FUN_004e2901` lower-cases
the name and mounts one archive into the manager at `0x6682b0`). The order is
`graphics.res`, `main.res`, `patch.res`, `world.res`, `music.res`,
`video.res`, then `sfx.res`, `movies.res`, `scenario.res`,
`speech.res`. The name of the first is pasted together from `"grap" + "hi"
+ "cs.res"`, so the lone `cs.res` string is not a separate archive.
`-nomusic` is checked between the two groups.

The manager keeps a list of **loose directories** (CONFIRMED;
`FUN_004e2963` adds one, fatal error 3 unless `FUN_004e34d0` reports a
directory or a drive root `X:\`):

1. the current directory at start-up (the manager's static constructor
   `FUN_004e24f6`, before `WinMain`);
2. the temp directory (`GetTempPathA`, trailing `\` cut);
3. `<CD>\Allods`, when `HKLM\SOFTWARE\Rage of Mages 2` value `CD`
   exists (the volume label is compared with `ROM2`, but the result is
   ignored). The GOG install ships an empty `Allods\dummy.txt`.

An archive is opened as `<dir>\<name>` from the first directory where the
open succeeds (`FUN_004e274a`; none → fatal error 2). A file lookup
(`FUN_004e2b5d`) asks each archive in mount order; the first hit wins. If no
archive has the path, or the hit carries `0x20000000`, it tries
`<dir>\<path>` in each loose directory in order (`CFile` open errors 2
and 3, not found, move on; any other is fatal).

`update.lst` (CONFIRMED, `FUN_004e2a1d`): read after the mounts through
the same loose lookup. Each line, with CR/LF cut, is a game path; reading
stops at the first line whose first character is not printable
(`isprint`). `FUN_004e2af9` sets `0x20000000` on that path's entry in the
first archive that has it, so the loose copy replaces it. The GOG install
has no `update.lst`.

`World\Mission\scr_<map>.reg` mission scripts are opened the same way
(`FUN_005756a1`); it adds the current directory to the loose list again
on every call.

Game paths name the archive first, e.g. `graphics\units\units.reg`,
`main\graphics\famehall\hall.bmp`, `main\id` (CONFIRMED, exe strings).

## Library: `a2res`

Standard library only, no dependency on `allods2`. `ResArchive(path)`
memory-maps one archive and parses the directory once; `read(path)` is a
`memoryview` slice of the map (no copy), `lookup` follows § Lookup, with
one table per section built on first use (O(1) per component),
`check()` is the validation above. `ResFS(install)` mounts the archives
in mount order, lower-cases the path (§ Lookup) and routes it by its
first component. `DirFS(folder)` serves a loose
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

- None. (The CD mount needs the original CD and is not reproduced.)
