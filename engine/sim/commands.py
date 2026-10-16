"""Commands: the only way input reaches the simulation."""

from collections import deque


class Command:
    """Base class; concrete commands come with the systems that run them."""


class CommandQueue:
    def __init__(self):
        self._q = deque()

    def put(self, cmd):
        self._q.append(cmd)

    def drain(self):
        out = list(self._q)
        self._q.clear()
        return out

    def __len__(self):
        return len(self._q)
