# Saves: `.a2c` characters, `famehall.dat`, `game%d.sav`

Code: `allods2/formats/saves.py` (readers, writers, byte layer), `engine/party.py` (`place_party(record=)`, `apply_record`).
Tests: `tests/test_saves.py`, `tests/test_engine_party.py`. Addresses refer to the GOG `allods2.exe`
(sha256 in [README](README.md)); `FUN_` names are Ghidra's.

**Evidence.** The install holds no `.a2c` and no `.sav` (a fresh install has no characters or saves); only
`famehall.dat` (228 B, decoded exactly: 10 entries) is a real file. The `.a2c` and `.sav` layouts below are read from the code
(reader and writer both decompiled, the fields cross-checked between them), and the readers / writers are tested on files built
from that layout. Everything marked CONFIRMED is a routine checked in the exe; no byte of a real `.a2c` / `.sav` was compared.

## 1. Where the hero lives (summary, CONFIRMED unless noted)

* **Single player keeps the party in memory.** The campaign maps hold no hero of the human ([triggers §9](../engine/triggers.md#9-the-party-at-map-start-fun_004f2c83)).
  The hero is created once (new game: the character screen sends message `0x48` with strength / dexterity / mind / spirit / school /
  flags, handler `FUN_004f6af6` -> `FUN_004f254b`, [triggers §9.3](../engine/triggers.md#93-a-fresh-character-fun_004f254bplayer-str-dex-mind-spirit-school-flags-confirmed))
  and stays in the player's unit list (`player+0x24`, main hero `player+0x38`) across the whole campaign. The server object is not
  rebuilt between missions: the end-of-mission routine `FUN_004ebd5f` (§4) cleans the map and keeps the humans' units.
* **A saved game** (`game%d.sav`, §6) serialises the whole server (players, creatures with their items, map state, script state) plus the
  client's `.reg` tree and the Scenario.dll state (the 1000+ script variables travel there).
* **The `.a2c` character file** (§2) is the *network* hero record: a client sends it in the join message `0xbe` (`FUN_0041c6b5`), the
  server builds the hero from it (`FUN_004ea6ab`). In single player the character screen (`FUN_0049183e`, taken when `client+0x30 & 1`
  or the game kind `[client+0x5d8] == 2`) sends message `0x48` instead: **an existing `.a2c` only supplies the four attributes, the
  school and the class flags in single player** (its items, XP, spells and gold are not used; INFERRED consequence: the point budget
  of `FUN_004f254b` can reject an advanced character's attributes, then all four become 25).
* The client rewrites the file while playing (writer `FUN_004edbaf` called from the creation screen `0x4915cd`, `0x491078`, `0x491f1c`, `0x4920ee`, `0x4921be` and
  twice from the message pump `FUN_0040d9b2`, one chunk set per call; triggers INFERRED: the server messages and inventory window events that carry the data). The server-side writer
  `FUN_004e9e97` (hero -> file) cannot run in this build: it needs `[server+0x1a8] == 0 && [server+0x74] != 0`, but the starter
  `FUN_004eb356` stores `+0x74 = (mode < 2)` and `+0x1a8 = (+0x74 != 0)`, and nothing else writes `+0x1a8` of the server. The
  loader `FUN_004ea472` (path `%schr\%s\%u%u.a2c`) has no caller at all. The earlier note "writer `0x4eab4a`" was an
  address inside `FUN_004ea6ab` (the skill recompute), not a writer.

## 2. The byte layer (CONFIRMED)

| Name | Routine | Rule |
|---|---|---|
| checksum | `FUN_004edacd` | `h = 0; for b: h = 2h + b` (u32). Only the last 32 bytes matter: a byte shifted out after 32 steps leaves no trace, so the first bytes of a long chunk are not protected (quirk, tested) |
| stream cipher | `FUN_004edb23` (own inverse) | key = the chunk's 16-bit flags; `r = key | key << 16`; byte `i ^= (r >> 16) & 0xff`; `r <<= 1` (u32); after byte `i & 15 == 15`: `r |= key` |
| RLE (bytes) | `FUN_00421080` / `FUN_0053c140` | `u32 n` units, then ops: `0x80 | c` + one unit = run of `c` (1..0x7f); `c < 0x80` + `c` units = literal. Encoder: run needs two equal units (cap 0x7f), literal stops before the next pair (cap 0x7e) and takes the last unit at the end; the exe peeks one unit past the buffer (here: never equal) |
| RLE (words) | `FUN_0053a330` / `FUN_00539e70` | the same with 16-bit units (run op = 3 bytes) |

## 3. The `.a2c` character file

### 3.1 Container (`FUN_004ee7cb` reader, `FUN_004edbaf` writer)

`u32 0x04507989`, then chunks to the end of the file (the exe requires the file to be `< 0x10000` bytes, `FUN_004ea472`). A chunk:

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | tag |
| 4 | 4 | length of the stored payload (the reader ignores it for tag `0x41392521`) |
| 8 | 2 | 0 |
| 0xa | 2 | flags = `rand(0x7fff)`: the cipher key (and the junk-byte mask of the stats chunk) |
| 0xc | 4 | checksum of the **plain** payload |

An unknown tag or a bad checksum makes the reader fail (the hero is not built). The writer (`FUN_004edbaf(path, id, stats, blob, equip, pack, hotkeys, hotkey_len)`)
reads the existing file first and **replaces only the chunks it is given**, so the client updates one chunk at a time (each caller passes a different subset).

| Tag | Content | Stored as | Writer (client / server) | Reader |
|---|---|---|---|---|
| `0xAAAAAAAA` | identity, 0x34 bytes (§3.2) | cipher | `FUN_004915cd` (creation, all chunks), `FUN_00491f1c` (with stats; called by the message pump `FUN_0040d9b2` and the shell `FUN_004852d8`-area `0x484bae`), `FUN_00491078` (identity alone), `FUN_004e9e97` (dead) | `FUN_004ea6ab`, `FUN_004904c5` (character list) |
| `0x41392521` | stats, 0x34 bytes (§3.3) | per-field transforms + junk bytes | same | same |
| `0x55555555` | client settings, `0xa00` bytes | byte RLE, cipher | `FUN_004921be` (`client+0x3f70`; pump sites `0x40ee51`, `0x40ee9b`) | `FUN_004ea6ab` copies it to `player+0x44` |
| `0xDE0DE0DE` | the 12 equipped items (§3.4) | cipher | the message pump `FUN_0040d9b2` at `0x4122d7` (the equipment packet), creation (`0x685298`) | `FUN_004ea6ab` |
| `0x3A5A3A5A` | the backpack (§3.4) | cipher | the message pump at `0x411aa2` (items of `client+0x4974`) | `FUN_004ea6ab` |
| `0x40A40A40` | 9 hotkey records, variable | cipher | `FUN_004920ee` (inventory window events `0x4a3e3d`, `0x4c745f`), creation | `FUN_004904c5` (`FUN_0041e0c2` x 9) |

The exe's builders write them in the order identity, stats, settings, equipment, pack, hotkeys (server) — the reader accepts any order.
`FUN_004ea6ab` fails (returns null) without the identity, the stats and the equipment chunk.

### 3.2 Identity chunk `0xAAAAAAAA` (0x34 bytes, CONFIRMED)

| Offset | Size | Field | Source / use |
|---|---|---|---|
| 0 | 8 | two u32 ids; the file is `%u%u.a2c` (`0x5fc360`) | player `+0x10`; client `this+8` |
| 8 | 4 | extra u32 | client `this+0x64` |
| 0xc | 32 | name, NUL padded; `name|title`: the character list splits at `|` (`FUN_004904c5`) | player `+0x18` (CString) |
| 0x2c | 1 | class flags: `0x80` female (`FUN_0053a5c0`), `0x40` mage (`FUN_0053a5a0`); `& 0xc0` picks `Start_MF / MM / FF / FM` (0, 0x40, 0x80, 0xc0) | hero |
| 0x2d | 1 | portrait / face -> hero `+0x4b` | hero `+0x4b` |
| 0x2e | 1 | best school 1..5 -> hero `+0x23c` | hero `+0x23c` |
| 0x2f | 1 | server writes 4; the character screen keeps its byte (`this+0x30`); bit 0 set = "send the creation message `0x48`" in `FUN_0049183e` (INFERRED meaning: not yet created in a game) | |
| 0x30 | 1 | difficulty (player `+0xa44`; client `this+0x88`) | |
| 0x31 | 3 | stack garbage | |

### 3.3 Stats chunk `0x41392521` (0x34 bytes, CONFIRMED)

Thirteen words read in order; before field `i` a junk byte (a `rand(0xff)`) is present when the flags bit is set. Stored value -> plain value
(`v0..` are the plain values; all u32 wrap):

| Offset | Size | Field | Flag bit | Plain value from stored `s` | Player / hero field |
|---|---|---|---|---|---|
| 0x00 | 4 | monster kills | 0x1 | `v0 = s ^ 0x01529251` | player `+0xa48` |
| 0x04 | 4 | player kills | 0x2 | `v1 = s + 0x13141516 + 5·v0` | player `+0xa4c` |
| 0x08 | 4 | statistic | 0x4 | `v2 = s + 0xabcdef + 7·v1` | player `+0xa58` |
| 0x0c | 4 | hero deaths | 0x8 | `v3 = s ^ 0x17ff12aa` | player `+0xa54` |
| 0x10 | 4 | **gold** | 0x10 | `v4 = s - 0x21524542 + 3·v0` | player `+0x3c` |
| 0x14 | 1 | body (base) | 0x20 | `v5 = s + 0x11·(v4 & 0xff) + 0x13·(v0 & 0xff)` | hero `+0x84` (the server stores `+0x84 - (s8)+0xd4`: no effect bonus) |
| 0x15 | 1 | reaction | 0x40 | `v6 = s + 3·v5` | `+0x86` (`-` byte `+0xd5`) |
| 0x16 | 1 | mind | 0x80 | `v7 = s + v5 + 5·v6` | `+0x88` (`+0xd6`) |
| 0x17 | 1 | spirit | 0x100 | `v8 = s + 7·v5 + 9·v7` | `+0x8a` (`+0xd7`) |
| 0x18 | 4 | spell book mask (bit n = spell n, 1..29) | 0x4000 | `s - 0x10121974` | hero `+0x140` (`FUN_0051c4a4`); applied only to a hero with max mana > 0 |
| 0x1c | 4 | selected special-spell slot | 0x2000 | raw | brain `+0x78` of `+0x1c4` (mages only) |
| 0x20 + 4i | 4 | XP pool of school 1+i (i = 0..4) | 0x200 << i | `p0 = s ^ 0xdadedade`; `p_i = s - 0x771·p_{i-1}` for i > 0 | hero `+0x240 + 4i` |

The flags bit `0x2000` is shared by the word `+0x1c` and pool 4, so that bit writes two junk bytes while the header length (`0x34 + popcount(flags)`,
counted by the writer over all 16 bits) counts one; the reader consumes by field, not by length. Plain checksum = over the 0x34 plain bytes.
A hero's skills are not stored: skill `k` (1..5) = `level_of(pool_k)` (`FUN_00512870`), `+0x116` copies them, `+0x130` is the pool sum.

### 3.4 Item chunks (CONFIRMED)

The inventory message (net type `0x76`, packet ctor `FUN_0050c7f5`) is stored from packet offset `+0xa`: 3 uninitialised bytes, `u16 count` (`+0xd`:
the number of items in the pack; 0 in the equipment packet), `u16` (`+0xf`, 0), `u16 length` (`+0x11` = bytes of the item stream), then the items
(chunk length = `length + 9`). The equipment chunk always carries 12 items, read in order into the slots (`FUN_004ea6ab` reads exactly 12): the
weapon `hero+0x74`, the second hand `+0x78`, then `+0x214..+0x238` (slots 3..12; the fighter/mage slot names of [items §5](../data/items.md#5-modifiers-effects-and-the-stats-group)
are INFERRED to follow the same 1..12 order). An empty slot is `00 00 80` (code 0). The pack chunk is read until `length`.

Item (`FUN_005241bf` writer, `FUN_004ed5f5` reader): `u16 code` ([items §3](../data/items.md): `material << 12 | class << 8 | quality << 5 | index`; class 1 weapon,
2 shield, `0xe` special (key `code & 0xff`), else armour), `u8 f`:

| `f` | Meaning |
|---|---|
| `f & 0x80` | stack of `f & 0x3f` items, nothing follows (a stack needs `count < 0x40`) |
| `f & 0x20` | a single item with modifiers: `u32 price` (item `+0x1c`), then records; `f & 0xf` = record units still to read |
| neither | stack of `u16 count` |
| `f & 0x40` | written when the item was flagged new (`item+8`), ignored by the reader; `f & 0x10` marks a castSpell record |

Records (kind byte = the data.bin stat id): kind 41 castSpell `41 spell 0x32 charges` (2 units), kinds 44-48 `k min k spread` (2 units), any other kind `k value`
(1 unit); kind 1 is not written. The reader decodes the item (class by the code), applies the records, and flags the owner `+0x1bc = 1` when the modifiers
exceed 1.5 x the capacity ([items §12](../data/items.md#12-trade-hero-window-and-wire-flags)).

### 3.5 Hotkey chunk `0x40A40A40` and settings `0x55555555`

Nine records `u16 a, u16 b, u32 n, n bytes` (`FUN_0041df0c` write, `FUN_0041df74` read; client `+0x8c + 12 i` while playing, `+0x4dc + 12 i` in
the save code); INFERRED: the nine quick-use slots. The settings blob is the client's `0xa00` bytes at `client+0x3f70`, copied to `player+0x44`. **CONFIRMED content: the viewer's knowledge table**, one byte per unit type id (server id `+0x14c`, 0..0x9ff), the hero's kill count of that type capped at 14; the info panel's detail level is `byte >> 1` ([ui-layout 11.1](../engine/ui-layout.md#detail-level-and-the-knowledge-table), writers `FUN_0052b459` / `FUN_00505582`).
The character screen creates a file with gold 1000, the chosen attributes / pools / spell mask / slot and these two (`FUN_004915cd`).

### 3.6 Building a hero from a record (`FUN_004ea6ab`, CONFIRMED order)

1. Parse the chunks (`FUN_004ee7cb`); fail unless identity, stats and equipment are present.
2. Create the template by `flags & 0xc0`: `Start_MF` / `MM` / `FF` / `FM` (`FUN_005143e4(name, 1, 0)` = the constructor `FUN_005145d1`; its tail at **`0x514920`** is the
   loop that equips the data.bin equipment strings — *not* a load routine; the loader replaces that equipment below).
3. Attributes `+0x84..+0x8a` = the four bytes; portrait `+0x4b`; pools `+0x240..` = the five words; best school `+0x23c`; skills `+0xa8 + 2k` and `+0x116 + 2k` =
   `level_of(pool_k)`; `+0x130` = pool sum; recompute (vtable `+0x58`).
4. If max mana > 0 (a mage): flag `+0x4c |= 6`, a new spell book, spells added for mask bits 1..29, brain byte `+0x78` = the slot.
5. The hero's name `+0x80` := the player's name; player `+0x3c` = gold, `+0xa48 / +0xa4c / +0xa54 / +0xa58` = the four statistics words; the settings blob -> `player+0x44`.
6. Equipment: clear the template's (vtable `+0x4c`; the weapon / second item go back to the pack), a new empty pack, equip the 12 decoded items (vtable `+0x44`), insert the
   pack items (`FUN_00529ac2`).
7. New brain objects `+0x1c0` / `+0x1c4`, cleared orders `+0x40/+0x44/+0x5c/+0x64/+0x68`, recompute, **HP := max, mana := max** (`+0x94 = +0x96`, `+0x9a = +0x9c`),
   dying latch `+0x13c := 0`, state bit `+0x4c &= ~8`, `+0x1a4 := player+0x30` (the player slot).

`engine/party.py` `apply_record` follows steps 2-7: template, attributes, pools -> skills, school, spell mask, gold and statistics, and step 6 through the equip
methods of [items §15](../data/items.md#15-equip-use-pack-and-ground-items-confirmed-engine-sim-gearpy) (`gear.put_and_file` per chunk item in record order, then the pack items;
the maximum HP / mana, the speed and the combat numbers include the equipment, HP and mana start at the maxima). Item `i` of the equipment chunk is creature slot `i + 1`
(0 weapon, 1 second hand, 2..11 the armour table slots 3..12; an armour piece goes to the slot of its class, not necessarily slot `i + 1`). Without an item table
(synthetic worlds) the items are only stored.

## 4. Carry-over between campaign maps (single player, CONFIRMED)

The humans' units stay in the player's list; the server object stays. End of a mission (`FUN_004852d8` `0x486ae1` / `0x486c03`: after the result, the mission time is recorded
(`FUN_00493b40`, tick / 16), the client calls the server's **`FUN_004ebd5f`**, then `ScenarioLeaveLocation` returns to the town / world map):

* for every human with a main hero: per-player upkeep (`FUN_004f3cad`, `FUN_004f3d14`, `FUN_0052f8e2`: not decoded); a main hero flagged dead (`+0x13c`) is rebuilt by
  `FUN_004f254b(player, 0,0,0,0,0)` only in the network modes (`+0x74 != 0`);
* the map objects are freed (`DAT_0066832c` path finder, `DAT_00670e48` map);
* the list at `unit+0x20` of every unit of every human (`0x4ec159`-`0x4ec1b7`) is emptied: each element gets `+0x42 := 1`, `+0x44 := 0`, is detached via its vtable `+0x38(unit)` and removed from the list (INFERRED: the applied spell effects, the same list the item serialiser walks for modifiers);
* for each human with a name: the ready flag `player+0x41 := 0` (so `FUN_004f2c83` places the party again on the next map); each unit whose type `+0xe` is outside `0x21..0x3f`
  (summons, monsters) is deleted (`FUN_005161eb`); each human unit (heroes, companions) keeps its level, items and XP and gets **HP := max, mana := max, `+0x13c := 0`**,
  orders / targets (`+0x40, +0x44, +0x5c, +0x64, +0x68`) cleared and the stand-state recompute `FUN_005105e6`; computer players' lists are cleared;
* server `+0xd4` (scenario id) `:= 0`, loaded flag `+0x94 := 0`, both tick counters `:= 0`; then message `0xb8` and the flush.

Gold (`player+0x3c`), the statistics words, the spell book and the script state are untouched, so they carry over by staying in memory. The Scenario.dll variable array
(`ScenarioGetVar/SetVar`, [triggers](../engine/triggers.md#2-compilation-at-map-start-fun_00562745)) is a global of the DLL, not reset by this routine.
`ScenarioNewGame` (`0x100033be`, called at `0x4862ba`) initialises it for a new campaign: all zero except Var(0x300) = 10 ([triggers §11](../engine/triggers.md#11-the-end-of-the-mission-scenariodll-and-the-client-flow)).

## 5. `famehall.dat` (CONFIRMED, the install's file decodes exactly)

Loader `FUN_004a91d5` (file `famehall.dat`, `0x5f31f4`), writer `FUN_004a90c9` (`0x4825c4`, opened `0x1001`); the object is at `client+0x598`. `u32 count` (0 = the default hall,
`FUN_004a9730`), then per entry `u32 length`, the name with its NUL (`length` bytes), `u32 a, u32 b, u32 c`. The install's 10 entries are sorted by `a` descending (70006,
65817, ...) with `b = c = 0`: INFERRED `a` = score, `b`, `c` unknown. Size = `4 + sum(16 + length)` = 228.

## 6. The saved game `game%d.sav`

Slot names (`FUN_0043ece0` and the list code `FUN_0043dc54`): `game%04ld.sav`-style zero padding (`game000%ld`, `game00%ld`, `game0%ld`, `game%ld`), the list scans `\game*.sav`; the
literals `game9998.sav` / `game9999.sav` and `game0000.sav` (read by the server start when `server+0x1ac != 0`, `0x4eb992`). The save UI
formats `game%d.sav` (`0x48850d`) as `9999 - slot`. **CONFIRMED** (full caller audit in [ui-layout 11.4](../engine/ui-layout.md#114-in-game-menu-pause-freeze)): `game9999.sav` is the automatic save written by the mission entry `FUN_0048c8a3(0)` (message `0x442`, description patch `0x37` "Restart last mission"); `game9998.sav` has no sender (description patch `0x5f` "Abort mission and return to town"); the Save dialog hides both, the Load dialog lists them. Single player never writes a `.a2c` (all writers gated by `+0x5d8 != 2`).

### 6.1 Container (CONFIRMED, `FUN_004e9816` writer, `FUN_004e9b95` reader)

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | `0x26677342` ("Invalid save file" otherwise) |
| 4 | 4 | end of the server block (patched after the write; the loader skips it; the client reader seeks to it) |
| 8 | 4 | version `0x0BAD0002` ("Outdated save file" if lower; a higher one loads) |
| 0xc | 4 | length of the compressed block |
| 0x10 | n | word RLE (§2) of the server stream, `u32` = number of 16-bit words (the stream is padded to an even length) |
| end | | multiplayer saves: a 0x100-byte "Server Multiplayer save file." header (`+0x74 != 0`), out of scope |
| end | | the client tail (§6.3), written by `FUN_0048dc9f`: opened read-write, seek to the end |

Before writing, the server removes from the group list (`player+0x28`) of every human player (`+0x2c == 0`) the entries for which `FUN_0044fc20` returns 0 (cleanup pass `0x4e9886`-`0x4e990f`; INFERRED: empty groups).

### 6.2 The server stream (`FUN_004ec732`, the same routine saves and loads; MFC archive, little endian)

| Order | Content | Server field |
|---|---|---|
| 1 | u32 | `+4` **tick counter** |
| 2 | u32 | `+0` **16-tick block counter** |
| 3 | CString (length byte, `0xff` + u16 above 254) | `+0x90` map / scenario name |
| 4 | 11 x u32 | `+0x174, +0x17c, +0x180, +0x184, +0x188, +0x18c, +0x190, +0x194, +0x1a0, +0x19c, +0x198` (options; meaning unknown) |
| 5 | u32 | `+0xd4` mission / scenario id (non-zero builds the `Scenario\<n>` name) |
| 6 | u32 | `+0xd8` difficulty (applied on load only when 1..3) |
| 7 | `FUN_0052d16b`, then vtable `[0]` of the object at `[server+0x7c]+0xc` | player / object tables (INFERRED: the player list with the hero units) |
| 8 | u8 loaded flag (`+0x94` set), when 1: `FUN_0052c3da`, `FUN_0052d5cb`, `FUN_00550008` (map state), `FUN_0057468d` (script state: 1000 values, 1000 fired flags, counters, [triggers §1](../engine/triggers.md)), `FUN_0052d5b2`, `FUN_0053bbd0` | |
| 9 | u32 `0xbadface1` twice (the loader reads and ignores them) | |
| 10 | `FUN_0057a951` | |

**Tick counters after a load (CONFIRMED).** The first two words are `server+4` (tick) then `server+0` (block). The new-game branch of `FUN_004eb715` (`this+0x1ac == 0`) loads the
map and zeroes both (`0x4eba47`); the load branch (`this+0x1ac != 0`) calls `FUN_004e9b95` and skips the zeroing, so **both counters resume exactly as saved**, then `+0x94 := 1`.
The loader rebuilds the player lists, calls `FUN_0052b22a` for every unit without bit `0x8` of `+0x4c`, creates the map object (`FUN_00534ad4`, `Scenario\...` name), the path
finder (`FUN_00568c9a`), recompiles the script (`FUN_00562745(map, 0)` without reset) and restores the client-visible state. The creatures', groups' and map's own serialisers
are not decoded (open questions).

### 6.3 The client tail (CONFIRMED, `FUN_0048dc9f` writes, `FUN_0048c2e9` reads from `[offset 4] + 0x100`)

| Order | Content | Routine |
|---|---|---|
| 1 | 0x100 bytes slot description (`client+0x148`) | |
| 2 | a `.reg` tree in the [reg](reg.md) layout (`FUN_004e4bb0` + setters, `FUN_004e4a86`) | keys below |
| 3 | mission list: `u32 n`, `n x (u32, u32)`, `u32 +4`, `u32 +8` of the object at `client+0x598` | `FUN_004a8f96` / `FUN_004a9032` |
| 4 | Scenario.dll block (`ScenarioSave`, ordinal 12, `0x10003585`): 0x1000 bytes of the variable array (1024 x i32, DLL `0x10036028`), 0x140 bytes of the shop table (4 towns x 4 blocks x 20 bytes), `u32 n`, `n x {u32 index, u32 type (1 mission, 2 town), 16-byte name}`, `u32` position of the current location in the list | `ScenarioLoad` `0x10003686` |
| 5 | nine hotkey records (§3.5) from `client+0x4dc` | `FUN_0041df0c` / `FUN_0041df74` |

`.reg` keys written (`FUN_004e7018` int, `FUN_004e6e2d` string, `FUN_004e7cc2` int array, `FUN_004e7b2a` id array): `CurrentState/InBattle` (client `+0x404 & 1`), `Character/Name`
(client `+0x460`, 32 bytes), `GameOptions/{Wimpy, ShowHP, FlyingHP, Formation, Speed, ShowTimeFlow}`, `View/{X, Y}`, `SpellBook/{IsOpen, Pressed, Shortcuts}`, `Objects/Selection`,
`Objects/Group<n>` (n = 0..9, only the non-empty ones), `Inventory/IsOpen`; only when in battle (`InBattle` = 1): `Projectiles/FreeIndex`, `Projectiles/IDs`, one section `Prj<id>` per
projectile with `x, y, z, picture, dir, phase, lastaction, action, actiondir, actiontarget, actionx, actiony, actionz, actionphase, actionsegments, actionspell`, and `Fog/FirstState` +
`Fog/Data` (run lengths of the fog bit 15 over the map cells). The loader reads `CurrentState/InBattle`, `Character/Name` (default "No name") and `GameOptions/*`.

Gold and the 1000 script variables: gold is `player+0x3c` inside the server stream (players), the script variables are in the Scenario.dll block (tail item 4) and in the script state
(`FUN_0057468d`, `values`).

## 7. Code

`allods2.formats.saves`: `parse_a2c / build_a2c / load_a2c` (`Character`, `Identity`, `Stats`, `ItemPacket`, `Item`, `encode_item / decode_item`), `parse_famehall / build_famehall`,
`parse_save` / `SaveGame.pack` (`ServerHead`, `ClientTail`, `ScenarioState`), the byte layer (`checksum`, `xor_stream`, `rle_encode / rle_decode`). `Character.layout` keeps the header
flags and junk bytes, so a parsed `.a2c` rebuilds byte for byte. The server stream beyond its head is kept as raw bytes (`ServerHead.rest`).

## Open questions

* The server stream's object serialisers: `FUN_0052d16b`, vtable `[0]` of `[server+0x7c]+0xc`, `FUN_0052c3da`, `FUN_0052d5cb`, `FUN_00550008`, `FUN_0052d5b2`, `FUN_0053bbd0`,
  `FUN_0057a951` (creatures with items and effects, groups, map dynamic layer) and the 11 option words of §6.2 (start `FUN_004ec732`).
* The `0x2f` flag byte (network only: every client-pump rewrite of the file is gated by `+0x5d8 != 2`, so never in single player).
* Whether a single-player continue ever uses a stored character's items (VERIFY IN GAME: pick an advanced character for a new campaign and compare attributes).
* `famehall.dat` fields `b`, `c` and when the hall is written (`FUN_004825c4` caller; the score formula); the mission list (`FUN_004a8f96`) record meaning.
* Who writes `game0000.sav` (read at server start; `FUN_004f515d` case 7 -> `FUN_004e9816` at `0x4f723d` writes a stream, no file name seen) and the field order of the date in the save list.
