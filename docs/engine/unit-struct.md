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
1. owner: `FUN_0051680d(0x68d2c4 player mgr, mapunit+0x14 as word)`; missing -> error log + skip. If `[0x6044c4+0x174]` and `player+0x2c` both set -> skip (INFERRED: inactive slot / multiplayer filter).
2. alloc + ctor by template name (above). Difficulty tweak (`[0x6044c4+0xd8]`: 2 skip; 1: maxHP*=const `0x5d1b00`, HP=maxHP, brain+0x44>>=1; else +0x32 to words +0xa6,+0xbe and maxHP*=`0x5d1b08`). CONFIRMED 0x561e20-0x561f0b (meaning of the +0xd8 modes INFERRED).
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
| +0x20 | 0x1c | list sub-object (ctor 0x541de0; iterated in tick 0x50f17c, each entry vtable+0x38(creature): timed effects list) | INFERRED (effects/auras) |
| +0x3c | 4 | ptr to data.bin record (params at record+8; `FUN_0041e7e0(k)`) | CONFIRMED 0x4a4b54, 0x514850 |
| +0x40 | 4 | dword, reset 0 | UNKNOWN |
| +0x44 | 4 | dword | UNKNOWN |
| +0x48 | 1 | byte (0 init) | UNKNOWN |
| +0x49 | 1 | param (monster 31 / human 21 TokenSize) | CONFIRMED loader (0x514f37) |
| +0x4a | 1 | param (monster 32 / human 22 MovementType); `>1` => HP set to -1000 in death (0x50f273) | CONFIRMED |
| +0x4b | 1 | param face / palette variant (human 17, monster 30); bit 7 |= gender (0x514bdc) and `|=0x80` when item[0x12] nonzero (0x4a4be3) | CONFIRMED |
| +0x4c | 1 | caster flags: |=2/4/6 if maxMana (+0x9c) > 0 | CONFIRMED 0x514907/0x4a4c93 |
| +0x50 | 4 | current **order id** (0 none, 1 and 0xa special-cased by AI 0x56e1d3/0x56e1ed; 0xb at 0x50ec6a; 0x10 on removal) | CONFIRMED set sites; per-value meaning INFERRED |
| +0x54 | 4 | **state** executed by tick FUN_0050f12c: 0 idle, 1 move step, 2 pick up item at cell, 3 melee attack, 0xd cast/shoot at target object (+0x5c), 0xe cast at cell (+0x60,+0x61), 0xf use structure at cell, 0x10 dead/removed, 0x1b AI wait | CONFIRMED jump table 0x50fc17 / byte table 0x50fc2f; writers 0x56ddb4,0x56de25 etc. |
| +0x58 | 4 | attack sub-phase: 0 start, 5 wind-up counting, 7 recovery | CONFIRMED 0x50f3b3-0x50f68c |
| +0x5c | 4 | target object id (state 0xd) / spell arg | CONFIRMED 0x4f0866, 0x56de89 |
| +0x60,+0x61 | 1,1 | target cell x,y (state 0xe) | CONFIRMED 0x4f08a3 |
| +0x64 | 4 | spell/effect object ptr (carrier) or weapon attack id (copied from weapon +0x84) | CONFIRMED 0x4f0808, 0x50f41e |
| +0x68 | 4 | weapon/attacker object (or 0) | CONFIRMED 0x50f42a |
| +0x6c | 1 | tick timer: wind-up/relax countdown (loaded from +0x134/+0x135) and death timer (vtable+0x74 -1) | CONFIRMED 0x50f22a, 0x50f4d8 |
| +0x70 | 4 | dword, 0 on init/copy | UNKNOWN |
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
| +0x12c | 1 | byte copy | UNKNOWN |
| +0x130 | 4 | dword | UNKNOWN |
| +0x134 / +0x135 | 1 | attack wind-up / recovery ticks (monster 17/18, human 19/20; human default 8/4) | CONFIRMED 0x5122a4, 0x514f14 |
| +0x136 | 1 | "attack done" flag (set 1 init, 0 when a swing starts) | CONFIRMED 0x50e309, 0x50f4bb |
| +0x138 | 4 | dword | UNKNOWN |
| +0x13c | 1 | death handled flag (set 1 first tick with HP<=0, calls FUN_00510745) | CONFIRMED 0x50f1f1 |
| +0x140 | 4 | spellbook object (0x1c bytes, ctor 0x53a600; spells added by 0x51c29e) created if maxMana>0; also built for carriers | CONFIRMED 0x514abf-0x514b00 |
| +0x144 | 4 | status flag bits (0x40000 tested by AI at 0x56dd39) | CONFIRMED test; other bits UNKNOWN |
| +0x148 | 4 | dword (view +0x148 = 16 bit) | UNKNOWN |
| +0x14c | 2 | **server/type id** (data param "serverID": human 24, monster 55; values >10000 reduced by (v/10)%1000) | CONFIRMED 0x4a4b8f, 0x4a4bb2, 0x4f3420 |
| +0x150 | 4 | dword 0 | UNKNOWN |
| +0x154 | 0x40 | zeroed buffer | UNKNOWN |
| +0x194,+0x198,+0x19c,+0x1a0 | 4 each | scenario flags from mapunit+0x50 bits 0,2,1,3 (file+16); +0x1a0 also set to 1 at 0x51a7cf/0x560c20 | CONFIRMED set; semantic UNKNOWN |
| +0x1a4,+0x1a6 | 2 | word pair (read by messaging 0x502019, 0x52b368) | UNKNOWN |
| +0x1a8 | ~0x18 | object (ctor 0x59f003) | UNKNOWN |
| +0x1c0 | 4 | ptr **Mover** (0xb4 bytes, ctor 0x551346, zeroed then +5=0x41, +8=5, +9=0xff, +0xa=0x10); +0 and +1 are facing bytes (init `0x40+rand(0x80)`, 0x50e2ac), +0xa turn rate (human param 7) | CONFIRMED init; semantics partly INFERRED |
| +0x1c4 | 4 | ptr **Brain/AI** (0xb8 bytes, ctor 0x569003): +8 AI mode (1..15, jump table 0x56e470), +9 current order (1 attack, 2 cast, 3 move, other -> state 0x1b), +0x15 retry counter, +0x2 word, +0xb0 word pending dest (x lo, y hi), +0x5c target, +0x71=1, +0x16=0xffdc | CONFIRMED order dispatch 0x56dd7d-0x56dfff; field meanings INFERRED |
| +0x1c8, +0x1e4 | 0x1c | two arrays of 10 (ctor 0x5420f0(10)) | UNKNOWN |
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
- vtable +0x14 (0x50fc5a): every 4th tick (`[0x6044c4]&3 == id&3`): HP/mana regeneration `(HP*100+acc + maxHP*2*(100+bonus)*k/regen)/100`, k=3 if FUN_0050fc3e > 0x50 else 1; HP<0 loses 1 per 4 ticks. Notify 0x502019 kinds 1 (HP) / 2 (mana).
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

## Handoff to game data

For the engine's units (G3a): the creature needs, from data: the data.bin record (`+0x3c`: params
by column name, [databin](../formats/databin.md)), the units.reg type (`+0xe`, [units](../formats/units.md)),
the player and its colour ([map.md part 5](../formats/map.md#part-5-players-units-items)); phase F
supplies the item tables for the pack (`+0x7c`), the weapon / second item (`+0x74`, `+0x78`) and
the 13 equipment slots (human `+0x208`). Id tables: units.reg, data.bin groups 3–6 and 8, item codes.

## Open questions

- Mover (`+0x1c0`, 0xb4 bytes) and Brain (`+0x1c4`, 0xb8 bytes) interiors, the `+0x1c8` / `+0x1e4`
  arrays, the sub-objects at `+0xa6`, `+0xbe`, `+0xd4`, `+0x114` field by field, equipment slot
  meaning, `+0x50` order values, spell-carrier layout (`0x4f06ac`).
- Meaning of the booleans `+0x194`–`+0x1a0` (section 6 `behaviour`).
