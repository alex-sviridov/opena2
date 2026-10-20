"""Experience and level-ups of heroes: the per-hit credit, the kill credit and the award chain.

Spec: docs/data/progression.md sections 3-4 and docs/engine/combat.md 12.7; routines `FUN_00513128` (hit), `FUN_00512fcb` (kill),
`FUN_005128cb` (award, skill-up), `FUN_0051366b` (recompute).  Layer 4: reads and writes `engine.world` only.
"""

from allods2.formats import progression as prog
from engine.world import LevelUp

from .combat import combat_stats, log

MAX_SKILL = 100                 # an award is ignored at skill >= 100
KILL_LIST = 5                   # entries of the repeat-kill list (+0x1a8)
THR = prog._build_thresholds()


def is_hero(u):
    """A unit that earns XP: the hero types `0x21..0x3f` (the `_Hero` templates, progression.md section 4)."""
    return u.human and u.stats is not None and prog.is_hero_name(u.stats.name) and bool(u.skills)


def hostile(world, a, b):
    """The award test on the victim's owner: it differs from ours and is not allied (matrix bit 2)."""
    if a.owner == b.owner:
        return False
    p = world.players.get(a.owner)
    return not (p is not None and len(p.relations) >= b.owner and p.relations[b.owner - 1] & 2)


def _count(hero, victim):
    for sid, n in hero.kill_list:
        if sid == victim.server_id:
            return n
    return 0


def award(world, hero, xp_in, school, victim=None):
    """`FUN_005128cb`: Mind scaling, repeat-kill discount, off-school reduction, span cap, pool, skill-up.  `school` 0 means the weapon school
    of a fighter (`+0xb6`); a mage with no school earns nothing."""
    if not is_hero(hero) or (victim is not None and not hostile(world, hero, victim)):
        return
    if not hero.xp:
        hero.xp, hero.xp_total = prog.start_pools(hero.skills)
    mind = prog.attributes(hero.stats)[2]
    xp1 = int(xp_in * (mind / 30.0 + 0.25))
    n = _count(hero, victim) if victim is not None else 0
    xp1 = xp1 * 10 // (n + 10)
    st = combat_stats(world, hero)
    s = school or (0 if st.mage else st.record.kind)
    if not 1 <= s <= 5:
        return
    skill = hero.skills[s]
    if skill >= MAX_SKILL:
        return
    if s != hero.best_school and s != 5:
        xp1 = (xp1 + 7) >> 3
    gain = min(xp1, THR[skill + 1] - THR[skill])
    pools = list(hero.xp)
    pools[s - 1] += gain
    hero.xp = tuple(pools)
    hero.xp_total += gain
    if THR[skill + 1] <= pools[s - 1]:
        level_up(world, hero, s)


def level_up(world, hero, school):
    """Skill `school` + 1 and the recompute (progression.md section 3): max HP / mana from the new XP total, the combat numbers rebuilt on
    next use.  Current HP and mana are kept (clamped to the new maximum, INFERRED)."""
    sk = list(hero.skills)
    sk[school] += 1
    hero.skills = tuple(sk)
    hp_max, mana_max = prog.derived_vitals(hero.stats, hero.skills, total=hero.xp_total)
    hero.hp_max = hp_max
    hero.hp = min(hero.hp, hp_max)
    hero.mana_max = mana_max
    hero.mana = min(hero.mana, mana_max)
    hero.combat = None
    log(world, LevelUp(world.tick, hero.id, school, hero.skills[school]))


def damage_credit(world, attacker, victim, dmg, before, spell=0):
    """`FUN_00513128(victim, dmg, spell)` after a blow: `dmg > 0`, the victim had HP > 0 before and has HP > -10 now, and its owner is
    computer-controlled (every owner but the human player): `0.5 * victim.xp * dmg / victim.maxHP + 1` through the award.  `spell` != 0 (a
    spell's damage: the damage effect `FUN_0051e65b`, Drain Life, Poison pass the spell number): only a mage (`+0x4c & 4`) earns, into the
    spell's sphere (`0x513138`-`0x51317d`, docs/engine/effects.md); 0 = a weapon blow (the weapon school)."""
    if dmg <= 0 or before <= 0 or victim.hp <= -10 or victim.hp_max <= 0 or not is_hero(attacker):
        return
    school = 0
    if spell:
        from .combat import combat_stats
        if not combat_stats(world, attacker).mage or world.spell_table is None:
            return
        school = world.spell_table.get(spell).sphere
    if world.players[victim.owner].human or victim.stats is None:
        return
    award(world, attacker, int(0.5 * victim.stats.get("xp", 0) * dmg / victim.hp_max + 1), school, victim)


def kill_credit(world, victim):
    """`FUN_00512fcb` at the removal tick: `0.5 * victim.xp` to the last hitter if it is a living hero (HP >= 0), a summoned victim pays nothing;
    then the repeat-kill list is updated."""
    killer = world.units.get(victim.last_attacker)
    if killer is None or killer.hp < 0 or not is_hero(killer) or victim.behaviour & 8 or victim.stats is None:
        return
    award(world, killer, int(0.5 * victim.stats.get("xp", 0)), 0, victim)
    for e in killer.kill_list:
        if e[0] == victim.server_id:
            e[1] += 1
            return
    if len(killer.kill_list) >= KILL_LIST:
        killer.kill_list.pop(0)
    killer.kill_list.append([victim.server_id, 1])
