"""Fixed-step simulation."""

from . import ai as ai_mod
from . import gear as gear_mod
from . import triggers as triggers_mod
from .movement import movement_system
from .orders import orders_system
from .selection import selection_system
from .spells import carrier_system
from .traps import transient_system
from .vitals import vitals_system


class Simulation:
    """`step(commands)` advances the world one tick: systems run in list
    order, each as `system(world, commands)`; then the tick counter grows.  Every command
    is appended to `log` as `(tick, command)`.  `systems=None` installs the vitals job (tick & 15 == 12), order, selection and movement systems;
    `ai=True` the squads' group pass, `triggers=True` (after `triggers.enable`, implies `ai`) the map script and the victory / defeat pass.

    Timing (CONFIRMED, docs/engine/simulation.md 1.1): `world.tick` is the exe's server counter `server+4` *before* its
    increment in `FUN_004f8521`; it starts at 0 on a new game (`FUN_004eb715`, `0x4eba47`).  A command handed to `step`
    is applied by that very step (the exe's loop-back delivers synchronously: no extra tick of latency), so the caller
    puts a command into the next step after it was issued."""

    def __init__(self, world, systems=None, ai=False, triggers=False):
        self.world = world
        if triggers:                            # the scenario script (sim/triggers.py) runs inside the AI's group pass
            if world.script is None:
                raise ValueError("triggers=True needs triggers.enable(world, map) first")
            ai = True
        self.systems = [vitals_system, orders_system, selection_system, transient_system, carrier_system, movement_system] if systems is None else list(systems)
        if ai:                                  # the monsters think at tick & 15 == 6, before the drain (docs/engine/ai.md 10)
            if not world.ai_on:
                ai_mod.enable(world)
            self.systems.insert(self.systems.index(orders_system) if orders_system in self.systems else 0, ai_mod.ai_system)
        if triggers:
            self.systems.append(triggers_mod.mission_system)   # FUN_004f8967 at the end of the step (docs/engine/triggers.md 6)
        self.log = []
        gear_mod.template_speeds(world)         # the humans' speed stat from their equipment strings (load penalty, speed modifiers)

    @property
    def tick(self):
        return self.world.tick

    @property
    def seed(self):
        """The game's RNG seed (`World.seed`): with the command log it reproduces a session exactly."""
        return self.world.seed

    @property
    def block(self):
        """The exe's 16-tick block counter `server+0` (`FUN_004f08c0` `0x4f0aa7`): +1 after the step whose counter after the
        increment is 15 mod 16, i.e. `(completed ticks + 1) // 16`."""
        return (self.world.tick + 1) >> 4

    def step(self, commands=()):
        commands = list(commands)
        self.log.extend((self.world.tick, c) for c in commands)
        for system in self.systems:
            system(self.world, commands)
        if self.world.ai_emitted:               # the AI's commands join the session log, tagged with the tick they were issued in
            self.log.extend((self.world.tick, c) for c in self.world.ai_emitted)
            self.world.ai_emitted.clear()
        self.world.tick += 1


def replay(sim, log, ticks):
    """Step `sim` for `ticks` ticks, feeding each tick the commands logged for it."""
    by_tick = {}
    regen = sim.world.ai_on                     # the AI regenerates its commands: drop the logged ones (a sim without AI applies them)
    for tick, cmd in log:
        if regen and getattr(cmd, "ai", False):
            continue
        by_tick.setdefault(tick, []).append(cmd)
    for _ in range(ticks):
        sim.step(by_tick.get(sim.world.tick, ()))
