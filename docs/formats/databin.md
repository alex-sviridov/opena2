# `world/data/data.bin`: the game database

Code: `allods2/databin.py` (`databin(fs)`, `DataBin.columns`). Tool:
`tools/validate_databin.py`.

An MFC `CArchive` stream (149,971 bytes, in `world.res`) holding the item, unit,
structure and spell tables the server builds units and effects from.
Loader `FUN_004f9fb0` (path `<dir>Data.bin`, `CArchive` load mode,
buffer 0x1000) → serializer `FUN_004fac89`; `FUN_004fa342` is the
matching writer (store mode). CONFIRMED (REA), and the decoder consumes
the shipped file exactly.

## Primitives (MFC 4)

| Item | Encoding | Routine |
|---|---|---|
| count (string array) | u16; `0xffff` → u32 follows | `FUN_005aab7b` (ReadCount) |
| list count | u32 | `FUN_0053bb70` |
| CString | u8 length; `0xff` → u16; `0xffff` → u32; then cp1251 bytes | `FUN_005aa4f7` |
| string array | count + CStrings | `FUN_0059ef9a` (CStringArray::Serialize) |
| param array | count + that many i32 | `FUN_005393b0` → `FUN_005394d0` |

## Layout

Eight groups, each opening with a string array (the group's column
names, § Column names), then one or three lists. A list is `u32 n` + records; **1-based** lists serialize
elements `1 … n−1` (element 0 exists in memory only), 0-based lists all
`n`.

| # | List | Base | Records | Record class (vtable, Serialize) | Accessor |
|---|---|---|---|---|---|
| 1 | qualities | 0 | 7 (`Common` … `Good`) | `0x5d0a28`, `FUN_004fe455` | `FUN_0053e160` |
| 1 | materials | 0 | 16 (`Iron` … `None`) | same | same |
| 2 | stat names | 0 | 50 (`""`, `price` … `damageBonus`) | `0x5d0a68`, base | `FUN_0053e200` |
| 3 | armour, shields, weapons | 1 | 30, 9, 27 | `0x5d09d0`, `FUN_004fe3f9` | `FUN_0053e1a0` |
| 4 | special items | 1 | 96 (books, scrolls, potions, quest items) | `0x5d0a48`, `FUN_004fe55d` | `FUN_00439df0` |
| 5 | monsters | 1 | 241 (180 named) | `0x5d0a88`, `FUN_004fe8dc` | `FUN_0041e890` |
| 6 | humans | 1 | 289 (284 named) | `0x5d0aa8`, `FUN_004ff159` | `FUN_004a65b0` |
| 7 | structures | 1 | 179 | `0x5d0ac8`, base | `FUN_004a65d0` |
| 8 | spells | 1 | 34 (29 named) | `0x5d0ae8`, `FUN_004ff6e9` | `FUN_0053e260` |

Record contents (CONFIRMED by the Serialize routines):

| Kind | Fields in file order |
|---|---|
| quality / material | CString name; 0x48 bytes to `+0x20`: 16 bytes (zero) + 7 × f64 |
| base (`FUN_004fe3ab`) | CString name (`+4`); param array (object at `+8`) |
| item class | base; 7 × i16 (`+0x1c`); string array (`+0x2c`) |
| special item | base; u8 (`+0x1c`); CString (`+0x40`, e.g. `castSpell=Fire_Arrow:50`, quest `1`) |
| monster | base; 2 CStrings (equipment text, e.g. `Bronze Pike`) |
| human | base; 10 CStrings (equipment) |
| structure | base |
| spell | base; CString (modifier text) |

`FUN_0041e7e0(k)` returns `&params[k]` of a record (templates keep the
record at `obj+0x3c`, params at `+8`).

## Factors (qualities, materials)

Item weight uses f64 #1 (record `+0x38`) of both lists (below). Values:
Common 1.0, Uncommon 1.1, Rare 1.2, Very Rare 1.3, Elven 1.0; Iron 1.0,
Bronze 0.5, Steel 1.3, Wood 0.5, Leather 0.2, Mithrill 0.5, Crystal 2.0.
INFERRED: f64 #0 is a price factor (1, 2, 4, 10 for Common … Very Rare).

## Stat names and modifier text

The 50 stat names are also built into the exe (table at `0x5f8f50`,
lowercase, same order; CONFIRMED by comparison). A stat's index is the
**effect kind**: `FUN_0051d436` switches on effect `+0x3c` (2 body →
`+0x84`, 3 mind → `+0x88`, 4 reaction → `+0x86`, 5 spirit → `+0x8a`,
17 speed, 18 rotationSpeed → `mover+0xa`; CONFIRMED).

Modifier text `name=value[:time]` (spell texts, items), one term parsed
by `FUN_0051e8fa` (how multi-term texts such as Stone Curse's
`"absorbtion=+5:duration 8,defence=-20:duration 8"` are split is not
traced): kind = index of `name` (compared
case-insensitively) → effect `+0x3c`; `+0x40` = value; time part by
`FUN_0051f29c`: `permanent` → mode 0, `singleuse` 8, else the first of
`charges N` (4), `duration N` (1), `continuous N` (2) found; `+0x3d` =
mode, `+0x42 = N << 4` (ticks). `castSpell`, `teachSpell` and the
`damage*` kinds parse their values differently (`FUN_0051f1c3`,
`FUN_0051f072`; not decoded). On apply, delta = ±`+0x40`
(`0x51d4b1`; sign INFERRED: + on start, − on expiry).

Example: Haste `speed=+2: duration 30` → kind 17, +2 speed for
30 · 16 = 480 ticks (30 s at 16 ticks/s); Slow `speed=-2: duration 30`.

## Column names

CONFIRMED (data, `test_column_names_match_parameter_maps`): string array
`g` holds the column labels of group `g` (`allods2.databin.GROUPS`):
`header[0]` labels the record name, `header[k + 1]` param `k`; every label
agrees with the fields the code maps below (monster 8 `speed`, 9
`rotationSpeed`, 29 `typeID`, 30 `face` = palette variant; class 3
`weight`, 12/13 `@.charge`/`@.relax` = windup/recovery; spell 5 `Delivery
System` (2 = missile), 7 `Spell Effect Speed`). The last label of a group
with strings (monsters, humans `EquipItem`, items/spells `Effects`) names
the trailing CString(s). Groups and counts (labels after the name column):

| Group | Labels | Params | Examples |
|---|---:|---:|---|
| factors | 10 | 7 × f64 | `Abbreviation`, `Materials`, then `Price`, `weight`, `@.damage`, `@.toHit`, `#.defence`, `#.absorption`, `MagCap`, `Level` |
| stats | 29 | 28 | `cost.MP`, `affectMin`, `affectMax`, `UsableBy`, 24 × `in.<slot>` |
| classes (armour, shields, weapons) | 17 | 17 | `Shape`, `Material`, `Price`, `weight`, `Slot`, `@.attackType`, `@.physicalMin/Max`, `@.toHit`, `#.defence`, `#.absorption`, `@.range`, `@.charge`, `@.relax`, `2 handed`, `sutableFor`, `Other Parameter` |
| items | 3 | 2 | `Price`, `weight`, `Effects` |
| monsters | 63 | 62 | below |
| humans | 27 | 26 | `Body`, `Reaction`, `Mind`, `Spirit`, `HealthMax`, `ManaMax`, `Speed`, `RotationSpeed`, `ScanRange`, `Defence`, `Skill.General`, `Skill.Blade (Fire)` … `Skill.Shooting (Astral)` (10–15), `typeID` 16, `face`, `gender ( is female? )`, `AttackChargeTime`, `AttackRelaxTime`, `TokenSize`, `MovementType`, `DyingTime`, `serverID`, `knownSpells` 25, `EquipItem` |
| structures | 8 | 6 | `sizeX`, `sizeY`, `scanRange`, `healthMax`, `Passability`, `BuildingPresent` (+ `Start ID`, `Tiles`: no param) |
| spells | 23 | 22 | `Complication Level`, `Mana Cost`, `Sphere`, `Item`, `Spell Target`, `Delivery System`, `Max Range`, `Spell Effect Speed`, `Distribution system`, … `damageMin`, `damageMax`, `Defensive`, `SkillOffset`, `scrollCost`, `bookCost`, `Effects` |

Monster labels 0–28: `body`, `reaction`, `mind`, `spirit`, `healthMax`,
`HP regeneraton`, `manaMax`, `MP regeneraton`, `speed`, `rotationSpeed`,
`scanRange`, `physicalMin`, `physicalMax`, `attackKind`, `toHit`,
`defence`, `absorbtion`, `attackChargeTime`, `attackRelaxTime`, `prot
Fire/Water/Air/Earth/Astral`, `res.Blade/Axe/Bludgeon/Pike/Shooting`; 29–61:
`typeID`, `face`, `tokenSize`, `movementType`, `dyingTime`, `Withdraw`,
`Wimpy`, `See invisible`, `XPvalue`, treasure fields (38–45), `not used`
×2, `Power`, three (`Spell n`, `Probability n`), `Spell Power`, `serverID`,
`knownSpells`, `skillFire` … `skillAstral`. Example: structure `Goblin Hut`
= `3, 2, 4, 300, 55, 63` (3 × 2 cells, scan 4, 300 HP). INFERRED: factors
f64 `k` = label `k + 2` (`Price`, `weight`, …; f64 #1 = weight is
CONFIRMED below), the labels being the authoring tool's columns.

## Parameter maps

**Monsters** (CONFIRMED `FUN_005114f3`: a cursor reads params in order;
`-1` keeps the default; `MONSTER_PARAMS` in the code):

| Index | Field | Index | Field |
|---|---|---|---|
| 0–3 | body `+0x84`, reaction `+0x86`, mind `+0x88`, spirit `+0x8a` | 17, 18 | attack windup `+0x134`, recovery `+0x135` |
| 4 | max HP `+0x96` (and HP `+0x94`) | 19–23 | `+0xc4 … +0xcc` (5 × s16) |
| 5 | `+0x98` | 24–28 | bytes `+0xcf … +0xd3` |
| 6 | max mana `+0x9c` (`+0x9a`, `+0xa0`) | 29 | `+0xe` = units.reg type ID (Goblin_Pike 64) |
| 7 | `+0x9e` | 30–32 | bytes `+0x4b` (palette variant, [units](units.md)), `+0x49`, `+0x4a` |
| 8 | **speed** `+0x8c` | 33 | read, unused |
| 9 | **turn rate** `mover+0xa` | 34–36 | `+0x1c4` object `+0x40`, `+0x44`, `+0x71` |
| 10 | `+0xa5` | 37 | `+0x1c` (also re-read by `FUN_00511959`) |
| 11–13 | damage min, max, kind (`+0xb4`/`+0xb5`, `+0xb7`…`+0xba`) | 48–61 | `FUN_00511959`: 48–53 three (spell id, value) pairs (effects `FUN_0051906d`), 54 → `+0xaa … +0xb2` (five copies), 55 → `+0x14c`, 56 spell bit mask, 57–61 → `+0xaa … +0xb2` |
| 14 | `+0xa6` (and `+0xa8`) | 15, 16 | `+0xbe`, `+0xc0` |

Monster creation `FUN_00511959(name)` searches the list by name from
index 26 upward, skipping 30 … 62 (CONFIRMED); the index is the unit's
template id. Examples (base `.1` / `.5`): Goblin_Pike speed 24/27, turn
16/27, attack 7 + 3; Ogre 15/18, 12/18, 12 + 6; Troll 8/11, 8/11, 10 + 6;
Catapult speed 8, turn 8, attack 2 + 38.

**Items** (class lists; CONFIRMED `FUN_00528c92`, `FUN_005290cc`):
`param[3]` → `item+0x4a` **weight** = `round(param[3] · quality.f64[1] ·
material.f64[1])` (+0.5, `ftol`); inventory adds `weight · count`
(`+0x42`) to the pack total (`FUN_00529ae2`), which the hero recompute
compares with capacity `Body·10 + 1` (CONFIRMED). `param[12]`, `[13]` →
attack windup/recovery (kept when −1). Also `param[6]`→`+0x68`,
`[7]`→`+0x69`, `[8]`→`+0x5a`, `[9]`→`+0x72`, `[11]`→`+0x58` (default 1).
INFERRED: `[6]`, `[7]` damage, `[2]` price. Long Sword: weight 20,
attack 7 + 4.

**Spells**: `param[5] == 2` = missile, `param[7]` = missile speed in
1/256 cell per tick (Fire Arrow 200, Fire Ball 384, Lightning 60);
[animation §3.4](animation.md#34-where-the-speeds-come-from).

## Open questions

- Human and structure fields in code (loaders via `FUN_004a65b0`,
  `FUN_004a65d0`; the column names above give their meaning); 7 × i16 of
  item classes; special-item byte; `castSpell`/`damage*` modifier values
  (`FUN_0051f1c3`, `FUN_0051f072`).
