# Install inventory and binary triage

Survey of `samples/allods2_en_gog/`: "Rage of Mages II: Necromancer" from
GOG (game id 1459856152, launched as `allods2.exe -1024`; README dated May
28, 1999). Single-player work only: the campaign, towns and world map;
the multiplayer client/server parts of the exe are out of scope.
`python tools/inventory.py` → `out/inventory.csv` (6,094 rows: every loose
file and every archive member as `<stem>.res:<path>`; size, extension,
first 16 bytes; stays in gitignored `out/` because it holds game bytes).

## 1. Totals

**Loose files** (116): `allods2.exe`, `Scenario.dll`, `smackw32.dll`,
`ROM2 Map Editor.exe` with its HTML `Help/` (38 `.gif`, 17 `.jpg`, 13
`.htm`), the ten `.res` archives (499 MB), 11 multiplayer `.alm` maps
(not used), `famehall.dat` (228 B), `server.cfg` (commented server
settings), `Music.ini` (17 track names), `Description Checks/Instants.ini`
(map editor), GOG files (`goggame-*.dll/.info/.hashdb/.ico`, `unins000.*`,
`GameuxInstallHelper.dll`, `webcache.zip`), Windows `SHLWAPI.DLL`,
`WININET.DLL`, and an empty CD-overlay folder `Allods/dummy.txt`
([res § Mounting](formats/res.md#mounting)).

**Archive members** (5,978 files, 513.7 MB; per archive:
[res § Contents](formats/res.md#contents-gog)):

| Extension | Files | MB | Magic / first bytes | Kind |
|---|---:|---:|---|---|
| `.wav` | 1,599 | 268.1 | `RIFF`; PCM 16-bit and MS ADPCM (`wFormatTag` 2), 22,050 Hz (3 × 44,100) | standard: music, sfx, speech |
| `.smk` | 8 | 121.4 | `SMK2` | standard Smacker video |
| `.bmp` | 1,515 | 85.5 | "BM", uncompressed 24-bit and 8-bit | standard DIB, [bitmaps](formats/bitmaps.md) |
| `.256` | 1,929 | 22.2 | 1,915 with palette; 8 are 0 bytes (4 cursors, 4 equipment) | **custom**, [sprites](formats/sprites.md) |
| `.16a` | 623 | 7.2 | palette, no header | **custom**, [sprites](formats/sprites.md) |
| `.alm` | 46 | 5.6 | "M7R\0" | **custom** campaign maps (`scenario/`), §5.2 |
| `.pal` | 159 | 2.8 | 156 BMP-wrapped; 3 `human.pal` raw 16 KiB | [palettes](formats/palettes.md) |
| `.txt` | 68 | 0.5 | cp1251 text | `main/text/`, `patch/patch.txt`, §5.3 |
| `.reg` | 17 | 0.3 | "&YA1" = 0x31415926 | **custom**, [reg](formats/reg.md) |
| `.bin` / `.pkt` / `.pat` | 2 / 1 / 1 | 0.2 | — | `world/data/data.bin` ([databin](formats/databin.md)), `itemname.bin/.pkt`, `main/text/itemname.pat` |
| `.16` | 3 | 0.04 | — | **custom** 4-bit font sprites |
| `.dat` | 5 | <0.01 | — | font metrics ×4, `graphics/interface/data.dat` (`0\r\n`) |
| `.exe` | 1 | 0.02 | `MZ` | `main/text/namemake.exe` (tool leftover) |
| (none) | 1 | <0.01 | text | `main/id` = `english 0` ([fonts](formats/fonts.md#the-remap-switch-dat_006227fc)) |

## 2. Grouped by folder

| Folder | Files | Contents |
|---|---:|---|
| `graphics/interface/` | 1,162 | UI and town screens (`town`, `town_druid`, `town_kaarg`, `townbirds`, `docs`, inn, shops), `.bmp`, `.16a`, `.256` |
| `graphics/equipment/` | 1,104 | `.256` paper-doll layers per `{m,f}{fighter,mage}/{primary,secondary}` ([paperdoll](formats/paperdoll.md)) |
| `graphics/inventory/` | 491 | `.16a` item icons |
| `graphics/units/` | 337 | `.256` sprites, `.pal`, `units.reg`, `material.reg` |
| `graphics/structures/`, `objects/` | 327, 271 | `.256` + `b.256`, `structures.reg`, `objects.reg` |
| `graphics/infowindow/` | 185 | `.bmp` portraits |
| `graphics/terrain/` | 53 | `tile{1..}-{00..15}.bmp`, `dirt.bmp` |
| `graphics/projectiles/`, `cursors/` | 46, 46 | sprites, `projectiles.reg`, 2 `.pal` |
| `graphics/global.map/` | 17 | world map: Flag, Flag1, Cross, FlagOnMap, MissionFlag, YourFlag, scrolls, paths |
| `main/` | 104 | locale: `text/*.txt` (incl. 46 `mission%d.txt`), menu/logo/famehall bitmaps, `id` |
| `movies/` | 156 | shop pictures `shop_druid/`, `shop_kaarg/`, `shopanim/` |
| `sfx/`, `speech/`, `music/` | 446, 1,133, 21 | sound effects (+ `sfx.reg`), NPC voices, music |
| `video/` | 16 | `*/01.smk` + `.reg` fade scripts, `logos/` |
| `world/data/` | 5 | `data.bin`, `itemname.bin/.pkt`, `ai.reg`, `map.reg` |
| `scenario/` | 47 | campaign `10.alm … 110.alm`, `npc.reg` |

## 3. Binary triage

REA (Ghidra 12.1.4) for `allods2.exe`; objdump/strings for the rest.

| File | sha256 (prefix) | Built | Toolchain | Notes |
|---|---|---|---|---|
| `allods2.exe` | 0eaa9673… | 1999-04-29 | Linker 5.02, static MFC → MSVC 5.0 (INFERRED) | not packed; PDB path `S:\Peter\AddOn\AddOn___\rom2.pdb` (not shipped); version string `1.01` in the server report URL |
| `Scenario.dll` | d23a9361… | 1999-03-29 | Linker 5.02 | 18 named `Scenario*` exports: campaign state machine (`ScenarioNewGame/Load/Save/GetVar/SetVar/TalkTo/EnterInn/EnterShop/EnterLocation/…`) |
| `smackw32.dll` | 21be2e65… | 1998-06-09 | RAD Game Tools | Smacker SDK |
| `ROM2 Map Editor.exe` | b891d259… | 1999-04-13 | Linker 6.0 | map editor (not analysed) |

**allods2.exe sections**: `.text` 0x401000 (1.79 MB), `.rdata` 0x5cb000,
`.data` 0x5ee000, `.idata` 0x6ce000, `.rsrc` 0x6d2000.

**Imports by purpose**: graphics DDRAW; sound DSOUND, MSACM32; time WINMM
`timeGetTime` (the game clock, [animation §3.1](formats/animation.md));
video smackw32; network WSOCK32, WININET (multiplayer, not covered); file
I/O KERNEL32; registry ADVAPI32 (key `SOFTWARE\Rage of Mages 2`: CD
speed, resolution, install dir); UI USER32 (`CharToOemA`/`OemToCharA`,
[fonts](formats/fonts.md#locale-text-chartooema)), COMCTL32, comdlg32,
SHELL32, WINSPOOL, ole32 (MFC).

**File-name strings** (CONFIRMED, `strings`):
- Archives: the ten `.res` names ([res](formats/res.md#mounting)),
  `update.lst`.
- Graphics: `graphics\<category>\...\sprites.256|spritesb.256|sprites.16a`,
  `graphics\units\humans\human.pal`, `graphics\terrain\tile%d-%d.bmp`,
  `graphics\Global.Map\*`, `main\graphics\**`, `graphics\fontN\fontN`,
  `%s%d.256`.
- Text: `main\text\*.txt`, `patch\patch.txt`, `mission%d`, `docs\%d`.
- Sound: `SFX\**.wav`, `music\B00…B16.wav`, `menu.wav`, `map.wav`.
- Campaign and saves: `%d.alm` (`0x48ca44`), `World\Mission\scr_`,
  `Scenario\`, `%schr\%s\%u%u.a2c`, `chr\*.*`, `lockflag`, `game%d.sav`,
  `\game*.sav`, `famehall.dat`.
- Video: `video\%s\%02d.smk`, `video\logos\{nival,publisher}.smk`.

## 4. Single-player scope

The exe holds client and server; single player runs both in one process
(the clock steps the server once per client tick,
[animation §3.1](formats/animation.md)). Covered: everything the campaign
reaches (maps in `scenario.res`, towns, world map, saves, `Scenario.dll`).
Not covered: network transport (WSOCK32/WININET, `server.cfg`, the 11
root `.alm` maps, chat, diplomacy).

## 5. Custom formats: what is known

### 5.1 `.reg` registry (`&YA1`)

See [formats/reg.md](formats/reg.md) (CONFIRMED).

### 5.2 `.alm` maps (`M7R\0`)

Header, terrain and the container are specified in [formats/map.md](formats/map.md);
this section keeps the byte accounting.

46 campaign maps (`scenario/<n>.alm`, 41,060–306,948 bytes, all
distinct). Container CONFIRMED by data (walks to EOF on all 46,
`allods2/alm.py`); field meanings INFERRED unless marked.

Header (20 bytes): `M7R\0`; u32 header size 0x14; u32 always
`width·height·4 + 72`; u32 section count, always 13; u32 1300 (41 maps)
or 1600 (5). Then 13 sections, each a 20-byte header `{u32 tag, u32
header size 0x14, u32 data size, u32 id, u32 ?}` + data. Tag 7 in 37
maps, 5 in 9 (perhaps a version). **Quirk**: section 0 is followed by 16
bytes beyond its declared 644. IDs always in order 0, 1, 2, 3, 5, 11, 4,
9, 8, 6, 7, 10, 12.

| ID | Size | Observations |
|---|---|---|
| 0 | 644 (+16) | General block, [map § Section 0](formats/map.md#section-0-general-block-644-bytes--16); first fields: u32 width, height at data +0x00/+0x04 (file 0x28/0x2c): 144² (32), 80² (13), 256² (1); at +0x08 f32 0x3f490fda (π/4) |
| 1 | w·h·2 | u16 terrain tiles ("Tiles block", CONFIRMED by the error string "Tiles block not found" in `FUN_005606aa`; [terrain](formats/terrain.md)) |
| 2 | w·h | u8 heights ("Altitudes block", CONFIRMED); copied verbatim to `+0x10`, read **signed** ([terrain](formats/terrain.md#heights)) |
| 3 | w·h | u8 object layer: copied to runtime `+0x14` inside an 8-cell border, byte = object index + 1 (CONFIRMED, [animation §1.7](formats/animation.md#17-map-placement-of-objects)) |
| 4 | 20 · n (+ 8 per sized bridge) | structures, [map § Part 4](formats/map.md#part-4-objects) (CONFIRMED, tiles exactly on all 46) |
| 5–12 | variable | records (players, units, triggers, …); 10 always empty, 11 empty in 36 maps, 8 in 21 |

### 5.3 Others (all INFERRED)

| File | Observations |
|---|---|
| `world/data/itemname.bin` (982 B) | starts `ab f8 ae f7 ad f7 02 15 …`: item ids → names/sprites |
| `world/data/itemname.pkt` (7,763 B) | `00 00 00 eb 01 00 00 4a 1e …`: packed item-name records |
| `famehall.dat` (228 B, loose) | u32 count?, records `{u32 len, name\0, u32 score, …}`: hall of fame |
| `main/text/*.txt` | cp1251; one string per line (`main.txt`, `itemname.txt`) or `#key` sections (`town.txt` `#tips1`, `quest.txt`, `globalmap.txt`, `mission%d.txt` `#briefing`, `#failure2`, `===` comments) |
| `video/*/NN.reg` | `Common/Fading1…`, `startx/starty/nFadings/startframe/endframe/startfade/endfade` |

## 6. Plan: custom formats to reverse, in order

Small bounded formats first, dependencies before dependants. Done:
`.res`, sprites, palettes, BMP, `.reg`, fonts, the `human.pal` "remap"
(= shade tables + player palettes), `data.bin` container and columns.

1. **`main/text` conventions**: line-indexed vs `#key` sections; needed by
   UI, items, quests, mission briefings.
2. **`itemname.bin` / `.pkt`**: item IDs → names/sprites; need the
   data.bin item model.
3. **`.alm` sections 0, 4–12**: structures, units, players, triggers of
   the 46 campaign maps; the server reader `FUN_00534ad4` switches on the
   section id. "Map version too new (update loader!)".
4. **Campaign flow**: `Scenario.dll` exports, `World\Mission\scr_`
   scripts, mission texts.
5. **`.a2c` characters / `game*.sav` saves** (incl. the `Scenario.dll`
   chunk; INFERRED, not yet checked in this DLL: `ScenarioLoad` reads a
   0x1000-byte variable block, 4 × 4 records of 0x14 bytes, u32 N + N
   list entries, u32 cursor): need data.bin and `.alm`.
6. **`famehall.dat`**: tiny, self-contained, low priority.

Not planned as formats: `.smk` (standard Smacker), `.wav` (standard
RIFF), the network protocol.
