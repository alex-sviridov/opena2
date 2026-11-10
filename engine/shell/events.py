"""Input events of the shell: the backend turns pygame events into these (positions in screen pixels), tests script them."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Move:
    x: int
    y: int


@dataclass(frozen=True)
class Press:
    x: int
    y: int
    button: int = 1


@dataclass(frozen=True)
class Release:
    x: int
    y: int
    button: int = 1


@dataclass(frozen=True)
class Key:
    """`name`: 'escape', 'return', 'tab', 'left', 'right', 'up', 'down', a lower-case letter or digit; `ctrl` for Ctrl+key."""
    name: str
    ctrl: bool = False


@dataclass(frozen=True)
class Wheel:
    x: int
    y: int
    dy: int
