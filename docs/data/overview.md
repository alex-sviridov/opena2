# Game data layer: overview and handoff

One page over the data tables the engine reads. Facts live in the linked specs; marks as in CLAUDE.md. All tables are
built from `world/data/data.bin` (plus small text files), cached by `AssetCache` (`allods2/assets.py`), exported with
`python -m allods2 data export units|items|spells|progression out/data/<name>.json` (gitignored `out/`), and pinned by
`tests/golden.json` (keys `units`, `items`, `spells`, `progression`; regenerate with `tools/update_golden.py`).

## 1. Tables

| Table | Source | Status (open) | Loader / AssetCache | Engine consumer |
|---|---|---|---|---|
| data.bin | `world/data/data.bin` (MFC archive, groups 1-8 and structures) | CONFIRMED, consumed exactly; every column named ([databin](../formats/databin.md)). Open: human/structure fields read in code | `allods2.databin.databin(fs)`, `AssetCache.databin()` | `World` (structure footprints `databin().structures`), all tables below |
| units | data.bin group 5 monsters (`serverID` p55), group 6 humans (p24) | CONFIRMED loaders and most fields; 464 types. Open: damage kinds 1/2 element, resistance scaling, negative spread ([units](units.md)) | `formats.unitstats.load/build`, `AssetCache.unit_stats()` | `World._load_units` (`Unit.stats`, HP, movement type, face); not yet used for stats in play |
| items | data.bin groups 1-4, `itemname.*`, `itemname.pkt` | CONFIRMED class stats, scaling, price, modifiers, generator; 162 definitions, 491 named items ([items](items.md)) | `formats.itemdefs.load/build`, `formats.itemgen`, `AssetCache.items()` | none yet (ground piles hold raw codes, `World._load_items`; inventory and loot are phase I) |
| spells | data.bin group 8, `spell.txt`, `spells.txt` | CONFIRMED params 0-18, 20-21, handler per spell, level scaling, damage; 29 spells ([spells](spells.md)). Open: unread params 3, 10, 12, 13, 15, 19 | `formats.spelldefs.load/build`, `AssetCache.spells()` | none yet (phase I prototype: Fire Arrow) |
| progression | exe formulas (XP curve, recompute) and data.bin humans (hero templates) | CONFIRMED curve, award, recompute, hero start; 6 templates ([progression](progression.md)). Open: kill-credit caller, quest XP, skill 0 role, carry-over | `formats.progression.load/build`, `AssetCache.progression()` | `World._load_units` (`Unit.skills`, `xp`, `xp_total`, `best_school`); no award logic yet |
| map entities | `.alm` sections 5, 6, 8, 9 | CONFIRMED, tile all 46 maps ([map part 5](../formats/map.md)). Open: section 9 per-cell payload, sections 7, 10-12 | `Map.players/.units/.item_groups/.item_records` | `World._load_players/_load_units/_load_items` |

## 2. Cross-reference check

`tests/test_data_integration.py` (needs the install) loads every table and resolves: monster type -> units.reg set, item code
-> inventory icon and paper-doll layer, missile spell -> projectiles.reg record, and for all 46 campaign maps: unit
`server_id` -> data.bin record and units.reg set, item groups -> item definition, icon and claimed-record stat ids, spell ids
(record spells, unit slots, `known_spells` bits) -> spells. Result: no unresolved reference except the explicit exclusions
below (each is a list in the test, asserted to still be true).

| Exclusion | Why |
|---|---|
| monsters `Root` (`unit_type` 78) and `Human` (serverID -1) have no units.reg set | no campaign map places them (INFERRED: editor/unused records) |
| humans are not checked via `unit_type` | the by-name ctor overwrites it with 0x21-0x24 ([units](units.md)); the sprite set of a map human comes from the section 6 `type`, checked per map |
| weapons 1 BareHands, 23 `rem`, 24 Sonic Beam, 25 Flame Thrower, 26 Boulder Thrower, 27 Plasma Sword have no item code | monster natural weapons reached by name through equipment strings; 23 is a placeholder, 27 is never equipped (INFERRED) |
| special items (class 14) have no paper-doll layer | never drawn on the doll ([paperdoll](../formats/paperdoll.md)) |
| spells 12 14 15 18 21 22 25 29 have no projectiles.reg record | they draw through unit effects or not at all ([spells §7](spells.md)) |

## 3. Handoff to movement and combat (phases H, I)

**Movement** (H1; [unit-struct](../engine/unit-struct.md), [animation §3.4](../formats/animation.md)). Source field: monster
`speed` (p8, `+0x8c`) or the human recompute (`Reaction`, see [progression §3](progression.md)); effects Haste/Slow add to
it. Step length `mover+0xa8` is in 1/256 cell per tick, clamp 1..63, computed by `FUN_00559195` (group speed byte `+0x44`
overrides the unit speed in formation; ground units scale by terrain cost and height difference, fliers do not); diagonals
use 0.707; ticks per cell = `ceil(256 / larger component)` (`+0xaa`). CONFIRMED in the linked specs and re-read in the exe for this page (`FUN_00559195`: clamp 1..63, `+0xa8`, `+0xaa`). `turn_rate` (monster p9,
human p7) feeds `mover+0xa`. Block layers and movement masks: [map part 3](../formats/map.md).

**Attack fields** (names as exported). Monsters: `damage_min`/`damage_max` (stored as min + spread), `damage_kind` (-1/0
physical, 1, 2, 3 ignores absorption), `to_hit`, `defence`, `absorption`, `windup`, `recovery`, `prot_*`, `res_*`. Humans have
no damage fields: they come from the weapon (itemdefs `damage_min`, `damage_max`, `to_hit`, `attack_type`, `range`, `windup`,
`recovery`) and the recompute. Attack range: weapon `range` (-1 gives 1), spell `max_range`, creature default `+0x12c`;
the AI approach distance is `FUN_0056ac5b` ([unit-struct](../engine/unit-struct.md)). Cooldown: server hit at `windup` ticks
after the attack message, recovery `+0x135 + rand(0..3)` + hero delay ([animation §5.3](../formats/animation.md)).

**Still to reverse and implement in phase I.**
- Hit chance and damage: `FUN_00516f6f` (`0x516f6f`, re-read for this page, CONFIRMED) is the whole resolution: with
  `r = rand(200) - 100` a physical hit lands if `defence < toHit + r`, or `r >= 90` (always hits), and never if `r < -90`;
  flag `0x10` of the attacker skips the roll and the absorption; absorption is subtracted from physical damage (min 0),
  element parts follow with their protection (`+0xc4..+0xcc`); the attack record packs min/spread (bit 7 = stored /15).
  Open: scaling of resistances and protections, damage kinds 1/2 ([units](units.md)). To-hit sources for
  humans ([progression §3](progression.md)): `(1.1^Body + 1.1^Reaction) / 5`, +3 per school skill with a melee weapon.
- Derived max HP/mana: the exe never uses the template `healthMax` of humans; the recompute (`FUN_0051366b`) sets it and the manaMax-derived
  mana. All 605 campaign human units take this value (their map HP is default), e.g. `2A_Knight4` 167 not 351. `progression.derived_vitals`
  implements it and `World._load_units` uses it for every human ([progression §6](progression.md#6-hero-start)); bonus block and difficulty
  tweak are not modelled yet.
- XP awards (per-hit and per-cast credit plus the kill credit when a death completes): [progression §4](progression.md).
- **Prototype spell Fire Arrow** (#1): everything it needs is tabulated in [spells §9](spells.md): params (mana 3, range 7,
  speed 200, damage 5..10), order -> state -> cast start (`FUN_00519998`), windup/recovery timing, level `skill_fire - 30 +
  Mind` and `scaled(L)`, damage branch `FUN_00519db8` -> `FUN_00516f6f`, `prot_fire`, projectile 10 (`firebolt`, trail
  smoke0, sound `sfx/magic/arrow.wav`), spellbook `unit+0x140` bit 1, staffs `castSpell=Fire_Arrow` in 16 maps.
