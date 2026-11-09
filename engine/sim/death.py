"""Death: the dying countdown, the removal at state 0x10, loot and the corpse list.

Spec: docs/engine/combat.md section 12 (C§12.x in the comments); routines `FUN_0050f12c` (HP <= 0 branch), `FUN_00510a70` (removal and loot),
`FUN_0052b459` (creature loop tail), `FUN_005110b8` (corpse decay).  Layer 4: reads and writes `engine.world` only.
"""

from dataclasses import replace

from allods2.formats import progression as prog
from allods2.formats.itemgen import loot_item
from engine.world import DEAD, HeroDied, Item, Killed, Loot, Removed, death_stage

from . import sounds, xp
from .combat import combat_stats, log
from .combatstats import equipment_bag, equipment_codes
from . import gear

HUMAN_DYING_DEFAULT = 8         # `FUN_00512526`: a human without dying time (-1) uses 8
HERO_DEATH_HP = -50             # `FUN_00510a70` step 7: the main hero's HP after its items dropped
HERO_FLOOR = -61                # corpses of hero types stop decaying here (`FUN_005110b8`)
STAGE5_HP = -10001              # a corpse that reached death stage 5 is set here (stops the decay)


def dying_time(u):
    """`vtable +0x74` before the `-1`: data.bin `dying_time` (monsters p33, humans p23; a human's -1 means 8)."""
    st = u.stats
    d = st.get("dying_time", -1) if st is not None else -1
    if u.human and d < 0:
        return HUMAN_DYING_DEFAULT
    return max(d, 0) if st is not None else HUMAN_DYING_DEFAULT


def _signed8(v):
    v &= 0xFF
    return v - 256 if v & 0x80 else v


def _deselect_if_bones(world, u):
    """The client drops a unit from the selection when its death stage reaches 2 (HP <= -11, `0x4108dd`, C§12.2); stage 1 (HP -10..0) stays selected."""
    if death_stage(u.hp) >= 2:
        for p in world.players.values():
            if u.id in p.selection:
                p.selection = tuple(i for i in p.selection if i != u.id)


def dying_tick(world, u):
    """The HP <= 0 branch of the creature tick (C§12.1).  Orders and state are cleared every tick; the first time (`T0`) the pending spell is
    cancelled (none exist yet), the defence is halved, the timer takes `dying_time - 1`; the unit leaves the selections only at death stage >= 2 (HP <= -11; `_deselect_if_bones`); afterwards the
    timer counts down and the unit is removed once it ran out **and** HP < -9 (a flyer or ghost gets HP -1000 first; a ground unit at
    HP -9..0 waits for more hits or the HP drain).  Returns True when the state became 0x10 this tick (the caller removes the unit)."""
    u.order = 0
    u.state = 0
    if not u.death_seen:
        u.death_seen = True
        u.death_tick = world.tick
        sounds.death(world, u)                  # the death animation starts: the [dead] sound (`0x4106be`; audio.md 2.1)
        st = combat_stats(world, u)
        u.combat = replace(st, block=st.block.copy())
        u.combat.block.defence = int(u.combat.block.defence / 2)        # signed truncating halving
        u.timer = (dying_time(u) - 1) & 0xFF
        u.action, u.action_start_tick = "dying", world.tick
        _deselect_if_bones(world, u)
        return False
    _deselect_if_bones(world, u)
    if _signed8(u.timer) < 1:
        if u.move_type > 1:
            u.hp = -1000
        if u.hp < -9:
            u.state = u.order = DEAD
            return True
    else:
        u.timer = (u.timer - 1) & 0xFF
    return False


def remove_dead(world, u):
    """State 0x10 reached (C§12.3): loot and hero rules, one corpse decay step, the release (`World.bury`), the kill credit (C§12.7)."""
    drop_loot(world, u)
    hero_event = None
    pl = world.players.get(u.owner)
    if pl is not None:
        main = pl.main_hero == u.id
        if main:                                # step 7: owner+0x38 == the unit: deaths counter, HP := -50
            pl.hero_deaths += 1
            u.hp = HERO_DEATH_HP
        if pl.human and u.human and u.stats is not None and prog.is_hero_name(u.stats.name):     # step 8: hero types 0x21..0x3f, the human owner
            sid = (u.server_id // 10) % 1000 if u.server_id > 10000 else u.server_id       # +0x14c is the reduced id (units.md): Start_MF 10210 -> 21
            pl.death_code = (sid - 0x13) & 0xFF
            pl.defeat_dialog = True             # client message 0xb4 -> window message 0x433/0xff -> 0x431 (C§12.4)
            hero_event = HeroDied(world.tick, u.id, pl.death_code, main)
    decay_step(world, u)
    world.bury(u.id)
    if u.hp <= STAGE5_HP:                       # the decay step above already took it to stage 5: the id is freed
        world.corpses.pop(u.id, None)
        world.net_ids.free(u.net_id)
    log(world, Removed(world.tick, u.id))
    if hero_event is not None:
        log(world, hero_event)
    killer = world.units.get(u.last_attacker)
    if killer is not None and killer.hp >= 0 and xp.is_hero(killer):     # `0x52b709`: the killer is a hero type (+0xe 0x21..0x3f), `FUN_00542770` clear
        log(world, Killed(world.tick, u.id, u.server_id, bool(u.human), killer.id, killer.owner))
    xp.kill_credit(world, u)


def drop_loot(world, u):
    """`FUN_00510a70` steps 1-5 and the drop (C§12.4): the bag is the carried group (section 8, loaded into the pack) plus the template equipment
    (`combatstats.equipment_codes`: shield, the weapon when its class parameter 15 is non-zero, a human's armour slots); a summoned unit or a
    template named `NPC` empties it; monsters roll gold, then one item.
    Draws in the exe's order: `rnd(100)`, `rnd(spread)` (on a hit), `rnd(100)`, the generator, `rnd(len - 1)`."""
    st = u.stats
    summoned = bool(u.behaviour & 8)
    table = world.item_table
    if summoned or (st is not None and "NPC" in st.name):
        codes, mods = [], []
    elif u.human and u.equipment and table is not None:
        codes, mods = gear.bag(world, u)                # a loadout: the pack, then the second hand, the weapon and the armour as they are
        codes, mods = list(codes), list(mods) or [()] * len(codes)
    else:
        codes = list(u.carried)
        mods = [tuple(u.carried_mods[i]) if i < len(u.carried_mods) else () for i in range(len(codes))]
        for code, effects in equipment_bag(st, table):  # the template's strings keep their `{castSpell=..}` terms
            codes.append(code)
            mods.append(gear.mods_of(effects))
    if not u.human and not summoned and st is not None:
        rng = world.rng
        gold = 0
        if rng.rand(100) < st.get("gold_chance", 0):
            gold = st.get("gold_base", 0) + rng.rand(st.get("gold_spread", 0))
        if rng.rand(100) < st.get("item_chance", 0) and table is not None:
            it = loot_item(table, st.get("item_value_min", 0), st.get("item_value_max", 0), st.get("item_flags", 0), rng)
            if it is not None:
                codes.append(it.code & 0xFFFF)
                mods.append(gear.mods_of(it.effects))
    else:
        gold = 0
    if not codes and not gold:
        return
    if world.place_pile(u.x, u.y, gold, codes, mods=tuple(mods) if any(mods) else ()) is None:     # `FUN_005538c7` failed: the pile with its gold and items is deleted (rolls are spent)
        return
    log(world, Loot(world.tick, u.id, u.x, u.y, gold, tuple(codes)))


# --- corpses (C§12.6) ----------------------------------------------------------------------------

def decay_step(world, u):
    """`FUN_005110b8` for one body: on an even block HP falls by 1 (every 32 ticks) down to -10000; hero types stop at -61; at death stage 5
    the HP is set to -10001 and the id is freed (the corpse leaves `World.corpses`)."""
    if u.hp > STAGE5_HP and (world.tick >> 4) % 2 == 0:
        if not (u.human and prog.is_hero_name(u.stats.name) and u.hp <= HERO_FLOOR):
            u.hp -= 1
    if u.hp < -600 and u.hp > STAGE5_HP:
        u.hp = STAGE5_HP
        world.corpses.pop(u.id, None)
        world.net_ids.free(u.net_id)            # `FUN_005110b8` 0x51121b: a ground unit (`+0x4a <= 1`) frees its id at death stage 5


def decay_corpses(world):
    for u in list(world.corpses.values()):
        decay_step(world, u)
