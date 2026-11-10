"""Load game: the screen exists in the graph, the button is disabled until the Save / load step (docs/engine/shell.md 6)."""

from .scene import Scene
from .screen import Screen


class LoadGame(Screen):
    name = "load"

    def event(self, ev):
        return None

    def update(self, dt_ms):
        return "menu"                              # unreachable while the menu keeps the button disabled; never a dead end

    def scene(self):
        return Scene([])
