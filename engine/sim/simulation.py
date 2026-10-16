"""Fixed-step simulation."""


class Simulation:
    """`step(commands)` advances the world one tick: systems run in list
    order, each as `system(world, commands)`; then the tick counter grows."""

    def __init__(self, world, systems=()):
        self.world = world
        self.systems = list(systems)

    @property
    def tick(self):
        return self.world.tick

    def step(self, commands=()):
        commands = list(commands)
        for system in self.systems:
            system(self.world, commands)
        self.world.tick += 1
