"""Fixed-step simulation."""

from .movement import movement_system
from .selection import selection_system


class Simulation:
    """`step(commands)` advances the world one tick: systems run in list
    order, each as `system(world, commands)`; then the tick counter grows.  Every command
    is appended to `log` as `(tick, command)`.  `systems=None` installs the selection and movement systems."""

    def __init__(self, world, systems=None):
        self.world = world
        self.systems = [selection_system, movement_system] if systems is None else list(systems)
        self.log = []

    @property
    def tick(self):
        return self.world.tick

    def step(self, commands=()):
        commands = list(commands)
        self.log.extend((self.world.tick, c) for c in commands)
        for system in self.systems:
            system(self.world, commands)
        self.world.tick += 1


def replay(sim, log, ticks):
    """Step `sim` for `ticks` ticks, feeding each tick the commands logged for it."""
    by_tick = {}
    for tick, cmd in log:
        by_tick.setdefault(tick, []).append(cmd)
    for _ in range(ticks):
        sim.step(by_tick.get(sim.world.tick, ()))
