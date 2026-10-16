"""World state: the map cells and heights, the tick counter, entity ids.

Layer 3: knows nothing of view, ui or pygame.
"""

import numpy as np


class World:
    """`cells` (h, w) uint16 runtime tile values, `heights` (h, w) int8
    (one signed byte per vertex, 1 px each).  Entities are integer ids."""

    def __init__(self, cells, heights, name=""):
        self.cells = np.asarray(cells, np.uint16)
        self.heights = np.asarray(heights).astype(np.int8)
        if self.cells.shape != self.heights.shape:
            raise ValueError("cells and heights differ in shape")
        self.height, self.width = self.cells.shape
        self.name = name
        self.tick = 0
        self._next_id = 1
        self.entities = {}          # id -> data (empty in G1)

    @classmethod
    def from_map(cls, m):
        """From an `allods2.formats.Map`: cells as the game holds them after loading."""
        return cls(m.runtime_terrain(), m.heights_i8, m.name)

    def new_entity(self, data=None):
        eid = self._next_id
        self._next_id += 1
        self.entities[eid] = data
        return eid
