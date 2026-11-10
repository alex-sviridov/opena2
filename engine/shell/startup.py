"""Startup (docs/engine/shell.md 2): the exe plays `video\\logos\\publisher.smk`, `video\\logos\\nival.smk`, `video\\intro\\01.smk` (CONFIRMED
`FUN_0048fb2a`, `FUN_0048f919`, post `0x421` at `0x4818a0`) and then shows the main menu.  Decoding Smacker is a later step: every video is a
placeholder that logs `video skipped: <name>` and counts as played, so the chain runs on to the menu at once.  A key or a click would abort the
rest of the chain in the exe; here nothing is left to abort."""

from .screen import Screen
from .scene import Scene

VIDEOS = ("video/logos/publisher.smk", "video/logos/nival.smk", "video/intro/01.smk")


class Startup(Screen):
    name = "startup"

    def enter(self, **params):
        self.pending = list(VIDEOS)

    def update(self, dt_ms):
        while self.pending:
            self.shell.log("video skipped: %s" % self.pending.pop(0))
        return "menu"

    def event(self, ev):
        return None

    def scene(self):
        return Scene([], cursor=False)             # black: the exe clears the screen to colour 0 before each picture
