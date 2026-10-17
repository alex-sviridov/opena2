# Game data tables

Typed views of the game database for the engine. Facts are marked CONFIRMED / INFERRED / UNKNOWN as in
[formats](../formats/README.md).

| Table | Document | Status |
|---|---|---|
| Unit and monster stats (`data.bin` groups 5, 6) | [units.md](units.md) | CONFIRMED loaders and most fields; 464 types, all map units resolve |
| Item definitions (`data.bin` groups 1-4, `itemname.*`) | [items.md](items.md) | CONFIRMED class stats, quality/material scaling, price, modifiers; 162 definitions, 491 named items, all map codes resolve |
| Spell definitions (`data.bin` group 8, `spell.txt`, `spells.txt`) | [spells.md](spells.md) | CONFIRMED params 0-18, 20-21 (3, 10, 12, 13, 15, 19 unread), handler per spell number, level scaling, damage/protection formula, animation and sound ids; 29 spells; prototype spell Fire Arrow |
| Progression: XP curve, skills, hero templates (`data.bin` humans, exe formulas) | [progression.md](progression.md) | CONFIRMED curve, award formulas, recompute (what a skill-up changes), hero start; 6 hero templates; kill-credit callers and quest XP open |

Overview of all tables, cross-reference check and the handoff to movement and combat: [overview.md](overview.md).
