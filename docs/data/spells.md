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
| Heal | 24 | `0x51a2b8` | (engine: built, §9d) target not hostile (relation matrix `[ +0xa8c4 ] & 1` clear), `hp > -10`, `+0x98 != 0`; amount `min' + rand(1..spread')` capped to `maxHP - HP` (`unit+0x96`, `+0x94`); `FUN_00510484(amount)` |
| Drain Life | 26 | `0x51a3f3` | (engine: built, §9d) creature targets only; `amount = (min' + rand(1..spread')) * (100 - protAstral) / 100` (int, `unit+0xcc`), capped at `target HP + 10`; target HP `-= amount`, caster `FUN_00510484(amount)` (heal), XP credit vtable `+0x6c` |
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
there is no "roll < -90 never hits" rule (the branch exists but changes nothing, [combat §5.2](../engine/combat.md)); Bless / Curse change only the damage roll (§4): `min' = min + spread` and no random part with chance
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

## 9c. The cast chain of a unit-target spell (I4a research, REA of the GOG exe)

CONFIRMED by decompilation unless tagged. `unit+0x1c4` = brain, `unit+0x54` state, `+0x58` phase, `+0x6c` countdown, `+0x134` windup byte, `+0x135`
recovery byte, `+0x136` done flag, `+0x5c` target, `+0x60/+0x61` target cell, `+0x64` spell wrapper being cast, `+0x68` item the cast comes from
(0 = a learned spell), `+0x74` wielded weapon. Wrapper (`FUN_0051c391(n)` / item wrapper `FUN_0051906d`): `+4` spell record, `+8` spell number,
`+9` scaled range, `+0xc` mana cost, `+0xe/+0xf` scaled damage min' / spread' (bytes).

### 9c.1 Command and order (client -> server)

| Fact | Where | Tag |
|---|---|---|
| Client, cast at a unit: `FUN_004195fa(target unit id, spell button)` builds command `0x1e` (operand byte `+0x10` = button, ids = the selected units whose cast mask has bit `button-1`). Nothing is sent unless `FUN_004c70b9(button-1)` (view `+0xd0` object, mask `+0x148`) is set; the item variant (`FUN_004c70fe`, mask `+0x150`) sends `0x25`. The masks are the greyed/enabled state of the spell buttons: **there is no "out of mana" or "out of range" message in this path, the button is simply not usable**. The masks follow the spellbook only, **not the mana** (§9e.1) | `0x4195fa`-`0x419a53`, `0x4c70b9`, `0x4c70fe` | CONFIRMED |
| Server intake `FUN_004f515d`: command `0x1e` / `0x1f` first maps the button to a spell number (table `0x5f8120`, stride 4), then for **every** group member with a spellbook (`+0x140 != 0`): `member+0x44 = FUN_0051c391(spell)` (the unit's wrapper, 0 when it does not know the spell). Cast at a unit (`0x1e`): `FUN_005702be(group, target)` with no further test. Cast at a cell (`0x1f`): only if `FUN_0051941a()` (spell targets a cell) | `0x4f5a22` ff. | CONFIRMED |
| `FUN_005702be`: per member with `+0x44 != 0`: `FUN_0056d3e6(member, target, wrapper)` = cancel (`FUN_0056dbfb`), **order `+0x50 = 0xd`**, brain `+0x28` = target, `+0x30` = wrapper, `+0x14` (range) = wrapper `+9`, brain mode `+8 = 0`; then `+0x44 = 0`. A member with `+0x44 == 0` gets a different call (decompiled as `ReleaseAccessors`, unresolved; INFERRED: it does nothing useful). Group order byte `+0x20` cleared | `0x5702be`, `0x56d3e6` | CONFIRMED |
| Group pass (`tick & 15 == 6`) per-member dispatcher `FUN_00569321`, **order `0xd`** -> `FUN_0056c72b(unit, brain+0x28, brain+0x30)`: brain mode `+8 = 8`, target and wrapper stored again, the **target's** `brain+0xa4` = spell number and `brain+0xa8` = server tick (used by the AI buff logic), final `brain+0x14 = wrapper+9`. Order `0xe` (cell) -> `FUN_0056969c` (mode 9). So a cast starts at the next `tick & 15 == 6`, like an attack | `0x569321`, `0x56c72b` | CONFIRMED |
| Item casts: `0x25` (unit) / `0x26` (cell) set `member+0x68 = item` and `member+0x44 = FUN_0051906d` (a wrapper built from the item, level = the item's count), then the same `FUN_005702be`; on a refused cell cast the item reference is dropped | `0x4f5a22`... `case 0x25` | CONFIRMED |

### 9c.2 Brain mode 8 and the state machine

| Fact | Where | Tag |
|---|---|---|
| Brain tick `FUN_0056dca2`, mode 8 -> `FUN_0056ebc0`: `unit != target` and not (`FUN_0055532d(unit, target, brain+0x14) != 0`) -> `FUN_0056ea52` (the follow driver of melee, turns and walks) and `state = 1`; else `FUN_0056e906` (start). `FUN_0055532d` = facing (`mover[0]`) equals `FUN_005568e4(unit, target)` (the octant to the target) **and** `FUN_00556dcd(unit, target) <= range`: the **same facing + gap-level test as the melee attack** (`combat.attack_mode`, `ai.reach_gap`), with the spell range instead of the weapon range. No line-of-sight, no fog, no mana test here | `0x56ebc0`, `0x55532d` | CONFIRMED |
| `FUN_0056e906` (unit target): brain order `+9 = 2` (cast in progress), count `+0x15 = 0`, **state `0xd`**, `+0x5c` = target, `+0x64` = wrapper, brain `+0x5c = 1`; if brain `+0x60 == 0` -> stop `FUN_0056dbc6`. `FUN_0056e986` (cell): state `0xe`, cell in `+0x60/+0x61`, brain `+0x5c = 0` | `0x56e906`, `0x56e986` | CONFIRMED |
| Brain order 2 (`FUN_0056dca2` else-branch, same shape as the swing's order 1): state := `0xd` if brain `+0x5c` else `0xe`, count `+0x15` += 1; once count > 2 and the done flag `+0x136` is set: brain order 0, state 0, and the `+0x4d+2` ... (the done byte). While brain order != 0 the mode executors do not run, so **a new order cannot interrupt a cast in progress** (the order is stored and takes effect after) | `0x56dca2` | CONFIRMED structure |
| Creature tick `FUN_0050f12c`, states 3 / `0xd` / `0xe` share one phase machine on `+0x58`. **Phase 0**: state `0xd` -> `FUN_00519998(unit, target, 0, 0)` (`0xe`: cell); if it returns non-zero: done flag := 0, phase := 5, countdown := **windup byte `+0x134`** (no arrow-flight extra as in melee). If it returns 0 (mana short) nothing changes: the phase stays 0 and the brain order ends after 3 ticks (done flag still set), mode 8 restarts the cast at once: a **silent retry loop** without messages. **Phase 5**: countdown -= 1; at 0: state `0xd` -> `FUN_00519d7f(unit, target)` -> `FUN_00519db8` (the effect: §9c.3); then (item casts) the item and wrapper are cleared and a **scroll** (`FUN_0053bff0() == 0xe`) is deleted; phase := 7. **Phase 7**: countdown -= 1; at 0: phase 0, done flag := 1 | `0x50f12c` | CONFIRMED |
| Recovery countdown set at the end of phase 5: `L = 0`; if the unit has a weapon `+0x74` and the vtable `+0x30` test (hero) holds: `L = clamp((weapon.weight(+0x4a) + (30 - Reaction(+0x86)) * 5) / 12, 0, 12)` (same as `combat.hero_delay`); `L += FUN_0051fa25(3)` (the engine's `rand(3)`, 0..3); countdown = `+0x135 + L`; **plus the spell's `complication_level` (param 0) when `+0x64` is still set**, i.e. for a learned spell, not for a weapon / item cast (its `+0x64` was just cleared) | `0x50f12c` | CONFIRMED |
| **Mana** (`FUN_00519998`, at phase 0, the first tick of the cast): only if the caster is a mage (`+0x4c & 4`, `FUN_0053a5a0`) **and** `+0x68 == 0` (not an item cast): `mana (s16 +0x9a) < cost` -> return 0 (nothing spent); else `mana -= cost`. A non-mage with a spell pays nothing; an item cast pays nothing. Also: a caster with `+0x74` weapon equal to `+0x68` and not a mage returns 1 at once (no effect; INFERRED the weapon-spell bookkeeping) | `0x519998` | CONFIRMED |
| Same function, for the client visual: `n = trunc(sqrt(dx^2 + dy^2)) / speed` for missile delivery (`param[5] == 2`), 5 for spells 10 and 11, positions in 1/256 cell; message `0x86` (target unit, `FUN_005041d6`) or `0x8b` (cell, `FUN_005042ba`) with projectile id `2n+8` and the flight ticks. A target with footprint size > 1 is aimed at its centre `- 1` in both axes (`FUN_0050d884/0d8c0`). Casting at another unit clears Invisibility (effect kind `0xc`, `+0x42 := 1`, `FUN_005106d2(0xc)`) | `0x519998` | CONFIRMED |
| Hero flags: `+0x4c & 2` (`FUN_00543130`, the "has a spell list" bit) gates the cast XP (`vtable +0x70`, spells.md §4 XP row) for learned-spell casts | `0x519db8` | CONFIRMED test, XP row as §4 |
| **Staff / weapon spells are a branch of the melee swing, not a command**: in state 3 at phase 0 and at the end of phase 5, `weapon (+0x74) != 0 && weapon+0x84 != 0` (`FUN_00542580`, the weapon's spell wrapper from its `castSpell=Name:N` effect) **and the unit is a mage (`+0x4c & 4`)** -> `+0x64 = weapon+0x84`, `+0x68 = weapon`, state := `0xd` and the cast code runs in the same tick (target `+0x5c` = the swing target). So a mage who wields the start staff and is ordered to **attack** casts Fire Arrow instead of hitting: no mana (`+0x68 != 0`), level = the item's count, windup `+0x134`, and at the end of the release `+0x68` / `+0x64` are cleared (a scroll, item class 14, is deleted; a staff stays), so **no complication ticks** in its recovery. Brain order stays 1 (swing) and sets state 3 every tick; the flip happens again at each check | `0x50f12c` case 3, `0x542580` | CONFIRMED |
| The client message of the cast start (`FUN_005041d6`, also for cells) stores the server tick in **unit `+0x138`** (the rest clock of the regeneration): `Unit.step_end := tick` at the cast start | `0x5041d6` | CONFIRMED |
| After `FUN_0056e906` a player's cast leaves Brain mode 0, order `0xc` and `stopped` = 1: `brain+0x60` is 0, so `FUN_0056dbc6` runs right after the state was set (state := 0, the phase machine starts on the **next** tick). Wrapper byte `+0xa` is `defensive == 1` (`FUN_0051922e`), `+9` the base range byte, `+0xc` the mana cost | `0x56e906`, `0x51922e` | CONFIRMED |

### 9c.3 Release, carriers, damage

| Fact | Where | Tag |
|---|---|---|
| `FUN_00519db8(unit, target, x, y)`: **level** (re-computed at release): learned spell `clamp(skill[sphere](s16 +0xa8+2*sphere) - 30 + s16 +0x88, 0, 255)` (the code caps at 255 and floors at 0, both as `level_of`); item cast (`+0x68 != 0`) the count `s16 item(+0x42)` (`FUN_005238c5`) | `0x519db8` | CONFIRMED |
| Target test: a target with vtable `+0x2c != 0` and flag `+0x4c & 8` (off the map) -> the cast ends **with no effect** (mana already spent, recovery still runs) | `0x519db8` | CONFIRMED |
| Damage branch (min' + spread' != 0, spell not 0x18 / 0x1a): an elemental `Effect_DirectDamage` (`FUN_0051e505`) with the caster pointer in `+0x44`, element by sphere (`FUN_00543040/70/a0/d0/100`), min' / spread' from the wrapper; a **point carrier** (`FUN_005178d4`, `PointEffect`) holds target + effect; its caster pointer `+0x3c`, hostile flag `+0x41 = (wrapper+10 == 0)`. `distribution == 1`: `delivery == 1` -> appended to the active list at once; `delivery == 2` -> a **missile carrier** `FUN_00518d1e(point carrier, caster pos, speed)` with `+0x50 = (s16) (FUN_00516aae / speed)` ticks (distance **at release**, caster `unit+0x10` position to the target position as above), set to **10** for spells 10 / 11, appended instead | `0x519db8` | CONFIRMED |
| Carrier list: `FUN_004f04cf` -> `FUN_0052c279` calls vtable `+0x18` of each carrier in list (creation) order, **before the creature pass** `FUN_0052b459` of the same server tick; a carrier is removed when its byte `+0x40` is set. Missile tick `FUN_00518efd`: `+0x50 -= 1`; if `< 1`: `FUN_00542e60(point carrier)` appends it to the **tail of the same list** (visited later in the same pass), `+0x40 := 1`. So a cast released in the creature pass of tick `T` with `N` flight ticks first ticks at `T+1`, the damage is applied at tick `T + max(N, 1)` | `0x4f04cf`, `0x52c279`, `0x518efd`, `0x542e80` | CONFIRMED |
| Point carrier tick `FUN_00517949`: the effect's caster `+0x44` is cleared when the caster object's `+0x14 == 0` (the caster is gone). A target creature is hit **only if its `+0x14 != 0`** (alive in the world): effect apply (vtable `+0x3c`) = `FUN_0051e65b` (§5: `min' + rand(0..spread')`, protection, HP). Then, when the carrier has a caster and the hostile flag: victim `+0x40` (last attacker) := caster (if the caster is still valid) and `+0x48` := spell number, and `FUN_0056e6b8(caster, victim, 0)` (the AI hit reaction) when both are valid. Structures take the `vtable +0x34` branch | `0x517949` | CONFIRMED |
| Nothing in the chain tests the **target's HP**: a unit at HP <= 0 that is still in the world (dying, `+0x14 != 0`) is hit again (same as melee, combat.md 12.2) | `0x517949` | CONFIRMED (absence) |

### 9c.4 Engine mapping and VERIFY IN GAME (I4a)

- Order `0xd` is the cast analogue of the attack order: group pass at `tick & 15 == 6`, then mode 8 with the melee approach (`combat.attack_mode` conditions), `Unit.spell_cast` holds the phase machine, `spells.cast_tick` mirrors `combat.swing_tick`.
- The silent retry loop for insufficient mana is reproduced as is (no event); there is no "no mana / out of range" feedback at all: the button stays enabled whatever the mana (§9e.1).
- Carriers: `World.carriers`; `spells.carrier_system` runs **before** `movement_system` (carriers pass, then creature pass); a missile with `N` flight ticks delivers `max(N, 1)` ticks after the release tick; the point carrier's damage is applied in the same pass.
- INFERRED: casters are "gone" when removed from `world.units`; a caster that dies between release and delivery still lets the carrier hit (the missile is independent), only the attacker credit is dropped.
- VERIFY IN GAME: (1) a hero with the start staff casts Fire Arrow with no mana change; (2) a learned-spell cast with 2 mana left of 3 does nothing and retries silently; (3) the delay between the cast animation start and the first damage number at 7 cells (windup + 8 ticks); (4) Stop pressed during the windup: the cast completes (CONFIRMED structure, §9e.3); (5) a scroll is consumed, a staff is not.

## 9d. AI casts, cell casts and the built handlers (phase K)

The AI's decision is in [ai §12](../engine/ai.md#12-casters-and-special-attacks-confirmed-unless-marked-engine-127). Cast side (CONFIRMED there): an AI cast is
`brain+0x60 := 1` + `FUN_0056c72b` (mode 8) or `FUN_0056969c` (mode 9), so the Brain mode **stays** after the cast starts and the spell is cast again until the next
group pass; command `0x1f` = `FUN_0057033d` -> `FUN_0056d446` (order `0xe`, only `target == 2` spells); mode 9 = `FUN_0056ec3f` (in range: facing to the cell and
Chebyshev `<=` range, else the move driver with stop distance = range); state `0xe` releases through `FUN_00519db8(caster, 0, x, y)`. Monsters: mana = `manaMax`
(`0x5115a5`), skills = `spell_power` or `skill*` (mages), the book = the slot spells or the `known_spells` mask, the mage flag from the mask (ai §12.1).

Engine (`engine/sim/spells.py`): the damage branch (I4a), **Heal 24** (`heal_release`, §4 row, `0x51a2b8`: no effect on an at-war target, HP > -10 and `+0x98 != 0`,
`min' + rand(1..spread')` capped at `maxHP - HP`, `FUN_00510484` with the revive `FUN_00510534`) and **Drain Life 26** (`drain_release`, `0x51a3f3`: astral protection,
cap HP + 10, damage XP credit, hit reaction, last attacker, the caster heals the amount) are built; `FUN_0051fa4e(n)` = `rand(n - 1) + 1`. Every other handler (protections,
Bless / Curse, Haste / Slow, Shield, Invisibility, Stone Curse, the area / field carriers of Fire Ball, Wall of Fire / Earth, Poison Cloud, Blizzard, Acid Stream, Darkness,
Light, Teleport, the Prismatic Spray chain at cast start) is a **documented no-op**: mana, cast animation, windup and recovery run as in the exe,
the release changes nothing and is counted in `World.unbuilt_casts` (spell number -> count; `stub_release`). Not a guess of the effect: they need the effect system
(`FUN_0051ce12`, `+0x144` bits) and the carriers of §4 / §9b. **Summon 25 and Control Spirit 22 are built** (they create units, no effect object: `summon_release`, `raise_release`, [§9b](#9b-field-carriers-summons-raising-tooltip)) when the world carries its asset tables (`World.assets`, set by `from_map`).

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
caster (`FUN_00510089(caster cell, 6)`, the family roll `FUN_0051fa4e(3)` is the first RNG draw; no free cell: the cast ends), owner = caster's player, `+0x1a0 = 1` (no loot, no XP), master id `+0x148` = caster id. Then the minion gets **a group of its own** (`FUN_0052ae43`,
`FUN_0052af8c`), a stand (`FUN_0056dba1`) and **`FUN_005709d9(group, 0)` (`0x51a8d7`) = the player's G command: group order 1, members order `0xb`, radius `MinimalGuardRange`** (10); the awake map is recomputed (`FUN_0055b5f1`). The earlier
"brain mode 1" was a misreading: `+0x20` is the **group record's order byte** ([ai §14](../engine/ai.md#14-the-other-group-orders-confirmed-fun_005700f3-dispatch-engine-implemented-see-the-end-of-this-section)), not a Brain mode; there is no
minion mode. Engine: `spells.summon_release` (`engine/sim/spawn.py` builds the unit from the world's asset tables, `squad` = a private negative number so that it never joins a map squad), with the cap job `spells.minion_job` (called by `vitals_system`).
No timer: minions persist, but a master with `n >= 2` minions loses one every 16 ticks with probability `(n-1)/100`
(`FUN_0052bbb7`, tick `& 0xf == 0xc`, `minion_expiry_chance`; engine `spells.minion_job`: one `rand(1..100)` per master key, the first minion of a marked key is removed through `death.remove_dead` with HP -10000; the key order is the first appearance in the creature list, DECISION: the exe walks a 17-bucket hash map keyed by the master's network id, exact for one master); a minion's death handler sets HP -10000 at once (`FUN_00510a70`), so no corpse
remains.

**Control Spirit / "Animate Dead" (22, `0x51a91f`).** Target = cell. Corpse stage `unit+0x13c` is derived from HP by the corpse
decay `FUN_005110b8` (run every 16 ticks per corpse, HP -1 per run, types 0x21..0x24 heroes stop at HP -60): `corpse_stage`
(HP < -10 -> 2, < -20 -> 3, < -40 -> 4, < -600 -> 5 removed). The spell searches the corpse list for a stage-2 corpse on exactly the
target cell (`FUN_0054fa73`, cell index equality), then stage 3, then 4; types `unit_type` 0x52..0x62 (zombies, skeletons) are skipped.
The corpse is consumed (stage 5, HP -10001, at once: a failed placement leaves it consumed). The new unit (`+0x1a0 = 1`, master 0, owner = caster's player, permanent,
level-independent) is placed by `FUN_00510089(corpse cell, 0)` with a stand and **`FUN_00570f2b(group)` (`0x51b1a2`) = cancel + stand ground `FUN_00570b8b`: group order 3, member order `0xc`** (the earlier "brain mode 3" is the group order byte too); it appears on that cell with copied stats (`raise_dead`): stage 2 `F_Zombie.1` (body, mind, spirit, max HP copied,
reaction/2+1), stage 3 `F_Skeleton.1` (body and reaction /2+1, max HP/2), stage 4 `Ghost` (reaction/2+1, max HP/2); attack skill `+0xa6`
and defence `+0xbe` copied; HP = max HP. Whether the template recompute (vtable `+0x58`) overrides the copy: INFERRED not. Engine: `spells.raise_release` (the copies replace the template columns `body`, `reaction`, `mind`, `spirit`, `hp_max`, `to_hit`, `defence` of the new unit; the corpse's attack skill and defence are read from its combat stats, i.e. the halved defence of a dying body).

**Spell level of a hero (cast side).** The client overview (`FUN_00416615` loop over 24 spells, order `SPELLS_TXT_ORDER`) computes per party
member `L = clamp(skill[sphere] + mind - 30, 0, 255)` from view bytes `+0x156+sphere` and `+0x145`, scales a wrapper copy (`FUN_0051951d`)
and sums / min-maxes the party. Same formula as the server (`level_of`).

**Spellbook tooltip (`FUN_004c628f`).** Shown for the spell under the cursor when the party knows it. Text: `spells.txt` line `k` (title
and description, `#` = line break) for spell `SPELLS_TXT_ORDER[k]` (table `0x5f8124`), then rows built from `main.txt` labels, each shown
as `x` or the party range `x...y`: Mana cost (117), Damage (118, sum over the party), Range (123), Duration (124, ticks/16 s, `%5.1f`),
Speed (182), Resistance (183, protection `L/2`), Sight (184), Maximum Damage Probability (185, Bless value), rays (186, Prismatic Spray
`min(7, L/20+2)`), Minimum Damage Probability (187, Curse value), Absorption (217, Shield `L/10+3`). Row-to-array pairing: CONFIRMED, §9e.4 (Speed = Haste, Sight = Darkness / Light, which have no slot).
Display names come from `spell.txt`, descriptions only for these 24 spells (no entry for 9, 14, 15, 28, 29).

## 10. VERIFY IN GAME

- Fire Arrow damage and flight time against §6/§5 (staff level 1 and a scroll `:50`: 5..10 vs 13..26; rounding of `m`).
- That the player UI refuses or walks to out-of-range targets (server has no check, §3); Blizzard / Acid Stream stone and cone visuals against §9b.

## 9e. The spell panel: slots, enable masks, hotkeys, tooltip (REA of the GOG exe, phase J data side)

Code: `engine/ui/spellbook.py` (slots, masks, tooltip fields), `engine/ui/orders.py` (`OrderInput.fkey`, `select_slot`, `C`). Tests: `tests/test_engine_spellbook.py`.

### 9e.1 Slots and the enable masks

| Fact | Where | Tag |
|---|---|---|
| The panel has **24 slots** (12 columns x 2 rows of 38 px, hit test `FUN_004c6fe0`: `x / 38 + (y / 38) * 12`, `y < 75`, `x <= 0x1c7`). Slot -> spell number = the byte-dword table `0x5f8124` = `SPELLS_TXT_ORDER` (1 2 3 4 24 20 21 26 13 12 11 10 5 6 7 8 25 22 23 27 19 18 17 16); spells 9, 14, 15, 28, 29 have no slot. The command's `button` is `slot + 1` (server table `0x5f8120`) | `0x4c6fe0`, `0x4c7532`, `0x4f515d` | CONFIRMED |
| `view+0x148` (`FUN_004167c2`, run at every selection change) = **OR of `obj+0x18` over the selected objects** (`FUN_0041eb40 != 0`); `obj+0x18` is a **slot-bit mask**. `obj+0x1c` is the spell-number mask (bit n = spell n) sent by the server (update flag `0x100000`, `0x40fd47`); the client update `0x41035d`-`0x4103f2` sets `obj+0x18 = 0` and, **only for the local player's own objects** (`obj+0x14 == client+0x9cc`) with `+0x1c != 0`, ORs `0x5f8e98[n]` (slot bit of spell n, 0 for 0, 9, 14, 15) for every bit n of `+0x1c`. The server mask is `FUN_0051c4a4` of the spell set `unit+0x140`: bit n for every non-empty entry n = 1..count-1 (`0x4ea04b`, `0x502899`, `0x531d23`, `0x532e43`); dirtied by `0x51e0b5` when a spell is learned. **No mana, level or cost enters any mask**: a spell with a button whose mana is short stays enabled and the cast starts and retries silently (§9c.2) | `0x4167c2`, `0x40fd47`, `0x4103b7`, `0x51c4a4`, `0x51e0b5` | CONFIRMED |
| `view+0x150` (items): for each backpack item of class `0xe` (scroll; `FUN_0041e9e0 == 0xe`) whose `FUN_0041eb20` (the item's spell number) is non-zero: `+0x150 |= 0x5f8e98[n]` (and `obj+0x20`). Command `0x25`. The engine has no scroll cast: not modelled | `0x4173c6`, `0x4c70fe` | CONFIRMED, not built |
| `view+0x14c` |= `0x5f8e98[obj+0x118]` (the unit's auto-cast spell byte, set by Ctrl+A: `0x4c74b1` -> `FUN_0041a727(spell)` -> command `0x46` sub 4 for the selected objects that have the spell; the unit then casts by itself, what the server does with it: open) | `0x4167c2`, `0x41a727` | CONFIRMED set; use open |
| Button 5 (`C`) is enabled by `FUN_0041757b`: 0 for a foreign selection (`view+0x144 & 4`), else `0xef | (0x10 if +0x148 or +0x150)`. The engine: `OrderInput.key("c")` needs a non-empty mask | `0x41757b` | CONFIRMED |
| The spellbook click (`FUN_004c7580`): the slot under the cursor becomes the panel's selection **only if its bit is in `+0x148 | +0x150`** | `0x4c75a9`-`0x4c75da` | CONFIRMED |

### 9e.2 The selection state the window must keep and the F4-F12 shortcuts

| Fact | Where | Tag |
|---|---|---|
| The spell panel object (client `+0xec`, handler `FUN_004c72f5`) holds the **selected slot `+0x60`** (-1 none; message `0x411` resets it) and the item panel's `+0x64` / `+0x68` (`FUN_004c7143` stores the selected backpack entry, `+0x64 = FUN_0041eb20 - 1`). `FUN_0041f370` = `+0x64` if >= 0, else `+0x60`: **the selected button index**; the cast branch of the cursor chooser and the click both use `selected + 1` as `button`. A click on a unit with cursor cast and a selection < 0 does nothing (`0x417856`) | `0x41f370`, `0x41784a`-`0x4178af` | CONFIRMED |
| Client hotkey table `client+0x4dc`: 9 entries of 12 bytes for F4..F12 (vk `0x73`..`0x7b`), `word +0` = type (0 none, 1 spell slot, 2 item), `word +2` = slot; initial type 0 (`FUN_00493b10` clears); saved with the settings (`0x48c3f9`, `0x48e6b0`: persistence INFERRED) | `0x40ca16`, `0x41dd5e`, `0x493b10` | CONFIRMED |
| **F`n`** (`0x40ca16`, active in game state 1 with the map, no text focus; no selection needed): `E = table[n-4]`. (a) `E.type != 2 or Ctrl`, and no Shift: message `0x417(index, Ctrl)` to the spell panel: with Ctrl the **selected slot** (`+0x60`; if -1 the slot under the mouse) is bound (`type 1`, slot) and every other entry holding the same slot is cleared (`FUN_0041de8f` compare, `FUN_00493b10` clear); without Ctrl and `E.type == 1`: `+0x60 := E.slot`. (b) the item panel gets the mirror message (type 2, Shift). (c) If `E.type == 1` and the **spellbook is closed**: `FUN_004c70b9(E.slot)` (spell mask) -> `FUN_00418a02(9)`; else `FUN_004c70fe(E.slot)` (item mask) -> `FUN_00418a02(10)`. With the book open nothing is armed. `FUN_00418a02(9/10)`: mode := 5 (the `C` mode), highlight button 5, **the spellbook is not opened** (the switch only opens it for button 5); `10` skips the mask-bit test. The Ctrl bind step (a) also runs (c) | `0x40ca16`-`0x40cb62`, `0x4c72f5`, `0x418a02` | CONFIRMED |
| So with the book closed F`n` selects the bound slot and arms the cast cursor; the next click on a unit sends `0x1e` with `button = slot + 1` if the selection's `+0x148` has the bit, else nothing. `C` (btn 5) arms mode 5 **and opens the book**, where the slot must be chosen by a click (or the `+0x60` selection of an earlier F`n`) before a click casts | `0x418b91`, `0x4195fa` | CONFIRMED |
| Engine: `OrderInput.slot` (+0x60), `hotkeys` (type 1 entries), `fkey(n, ctrl, shift)`, `select_slot` (the window's click); the F-key table is not saved. `C` casts the selected slot, else (no window) `castable_spell` (the lowest enabled prototype spell, DECISION). The debug overlays F4 / F5 moved to Shift+F4 / Shift+F5 | | DECISION |

### 9e.3 Stop and other orders during a cast (CONFIRMED)

`FUN_0056dbc6` (the `T` key's per-unit routine is `FUN_0056d52b` via `FUN_00570b8b`) = `FUN_0056d969` (facing, reservation, `brain+0x14`, `brain+0x60 := 0`, `mover+0x7c := 0`, unit state `+0x54 := 0`) + `FUN_0056dba1` (cancel + `FUN_0056d52b`: unit order `+0x50 := 0xc`, anchor = own cell, Brain mode `+8 := 0`) + `brain+0x50 := 1`. **None of them writes the Brain low-level order `brain+9` (2 = cast in progress), its counter `+0x15`, the cast target `unit+0x5c` or the wrapper `unit+0x64`.** The creature tick `FUN_0050f12c` calls the Brain `FUN_0056dca2` (`0x50f357`) *before* the state switch, and Brain order 2 sets state `0xd` / `0xe` again, so the phase machine runs on: the cast **completes** (effect at phase 5, recovery), mana already spent, at the original target; the new order's mode (cast: brain `+0x28` / `+0x30` stored by `FUN_0056d3e6`, the next mode 8) takes effect after the Brain returns to order 0. This is what the engine did; now pinned by `test_no_new_order_interrupts_a_cast_in_progress` (move, stop, guard, stand still, attack, a second cast).

### 9e.4 Tooltip arrays (CONFIRMED; the Speed / Sight pairing)

The view builds the arrays per slot (`FUN_004167c2`, stride 4 bytes, index = slot; `min` starts at 0xffff, `max` at 0 or -65535) from a wrapper made by `FUN_0051906d(spell)` and scaled by `FUN_0051951d(skill, mind)` with `skill = obj+0x156+sphere`, `mind = obj+0x145` (bytes). **The wrapper level is the byte `skill + mind - 30` with wrap-around and no clamp** (an 8-bit add: `5 + 10 - 30` gives 241); the helpers get the clamped level `0..255`. For each selected own object with `obj+0x24` in {0x17, 0x18} (what those are: open) and a non-empty `+0x18`, for every set slot bit:

| Array (min / max) | Value | Tooltip row (`main.txt` line) | Format (`0x5f6414`..) |
|---|---|---|---|
| `+0x2d4` (also `+0x334`) | wrapper `+0xc` (s16 mana cost), last unit wins; `>= 0xffff` = no tooltip | Mana cost (117 = 0x75), prefixed by the `spells.txt` line of the slot (`FUN_00474733(slot)`) | `%s#%s: %d` |
| `+0x154` / `+0x1b4` | **sum** over the units of `min'` (`+0xe`) / `min' + spread'` (`+0xf`) | Damage (118), if `+0x1b4 != 0` | `#%s: %d` or `#%s: %d-%d` |
| `+0x214` / `+0x274` | min / max of `+9` (range) | Range (123 = 0x7b), if max != 0 | `%d` / `%d-%d` |
| `+0x394` / `+0x3f4` | min / max of `+0x10` (u16 ticks); the slot of spell 18 (Stone Curse) zeroes the min after every unit | Duration (124 = 0x7c), if max != 0, ticks / 16 | `#%s: %5.1f` / `#%s: %5.1f -%5.1f` |
| `+0x454` / `+0x4b4` | `FUN_00519966`: spell **21 Haste** `L/15 + 1` | **Speed (182 = 0xb6)**, if max > -65535 | `%d` / `%d...%d` |
| `+0x514` / `+0x574` | `FUN_0051989f`: spells 4, 8, 13, 19 (the protections) `L/2` | Resistance (183 = 0xb7), if max != 0 | `+%d` / `+%d...+%d` |
| `+0x5d4` / `+0x634` | `FUN_00519922`: spells 15 Light and 14 Darkness `-1 - L/30` | **Sight (184 = 0xb8)**, if max > -65535 | `%d` / `%d...%d` |
| `+0x694` / `+0x6f4` | `FUN_00519837`: spell 20 Bless `L*4/5 + 20` | Maximum Damage Probability (185 = 0xb9) | `+%d%%` / `+%d...+%d%%` |
| `+0x754` / `+0x7b4` | `FUN_0051986b`: spell 28 Curse `L*4/5 + 20` | Minimum Damage Probability (187 = 0xbb) | same |
| `+0x814` / `+0x874` | `FUN_005197e3`: spell 11 Prismatic Spray `min(7, L/20 + 2)` | rays (186 = 0xba) | `%d` / `%d-%d` |
| `+0x8d4` / `+0x934` | `FUN_005198f1`: spell 27 Shield `L/10 + 3` | Absorption (217 = 0xd9) | `%d` / `%d-%d` |

The final string is `title+mana, damage, range, duration, helper row` concatenated (`%s%s%s%s%s`); the helper rows share one string, so only one is shown (they are mutually exclusive). The tooltip is built only when the hovered slot's bit is in `+0x148` and the game mode is 1 or has bit 2. Speed is therefore **Haste** and Sight **Light / Darkness** (neither has a slot, so the Sight row and the Curse row can never show in the spellbook; they are dead code for a player). `engine.ui.spellbook.spellbook(world, ids, lines)` lists the entries (`SpellEntry` fields `damage`, `range`, `duration`, `speed`, `resistance`, `sight`, `max_probability`, `min_probability`, `rays`, `absorption`, `mana_cost`, `name`, `text`, `description`) and `tooltip(entry, labels)` renders the exe's string; the descriptions are `spells.txt` line `slot`.

## 11. Open questions

- Book wrapper scaling: whether `FUN_00519483` rewrites the spellbook wrapper's `+9` in place (the AI reads `+9` as a range, [ai §12](../engine/ai.md#open-questions)).
- Tooltip filter: the client object type `obj+0x24` must be 0x17 or 0x18 (`FUN_004167c2`) for a unit to contribute (what those types are; the engine counts every own selected unit).
- Auto-cast spell (Ctrl+A, `FUN_0041a727`, command `0x46` sub 4, client `obj+0x118`): what the server does with it; the `0x411` senders (`0x483537`, `0x580d18`) that reset the panel selection `+0x60`; whether the F-key table is saved (`0x48c3f9`, `0x48e6b0`) and how the item mask `+0x150` / scroll casts (`0x25`) look in the UI.
