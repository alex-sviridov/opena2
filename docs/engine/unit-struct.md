# Runtime unit struct (`allods2.exe`)

The live unit of the server world ("Creature": our name, the exe has none) built from a section 6
record ([map.md part 5](../formats/map.md#part-5-players-units-items)), plus the client's draw
object. GOG 1.01 (sha256 in [formats/README](../formats/README.md)); all addresses are VAs.
Tags: **CONFIRMED** = read in the binary with the routine or instruction address given;
**INFERRED** = from code shape or use; **UNKNOWN** = not traced.

**Summary.** Monsters (and everything non-human that needs a unit) are `0x208` bytes, vtable
`0x5d0eb0`, ctor `0x50dc2b` (by name `0x50dd41`); humans and heroes are `0x254` bytes (leaf vtable
`0x5d0fb8`, ctor `0x514377`, base `0x5d0f40` / `0x512133`, which derives from the monster class).
Map-load allocation sites: server `0x561d5b` (human) / `0x561dcd` (monster), client `0x4a4ae1` /
`0x4a4e61`; about 35 other `push 0x208` / `push 0x254` sites (spawns, spell carriers, message loop
`0x40f372`) are listed in §1. The client also builds a `0x1e4`-byte draw object (§4). The class is
chosen by the record's `flags & 0x10`.



## 1. Two object families are built per map unit

Server (sim) side, FUN_00561bf9 (`this`=server world, arg = server map object whose list at map+0x3a4 holds the
0x54-byte section-6 records; loop i=1..n, record = list[i-1]; called from the server map load FUN_005606aa area):
creates a **Creature** (sim unit) and registers it. Client side, FUN_004a449c (the scene/map load, `this` vtable 0x5cea28,
re-reads the .alm with FUN_00534ad4 at 0x4a4508): creates its own copy of a Creature (same classes) AND a
**view unit** (0x1e4 bytes, draw class) and links them with FUN_004699d2(viewunit, creature).

### Allocation / classes (operator new FUN_00401880 size = struct size; ctor next)
| Class | vtable | size | ctor | base | notes |
|---|---|---|---|---|---|
| Base object | 0x5d0e28 | (part of Creature) | 0x50d493 | CObject-like FUN_00401900 | sets +0x10 = new Position (0xc bytes, ctor 0x54fa22(0, world 0x670e48)); FUN_0050d6ae zeroes +0x18 (w), +0x1c, +4. CONFIRMED |
| **Creature** (monsters; also base of humans, and used for spell/effect carriers) | 0x5d0eb0 | **0x208** | 0x50dc2b (by name: 0x50dd41) | Base | CONFIRMED (push 0x208 at 0x4a4e61, 0x561dcd; ctor 0x50dc2b sets vtable at 0x50dcdf) |
| HumanBase | 0x5d0f40 | 0x254 | 0x512133 (by name 0x5143e4 / 0x5145d1 parse) | Creature (call 0x50dc2b at 0x512152) | FUN_005121e1 default human stats. CONFIRMED |
| Human leaf | 0x5d0fb8 | **0x254** | 0x514377 (default name "Man_Unarmed", string 0x5fe3ac) | HumanBase (call 0x512133 at 0x514398) | map load allocs this at 0x4a4ae1 (humans). CONFIRMED |
| view unit (client) | 0x5cd5d0 | 0x1e4 | 0x462a4a | 0x45fa00 (vtable 0x5cd470) | alloc 0x4a4e12 (monsters) / 0x4a50c1; draw FUN_004632a1, tick FUN_0046617c (docs/formats/animation.md). CONFIRMED |
| view hero | 0x5cd660 | 0x1e4 | 0x46bfa6 | 0x462a4a | sets +0x10 = 0x10; chosen when `[0x66..]` flag at 0x4a5063 `[unit+0x124]!=0`. CONFIRMED (construct), meaning INFERRED |

Which class a map unit becomes: `mapunit+0x48 & 0x10` (file+12 bit 4) set -> **human** (0x254, Leaf ctor, template list
`0x68f590`, ID->index map `FUN_004fd5ad`), clear -> **monster** (0x208, ctor 0x50dc2b/0x50dd41, list `0x68f57c`,
`FUN_004fd62f`). The ID looked up is `mapunit+0x10` (file+20). CONFIRMED (0x561d12-0x561dca, 0x4a4ad3-0x4a4b31, 0x4a4e61-0x4a4ec0).
Other creation sites (all `Creature`/`Leaf`): 0x4f312a (server spawn of a type list per player: sets +0x14c=type, +0x14=player
0x68d2c4, +4 = FUN_004f8d90 unique id), 0x4f06ac (temporary spell carrier: state 0xd/0xe), 0x490861.., 0x4ea7cc.., 0x4f275c..,
0x4f89d1, 0x512097, 0x5142db, 0x520770.., 0x40d9b2 (client message loop, 0x40f372), 0x51a61e/0x51ac7d. Not all traced.

### Hierarchy / class order of the creature creation path (map load, FUN_00561bf9)
1. owner: `FUN_0051680d(0x68d2c4 player mgr, mapunit+0x14 as word)`; missing -> error log + skip. If `[0x6044c4+0x174]` and `player+0x2c` both set -> skip (`player+0x2c` = computer-controlled, CONFIRMED [progression](../data/progression.md#4-xp-sources); the skip is a multiplayer filter, INFERRED).
2. alloc + ctor by template name (above). Difficulty tweak (`[0x6044c4+0xd8]`: 2 skip; 1: maxHP*=const `0x5d1b00`, HP=maxHP, brain+0x44>>=1; else +0x32 to words +0xa6,+0xbe and maxHP*=`0x5d1b08`). CONFIRMED 0x561e20-0x561f0b ; modes: 1 easy, 2 normal (server ctor default `0x4e97bf`), 3 hard, setter `0x493d80` from window `0x4891d8`: [ai §10.1](ai.md#101-difficulty-tweak-fun_00561bf9-0x561e20-0x561f0b-confirmed) CONFIRMED.
3. `mapunit+0x50` bits -> creature dwords: bit0 -> +0x194, bit1 -> +0x19c, bit2 -> +0x198, bit3 -> +0x1a0 (0/1). CONFIRMED 0x561f0f-0x561f77.
4. if word +0xe == 0 -> error "bad unit" and delete. vtable +0x58 (recompute from template; 0x5118be for monsters).
5. HP: if human bit and mapunit s16 +0x22 != -1 and == s16 +0x20 -> both set to -1. then `+0x96 = mapunit.s16(+0x22)` if != -1; `+0x94 = mapunit.s16(+0x20)` if != -1 else `+0x94 = +0x96`. CONFIRMED 0x562013-0x562099. (so file+36 = HP, file+38 = maxHP override, -1 = template value)
6. place: `FUN_00510089(creature, x = mapunit.x>>8, y = mapunit.y>>8, 0)` spiral search for a free cell, then insert (`FUN_0055020a`); fail -> error + delete. CONFIRMED.
7. `creature+8 = (s16)mapunit+0x3c` (scenario unit number, file+40); registered in `0x68d2dc` manager (FUN_0052b281); `creature+0x14 = player`; added to `player+0x24` unit list (FUN_0052b22a); group: iterate `player+0x28` groups (0x50-byte objects, ctor 0x52ae43) for one with `group+0x1c == mapunit+0x40` (file+44), else new group; `FUN_0052af8c(group, creature)` adds. So **file+44 = per-player group number**. CONFIRMED 0x562160-0x562262.
8. Client side (FUN_004a449c) additionally: view `+4 = 0x6000 + s16(mapunit+0x3c)` (object id), view `+0x1e0 = mapunit+0x40`, view `+8 = +0x2c = mapunit.x`, `+0xc = +0x30 = mapunit.y` (1/256 cell), view `+0x14` = player ptr; `FUN_004699d2` copies creature stats to the view (table in section 5).

## 2. Creature layout (server, 0x208 / 0x254)
Offsets from the constructors 0x50d493, 0x50dc2b, init 0x50e173, copy 0x50e48e (vtable +0x3c: copies every field below), 0x5121e1, 0x5145d1, 0x514cf2, loader 0x5114f3 (docs/formats/databin.md) and users listed.

| Off | Size | Meaning | Tag / evidence |
|---|---|---|---|
| +0x00 | 4 | vtable (0x5d0eb0 / 0x5d0f40 / 0x5d0fb8) | CONFIRMED |
| +0x04 | 4 | object id (FUN_004f8d90 on spawn; message/object key; 0 for carriers) | CONFIRMED 0x4f342b, 0x4f0715 |
| +0x08 | 4 | scenario unit number = mapunit s16 +0x3c (file+40) | CONFIRMED 0x562167 |
| +0x0c | 2 | template index into the data.bin list (humans g6 / monsters g5) | CONFIRMED 0x514835, 0x4a4b39 |
| +0x0e | 2 | units.reg type ID (animation set); 0 = invalid -> creation fails. Humans: param16 typeID (+0x21/+0x23 +gender: 0x514bc7/0x514bd3) | CONFIRMED (0x561f7a test; monster param 29 per docs) |
| +0x10 | 4 | ptr **Position** (0xc bytes, section 3) | CONFIRMED |
| +0x14 | 4 | owner Player object ptr (`0x68d2c4` manager) | CONFIRMED 0x56217f |
| +0x18 | 2 | zeroed on init/copy | UNKNOWN meaning |
| +0x1c | 4 | monster param 37 (also re-read 0x511959) | CONFIRMED (docs) / meaning UNKNOWN |
| +0x20 | 0x1c | effect list (ctor 0x541de0; iterated first in the creature tick 0x50f17c: vtable +0x38 tick, removed when finished): [effects](effects.md) | CONFIRMED |
| +0x3c | 4 | ptr to data.bin record (params at record+8; `FUN_0041e7e0(k)`) | CONFIRMED 0x4a4b54, 0x514850 |
| +0x40 | 4 | dword, reset 0 | UNKNOWN |
| +0x44 | 4 | dword | UNKNOWN |
| +0x48 | 1 | byte (0 init) | UNKNOWN |
| +0x49 | 1 | param (monster 31 / human 21 TokenSize) | CONFIRMED loader (0x514f37) |
| +0x4a | 1 | param (monster 32 / human 22 MovementType); `>1` => HP set to -1000 in death (0x50f273) | CONFIRMED |
| +0x4b | 1 | param face / palette variant (human 17, monster 30); bit 7 |= gender (0x514bdc) and `|=0x80` when item[0x12] nonzero (0x4a4be3) | CONFIRMED |
| +0x4c | 1 | creature flags: 2 = has a spell list (monster `spell_1` > 0 `0x511c0a`; human spellbook), 4 = mage (monster `known_spells` not 0/-1 `0x511dd6`; human maxMana +0x9c != 0 `0x514907`), 8 = off the map (`FUN_005102a3` sets, `FUN_00510318`/`FUN_005103ae` clear), 0x10 = sure hit; `FUN_0053a5a0` returns `& 4` | CONFIRMED ([ai §6](ai.md#6-attack-and-return-execution-confirmed)) |
| +0x50 | 4 | current **order id** (0 none, 1 and 0xa special-cased by AI 0x56e1d3/0x56e1ed; 0xb at 0x50ec6a; 0x10 on removal) | CONFIRMED set sites; per-value meaning INFERRED |
| +0x54 | 4 | **state** executed by tick FUN_0050f12c: 0 idle, 1 move step, 2 pick up item at cell, 3 melee attack, 0xd cast/shoot at target object (+0x5c), 0xe cast at cell (+0x60,+0x61), 0xf use structure at cell, 0x10 dead/removed, 0x1b AI wait | CONFIRMED jump table 0x50fc17 / byte table 0x50fc2f; writers 0x56ddb4,0x56de25 etc. |
| +0x58 | 4 | attack sub-phase: 0 start, 5 wind-up counting, 7 recovery | CONFIRMED 0x50f3b3-0x50f68c |
| +0x5c | 4 | target object id (state 0xd) / spell arg | CONFIRMED 0x4f0866, 0x56de89 |
| +0x60,+0x61 | 1,1 | target cell x,y (state 0xe) | CONFIRMED 0x4f08a3 |
| +0x64 | 4 | spell/effect object ptr (carrier) or weapon attack id (copied from weapon +0x84) | CONFIRMED 0x4f0808, 0x50f41e |
| +0x68 | 4 | weapon/attacker object (or 0) | CONFIRMED 0x50f42a |
| +0x6c | 1 | tick timer: wind-up/relax countdown (loaded from +0x134/+0x135) and death timer (vtable+0x74 -1) | CONFIRMED 0x50f22a, 0x50f4d8 |
| +0x70 | 4 | ptr to the owner's group (0x50-byte object, ctor 0x52ae43; `+0x3c` → GroupAI object, `+0x44` group speed, `+0x45` active flag) | CONFIRMED 0x52af8c, 0x55915a |
| +0x74 | 4 | equipped weapon item obj (0x88 bytes, ctor 0x528808/0x528fd8) | CONFIRMED sizes; role INFERRED from tick 0x50f3ee |
| +0x78 | 4 | equipped second item obj (0x6c, ctor 0x52836a/0x5273f0/0x527e23: armour/shield) | CONFIRMED size; role INFERRED |
| +0x7c | 4 | inventory/pack obj (0x24 bytes, ctor 0x529a25; add 0x529ac2) | CONFIRMED 0x5108a6 |
| +0x80 | 4 | CString: template name (e.g. "Man_Unarmed", "Goblin_Pike") | CONFIRMED 0x50e3c2, 0x514796 |
| +0x84,+0x86,+0x88,+0x8a | 2 each | body, reaction, mind, spirit (human init 30 each; params 0-3) | CONFIRMED 0x514d0b-0x514d46; docs 0x51d436 |
| +0x8c | 2 | speed (param 8 monster / 6 human; human default 0x10) | CONFIRMED 0x514da3 |
| +0x8e,+0x90,+0x92 | 2 | copied; UNKNOWN (client +0x90 -> view +0x10e) | UNKNOWN |
| +0x94 | 2 | **HP** (s16) | CONFIRMED 0x50fc74, 0x562083 |
| +0x96 | 2 | **max HP** | CONFIRMED 0x50fca8 |
| +0x98 | 2 | HP regeneration rate (monster param 5) | CONFIRMED 0x50fcbd |
| +0x9a | 2 | **mana** | CONFIRMED 0x50fdd8 |
| +0x9c | 2 | **max mana** | CONFIRMED 0x514d78 |
| +0x9e | 2 | mana regeneration rate | CONFIRMED 0x50fe2f |
| +0xa0 | 2 | copied (monster param 6 also writes); UNKNOWN | UNKNOWN |
| +0xa2 / +0xa3 | 1 | fractional accumulators (0..99) HP / mana regen | CONFIRMED 0x50fd5b, 0x50fe4f |
| +0xa4 | 2 | copied; client view +0x10a (sight/scan range) | CONFIRMED copy 0x469b60 |
| +0xa5 | 1 | scan range byte (human param 8 at 0x514dc4) | CONFIRMED loader |
| +0xa6..+0xbd | 0x18 | sub-object (copy ctor 0x5159cb): words incl. +0xa8..+0xb2 (6 skills, human params 10-15) | CONFIRMED copy; field roles per docs |
| +0xbe..+0xd3 | 0x16 | sub-object (copy 0x5156bf): +0xbe word = defence (human param 9; halved at death 0x50f20f), +0xc0, +0xc4..+0xcc, +0xcf..+0xd3 (monster params 15-28) | CONFIRMED loader, meanings per docs |
| +0xd4..+0x113 | 0x40 | sub-object (ctor 0x511266, copy 0x511326): +0xde word HP-regen bonus %, +0xe2 word mana-regen bonus % (0x50fd27/0x50fe1b) | CONFIRMED those two |
| +0x114..+0x12b | 0x18 | sub-object (0x5159cb copy): +0x116.. copy of skills 1..5 | CONFIRMED 0x514ea1 |
| +0x12c | 1 | default attack range in cells (fallback of `FUN_0056ac5b`) | INFERRED |
| +0x130 | 4 | dword | UNKNOWN |
| +0x134 / +0x135 | 1 | attack wind-up / recovery ticks (monster 17/18, human 19/20; human default 8/4) | CONFIRMED 0x5122a4, 0x514f14 |
| +0x136 | 1 | "attack done" flag (set 1 init, 0 when a swing starts) | CONFIRMED 0x50e309, 0x50f4bb |
| +0x138 | 4 | dword | **rest clock**: `tick + n` written by the move step (0x6b, step ticks), the turn (0x6d, `(target facing+8)>>4`), melee/ranged swing start (0x71 byte / 0x72: `+0x134 + +0x135`) and `tick` by cast starts (0x86/0x8a/0x8b/0x8c); init 0 (`0x50e3d8`), copied by `0x50ea4b`; `FUN_0050fc3e` = tick - this (signed); regen x3 above 80, main-hero resend at exactly 80 (combat §12.5) | CONFIRMED 0x504122, 0x5041ba, 0x504292, 0x504369, 0x50446f, 0x50e3d8, 0x50ea4b |
| +0x13c | 1 | death handled flag (set 1 first tick with HP<=0, calls FUN_00510745) | CONFIRMED 0x50f1f1 |
| +0x140 | 4 | spellbook object (0x1c bytes, ctor 0x53a600; spells added by 0x51c29e) created if maxMana>0; also built for carriers | CONFIRMED 0x514abf-0x514b00 |
| +0x144 | 4 | **effect mask**: bit `1 << id` per active effect of the list `+0x20` (id = spell number; 0x1000 Invisibility, 0x40000 Stone Curse: Brain order 4 waits while it is set, 0x56dd39); the stat-class bits are the client update mask `+0x150` ([effects §7](effects.md#7-the-effect-pass-and-the-effect-mask)) | CONFIRMED |
| +0x148 | 4 | **master id** of a summoned minion = the caster's `+0x04` (Summon, `0x51a839`); 0 for everything else (init `0x50e3e5`, Control Spirit `0x51b0e1`); drives the minion cap job and is excluded from event 4 / spawner counts ([combat 12.6](combat.md)) (view +0x148 = 16 bit, unrelated) | CONFIRMED |
| +0x14c | 2 | **server/type id** (data param "serverID": human 24, monster 55; humans only: values >10000 reduced by (v/10)%1000, monsters stored raw) | CONFIRMED 0x4a4b8f, 0x4a4bb2, 0x4f3420 |
| +0x150 | 4 | client update mask: stat classes changed since the last update (`FUN_0051ce12` zeroes it, `FUN_0051d436` ORs, `FUN_00502019(unit, 0, +0x150, 0xffb)` sends it) | CONFIRMED |
| +0x154 | 0x40 | zeroed buffer | UNKNOWN |
| +0x194,+0x198,+0x19c,+0x1a0 | 4 each | scenario flags from mapunit+0x50 bits 0,2,1,3 (file+16); +0x1a0 also set to 1 at 0x51a7cf/0x560c20 | CONFIRMED set. `+0x1a0` = summoned: no loot (`FUN_00510a70`), no XP (`FUN_005128cb`), set by summon/clone spells (`FUN_00519db8`). The other three only gate candidates of the event generator `FUN_005303ed` (not AI). See [map.md](../formats/map.md#units-section-6) |
| +0x1a4,+0x1a6 | 2 | word pair (read by messaging 0x502019, 0x52b368) | UNKNOWN |
| +0x1a8 | ~0x18 | object (ctor 0x59f003) | UNKNOWN |
| +0x1c0 | 4 | ptr **Mover** (0xb4 bytes, ctor 0x551346, zeroed then +5=0x41, +8=5, +9=0xff, +0xa=0x10); +0 and +1 are facing bytes (init `0x40+rand(0x80)`, 0x50e2ac), +0xa turn rate (monsters param 9; humans: the recompute `FUN_0051366b` copies the low byte of the speed `+0x8c` at `0x513ffc`-`0x514005`, simulation.md 4.3) | CONFIRMED init; semantics partly INFERRED |
| +0x1c4 | 4 | ptr **Brain/AI** (0xb8 bytes, ctor 0x569003): +8 AI mode (1..15, jump table 0x56e470), +9 current order (1 attack, 2 cast, 3 move, other -> state 0x1b), +0x15 retry counter, +0x2 word, +0xb0 word pending dest (x lo, y hi), +0x5c target, +0x71=1, +0x16=0xffdc | CONFIRMED order dispatch 0x56dd7d-0x56dfff; field meanings INFERRED |
| +0x1c8, +0x1e4 | 0x1c | two linked lists of u16 cells (ctor 0x5420f0, block size 10): `+0x1c8` static path, `+0x1e4` dynamic path; `[list+4]` head, `[+8]` tail, `FUN_0055f170` push-front, `FUN_0055f110` pop head, `FUN_0055f0d0` peek head, `FUN_0055f0f0` peek tail ([simulation §7](simulation.md#7-pathfinding-phase-h2)) | CONFIRMED (asm) |
| +0x200 | 4 | ptr 0xc-byte object (ctor 0x54f955) | UNKNOWN |
| +0x204 | 4 | dword | UNKNOWN |
| Human only: +0x208..+0x23b | 13 x4 | equipment slot pointers (zeroed by 0x5121e1 loop <0xd) | CONFIRMED (size/loop) |
| +0x23c..+0x253 | 6 x4 | per-school values: [0] best school index, [1..5] (view +0x16c..+0x17c, sum -> view +0x110) | INFERRED (0x469c1a-0x469cbc) |

### Position (creature+0x10, 0xc bytes; ctor FUN_0054fa43, set 0x54f9b9, accessors 0x54ff5b/7c/b0/c0)
+0 cell x byte, +1 cell y byte, +2 word packed `(y<<8)+x`, +4 sub-cell x byte, +5 sub-cell y byte (0x80 = cell centre; `FUN_00551383` tests both == 0x80), +8 world ptr (0x670e48).
Full position = `cell*256 + sub` (0x54ff5b, 0x54ff7c) = same 1/256-cell unit as the file x,y. CONFIRMED.

### Mover (creature+0x1c0), Brain (+0x1c4): see table; deeper path fields (Mover +0x72 word, +0x98 flag "new path
request" 0x56e1b0, +0xa4 next dir, +0xa8/+0xaa/+0xac/+0xae words, +0xb0/+0xb1) are INFERRED/UNKNOWN (FUN_00555b38 move order,
FUN_00558b3d turn step, FUN_0055be86). Move result is sent as message 0x6d (FUN_005040c4) with direction `(mover[1]+8)>>4` (0x50ffb0-0x50ffc3).

## 3. Per-tick behaviour (CONFIRMED)
- vtable +0x18 (0x50f12c, 5d0eb0 slot 0x18): skip if state 0x10; run effects list (+0x20); if HP<=0: order=0, state=0, first time calls 0x510745 + halves defence word, +0x6c = vtable+0x74()-1 (dying time), notify 0x4001; countdown, then HP=-1000 for movementType>1, at HP<=-10 state=0x10 and FUN_00510a70 (remove from world, notify 0x282000). Else dispatch state.
- vtable +0x14 (0x50fc5a): called once per 16-tick block (job `tick&15==12`); `[0x6044c4]` is the BLOCK counter, so HP regeneration runs when `block&3 == id&3` (every 64 ticks per unit), mana every block; see [combat §12.5](combat.md#125-regeneration-vtable-0x14-fun_0050fc5a-and-the-open-question-3-of-simulationmd): HP/mana regeneration `(HP*100+acc + maxHP*2*(100+bonus)*k/regen)/100`, k=3 if FUN_0050fc3e > 0x50 else 1; HP<0 loses 1 per 4 blocks (64 ticks). Notify 0x502019 kinds 1 (HP) / 2 (mana).
- Damage code and client deltas are sent via FUN_00502019(0x6831a8, creature, kind, 0xffb, ...).

## 4. Client mirror (view unit 0x1e4, built by FUN_004699d2 from the creature) - cross-check
view+0x24 <- creature word +0xe (type T); +0x104 <- +0x94 (HP); +0x108 <- +0x96; +0x148 <- +0x9a; +0x14a <- +0x9c; +0x10c <- +0x8c; +0x10a <- +0xa4; +0x10e <- +0x90;
+0x144..+0x147 <- +0x84,+0x88,+0x86,+0x8a bytes; +0x150 <- +0xbe; +0x152 <- +0xa6; +0x14e <- +0xc0; +0x154/+0x155 <- +0xb4/+0xb5; +0x1dc <- +0x14c;
+0x156 = 2 for T in {0x46,0x49,0x68}; +0x16c.. <- human +0x240..+0x250. Known draw fields (docs/formats/animation.md): facing +0x70, phase +0x74, state +0x78, action +0x8c, ticks +0xa8, death stage +0x184, pos +0x2c/+0x30.
Base view ctor 0x45fa00 initialises +4 (word id), +8, +0xc, +0x2c, +0x30 position (1/256 cell), +0x10, +0x70, +0x74, +0x84.. ; hero sprites +0x1c0/+0x1c4 (animation.md).

## 5. Section-6 record → Creature (details: [map.md part 5](../formats/map.md#part-5-players-units-items))
x (file+0), y (+4) -> placement cell >>8 (and view +8/+0xc raw); +8 u16/+10 u16 -> mapunit +8/+0xc (not used by 0x561bf9 except error text +0x3c, +0x14);
+12 u32 bit 4 -> human vs monster; +16 u32 low 4 bits -> creature +0x194/+0x19c/+0x198/+0x1a0;
+20 u32 -> template ID (`FUN_004fd5ad/4fd62f` -> list index); +24 -> owner player id; +36 s16 -> HP; +38 s16 -> maxHP (-1 = template);
+40 u32 (word) -> creature +8 (unit number) ; +44 u32 -> group number within the player (groups under player+0x28).
File+28 (item group) is resolved in the map reader and by `FUN_00564072`, which fills the pack at `+0x7c`.


Tags in §6–§12: C = CONFIRMED (address), I = INFERRED, U = UNKNOWN. Offsets in bytes; "ptr" fields are creature pointers (e.g. Brain `+0xc`/`+0x10`/`+0x28`/`+0x68` are dereferenced).
**Corrections to §1–§3:** the Brain tick (`FUN_0056dca2`, called first in `0x50f12c`) performs *all* movement and turning; state 1 only sends the client a notification (§7.5). Brain `+0x5c` is the cast-kind flag (1 = object), the real target is `+0x28`.

## 6. Tick pipeline
1. state 0x10 -> nothing. Run effects list (+0x20).
2. HP<=0 -> dying (existing doc). Else:
3. snapshot old position (x16,y16 = cell*256+sub) and old Mover facing bytes.
4. `FUN_0056dca2(creature)` = Brain tick (§8). It performs ALL movement/turning for this tick and
   sets `+0x54` (state). (Called only if `FUN_00542560()==0`; I: busy/stunned test.)
5. switch(state): 1 -> `FUN_0050ff2d(oldx,oldy,oldfacing)` = client notification only (§7.6), then `+0x58=0`;
   2 pick up item at own cell (`FUN_00553ab3`, `005539e5`, `0053cbf0`, `005108fa`); 3/0xd/0xe attack-cast phases
   (+0x58: 0 start, 5 wind-up, 7 recovery; see 0.1); 0xf use structure; 0x1b nothing.
Server-wide alternative entry: `FUN_0056dc49` loops all creatures of a world list (+0xa456c) and calls 0056dca2 (I: AI-only pass).
Order validity runs elsewhere: `FUN_00569321` (§9).

### 6.1 Attack timer details (C, 0x50f12c case 3/0xd/0xe)
Implemented and re-read in I1: [combat §4](combat.md#4-the-swing-state-3-fun_0050f12c-confirmed) (timeline, byte timers, `+0x15`/`+0x136` handshake);
the hit is [combat §5](combat.md#5-hit-resolution). Correction: vtable `+0x58` of the monster class (`0x5118be`) is the small mana-regen
recompute, not a template load; the monster template init is `FUN_00511959` (loader `FUN_005114f3`, equipment strings, then the merge `FUN_005113e7`).
phase 0: start -> `FUN_00516b2f(creature, target+0x5c, &extra)` (melee start, picks swing, `extra=(sVar1*256+128)/200` if sVar1>1);
sets `+0x136=0`, `+0x58=5`, `+0x6c = +0x134` (wind-up ticks) (+extra for melee; spells: +0x134 only).
phase 5: `+0x6c--`; at 0: melee `FUN_00516c1f(creature,target)` -> vcall target+0x2c => `FUN_00516ceb` (creature target),
+0x34 => `FUN_00516ea0` (structure target), else log "I don't know how to attack"; spells `FUN_00519d7f` (object) / `00519db8` (cell).
Then `+0x58=7`, `+0x6c = +0x135 + L + rand(0..3)` where, for humans with weapon (+0x74): `L = clamp((weapon.s16(+0x4a) + (0x1e - reaction(+0x86))*5)/12, 0, 12)` (I: weapon speed term), else L=0;
spell with weapon-object: `+ byte FUN_0041e7e0(0)`. phase 7: `+0x6c--`; at 0: `+0x58=0`, `+0x136=1` (done; Brain then clears order 1/2).
`rand(n)`=FUN_0051fa25: `rand15*(n+1)>>15` (0..n incl.), rand15 = CRT-style `FUN_00583290` (0..0x7fff).

## 7. Mover
Creature init sets facing +0 = +1 = 0x40+rand(0x80) (0x50e2ac, existing doc); data load sets +0xa (turn rate: monster param 9; humans: the recompute copies the speed byte, simulation.md 4.3;
effect kind 18 adds to it, `FUN_0051d436`).
Position object (creature+0x10, existing doc): +0 cell x, +1 cell y, +2 packed (y<<8)+x, +4/+5 sub-cell x/y; full coordinate = cell*256+sub
(`FUN_0054ff5b` x, `0054ff7c` y, `0054ff9e` packed cell, `0054ffb0` cell x, `0054ffc0` cell y; setter `FUN_0054fc41(x16,y16)` splits both). "At centre" = sub x==sub y==0x80 (`FUN_00551383`).

### 7.1 Field table
| Off | Size | Meaning | Tag |
|---|---|---|---|
| +0x00 | u8 | current facing, 0..255 clockwise from "up" (north, dy=-1); dir8 = (f+0x10)>>5; client dir16 = (f+8)>>4 | C 559195, 50ff2d |
| +0x01 | u8 | target facing (set by every turn/move command); turn done when +0==+1 | C 555c7e, 556454 |
| +0x04/+0x05 | u8 | ctor writes +5=0x41; not used as position (Position object holds sub-cell) | C ctor / U meaning |
| +0x06 | u16 | current step target cell (waypoint popped from the path list), packed (y<<8)+x | C 555c7e |
| +0x08 | u8 | ctor 5 | C ctor / U |
| +0x09 | u8 | counter of waypoints consumed since the last path request (0xff = force re-plan); re-plan when > StaticRefreshRate (map.reg Path Finding, default 16) | C 555411, 55574d; I name |
| +0x0a | u8 | turn rate (facing units per tick; default 0x10 = 22.5 deg) | C 5551ef, 556454 |
| +0x6c | u32 | set to 1 by mode-1 move (56e4ac); no reader seen | C set / U |
| +0x70 | u16 | cell where the current step began (packed) | C 555c7e |
| +0x72 | u16 | `FUN_0055687d` result after entering a new cell: ground (movementType 1): speed*8/cost(cell); movementType 2,3: speed; else 0 (I: effective speed, feeds nothing seen) | C calc / I use |
| +0x74 | u16 | path destination cell currently planned for (compare with requested dest) | C 555411 |
| +0x76 | u16 | last cell of the planned path (= dest if reachable, else nearest reachable); path "complete" when position == +0x76 | C 555411, 569321 |
| +0x78 | u8 | ticks waited at a cell centre (blocked/waiting counter); compared with DynamicRefreshRate (default 32); reset 0 on every step start | C 555411 |
| +0x7c | u32 | object ptr being followed (FUN_0055574d); 0 otherwise (cleared by stop) | C 55574d, 56d969 |
| +0x80 | u16 | stamp cell: the cell word the last `FUN_0055be86` stamped for (mode 0 = next cell, mode 1 = own cell, mode 2 = 0). A unit at a centre with `+0x80` neither 0 nor its own cell (e.g. cancelled while turning) stamps its own cell again (`FUN_00558b75`); engine `Mover.stamp_cell`, `movement.restamp_displaced` | C 56d969, 56a1fb, 55c1b6-55c1de |
| +0x8a | u16 | follow bookkeeping: 0xff reset; later path length (`FUN_0055f090`) | C 55574d / I |
| +0x8c | u16 | follow: destination (packed) of last plan | C 55574d |
| +0x90 | u32 | 1 = destination reached (position==+0x76); 0 reset by every move command | C 555411, 56d032 |
| +0x94/+0x96 | u16 | follow: `+0x94` = target cell, `+0x96` = my cell when the plan was made | C 55574d / I |
| +0x98 | u32 | "new path request / path exhausted" event flag. Set 1 by the move drivers when the path list is empty (555581, 55597b, 555f47, 431bbb); consumed (cleared) at the end of the Brain tick, which then reacts by creature order id (§8.3) | C |
| +0x9c | u8 | 0 on next waypoint (555c7e) | C / U |
| +0x9d | u8 | turn ticks done in current turn | C 556454 |
| +0xa0 | u32 | 1 while a multi-tick turn is in progress (>45 deg) | C 556454 |
| +0xa4 | u8 | number of ticks the current turn takes = ceil(min(angle,256-angle)/rate); 1 for an instant turn. Sent to client in the turn message (`FUN_00558b3d`) | C |
| +0xa8 | u16 | step length per tick in 1/256 cell (1..63) | C 559195 |
| +0xaa | u16 | ticks to cross one cell = ceil(256/max(\|dx\|,\|dy\|)) (if dx==0 uses dy) | C 559195 |
| +0xac | u16 | tick counter within the cell step (0 at step start, +1 per tick) | C 554fd2, 555c7e |
| +0xae | u16 | step direction index dir8 (0=N,1=NE,2=E,3=SE,4=S,5=SW,6=W,7=NW) | C 559195 |
| +0xb0 | s8 | dx per tick (1/256 cell) | C |
| +0xb1 | s8 | dy per tick | C |
Direction tables in the path-finder object (world+0x58e88 dx, +0x58e90 dy, +0x58e98 packed delta dy*256+dx): dx=[0,1,1,1,0,-1,-1,-1], dy=[-1,-1,0,1,1,1,0,-1] (C, init 0x553e4e..0x553f2f).

### 7.2 Position change per tick (C, FUN_00554fd2, called from FUN_00555b38 each moving tick)
```
x16 = cell_x*256 + sub_x ; y16 likewise
steps += 1                                       # mover+0xac
nx = (x16 + s8(mover+0xb0)) & 0xffff ; ny = (y16 + s8(mover+0xb1)) & 0xffff
if dir8 in (1,5) and (nx & 0xff)==0 and (ny & 0xff)==0: nx -= 1          # corner quirk
if cell(nx)==cell_x and cell(ny)==cell_y: Position.set(nx, ny)             # same cell: just sub-cell
else: release reservation (0055be86(c,0,2)); remove from cell list (00550697);
      Position.set(nx,ny); insert in new cell (0055020a); reserve (0055be86(c, oldpacked, 0))
if steps >= mover+0xaa: sub-cell := (0x80,0x80)                              # FUN_005551d6 snap to centre
```
Step length v (mover+0xa8): `FUN_00559195` (speed/slope/cost formula already in animation.md 3.4 and map.md). Diagonals: component = trunc(v*dx*0.707) (double at 0x5d1aa8 = 0x3FE69FBE76C8B439 = 0.70699...), axis steps: v*dx. Steps per cell = ceil(256/\|larger component\|).
Speed source: `FUN_0055915a`: group byte (creature+0x70 -> +0x3c -> +0x44) if non-zero else s16 creature+0x8c. Config (map.reg `Path Finding`): SpeedMultiplier +0x58d84 (8), StaticRefreshRate +0x5858c (16), DynamicRefreshRate +0x58590 (32), DynamicByStaticLookup +0x58594 (3), StaticIsntNeeded +0x58598 (5) (C, 0x5543d9-0x5545d6; values from map.reg when present).

### 7.3 One movement tick, high level (C unless marked)
`FUN_00555b38` (continue/advance step, called while a step is in progress and as order-3 handler):
1. `FUN_00554fd2` (above). 2. If the cell changed: `mover+0x72 = FUN_0055687d(...)`.
3. If now at centre: clear +0xa8/+0xaa/+0xac; re-reserve cells (`0055be86(c,0,2)` then `(c,0,1)`); then a cell-table lookup (`FUN_0055f3e0(cell)` in a table at world+0x5402c) and, if the entry byte at world+0x54060 == 0x17, `FUN_0055a96c(creature, b+0x54064, b+0x54065)` (I: teleport/portal-like effect; not traced).
`FUN_00555c7e` (start next step, called by the move drivers when at centre and not yet at the target):
- path list (creature+0x1c8?, the linked lists built by the pathfinder `FUN_0054d76e`, [simulation §7](simulation.md#7-pathfinding-phase-h2); `+0x1c8` static, `+0x1e4` dynamic) non-empty: `+6 = front waypoint` (peeked: `FUN_0055f0d0` returns the head element's address, nothing is removed there), `+0x70 = my cell`, `+0x9c=0`, reserve target cell (`0055be86(c,+6,0)`), `+1 = FUN_0054f618(c, +6)` (target facing = dir8*32 from sign(dx),sign(dy) of the cell-centre delta).
  If `+0==+1`: `FUN_00559195(c, mycell, facing)` computes (+0xa8,+0xaa,+0xb0,+0xb1,+0xae), `+0xac=0`, first `FUN_00554fd2` immediately. Else `FUN_00556454(c, +1)` starts a turn (below); no movement this tick.
- path list empty: `FUN_005551ef` (just finish turning).
Turn (C 00556454/005551ef/00555f86): angle d = (+0 - +1) folded to 0..128. If no turn is in progress (+0xa0==0) and d<=0x20 (45 deg): facing := target instantly, +0xa4=1. Otherwise `005551ef`: if d < rate: facing := target; else facing += rate toward the target (clockwise if (f+d)&0xff==target else counter-clockwise); +0xa4 = ceil(d/rate); +0xa0=1; +0x9d++; +0xa0=0 once equal. Movement starts on a later tick once +0==+1. `00555f86` variant (turn-to-cell): instant if d<=0x20.
Move driver `FUN_00555411(c, destcell, thr)` (mode 1/9/12/15 use it; thr = allowed distance, 0 = exact):
 not at centre -> `00555b38`. At centre and `thr < dist(mycell,dest)` (`FUN_00558fe9`): `+0x78++`; if `+0x74!=dest` or `+9 > StaticRefreshRate`: request a path `FUN_0054d72d(c, x, y, 1, 0)` (A*; fills the list), `+0x90=0`, `+0x74=dest`, `+0x76` = last list cell (or my cell when no route, then `+0x98=1`), `+9=0`;
 if mycell==+0x76: `+0x90=1`; else if list empty or `+0x78 > DynamicRefreshRate`: try the next waypoint; if the cell is occupied (`FUN_0055c5a0`) ask `FUN_0056fc69` (I: swap/push a friendly blocker), on failure re-plan (`FUN_00555dc2`: picks front waypoint / DynamicByStaticLookup lookahead, calls `54d72d`, `+0x98=1` when no waypoint) and `+9++`, `+0x78=0`; then `00555c7e`.
 At centre and `thr>0` and dist<=thr: `FUN_00556da2` = turn to face dest (`00556b2c` dir to cell -> `00556454`). Object variant `FUN_0055574d(c, obj, thr)` is the same for a moving target (re-plans when the target's cell changed, `+0x7c=obj`).

### 7.4 Occupancy reservation (C 0055be86(creature, cell, mode))
Builds a 3x3-ish footprint (token size +0x49 gives `size+2` square) around the creature: mode 0 marks `cell` footprint as "reserved" (value 2, `0055c2ce`) and current footprint as value 3; mode 1 re-reserves at current cell (`+0x80 = current cell`); mode 2 releases (`+0x80 = 0`). Border cells (value 1) get `FUN_0055c1fe`. I: this is the dynamic block layer used by the path finder (Map.block local recompute).

### 7.5 Message sent to client (C FUN_0050ff2d + FUN_005040c4)
After the Brain tick in state 1: (a) position unchanged and target facing changed during the tick (`FUN_00558b3d`: old +1 != new... returns true and gives `+0xa4`) -> message **0x6d** (creature, `(facing_target+8)>>4`, turn ticks `+0xa4`); (b) the unit started this tick at a cell centre (old sub == 0x80,0x80) and moved -> message type 0 with direction pair from tables 0x5f81c0 / 0x5f8200 indexed by `dir8*2` and step count `+0xaa` (client plays one cell). So the client gets one move message per cell, at step start.

## 8. Brain
### 8.1 Field table
| Off | Size | Meaning | Tag |
|---|---|---|---|
| +0x00 | u16 | anchor ("home") cell, packed; set by orders 0xb/0xc/0x17/0xa to current (or next, order 0xb while moving: mover+6) cell | C 56d4ba..56d572, 56d6b7 |
| +0x02 | u16 | patrol: current waypoint cell (from list +0xb4); also used as idle destination | C 56d6b7, 56e2c6 |
| +0x04 | u32 | patrol flag (1 when re-evaluating) | C 56e200 |
| +0x08 | u8 | **AI mode** (0..15; 0 = no action) -> jump table 0x56e470 (§8.2) | C |
| +0x09 | u8 | **brain order** (low-level): 0 none (modes run), 1 attack swing, 2 cast, 3 move step in progress, 4 wait (status flag 0x40000), 0xff hold; other -> state 0x1b | C 56dca2 |
| +0x0a | u16 | destination cell (move/go-to/pick-up/use-structure orders), packed | C |
| +0x0c | ptr | attack target creature (order 3 / mode 2,5,6) | C |
| +0x10 | ptr | follow leader (orders 8/0x11), +0x70 follow distance (default 3, arg) | C 56d5b9 |
| +0x14 | u8 | attack range / approach distance: `FUN_0056ac5b` (spell range if brain+0x78 spell is usable (mana>=cost) else creature +0x12c); structures: 1..3 by footprint | C |
| +0x15 | u8 | retry counter (reset 0 on mode start; order 1/2 end after >2 and creature +0x136 done) | C 56dca2 |
| +0x16 | s16 | ctor 0xffdc (-36) | C ctor / U |
| +0x18 | ptr | mode 4 approach object | C 56e11b |
| +0x28 | ptr | cast target creature; +0x30 spell/effect ptr (-> creature +0x64); +0x3c u16 cast cell; creature +0x60/+0x61 get cell x,y | C 56e906, 56dca2 |
| +0x38 | u32 | **dead**: zeroed by `FUN_00570e83` for every member at each group command (and by `FUN_00570e22`, no caller); ctor memset 0; no other writer and no reader (scan of every `[reg+off]` access reached from `creature+0x1c4`, also through locals and arguments) | CONFIRMED |
| +0x40 | u32 | "Withdraw" HP threshold, **s16 HP `unit+0x94` <= it** (signed compare) and a hostile within 2 cells: `FUN_00573713` -> `FUN_0056cd11` -> `FUN_0056ce0f` ([click-to-move-research §4.5](click-to-move-research.md#45-the-post-step-fun_00573713-retreat-and-withdraw)). Monsters: data.bin p34, read from the template stream by `0x51186d` (`FUN_005114f3`). Humans: no template value, memset 0; rewritten by the player's retreat-mode message (`0x4f68f..`, `FUN_0057393c`: `maxHP(+0x96) * a / 100` by class `+0x4c`, class 0 gets `a = 0` (`push 0` at `0x4f6853`)) for every unit of the sending player that exists then: **0 for humans** | CONFIRMED |
| +0x44 | u32 | "Wimpy" HP threshold (**HP <= it** and a hostile within `mover+8 + 5` = 10 cells: `FUN_0056cb0c` -> `FUN_0056c9bc`). Monsters: data.bin p35 (`0x51187f`), `>>= 1` at map load on difficulty mode 1 (`0x561e93`..`0x561ea1`). Humans: 0, rewritten by the retreat-mode message (`FUN_00573b38`): `maxHP * x / 100` with x = 0, 10, 30 for the client option 0 (default: `view+0xab4` ctor `0x402db0`, registry value `WimpyMode` read in place by `0x4415d4`, `Ctrl+W` cycles `0 -> 1 -> 2`, sent as cmd `0x46` sub-code 1 by `FUN_0041a4ef`, at game start `0x48cb3e`) | CONFIRMED (client default 0 INFERRED: no code sets another value) |
| +0x4c | u8 | threshold class 0/1/2 for the two routines above; written only by `FUN_0057382c`, whose only caller (`0x511fb1`) is inside the **monster** recompute `0x5118be` and whose first test is `IsHuman` (vtable `+0x30`: monster `0x542420` returns 0, human `0x542730` returns 1): it returns at once. Always 0, so `FUN_0057393c` always takes class 0 (`FUN_0057393c` itself writes 0 for an unknown class) | CONFIRMED |
| +0x50 | u32 | **stopped flag** (the "arrived/stopped" state of a unit in a move group). Writers (all): `FUN_0056dbc6 := 1` (callers `0x56935c/38c/3d8` order executor `FUN_00569321`, `0x56e97b/56ea19/56ea47/56ed10` cast/pick-up/use second pass, `0x573229/0x573281` arrival in `FUN_00573198`); `FUN_0056dbfb := 0` (every order issuer, `FUN_0056dba1`, `FUN_00570e83`); ctor 0. **`FUN_0056dc24` (failure of order 1) leaves it 0** (it calls `0x56d969` and `0x56dba1` = `0x56dbfb` + `0x56d52b`, never `0x56dbc6`). Readers: only `FUN_00573198` (`0x57321c` arrival test needs 0; `0x5732a2` splits "stopped: guard scan `FUN_0056afac(u,0)`" from "not stopped: restart `FUN_0056c8af(u, brain+0xa)`") | CONFIRMED |
| +0x6c | u32 | **dead**: set to 1 only at `0x5732d3` (in `FUN_00573198`, when the group record's speed byte `+0x44` is non-zero, i.e. a formation group); never read (the `+0x6c = 1` of `0x56e4bc` is the *mover's*). It changes nothing in movement, speed (the speed base `FUN_0055915a` reads the group record) or steps | CONFIRMED |
| +0x71 | u8 | monster p36 "See invisible" (ctor 1); compared with the `FUN_00556dcd` gap of a hidden (`+0x144 & 0x1000`, Invisibility) unit at `0x567ae7` | C 5114f3, 567a16, 556dcd |
| +0x54 | u32 | idle gate for mode 11 (0 => random turns allowed) | C 56e5bc |
| +0x5c | u32 | cast target kind: 1 = object (set by 56e906), 0 = cell. Existing doc "target" is this flag; real target = +0x28 | C 56dca2 case 2, 56e906 |
| +0x60 | u32 | spell valid flag (0 -> cancel order, 56dbc6) | C 56e906, 56d969 |
| +0x68 | ptr | structure / sack object (order 0xf) | C 56d22b |
| +0x70 | u8 | follow distance | C |
| +0x78 | u8 | selected special spell/ability slot id for range (`FUN_0051c391` lookup in spellbook +0x140) | C 56ac5b |
| +0x7c,+0x80,+0x84 | u32 x3 | special-attack spell ids (monster params 48..53 pairs); +0x88,+0x8c,+0x90 their probabilities (compared with raw `rand()` in `FUN_0056acc8`) | C 56acc8 / I mapping to params |
| +0x94 | u32 | last caster ptr / +0x98 tick (`[0x6044c4]+4`) / +0x9c u16 cell: spell cast bookkeeping (FUN_0056e6b8, missile launch) | C writes / I |
| +0xb0 | u16 | pending **teleport destination** (x lo, y hi). Only writer: `FUN_005503af` (stamping a unit onto a cell) when the cell record's effect byte (`rec+0x34`, scratch `world+0x54060`) is `0x17` (the Teleport spell id): `rec+0x38/+0x39`. Only reader: the Brain tick `0x56e026`: at a cell centre `FUN_0055a96c(unit, x, y)` (validity `0x55a928`, lift `0x553891`, set position `0x54fbf7`, place `0x55020a`, **stop `0x56dba1`**, effect message `0xffb`), then cleared. The step-end code `0x555c58` calls `FUN_0055a96c` directly for the same record. No code writes `rec+0x34..+0x39` (records are memset by `0x54f89a` and filled by structure registration `0x5508a0`/saved games only), so INFERRED never set in single player | CONFIRMED code path, INFERRED dead |
| +0xb4 | ptr | patrol waypoint list (0x1c bytes, ctor 0x5420f0(10)) | C |

### 8.2 AI modes (+0x08), executed only while brain order (+0x09)==0 (C jump table 0x56e470 via 56e0b7, handlers listed)
| Mode | Handler | Behaviour |
|---|---|---|
| 0 | none | idle. The idle re-scan is only reached through the mover event flag (§8.3) or order executors (§9) |
| 1 | 56e4ac | go to cell brain+0xa: `00555411(c,dest,0)`; if not at centre afterwards: brain order=3, +0x15=0; state=1 |
| 2 | 56e8c3 | melee swing: brain order=1, +0x15=0, state=3, creature +0x5c = brain+0xc |
| 3,13,14 | - | unused |
| 4 | 56ea52 | approach object brain+0x18 within brain+0x14 (`0055574d`), state=1 |
| 5 | 56eab5 | attack with approach: if in range (`FUN_0055532d`: facing==dir to target and dist<=range) -> mode-2 swing, else approach brain+0xc |
| 6 | 56eff3 | like 5 for AI/ranged units: if ranged (`53a5a0`), range<2 and owner flag +0x2c==0: give up (mode 0); else swing if in range else step toward target (`56f0bb` dir) |
| 7 | 56ea24 | pick up item on own cell: state 2 (second pass: stop via 56dbc6) |
| 8 | 56ebc0 | cast at object brain+0x28: approach (`56ea52`) then `56e906`: brain order=2, +0x15=0, state 0xd, creature +0x5c/+0x64 from brain+0x28/+0x30, brain+0x5c=1; cancel if brain+0x60==0 |
| 9 | 56ec3f | cast at cell brain+0x3c: move there (`56e4ac`) then `56e986` (cast at cell, state 0xe) |
| 10 | 56e55d | turn in place to facing mover+1 (state 1 while turning, then mode 0, state 0) |
| 11 | 56e5bc | idle look-around: if facing==target: unless (brain+0x54==0 and rand()>0xcc) set target facing = facing + 0x21 + rand*0xbe/range, turn; else keep turning |
| 12 | 56eb2d | go to brain+0xa, then state 2 (pick up), second pass mode 0 |
| 15 | 56ecbc | go to brain+0xa then state 0xf (use structure) |
Brain order (when != 0) in the same tick function (C 56dca2 else-branch): 1 -> state=3, +0x15++, ends (order=0,state=0) when +0x15>2 and creature +0x136!=0; 2 -> state 0xd/0xe per brain+0x5c, +0x15++; at 3 sends a cast request (world+0xbd98 block, `FUN_0057b210`; type 2 object / 3 cell), ends when +0x136!=0; 3 -> `00555b38`, state=1, ends when at centre; 4 -> state 0x1b until the Stone Curse bit +0x144&0x40000 clears; 0xff -> state 0x1b; other -> order=0, state=0x1b.
Pre-checks in 56dca2: (a) (details and the wake map: [ai §15](ai.md#15-sleeping-squads-record-0x45--0x48-and-the-quest-that-sends-a-group-order-2)) if world+0xbbe8==0 and group-record +0x45 (creature+0x70 -> +0x3c -> +0x45; GroupAI object, ctor 0x5690ee, 0x50 bytes, +0x45 = 1 by default) ==0 and brain order==0 -> state 0x1b, return. (b) state := 0 unless it is 2 or 0xf. (c) `+0x144 & 0x40000` (Stone Curse) and order==0 -> brain order=4.

### 8.3 Mover event flag handling (C end of 56dca2, 0x56e1b0)
If mover+0x98 != 0: clear it, then by creature order id: **1** -> `FUN_0056dc24` (stop: cancel + stand); **0xa** (patrol) -> brain+4=1, mode=0, when within 2 cells of waypoint brain+0x2 take next waypoint from list +0xb4 (`57b020`,`55f1f0`,`55f0d0`); **0x18** -> brain order=0xff; **others** -> mode=0 and **`FUN_0056ed4e` (auto target scan)**: nearest enemy in world lists (+0xa456c list, +0xa68 visible enemies) by `FUN_005568e4` direction/`FUN_0055aa21` cost; found -> brain+0xc=target, mode 6 + `56eff3`; none: mode 0, or mode 0xb (look-around, `56e5bc`) when owner flag +0x2c != 0.

## 9. Orders (`+0x50`)
Order issuers (ECX = server order object; every one first calls `FUN_0056dbfb` = `56d969` (target facing := facing, release the reservation only if +0x80 is set, the unit is at a centre and the reserved cell is not the own one, brain+0x14=`56ac5b`, brain+0x60=0, mover+0x7c=0, state=0) and then **brain+0x50 := 0**, a "stopped" flag set to 1 only by `FUN_0056dbc6` (field table above); it does not write unit+0x50, the issuer sets that ([click-to-move-research](click-to-move-research.md) §3.4, CONFIRMED). Player command message type (byte at msg+9 in `FUN_004f515d`) -> issuer.
| Value | Meaning (I name) | Issuer / message | Brain setup | Group-order-0 executor `FUN_00569321` (run every 16 ticks by the group pass, NOT per tick; a move group (order 4) is driven by `FUN_00573198`, research §4.4) |
|---|---|---|---|---|
| 0 | none / idle | 56dbfb | - | state:=0 |
| 1 | move to cell | 56d032 (`& 0xff`, then clamps x,y to [8, size-9] of the path finder +0x58eb8..bb) / 56d158; msg 0x16 and 0x1c (both 5703c0), 0x1a (57063e, group order 5) | dest brain+0xa, mover+0x90=0, mode 1 | `56c8af`: mode 1, dest; auto-stop when mover+0x90 and mover+0x76==my cell |
| 2 | go and pick up item/sack at cell | 56da98; msg 0x21 | dest brain+0xa, mover+0x90=0, mode 0 | `56c8da` (go, mode 12 then state 2) |
| 3 | attack target | 56d1be (self target -> stop `56dba1`); msg 0x19 | brain+0xc=target, brain+0x14=range, mode 0 | `56acc8`: special spell roll (3 slots), else mode 5; stops (`56dbc6`) when target state==0x10 |
| 4 | AI-internal move to cell | 56d393 only caller 0x56f75a | dest, mode 0 | `569638` |
| 8 | follow leader | 56d5b9; msg 0x1b | brain+0x10=leader, +0x70=dist (default 3), mode 0 | `5696e8` (engine `follow.exec_defend`, [ai §14.2](ai.md)); stops when leader state==0x10 |
| 0xa | patrol along waypoint list | 56d6b7 (add), 56d7b5 (rotate), 56d850 (AI); msg 0x1d | anchor=my cell, waypoints list +0xb4, brain+2 | `569b62` (engine `follow.exec_patrol`); flag handling 2.3 |
| 0xb | stand (at next cell if moving) | 56d4ba; msg 0x17 | anchor = mover+6 if not centred else my cell, mode 0 | `569cc9` -> `56a5fc` |
| 0xc | stand / guard here | 56d52b (also what Stop = `56dba1` issues); msg 0x18 | anchor = my cell, mode 0 | `56a1fb`: scan enemies in range (range+1), nearest by distance then cost -> attack (`56c840`) else idle (`56afd9`) |
| 0xd | cast at object | 56d3e6; msg 0x1e (5702be), 0x25 | brain+0x28 obj, +0x30 spell, +0x14 range | `56c72b` |
| 0xe | cast at cell | 56d446; msg 0x1f (57033d), 0x26 | brain+0x3c cell, +0x30 spell | `56969c` |
| 0xf | use structure/sack | 56d22b (obj centre cell, size 1..4 -> offsets +0/+0x101/+0x202); msg 0x24 | brain+0x68 obj, dest, +0x14=1..3 | `56af23` (state 0xf, tick case 0xf) |
| 0x10 | removed/dead (set by 510ad6 on removal) | - | - | - |
| 0x11 | follow variant | 56d638 | like 8 | `569857` (engine `follow.exec_follow`) |
| 0x16 | (U) mode-0 order | 56da4f; msg 0x14 | none | `56c9bc` |
| 0x17 | stand variant (anchor = my cell) | 56d572; msg 0x12 | anchor | default branch -> `56afac(c,0)` = `56a1fb` |
| 0x18 / 0x19 | (U) set only (56db41, 56db71) | - | - | `56f492` / `56f71a`; 0x18 also special-cased at 2.3 |
| 0x1a | (U) | 56dafe; msg 0x13 | mover+0x90=0 | `56a909` (path to nearest..., mode 0xc) |
| 0x1b | wait | 573736 (state/other object) | - | state:=0x1b |
Default order of the default-stat creature template `FUN_0050ec60` is 0xb (body 30, reaction 30, mind 20, spirit 20, speed 10) (C); `FUN_0050e173` init sets 0.

## 10. States (`+0x54`)
| Value | Meaning | Writers (examples) |
|---|---|---|
| 0 | idle / standing | many (56dd1d, 56d969, 56dbfb) |
| 1 | moving: client gets turn/move message; movement itself already done by the Brain | 56e4ac, 56ea52, 56e55d, 56dca2 |
| 2 | pick up item at own cell (tick case 2) | 56ea24 (mode 7), 56eb2d (mode 12) |
| 3 | melee attack (phases via +0x58: 0 start, 5 wind-up, 7 recovery) | 56e8c3 (mode 2), 56ddb4 |
| 0xd | cast at object (+0x5c target, +0x64 spell) | 56e906, 56de25, 4f0859 (carrier) |
| 0xe | cast at cell (+0x60,+0x61) | 56e986, 56de31, 4f0896 |
| 0xf | use structure at cell (tick case 0xf: potions, doors etc. by type) | 56ecbc (mode 15) |
| 0x10 | dead + removed from world | 50f299, 510ac9 |
| 0x1b | AI standby/no-op (no tick case) | 56dce0, 56dfca, 56dff6, 56e00f |

## 11. Sub-objects
Blocks use two layouts (C copy/add routines 0x5159cb/0x515617/0x5156bf):
**Armour block B (0x16 bytes)**: +0 s16 defence, +2 s16 absorption, +4..+0xe 6 x s16 protection[phys, fire, water, air, earth, astral], +0x10..+0x15 6 x u8 resistance[0 (phys?), Blade, Axe, Bludgeon, Pike, Shooting]. Instances: base **+0xbe..+0xd3** (monster params 15,16,19-23,24-28 = defence, absorbtion, prot Fire..Astral at +0xc4..+0xcc, res Blade..Shooting at +0xcf..+0xd3; +0xc2 and +0xce have no loader), item bonus **+0xfe..+0x113** (humans: effect kinds 15,16,20-25 add here; equipping an item adds `item+0x56` block to +0xbe and +0xfe, `FUN_00527a13`).
**Attack block A (0x18 bytes) +0xa6..+0xbd**: +0xa6 s16 attack skill / toHit (monster param 14; humans 0), +0xa8..+0xb2 6 x s16 skills [general, Blade(Fire), Axe(Water), Bludgeon(Air), Pike(Earth), Shooting(Astral)] (human params 10-15 at +0xa8..; monster toHit also copied to +0xa8), +0xb4/+0xb5 u8 damage min / spread (kind 0; bit7 of +0xb4 = x15 scaling when min>=0x80 or spread>min+255), +0xb7/+0xb8 kind 1 min/spread, +0xb9/+0xba kind 2 (stored negated), kind 3 -> +0x4c|=0x10 and +0xb4/+0xb5; +0xbb u8 copied (U). (C 0x5114f3; kind names U: attackKind column.)
**Bonus accumulators +0xd4..+0x113 (0x40 bytes, ctor 0x511266)**: filled by effect application `FUN_0051d436` (effect kind = index into data.bin stats names; amount = value*stack; flag +0x3d&8 = skip the byte tracker). Fields: +0xd4 u8 body, +0xd5 u8 reaction, +0xd6 u8 mind, +0xd7 u8 spirit (non-permanent running totals); +0xd8 s16 speed bonus (human; monsters add to +0x8c directly); +0xdc s16 max HP bonus (kind 7 also adds to HP +0x94 — the exe adds to +0x94, not +0x96); +0xde s16 HP regen bonus (kind 8); +0xe0 s16 max mana bonus (kind 10, also mana +0x9a); +0xe2 s16 mana regen bonus (kind 11); +0xe4 s16 scan range bonus x256 (kind 19; monsters: +0xa4); +0xe6 s16 toHit bonus (kind 12); +0xe8..+0xf2 6 x s16 skill bonuses (kinds 26-31 fighter [general,Blade..Shooting], 32-37 mage [general,Fire..Astral] share the same 6 words, guards `FUN_00542c90`/`FUN_0053a5a0` U); +0xf4 u8 damage-min bonus (kinds 13, 43 damage, 49 damageBonus), +0xf5 u8 damage-max bonus (kind 14); +0xf9/+0xfa/+0xfb elemental damage min/max/element(1..5 = kinds 44-48 damageFire..Astral); +0xfe..+0x113 armour block B (human defence, absorption, 6 protections, 6 resists).
Direct effect writes: kind 2 body +0x84, 3 mind +0x88, 4 reaction +0x86, 5 spirit +0x8a (all capped 100), 6 health +0x94 (cap +0x96), 9 mana +0x9a (cap +0x9c), 15/16 monster defence +0xbe / absorption +0xc0, 17 monster speed +0x8c, 18 mover+0xa, 42 teachSpell (spellbook +0x140). Then vtable+0x58 (recompute from template + bonuses, 0x5118be monsters).
**+0x114..+0x12b (0x18)**: human copy of the school skills 1..5 at +0x118..+0x120 (word k at +0x116+2k), taken from +0xa8+2k at load; +0x23c = index (1..5) of the highest school skill when the template name contains "Hero"/"Start" (`FUN_00514cf2`). C.
**Effect mask +0x144 / client update mask +0x150** (corrected, [effects §7](effects.md#7-the-effect-pass-and-the-effect-mask): the stat-class bits below belong to `+0x150`, `+0x144` holds only `1 << effect id`): effect application ORs a bit per stat class (e.g. 1 HP, 2 mana, 4 skills, 0x4000 defence, 0x8000 absorption, 0x10000 toHit, 0x20000 damage, 0x40000 scan range, 0x80000 speed, 0x100000 spell taught, 0x1000000 protections, 0x2000000x attributes); `+0x144` = `1 << effect id` (`FUN_0051ce12` sets, `FUN_0051cc9f` clears; 0x1000 = Invisibility, read by the AI pool/flee list `FUN_00567a16`; 0x40000 = Stone Curse, Brain order 4 waits, C 56dd39). I: pending client sync; +0x150 gets 0xc000 on equip (C 527b00).
**Other**: creature +0x70 = ptr to the owner's group (0x50-byte object, ctor 0x52ae43; group +0x3c -> GroupAI object (0x50 bytes, ctor 0x5690ee): +0x44 u8 group speed, +0x45 u8 active flag default 1) (C 52af8c, 55915a); +0x12c u8 = default attack range in cells (fallback of `56ac5b`) (I).

## 12. Human equipment slots
| Slot | Offset | Fighter set (`in.<slot>` col) | Mage set |
|---|---|---|---|
| 1 | +0x20c | Weapon (weapons class, all Slot=1) | Weapon |
| 2 | +0x210 | Shield (class `shields`, Slot=2) | - |
| 3 | +0x214 | notUsed3 | notUsed |
| 4 | +0x218 | Ring | Ring |
| 5 | +0x21c | Amulet | Amulet |
| 6 | +0x220 | Helm | Hat |
| 7 | +0x224 | Mail | Robe |
| 8 | +0x228 | Cuirass | Cloak |
| 9 | +0x22c | Bracers | notUsed |
| 10 | +0x230 | Gauntlets | Gloves |
| 11 | +0x234 | notUsed11 | notUsed11 |
| 12 | +0x238 | Boots | Shoes |
(+0x208 slot 0 and the 13th word up to +0x23b are never used by the item data: armour Slot values present: 4,5,6,7,8,9,10,12.) Equip: `FUN_00527a13(this=item, creature)` humans only (vtable+0x30); previous item un-equipped via vtable+0x3c; stat blocks added (above). Paper doll layer numbers P0..P11 = slot-1 (paperdoll.md), so P0 weapon, P1 shield, P3 ring... INFERRED consistent.

## Handoff to game data

For the engine's units (G3a): the creature needs, from data: the data.bin record (`+0x3c`: params
by column name, [databin](../formats/databin.md)), the units.reg type (`+0xe`, [units](../formats/units.md)),
the player and its colour ([map.md part 5](../formats/map.md#part-5-players-units-items)); phase F
supplies the item tables for the pack (`+0x7c`), the weapon / second item (`+0x74`, `+0x78`) and
the 13 equipment slots (human `+0x208`). Id tables: units.reg, data.bin groups 3–6 and 8, item codes.

## Cell record effect (CONFIRMED)

Cell record effect `+0x34..+0x39`: `FUN_0055ba36(cell, effect6)` (`0x55ba36`) copies a 6-byte effect (`FUN_0055b978`) into the record, creating it when missing (`FUN_005508a0`); refused when the live cell has bit 0 set (`+0x20000 & 1`).
  Its only callers are `0x564280` (map load `FUN_00562745`, from a map record: x/y at `+8`/`+0xc`, effect bytes from the list at `+0x1a`) and `0x57853b` (scenario instant function `FUN_0057847e`, effect from args `+0x18..+0x24`). Readers: place (`0x5503af`, on entering a cell) and step end (`0x555c50`): id `0x17` = Teleport -> `brain+0xb0 = (rec+0x39 << 8) | rec+0x38`, consumed by `FUN_0055a96c`; other ids start a spell via `FUN_00519408` / server `0x4f0832`/`0x4f086f`. `CMap::Serialize` of the record table (`0x55f6b0`, raw `0x3c` bytes per record via `0x55fff0`) has no direct caller (vtable `0x5d1ab8` slot 8 only), so records are not restored from a stream. **Feeders (CONFIRMED by a census of the 46 campaign maps)**: map section 9 per-cell payloads (30 records in maps 76, 93-96, [map](../formats/map.md#open-questions)) and the Set trap instant 25 ([triggers §4](triggers.md#4-instants-fun_00574f3f); 9 records in maps 53, 93-96). The engine has no cell effects (needs the spell system).

## Open questions

- Not traced: the structure damage `0x516ea0` (an attack on a structure, [combat](combat.md) section 10), the wire format of `FUN_005040c4` (client message sender; the simulation does not need it).
- Meaning of the event classes of the three scenario booleans `+0x194`, `+0x198`, `+0x19c` (`FUN_005303ed`).
