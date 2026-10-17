# Unit and monster stat table

Code: `allods2/formats/unitstats.py` (`load(fs)`, `build(db)`, `UnitTable.lookup(is_human, server_id)`).
Engine: `AssetCache.unit_stats()`; `World._load_units` takes HP, `face`, `movementType` and keeps the
`UnitType` in `Unit.stats`; `python -m engine world-info MAP --units` lists each unit's stats.
Export: `python -m allods2 data export units out/data/units.json` (gitignored `out/`; the repo holds
only the golden hash, `tests/golden.json["units"]`). GOG 1.01, addresses are VAs
(sha256 in [formats/README](../formats/README.md)). Tags as in CLAUDE.md: **CONFIRMED** (routine read in REA),
**INFERRED**, **UNKNOWN**.

## 1. Sources

There is one source: `world/data/data.bin` ([databin](../formats/databin.md)), no text table and no
other binary table. CONFIRMED (the unit constructors read nothing else; hard-coded defaults in §5).

| Table | data.bin group | Records | Key | Struct | Loader |
|---|---|---:|---|---|---|
| monsters | 5 | 241 slots, 180 named (one a placeholder) | `serverID` = param 55 | `0x208` Creature | `FUN_00511959` (by name) → `FUN_005114f3` |
| humans (heroes, soldiers, NPC men) | 6 | 289 slots, 284 named | `serverID` = param 24 | `0x254` HumanBase | `FUN_005145d1` (by name) → `FUN_00514cf2` |

Units, monsters and heroes are **separate tables**; a section 6 unit picks one by `flags & 0x10`
([map.md](../formats/map.md#units-section-6)) and matches `server_id` against that table's `serverID`
(`FUN_004fd62f` monsters, `FUN_004fd5ad` humans; both compare the raw param, CONFIRMED). The 4,212 units
of the 46 campaign maps use 205 distinct (kind, serverID) pairs; every one has a record (no exclusions).
Heroes have no separate stat source: a hero is a human record (`_Hero`/`Start_` names set the best-school
field `+0x23c`, CONFIRMED `FUN_00514cf2`), levelled at run time ([progression](progression.md)). Campaign carry-over
(saves, hero state between maps) is not read here: **UNKNOWN**, phase F saves.

Records with no params are editor slots and are skipped (61 monster slots). Monster record 241 `Human`
(`serverID` -1) is a placeholder no map uses; human `ManMage_Unarmed` (serverID 23) has `HealthMax` -1
(constructor default, unused).

## 2. Field table

Column labels come from data.bin ([databin § Column names](../formats/databin.md#column-names)); `fields`
in `UnitType` uses the snake_case names below (`field_name`). Every value is the raw param; **-1 = keep the
constructor default** for all fields (CONFIRMED `0x5425c0/0x542610/0x542660`: a -1 param is skipped). "Struct" is the
Creature offset ([unit-struct](../engine/unit-struct.md#2-creature-layout-server-0x208-0x254)).

### Monsters (62 params; humans: see below)

| P | Field | Struct | Meaning | Tag |
|---|---|---|---|---|
| 0–3 | body, reaction, mind, spirit | +0x84…+0x8a | attributes | CONFIRMED |
| 4 | hp_max | +0x96 (+0x94 = it) | max HP; map `max_hp`/`hp` override it | CONFIRMED |
| 5 | hp_regen | +0x98 | HP regeneration | CONFIRMED |
| 6 | mana_max | +0x9c (+0x9a, +0xa0) | max mana | CONFIRMED |
| 7 | mana_regen | +0x9e | | CONFIRMED |
| 8 | speed | +0x8c | movement speed | CONFIRMED |
| 9 | turn_rate | mover+0xa | | CONFIRMED |
| 10 | scan_range | +0xa5 | sight / scan range | CONFIRMED |
| 11, 12 | damage_min, damage_max | +0xb4/+0xb5 or +0xb7…+0xba | spread = max − min; min ≥ 0x80 or spread > min+255 are stored /15 with bit 7 (`0x516f6f` ×15). `F_Skeleton.5` has min > max (negative spread) | CONFIRMED loader `0x5115e0`; semantics of a negative spread UNKNOWN |
| 13 | damage_kind | +0xb7/+0xb9 or +0x4c bit 4 | -1/0 physical in +0xb4/b5; 1 → +0xb7/b8; 2 → +0xb9/ba negated; 3 → flag 0x10 (ignores absorption) then as 0 | CONFIRMED loader; which element 1/2 are: UNKNOWN |
| 14 | to_hit | +0xa6 (+0xa8) | attacker hit value | CONFIRMED loader; use INFERRED |
| 15 | defence | +0xbe | a hit lands if `defence < toHit + rand(200) − 100` | CONFIRMED `0x516f6f` |
| 16 | absorption | +0xc0 | subtracted from physical damage (min 0) | CONFIRMED `0x516f6f` |
| 17, 18 | windup, recovery | +0x134, +0x135 | attack timing, ticks | CONFIRMED |
| 19–23 | prot_fire, water, air, earth, astral | +0xc4…+0xcc | per-element protection (scaling formula UNKNOWN) | CONFIRMED mapping |
| 24–28 | res_blade, axe, bludgeon, pike, shooting | +0xcf…+0xd3 | per attack-type resistance (index `+0xce + type`) | CONFIRMED index; formula INFERRED |
| 29 | unit_type | +0xe | units.reg type id (animation set); 0 → "Invalid unit" | CONFIRMED |
| 30 | face | +0x4b | palette variant ([units](../formats/units.md)) | CONFIRMED |
| 31, 32 | token_size, movement_type | +0x49, +0x4a | footprint token; mover class 1 walker, 2 ghost/bee, 3 flyer | CONFIRMED |
| 33 | dying_time | vtable +0x74 → timer +0x6c | ticks of the death animation (`dying − 1`) | CONFIRMED `0x50f048`, `0x50f221` (corrects databin.md "unused") |
| 34 | withdraw | brain obj +0x40 | HP threshold: at HP ≤ it the AI looks for a spot and moves (`0x56cd11`); name INFERRED | CONFIRMED compare |
| 35 | wimpy | brain obj +0x44 | HP threshold of a second flee move (`0x56cb0c`); halved by the difficulty tweak | CONFIRMED compare; flee semantics INFERRED |
| 36 | see_invisible | brain obj +0x71 | detection level compared at `0x567ae7`; default 1 | compare CONFIRMED, effect INFERRED |
| 37 | xp | +0x1c | XP reward base, see §4 | CONFIRMED |
| 38 | gold_chance | — | gold drops if `p38 > rand(0..100)` | CONFIRMED `0x510ca0` |
| 39, 40 | gold_base, gold_spread | — | gold = base + rand(0..spread) (40 is a spread, not a max) | CONFIRMED `0x510cc3` |
| 41 | item_chance | — | item drops if `p41 > rand(0..100)` | CONFIRMED `0x510cfd` |
| 42, 43 | item_value_min, item_value_max | — | filter `min ≤ item[+0x1c] ≤ max` in generator `0x525f67` (value = price: CONFIRMED, [items](items.md#4-price)) | CONFIRMED passing |
| 44 | item_flags | gen +0x54 | item-pool flags: bits 0-14 materials, 15-21 qualities, 0x400000 fighter weapons, 0x800000 shields, 0x1000000 armour, 0x8000000 staves (with 0x20000000), 0x4000000 stock, 0x10000000 bypass, 0x20000000 enchant + window ([items §11](items.md#11-random-generation)) | CONFIRMED `0x5254e7`, `0x525f67`, `0x524bca` |
| 45, 46 | not_used, not_used1 | — | no reader (all 198 `0x41e7e0` call sites checked) | INFERRED unused |
| 47 | power | — | not read by either loader | CONFIRMED not read; INFERRED unused |
| 48–53 | spell_1, probability_1 … spell_3, probability_3 | brain +0x7c+4i, +0x88+4i | spell ids and use chance, stored ×0x147 (327: percent on a 15-bit scale); AI `0x56ad00` takes the last slot that passes | CONFIRMED |
| 54 | spell_power | +0xaa…+0xb2 (all five) | skill level of all schools, overridden by 57–61 | CONFIRMED |
| 55 | server_id | +0x14c | stored raw (no reduction for monsters) | CONFIRMED `0x511a33`, `0x4a4f16` |
| 56 | known_spells | spellbook +0x140 | bit mask, bits 1..29 learned; flags \|= 6 | CONFIRMED `0x511db8` |
| 57–61 | skillfire … skillastral | +0xaa…+0xb2 | per-school skills (only with a non-zero mask) | CONFIRMED |
| strings | equipment (2 CStrings) | | `[Quality] [Material] Class{terms}`, [items §9](items.md#9-equipment-strings) | CONFIRMED |

### Humans (26 params + 10 equipment strings)

| P | Field | Struct | Tag |
|---|---|---|---|
| 0–3 | body, reaction, mind, spirit | +0x84…+0x8a | CONFIRMED |
| 4, 5 | hp_max, mana_max | +0x96/+0x94, +0x9c/+0x9a | CONFIRMED |
| 6, 7 | speed, turn_rate | +0x8c, mover+0xa | CONFIRMED |
| 8, 9 | scan_range, defence | +0xa5, +0xbe | CONFIRMED |
| 10–15 | skill_general, skill_blade, skill_axe, skill_bludgen, skill_pike, skill_shooting | +0xa8+2k (1..5 copied to +0x116+2k) | CONFIRMED; +0xa6 (toHit) forced 0 |
| 16 | unit_type | +0xe, but the by-name ctor overwrites it: `0x21/0x22` fighter, `0x23/0x24` mage + gender (`0x514bc7`) | CONFIRMED |
| 17 | face | +0x4b (bit 7 = female) | CONFIRMED |
| 18 | gender | -1: derive from the name (`.f` = female); else overrides it (`0x514870`) | CONFIRMED |
| 19, 20 | windup, recovery | +0x134, +0x135 | CONFIRMED |
| 21, 22 | token_size, movement_type | +0x49, +0x4a | CONFIRMED |
| 23 | dying_time | accessor `0x512526`: p23, or 8 when absent/-1 | CONFIRMED |
| 24 | server_id | +0x14c; **if > 10000: `(v/10) % 1000`** (`0x5148cb`, client `0x4a4ba5`); lookups compare the raw param | CONFIRMED |
| 25 | known_spells | only if max mana > 0 | CONFIRMED |
| strings | 10 equipment CStrings | slot 0 weapon (0x88-byte object), 1 second item (0x6c), 2–9 armour (0x6c); skipped for some callers | CONFIRMED sizes; slot roles INFERRED |

Humans have no damage, to-hit, absorption, protection, XP or loot params: their melee comes from the
equipped weapon, defence from `defence` + armour, and the 0x254 constructor (`FUN_005121e1`) defaults apply
(§5). Item stats are phase F "items".

## 3. Link to the runtime struct and map overrides

Each row's "Struct" column is the field the value initialises. Map section 6 replaces only
**HP**: `hp`/`max_hp` (-1 = template, §4 of [unit-struct](../engine/unit-struct.md#hierarchy--class-order-of-the-creature-creation-path-map-load-fun_00561bf9)),
a human (flag `0x10`) with `hp == max_hp` is reset to default and keeps the *recomputed* maximum ([progression §6](progression.md#6-hero-start): the template `healthMax` of humans is never used), `behaviour` bits set `+0x194…+0x1a0`, and the difficulty tweak scales
max HP and halves the brain's `+0x44` (wimpy). Nothing else in the record is overridden by the map (CONFIRMED
`0x562013-0x562099`, `0x561e20-0x561f0b`). `World._load_units` reproduces the HP rule (humans take `progression.derived_vitals`, see progression §6) and keeps the full
template in `Unit.stats` for the later systems (movement, combat, AI, loot).

## 4. Rewards

- **XP.** Awarded to the *attacker* (a human) per hit and per cast, not only per kill; formulas, the threshold
  curve and the callers are in [progression](progression.md#4-xp-sources). The monster side is this table's `xp`
  (`+0x1c`, p37). CONFIRMED.
- **Loot.** `FUN_00510a70` at death, only if `unit_type ≥ 0x40` and not summoned (`+0x1a0 == 0`). Gold and
  item are rolled independently (fields 38–44). Gold is dropped by `0x5109f5`; the item is one random entry
  of the generated pool, count 1. CONFIRMED.

## 5. Constructor defaults (-1 params)

`FUN_005121e1` (human base) / `FUN_0050dc2b`: attributes 30 (0x1e), HP 50 (0x32), speed 16, turn rate 8,
windup 8, recovery 4, damage 1 with spread 1. A -1 in a record leaves these. The engine currently uses the raw
values and falls back to 0 only for unknown types; applying the defaults is future work (no map unit needs it:
every map unit has `hp_max > 0`).

## 6. Tests

`tests/test_unitstats.py`: field naming, build rules (empty slots skipped, first id wins), synthetic data.bin;
on the install: 180 monsters + 284 humans, every param named (no leftovers), all 205 map (kind, serverID)
pairs resolve (exclusion list empty), range checks (HP > 0 except `ManMage_Unarmed`, speed 8–35, ...),
`Goblin_Pike` against [databin](../formats/databin.md#parameter-maps), golden hash of `units.json`
(`tools/update_golden.py` regenerates it).

## VERIFY IN GAME

- A `Goblin_Pike` has 40 HP, speed 24, hits 4–8 (select it: HP bar and info panel).
- Gold/item drop chances (`gold_chance`, `item_chance`) and amounts for a few monsters (e.g. `Goblin_Pike`:
  60 %, 30–120 gold).
- XP per kill (`xp × 0.5`) and the repeat-kill penalty after 5 kills of one type.
- `Bat_Sonic.4` defence 255, `xp` 13,023 and `F_Skeleton.5` damage 262–197 look odd: confirm in game.
- Withdraw / wimpy thresholds: do units flee at that HP?

## Open questions

- Damage kinds 1/2 (`+0xb7…+0xba`) of weapons and negative damage spread in `0x516f6f`. (The elemental part is
  answered by [spells §5](spells.md#5-damage-and-protection): kind 1-5 = fire..astral, `ftol(d*(100-prot)/100+0.75)`.)
- Hero state between campaign maps. Start: `FUN_00514920`. (Equipment strings are resolved: [items §9](items.md#9-equipment-strings).)
