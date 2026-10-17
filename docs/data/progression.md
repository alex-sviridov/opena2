# Character progression

Code: `allods2/formats/progression.py` (`load(fs)`, `build(units, spells)`, `Progression.thresholds` / `.hero_templates`).
Engine: `AssetCache.progression()`; `World._load_units` gives every human `Unit` its `skills`, `xp`, `xp_total`, `best_school`
(no award logic yet). Export: `python -m allods2 data export progression out/data/progression.json` (gitignored `out/`;
the repo holds only the golden hash `tests/golden.json["progression"]`). Tests: `tests/test_progression.py`.
GOG 1.01, addresses are VAs (sha256 in [formats/README](../formats/README.md)). Tags as in CLAUDE.md. Formulas are
written as math. Related: [units](units.md), [spells](spells.md), [items](items.md), [unit-struct](../engine/unit-struct.md).

## 1. Model

There is **no single character level**. A human has six skill words `+0xa8..+0xb2`: index 0 *general*, 1-5 the five
schools. Schools 1-5 level individually from their own XP pool `+0x23c+4k`; `+0x130` is the sum of the pools; `+0x116+2k`
is the permanent copy of the skill (the live word `+0xa8+2k` is rebuilt from it plus the effect bonus `+0xe8+2k`).
`+0x23c` itself (k = 0) holds the best-school index. Skill 0 never levels (all loops run k = 1..5). CONFIRMED
(`FUN_00513497`, `FUN_005128cb`, `FUN_00514cf2`).

| k | name (weapon / spell school) | weapon class (item p5, `FUN_005290cc`) | spell sphere (p2) |
|--:|---|--:|--:|
| 0 | general | - | - |
| 1 | Blade / Fire | 1 | 1 fire |
| 2 | Axe / Water | 2 | 2 water |
| 3 | Bludgeon / Air | 3 | 3 air |
| 4 | Pike / Earth | 4 | 4 earth |
| 5 | Shooting / Astral | 5 | 5 astral |

## 2. Curve

```
thr[n] = trunc(1.1 ** n)             n = 0..149      (table 0x6a8998, built at start-up by FUN_00512824 from 0x480c8d)
threshold(n) = thr[min(n, 149)]      FUN_005128ac
level_of(xp) = max n with thr[n] <= xp   (client inverse FUN_00512870; at xp >= thr[149] it returns thr[149], not 149)
```

`thr` = XP accumulated in *that skill* for level n: 1 for n <= 7, 2 for 8..11, `thr[20]` = 6, `thr[100]` = 13 780,
`thr[149]` = 1 470 652. A level is capped at 100 for XP purposes (an award is ignored at skill >= 100). CONFIRMED.
Start pools: `pool[k] = thr[skill_k]`, `total = sum(pool)` (`FUN_00513497`, called after template load); a hero with
Blade 20 starts with 6 XP in Blade, 1 in each other school. CONFIRMED.

## 3. What a skill-up changes

A level-up (`FUN_005128cb`) does: `skill_k += 1` (permanent copy and live word), client notification (`FUN_005052d2` event 2, only
when the owning player's `+0x2c == 0`), the virtual **recompute** `vtable+0x58` = `FUN_0051366b`, and the stat-change message
`FUN_00502019(0xffb)` (flag `0x100 << (k-1)` | `0x3000c`). The recompute rebuilds **every derived stat** from attributes, `total`
(`+0x130`), skills and the effect/equipment bonus block `+0xd4..` (CONFIRMED `0x51366b`):

Attribute caps (`attr = min(attr, cap + bonus_byte)`, bonuses `+0xd4..+0xd7`); class from `+0x4c & 4` (mage = mana_max > 0:
CONFIRMED `0x514903` server, client loader `FUN_004a449c`) and unit type 0x22/0x24 (= female, `type = 0x21 + gender + 2*mage`):

| class | Body | Reaction | Mind | Spirit |
|---|--:|--:|--:|--:|
| fighter, male | 52 | 50 | 48 | 46 |
| fighter, female | 50 | 52 | 46 | 48 |
| mage, male | 48 | 46 | 52 | 50 |
| mage, female | 46 | 48 | 50 | 52 |

With `L(x) = log(x) / log(1.1)`, `G = L(total / 5000 + 1)` (total XP of all pools; at most 5 x 13 780 gives G ~ 28),
`mage` = 1 or 0 (all values are `ftol` truncated; Body/Spirit/Mind/Reaction are the capped values):

```
max HP     = ftol( ftol( Body * (mage ? 1 : 2) + (mage ? 1 : 2) * G ) * (1 + 1.1**Body / 100) ) + bonus_hp      (always: +0x96 is first overwritten with Body * k, the template healthMax is never used)
max mana   = ftol( ftol( 2*Spirit + (mage ? 2 : 1) * G ) * (1 + 1.1**Spirit / 100) ) + bonus_mana              (only if the stored max mana, i.e. the template manaMax, is non-zero, else mana = 0)
scan range = ftol( ((Mind + Reaction) / 25 + 4) * 256 ) + bonus      (+0xa4 in 1/256 cell; +0xa5 = whole cells)
speed      = Reaction                if Reaction < 12 else Reaction/5 + 12      (+10 for unit types 0x13, 0x15), - load penalty, min 6
load cap   = Body*10 + 1  (+0x92);  load = +0x8e + (the +0x7c object's field +0x20)/2, at most 32000 (INFERRED: weight);  if load >= cap: speed -= load / cap
damage     = ftol(1.1**Body / 20) (+0xb4 min, +0xb5 spread; bytes)
to-hit     = ftol((1.1**Body + 1.1**Reaction) / 5)        (+0xa6)
melee skill bonus (weapon school s = +0xb6 != 0):  to-hit += 3 * skill_s ;  damage_min += skill_s / 5
defence    = Reaction / 3 (+0xbe); protections (+0xc4..+0xcc) = min(Spirit/2, 100), cap Spirit/2 + 70; then the block of equipment/effects
```

So: **a school skill-up changes**: (1) the melee to-hit and minimum damage of a hero wielding that school's weapon (+3 to-hit,
+0.2 damage per skill point), (2) the level of every known spell of that sphere (`level = clamp(skill - 30 + Mind, 0, 255)`,
`FUN_00511913`/`FUN_00519483`; `FUN_0051c3e4` re-levels the whole spellbook after a skill-up, spell values then follow
[spells §6](spells.md#6-level-and-scaling)), (3) the summon tier of Summon Skeleton (`clamp(astral / 25 + 1, 1, 4)`, `0x51a6a1`), and
(4) through `total` a small logarithmic gain of max HP and mana (at most ~ +28 x class factor before the multiplier). Attributes do
**not** grow (no stat points); they change only through equipment/effects. **Weapon and armour equip tests read no skill**
([items §9](items.md#9-equipment-strings), `FUN_005290cc`). Max HP of a template human is therefore **derived**, not the data.bin
`healthMax` (see §6 for the consequence). All CONFIRMED (`0x51366b`, constants `0x5d0830..0x5d0890` read); the female type numbers
and the mapping of the four cap rows to attributes are read from the code (`0x5136a5..0x513719`).

## 4. XP sources

All awards end in **`FUN_005128cb`**, vtable slot `0x64` (the exe's slot map: `0x58` recompute, `0x64` award, `0x68` kill credit
`FUN_00512fcb`, `0x6c` damage credit `FUN_00513128`, `0x70` cast credit `FUN_005131ef`; correct the slot numbers of earlier notes).
Only a unit whose type word `+0xe` is 0x21..0x3f earns XP: the hero types `0x21 + gender + 2*mage`, which the server constructor writes for
`_Hero` templates (`0x514bbe`, flag from `0x561d4c`) and the client loader `FUN_004a449c` for reduced serverIDs 21-23 ([units p24](units.md)); ordinary
humans keep their units.reg typeID 1..24 (the data.bin `typeID`) and gain nothing. A victim with `+0x1a0 != 0` (summoned) gives nothing. CONFIRMED.

```
xp0  = trunc( xp_in * (Mind / 30 + 0.25) )                       # Mind-scaled, applied first (0x512915)
xp1  = xp0 * 10 / (n + 10)   (integer division), n = kills of the victim's type (high word of its entry in the list at +0x1a8)
award if there is no victim, or `FUN_00542770() != 0`, or the victim's owner differs from ours and is not allied (matrix bit 2)
school s = explicit argument (mage) or +0xb6 (fighter, when the argument is 0 and +0xb6 != 0); skipped at skill_s >= 100
if s != best_school and s != 5:  xp1 = (xp1 + 7) >> 3
xp   = min(xp1, thr[skill_s + 1] - thr[skill_s])                  # FUN_00512f44 (single player; a network session divides the span by 5)
pool[s] += xp ; total += xp
if thr[skill_s + 1] <= pool[s]:  skill_s += 1 ; recompute (§3)
```

Fighters (non-mage, `+0x4c & 4 == 0`) use the weapon school `+0xb6` (set on equip from the weapon's class p5 < 10, `FUN_005290cc`; 0 when
unarmed or with staves/class >= 10); **mages only earn XP when a spell supplies the school** (kills with a staff give none). Spells are
credited only if the caster is a mage. The repeat list holds 5 victim types (low word = victim `serverID`, high word = count); a kill of a
listed type increments its count after the award, an unlisted type is appended after dropping the oldest of 5 (`0x5130db..`).
**Quirk:** for a skill 0..6, `thr[s+1] - thr[s] = 0` so `xp = 0`, and `thr[s+1] <= pool[s]` already holds, so every award event raises
that skill by one until it is 7. INFERRED from the code shape (no template hero starts below 20).

Callers (the `xp_in` of each):

| Source | Code | `xp_in` | School |
|---|---|---|---|
| melee hit | `FUN_00516ceb` calls slot `0x6c` at `0x516e98` after the damage, only if the victim was alive (HP > 0) before the hit and has HP > -10 after it | `trunc( 0.5 * victim.xp * damage / victim.maxHP + 1 )` (`FUN_00513128`; `victim.xp` = `+0x1c`, [units p37](units.md)); only if the victim's owner has `+0x2c != 0` | weapon `+0xb6` |
| damage spell | spell effect `FUN_00519db8` calls slot `0x6c` at `0x51a4b3` with the final damage (after protection, capped at victim HP + 10) and the spell number | same formula | spell p2 |
| projectile / carrier / poison tick | `FUN_0051e65b` (`0x51e6ed`), `FUN_0051d175` for Poison Cloud (spell 6, `0x51d235`) | same formula | spell p2 |
| spell cast | `FUN_00519db8` calls slot `0x70` at `0x519f42` when a *unit* (not an item) casts | `trunc( 0.5 * mana_cost + 0.5 )` (`FUN_005131ef`, [spells p1](spells.md)) | spell p2 |
| kill credit | slot `0x68` `FUN_00512fcb(victim, spell)`, called at `0x52b74b` from the creature update loop `FUN_0052b459` when a victim's death completes (state `+0x54 == 0x10`) and its killer (`victim+0x40`) is a hero-type unit (0x21..0x3f) with HP >= 0 (`FUN_00542770` tests `+0x94 < 0`); `spell` = signed byte `victim+0x48` (spell of the killing blow, 0 = melee) | `trunc( 0.5 * victim.xp )`, passed through the same award (repeat-kill discount, off-school, cap) | spell p2 when `spell != 0` and the killer is a mage; 0 otherwise |

Per-damage credit and the `+1` mean XP accrues **continuously during a fight**, in proportion to the damage dealt; the **kill credit adds a
second `0.5 * victim.xp` when the victim dies** (so a victim killed in one blow of its max HP yields about `1.0 * xp` before the discounts, a long
fight the same sum). The kill credit is also the only place that updates the repeat-kill list (`+0x1a8`: it increments the high-word count of
the victim's type, or appends it; at 5 entries the oldest is dropped), and it is skipped entirely when `spell != 0` and the killer is not a mage.
A mage that kills with melee (`spell == 0`, school 0) gets no XP from the award (mages need an explicit school) but still updates the list.
The same death branch also bumps the owner's kill counters (`player+0xa48` monster kills, `+0xa4c` player kills) and, for a monster killed
by a human, runs killer slot `0x50` (`FUN_0051327b`, same function in both human vtables): its whole body is guarded by `[0x6044c4+0x74] != 0`, so it is a
no-op in single player (a network session notifies via `FUN_00516238`, out of scope). CONFIRMED (`0x52b709`-`0x52b84a`, `0x512fcb`). **`Player+0x2c` = computer-controlled** (server player object): set to 1 at creation and cleared to 0 only for record 1 when
`[0x6044c4+0x74] == 0` (single player, `0x5613d0`-`0x5613ec`). It gates the damage credit (`FUN_00513128`, `0x5131a3`: the **victim's** owner must
be computer-controlled, so hitting a human-owned unit earns no per-damage XP; the kill and cast credits do not test it) and the client level-up
notification (`FUN_005128cb`: sent only when the **killer's** owner is the human, `+0x2c == 0`). CONFIRMED.

**No quest or scenario XP exists.** The award slot `0x64` is
reached only from the three credit routines (`0x513046` kill, `0x5131e6` damage, `0x513272` cast; `FUN_005128cb` has no direct caller, and the
other `call [reg+0x64]` sites belong to view, network and MFC classes). `Scenario.dll` exports 18 functions, none touching a unit
(locations, shops, inns, `ScenarioGetVar`/`SetVar`, save/load) and imports only system DLLs, so it cannot award XP. The quest payout is an item
upgrade whose value is *derived from* the hero's XP total `+0x130` ([items §14](items.md#14-quests-and-the-item-upgrade-message-0x38)), never
an XP gain. CONFIRMED (call-site scan of the full disassembly, export/import tables). Other readers of the skills: the quest generator `FUN_005303ed` loops `best = max(skill_1..skill_5)` of the quest hero (`0x530577`,
CONFIRMED) and keeps as quest targets the candidate units whose **strength** `S` satisfies `3*best - 50 < S < 3*best + 75` (`0x5307ac`, `0x530cf9`,
`0x530fc8`, `0x531524`, `0x531800`; role as target selection for the kill/hunt quests INFERRED). `S` = `FUN_00510a26(unit)` = `defence (+0xbe)`
`+ 25` if MovementType (`+0x4a`) is 3 `+ 50` if max mana (`+0x9c`) is non-zero (CONFIRMED). The payout `FUN_005325ee` counts the schools with skill
> 75 (`0x533768`); with at least four of them and a reward value `v >= 1 000 000` (or `FUN_0053dd90`) it upgrades the equipped items
([items §11](items.md#11-random-generation)). The notes "needs 4 and gold < 1 000 000" and "four of the five hero attributes" in earlier drafts were wrong:
these are the five **school skills** and the reward value. `FUN_00514f59(school, level)` builds a level-L hero (school skill L, Shooting L/2, a school staff or weapon) for
`0x491d0c`/`0x4f2b04` (hero creation in the UI): not on the campaign path.

## 5. Skill table

| Skill | Name | Affects | Use sites |
|--:|---|---|---|
| 0 | general | no level-up. Copied to the to-hit bonus `+0xe6` for non-melee weapon classes (`0x529200`); effect kinds 26/32 add to it; a scan of every word read at `+0xa8` in the creature code (`0x5114f3`-`0x5325ee`) found no other reader; template heroes have 0 (INFERRED: vestigial for humans, it is the monsters' to-hit copy) | `0x529200` |
| 1 | Blade / Fire | melee to-hit +3, damage_min +1/5 per point with a blade (p5 = 1); level of Fire spells (`skill - 30 + Mind`) | `0x513dc0`, `0x513df0`, `0x511927`, `0x5194a7`, `0x519e69` |
| 2 | Axe / Water | same with axes (2); Water spells | same |
| 3 | Bludgeon / Air | same with bludgeons (3); Air spells | same |
| 4 | Pike / Earth | same with pikes (4); Earth spells | same |
| 5 | Shooting / Astral | same with missile weapons (5); Astral spells and the Summon Skeleton tier (`astral / 25 + 1`, 1..4) | `0x51a6a1`, same |

The school skills are also read by the AI/encounter code (`0x530577`, `0x533768`) and written by the hero save/load path (`0x4eab4a`:
the client rebuilds each skill as `level_of(pool)` from the pools sent by the server). Live word = `min(permanent, 100) + bonus`
(the cap applies before the bonus), bonus kinds 26-31 (fighter) / 32-37 (mage) share `+0xe8..+0xf2`.

## 6. Hero start

**Source: the data.bin human record only.** A section 6 unit with `flags & 0x10` resolves to a human by `serverID` (server
`FUN_00561bf9`: `FUN_004fd5ad` -> `FUN_004a65b0` -> constructor `FUN_005143e4` -> `FUN_005145d1`), no other file contributes. CONFIRMED
sequence in `FUN_005145d1`: template params (attributes, `healthMax`, `manaMax`, speed, scan range, defence, the six skills p10-15)
through `FUN_00514cf2` (a -1 keeps the constructor value, skills 0); `mana_max > 0` sets `+0x4c |= 6` (mage) and builds the
spellbook `+0x140` from the known-spells bit mask (p25; bit n = spell n, n = 1..29; `FUN_0051906d` + `FUN_0051c29e`; no spellbook
otherwise); the 10 equipment strings through vtable `+0x44` (slot 0 weapon `FUN_00528808`, 1 shield-class `FUN_00527e23`, 2-9
armour `FUN_005273f0`); `FUN_00513497` start pools; recompute `vtable+0x58`; HP and mana set to the new maxima. Back in `FUN_00561bf9`
the map's `max_hp`/`hp` override HP (`0x562013`; any human, record flag `0x10`, with `hp == max_hp` is reset to *default*, i.e. keeps the derived maximum) and the recompute is not repeated.
Order in `FUN_00561bf9` (CONFIRMED `0x561e20`-`0x562099`): create, difficulty tweak, behaviour bits, **recompute** (`0x562010`), map HP override.
`FUN_00514cf2` sets the best school `+0x23c` = first strictly highest school skill when the template name contains `_Hero` or `Start_`
(case-sensitive substring; 0 when all schools are 0); the server constructor flag `_Hero` additionally fixes the type to
`0x21 + gender (+2 mage)`. Map section 6 carries no skills, XP or spells: a map hero is exactly its template at skill 20-25.

Templates (6 records; pools `thr[skill]`):

| Name | serverID | Body/React/Mind/Spirit | template HP / mana | Skills (g,1-5) | Best | Spells | Weapon / armour |
|---|--:|---|---|---|--:|---|---|
| Start_MF | 10210 | 40/36/25/17 | 50 / - | 0,20,0,0,0,0 | 1 | - | Iron Long Sword, plate set |
| Start_FF | 10211 | 37/39/21/25 | 20 / - | same | 1 | - | same |
| Start_MM | 10212 | 28/20/41/32 | 30 / 70 | same | 1 | Heal, Shield | Wood Staff {castSpell=Fire_Arrow:1}, robe |
| Start_FM | 10213 | 19/23/30/42 | 30 / 70 | same | 1 | Heal, Shield | same |
| Fighter_Hero | 10220 | 41/39/25/21 | 50 / - | 0,25,0,0,0,10 | 1 | - | Uncommon Steel Two Handed Sword, steel set |
| Mage_Hero | 10230 | 14/33/35/44 | 30 / 70 | 0,25,0,0,0,10 | 1 | Fire Arrow, Prot. from Fire, Bless, Haste, Heal, Shield | none, Uncommon None Shoes, None Dress |

(Pools: Start_* `[6,1,1,1,1]` total 10; Fighter/Mage_Hero `[10,1,1,1,2]` total 15.) The `Start_*` skill rows are the first and only
non-default skill; the other schools are 0. Only map `scenario/40.alm` places a `_Hero` template (a `Mage_Hero`, HP 5 of the derived 14); `Start_*`
appear in no campaign map (INFERRED: the new-game characters of the creation screens `0x490xxx`/`0x491xxx`, which use the named constructor).

**Consequence for the engine (CONFIRMED, measured on the install; implemented):** every one of the 605 human units of the 46 campaign maps carries
`hp = max_hp = 0xFFFF` (default), so **all** of them take the derived maximum, none the template `healthMax` and none a map value. The recompute also
discards the difficulty tweak for humans (it rewrites max HP, to-hit `+0xa6` and defence `+0xbe` after it; only the brain `+0x44` halving of easy mode
survives). Examples (template -> exe; derived from the template attributes, start pools and the §3 formulas, equipment adds no HP/mana: no human
template has a `health`/`mana` modifier, only `spirit`, `speed`, `scanRange`, protections, defence, to-hit, castSpell):

| Unit | template HP / mana | exe HP / mana |
|---|--:|--:|
| Start_MF | 50 / - | 116 / - |
| Mage_Hero | 30 / 70 | 14 / 146 |
| 2U_PeasantMale | 75 / - | 55 / - |
| 2A_Knight4 | 351 / - | 167 / - |
| 2M_Knight4 | 137 / 390 | 58 / 267 |

`allods2.formats.progression.derived_vitals(template)` implements the formula and `World._load_units` uses it for every human (`Unit.hp_max`,
`Unit.mana_max`, `Unit.mana`; a map `hp` still sets the current HP, a map `max_hp` below the default sets the maximum). Not modelled yet: the equipment /
effect bonus block (`bonus_hp`/`bonus_mana`, no template has one), re-running the recompute after a skill-up, and the difficulty tweak.

Carry-over of hero state between maps: the maps hold nothing (§6 above), so it must live in the campaign save / `.a2c`: UNKNOWN (out of scope
until saves are read).

## 7. Tests

`tests/test_progression.py`: curve values (`thr[100] = 13780`, `thr[149] = 1470652`, monotone), `level_of`, best-school ties, start pools, `-1` skills, spell mask decode,
hero name rule, template build on synthetic units, export CLI and golden hash `["progression"]`, the six install templates, and the world state of
the hero on map 40 and of all humans/monsters (`Unit.skills/xp/xp_total/best_school`).

## Open questions

- Hero state between campaign maps (saves, `.a2c`). Start: `FUN_00514920`.
