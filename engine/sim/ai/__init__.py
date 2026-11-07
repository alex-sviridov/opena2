"""Monster AI package.  Layers, bottom up: `perception` (sight, pools) -> `targeting` (scores) -> `brain` (command executors) -> `casting` ->
`autocast` (the player's casters) -> `actions` (engage / idle) -> `reaction` (scans, hit reaction, flee) -> `groups` (squad passes).  Names are
re-exported here.

Monster AI: the squad group handler `FUN_005728fa` and what it calls (docs/engine/ai.md; routine addresses in the comments).

Layer 4: reads and writes `engine.world` only.  The AI thinks inside the group pass (`tick & 15 == 6`, before the command drain) and
acts through the commands the player uses, `MoveUnits` / `AttackUnit` / `Stop` with `ai=True` (the brain-level executors in `brain.py`), so every action lands in the same log (`Simulation.log`).  State: `Unit.ai` (Brain fields), `World.ai_groups` (squads).
"""

import math
import struct

from engine.world import DEAD, AiGroup, AiState

from .. import combat as cb
from .. import combatstats
from .. import effects
from .. import movement as mv
from .. import spells
from ..commands import AttackUnit, CastSpell, MoveUnits, Stop
from ..pathfinding import chebyshev, follow_distance, foot, unit_size

from .perception import (  # noqa: F401
    MARK_TURNS,
    NO_TARGET,
    SCAN_SHIFT,
    WANDER_DX,
    WANDER_DY,
    _COST,
    _PAR,
    _SIGHT_CACHE_LIMIT,
    _build_tables,
    _detected,
    _hostiles_on,
    _scan_range,
    _visible,
    at_war,
    centroid_stats,
    pos16,
    reach_gap,
    see_invisible,
    sight,
    unword,
    word,
)
from .targeting import (  # noqa: F401
    PREFERENCE,
    score,
    score_stand,
)
from .groups import (  # noqa: F401
    on_static_plan,
    DEFAULT_RADIUS,
    GROUP_ORDER,
    GUARD_ORDER,
    G_COMPUTER,
    G_EMPTY,
    G_GUARD,
    G_HOLD,
    G_MOVE,
    G_NONE,
    G_STAND,
    G_STILL,
    G_SWARM,
    G_WANDER,
    HIT_WINDOW,
    MIN_GUARD_RANGE,
    PASS_ORDERS,
    POOL_GROW,
    SLEEP_STATE,
    STAMP_FAR,
    STAMP_NEAR,
    WAKE_BLOCKS,
    WANDER_LIMIT,
    WANDER_NEAR,
    WANDER_STEP,
    _act,
    _assign_targets,
    _grow,
    _live,
    _on_post,
    _pool,
    _pool_all,
    _stand_squads,
    ai_system,
    asleep,
    enable,
    find_squad,
    group_order,
    guard_pass,
    handler,
    hold_pass,
    init_group,
    pool_driven,
    record_stats,
    run_group,
    set_group_order,
    stand_pass,
    swarm_pass,
    wake,
    wander_pass,
)
from .actions import caster_attack, engage, idle  # noqa: F401
from .casting import (  # noqa: F401
    CLEVER_MELEE,
    CLEVER_MIND,
    IDLE_MANA,
    OWN_SPELLS,
    SPECIAL_AHEAD,
    SPECIAL_CELL,
    SPECIAL_ENEMY,
    SPECIAL_SELF,
    _divide,
    _ratio,
    _wrapper_ok,
    allied,
    can_stand,
    cast_at,
    cast_cell,
    effect_active,
    friend_cast,
    is_mage,
    mage_idle,
    ring_cells,
    special_attack,
)
from .autocast import (  # noqa: F401
    AUTO_BUFF,
    AUTO_HEAL,
    AUTO_PROT,
    BUFF_PROTECTIONS,
    FRESH_TICKS,
    FRIEND_ALLY,
    FRIEND_NEUTRAL,
    FRIEND_OWN,
    SCAN_MANA,
    _members_of,
    castable,
    caster_lists,
    fresh,
    friend_of,
    human_attack,
    human_scan,
    in_cast_range,
    mode0,
    selected_cast,
)
from .reaction import (  # noqa: F401
    FLEE_CELLS,
    RUN_AWAY,
    WIMPY_RADIUS,
    WITHDRAW_RADIUS,
    _enemies,
    _set_war,
    auto_scan,
    away_cell,
    declare_war,
    enemies_around,
    flee_cell,
    guard_scan,
    on_hit,
    post_step,
    retreat_exec,
    spray_distance,
    spray_targets,
)
from .brain import (  # noqa: F401
    _human,
    apply,
    apply_cast,
    attack,
    emit,
    go,
    look_around,
    mode_name,
    overlay,
)

__all__ = ["enable", "ai_system", "on_hit", "apply", "AiState"]
