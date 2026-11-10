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
    """Frame `frame` of the `.256` sprite file `path` (keyed), top-left at (x, y); `shadow` first draws its silhouette darkened at (+5, +4) (check boxes, `0x4d757c`)."""
    path: str
    frame: int
    x: int
    y: int
    shadow: bool = False
