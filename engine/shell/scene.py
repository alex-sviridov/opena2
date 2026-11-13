"""The drawing description of a screen: a list of ops the backend paints in order (no pygame here, so a screen is testable without a window).

`Image`: a bitmap of the game file system, opaque, top-left at (x, y).  `Text`: font1..4 text in a colour table of `backend_pygame.text.TABLES`
(flags as `engine.ui.info`: 0 left, 1 right, 2 centre, 8 middle).  `Fill`: a flat rectangle.  `Scene.cursor`: draw the arrow cursor (the shell's
only cursor; the original's menus use the default one)."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Image:
    path: str
    x: int
    y: int
    key: bool = False               # black (0, 0, 0) is transparent: the overlays of the character generator's class pictures


@dataclass(frozen=True)
class Text:
    text: str
    x: int
    y: int
    font: int = 1
    table: str = "normal"
    flags: int = 0
    shadow: int = 1


@dataclass(frozen=True)
class Fill:
    x: int
    y: int
    w: int
    h: int
    rgb: tuple = (0, 0, 0)


@dataclass(frozen=True)
class Tooltip:
    """The shared tooltip box (ui-layout 11.6b, `FUN_00427999`): `lines` in the box (x, y)-(right, bottom) (the exe's RECT), painted by the in-game tooltip painter; the caller emits it last."""
    lines: tuple
    x: int
    y: int
    right: int
    bottom: int


@dataclass
class Scene:
    ops: list = field(default_factory=list)
    cursor: bool = True


@dataclass(frozen=True)
class Frame:
    """A dialog frame of `lm.256` (ui-layout 11.4): w x h including the 8 px drop shadow, top-left at (x, y)."""
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class Button:
    """A dialog text button (ui-layout 11.4 `FUN_004d571a`): bevel, centred font1 label, gold while enabled and hovered, shadow 4 while pressed, darkened when disabled."""
    x: int
    y: int
    w: int
    h: int
    label: str
    enabled: bool = True
    hover: bool = False
    pressed: bool = False


@dataclass(frozen=True)
class Sprite:
    """Frame `frame` of the `.256` sprite file `path` (keyed), top-left at (x, y); `shadow` > 0 draws the frame's silhouette darkened by that level instead of the frame itself (the caller emits it first, offset by (+4, +4) / (+5, +4):
    check boxes `0x4d757c`, sliders `0x4da80f`): `dst * (16 - level) / 16`."""
    path: str
    frame: int
    x: int
    y: int
    shadow: int = 0                 # darken level of the silhouette drawn first at (+4, +4) / (+5, +4): `dst * (16 - level) / 16` (0 = none; the widgets use 4)
