# Item definitions

Code: `allods2/formats/itemdefs.py` (`load(fs)`, `build(db)`, `ItemTable.lookup(code)`, `.resolve(code, effects)`,
`.class_stats`, `.price_with_effects`, `.parse_effects`, `.parse_equipment`, `icon_path`, `load_packets`).
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
| 0, 1 | shape, material | never read in the item code (0 or -1 in the data) | INFERRED unused |
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
| 16 | other | never read in the item code (armour 1-10, `Cap` 1 .. `Dress` 10) | INFERRED unused |
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
ftol(quality[6] * material[6])` (item `+0x48`; what reads it: open). CONFIRMED `FUN_00528c92`, `FUN_0052765b`, `FUN_0052810d`.
Worked example: Common Iron Long Sword (28..56 damage, to hit 3): min 6, spread 5, to hit 3, price 600, weight 20.

Masks: class record word `q` (q = quality 0..6) bit `m` says "may be made of material `m`" (`FUN_005247db` tests
`word[q] & 1 << m`). The 395 allowed combinations are exactly the 395 class items of `itemname.bin` (test).

## 4. Price

`item +0x1c` is the price (CONFIRMED: `FUN_00528e04` weapons, `FUN_00527862` armour, `FUN_0052823a` shields; loot window
`FUN_005247db` compares it with the monster `item_value_min/max`, [units](units.md)). All gold amounts, shop prices
and the pile frame total are this value.

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
-, -, ring, amulet, hat, robe, cloak, -, gloves, -, shoes). `FUN_00526ec4` rolls `r = rand(total)` and takes the stat whose
cumulative range contains `r`, then `FUN_0051f7d3(budget, magic capacity)` for the magnitude: CONFIRMED structure, role of its
parameters INFERRED. `slot_weights(slot, mage)` returns the differences.

## 6. Who may use an item

`FUN_00512573` (equip by name, also CONFIRMED structure for the human constructor): a weapon, armour or shield is equipped
only if `suitable_for & 1` for a fighter or `& 2` for a mage (mage = carrier flag `+0x4c` bit 4, `FUN_0053a5a0`). No other
requirement (skill, Body, level) is read by the item code: CONFIRMED absent in `0x522000-0x52b000`; other requirement
checks in the inventory UI or the server: not searched, see open questions.

## 7. Special items

96 records (`Price`, `weight`, flag byte always 1, text). The sub-type is the **name prefix** (`FUN_00523148`, CONFIRMED):
`Potion` 3, `Book` 5, `Scroll` and `SuperScroll` 4, else 0 (quest). 5 books (one per school: Air, Water, Fire, Earth,
Astral), 29 scrolls (`castSpell=..:50`), 29 super scrolls (`:100`), 13 potions (`health=+30`, `body=+1`...), 20 quest items
(text `1` or empty). Item `+0x44` holds this tag; class items use 1 armour/shield, 2 weapon.

## 8. Names, icons, packets

- Name: `itemname.txt[i]` for `itemname.bin[i]`. Class items read `Bronze Dagger`; the five books are all `Book`, scrolls
  `Scroll` / `Elven Scroll`: the spell part is added elsewhere (UNKNOWN).
- Icon (`FUN_00438ba1`, CONFIRMED, all 491 files exist): class items `graphics/inventory/` + `%02d%02d%1d%02d` of
  (material, class, quality, index) + `.16a`; special items `%02d%02d%03d` of (material, 14, `code & 0xFF`). Class is the
  code field (armour: the slot). Ground pile: the backpack sprite frame from the pile total ([map](../formats/map.md#drawing)).
- `itemname.pkt` (INFERRED layout; tiles exactly): 9 header bytes, then records `u16 code, u8 1, u8 0, u8 a, u8 b, u8 n,
  n payload bytes`; `a, b` unknown (the client copies `b`, `0x4388a2`). Payload: `01`, `u32 price`, then (class items)
  `(stat, value)` byte pairs: 12 to hit, 13 damage min, 14 spread, 15 defence, 16 absorption, 38 range (only with
  damage); specials: `33 00` then pairs (`29 spell charges charges` for scrolls). All 409 class prices and stat pairs equal
  §3/§4 (the pkt is the client's copy of the computed item). Scroll price in the pkt is `trunc(scrollCost * 2^(...) / 50)`
  (58 of 58), not the record price the exe computes in §4: VERIFY IN GAME.

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
resolve, golden hash `["items"]`. `tools/validate_items.py` runs the same checks.

## VERIFY IN GAME

- Price shown for a Common Iron Long Sword (600) and a Rare Bronze one (600), a Rare Mithrill Helm with `{defence=13}`.
- Scroll of Fire Arrow price in a shop: record price 100 (§4) or about 41 (pkt).
- A two-handed weapon pushes the shield into the pack; a mage cannot equip a Long Sword, a fighter cannot equip a Staff.
- Weight: Bronze Cuirass 38, Meteoric / Crystal items heavier (material f64 1).

## Open questions

- What reads `magic_cap` (item `+0x48`, quality level x material `MagCap`) and the parameters of the random modifier roll
  `FUN_00526ec4` / pool builders `FUN_005247db`, `FUN_00524e31`; loot `item_flags` ([units](units.md#open-questions)).
- Class params 0, 1, 16 and the special-item byte: no reader found; itemname.pkt header bytes `a, b`.
- Requirements outside the item code (UI, server), how a spell name is appended to `Book` / `Scroll`, scroll price (§8).
- Elemental damage kinds of `damageFire..Astral` in combat (carrier `+0xf9..+0xfb`, [units](units.md#open-questions); the formula for spell damage is in [spells §5](spells.md#5-damage-and-protection)).
