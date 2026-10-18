"""Death: the dying countdown, the removal at state 0x10, loot and the corpse list.

Spec: docs/engine/combat.md section 12 (C§12.x in the comments); routines `FUN_0050f12c` (HP <= 0 branch), `FUN_00510a70` (removal and loot),
`FUN_0052b459` (creature loop tail), `FUN_005110b8` (corpse decay).  Layer 4: reads and writes `engine.world` only.
"""

from dataclasses import replace

from allods2.formats import progression as prog
from allods2.formats.itemgen import loot_item
from engine.world import DEAD, Item, Loot, Removed

from . import xp
from .combat import combat_stats, log

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


def dying_tick(world, u):
    """The HP <= 0 branch of the creature tick (C§12.1).  Orders and state are cleared every tick; the first time (`T0`) the pending spell is
    cancelled (none exist yet), the defence is halved, the timer takes `dying_time - 1` and the unit leaves the selections; afterwards the
    timer counts down and the unit is removed once it ran out **and** HP < -9 (a flyer or ghost gets HP -1000 first; a ground unit at
    HP -9..0 waits for more hits or the HP drain).  Returns True when the state became 0x10 this tick (the caller removes the unit)."""
    u.order = 0
    u.state = 0
    if not u.death_seen:
        u.death_seen = True
        u.death_tick = world.tick
        st = combat_stats(world, u)
        u.combat = replace(st, block=st.block.copy())
        u.combat.block.defence = int(u.combat.block.defence / 2)        # signed truncating halving
        u.timer = (dying_time(u) - 1) & 0xFF
        u.action, u.action_start_tick = "dying", world.tick
        for p in world.players.values():
            if u.id in p.selection:
                p.selection = tuple(i for i in p.selection if i != u.id)
        return False
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
    if u.human and prog.is_hero_name(u.stats.name) and world.players[u.owner].human:
        u.hp = HERO_DEATH_HP                    # step 7 (the main hero); the death dialog message 0xb4 is the Removed event
    decay_step(world, u)
    world.bury(u.id)
    if u.hp <= STAGE5_HP:                       # the decay step above already took it to stage 5: the id is freed
        world.corpses.pop(u.id, None)
    log(world, Removed(world.tick, u.id))
    xp.kill_credit(world, u)


def drop_loot(world, u):
    """`FUN_00510a70` steps 4-5 and the drop (C§12.4): a summoned unit or a template named `NPC` empties its bag; monsters roll gold, then one item.
    Draws in the exe's order: `rnd(100)`, `rnd(spread)` (on a hit), `rnd(100)`, the generator, `rnd(len - 1)`."""
    st = u.stats
    summoned = bool(u.behaviour & 8)
    codes = [] if summoned or (st is not None and "NPC" in st.name) else list(u.carried)
    gold = 0
    if not u.human and not summoned and st is not None:
        rng = world.rng
        if rng.rand(100) < st.get("gold_chance", 0):
            gold = st.get("gold_base", 0) + rng.rand(st.get("gold_spread", 0))
        if rng.rand(100) < st.get("item_chance", 0) and world.item_table is not None:
            it = loot_item(world.item_table, st.get("item_value_min", 0), st.get("item_value_max", 0), st.get("item_flags", 0), rng)
            if it is not None:
                codes.append(it.code & 0xFFFF)
    if not codes and not gold:
        return
    pile = next((world.items[i] for i in sorted(world.items_at(u.x, u.y))), None)
    if pile is not None:                        # `FUN_0052ab07`: merge into the pile on the cell
        pile.gold += gold
        pile.codes += tuple(codes)
    else:
        world.add_item(Item(world.new_pile_id(), u.x, u.y, 128, 128, gold, tuple(codes)))
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


def decay_corpses(world):
    for u in list(world.corpses.values()):
        decay_step(world, u)
