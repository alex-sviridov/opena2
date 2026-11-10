"""The shell (docs/engine/shell.md): the screens around the game and the one state machine that moves between them.  No pygame, no World:
screens are UI-layer objects (enter / exit, input events, a drawing description); only `GameScreen` asks for a `World`, through the
`services.start_game` the backend supplies."""

from .events import Key, Move, Press, Release, Wheel
from .game import GameScreen
from .machine import GRAPH, Shell, ShellError, Services
from .mainmenu import MainMenu
from .newgame import NewGame
from .options import Options
from .scene import Button, Fill, Frame, Image, Scene, Sprite, Text
from .startup import Startup

__all__ = ["GRAPH", "Shell", "ShellError", "Services", "Screen", "Startup", "MainMenu", "Options", "NewGame", "GameScreen",
           "Key", "Move", "Press", "Release", "Wheel", "Scene", "Image", "Text", "Fill", "Frame", "Button", "Sprite"]

from .screen import Screen  # noqa: E402
