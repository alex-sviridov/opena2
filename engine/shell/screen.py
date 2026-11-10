"""`Screen`: one state of the shell.  A screen is a UI-layer object: `enter` / `exit`, `event` (input -> optionally the name of the next screen),
`update` (time), `scene` (what to draw).  Screens never touch the simulation; they ask the shell for services (sounds, music, settings, files)."""


class Screen:
    name = ""
    music = None                    # the playlist the screen asks for (None = leave the music alone)
    driven = False                  # True: the backend hands the loop to `run` (the in-game screen) instead of drawing `scene`

    def __init__(self, shell):
        self.shell = shell

    # -- lifecycle -----------------------------------------------------------------------------------------------------------------
    def enter(self, **params):
        """Called when the screen becomes current (params of `Shell.go`)."""

    def exit(self):
        """Called when the screen is left."""

    # -- per frame -----------------------------------------------------------------------------------------------------------------
    def event(self, ev):
        """One input event; returns the next screen's name or `(name, params)`, None to stay."""
        return None

    def update(self, dt_ms):
        """Time passed; same return as `event`."""
        return None

    def scene(self):
        """The `Scene` to draw now."""
        raise NotImplementedError

    # -- helpers -------------------------------------------------------------------------------------------------------------------
    @property
    def origin(self):
        """Top-left of the 640x480 picture on the screen (`FUN_0048205b`: `(W - 640) / 2`, `(H - 480) / 2`)."""
        w, h = self.shell.size
        return (w - 640) // 2, (h - 480) // 2
