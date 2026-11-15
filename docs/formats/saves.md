# Saves: `.a2c` characters, `famehall.dat`, `game%d.sav`

Code: `allods2/formats/saves.py` (readers, writers, byte layer), `engine/party.py` (`place_party(record=)`, `apply_record`).
Tests: `tests/test_saves.py`, `tests/test_saves_l10b.py`, `tests/test_engine_party.py`. Addresses refer to the GOG `allods2.exe`
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
(`FUN_00493b40`, tick / 16), the client calls the server's **`FUN_004ebd5f`**, then `ScenarioLeaveLocation` and the recruit, [triggers §11](../engine/triggers.md#11-the-end-of-the-mission-scenariodll-and-the-client-flow)).
`FUN_004ebd5f(server)` in order (asm `0x4ebd5f`-`0x4ec3xx`; "human" = a player with `+0x2c == 0`, "has a hero" = `+0x38 != 0`):

1. `FUN_004ed298`: housekeeping only (INFERRED: removes a temp file whose name is the CString `0x627158` when it is non-empty; logs a line in the lobby mode `[0x68f628]+0x4e0 == 3`); `server+0x8c := 1`.
2. **Per-player upkeep** for every human with a main hero, keyed by the hero's position record `hero+0x10` (a cell): `FUN_004f3cad` = the structure standing on that cell looked up in
   the structure table `server+0x7c` (`FUN_0052c129`) and accepted when it is of the class with RTTI `0x5f90e0`, `FUN_004f3d14` the same for the class `0x5f91b8`
   (`__RTDynamicCast`; `FUN_004f3cad` returns `0x68ff30` at once when `server+0x1a4 != 0`, the network flag). For the first class (the shop: its `+0x6c` object holds the four 28-byte
   stock blocks of [items §11](../data/items.md)) `FUN_005226f5(hero)` / `FUN_00522936(hero)` end the hero's open shop session; for the second class (the quest-giver of [items §14](../data/items.md#14-quests-and-the-item-upgrade-message-0x38))
   `FUN_0052f8e2(hero, -1)` removes the hero from its visitor lists (`+0xa4` / `+0xa8`) and, in network games only (`server+0x74 != 0`), sends `FUN_005103ae`. **No persistent state**: a session cleanup for a hero
   that ends the mission standing on a shop / quest structure (INFERRED purpose; the removals themselves CONFIRMED). Nothing the campaign needs.
3. A main hero flagged dead (`+0x13c`) is rebuilt by `FUN_004f254b(player, 0,0,0,0,0)` and placed (`FUN_004f2c83`) **only in the network modes** (`server+0x74 != 0`). In single player the death of the main hero is the defeat ([combat §12.3a](../engine/combat.md#123a-hero-death-message-0xb4-the-dialog-and-the-game-confirmed-unless-marked-allods2exe-sha256-in-formatsreadmemd)), so the branch never runs.
4. `FUN_004f03e9`: frees the object at `server+8` (INFERRED: the pending message list). The map objects are freed: `DAT_0066832c` (the path finder / world manager) and `DAT_00670e48` (the map) are deleted and set to 0.
5. The list at `unit+0x20` of every unit of every human (`0x4ec159`-`0x4ec1b7`) is emptied: each element gets `+0x42 := 1`, `+0x44 := 0`, is detached via its vtable `+0x38(unit)` and removed from the list
   (INFERRED: the applied spell effects, the list the item serialiser walks for modifiers, so **timed effects end with the mission**).
6. For each human **with a name** (`FUN_00439e10(player+0x18) == 0`, INFERRED = the name is non-empty; any other player's unit list is cleared instead, `FUN_0053b010`): the ready flag `player+0x41 := 0` (so `FUN_004f2c83` places the party
   again on the next map), then for **every unit of the player's list**:
   * unit type `+0xe` outside `0x21..0x3f` -> deleted (`FUN_005161eb`): summons, monsters, **and the hired mercenaries** (their `+0xe` is the template's own type id 15 / 5 / 23 / 100-102 / 26, [triggers §11.3](../engine/triggers.md#113-recruit-routines));
   * else (the heroes and companions, `+0xe` = `0x21..0x24`): **HP := max** (`+0x94 := +0x96`), **mana := max** (`+0x9a := +0x9c`), the death flag `+0x13c := 0`, orders / targets `+0x40, +0x44, +0x5c, +0x64, +0x68` := 0, and the
     stand-state reset **`FUN_005105e6(unit)`** (below). Level, XP, skills, items (equipped and pack), spell book, name, `+0x14c` hero number and the group stay as they are.
7. `server+0xb8 := 0`, `FUN_00437b90()` (a one-line wrapper, INFERRED a string reset), `+0xd4 := 0` (scenario id), `+0x94 := 0` (loaded flag), `+0 := 0`, `+4 := 0` (both tick counters); when `server+0x74 == 0` `FUN_0053b450(0)` (a one-word setter,
   `obj+0x20 := arg`; INFERRED the current-map slot); message `0xb8` (`FUN_005052f8`) and the flush `FUN_00504bb7`.

**`FUN_005105e6(unit)`, the stand-state reset (CONFIRMED `0x5105e6`-`0x5106d1`)**: `FUN_00510745(unit)` (cancels a pending spell, [combat §12.1](../engine/combat.md)); then, when `+0x136 == 0` and `+0x68` holds a
spell-effect object (kind byte `0xe`), that object and the carrier `+0x64` are deleted and both fields cleared; finally always `+0x64 := 0`, `+0x58 := 0`, **`+0x136 := 1`**, state `+0x54 := 0`, order `+0x50 := 0`. Net effect: the unit stands
idle with no action, no pending cast and no target.

**Dead units.** A unit whose HP fell to <= -10 has already been removed from the owner's list at its removal tick ([combat §12.3](../engine/combat.md)): **a dead companion is gone for good** (no resurrection, no replacement except the recruit rules of
triggers §11.3). A unit that is dying but still in the list when the mission ends (HP <= 0, flag `+0x13c == 1`, not yet removed) **is revived** by step 6: full HP / mana, flag cleared (CONFIRMED code; the situation needs the end of the mission within `D` ticks of a death,
[combat §12.1](../engine/combat.md)). The hero-death script variables are a separate mechanism ([triggers §11.4](../engine/triggers.md#114-hero-death-variables)).

**What persists after the call (the L1 carry-over contract).** Per human player: the unit list (hero numbers `+0x14c`, level / XP / skills / pools / items / spells of each unit with `+0xe` in `0x21..0x3f`), `player+0x38` main hero, gold `player+0x3c`,
the statistics words, the spell book; the Scenario.dll variable array. Reset: HP / mana / death flag / orders / effects of the units, `player+0x41`. Gone: every other unit of the list. 
The Scenario.dll variable array ([triggers §2](../engine/triggers.md#2-compilation-at-map-start-fun_00562745)) is a global of the DLL, not reset by this routine; `ScenarioNewGame` (`0x100033be`, called at `0x4862ba`) initialises it for a new campaign: all zero except Var(0x300) = 10.

## 5. `famehall.dat` (CONFIRMED, the install's file decodes exactly)

Loader `FUN_004a91d5` (file `famehall.dat`, `0x5f31f4`), writer `FUN_004a90c9` (`0x4825c4`, opened `0x1001`); the object is at `client+0x598`. `u32 count` (0 = the default hall,
`FUN_004a9730`), then per entry `u32 length`, the name with its NUL (`length` bytes), `u32 a, u32 b, u32 c`. The install's 10 entries are sorted by `a` descending (70006,
65817, ...) with `b = c = 0`: INFERRED `a` = score, `b`, `c` unknown. Size = `4 + sum(16 + length)` = 228.

## 6. The saved game `game%d.sav`

Slot names (`FUN_0043ece0` and the list code `FUN_0043dc54`): `game%04ld.sav`-style zero padding (`game000%ld`, `game00%ld`, `game0%ld`, `game%ld`), the list scans `\game*.sav`; the
literals `game9998.sav` / `game9999.sav` and `game0000.sav` (read by the server start when `server+0x1ac != 0`, `0x4eb992`). The save UI
formats `game%d.sav` (`0x48850d`) as `9999 - slot`. **CONFIRMED** (full caller audit in [ui-layout 11.4](../engine/ui-layout.md#114-in-game-menu-pause-freeze)): `game9999.sav` is the automatic save written by the mission entry `FUN_0048c8a3(0)` (message `0x442`, description patch `0x37` "Restart last mission"); `game9998.sav` is written by message `0x442` with wParam 1, posted by the three town scenes' leave click right before `0x42d` (`0x4cad5d`, `0x4d0758`, `0x4d3058`, [town-worldmap 1](../engine/town-worldmap.md); description patch `0x5f` "Abort mission and return to town"); the Save dialog hides both, the Load dialog lists them. Single player never writes a `.a2c` (all writers gated by `+0x5d8 != 2`).

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

### 6.4 MFC archive layer of the server stream (CONFIRMED unless noted)

Read / write direction is chosen by `FUN_00401db0` (true = storing: `archive+0x14 & 1 == 0`); every serialiser below is one routine with a store branch and a load branch, and the two
branches agree field by field in everything decoded here. Primitives (little endian): `FUN_0053ba30/0053baf0` u32 write / read, `FUN_0053ba50/0053bb10` u8, `FUN_00543170/005431e0` u16
(`FUN_00543190/00543200` the signed variants, same width), `FUN_005aa981/005aa873` raw bytes (`ptr, n`), `FUN_005aa47d/005aa4f7` CString (§6.2 item 3).

* **Counted lists** (`FUN_00546610` players, `FUN_005462b0` buildings, `FUN_00546850` spell effects, `FUN_00546750` class `0x5f91a0`, `FUN_0053bbd0` virtual casters, `FUN_00546360` a group's units,
  `FUN_00546410` a unit's sub-list): `u32 count`, then `count` MFC object pointers (`FUN_005ac36a` store, `FUN_005ac3e9(CRuntimeClass*)` load, a class-checked read). The load side clears the list first.
* **Object pointer = MFC `WriteObject`** (`FUN_005ac36a`): `u16 0` null; a pointer already written: `u16 index` (`index <= 0x7ffe`) or `u16 0x7fff` + `u32 index`; a new object: the class tag (new
  class `u16 0xffff, u16 schema, u16 nameLen, name`; known class `u16 0x8000 | classIndex`; MFC standard) and then the object's `Serialize` (vtable slot 2, `+8`). The running map counter is at
  `archive+0x30`; the object's index is stored in a per-object slot (`FUN_005a120b`) and the counter increments after the class tag and before `Serialize` (CONFIRMED order in `FUN_005ac36a`;
  INFERRED: the first index is 1, as MFC). A re-implementation must reproduce this tagging; indices are in write order, classes and objects share one counter.
* **Raw pointers as keys.** Several serialisers write `this` (or a stored pointer) as a plain u32; the loader maps the old value to the new object with a global map (`SetAt(old, this)`, initialised
  with `SetAt(0,0)` in `FUN_0052d16b`) and fixes stored pointers with `FUN_00546700` / `FUN_005465d0` (lookup, 0 when missing). The values are therefore arbitrary but must be unique and
  consistent: **any unique non-zero ids work** (INFERRED for the write side, CONFIRMED for the read side's use as keys).
* **XOR-protected words**: `FUN_00546740(x) = x ^ 0x5c073f4d` is applied to player `+0x3c` (gold, §6.1) and `+0xa48` on both directions.
* CRuntimeClass table (record = `name, objectSize, schema, create, base, next`): `Player` `0x5f82b8` (size `0xa80`, schema 1, base CObject); the game-object base `0x5f8240` (size `0x3c`, create `0x50d3df`);
  `Unit` `0x5f8270` (name pointer `0x5fb6e8`, size `0x208`, create `0x50db74`, base `0x5f8240`); `Building` `0x5f9098` (`0x6c`), `SpellEffect` `0x5f8310` (`0x48`),
  `Sack` `0x5f91a0` (`0x50`), `Item` `0x5f9140` (`0x54`), `Effect` `0x5f8f20` (`0x48`), `Spell` `0x5f8e68`, `VirtualCaster` `0x5f8258` (`0x44`); `Humanoid` `0x5f8288` derives from `Unit` (6.10): all schema 1, base `0x5f8240`.
* Vtables (slot 2 = `Serialize`): `Player` `0x5d1030` (`0x52d1c5`), `Unit` `0x5d0eb0` (`0x52c618`), `Building` `0x5d1268`, `SpellEffect` `0x5d1060`, `VirtualCaster` `0x5d0e78`, `Sack` `0x5d1530`, `Item` `0x5d1388`, `Effect` `0x5d1178`.

### 6.5 Server stream, annotated (`FUN_004ec732`, store branch order; CONFIRMED)

After the CString and the options, the **thirteen u32 words** are, in this exact order: `+0x174, +0x17c, +0x180, +0x184, +0x188, +0x18c, +0x190, +0x194, +0x1a0, +0x19c, +0x198` (the "11 option
words", read with `FUN_0053baf0` in the same order), then `+0xd4` and `+0xd8` (items 5, 6). Load applies `+0xd8` only for 1..3 (`0 < v < 4`). The loader first calls `FUN_004f8cc9` (resets state). Meaning of the
11 option words: not decoded (open question). After items 5, 6:

| Step | Routine | Writes |
|---|---|---|
| a | `FUN_0052d16b` | `u32 server+0x20`; then the **player list** (`FUN_00546610`, §6.6) |
| b | vtable `[0]` of `[server+0x7c]+0xc` (store) / `[1]` on load | a polymorphic object; not decoded |
| c | `u8` loaded flag | 0 = town save, the stream continues at `FUN_0057a951` (item e); 1 = mission |
| d | flag 1: `FUN_0052c3da` = building list (`FUN_005462b0`, `Building`); `FUN_0052d5cb` = spell-effect list (`FUN_00546850`, `SpellEffect`); `FUN_00550008` map layer; `FUN_0057468d` script state (only `if DAT_0066832c == 0` on load, always on store); `FUN_0052d5b2` = **Sack** list (`FUN_00546750`, ground sacks / items on the map, INFERRED); `FUN_0053bbd0` = virtual-caster list | |
| e | `u32 0xbadface1` x 2 (written; the loader reads two u32 and ignores them), then `FUN_0057a951` | **`400` raw bytes** at the end of the stream (`FUN_005aa981(this, 400)`); `this` is the object left in ECX (INFERRED: the random generator state; not confirmed which object) |

Order on load differs only in object creation: the loader walks every player's groups' units calling `FUN_0052b22a` for units without bit `0x8` of `+0x4c`, creates the building list / spell-effect list holders
(`[server+0x7c]+0` size `0x1c` `FUN_0052bf45`, `+4` size `0x20` `FUN_0052c1e9`, `+8` size `0x1c` `FUN_0053ab10`), the map (`FUN_00534ad4`, size `0x3b8`) and the map object `FUN_0054d2d9` (size `0xa4570`, `DAT_00670e48`),
the path finder only when `DAT_0066832c == 0` (before the script state), recompiles the script and calls `FUN_004a6430(1)`. For a town save (flag 0) the loader zeroes `+0x40, +0x44, +0x5c` of every unit.

### 6.6 Player (`FUN_0052d1c5`, CONFIRMED order; field = player object offset)

| Order | Type | Field | Meaning |
|---|---|---|---|
| 1 | CString | `+0x18` | player name |
| 2 | u16 | `+4` | |
| 3 | u32 | `+8` | |
| 4 | 8 bytes | `+0x10` | |
| 5 | u8 | `+0xa44` | |
| 6 | u32 | `+0x2c` | |
| 7 | u16 | `+0x30` (load copies to `+0x32`) | |
| 8 | u32 | `+0x3c` XOR `0x5c073f4d` | gold ([§6.3](#63-the-client-tail-confirmed-fun_0048dc9f-writes-fun_0048c2e9-reads-from-offset-4--0x100)) |
| 9, 10 | u8, u8 | `+0x40`, `+0x41` | |
| 11 | u32 | `+0xa48` XOR `0x5c073f4d` | second protected value |
| 12 | u32 | `+0xa50` | |
| 13 | u16, u16 | `+0xa54`, `+0xa4c` | stored clamped to `0x7fff`; loaded as ints |
| 14 | u32 | `+0xa5c` | |
| 15 | u32 | `+0x38` | player id |
| 16 | u32 | `this` | old pointer (key for the load map, §6.4) |
| 17 | 0xa00 bytes | `+0x44` | table (INFERRED 640 x u32) |
| 18 | group list | `FUN_0052c3f3` on `player+0x28` | `u32 count`, per group `FUN_0052d932` (§6.7) |
| 19 | 0x24 bytes | `FUN_00574656` (`FUN_005aa981(this, 0x24)`); INFERRED `this` = `player+0x34` (the 0x24-byte object the constructor creates) | statistics block |

Load tail: `+0x38` is registered, and for every unit of every group in `player+0x28`: `FUN_0052b22a(unit)` and `unit+0x14 = player`. The base-class call `FUN_00401970` is an empty function (CONFIRMED).

### 6.7 Group (`FUN_0052d932`, size `0x50`; CONFIRMED)

1. embedded polymorphic object at `group+0x20`: its `Serialize` (vtable slot 2; class not identified).
2. `FUN_00574560` on `*(group+0x3c)`: `0x50` raw bytes of that object, then its `+0x4c` sub-object (size `0x1c`, built by `FUN_005420f0(10)`, polymorphic): load deletes the old one through vtable slot 1
   (with arg 1), creates a new one and calls `Serialize`; store calls `Serialize`. INFERRED: the group's order / AI block.
3. the unit list (`FUN_00546360`: count + MFC object pointers of class `Unit`, `FUN_0050dc0f`).
4. `u32 +0x1c`, `u32 +0x40` (pointer, fixed by `FUN_00546700`), `u32 +0x44` (pointer, `FUN_005465d0`).

### 6.8 Unit (`FUN_0052c618`, class `Unit`, size `0x208`; CONFIRMED order, meanings mostly open)

Common part first: `FUN_0052cf8d` (object base `0x3c`): empty base `FUN_00401970`, `FUN_0054ffd1` (not decoded), then `u32 +4` (an id; on load non-zero ids go to `FUN_004f8cec`), `u16 +0xc`, `u16 +0xe`,
`u32 +8`, `u16 +0x18` (load forces 0), `u32 +0x1c`, `u32 this` (old pointer), `u32 +0x14` (pointer, `FUN_005465d0`). Then in this order: `FUN_00546410` (a counted MFC list of
class `0x5f...` via `FUN_0051ca31`, not decoded), the objects at `unit+0x1c8` and `unit+0x1e4` (polymorphic `Serialize`), `FUN_00515bea` (`0x18` raw bytes), `FUN_005157ee` (`0x16` raw bytes),
`FUN_00515bea`, `FUN_005114bc`, `FUN_005595a8`, `FUN_00574452` (not decoded; ECX = embedded sub-objects of the unit, INFERRED). Then the unit's own fields (store order):

| # | Type | Field | # | Type | Field |
|---|---|---|---|---|---|
| 1 | u8 | `+0x49` | 22 | u8 | `+0xa2` |
| 2 | u8 | `+0x4a` | 23 | u8 | `+0xa3` |
| 3 | u8 | `+0x4b` | 24 | u16 | `+0xa0` |
| 4 | u8 | `+0x4c` (low byte of the dword) | 25 | i16 | `+0xa4` |
| 5 | 4 bytes | `+0x50` | 26 | u8 | `+0x12c` |
| 6 | 4 bytes | `+0x54` | 27 | u32 | `+0x130` |
| 7 | 4 bytes | `+0x58` | 28 | u8 | `+0x134` |
| 8 | u8 | `+0x60` | 29 | u8 | `+0x135` |
| 9 | u8 | `+0x61` | 30 | u8 | `+0x136` |
| 10 | byte (`FUN_005464c0/e0`) | `+0x6c` | 31 | u32 | `+0x138` |
| 11 | MFC pointer | `+0x74` | 32 | u8 | `+0x13c` |
| 12 | MFC pointer | `+0x78` | 33 | u32 packed | `word(+0x14c)` \| `(+0x204 != 0) << 16` \| `(+0x1a0 != 0) << 24` |
| 13 | CString | `+0x80` | 34 | u32 | `+0x144` |
| 14-27* | 14 x u16 | `+0x84, +0x86, +0x88, +0x8a, +0x8c, +0x8e, +0x90, +0x92, +0x94, +0x96, +0x98, +0x9a, +0x9c, +0x9e` | 35 | MFC pointer | `+0x68` |
| | | | 36 | u8 flag (`+0x7c != 0`) | then `FUN_0052da4d` (not decoded) when 1 |
| | | | 37 | u8 flag (`+0x140 != 0`) | then the object's `Serialize` (size `0x1c`, `FUN_0053a600`) when 1 |
| | | | 38 | u32 x4 | `+0x5c, +0x64, +0x44, +0x40` |
| | | | 39 | byte | `+0x48` (`FUN_005464c0/e0`) |

(*) the 14 u16 are interleaved by the decompiler's `in_ECX[n]` / `+0x86` pairs: they are written in the order listed; the item numbers of the left column skip 14..27 for them.

Offsets are the decompiler's `index * 4` arithmetic (the two branches use identical offsets); the **meaning** of each field is not decoded (stats / position / HP are in the object base and the `+0x84..` pairs, INFERRED:
current / maximum value pairs). Load post-fixups: `unit+0x3c = FUN_0041e890(short +0xc)` unless virtual `[0x30]` returns non-zero (then 0); `+0x204` and `+0x1a0` come from bytes 2 and 3 of the packed word.

### 6.9 The remaining serialisers (CONFIRMED order unless noted; second pass)

Class identities (name strings read at the `CRuntimeClass.name` pointers): `0x5f9140` = **Item** (size `0x54`), `0x5f91a0` = **Sack** (size `0x50`, name pointer `0x5fbc7c`), `0x5f8f20` = **Effect** (`0x48`),
`0x5f8e68` = **Spell** (element of the unit's spell array), `Unit` has a subclass record at `0x5f8288` = **Humanoid** (size `0x254`, create `0x51207c`, base Unit; decoded in 6.10). Shared helpers: `FUN_00401970` empty; `FUN_005aab4d / 005aab7b` = MFC count (`u16`, or `0xffff` + `u32` when
`>= 0xffff`); `FUN_00543570 / 005435c0` = u32; `CList<u16>`-like lists (`FUN_005420f0(10)`, vtable `0x5d0f28`, `Serialize` `0x542230`): `count` (MFC count), then `count` elements of 2 bytes (`FUN_00421390`, INFERRED u16).

| Routine | Class / object | Layout (store order) |
|---|---|---|
| `FUN_0052cf8d` (base of every game object, size `0x3c`) | `Object` | `0xc` raw bytes (`FUN_0054ffd1`, ECX not verified); u32 `+4`; i16 `+0xc`; i16 `+0xe`; u32 `+8`; i16 `+0x18`; u32 `+0x1c`; u32 `this`; u32 `+0x14` (pointer). Load: `+4 != 0` registers the id (`FUN_004f8cec`), `+0x18` forced 0 |
| `FUN_0052029c` | **Building** (`0x52029c`, vtable `0x5d1268`) | base; `0x16` raw bytes (`FUN_005157ee`); u8 `+0x40`; u16 `+0x42`, `+0x44`, `+0x46`; u8 `+0x48`, `+0x60`, `+0x61`; u32 `+0x64`, `+0x68` (`FUN_00543570`). Load: `+0x3c = FUN_004a65d0(+0x40)` when `+0x40 != 0` else 0 |
| `FUN_0051c6b5` | **SpellEffect** (vtable `0x5d1060`) | base; u8 `+0x40`; u8 `+0x41` |
| `FUN_0052db3e` | **VirtualCaster** (vtable `0x5d0e78`) | base; u8 `+0x3c`; 6 raw bytes at `*(+0x40)` (a 6-byte sub-object built by `FUN_0055b95f`) |
| `FUN_0052d8de` | **Sack** (vtable `0x5d1530`) | base; u32 `+0x3c`; then `FUN_0052da4d` |
| `FUN_0052da4d` | Sack / unit pack (also unit `+0x7c`) | `FUN_00546970` = counted list of **Item** pointers (`FUN_00522e40`); u32 `+0x1c`; u32 `+0x20` |
| `FUN_0052d65a` | **Item** (vtable `0x5d1388`) | base; `FUN_00546410` (counted list of **Effect** pointers, `FUN_0051ca31`); i16 `+0x40`; i16 `+0x42`; u8 `+0x44`, `+0x45`, `+0x46`; u16 `+0x48`, `+0x4a`; u8 `+0x47`. Load: `+0x3c = FUN_00439df0(+0xc)` when `+0xc < FUN_0053e1c0()` (item type table) else 0 |
| `FUN_0051c5ed` | **Effect** (vtable `0x5d1178`) | base; u8 `+0x3c`; u8 `+0x3d`; u32 `+0x40`; i16 `+0xc` |
| `FUN_0051c505` | unit `+0x140` (CArray of **Spell** pointers, vtable `0x5d0b20`) | u32 `+0x18`; u32 `GetSize`; then elements `1 .. GetSize-1` as MFC **Spell** pointers (element 0 is not saved) |
| `FUN_00574560` | `*(group+0x3c)` (size `0x50`) | `0x50` raw bytes; a `CList<u16>` at `+0x4c` (load: delete old, create new, `Serialize`) |
| `FUN_00574452` | block at unit | `0xb8` raw bytes; a `CList<u16>` at `+0xb4` (same rule) |
| `FUN_00515bea` / `FUN_005114bc` / `FUN_005595a8` | unit sub-blocks | `0x18`, `0x40`, `0xb4` raw bytes (ECX = embedded sub-object, not verified) |
| unit `+0x74`, `+0x78`, `+0x68` | Item pointers | `FUN_00522e40` on load, `FUN_0053bc80` on store |

So a **unit's items** are Item objects: the pack at `unit+0x7c` and the held-item pointers `+0x74 / +0x78 / +0x68`; **effects on a unit** are the Effect list at the start of the unit serialiser
(`FUN_00546410`), and each Item carries its own Effect list.

**Script state (`FUN_0057468d`, ECX = the script runner / trigger object; offsets from it; CONFIRMED):** raw `4000` bytes at `+0xc784` (1000 x i32 values), `1000` bytes at `+0xe6c4` (1000 fired flags),
`0x30` bytes at `+8`, `400` bytes at `+0xa728`, `0x132c` bytes at `+0xa8bc`, u8 `+0xa48`, u8 `+0xa49`, u32 `+0xa4c`, u32 `+0xbe0c`, `+0xbe10`, `+0xbe14` ([triggers](../engine/triggers.md)).
(`+0xa728` 400 bytes is a block of the same size as the stream's last 400 bytes but a different object.)

**Map dynamic layer (`FUN_00550008`, ECX = the map object, size `0xa4570`; CONFIRMED):** store: scan positions `i = 0x807 .. 0xedec` of the two planes at `map+0x10000` and `map+0x20000` (bytes `a` = `[+0x10000+i]`,
`b` = `[+0x20000+i]`); for each `i` with `b > 0xf` collect the u32 `(i << 16) | (b << 8) | a`; then `FUN_0055fc20` writes the collected list (MFC count + one u32 per element, element order
= collection order); then the polymorphic object at `map+0x54084` (`Serialize`, class not identified); then u32 `this`. Load: `FUN_0055fc20` reads the list back, the object at `+0x54084` reads, u32
old pointer (`SetAt`), and each element is written back: `[+0x20000 + (e >> 16)] = (e >> 8) & 0xff`, `[+0x10000 + (e >> 16)] = e & 0xff`. So the dynamic layer is **a sparse list of (index, plane-2 byte > 0xf, plane-1 byte)**;
the planes themselves are rebuilt from the map file by the loader (INFERRED: plane 2 bytes `<= 0xf` are the static state). The 2 planes are not otherwise saved.

**Stream end.** `FUN_0057a951` writes `400` bytes with ECX = the object left in ECX by `FUN_004ec732` (not identified from the decompiled form; INFERRED RNG).

**Server start and `game0000.sav` (`FUN_004eb715`, CONFIRMED):** when `server+0x1ac != 0` (`in_ECX[0x6b]`) the server loads `game0000.sav` with `FUN_004e9b95` (nonzero = error code 4); when 0 it loads the map
(`FUN_005606aa`, error 5) and zeroes tick and block counters. `server+0x1ac` is therefore the "load the pending save" switch: `game0000.sav` is a **scratch slot** the client writes (the load path copies
the chosen slot there, INFERRED; the writer was not found, open question). Also clears `DAT_0068ec78` (a 32 x 32 u16 table) after the load.

### 6.10 Round 3: exact MFC tags, Humanoid, embedded objects, stream owners (CONFIRMED unless noted)

**MFC tags** (`FUN_005ac36a` object store, `FUN_005ac598` class store, `FUN_005ac3e9` load; little endian):

| Case | Bytes |
|---|---|
| null pointer | `u16 0x0000` |
| object already written, index `< 0x7fff` | `u16 index` |
| object already written, index `>= 0x7fff` | `u16 0x7fff`, `u32 index` (no flag bit) |
| new object, class not yet written | `u16 0xffff`, class record (`FUN_005aa6c9`: schema word of the CRuntimeClass at `+8`, which is **1** for every class here; then name length and name, MFC `CRuntimeClass::Store`, INFERRED field widths u16 / u16 / bytes), then the object body (`Serialize`) |
| new object, class already written, class index `< 0x7fff` | `u16 (0x8000 | classIndex)`, then the body |
| new object, class index `>= 0x7fff` | `u16 0x7fff`, `u32 (0x80000000 | classIndex)`, then the body |

Numbering: one counter (`archive+0x30`) shared by classes and objects; a new class takes the next index when it is written, then the object takes the next one **before** its body is serialised (so a child's
back-reference to its parent works). **Not confirmed**: the counter's starting value (the archive constructor was not read; standard MFC starts at 1, index 0 = null). The reader maps the new object with
`FUN_0059f62b(count, ptr)` in the same order. A reader that meets a class tag for a class whose pointer type check fails raises error 6 (`FUN_005ac8ad`), an index above the map size error 5.

**Humanoid** (`FUN_0052d7c8`, vtable `0x5d0f40`, size `0x254`): `Unit::Serialize` (6.8), then `0x18` raw bytes at `+0x23c`, then 12 **Item** pointers for `+0x20c .. +0x238` (slots 1..12; slot 0 not saved; INFERRED equipment slots).

**The class set (closed).** The `.data` records whose base is the object base `0x5f8240` are exactly `VirtualCaster`, `Unit`, `SpellEffect`, `Effect`, `Building`, `Item`, `Sack` (search of the pointer value), plus
`Humanoid` (base `Unit`), `Player` and `Spell` (base CObject). **Spell** (`0x5f8e68`, size `0x14`, vtable `0x5d1160`, `Serialize` `0x51bf44`): u8 `+8`, u8 `+9`, u8 `+0xa`, u16 `+0xc`, u32 `this`; load: `+4 =
FUN_0053e260(+8)` (spell table lookup).

**Unit embedded objects (assembly of `FUN_0052c618`, ECX per call):** `+0x20` = counted list of **Effect** pointers (`FUN_00546410`); `+0x1c8` and `+0x1e4` = embedded `CList<u16>`-style lists (vtable `0x5d0f28`, `Serialize`
`0x542230`: MFC count, then `count` 2-byte elements); raw blocks: `0x18` bytes at `+0xa6`, `0x16` at `+0xbe`, `0x18` at `+0x114`, `0x40` at `+0xd4`, `0xb4` at `*(unit+0x1c0)` (the **brain** object), and `0xb8`
bytes at `*(unit+0x1c4)` followed by a `CList<u16>` at that object's `+0xb4` (the second brain object, same shape as the group's `*(group+0x3c)`). Store order of the head: base, effects, `+0x1c8` list,
`+0x1e4` list, `+0xa6`, `+0xbe`, `+0x114`, `+0xd4`, brain `+0x1c0`, brain `+0x1c4`, then the fields of 6.8. The group's `+0x20` object is the same embedded `CList` kind (INFERRED, constructed by `FUN_005420f0(10)`).

**Server-side holders (assembly of `FUN_004ec732`):** `FUN_0052d16b` and the player list run on the global player manager `[0x68d2c4]`; `FUN_0052c3da` on `*[server+0x7c]` (buildings), `FUN_0052d5cb` on
`[server+0x7c]+4` (spell effects), `FUN_0052d5b2` on `[server+0x7c]+8` (sacks), `FUN_0053bbd0` on the **embedded** list at `[server+0x7c]+0x10` (virtual casters); the polymorphic object at `[server+0x7c]+0xc`
is called through vtable slot **0** to store and slot 0 to load (and slot 1 after the load: it is not an MFC `CObject`, there is no `GetRuntimeClass` slot); the map is `[0x670e48]`, the script runner
`[0x66832c]`. Store order check: tick, block, name, 13 words, player manager, `+0xc` object, flag `[server+0x94]`, then (flag 1) buildings, effects, map, script, sacks, casters, then the two `0xbadface1`.

**The 400-byte tail (see 6.11).** `FUN_0057a951` runs with ECX = `[server+0x170]` (a debug block, 6.11: `FUN_005aa981(this, 400)` writes the first 400 bytes of it at the very end of the stream, after the two `0xbadface1`). It is **not**
the engine's RNG: [engine/rng.py](../../engine/rng.py) models the CRT generator whose whole state is one 32-bit word (`ptd+0x14`), and no 4-byte RNG word was found in any decoded serialiser, so a reload does not
restore the CRT sequence (INFERRED: the undecoded polymorphic objects might hold one). What the 100-dword block is (a per-server table) is open. For a writer: copy the 400 bytes through, or zeros.

**Save list date (CONFIRMED).** `FUN_0043dc54` lists the directory with `FindFirstFileA` (pattern `\game*.sav`), skips directories, skips `game9999.sav` and `game9998.sav` for the Save dialog (parameter 0; the Load dialog, parameter 1, keeps
them), copies the whole `WIN32_FIND_DATAA` (0x50 dwords) into a list entry (`FUN_0044fd10`) and sorts. The date is therefore the **file system's last-write time** (`ftLastWriteTime`), not a field of the file;
the description string is the 0x100-byte block of the client tail (6.3). A writer must only set the file time normally.

**`game0000.sav`.** The literal is referenced only by the reader in `FUN_004eb715` (`0x4eb992`, taken when `server+0x1ac != 0`); `FUN_004e9816` is called by exactly two sites (the client writer `FUN_0048dc9f`, and
the network case `0x4f723d`). So there is **no dedicated writer**: slot 0 of the `game%04d` numbering (`9999 - slot` in the save UI, 6) is `game0000.sav`, written by the ordinary save when the UI slot maps to it (INFERRED).

**`game9998.sav`.** The two literals `game9999.sav` / `game9998.sav` appear **only** in the list filter above. A load of either goes through the generic loader (`FUN_0048db37` -> `FUN_004e9b95`): there is no special
restore. `game9998` is a mission-kind save written at the town leave click ([6 intro](#6-the-saved-game-gamedsav)), so loading it restores the server state captured at that point exactly like any other mission save (INFERRED which instant: the state when the leave click posted `0x442`).

**Mission list of the client tail (`FUN_004a8f96`, 6.3 item 3).** `u32 count` (`FUN_004a99b0`), then per entry `FUN_004a88db` = two 4-byte raw writes (entry `+0`, `+4`: INFERRED `u32, u32`), then two more u32 (`+4`, `+8` of the owning
object at `client+0x598`). It is a list kept by the same object that holds the hall of fame, read back by `FUN_004a9032`; what the entries mean (INFERRED: a played-missions / medals list, entries = mission id and value) is not decoded.

### 6.11 Round 4: the last three objects, option words, server constructor (CONFIRMED unless noted)

**Server constructor `FUN_004e957b`** (allocates and defaults; `this` = server): `+0x7c` holder = static `DAT_0068e218` (`+0` buildings, `+4` spell effects, `+8` sacks, `+0xc` unit container, `+0x10` embedded virtual-caster
list); globals `DAT_0066832c` (script runner), `DAT_0068d2dc` (unit container), `DAT_00672f64`, `DAT_0068d2c4` (player manager), `DAT_00670e48` (map) start 0; `+0x170` = a 400-byte zeroed block (`FUN_0057a925` =
`memset(this, 0, 400)`); counters `+0`, `+4` = 0; **option word defaults**: `+0x174, +0x17c, +0x180, +0x184, +0x188, +0x18c, +0x190, +0x194, +0x198, +0x19c, +0x1a0` = **0**, `+0x178` = 0 (not saved), `+0x1a4` = 1,
`+0x1a8` = 1, `+0x1ac` = 0 (load switch), `+0xd4` = 0, `+0xd8` = **2** (difficulty), `+0x94` = 0.
`FUN_004eb356` (server start; arg `p`): `+0x74 = (p < 2)`, `+0x70 = (p > 0)`, `+0x1a8 = (+0x74 != 0)`, `+0x8c = 0`, `DAT_006044c4 = this`, then creates the 29 command slots at `+0xf8..`, the **unit container**
(`DAT_0068d2dc`), a second container (`DAT_00672f64`), the `[server+0x7c]+0xc` **unit container**, and the player manager (`FUN_0051628e`). The map loader `FUN_005606aa` (new-game branch) sets `+0x74 = (map+0xd8 > 1)`, `+0x178 = (+0x74 == 0)`,
`+0x1cc = map+0xdc`, `+0x1a4 = (+0x74 == 0)`, then sets unit `+0x1a0 = 1` for units of players whose relation to the local player `& 7 == 0`; **it does not touch the 11 saved option words**.

**`[server+0x7c]+0xc` and `DAT_0068d2dc` = the unit container** (`FUN_0052b19a`, vtable `0x5d1598`, size `0x20`, a list base `FUN_0053c3f0`; the same class as `Player+0x24` / the group list):
slot 0 = `FUN_0052c500` -> `FUN_00546360`: `u32 count`, then `count` MFC **Unit** pointers (MFC back-references to units already written inside the groups, so most are `u16 index`); slot 1 (after load) calls virtual
`+0x24` of every unit (post-load init). Written right after the player list.

**`map+0x54084`** (constructed by `FUN_0055f360(10)`, a `CMap` with 17 buckets, vtable `0x5d1ab8`, slot 2 `Serialize` = `FUN_0055f6b0`): MFC count, then per entry `u16 key` (`FUN_00421390`, 1 element) and a **60-byte value**
(`FUN_0055fff0`, local buffer `0x3c`; INFERRED raw 60 bytes). Load: for each entry `FUN_0055f430(key, value)` inserts. The map object (`0xa4570`, base = the unit-container class at `+0x5400c`) also embeds lists at `+0x54068` (`CList<u16>`), `+0x54190`, `+0x58d88`,
`+0x92ecc`, `+0xa44f4`, `+0xa4510` that `FUN_00550008` does **not** save (rebuilt from the map file / script).

**`[server+0x170]` (400 bytes)** is a **debug / trace state block**, not the RNG: `+0` = "Turn tracing" flag (Alt+T, `FUN_00578910` case 3), `+4` = "Script tracing" flag (case `0x13`); the rest is the zeroed remainder
(timing and XP statistics for the Alt-keys of the same handler). A writer emits **400 zero bytes** (what the constructor creates); the loader restores whatever was saved (harmless).

**The 13 option words.** Saved order: `+0x174, +0x17c, +0x180, +0x184, +0x188, +0x18c, +0x190, +0x194, +0x1a0, +0x19c, +0x198`, then `+0xd4`, `+0xd8`. Defaults 0 (ctor above); the single-player start path
(`FUN_004eb356`, `FUN_004eb715`, map loader) assigns none of the eleven, so **a world built by the engine should write eleven zeros** (CONFIRMED defaults; the words' consumers were not traced: address search shows
`+0x17c` / `+0x1a0` used by dozens of unrelated routines because of field-offset collisions, so no meaning is claimed). `+0xd4` = scenario id (`Scenario\<n>` name; **write the real mission id for a mission save, or 0 for a map without one**) and
`+0xd8` = difficulty (1..3 applied on load; default 2). Not saved but derived at load: `+0x178`, `+0x1a4`, `+0x74`, `+0x1cc`.

## 7. Code

`allods2.formats.saves`: `parse_a2c / build_a2c / load_a2c` (`Character`, `Identity`, `Stats`, `ItemPacket`, `Item`, `encode_item / decode_item`), `parse_famehall / build_famehall`, the byte layer (`checksum`, `xor_stream`,
`rle_encode / rle_decode`). `Character.layout` keeps the header flags and junk bytes, so a parsed `.a2c` rebuilds byte for byte.

**Saved game (L10b, tests `tests/test_saves_l10b.py`, `tests/test_saves.py`).**
* `parse_save(data)` / `SaveGame.pack()`: byte-exact round trip. Errors: `ValueError("Invalid save file")` (bad magic, or fewer than 16 bytes), `ValueError("Outdated save file")` (version below `0x0BAD0002`; a higher version
  loads and is written back as stored), `ValueError` for a truncated file, a server block whose end disagrees with the header, or trailing bytes after the client block. **Multiplayer**: the 0x100 bytes after the server block
  start with `"Server Multiplayer save file."` (§6.1) -> `MultiplayerSave` (a `ValueError` subclass, message says single player only). INFERRED: the exact text is the one named in §6.1 and the check is a prefix match at the server block end.
* `SaveGame.stream` = the decompressed server stream, padded to an even length; `ServerHead` types the head (§6.2 items 1-6) and keeps everything after it raw in `rest` (players, objects, script state, the 400-byte tail:
  unknown bytes are never dropped); `SaveGame.archive()` is an `MfcReader` over `rest` for the later steps.
* `allods2.formats.mfc`: `MfcWriter` / `MfcReader` (u8 / u16 / u32 / raw / counted-list u32 / CString) and the object-pointer scheme of §6.10: null `u16 0`; back-reference `u16 index`, `0x7fff` + `u32 index` from `0x7fff`; new class
  `0xffff, schema, nameLen, name`; known class `0x8000 | classIndex`, `0x7fff` + `u32 0x80000000 | classIndex` from `0x7fff`; one counter for classes and objects, the object's index taken before its body (a child can refer to its parent).
  The reader registers the (created, still empty) object before `load`. `MfcClass(name, schema=1, create, load)` is the class table entry. **Decision (INFERRED)**: the first index is 1 (`first_index` parameter to change it when a real save disagrees);
  the class record is `u16 schema, u16 nameLen, name` (CString-free, MFC `CRuntimeClass::Store`); a class whose schema differs from the table's is refused; an unknown class name or an index outside the map raises `ArchiveError` (the exe's errors 5 / 6).
* `ClientTail` (§6.3): `description`, `reg` / `reg_bytes`, `missions`, `mission_tail`, `scenario` (`ScenarioState`: 1024 `variables`, the `0x140` `shops` with `shop_block(town, block)`, `locations` of `Location(index, type, name16)` with `.text`,
  `current`), `hotkeys` (nine `Hotkey(a, b, data)`). `reg_bytes` is the stored image (so a loaded file writes back exactly); `ClientTail.state` is the typed `ClientState` view of the tree (`CurrentState/InBattle`, `Character/Name`
  (default `"No name"`), `GameOptions/{Wimpy, ShowHP, FlyingHP, Formation, Speed, ShowTimeFlow}`, `View/{X, Y}`, `SpellBook/{IsOpen, Pressed, Shortcuts}`, `Objects/Selection`, `Objects/Group<n>`, `Inventory/IsOpen`, and for a battle
  save `Projectiles/{FreeIndex, IDs}`, sections `Prj<id>` (16 fields `PRJ_FIELDS`), `Fog/{FirstState, Data}`; battle keys are read only when `InBattle & 1`). `ClientTail.with_state` / `ClientTail.new` build the tree with
  `allods2.reg.build_reg`. INFERRED: the leaf kinds (ints, int arrays for the id lists, shortcuts and `Fog/Data`), and that a tree built by `build_reg` is equivalent to, not necessarily byte-identical with, one the exe wrote
  (the exe's incremental writer leaves a 32-byte initial blob and spare room, [reg](reg.md)); a loaded file is never re-encoded, so this only matters for newly written saves.

## Open questions

* Meaning and consumers of the 11 option words (`server+0x174..0x1a0`); only their defaults (0) and the fact that the single-player start path does not assign them are CONFIRMED (6.11). A real mission save would show which become non-zero.
* The `0x3c`-byte values of the `map+0x54084` map and the `0x30` / `0x132c` script blocks, and the field meanings of player / unit / item / effect objects (6.6, 6.8, 6.9).
* The MFC archive counter's starting value and the exact `CRuntimeClass::Store` field widths (6.10; standard MFC assumed, implemented as first index 1 in `formats/mfc.py`): VERIFY by a real save.
* The `.reg` value kinds of the client tail's id arrays / `Fog/Data` and whether the exe's loader tolerates a `build_reg` tree whose blob layout differs from its own (7; INFERRED): VERIFY IN GAME.
* The `0x2f` flag byte (network only: every client-pump rewrite of the file is gated by `+0x5d8 != 2`, so never in single player).
* Whether a single-player continue ever uses a stored character's items (VERIFY IN GAME: pick an advanced character for a new campaign and compare attributes).
* `famehall.dat` fields `b`, `c` and when the hall is written (`FUN_004825c4` caller; the score formula); what the mission-list entries of the client tail mean (`FUN_004a8f96`, entry type in 6.10).
* Which UI path produces `game0000.sav` (no dedicated writer, 6.10); exactly which instant `game9998.sav` captures.
