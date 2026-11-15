"""Startup (docs/engine/shell.md 2, cutscenes.md 4): the exe plays `video\\logos\\publisher.smk`, `video\\logos\\nival.smk`, `video\\intro\\01.smk` (CONFIRMED
`FUN_0048fb2a`, `FUN_0048f919(0)`, post `0x421` at `0x4818a0`) and then shows the main menu.  With a video-capable backend (`Services.video`) the `cutscene` screen
plays the chain (a key or a click skips all of it, as the exe); without one every video logs `video skipped: <name>` and counts as played, so the chain runs on
to the menu at once (tests, headless runs)."""

from engine import cutscene as C

from .screen import Screen
from .scene import Scene

VIDEOS = ("video/logos/publisher.smk", "video/logos/nival.smk", "video/intro/01.smk")


class Startup(Screen):
    name = "startup"

    def enter(self, **params):
        self.pending = list(VIDEOS)

    def update(self, dt_ms):
        sh = self.shell
        if sh.services.video and sh.fs is not None and all(sh.fs.exists(p) for p in VIDEOS):
            self.pending = []
            sh.settings.videos_seen |= 1                      # the intro is code 0 (`0x48f919(0)` sets bit 0 and saves, even when aborted)
            sh.services.save_settings(sh.settings)
            return "cutscene", {"paths": list(VIDEOS), "then": "menu"}
        while self.pending:
            sh.log("video skipped: %s" % self.pending.pop(0))
        return "menu"

    def event(self, ev):
        return None

    def scene(self):
        return Scene([], cursor=False)             # black: the exe clears the screen to colour 0 before each picture
