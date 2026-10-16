# Install inventory and binary triage

Survey of `samples/Allods2_en_251005/Allods2_en/` (English 1.30,
allods2.eu build; the requested `samples/game/` does not exist). `maps/`
shipped empty; on 2026-10-15 the 216 `.alm` maps of the allods2.eu maps
pack (`https://allods2.eu/files/maps_all.zip`) were added.
`python3 tools/inventory.py` → `out/inventory.csv` (5,299 rows: path,
size, extension, first 16 bytes; stays in gitignored `out/` because it
holds game bytes).

## 1. Totals

5,299 files, 176.2 MB (5,083 / 144.8 MB before the maps pack).

| Extension | Files | MB | Magic / first bytes | Kind |
|---|---:|---:|---|---|
| `.bmp` | 1,012 | 72.3 | "BM"; 949 24-bit, 63 8-bit, uncompressed | standard DIB, [bitmaps](formats/bitmaps.md) |
| `.alm` | 216 | 31.4 | "M7R\0" | **custom** map (maps pack); container §5.2 |
| `.wav` | 558 | 25.1 | `RIFF`, PCM mono 16-bit, 557 × 22,050 Hz, 1 × 44,100 Hz | standard |
| `.256` | 1,931 | 22.7 | 1,912 start `00 00 00 00` (palette); 8 are 0 bytes (4 cursors, 4 equipment) | **custom**, [sprites](formats/sprites.md) |
| `.png` | 536 | 5.4 | RGBA 8-bit (2 are 16-bit) | standard, allods2.eu patch, §4 |
| `.16a` | 782 | 4.8 | palette, no header | **custom**, [sprites](formats/sprites.md) |
| `.exe` / `.dll` / `.old` | 3 / 14 / 2 | 10.3 | `MZ` | PE32, §3 |
| `.pal` | 166 | 2.9 | 161 BMP-wrapped; 3 `human.pal` raw 16 KiB | [palettes](formats/palettes.md) |
| (none) | 3 | 0.4 | text | `data/version` (SHA-1 manifest), `data/version_id`, `data/main/id` |
| `.txt` | 44 | 0.4 | cp1251 text | custom conventions |
| `.reg` | 17 | 0.3 | "&YA1" = 0x31415926 | **custom**, [reg](formats/reg.md) |
| `.bin` | 2 | 0.15 | — | **custom**: `world/data/data.bin`, `itemname.bin` |
| `.ttf` | 1 | 0.05 | `00 01 00 00` | TrueType `font5` (a2mgr) |
| `.16` | 3 | 0.03 | — | **custom** 4-bit font sprites |
| `.pkt` | 1 | 0.01 | `00 00 00 bd` | **custom**: `world/data/itemname.pkt` |
| `.dat` | 6 | <0.01 | mixed | font metrics ×4, `famehall.dat`, `interface/data.dat` (text) |
| `.cfg` / `.log` | 1 / 1 | <0.01 | text | a2mgr config `allods2.cfg`, log |

## 2. Grouped by directory

| Directory | Files | MB | Contents |
|---|---:|---:|---|
| `./` | 21 | 7.57 | cfg, famehall.dat, 13 dll, 2 exe, 2 `.old`, log, patch30.txt |
| `data/` | 4 | 3.14 | `version`, `version_id`, copies of `allods2.exe`, `a2mgr.dll` (updater staging, §4) |
| `data/graphics/units/` | 346 | 18.26 | 180 `.256`, 164 `.pal`, `units.reg`, `material.reg` |
| `data/graphics/interface/` | 641 | 37.29 | 598 `.bmp`, 30 `.16a`, 12 `.256`, `data.dat` |
| `data/graphics/infowindow/` | 190 | 21.90 | `.bmp` portraits |
| `data/graphics/equipment/` | 1,620 | 8.24 | 1,104 `.256` + 516 `.png` per `{m,f}{fighter,mage}/{primary,secondary}` |
| `data/graphics/inventory/` | 697 | 3.36 | `.16a` item icons |
| `data/graphics/structures/` | 327 | 2.66 | 326 `.256`, `structures.reg` |
| `data/graphics/objects/` | 271 | 1.14 | 270 `.256`, `objects.reg` |
| `data/graphics/projectiles/` | 46 | 0.68 | `.16a`, `.256`, 2 `.pal`, `projectiles.reg` |
| `data/graphics/terrain/` | 53 | 0.71 | `tile{1..}-{00..15}.bmp`, `dirt.bmp` |
| `data/graphics/cursors/` | 46 | 0.16 | 23 `.16a`, 23 `.256` |
| `data/graphics/font1..5/` | 9 | 0.12 | glyphs + `.dat`, `font5.ttf` |
| `data/graphics/global.map/`, `backpack/` | 4 | 0.02 | sprites |
| `data/locale/{en,ru}/` | 77 | 9.17 | 21 `.txt` per language, localized `.bmp`/`.png` |
| `data/movies/{shop_druid,shop_kaarg,shopanim}/` | 156 | 5.08 | numbered `.bmp` frames |
| `data/sfx/**` | 559 | 25.1 | `.wav` + `sfx.reg` |
| `data/video/*/` | 8 | <0.01 | **only** `.reg` fade metadata; `.smk` absent |
| `data/world/data/` | 6 | 0.17 | `data.bin`, `itemname.bin`, `itemname.pkt`, `ai.reg`, `map.reg`, `itemex.txt` |
| `data/scenario/` | 1 | <0.01 | `npc.reg` |
| `data/main/` | 1 | <0.01 | `id` = `russian 1` |
| `maps/` | 216 | 31.42 | maps pack `.alm` |
| `screenshots/` | 0 | 0 | empty |

### Assets the exe references that this install does not ship

CONFIRMED as strings in `allods2.exe`, absent on disk:

- **`.res` archives** `cs`, `main`, `patch`, `world`, `music`, `video`,
  `movies`, `scenario`, `speech`, `sfx` `.res` (table `0x5fd13c`); a2mgr
  adds `locale.res`. Contents are loose under `data/` (INFERRED, §4).
- **Campaign missions** `%d.alm`, `World\Mission\scr_` (INFERRED inside
  `world.res`/`scenario.res`); the maps pack lacks them.
- **Music** `music\B00..B16.wav`, `menu.wav`, `map.wav`, `chrgen.wav`,
  `credit.wav` (a2mgr also tries `data\music`).
- **Video** `video\%s\%02d.smk`, `video\logos\nival.smk` (only `.reg`
  companions ship).
- **Characters/saves** `chr\%s\%u%u.a2c`, `game%d.sav` (written at run
  time).
- **Network packers** `Packer1.dat`, `Packer2.dat` (from `0x509ca3`, next
  to "CBufferManager::ReceiveData(). Error during unpacking buffer";
  INFERRED net compression tables).

A retail install (or other source of `.res` files and campaign missions)
is the main data gap.

## 3. Binary triage

REA (Ghidra 12.1.4) for allods2.exe, a2mgr.dll, scenario.dll;
objdump/strings and a local PE parser for the rest.

| File | sha256 (prefix) | Built | Toolchain | Packed? | Symbols |
|---|---|---|---|---|---|
| `allods2.exe` (= `data/allods2.exe`) | 2a8bdf9d… | 1999-07-28 | Linker 5.02, no Rich, static MFC + old iostream → **MSVC 5.0** (INFERRED) | no (`.text` entropy 6.25, EP 0x58f400 in `.text`) | none; PDB path `c:\a2server\a2client\Release\allods2.pdb`; no RTTI for game classes |
| `allods2.exe.old` | 8e798d3e… | same | same | no | differs from the exe in 55 bytes |
| `a2mgr.dll` (= `data/a2mgr.dll`) | 6bc57ebb… | 2020-11-01 | Linker 14.0, Rich prodids 255–261 build 24123/24215 → **VS 2015 Update 3** (INFERRED) | no | 127 exports **by ordinal only**; exe imports 113 |
| `scenario.dll` | 871f57c7… | 1999-03-29 | Linker 5.02, static MFC → MSVC 5.0 (INFERRED) | no | 18 named `Scenario*` exports; `Scenario.pdb` (NB10) not shipped |
| `engine32.dll` | c9b42526… | 2004-09-23 | VC6 | no | `InitEngine`/`DeinitEngine`; VERSIONINFO "Allods 2 DLL Helper" 1.10.00.1, Nival; resolution dialog (`/videoconfig`, 800×600…1280×1024) |
| `helper32.dll` | ac8bfd16… | 2005-02-07 | VC6 | no | `InitEngine`/`DeinitEngine`; "Allods Map Editor", 16-bit mode switch; map editor helper, not loaded by the game (INFERRED) |
| `smackw32.dll` | f9b2fdb5… | 1998-06-09 | RAD Game Tools | no | Smacker SDK, 61 exports |
| SDL, SDL_image, SDL_ttf, libpng, zlib, jpeg, libtiff, libfreetype | — | 2009–2012 | MinGW | no | not imported by the exe or a2mgr (gdiplus); launcher leftovers (INFERRED) |

**allods2.exe sections**: `.text` 0x401000 (1.83 MB, 9,418 functions),
`.rdata` 0x5d5000, `.data` 0x5f8000, `.idata` 0x6db000, `.rsrc` 0x6df000,
non-standard **`.anet` 0x6e2000** (RWX, 16 KiB, ~360 non-zero bytes:
hand-written cdecl stubs and `hat.allods.net`; INFERRED community-patch
code cave).

**Imports by purpose**: graphics DDRAW `DirectDrawCreate`, GDI32 (87,
mostly MFC); sound DSOUND #1, MSACM32 `acmStream*`, WINMM `timeGetTime`;
video smackw32 (16: `SmackOpen/DoFrame/NextFrame/ToBuffer/Blit*/
SoundUseDirectSound…`); network WSOCK32 (23 by ordinal), WININET
`InternetOpen(Url)A/ReadFile/CloseHandle`; file I/O KERNEL32
`CreateFileA/ReadFile/SetFilePointer/CreateFileMappingA/MapViewOfFile/
FindFirstFileA…`, `GetPrivateProfile*`; registry ADVAPI32 `Reg*` (key
`SOFTWARE\1C\Allods2.eu`: `CDSPEED`, `RESOLUTION`, `INSTALLDIR`, read in
`FUN_0048626d`); UI USER32 (166), COMCTL32, comdlg32, SHELL32, WINSPOOL,
ole32 (MFC); CD check `GetVolumeInformationA` (CONFIRMED called in
`FUN_0048626d`), `GetDriveTypeA`, `GetLogicalDriveStringsA`; a2mgr.dll
ordinals 1–127 (113), which mount resources: `FUN_0048626d` calls
`Ordinal_108("cs.res")`, `Ordinal_108("main.res")` (CONFIRMED).

**File-name strings (allods2.exe)**:
- Archives: `*.res` above; `Data_updated.lst`, `dbg_alt.txt`,
  `dbg_grp.txt`, `passbase.txt`, `server.cfg`, `error.log`, `pkt.log`,
  `c:\structures.ini`.
- Graphics: `graphics\<category>\...\sprites.256|spritesb.256|sprites.16a`,
  `\palette%d`, `graphics\units\humans\human.pal`,
  `graphics\terrain[.3d]\tile%d-%d.bmp`, `graphics\interface\**.bmp`,
  `main\graphics\**`, `graphics\fontN\fontN`, `%s%d.256`,
  `Allods%04d.bmp` (screenshots).
- World: `World\Data\Data.bin`, `ai.reg`, `map.reg`,
  `world\data\itemname.bin|.pkt`; build-time sources `Armors.txt`,
  `Weapons.txt`, `Shields.txt`, `Magic.txt`, `Magic Items.txt`,
  `Materials.txt|.reg`, `Items.reg`, `Spells.txt|.reg`,
  `Shapes.txt|.reg`, `Buildings.txt|.reg`, `Units.txt`, `Humans.txt`, with
  "Parsing .txt files", ".reg processed", "Writing new .bin file": `Data.bin`
  is compiled from them when present (INFERRED).
- Text: `main\text\*.txt`, `mission%d.txt`, `Docs\%d.txt` (a2mgr remaps to
  `locale\<lang>\*.txt`).
- Sound: `SFX\**.wav`, `sfx\characters\%s\{attack,move,select,swarm}\%d.wav`,
  `sfx\sfx.reg`, `music\*.wav`.
- Maps/saves: `%d.alm`, `1.alm`, `\*.alm`, `World\Mission\scr_`,
  `%schr\%s\%u%u.a2c`, `game%d.sav`, `famehall.dat`, `lockflag`.
- Video: `video\%s\%02d.smk`, `video\logos\{nival,publisher}.smk`.

**scenario.dll**: `ScenarioNewGame/Load/Save/GetVar/SetVar/TalkTo/
EnterInn/EnterShop/EnterLocation/…` = single-player campaign state
machine. `ScenarioLoad` (`0x10003686`, CONFIRMED) reads via vtable `Read`
(+0x3c): a 0x1000-byte variable block; 4 × 4 records of 0x14 bytes; u32
N + N list entries; u32 cursor.

## 4. a2mgr.dll (allods2.eu client patch)

- **Updater** (CONFIRMED strings): fetches `/allods/version` and
  `/allods/version_id` from `api.allods2.eu`, posts `action=check_version`
  with exe/dll checksums; keeps `allods2.exe.old`, `a2mgr.dll.old`;
  stages updates as `data/allods2.exe`, `data/a2mgr.dll`.
- **`data/version`** = manifest `<path relative to data/> <sha1>`, 5,075
  lines, append-only; 5,072 match disk (SHA-1 checked over every listed
  file), the other 3 are older exe/dll hashes listed several times. Format
  CONFIRMED by data; last entry wins INFERRED. `data/version_id` = 40-hex
  SHA-1 of the manifest set (INFERRED).
- **Loose-file override** (INFERRED from strings `data\`, `data\patch\`,
  `locale.res`, `world\data\*`, `data\%s%d.256`, `data\%s%d.png`):
  Ordinal_108 and friends map `.res` paths onto `data/`. `%s%d.png` lets
  PNG replace `.256` (CONFIRMED for the paper doll, [png](formats/png.md));
  the 516 equipment PNG IDs never overlap `.256` IDs: post-release items.
- Also GDI+ PNG/TTF UI, screenshot upload, chat (`hat.allods2.eu`), log
  `allods2.log`.

## 5. Custom formats: what is known

### 5.1 `.reg` registry (`&YA1`)

See [formats/reg.md](formats/reg.md) (CONFIRMED; supersedes the survey).

### 5.2 `.alm` maps (`M7R\0`)

216 files, 32,596–386,478 bytes, 210 distinct (6 byte-identical copies).
Container CONFIRMED by data (walks to EOF on all 216); field meanings
INFERRED unless marked.

Header (20 bytes): `M7R\0`; u32 header size 0x14; u32 always
`width·height·4 + 72`; u32 section count, always 13; u32 always 0x640.
Then 13 sections, each a 20-byte header `{u32 tag, u32 header size 0x14,
u32 data size, u32 id, u32 ?}` + data. Tag 7 in 212 files, 5 in 4
(`aeq_maraslavin_1_104R`, `sc_ac_necro_1_2`, `sc_acq_zwilling_1_1`,
`sc_acq_zwilling_1_11`; perhaps a version). **Quirk**: section 0 is
followed by 16 bytes beyond its declared 644. IDs always in order 0, 1, 2,
3, 5, 11, 4, 9, 8, 6, 7, 10, 12.

| ID | Size | Observations |
|---|---|---|
| 0 | 644 (+16) | general info: u32 width, height at data +0x00/+0x04 (file 0x28/0x2c): 144² (101), 80² (46), 256² (38), 208² (13), non-square 48×112 … 256×144; at +0x08 f32 0x3f490fda (π/4) |
| 1 | w·h·2 | u16 terrain tiles ("Tiles block", CONFIRMED by error string in `FUN_0056a69a`; [terrain](formats/terrain.md)) |
| 2 | w·h | u8 heights ("Altitudes block", CONFIRMED); copied verbatim to `+0x10`, read **signed** ([terrain](formats/terrain.md#heights)) |
| 3 | w·h | u8 object layer: copied to runtime `+0x14` inside an 8-cell border (`FUN_004abc1c`), byte = object index + 1 (CONFIRMED, [animation §1.7](formats/animation.md#17-map-placement-of-objects)) |
| 4–12 | variable | records (structures, units, players, triggers, …); 8, 10, 11 can be empty |

### 5.3 Others (all INFERRED)

| File | Observations |
|---|---|
| `fontN.dat` | decoded, [fonts](formats/fonts.md) |
| `world/data/data.bin` (153,528 B) | starts `00 00 07 00 00 00 06 "Common"`: length-prefixed names (`Common`, `Uncommon`, `Rare`, …) + f64 multipliers (1.0, 0.2, …); compiled item/material/class/spell/unit database, the most depended-on data |
| `world/data/itemname.bin` (1,402 B) | u16 pairs (`02 01 03 01 …`), like (id, class) keys |
| `world/data/itemname.pkt` (10,629 B) | `00 00 00 bd 02 00 00 7c 29 …`: packed item-name records, repeated `0d 0X 0e 0X 0c` tags |
| `world/data/itemex.txt` | rule text: `ignore material Bone type not Staff …` |
| `famehall.dat` (228 B) | u32 count?, records `{u32 len, name\0, u32 score, …}` (`Diamond`, `Glazz`, `Gella`): hall of fame |
| `graphics/interface/data.dat` | ASCII `1c 30.03.99\r\n`: version/date stamp |
| `data/locale/*/*.txt` | cp1251; one string per line (`main.txt`, `itemname.txt`) or `#key` sections with `<part=N>` (`town.txt`, `quest.txt`, `globalmap.txt`) |
| `video/*/NN.reg` | `Common/Fading1…`, `startx/starty/nFadings/startframe/endframe/startfade/endfade` |

## 6. Plan: custom formats to reverse, in order

Small bounded formats first, dependencies before dependants. Done:
sprites, palettes, BMP, `.reg` (step 1), font metrics (step 2), the
`human.pal` "remap" (= shade tables + player palettes).

3. **Locale `.txt` conventions**: line-indexed vs `#key`/`<part>`, cp1251;
   needed by UI, items, quests.
4. **`world/data/data.bin`**: core rules database; depends on nothing,
   almost everything depends on it. Reader via the `Data.bin` string at
   `0x6072d4`.
5. **`itemname.bin` / `.pkt` / `itemex.txt`**: item IDs → names/sprites;
   need the data.bin item model.
6. **`famehall.dat`**: tiny, self-contained, low priority.
7. **`.res` container**: needed for a retail install; probably `&YA1`
   (check `FUN_004edd03`/`FUN_004eae80`); needs a sample file.
8. **`.alm` maps**: largest format (terrain, objects, units, triggers);
   needs data.bin, `.reg` metadata, terrain. Container mapped (§5.2);
   strings `%d.alm` (xref `0x492b02`), "Map version too new". Sections 0–3
   could precede data.bin; only 4–12 need its IDs.
9. **`.a2c` characters / `game*.sav` saves** (incl. the scenario.dll chunk,
   §3): need data.bin and `.alm`; a2c path built at `0x4f30b9`.

Not planned as formats: `.smk` (standard Smacker, absent);
`Packer1/2.dat` and the network protocol (network layer); `data/version`
(understood, §4).
