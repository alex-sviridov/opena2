# Spell definitions

Code: `allods2/formats/spelldefs.py` (`load(fs)`, `build(db, texts)`, `SpellTable.get(n)` / `.lookup(name)`,
`SpellDef.scaled(level)`, `level_of`, `damage_taken`); numbers and effect ids: `allods2/spells.py`.
Engine: `AssetCache.spells()`. Export: `python -m allods2 data export spells out/data/spells.json` (gitignored
`out/`; the repo holds only the golden hash `tests/golden.json["spells"]`). Check: `tools/validate_spells.py`.
GOG 1.01, addresses are VAs (sha256 in [formats/README](../formats/README.md)). Tags as in CLAUDE.md.
Related: [databin](../formats/databin.md) (archive, modifier text), [animation](../formats/animation.md) §3.4, §4.4
(cast timing, projectiles), [palettes §7](../formats/palettes.md) (effect ids), [units](units.md) (spell slots,
`known_spells`), [items](items.md) (`castSpell`, scroll/book price), [unit-struct](../engine/unit-struct.md) (orders,
states), [map](../formats/map.md) (dirt).

## 1. Sources

| Data | File | Notes |
|---|---|---|
| definitions | `world/data/data.bin` group 8 | 34 records: 29 named (number n = position, 1-based = `spells.SPELLS`), 5 empty (30-34). The exe's table `0x68f5cc` has 35 slots, slot 0 unused: `FUN_0053e260(n)` = `table[+4] + n*0x20` (CONFIRMED); record = name CString `+4`, parameter array `+8` (`FUN_0041e7e0(k)` = param k), modifier text CString `+0x1c`. Records 30-34 have no name and are never matched (the by-name constructor `FUN_005190e4` searches 1..count-1, "Invalind spell" error otherwise); INFERRED: spare slots, no spell uses them |
| display names | `main/text/spell.txt` | line k = spell k+1 (29 lines); differs from the data name for #16 (Diamond Dust shows as "Stone Missile") and #22 (Control Spirit shows as "Animate Dead"). Loader `FUN_00481186` (list `0x6226e0`, CONFIRMED); readers `FUN_0043901f`, `FUN_0046b9f0` (list use INFERRED) |
| descriptions | `main/text/spells.txt` | 24 lines `Name (Type)#Description` (Type: Homing, Area, Multi-Target, Caster Only, Corpse); order differs from the spells, matched by display name (#22 is spelled "Animated Dead" there); none for Acid Stream, Darkness, Light, Curse, Slow. List `0x6225f0`; the consumer is not identified (INFERRED spellbook tooltip) |
| animation, sound | `graphics/projectiles/projectiles.reg`, `sfx/sfx.reg` | §7 |
| spellbook art | `graphics/interface/SpellBook.bmp`, `SpellBack.bmp` | strings in the exe; no per-spell icon file exists in the install (INFERRED: the book draws names and text) |

## 2. Fields

Params by index (`FIELDS`); values are 32-bit ints; the 22 params and the CString are consumed exactly by the
data.bin loader ([databin](../formats/databin.md)). "Read" = every call site of `FUN_0041e7e0` on a spell record
was scanned (the by-wrapper pattern `[spell+4]+8` and the direct table `0x68f5cc` pattern; no other readers).

| P | Field | Meaning | Tag |
|--:|---|---|---|
| 0 | `complication_level` | extra **recovery ticks** after the cast: `0x50f7e8`-`0x50f80a` adds `*param[0]` of the unit's spell (`unit+0x64`) to the recovery countdown (`unit+0x6c`) | CONFIRMED use; name INFERRED |
| 1 | `mana_cost` | mana spent at cast start; wrapper `+0xc`; also cast XP (§6) | CONFIRMED `0x51922e`, `0x519998` |
| 2 | `sphere` | 1 fire, 2 water, 3 air, 4 earth, 5 astral: skill `unit+0xa8+2*sphere` (= `+0xaa..+0xb2`), damage element (carrier `+0x5d`; switch `0x51a0ff`: `FUN_00543040/70/a0/d0/100`), XP school | CONFIRMED |
| 3 | `item` | never read (0 everywhere); see the note below the table | CONFIRMED unread |
| 4 | `target` | 1 = target unit, 2 = cell/point (`FUN_00519441`: `param[4] == 1`) | CONFIRMED |
| 5 | `delivery` | 2 = missile (flight ticks `dist / speed`, `0x519b17`, `0x51bde1`), 1 = direct (carrier acts at once) | CONFIRMED |
| 6 | `max_range` | cells; wrapper `+9` (`FUN_005195b1`: `+level/30`, Teleport `+level/3`); the AI approach distance (`FUN_0056ac5b`, order `+0x14`) | CONFIRMED use; no range test found at cast (§3) |
| 7 | `speed` | missile speed 1/256 cell per tick; flight ticks `FUN_00516aae(dist in 1/256) / speed`; Lightning and Prismatic Spray (speed 60) are fixed at 5 (`0x519b41`); -1 on Bless/Haste/Curse/Slow is never read | CONFIRMED |
| 8 | `distribution` | shape of the effect: 1 single target, 3 diamond area, 4 wall (line), 5 "field" (Blizzard, Acid Stream); `FUN_00518024`, `0x51baba`, `0x51bd1b` | CONFIRMED values 1, 4, 5; 3 = else branch of `FUN_00518024` |
| 9 | `radius` | `"Radius, Length/2"`: carrier `+0x4d`; diamond = cells with `|dx|+|dy| <= r+1`, wall = `r` cells each way of the centre | CONFIRMED `0x51bbf4`, `0x5183a2`, `0x5182b6` |
| 10 | `area_affect` | never read (0 everywhere) | CONFIRMED unread |
| 11 | `area_duration` | area lifetime in 16-tick units; `ticks = p11*16 + level*16/10` (`0x51bcb7`, `FUN_005195b1`) | CONFIRMED |
| 12 | `area_frequency` | never read: the area carrier pulses every 16 ticks (`0x517cfe`: `(+0x50 & 0xf) == 0`) | CONFIRMED unread |
| 13 | `apply_method` | never read | CONFIRMED unread |
| 14 | `duration` | buff duration in 16-tick units: `ticks = ftol(p14 * 1.1^level * 16)` (`0x51b44b`, `FUN_005195b1`) | CONFIRMED |
| 15 | `frequency` | never read (only Poison Cloud has 1; the text term `continuous 8` drives the period) | CONFIRMED unread |
| 16, 17 | `damage_min`, `damage_max` | base damage; see §5/§6; -1 = none | CONFIRMED `FUN_005195b1` |
| 18 | `defensive` | 1 = friendly spell: wrapper `+0xa`; the AI looks for a friend (`FUN_005679cf`) instead of an enemy (`FUN_00567988`), `0x56c72b` | CONFIRMED |
| 19 | `skill_offset` | never read (0 everywhere) | CONFIRMED unread |
| 20 | `scroll_cost` | scroll price weight ([items §4](items.md)) | CONFIRMED `0x51f48d`, `0x51f7d3` |
| 21 | `book_cost` | book price ([items](items.md)) | CONFIRMED `0x52340f`, `0x524e31` |
| text | modifier text | `name=value[:time]` terms, `"a,b"` for several, `Invisibility = ON`; only the kind and the time are used for 4, 8, 13, 19 (protection), 6 (Poison Cloud: kind `health`), 14/15, 18, 27: the **value is replaced** by a level formula (§6) | CONFIRMED `FUN_0051caa0` + `0x51b3fa` |

Unread params 3, 10, 12, 13, 15, 19 (final answer): no reader exists. Evidence: every call of `FUN_0041e7e0` on a spell record
passes an immediate index (scan of the whole exe, 0x41e7e0 call sites with `[spell+4]+8` and the `0x68f5cc` table), the
only other record access is the loader, and the client spell overview `FUN_00416615` ff. copies a scaled wrapper (`+9`,
`+0xc`, `+0xe..+0x10`) rather than params; no loop over params 0..21 exists (the wrapper fills `+9..+0x10` only). They
are data-editor leftovers (INFERRED purpose); only the wrapper fields of section 3 reach the game.

Classification helpers: `SpellDef.missile`, `.targets_unit`, `.element`, `.handler`. Sphere sizes: fire 4, water 5,
air 6, earth 4, astral 10 (spells 1-4, 5-9, 10-15, 16-19, 20-29).

## 3. Behaviour selection and the cast pipeline

**Mixed**: no effect-type field exists. A spell's behaviour is chosen by (a) the **spell number**: a `switch` of
30 cases in the effect routine `FUN_00519db8` (`jump table 0x51becc`) for every non-damage spell, (b) **data
fields** for the delivery (`delivery`, `distribution`, `target`, `speed`, `radius`, damage, durations), and (c) a hard-coded
**AI table** by number (`FUN_0056a981`). All spells with `damage_min + damage_max > 0` after scaling skip the switch and
use the shared damage branch, except Heal (24) and Drain Life (26), which have their own cases. Handlers by number: §4.

Flow (CONFIRMED unless noted; `U` = unit tick `FUN_0050f12c`, states `+0x54` = 3 attack with a weapon spell, `0xd`
cast at a unit, `0xe` cast at a cell; phase `+0x58`, countdown `+0x6c`):

1. **Order.** Player commands (client messages `0x1e`/`0x1f`, `0x25`/`0x26`: `FUN_005702be`/`FUN_0057033d`) and the
   network command applier `FUN_005503af` create brain order 8/9 via `FUN_0056d3e6` / `FUN_0056d446` (`FUN_004f0832` /
   `FUN_004f086f` for script/trigger casts: `FUN_00578440`, `FUN_005783be`). AI: `FUN_0056acc8` rolls the three monster spell
   slots (probability test against `slot*0x147`, last passing slot wins; Teleport only when the target is more than 2 cells
   away), `FUN_0056a981` maps the spell number to a target (enemy: 1 5 10 11 16 18 26 28 29; cell at the enemy: 2 3 6 7 14 15
   17; self: 4 8 12 13 19 20 21 24 25 27; 9 cell ahead; 23 free cell near the target) and calls `FUN_0056c72b` (order 8, spell
   wrapper in `order+0x30`, range byte `order+0x14` = wrapper `+9`) or `FUN_0056969c` (order 9). Wrapper lookup
   `FUN_0051c391(n)` = the unit's spellbook slot (`unit+0x140`), 0 when the spell is unknown. The AI range is the wrapper
   range only when mana `>=` cost (`FUN_0056ac5b`).
2. **State.** `FUN_0056dca2` (brain order 2) sets state `0xd` / `0xe` (`FUN_0056e906`, `FUN_0056e986`, `unit+0x64` = wrapper,
   target in `+0x5c`, cell in `+0x60/+0x61`). Weapon spells (`castSpell=` on the wielded item) enter via state 3
   (`unit+0x74` weapon, wrapper `weapon+0x84`).
3. **Start (phase 0).** `FUN_00519998(caster, target)`: if the caster has the mage flag (`unit+0x4c & 4`, `FUN_0053a5a0`)
   and is not casting from an item (`unit+0x68 == unit+0x74`), it **fails when mana `unit+0x9a` < cost and otherwise subtracts the
   cost** (the only mana deduction); then target/cell setup (`FUN_0054f955`..), flight ticks (`delivery == 2`:
   `FUN_00516aae(...)/speed`, 5 for Lightning/Prismatic Spray), and the client messages `0x86` (target object) / `0x8b`
   (cell) with projectile id `2n+8` ([animation §3.4](../formats/animation.md)): `FUN_005041d6` / `FUN_005042ba`. Spell 11
   (Prismatic Spray) takes `FUN_00519483` + `FUN_00519c04` (a chain of up to `min(7, L/20 + 2)` targets, `L` from the caster or item count, `FUN_00519db8` on each, no `0x86`). A non-mage unit casting its weapon's spell (`unit+0x74 == unit+0x68`: catapult `Fire_Ball`) returns success at once without the message (INFERRED: the weapon attack path sends the projectile). Cast time:
   countdown `unit+0x134` (windup from the weapon's `windup` param or the monster/human param), phase 5.
4. **Effect (phase 5 reaches 0).** `FUN_00519d7f` (unit target; skips #11) or `FUN_00519db8` (cell) run the effect routine (§4).
5. **Recovery (phase 7).** countdown `unit+0x135 + rand(0..3) + hero_delay + spell.param[0]` (`0x50f7e8`), then ready again
   ([animation §3.1](../formats/animation.md)).
6. **Range / validity.** `max_range` only sets the AI approach distance (`FUN_0056ac5b`) and the order range byte `+0x14`
   (the order walks until within it). No range or line-of-sight test exists on the server cast path (`FUN_00519998`, `U`, the effect
   routines): CONFIRMED by reading `FUN_00519998` and `FUN_00519db8` (the only distance computations are flight ticks). The client-side
   command path (`0x1e`/`0x1f` builders, cursor) is not traced; so a cast from the player UI is limited only by the order
   approach (`order+0x14`), not by a hard check. A failed mana check leaves phase 0 (retried every tick, INFERRED).
7. **Texts.** Unknown spell id: "Invalid spell #0, can't cast" (`0x51be8c`).

Wrapper object (class `0x5d1160`, ctor by name `FUN_005190e4`, by number `FUN_0051906d`, copy `FUN_0051937b`; filled from
the record by `FUN_0051922e`): `+4` record, `+8` number, `+9` range, `+0xa` defensive, `+0xc` mana, `+0xe` damage
min, `+0xf` spread, `+0x10` duration (u16). Level scaling `FUN_005195b1(level)` is called by `FUN_00519483` (cast
time) and rewrites `+9`, `+0xe..+0x10` (§6). Spells are added to a spellbook by `FUN_0051c29e(n)` (console `+spell n` / `+spell all`
in `FUN_004f3d68`, unit creation from `known_spells` bit n, `FUN_00511959`).

## 4. Effect handlers

`FUN_00519db8(caster, target, x, y)` (this = wrapper) is the effect routine; the carrier classes are the objects it builds.
Level `L` = §6. "Carrier" = server object created, then applied to units as an *effect* (`FUN_0051ce12` merges effects of
the same spell id by max value / max time; Bless and Curse replace each other).

| Handler | Spell numbers | Address / case | What it does |
|---|---|---|---|
| shared damage branch | 1 2 3 5 7 9 10 11 16 (dmg > 0) | `FUN_00519db8` `0x51a0e0`..`0x51baa0` | `Effect_DirectDamage` carrier (class `0x5d11d0`, `FUN_0051e505`) with `min'`, `spread'`, element = sphere (`FUN_00543040`..`543100` store `+0x5b`, `+0x5c`, `+0x5d`); effect id `n*2+9` |
| direct apply of damage | all | `FUN_0051e65b` (apply), `FUN_00516f6f` (target take-damage) | §5 |
| point carrier | `distribution == 1` | `FUN_005178d4` (class `0x5d10a0`) | `delivery == 1`: `FUN_00542e60` at once |
| missile carrier | `delivery == 2` | `FUN_00518d1e` (class `0x5d1120`, tick `FUN_00518efd`) | flight `dist/speed` ticks, then `FUN_00542e60` delivers to the carrier (Fire Arrow, Ice Missile, Diamond Dust, Lightning, Prismatic Spray, Fire Ball) |
| area carrier | `distribution` 3, 4 | `FUN_00517c1a` (class `0x5d10e0`, tick `FUN_00517cfe`) | `FUN_00518024` picks the shape by `param[8]`: 4 wall `FUN_005182b6` (line from the direction tables `0x5f8400`/`0x5f84a8`, `FUN_00517ec3`), else diamond `FUN_005183a2`; `FUN_005184bf` adds the cell effect (`FUN_0055a325`; scorches the ground, `FUN_00559c28`, when it carries damage with spread > 0); then every 16 ticks `FUN_00518681` applies to the units in the radius cells until the lifetime `+0x50` (§6) ends (`FUN_00518594`). Mode bits `+8`: 1 = lifetime pulse, 2 = field (§9b), 0 = apply once (`FUN_00518833`: every cell of the radius square, units on both unit slots and the structure, plus scorch `FUN_005189b5`/`FUN_00559c28` for damage carriers; Fire Ball). Wall of Fire (damage), Wall of Earth (cells blocked, no damage), Poison Cloud, Darkness, Light, Fire Ball explosion (`FUN_005183a2` once) |
| field | `distribution == 5`: 7 9 | `FUN_00519db8` `0x51bd1b` (area carrier, mode `+8 = 2`, `+0x50 = 0`), tick `FUN_0051806c` (carrier mode bit 2, `0x517cfe`) | Blizzard (hail stones) and Acid Stream (cone): CONFIRMED, §9b |
| protection | 4 8 13 19 | case `0x51b385` | effect from the text (`FUN_0051caa0` -> `FUN_0051e8fa`, kind `protection<element>`), flags `|= 1`, value `L/2`, duration §6 |
| Bless / Curse | 20 / 28 | case `0x51b82c` | plain effect (`FUN_0051ca4d`, kind byte `+0x3c` stays 0 = no stat change), value `L*4/5 + 20` (`+0x40`), duration §6, bit `1<<spell` set in `unit+0x144`. Not to-hit: the value is a **percent chance for physical hits to roll maximum (Bless) or minimum (Curse) damage**, §5 CONFIRMED `0x516fe6`-`0x5170c4`; spells.txt agrees (Bless: "chances to do maximum damage with a hand-held weapon"). `FUN_0051d175` (effect vtable `+0x40`, per-pulse) only has cases for spell 6 (health), 14, 15 (scan range) |
| Haste / Slow | 21 / 29 | case `0x51b589` | value `L/15 + 1` (negated for Slow), kind speed, duration §6 |
| Shield | 27 | case `0x51b484` | text `absorbtion`, value `L/10 + 3`, duration §6 |
| Darkness / Light | 14 / 15 | `0x51b2de` / `0x51b239` | text `scanRange`, value `-(1 + L/30)` / `1 + L/30`, time from the text (`duration 1` = 16 ticks); area carrier |
| Invisibility | 12 | `0x51b927` | ticks `L*16` (`FUN_00519db8`), 0 = no effect; effect id `0x20` ([palettes](../formats/palettes.md)) |
| Stone Curse | 18 | `0x51b6ae` | ticks `L*15*16*2/100` (normal cast; item cast `*1`); on creatures `rand(0..ticks*(100-protEarth)/100)` (0 = no effect, `unit+0xca`); text terms `absorbtion +5`, `defence -20` |
| Poison Cloud | 6 | `0x51a206` | text `health=-2:continuous 8`: value `ftol(-2 * (L/45 + 1))` every 8 ticks (`FUN_0051cc9f`: mode bit 2 pulses when `ticks & 7 == 0`); area carrier |
| Heal | 24 | `0x51a2b8` | target not hostile (relation matrix `[ +0xa8c4 ] & 1` clear), `hp > -10`, `+0x98 != 0`; amount `min' + rand(1..spread')` capped to `maxHP - HP` (`unit+0x96`, `+0x94`); `FUN_00510484(amount)` |
| Drain Life | 26 | `0x51a3f3` | creature targets only; `amount = (min' + rand(1..spread')) * (100 - protAstral) / 100` (int, `unit+0xcc`), capped at `target HP + 10`; target HP `-= amount`, caster `FUN_00510484(amount)` (heal), XP credit vtable `+0x6c` |
| Summon | 25 | `0x51a595` | CONFIRMED, §9b: one monster per cast near the caster |
| Control Spirit ("Animate Dead") | 22 | `0x51a91f` | CONFIRMED, §9b: raises a corpse on the target cell as zombie / skeleton / ghost |
| Teleport | 23 | `0x51a554` | `FUN_0055a96c(caster, cell)` then `FUN_00502019`; client effect `0x36` ([animation §4.4](../formats/animation.md)) |
| XP | all | vtable `+0x70` = `FUN_005131ef` (`0x519f42`) | `AddExp(ftol(0.5*mana + 0.5), 0, sphere)` when casting at a unit, mage flag only |

Not reached from the switch: `FUN_00519d7f` skips spell 11.

## 5. Damage and protection

`FUN_00516f6f(damage record, attacker)` is creature take-damage (vtable `+0x54` of the unit class `0x5d0f40`; structures:
`FUN_005201b2`). A spell carries only the elemental part (physical bytes 0): CONFIRMED structure, elemental kind byte
`+0x15` = 1..5 = fire..astral, min `+0x13`, spread `+0x14`:

```
rolled   = min' + rand(0..spread')                                   // FUN_0051fa25(n) = rand()*(n+1) >> 15
dmg      = rolled                                   if protection[kind] == 0
         = ftol(rolled * (100 - protection[kind]) / 100 + 0.75)       // clamped >= 0; x87 constants 100.0, 0.75
protection[kind] = short at unit + 0xc4 / 0xc6 / 0xc8 / 0xca / 0xcc  // fire, water, air, earth, astral (data.bin prot_fire..)
HP (unit+0x94) -= dmg                                                 // FUN_0051e65b; the attacker gets XP credit
```

Spells always hit (no to-hit roll: the elemental part is applied when the physical part is empty, `0x5171a4`). The physical part
of the same routine (weapon hits) rolls `rand(0..200) - 100` against defence: hit when `defence < toHit + roll`, or roll >= 90;
roll < -90 never hits; Bless / Curse change only the damage roll (§4): `min' = min + spread` and no random part with chance
`value` (`value > rand(0..100)`) for Bless, no random part (damage = min) for Curse. Units with flag
`+0x4c & 8` take 0. Effect `FUN_0051e65b` runs once per application: missile/point once; area carriers once per 16-tick pulse per unit
in the cells. The other protection uses are Stone Curse (earth) and Drain Life (astral); Poison (`health` continuous) ignores
protection (no use found). XP: damage credit and cast credit into the spell's school, see [progression §4](progression.md#4-xp-sources).

## 6. Level and scaling

Level `L` of a cast (`FUN_00519db8`, `FUN_00519483`; clamp 0..255): from a **unit**: `skill[sphere] - 30 + Mind`
(`unit+0xa8+2*sphere`, `unit+0x88`; monsters: `spell_power` fills all schools); from an **item** (`castSpell=Name:N`,
`unit+0x68 != 0`, `FUN_005238c5`): `N` (so a staff `Fire_Arrow:1` is level 1; a scroll `:50` level 50; no mana). `SpellDef.scaled(L)`
reproduces `FUN_005195b1` (tests): `m = L/30 + 1` (double), `range = p6 (+ L/30; Teleport + L/3)`, `min' = ftol(p16*m)`,
`spread' = ftol(p17*m - min')` (both bytes), duration (u16 ticks): `p14 > 0`: Invisibility `L<<4`, Stone Curse `L*480/100`,
else `ftol(p14 * 1.1^L * 16)`; `p14 <= 0, p11 > 0`: `(p11<<4) + (L<<4)/10`. Example, Fire Arrow: L=1 5..10, L=30 10..20
range 8, L=60 15..30 range 9, L=99 21..43 range 10. Value formulas of the buffs are in §4.

## 7. Animation and sound links

Projectile / effect id = `2n+8` (flight, unit-attached) and `2n+9` (impact, area), `projectiles.reg` ([animation §1.2, §4.4](../formats/animation.md))
via `anim.load_projectile_set(id)`; the folder name is `File`. Cast sound: `FUN_00467da8` (client cast action `+0x60`) plays
sfx id `500 + obj+0xac` where `obj+0xac` = byte `msg+0xc` of message 0x86/0x8b = the **projectile id** (CONFIRMED
`0x467db4`-`0x467dc6`; the table is `0x627740`); the hail stone plays 523 at age 8. `sfx/sfx.reg` maps the id to a file
(`sfx/magic/<name>.wav`, all exist). Cast client action: `FUN_0046707e` spawns the projectile ([animation §3.4](../formats/animation.md)).

| n | Spell | `2n+8` | `2n+9` | cast sound | hit sound |
|--:|---|---|---|---|---|
| 1 | Fire Arrow | 10 firebolt (+ smoke trail) | 11 - | 510 arrow | - |
| 2 | Fire Ball | 12 fireball (+ trail) | 13 fireexpl | 512 fireball | 513 explosion |
| 3 | Wall of Fire | 14 - | 15 firewall (cells) | 514 - | - |
| 4 | Protection from Fire | 16 p_fire | 17 - | 516 pfire | - |
| 5 | Ice Missile | 18 icemissile | 19 - | 518 icemissile | - |
| 6 | Poison Cloud | 20 poison_d | 21 poison (cells) | 520 poison | - |
| 7 | Blizzard | 22 - | 23 Meteor (hail) | 522 - | 523 blizzard |
| 8 | Protection from Water | 24 p_water | 25 - | 524 pwater | - |
| 9 | Acid Stream | 26 - | 27 acid | 526 acid | - |
| 10 | Lightning | 28 lightnin | 29 - | 528 lightning | - |
| 11 | Prismatic Spray | 30 chain | 31 - | 530 spray | - |
| 12 | Invisibility | 32 - | 33 - | 532 invisib | - |
| 13 | Protection from Air | 34 p_air | 35 - | 534 plight | - |
| 14 | Darkness | 36 - | 37 - | 536 darkness | - |
| 15 | Light | 38 - | 39 - | 538 light | - |
| 16 | Diamond Dust | 40 meteorit | 41 - | 540 dust | - |
| 17 | Wall of Earth | 42 - | 43 wall (cells) | 542 wall | - |
| 18 | Stone Curse | 44 - | 45 - | 544 stone | - |
| 19 | Protection from Earth | 46 p_earth | 47 - | 546 pearth | - |
| 20 | Bless | 48 bless | 49 - | 548 bless | - |
| 21 | Haste | 50 - | 51 - | 550 haste | - |
| 22 | Control Spirit | 52 - | 53 - | 552 spirit | - |
| 23 | Teleport | 54 teleport | 55 - | 554 teleport | - |
| 24 | Heal | 56 healing | 57 - | 556 heal | - |
| 25 | Summon | 58 - | 59 - | 558 summon | - |
| 26 | Drain Life | 60 Drain | 61 - | 560 drain | - |
| 27 | Shield | 62 shield | 63 - | 562 pfield | - |
| 28 | Curse | 64 Curse | 65 - | 564 curse | - |
| 29 | Slow | 66 - | 67 - | 566 slow | - |

CONFIRMED by data (test): every missile spell has its projectile record, every record present loads, 27 of 29 cast ids have
an `sfx.reg` entry whose wav exists (not 3, 7). `-` = no record / no `sfx.reg` entry (spells 12 14 15 18 21 22 25 29 have no sprite effect;
Invisibility, Stone Curse draw through unit effects `0x20`, `0x2c`). Wall of Fire (514) and Blizzard (522) have no entry (silent: the sound table `0x627740` is an array of `SfxCount`+1 = 661 slots filled by the loader `0x4c4a48` from keys `Sfx<i>` in `sfx\\sfx.reg` (200 keys exist, 514 and 522 are absent), lookup `FUN_00420eb0` = unchecked index, in bounds; CONFIRMED no file can be named for them, the slot content for an absent key is INFERRED empty; players skip null slots `0x467e1a`, `0x415189`); the
files `sfx/magic/firewall.wav` (sfx id 2), `freeze.wav`, `sacrifice.wav` are not reached by these ids (INFERRED: id 2 is the
cell sound of the wall). The Sfx ids 508 (`ex-water`) = `2*0+8` has no spell.

## 8. Who uses what (install)

Spell slots (monster params 48-53; `spell_1..3`, probability) 54 slots; `known_spells` masks on 132 unit types (bits 1..29); `castSpell=Name:N`
on 162 item/equipment terms (scrolls `:50`, super scrolls `:100`, staffs, `Boulder Thrower {castSpell=Fire_Ball:70}`); `teachSpell=` books for 21 spells.
Every reference resolves (`tools/validate_spells.py`). Campaign maps: units whose type carries a spell slot - Fire Arrow 109 in 6
maps, Ice Missile 65 in 4, Diamond Dust 68 in 4 (maps 90-102); staves `Fire_Arrow` 36 units in 16 maps (earliest 21.alm),
Ice Missile 91, Lightning 58.

## 9. Prototype spell (phase I step 32)

**Fire Arrow** (#1). Chosen over Ice Missile (#5), Diamond Dust (#16) and Lightning (#10):

- Same parameter row as Ice Missile and Diamond Dust (mana 3, range 7, speed 200, damage 5-10), so the generic
  missile + damage path built for it also serves #5 and #16 by changing sphere only (protection index, sprite, sound).
  Lightning needs the special chain draw (ids 0x1c, fixed 5 ticks, 13-tick effect), a later step.
- It is the first spell a player casts: both start heroes (`Start_MM`, `Start_FM`) wield `Wood Staff {castSpell=Fire_Arrow:1}`
  (item cast: level 1, no mana), `Mage_Hero` knows it, `Orc_Shaman.1-5` and 34 staff strings use it; it appears in 16 campaign maps
  from 21.alm.
- Visual / audio needs are minimal: projectile 10 (`firebolt`, `A16 = 1`, 16 directions) with the smoke0 trail already in the
  anim API, no impact sprite (id 11 has none), sound `sfx/magic/arrow.wav` (510).

Everything it depends on:

| Part | Dependency |
|---|---|
| Params | complication 3 (recovery +3 ticks), mana 3, sphere 1 (fire), target 1 (unit), delivery 2 (missile), range 7, speed 200, distribution 1, damage 5..10, defensive -1, scroll 50, book 1000 |
| Order -> state | `FUN_0056c72b` / `FUN_005702be` -> `FUN_0056dca2` -> states `0xd`/`0xe` (`FUN_0056e906`/`986`), weapon spell via state 3 and `weapon+0x84` |
| Cast start | `FUN_00519998`: mage-flag mana check + spend (3), flight ticks = `trunc(dist*256)/200` (`FUN_00516aae`), messages `0x86`/`0x8b` projectile id 10 ([animation §3.4](../formats/animation.md)), client action `FUN_0046707e`, sound 510 |
| Timing | windup `unit+0x134`, effect at phase 5 -> 0 (`FUN_00519d7f`/`db8`), recovery `+0x135 + rand(0..3) + hero_delay + 3` |
| Level | unit: `skill_fire - 30 + Mind`; staff/scroll: item count N. `scaled(L)`: min' `ftol(5*(L/30+1))`, spread' `ftol(10*m - min')` |
| Effect | `FUN_00519db8` damage branch: `Effect_DirectDamage` `0x5d11d0`, element 1, missile carrier `FUN_00518d1e` (flight `dist/200`) -> `FUN_00542e60` -> `FUN_0051e65b` -> `FUN_00516f6f` |
| Damage | `min' + rand(0..spread')`, then `ftol(d*(100 - prot_fire)/100 + 0.75)`; HP `unit+0x94`; 0 if flag `+0x4c & 8` |
| Resistance | `prot_fire` of monsters/humans (data.bin): e.g. Squirrel.4 50, Catapult 0, Dragon high; item bonuses `protectionFire` |
| Anim | projectile 10 `firebolt\sprites` (`A16 = 1`), trail `smoke0`, phase `(age/2) mod Phases`, `anim.load_projectile_set(10)` |
| Units | spellbook `unit+0x140` (known bit 1), AI slot 1 (`Squirrel.4/5`, probability 10) via `FUN_0056acc8`, staffs in 16 maps |
| Items | `Scroll Fire Arrow` (`:50`), `SuperScroll Fire Arrow` (`:100`), `teachSpell=Fire_Arrow` book |

Damage example, hero staff (L=1): `5 + rand(0..5)`; Orc_Shaman.5 (`:99`): `21 + rand(0..22)` before protection.

## 9b. Field carriers, summons, raising, tooltip

All CONFIRMED in allods2.exe unless tagged. Code: `spelldefs.py` constants and functions named below.

**Field carriers (Blizzard 7, Acid Stream 9; `distribution == 5`).** `FUN_00519db8` `0x51bd1b` builds the area carrier
(`FUN_00517c1a`: centre = target cell, `+0x4d` radius, unused here) and forces mode `+8 = 2`, `+0x50 = 0`, ignoring `area_duration`
and `radius`. Carrier tick `FUN_00517cfe` -> `FUN_0051806c`: `+0x50` counts down, a *step* runs when it reads 0 and reloads 2, so
steps fall on the 1st tick and every 3rd tick after (`*_PERIOD = 3`). Per step, per cell of the pattern: the cell must be valid
(`FUN_0054fca8`, 8..size-9, `cell_valid`); the effect id is set to `2n+9` and message `0x86` (cell effect, lifetime byte = the
sprite ticks) is sent (`FUN_00504524`), then the damage effect is applied at once (before the sprite lands) to the unit in each of
the two unit slots of the cell and to the structure (`FUN_0055201a`, `FUN_00552079`, `FUN_00559b7f` -> `FUN_00518681`). No
friend/foe test in the loop. `FUN_00518681` (all carriers): skipped for Wall of Earth (17); Fire Ball takes the explosion path; otherwise
effect vtable `+0x3c` (apply); for creatures it then records the caster as attacker (`param[0x10]`, the monster spell caster byte)
and alerts the AI (`FUN_0056e6b8`), except for Light.
- Blizzard: 32 steps (`BLIZZARD_STONES`), one stone per step at `target + (rand(0..5) - 2, rand(0..5) - 2)` (x then y, `blizzard_offset`),
  96 ticks; stone sprite id 23 (`Meteor`), lifetime 16 ticks (cast sound 522 absent; hail plays 523 at age 8). Each stone hits one cell with
  the spell damage (10..30 scaled, water) once.
- Acid Stream: 6 steps (`ACID_STEPS`), 18 ticks; step `s` hits the rows of `ACID_AXIS[s]` (sectors 0, 2, 4, 6) or `ACID_DIAG[s]` (1, 3,
  5, 7) around the target cell, rotated by `acid_cells`; the sector is `direction8(target - caster)` (`FUN_00556b2c`). Axis rows widen
  1, 3, 5, 7, 9 cells forward; quirks kept: axis step 2 repeats cell (-1, 2) (that cell is hit twice, (-2, 2) never) and axis step 5 is empty
  while the diagonal step 5 has 6 cells. Sprite id 27 (`acid`), lifetime 18 ticks, no sound (527 absent); damage 10..14 scaled, water.
- Point/area activation: a missile carrier (`FUN_00518d1e`, flight `FUN_00516aae(dist)/speed` ticks; Lightning and Prismatic Spray
  override it to 10 ticks, `0x51be87`) and direct casts end in `FUN_00542e60`, which is a plain list append of the pending carrier
  to the world's active-carrier list (`*0x6044c4 + 0x7c`); carriers are then ticked each server tick. It sends no message.

**Summon (25, `0x51a595`).** One unit per cast, no level dependence. Family roll `rand(1..3)` -> `Squirrel`, `Turtle`, `Foot_Animated`; tier
`clamp(skill_astral / 25 + 1, 1, 4)` from the raw skill word `unit+0xb2` (not the level); tier 1 has no suffix, otherwise `.N`
(`summon_unit`; the types exist as `Name`, `.2`..`.5`). The unit is created by name (`FUN_0050e173`), placed within 6 cells of the
caster (`FUN_00510089`), owner = caster's player, `+0x1a0 = 1` (no loot, no XP), master id `+0x148` = caster id, brain mode 1.
No timer: minions persist, but a master with `n >= 2` minions loses one every 16 ticks with probability `(n-1)/100`
(`FUN_0052bbb7`, tick `& 0xf == 0xc`, `minion_expiry_chance`); a minion's death handler sets HP -10000 at once (`FUN_00510a70`), so no corpse
remains.

**Control Spirit / "Animate Dead" (22, `0x51a91f`).** Target = cell. Corpse stage `unit+0x13c` is derived from HP by the corpse
decay `FUN_005110b8` (run every 16 ticks per corpse, HP -1 per run, types 0x21..0x24 heroes stop at HP -60): `corpse_stage`
(HP < -10 -> 2, < -20 -> 3, < -40 -> 4, < -600 -> 5 removed). The spell searches the corpse list for a stage-2 corpse on exactly the
target cell (`FUN_0054fa73`, cell index equality), then stage 3, then 4; types `unit_type` 0x52..0x62 (zombies, skeletons) are skipped.
The corpse is consumed (stage 5, HP -10001). The new unit (`+0x1a0 = 1`, master 0, owner = caster's player, brain mode 3, permanent,
level-independent) appears on that cell with copied stats (`raise_dead`): stage 2 `F_Zombie.1` (body, mind, spirit, max HP copied,
reaction/2+1), stage 3 `F_Skeleton.1` (body and reaction /2+1, max HP/2), stage 4 `Ghost` (reaction/2+1, max HP/2); attack skill `+0xa6`
and defence `+0xbe` copied; HP = max HP. Whether the template recompute (vtable `+0x58`) overrides the copy: INFERRED not.

**Spell level of a hero (cast side).** The client overview (`FUN_00416615` loop over 24 spells, order `SPELLS_TXT_ORDER`) computes per party
member `L = clamp(skill[sphere] + mind - 30, 0, 255)` from view bytes `+0x156+sphere` and `+0x145`, scales a wrapper copy (`FUN_0051951d`)
and sums / min-maxes the party. Same formula as the server (`level_of`).

**Spellbook tooltip (`FUN_004c628f`).** Shown for the spell under the cursor when the party knows it. Text: `spells.txt` line `k` (title
and description, `#` = line break) for spell `SPELLS_TXT_ORDER[k]` (table `0x5f8124`), then rows built from `main.txt` labels, each shown
as `x` or the party range `x...y`: Mana cost (117), Damage (118, sum over the party), Range (123), Duration (124, ticks/16 s, `%5.1f`),
Speed (182), Resistance (183, protection `L/2`), Sight (184), Maximum Damage Probability (185, Bless value), rays (186, Prismatic Spray
`min(7, L/20+2)`), Minimum Damage Probability (187, Curse value), Absorption (217, Shield `L/10+3`). Row-to-array pairing for Speed and
Sight is INFERRED (spell-number helpers `0x5197e3`..`0x519966` fill the arrays; Stone Curse forces its minimum duration to 0).
Display names come from `spell.txt`, descriptions only for these 24 spells (no entry for 9, 14, 15, 28, 29).

## 10. VERIFY IN GAME

- Fire Arrow damage and flight time against §6/§5 (staff level 1 and a scroll `:50`: 5..10 vs 13..26; rounding of `m`).
- That the player UI refuses or walks to out-of-range targets (server has no check, §3); Blizzard / Acid Stream stone and cone visuals against §9b.

## 11. Open questions

- Client cast command path: cursor / spell button -> messages `0x1e`/`0x1f`, `0x25`/`0x26` (`FUN_005702be`, `FUN_0057033d`), range / mana / known-spell checks on the client; start `FUN_005702be`.
- Brain registration of minions: Summon uses `FUN_005709d9` (brain byte `+0x20` = 1), Control Spirit `FUN_00570b8b` (`+0x20` = 3); meaning of the modes.
- Spellbook tooltip arrays for the rows Speed (0xb6), Sight (0xb8) and which spell fills them (`FUN_00416615` ff., `FUN_004c628f`).
