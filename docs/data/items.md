# Item definitions

Code: `allods2/formats/itemdefs.py` (`load(fs)`, `build(db)`, `ItemTable.lookup(code)`, `.resolve(code, effects)`,
`.class_stats`, `.price_with_effects`, `.parse_effects`, `.parse_equipment`, `.display_name`, `icon_path`, `load_packets`,
`load_ui_texts`); random generation in `allods2/formats/itemgen.py` ([§11](#11-random-generation)).
Engine: `AssetCache.items()`. Export: `python -m allods2 data export items out/data/items.json` (gitignored
`out/`; the repo holds only the golden hash `tests/golden.json["items"]`). Check: `tools/validate_items.py`.
GOG 1.01, addresses are VAs (sha256 in [formats/README](../formats/README.md)). Tags as in CLAUDE.md.
Related: [databin](../formats/databin.md) (layout), [map](../formats/map.md#item-groups-section-8-and-records-section-9)
(item codes, section 9), [units](units.md) (equipment strings, loot price window).

## 1. Sources

| Data | File | Notes |
|---|---|---|
| definitions | `world/data/data.bin` groups 3 (weapons 27, shields 9, armour 30), 4 (special items 96), 1 (7 qualities, 16 materials), 2 (50 stats) | the only source of numbers |
| display names | `world/data/itemname.bin` (491 u16 codes) + `main/text/itemname.txt` (line i = name of code i) | loader `FUN_00474268`: code to name map `0x622640` (CONFIRMED) |
| item packets | `world/data/itemname.pkt` (491 records, same order) | `FUN_00474268` keeps the blob, map `0x6225c0` code to record (CONFIRMED); layout §8 |
| icons | `graphics/inventory/*.16a` (491 files, 80x80) | path §8 |
| `itemname.pat` | `main/text/` | not referenced by the exe: INFERRED editor aid, `Quality Material Class=Display name` |

The 491 codes of `itemname.bin` are exactly the item universe: the 395 class items are the (class, quality, material)
combinations that the per-class masks (§3) allow, plus the 96 special items. CONFIRMED by the decoder (test), mask use
`FUN_005247db`. All 37 distinct item codes of the 46 campaign maps are in it.

## 2. Class records (weapons, shields, armour)

Item code = `material << 12 | class << 8 | quality << 5 | index` (`FUN_00544120`, CONFIRMED; [map](../formats/map.md)
`decode_item`). Armour `class` is the record's `Slot`. Params by index (`CLASS_FIELDS`); -1 = not set:

| P | Field | Used for | Tag |
|---|---|---|---|
| 0, 1 | shape, material | no gameplay reader: only the data.bin text exporter `FUN_004fc25e` reads them (it dumps every column, 17 per class record; StaticData path `FUN_004f8f09`, not run by the shipped game) | CONFIRMED scan of all `FUN_0041e7e0` sites on class records; INFERRED unused |
| 2 | price | base price, §4 | CONFIRMED `FUN_00528e04` |
| 3 | weight | item `+0x4a`; pack total vs capacity `Body*10+1` ([databin](../formats/databin.md#parameter-maps)) | CONFIRMED |
| 4 | slot | armour `+0x54`: 4 ring, 5 amulet, 6 helm/hat, 7 mail/robe, 8 cuirass/cloak, 9 bracers, 10 gauntlets/gloves, 12 boots/shoes; must be <= 12 | CONFIRMED `FUN_0052765b` |
| 5 | attack_type | weapon `+0xb6` of the carrier if < 10: 1 blade, 2 axe, 3 bludgeon, 4 pike, 5 shooting (same order as monster `res_*`); 11 flame thrower (own branch) | CONFIRMED `FUN_005290cc`; names INFERRED |
| 6, 7 | damage_min, damage_max | weapon `+0x64` = min, `+0x65` = max - min (spread) | CONFIRMED `FUN_00528c92` |
| 8 | to_hit | weapon `+0x56` | CONFIRMED |
| 9 | defence | armour `+0x56`, shield `+0x54`, weapon `+0x6e` (pikes, lances) | CONFIRMED |
| 10 | absorption | armour `+0x58`, shield `+0x56` | CONFIRMED |
| 11 | range | weapon `+0x54`, -1 gives 1; carrier range `+= range - 1` | CONFIRMED |
| 12, 13 | windup, recovery | carrier `+0x134/+0x135` when not -1 and the carrier accepts them (vtable `+0x30`) | CONFIRMED `FUN_005290cc` |
| 14 | two_handed | 2: equipping it moves the shield to the pack; equipping a shield moves a 2-handed weapon away | CONFIRMED `FUN_005290cc`, `FUN_0052846b` |
| 15 | suitable_for | bit 1 fighters, bit 2 mages, 0 nobody (monster weapons); §6 | CONFIRMED `FUN_00512573` |
| 16 | other | as 0, 1: only the text exporter `FUN_004fc25e` (armour 1-10, `Cap` 1 .. `Dress` 10) | CONFIRMED scan; INFERRED unused |
| extra | 7 x i16 | per quality: bit m = material m allowed (§3) | CONFIRMED `FUN_005247db` |
| extra | string array | always empty | CONFIRMED (data) |

Carrier effects of a weapon (`FUN_005290cc`): `+0xf4 += min`, `+0xf5 += spread`, `+0xe6 += to_hit`, `+0xfe += defence`,
attack type to `+0xb6`; armour and shields add through their vtable (`+0x40`) and the effect list.

## 3. Quality, material, masks

Each quality and material holds 7 f64 at record `+0x30 + 8k` (CONFIRMED; [databin](../formats/databin.md#factors-qualities-materials)):

| k | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| factor of | price | weight | damage | to hit | defence | absorption | level (quality) / magic capacity (material) |

Scaling is `param * material[k] * quality[k]` with the **exe rounding**: `ftol(x + 0.5)` for price, weight, damage min,
to hit, defence; the damage spread is `ftol(max*m*q - min + 0.5)`; absorption is truncated (no +0.5); `magic_cap =
ftol(quality[6] * material[6])` (item `+0x48`: the capacity left for modifiers, readers in [§11](#11-random-generation)). CONFIRMED `FUN_00528c92`, `FUN_0052765b`, `FUN_0052810d`.
Worked example: Common Iron Long Sword (28..56 damage, to hit 3): min 6, spread 5, to hit 3, price 600, weight 20.

Masks: class record word `q` (q = quality 0..6) bit `m` says "may be made of material `m`" (`FUN_005247db` tests
`word[q] & 1 << m`). The 395 allowed combinations are exactly the 395 class items of `itemname.bin` (test).

## 4. Price

`item +0x1c` is the price (CONFIRMED: `FUN_00528e04` weapons, `FUN_00527862` armour, `FUN_0052823a` shields; loot window
`FUN_005247db` compares it with the monster `item_value_min/max`, [units](units.md)). All gold amounts, shop prices
and the pile frame total are this value.

Trade table (client, `FUN_004b960c`): buying costs `price x count`, selling pays `((price + 1) / 2) x count`.

1. `base = ftol(P2 * material[0] * quality[0] + 0.5)`.
2. For each effect of the item (§5): kind 1 (`price`) sets `price = value` and ends (no cap); kind 41 (`castSpell`) adds
   `spell_price`; every other kind adds `effect_cost` to `s`.
3. `price += ftol((1.5^(s/70) + 1) * s * 50)` (`FUN_0051e41a`), then `min(price, 19,999,999)`.

`effect_cost` (`FUN_0051e318`): kind 0 gives 0; kinds 44-48 (`damageFire..Astral`) `(min + spread) * cost`; kind 41
`charges * cost`; else `value * cost`, with `cost` = column `cost.MP` of the stat (§5).
`spell_price` (`FUN_0051f48d`): `ftol(scrollCost * 10 * 2^(log_1.2(charges/30 + 1)))`, `scrollCost` = spell param 20
(the inverse in `FUN_0051f7d3` confirms the shape). Example: Fire Arrow (scrollCost 50), 50 charges: 20,816.
Special items (`FUN_0052340f`): the record price (`-1` for quest items); a **Book** (name prefix, §7) takes the
`bookCost` (spell param 21) of its `teachSpell` effect, 0 without one.

## 5. Modifiers (effects) and the `stats` group

An item carries an effect list (`+0x20`). Sources: the data.bin special-item text, the `{...}` part of an equipment string,
section 9 pairs. Text term `name=value[:time]`, comma separated (`FUN_0051e78e`, `FUN_0051e8fa`; stat name case-insensitive,
unknown names and spells discard the term): plain kinds take an int (`+30`, `-2`); `castSpell=Fire_Arrow:50` /
`teachSpell` take a spell name (`Fire_Arrow` = `fire_arrow`, id 1..29 as data.bin spells) and `:N` charges
(`+0x42`); kinds 44-48 take `min-max` (stored as min and **spread** = max - min, `FUN_0051f072`); time part
`permanent`, `singleuse`, `charges N`, `duration N`, `continuous N` (`FUN_0051f29c`).

Effects are **separate additive modifiers**: they never change the class stats. On equip each effect is applied to the
carrier by its vtable (`+0x40`, loop `FUN_0052377e`), delta = value per stat kind ([databin](../formats/databin.md#stat-names-and-modifier-text)).
Section 9 pairs `(stat id, value)` become effects of that kind with `value` (CONFIRMED `FUN_00564072`; **id 41 is
stored as 49** `damageBonus`, so a pair never carries castSpell); the record's `c` field gives `castSpell` (`teachSpell`
for a book) with spell id and charges; element damage records store the second byte raw. `pair_effects` does this.

`stats` group (50 rows; stat id = row): `cost.MP` p0 price weight (§4, inverse `FUN_0051f7d3`); `affectMin/affectMax`
p1/p2 magnitude range of a generated modifier (`FUN_0051f7d3` rejects below min, clamps to max); `UsableBy` p3 bit 1
fighters / 2 mages (`FUN_0052397e`: a modifier is added only if its mask overlaps those already on the item, unless the
first is 3; the same kind replaces the value); `in.<slot>` p4-p27: **cumulative** weights, 12 columns for the fighter
set (weapon, shield, -, ring, amulet, helm, mail, cuirass, bracers, gauntlets, -, boots) then 12 for the mage set (weapon,
-, -, ring, amulet, hat, robe, cloak, -, gloves, -, shoes). `FUN_00526ec4` rolls `r = 1..total` and takes the stat whose
cumulative range contains `r`, then `FUN_0051f7d3(budget, magic capacity)` for the magnitude: CONFIRMED, full algorithm in
[§11](#11-random-generation). `slot_weights(slot, mage)` returns the differences.

## 6. Who may use an item

Item code and server (`FUN_00512573`, equip by name, also the human constructor): a weapon, armour or shield is equipped
only if `suitable_for & 1` for a fighter or `& 2` for a mage (mage = carrier flag `+0x4c` bit 4, `FUN_0053a5a0`). The
equip methods (`FUN_005290cc` weapon, `FUN_00527a13` armour, `FUN_0052846b` shield) read no skill, Body or level: CONFIRMED
absent in `0x522000-0x52b000`.

Hero window, drop of the dragged item on a slot (`FUN_004b028d`, CONFIRMED). The wire item's flag byte `+8` carries
`suitable_for << 1` (§8):
- `FUN_0046a9c2` allows it iff (bit 2 and the hero is not a mage) or (bit 4 and the hero is a mage); hero `+0x1b8` bit 2 =
  mage. Rings and amulets (`suitable_for` 3) fit both.
- blocked for slots 0 and 1 while the hero state `+0x78` is 3, 7 or 8; blocked when the item is named `Quest Treasure`
  (`FUN_00439d63`, string `0x5f0424`); a quest item with neither bit (`flags & 6 == 0`, code `0xe4d`) sends message `0x463`.
- a book (teachSpell entry `0x2a` of the item, `FUN_004b10b0`) is refused for a non-mage hero and when the hero's learned
  spell mask (`+0x1c`) already has the spell bit.
No skill, Body or level test exists in any of them. The server side of a hero-window equip is message `0x22` (§12): it
repeats no mage/fighter test.

## 7. Special items

96 records (`Price`, `weight`, flag byte always 1 (record `+0x1c`; no reader: byte/word reads of `[rec+0x1c]` in `0x438000-0x440000` and `0x4f0000-0x560000` find only the data.bin serializer `FUN_004fe55d`; INFERRED unused), text at `+0x40`). The sub-type is the **name prefix** (`FUN_00523148`, CONFIRMED):
`Potion` 3, `Book` 5, `Scroll` and `SuperScroll` 4, else 0 (quest). 5 books (one per school: Air, Water, Fire, Earth,
Astral), 29 scrolls (`castSpell=..:50`), 29 super scrolls (`:100`), 13 potions (`health=+30`, `body=+1`...), 20 quest items
(text `1` or empty). Item `+0x44` holds this tag; class items use 1 armour/shield, 2 weapon.

## 8. Names, icons, packets

- Name: `itemname.txt[i]` for `itemname.bin[i]`. Class items read `Bronze Dagger`; the five books are all `Book`, scrolls
  `Scroll` / `Elven Scroll`. The spell is added by the tooltip builder `FUN_0043901f` (CONFIRMED): for every teachSpell
  entry (`0x2a`), and for every castSpell entry (`0x29`) of a special item (class 14), it appends `" %s %s%s"` with the
  interface texts `0x5a` / `0x5b` of `main.txt` (`of`, empty) and the `spell.txt` line (`FUN_00474733(spell - 1)`):
  `Scroll of Fire Arrow`, `Book of Haste`. castSpell on other classes is a separate line `#casts <spell>` (texts `0x5c`,
  `0x5d`). `ItemTable.display_name(code, effects, spell_names, of, tail)`, `load_ui_texts(fs)`. The same builder prints
  `#<stat> +N` lines, `#<stat> min-max` for the damage kinds, `#Damage`, `Range`, `Speed` and the resistances.
- Icon (`FUN_00438ba1`, CONFIRMED, all 491 files exist): class items `graphics/inventory/` + `%02d%02d%1d%02d` of
  (material, class, quality, index) + `.16a`; special items `%02d%02d%03d` of (material, 14, `code & 0xFF`). Class is the
  code field (armour: the slot). Ground pile: the backpack sprite frame from the pile total ([map](../formats/map.md#drawing)).
- `itemname.pkt` (layout tiles exactly): 9 header bytes, then records `u16 code, u8 1, u8 0, u8 a, u8 b, u8 n,
  n payload bytes`; the record is the item descriptor of the wire item `FUN_004387b2` (`+6` code, `+8` flags, `+9` = b,
  `+0xa` = n, payload at `+0xc`; looked up in map `0x6225c0`) and is built on the server by `FUN_0050cabf`/`FUN_005244d6`
  (CONFIRMED). **`a`** = flag bits OR-ed into the wire flag byte: `suitable_for << 1` for all 395 class items (fighter 2,
  mage 4, both 6: data check), specials 1 (quest), 5 (book: mage), 7 (potion), `0x17` (scroll); client tests of bit 2 / 4:
  `FUN_0046a9c2`, sorting `FUN_004b6790`, bit `0x10` and `1` in `FUN_004b028d` / `0x41918e` (INFERRED: special, scroll).
  **`b`** = number of payload entries (price + pairs; 491 of 491 records), the bound of every payload loop
  (`FUN_0043901f`, `FUN_00438e8a`). Payload: `01`, `u32 price`, then (class items)
  `(stat, value)` byte pairs: 12 to hit, 13 damage min, 14 spread, 15 defence, 16 absorption, 38 range (only with
  damage); specials: `33 00` then pairs (`29 spell charges charges` for scrolls). All 409 class prices and stat pairs equal
  §3/§4 (the pkt is the client's copy of the computed item).
- Scroll price: three numbers exist. The server item price is the record price (`FUN_0052340f` type 4 = record `Price`,
  100 for the Fire Arrow scroll, per scroll 100 .. 100,000; super scrolls 1,000 .. 1,000,000). The pkt price of a scroll is
  `trunc(spell_price / 500)` (58 of 58; ~41 for Fire Arrow), and the 13 potions match their record price. The client
  uses the wire price for the trade table (`FUN_004b960c`: buying sums `price x count`, selling `((price + 1) / 2) x count`,
  affordability test in `FUN_004b18e2`); a stream item without extras (flag `0x20` clear, which `FUN_005244d6` forces for
  potions and scrolls: INFERRED reading of the stream) keeps the pkt template price (`FUN_004387b2`). Whether the server then charges the record price
  was not found (settlement routine): see VERIFY IN GAME.

## 9. Equipment strings

Monster (2) and human (10) records hold `[Quality] [Material] Class{terms}` (CONFIRMED `FUN_00528808`, `FUN_005273f0`,
`FUN_00527e23`, `FUN_005145d1` slot loop: 0 weapon, 1 shield, 2-9 armour). The exe cuts `{...}`, takes the **last**
quality then material whose name occurs (defaults Common, None), removes them, then armour and shields prefix `Soft ` when
the material name contains `Leather`, else `Wooden ` when it contains `Wood` (`FUN_004fa7e1`), shields drop ` Shield`, and the
rest is looked up by name from the end of the class list (`FUN_0053eb10`). 1,319 strings resolve; `Leather Gauntless`
(typo in data.bin) fails, the exe reports "Invalid armor". `parse_equipment(text, slot)` returns the item code and effects.

## 10. Tests

`tests/test_itemdefs.py`: synthetic rules (rounding, class stats, price, spell price, specials, masks, users, icons, text
terms, section 9 pairs, slot weights, equipment strings, pkt, names); on the install: 162 definitions, every packet equals
the formulas, masks regenerate the 395 items, all map codes and section 9 stat ids resolve, all equipment strings but one
resolve, golden hash `["items"]`. `tools/validate_items.py` runs the same checks. `tests/test_itemgen.py`: one synthetic test per
generation rule (rng, flag lists, pool, roll, magnitude, enchant, generator, stock, merge) and the display name; on the install the
generator runs with real loot flags.

## 11. Random generation

Code `allods2/formats/itemgen.py` (`generate`, `build_pool`, `enchant`, `roll_modifier`, `magnitude`, `loot_item`), tests
`tests/test_itemgen.py`. The random source is an object with `rand15()`, the CRT `rand()` of the exe (`0x583290`:
`x = x * 214013 + 2531011`, result `(x >> 16) & 0x7fff`, `MsvcRng`). `rnd(n)` = `FUN_0051fa25` = `(rand * (n + 1)) >> 15`
(0..n; n = 0 draws nothing), `rnd1(n)` = `FUN_0051fa4e` = `rnd(n - 1) + 1`. Float math is x87: `__ftol` truncates, NaN and
overflow give 0x80000000. All of this CONFIRMED (REA) unless tagged.

**Callers** of `FUN_005254e7` (build generator from `{min, max, count, stack, flags}`) + `FUN_00525f67` (generate):
monster drop `0x510da2` (p42, p43, 100 candidates, stack 1, flags p44; one list entry `rnd(len - 1)` kept with count 1,
[units](units.md)); mission reward `0x5325ee` (window `[v, 2v]` with flags `0x1b7fffff`, then `[3v/4, 3v/2]` with `0x2bffffff`,
100 candidates each, `v` = score clamped 250 .. 16,382,000; INFERRED name); shop stock `0x522767` (four blocks of five dwords
`min, max, count, stack, flags`, see below). No xrefs (dead): `0x525b44` (an older
generator) and `0x525a7f` (count by `+0x45`).

**Shop stock blocks** (CONFIRMED by disassembly): the server shop is the structure object of vtable `0x5d12e8` (ctor `0x520ee6`,
the only live creator is the map loader `FUN_00561422`), which owns a shop object (vtable `0x5d1358`, ctor `0x522289`, `shop+0x94` = the
structure). It is built only for the structure types (1-based data.bin id = section 4 `type`) 34 `Shop`, 35 `Shop 2`, 93-95
`Multiplayer Kaarg Shop 1-3`, 105-107 `Multiplayer Druid Shop 1-3`; none of them occurs in the 46 campaign maps (the Kaarg and Druid
shop buildings of the campaign, ids 90-92 and 102-104, are plain structures without this logic). The four blocks live in the structure at
`+0x70`, `+0x84`, `+0x98`, `+0xac`, 20 bytes each: `+0 min`, `+4 max`, `+8 count`, `+0xc stack`, `+0x10 flags` (the order `FUN_005254e7`
reads: `min -> gen+0x34`, `max -> gen+0x38`, `flags -> gen+0x54`; `FUN_00525f67(count, stack, min, max)`). The ctor fills block 0 with
`min 1,000,000`, `max 10,000,000`, `count 1`, `stack 1`, `flags 0x2fffffff` (every material, quality and pool bit including `0x4000000`
stock and `0x8000000` staves, `0x20000000` modifiers, but not `0x10000000`) and copies it to the other three. `FUN_00561422` then
overwrites all four from the section 11 middle list (the 84-byte records `u32 structure uid`, `flags[4]`, `min[4]`, `max[4]`, `count[4]`,
`stack[4]` at `+4`, `+0x14`, `+0x24`, `+0x34`, `+0x44`; read by `FUN_00534ad4` case 11 into the list at map object `+0x324`), matching the
record whose uid equals the structure's. That list is empty in all 46 maps ([map](../formats/map.md)), so a shop built from the shipped
maps would keep the defaults. `0x522767` (only when the shop list is empty, via `0x522d70` / `0x5228c1`; the latter returns 0 once the list
holds 250 entries) generates each block and stamps each new item's `+0x4d` with the block index + 1. `FUN_00521d4c` picks the block an item
returns to by its group byte `+0x44` (1 armour -> flag `0x1000000`, 2 weapon -> `0x400000`, 3-5 -> `0x4000000`). The branch
`[0x6044c4 + 0x74] == 0` calls the null pointer `DAT_00627474` (never written: dead). The same loader gives the structure types 67-69,
99-101, 111-113 (`Multiplayer Inn 1-3` and the Kaarg / Druid ones) a class from the first 12-byte list (flag word: `& 2` value, `& 0x10`,
`& 0x20`, `& 0x40`, `& 4`), and the types 70-75 (`Pointer`) a class from the second 12-byte list.

**Flags** (generator `+0x54`, monster p44, e.g. `0x1147ffff`, `0x2e7fffff`, `0x31ffffff`, `0x2c0fffff`):

| Bits | Meaning | Evidence |
|---|---|---|
| 0..14 | material list: bit i is material i, bit 13 is material 14, bit 14 is material 15 (material 13 is never rolled) | `FUN_00524bca` |
| 15..21 | quality list 0..6 | `FUN_00524bca` |
| `0x400000` | pool: fighter weapons (`suitable_for & 1`) | `FUN_005254e7` pool `0x68f540`, kind 2 |
| `0x800000` | pool: shields | pool `0x68f518`, kind 7 |
| `0x1000000` | pool: armour of every slot (rings, amulets, hats, mail ...) | pool `0x68f52c`, kind 1 |
| `0x8000000` | pool: staves (weapons with `suitable_for & 1 == 0`), only when `0x20000000` is also set | kind 8 |
| `0x2000000` | passed along, never tested | no reader |
| `0x4000000` | stock: books, scrolls, six potions | `FUN_00524e31`, `FUN_00525f67` |
| `0x10000000` | with `0x20000000`: `rnd(100) < 51` accepts without modifiers | `FUN_00525f67` |
| `0x20000000` | modifiers are rolled and the price window applies to the finished item | `FUN_00525f67`, `FUN_005247db` |

**Pool** (`FUN_00524bca`, `FUN_005247db`): per category, in the order weapons, staves, armour, shields, for each quality of the
list (outer) and material of the list (inner), every class record `i` (1 .. count - 1, the group holds `N + 1` slots: INFERRED from
`index < count` in `FUN_00523148`) whose mask word `q` has bit `m`. A record enters when `min <= ftol(price x material[0] x quality[0]) <= max`
(truncated), or always for the two categories with the enchant flag (armour, staves); such a restricted pool also drops items with
`magic_cap < min ** 0.4`. Armour skips `(quality, material, record)` = (0, 0, 2), (0, 1, 2), (6, 4, 6). Then `0x4000000` adds
(`FUN_00524e31`): a book for every spell 1..29 except 9, 14, 15, 24, 28, 29 (school record by spell: 1-4 Fire, 5-8 Water, 10-13
Air, 16-19 Earth, 20-27 Astral; price = the spell's `bookCost`; teachSpell effect; window check), then for every spell 1..29 a
coin `rnd1(2)`: 1 = Scroll record `spell + 5`, else SuperScroll record `spell + 34` (window check on the record price).

**Generation** (`FUN_00525f67`): empty pool returns nothing. With `0x4000000` first every pool book (count 2) and the potions
Health Regeneration, Medium Healing, Big Healing, Mana Regeneration, Medium Mana, Big Mana (count `50 + rnd1(50)`, no window
check). Then while `made < count` and `rejected <= count x 10`: draw `rnd(len - 1)` (redrawn while the entry is a book, at most 1000
draws; the run ends if the 1000th draw happened); take a copy; with `0x20000000`: `0x10000000` and `rnd(100) < 51` accepts,
else `enchant`; the final price must lie in `[min, max]`; a failure counts as rejected. Accepted: a stackable item (potion,
scroll, or any item without modifiers; `0x5234c2`) gets `rnd(stack) + 1` pieces, else 1, and merges into an entry of the same code
(`FUN_005259af`). The list is sorted by `FUN_0052571c` (fighter bit descending, record index, price ascending; its second key
is uninitialised stack for non-class entries, so tie order is not reproduced) and the sort does not change the distribution of
the uniform pick of `loot_item`.

**Enchant** (`FUN_00526b5d`; specials always fail: capacity 0): fighter items and non-weapons: modifier 1 = `roll_modifier(fighter,
type, class, magic_cap, 2 max - price, price)`; none fails the item, castSpell ends the procedure. Then `rnd(100) < 50`: modifier 2
with capacity `magic_cap - used` and the new price; `rnd(100) < 25`: modifier 3 (a failed roll or a castSpell ends it and keeps the
item); finally `magic_cap -= used`. Each modifier is added by `FUN_0052397e` (UsableBy rule, §5; same kind overwrites the value)
and the price recomputed (§4). Staves (`suitable_for & 1 == 0` weapons): one `FUN_0052714f` spell roll with budget
`min(2 max - price, price x 100)`, up to 100 draws of `(MAGE_SPELLS[rnd(6)], magnitude)`.

**Roll** (`FUN_00526ec4`): needs `magic_cap >= 1` and `budget >= 1`. Column = `class - 1` (+12 for non-fighter items). Up to 100 attempts:
`r = rnd1(total)` (total = cumulative weight of the last stat), stat = the named row with `cum[i-1] < r <= cum[i]`; a hit on the
100th attempt counts as failure (exe quirk). A non-fighter weapon is forced to castSpell. castSpell: spell `FIGHTER_SPELLS[rnd(1)]` =
18, 26 or (non-fighter) `MAGE_SPELLS[rnd(6)]` = 1, 10, 11, 18, 26, 5, 16 (data at `0x5d07f8`, `0x5d0800`), budget replaced by
`price x 10` (`x 100` non-fighter).

**Magnitude** (`FUN_0051f7d3(budget, capacity)`, the largest value): `cap_limit = capacity / cost`. castSpell: `r = log2(budget /
(scrollCost x 10))`; `charges = ftol((1.2 ** r - 1) x 30)` if `r > 0` else -1 (the inverse of `spell_price`), `min(charges, cap_limit,
100)`. Others: `s = ftol(ln(budget / (capacity x 50) - 1) / ln 1.5 x 70 / cost)`, `n = min(s, cap_limit)`; below `affectMin` gives -1, above
`affectMax` is clamped. The effect then draws its real value (`+0x54`, `0x51f6af`): `rnd1(m)` (always drawn first); castSpell charges =
that (<= 100); stats `max(that, affectMin)`; damageFire..Astral: min `rnd1(min(m, 255))`, spread `rnd1(m / 2)` (two more draws).

**magic_cap readers** (`+0x48`, short; scan of all word reads in the exe): the restricted pool filter (`0x524b0d`), `FUN_00526b5d` and
`FUN_00526ec4` (capacity of every roll, reduced by the modifiers' cost), the wire decoder `FUN_004ed5f5` (after the effects:
`+0x50 = (used > magic_cap x 3 / 2 && class != 14)`, then `magic_cap -= used`), the mission reward `0x5325ee` (when four of the
five hero attributes exceed 75 and `v > 999,999`, or `FUN_0053dd90` holds: each equipped item with modifiers and capacity left gets
its first modifier raised by `max(1, v x step / 8,000,000)`, at most `step` and `capacity / cost`, only while the value is below its
`affectMax`; step 1 for body, mind, reaction, spirit and the kinds 16-19, 8 for health, mana, to hit, defence, damage, castSpell
charges and the damage kinds, 20 for the regenerations, 5 for protections and skills). Not read by the hero recompute, spell casting
or the UI.

**Elemental damage kinds** (`damageFire..Astral`, kinds 44-48, `FUN_0051d436`): applying sets the carrier's `+0xfb` = 1..5 (fire, water,
air, earth, astral, the order of the protections `+0xc4..+0xcc`), `+0xf9` = min, `+0xfa` = spread; the sign is ignored, so removing
the item does not clear them and a later one overwrites (one slot). A weapon of attack type 11 / 12 (`FUN_005290cc`)
adds its own damage to `+0xf9/+0xfa` and sets kind 1 / 2; other weapons copy their element bytes `+0x69..+0x6b`. The hit record
(INFERRED base: carrier `+0xe6` for humans, `+0xa6` for monsters; `+0xf4/+0xf5` physical, `+0xf9..+0xfb` element) is read by
`FUN_00516f6f`: when the physical hit landed or has no physical damage, the element part is
`rnd(spread) + min`, scaled by the defender's protection of that kind ([spells §5](spells.md#5-damage-and-protection)), added if
> 0; absorption does not apply to it. The kinds 13, 14, 43 and 49 add to `+0xf4`, `+0xf5`, `+0xf4`, `+0xf4`.

## 12. Trade, hero window and wire flags

All CONFIRMED by disassembly of `allods2.exe` unless tagged. Client message `0x22` (`FUN_0041a20c`) moves an item: byte `+0xc` source
kind, `+0xd` destination kind, word `+0xe` source index, `+0x10` destination index, `+0x12` count. The server case `0x22` of `FUN_004f515d`
sends kinds 4..8 on both sides to the shop (`FUN_0052112f` -> `FUN_00522baf` -> `FUN_00521fd1`); the other combinations go through
the hero container methods (kind 1 = equipment slot via `vtable + 0x48` take / `+ 0x40` put; kind 3 stores the destination word in the
hero's `+0x1f` object `+0x1c`). Further shop messages: `0x33` buy (`FUN_0052115f` ->
`FUN_00522a71` -> `FUN_00521c29`), `0x34` sell (`FUN_0052117b` -> `FUN_00522ab2` -> `FUN_00521ae3`), `0x35` / `0x36` leave or cancel
(`FUN_005211bb` -> `FUN_00522c75` -> `FUN_005220d9`; `FUN_005210c9` -> `FUN_00522936`). A call from a hero that is not a customer logs
"Invalid shop transaction".

**Settlement.** The hero's gold is the field `+0x3c` of the hero object (`[customer + 0x14] + 0x3c`).
- *Buy* (`FUN_00521c29`): for each item in the cart list whose owner `+0x14` is 0 (still the shop's): `cost = item.+0x1c * item.+0x42`
  (price times count). If the gold is below the cost the loop stops (the earlier items stay bought); otherwise `gold -= cost`, the item
  leaves the cart, `+0x14` = hero, `+0x4c` (in-cart flag) = 0, and `FUN_00529ac2` files it in the pack. So the gold taken is the server
  item's `+0x1c` (§4 price with effects), **not** the pkt template price and not the short at `+0x4a`.
- *Sell* (`FUN_00521ae3`; the client table shows `((price + 1) / 2) x count`, the server rounds the whole stack once): for each cart item owned by the hero with `+0x1c != 0`: `gold += ftol(price * count * 0.5 + 0.5)` (constant
  `0x5d0828` = 0.5; half the price, rounded half up, truncating `__ftol`), then the item returns to the shop through `FUN_00521d4c`.
- *Cancel* (`FUN_005220d9`): shop-owned cart items go back to their block, hero-owned ones back to the pack; no gold moves.
- The container total at `+0x20` (`FUN_00529c96`, the pack insert) only sums `short +0x4a * count` of what it holds (stack merge: same code
  and same `+0x4d` block tag). It is not used for payment.

**Equip on the server.** The case `0x22` equip (destination kind 1) calls the carrier method `vtable + 0x40` (`FUN_005290cc` weapon /
`FUN_00527a13` armour / `FUN_0052846b` shield, §6) with no fighter/mage test: the readers of record parameter 15 (`suitable_for`) in the exe
are the equip-by-name functions `FUN_00527c46`, `FUN_005285f5`, `FUN_00529629` (via `FUN_00512573`), the generator and pool code
(`FUN_00524bca`, `FUN_00526b5d`), the comparator below and `FUN_00510a70` (`== 0` test for a natural weapon swap). INFERRED from
that absence: the server repeats no fighter/mage test for a hero-window equip; only the client test `FUN_0046a9c2` (§6) applies.

**Wire flag byte** (`+8` of the descriptor, built from the `itemname.pkt` header byte `a`, checked on all 491 packets): bit 1 only on
class 14 (specials: quest 1, book 5, potion 7, scroll `0x17`); bit `0x10` only on scrolls (58 of 58). Client `FUN_004b028d` (hero
window, item click) takes a separate branch when `flags & 0x10 and flags & 1` (scroll) and another for `flags & 1` alone.
Wire item decode `FUN_004ed5f5`: `u16 code`, `u8 f`; `f & 0x80` = count in `f & 0x3f`; else `f & 0x20` = `f & 0xf` modifier records of
`(type char, u8 value[, extra])` (types `)` takes two bytes, `, - . / 0` one extra byte); else a `u16` count.

**Item `+0x50` (over-capacity).** Set by `FUN_004ed5f5` (§11 magic_cap readers). Readers: the two item-list loops of the packet handler
`FUN_004ea6ab` (equipped list and pack list) set the owner flag `+0x1bc = 1` when any decoded item has `+0x50 != 0`, and the
server message `0xbe` (a player joins: `FUN_004f515d` case 0xbe) then logs
`"Cheating detected! Player: %s file: %u%u.a2c"` (`0x5fcf34`) and posts event `0x92` (5, hero id) when the new hero's `+0x1bc` is set.
The hero comes from the character file `<schr dir>\chr<name>_<u><u>.a2c` (format `0x5fcea4`) read by `FUN_004ea6ab`, or from the
join packet when no file is used. So a character whose item carries more modifier cost than 1.5x its capacity is reported as cheating.

**Generator order** (`FUN_0052571c`, the compare of the sort in `FUN_00525f67`): key `k(x) = x.+0x44 in {1, 2, 7} ? suitable_for(x) & 1 : 0`.
Order: `k` descending (fighter items first), then class record index `+0xc` ascending, then price `+0x1c` ascending. Exe defect: when the
second operand is not class 1/2/7 the code clears the first key again instead of setting the second, so the second key stays whatever the
stack slot held from an earlier call (not recoverable statically). Ties between differently classed entries are therefore not reproduced;
`loot_item` picks uniformly, so the distribution is unaffected.

## VERIFY IN GAME

- Price shown for a Common Iron Long Sword (600) and a Rare Bronze one (600), a Rare Mithrill Helm with `{defence=13}`.
- Scroll of Fire Arrow: price shown in a shop (about 41 from the pkt template, or 100); the gold taken is the server item's `+0x1c`
  times the count (§12).
- A two-handed weapon pushes the shield into the pack; a mage cannot equip a Long Sword, a fighter cannot equip a Staff.
- Weight: Bronze Cuirass 38, Meteoric / Crystal items heavier (material f64 1).

## Open questions

- Mission reward `0x5325ee`: CONFIRMED caller chain: server message `0x38` (`FUN_004f515d` case 0x38, after `FUN_00510745`; stores
  two payload bytes at hero `+0xa6c`) -> `FUN_0052f813`: if `FUN_00533e8f` (a record in the mission's list matches the player id
  `+8`, the mission object `+4` and `+0x10 == 1`) is 0 it runs the no-reward path `FUN_005303ed`, else `0x5325ee`. `v` = `+0x24` of that
  record (`FUN_005493d0`; no other reader), 0 if none; the upgrade step also runs when `FUN_0053dd90` (byte `+0xa78 > 0x32`).
  INFERRED: `+0x24` is written by the event handlers at `0x52f222` / `0x52f2d4` (event kind 8, 9: `(arg1 >> 16)^2 / 5`) and
  `0x52f386` (kind 10: `(arg1 >> 16)^2 >> 3`), each only when the record is still open (`FUN_00548510 == 0`); the senders of these
  event kinds and the meaning of `arg1 >> 16` are not traced. Left: how the upgrade step relates to the hero state kept between maps
  (`FUN_00514920`, [units](units.md#open-questions)); where the campaign town shops get their stock (the exe's server shop above is
  for the multiplayer shop buildings; `Scenario.dll` exports `ScenarioEnterShop`).
