# `world/data/data.bin`: the game database

Code: `allods2/databin.py`. Tool: `tools/validate_databin.py`.

An MFC `CArchive` stream (153,528 bytes in 1.30) holding the item, unit,
structure and spell tables the server builds units and effects from.
Loader `FUN_00502b5a` (path `<dir>Data.bin`, `CArchive` load mode,
buffer 0x1000) → serializer `FUN_00503833`; `FUN_00502eec` is the
matching writer (store mode). CONFIRMED (REA), and the decoder consumes
the shipped file exactly.

## Primitives (MFC 4)

| Item | Encoding | Routine |
|---|---|---|
| count (string array) | u16; `0xffff` → u32 follows | `FUN_005b4bfb` (ReadCount) |
| list count | u32 | `FUN_00545aa0` |
| CString | u8 length; `0xff` → u16; `0xffff` → u32; then cp1251 bytes | `FUN_005b4577` |
| string array | count + CStrings | `FUN_005a901a` (CStringArray::Serialize) |
| param array | count + that many i32 | `FUN_00543320` → `FUN_00423580` |

## Layout

Eight groups, each opening with a string array (empty in 1.30), then one
or three lists. A list is `u32 n` + records; **1-based** lists serialize
elements `1 … n−1` (element 0 exists in memory only), 0-based lists all
`n`.

| # | List | Base | Records (1.30) | Record class (vtable, Serialize) | Accessor |
|---|---|---|---|---|---|
| 1 | qualities | 0 | 7 (`Common` … `Good`) | `0x5dac78`, `FUN_00506fff` | `FUN_00548070` |
| 1 | materials | 0 | 16 (`Iron` … `None`) | same | same |
| 2 | stat names | 0 | 50 (`""`, `price` … `damageBonus`) | `0x5dacb8`, base | `FUN_00548110` |
| 3 | armour, shields, weapons | 1 | 30, 9, 27 | `0x5dac20`, `FUN_00506fa3` | `FUN_005480b0` |
| 4 | special items | 1 | 150 (books, scrolls, potions, quest items) | `0x5dac98`, `FUN_00507107` | `FUN_0043cbd0` |
| 5 | monsters | 1 | 246 (185 named) | `0x5dacd8`, `FUN_00507486` | `FUN_00421130` |
| 6 | humans | 1 | 298 (293 named) | `0x5dacf8`, `FUN_00507d03` | `FUN_004ade80` |
| 7 | structures | 1 | 179 | `0x5dad18`, base | `FUN_004adea0` |
| 8 | spells | 1 | 34 (29 named) | `0x5dad38`, `FUN_00508293` | `FUN_00548170` |

Record contents (CONFIRMED by the Serialize routines):

| Kind | Fields in file order |
|---|---|
| quality / material | CString name; 0x48 bytes to `+0x20`: 16 bytes (zero) + 7 × f64 |
| base (`FUN_00506f55`) | CString name (`+4`); param array (object at `+8`) |
| item class | base; 7 × i16 (`+0x1c`); string array (`+0x2c`) |
| special item | base; u8 (`+0x1c`); CString (`+0x40`, e.g. `castSpell=Fire_Arrow:50`, quest `1`) |
| monster | base; 2 CStrings (equipment text, e.g. `Bronze Pike`) |
| human | base; 10 CStrings (equipment) |
| structure | base |
| spell | base; CString (modifier text) |

`FUN_00421110(k)` returns `&params[k]` of a record (templates keep the
record at `obj+0x3c`, params at `+8`).

## Factors (qualities, materials)

Item weight uses f64 #1 (record `+0x38`) of both lists (below). Values:
Common 1.0, Uncommon 1.1, Rare 1.2, Very Rare 1.3, Elven 1.0; Iron 1.0,
Bronze 0.5, Steel 1.3, Wood 0.5, Leather 0.2, Mithrill 0.5, Crystal 2.0.
INFERRED: f64 #0 is a price factor (1, 2, 4, 10 for Common … Very Rare).

## Stat names and modifier text

The 50 stat names are also built into the exe (table at `0x603190`,
lowercase, same order; CONFIRMED by comparison). A stat's index is the
**effect kind**: `FUN_00527122` switches on effect `+0x3c` (2 body →
`+0x84`, 3 mind → `+0x88`, 4 reaction → `+0x86`, 5 spirit → `+0x8a`,
17 speed, 18 rotationSpeed → `mover+0xa`; CONFIRMED).

Modifier text `name=value[:time]` (spell texts, items), one term parsed
by `FUN_005285cb` (how multi-term texts such as Stone Curse's
`"absorbtion=+5:duration 8,defence=-20:duration 8"` are split is not
traced): kind = index of `name` (compared
case-insensitively) → effect `+0x3c`; `+0x40` = value; time part by
`FUN_00528f6d`: `permanent` → mode 0, `singleuse` 8, else the first of
`charges N` (4), `duration N` (1), `continuous N` (2) found; `+0x3d` =
mode, `+0x42 = N << 4` (ticks). `castSpell`, `teachSpell` and the
`damage*` kinds parse their values differently (`FUN_00528e94`,
`FUN_00528d43`; not decoded). On apply, delta = ±`+0x40`
(`0x527182`; sign INFERRED: + on start, − on expiry).

Example: Haste `speed=+2: duration 30` → kind 17, +2 speed for
30 · 16 = 480 ticks (30 s at 16 ticks/s); Slow `speed=-2: duration 30`.

## Parameter maps

**Monsters** (CONFIRMED `FUN_0051b12f`: a cursor reads params in order;
`-1` keeps the default; `MONSTER_PARAMS` in the code):

| Index | Field | Index | Field |
|---|---|---|---|
| 0–3 | body `+0x84`, reaction `+0x86`, mind `+0x88`, spirit `+0x8a` | 17, 18 | attack windup `+0x134`, recovery `+0x135` |
| 4 | max HP `+0x96` (and HP `+0x94`) | 19–23 | `+0xc4 … +0xcc` (5 × s16) |
| 5 | `+0x98` | 24–28 | bytes `+0xcf … +0xd3` |
| 6 | max mana `+0x9c` (`+0x9a`, `+0xa0`) | 29 | `+0xe` = units.reg type ID (Goblin_Pike 64) |
| 7 | `+0x9e` | 30–32 | bytes `+0x4b`, `+0x49`, `+0x4a` |
| 8 | **speed** `+0x8c` | 33 | read, unused |
| 9 | **turn rate** `mover+0xa` | 34–36 | `+0x1c4` object `+0x40`, `+0x44`, `+0x71` |
| 10 | `+0xa5` | 37 | `+0x1c` (also re-read by `FUN_0051b595`) |
| 11–13 | damage min, max, kind (`+0xb4`/`+0xb5`, `+0xb7`…`+0xba`) | 48–61 | `FUN_0051b595`: 48–53 three (spell id, value) pairs (effects `FUN_00522d34`), 54 → `+0xaa … +0xb2` (five copies), 55 → `+0x14c`, 56 spell bit mask, 57–61 → `+0xaa … +0xb2` |
| 14 | `+0xa6` (and `+0xa8`) | 15, 16 | `+0xbe`, `+0xc0` |

Monster creation `FUN_0051b595(name)` searches the list by name from
index 26 upward, skipping 30 … 62 (CONFIRMED); the index is the unit's
template id. Examples (base `.1` / `.5`): Goblin_Pike speed 24/27, turn
16/27, attack 7 + 3; Ogre 15/18, 12/18, 12 + 6; Troll 8/11, 8/11, 10 + 6;
Catapult speed 8, turn 8, attack 2 + 38.

**Items** (class lists; CONFIRMED `FUN_005329b4`, `FUN_00532dee`):
`param[3]` → `item+0x4a` **weight** = `round(param[3] · quality.f64[1] ·
material.f64[1])` (+0.5, `ftol`); inventory adds `weight · count`
(`+0x42`) to the pack total (`FUN_00533804`), which the hero recompute
compares with capacity `Body·10 + 1` (CONFIRMED). `param[12]`, `[13]` →
attack windup/recovery (kept when −1). Also `param[6]`→`+0x68`,
`[7]`→`+0x69`, `[8]`→`+0x5a`, `[9]`→`+0x72`, `[11]`→`+0x58` (default 1).
INFERRED: `[6]`, `[7]` damage, `[2]` price. Long Sword: weight 20,
attack 7 + 4.

**Spells**: `param[5] == 2` = missile, `param[7]` = missile speed in
1/256 cell per tick (Fire Arrow 200, Fire Ball 384, Lightning 60);
[animation §3.4](animation.md#34-where-the-speeds-come-from).

## Open questions

- Humans and structures: parameter maps (loaders via `FUN_004ade80`,
  `FUN_004adea0`); 7 × i16 of item classes; factors f64 #0, #2–#6;
  special-item byte; `castSpell`/`damage*` modifier values
  (`FUN_00528e94`, `FUN_00528d43`).
