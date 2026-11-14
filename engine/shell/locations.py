"""The world map (L5, docs/engine/town-worldmap.md; `engine.worldmap` is the pure part): the 640x480 picture with the available locations as flags.  The pointer
picks the nearest available location (no radius), the route to it shows as dots, a click starts the walk (a dot per 100 ms, the Cross at the destination),
the end enters the location through `TownCore.walk_to` (mission start, or a town's scene).  After town 1 the intro map (`Umoir`) walks to the head of the available list
by itself.  No button, no menu and no key leaves the screen (every key is consumed, ESC included: CONFIRMED `0x470fd4`).

DECISIONs: the pointer before the first move is the last one the shell saw (`Shell.mouse`, the picture's centre at the very start); the party point falls back to the
head of the available list when the core has none (a shell started on this screen); a click while walking finishes the walk at once, as the exe does; without an
install the route is a straight line and the locations get fixed stand-in points (`worldmap.WorldData`), so the screen runs in the synthetic tests."""

from engine import worldmap as M

from .events import Key, Move, Press, Release
from .scene import Image, Scene, Sprite, Text
from .screen import Screen

MISSION, TOWN = M.MISSION, M.TOWN
SPR = M.SPRITES
FRAMES = {"flag1": 9, "flag": 4, "cross": 13, "missionflag": 9, "flagonmap": 9, "yourflag": 4}          # town-worldmap 3.2
OFFSETS = {"flagonmap": (-5, -0x25), "missionflag": (-5, -0x29), "yourflag": (-0x14, -0x2c), "flag": (-10, -0x18), "cross": (-10, -12)}      # the frame's top-left from the point (open question 1)
GONE = None


class Locations(Screen):
    name = "locations"
    music = None                            # the core's `map` event picks the playlist (`TownCore.open_map`)

    def __init__(self, shell):
        super().__init__(shell)
        self.reset()

    def reset(self):
        self.intro = False
        self.avail = []                     # the available list (type, id), list order
        self.dest = None                    # index into `avail` of the hovered / walked-to location (`+0x10c`)
        self.route = []
        self.walk = None                    # `worldmap.Walk` while `+0x12c != 0`
        self.clock = self.since_draw = 0    # ms; a draw every 100 ms
        self.mouse = (320, 240)
        self.title, self.lines = "", []
        self.point_sound = 0                # `window+0x190`
        self.sound_end = 0                  # ms on `clock` when the current Point sound ends

    @property
    def core(self):
        return self.shell.town_core()

    @property
    def data(self):
        return self.shell.worldmap()

    def enter(self, **params):
        core = self.core
        if core.view != "map":
            core.open_map()                                                      # the map window's open (`0x48b419`): bit 0x10, the map music
        self.shell.drain_town()
        self.reset()
        self.intro = core.intro
        self.avail = list(self.shell.campaign.camp.available)
        self.party = core.party_point or (self.avail[0] if self.avail else None)
        self.mouse = self.shell.mouse or (320, 240)
        self.mouse = (self.mouse[0] - self.origin[0], self.mouse[1] - self.origin[1])
        if not self.intro:
            self.hover()

    # -- the model -----------------------------------------------------------------------------------------------------------------
    def points(self):
        return [self.data.point(loc) for loc in self.avail]

    @property
    def party_point(self):
        return self.data.point(self.party) if self.party is not None else None

    def hover(self):
        """`0x4716aa`: the nearest available location becomes the destination; the route and the text follow when it changed."""
        i = M.nearest(self.points(), *self.mouse)
        if i is None or i == self.dest or self.party is None:
            return
        self.set_dest(i)

    def set_dest(self, i):
        self.dest = i
        loc = self.avail[i]
        self.route = self.data.route(self.party_point, self.data.point(loc), self.intro)
        self.title, self.lines = self.text_of(loc)

    def text_of(self, loc):
        if self.intro:
            return "", []
        title, body = M.title_and_body(self.data.texts, loc)
        return title, self.wrap(body)

    def wrap(self, body):
        """The description's lines as the exe draws them (`worldmap.wrap` + `draw_lines`), measured with font2."""
        if not body:
            return []
        width = M.DESC_RECT[2] - M.DESC_RECT[0]
        try:
            from .chargen import measure_font2
            measure = lambda t: measure_font2(self.shell, t)
            measure(" ")
        except Exception:                                    # noqa: BLE001  no fonts (synthetic tests): 6 px per character
            measure = lambda t: 6 * len(t)
        return M.draw_lines(M.wrap(body, width, measure))

    def start_walk(self):
        if self.dest is None or not self.route:
            return
        self.walk = M.Walk(self.route)

    # -- input ---------------------------------------------------------------------------------------------------------------------
    def event(self, ev):
        ox, oy = self.origin
        if isinstance(ev, Move):
            self.mouse = (ev.x - ox, ev.y - oy)
            if self.walk is None and not self.intro:
                self.hover()
        elif isinstance(ev, Press) and ev.button == 1:
            self.mouse = (ev.x - ox, ev.y - oy)
            if self.walk is not None:
                return self.finish()                          # `0x470f72`: finish at once
            if not self.intro:
                self.hover()
                self.start_walk()
        elif isinstance(ev, Key) and self.walk is not None:
            return self.finish()                              # a key finishes the walk; with no walk every key is consumed too
        return None

    def update(self, dt_ms):
        """A draw every 100 ms: the intro starts its walk at the first one, a walk lays one more step."""
        self.clock += dt_ms
        self.since_draw += dt_ms
        while self.since_draw >= M.DRAW_MS:
            self.since_draw -= M.DRAW_MS
            out = self.draw_step()
            if out is not None:
                return out
        return None

    def draw_step(self):
        if self.intro and self.walk is None and self.avail:
            self.party = self.core.party_point or self.party
            self.set_dest(0)                                  # `0x46fe5d`: the head of the available list, the walk starts by itself
            self.start_walk()
        if self.walk is None:
            return None
        done = self.walk.step()
        if self.walk.laying and self.clock >= self.sound_end:   # `0x470353`-`0x4703ac`, after the counters grow: the current Point sound must have finished,
            self.point_sound ^= 1                             # then the index toggles and that sound starts (the first one played is Point2)
            path = M.POINT_SOUNDS[self.point_sound]
            self.shell.play(path)
            self.sound_end = self.clock + self.data.sound_ms(path)
        return self.finish() if done else None

    def finish(self):
        """The end sequence (`0x445` -> `0x44c` -> `0x468` -> `ScenarioEnterLocation`): the first available location whose point is the destination's (the head in the intro)."""
        self.walk = None
        if self.dest is None:
            return None
        pt = self.data.point(self.avail[self.dest])
        loc = self.avail[0] if self.intro else next(l for l in self.avail if self.data.point(l) == pt)
        if not self.core.walk_to(loc):
            return None
        self.shell.drain_town()
        if loc[0] == TOWN:
            return "town"
        return "game", {"campaign": self.shell.campaign, "mission": loc[1]}

    # -- drawing -------------------------------------------------------------------------------------------------------------------
    def frame(self, kind):
        return (self.clock // M.DRAW_MS) % FRAMES[kind]

    def sprite(self, kind, point, frame=None):
        ox, oy = self.origin
        dx, dy = OFFSETS[kind]
        return Sprite(SPR[kind], self.frame(kind) if frame is None else frame, ox + point[0] + dx, oy + point[1] + dy)

    def scene(self):
        ox, oy = self.origin
        ops = [Image(M.BACKGROUND[self.intro], ox, oy)]
        if self.walk is not None:
            dots = self.walk.dots
        else:
            dots = self.route[::M.STEP] if self.route else []
        ops += [Image(M.BALL, ox + x - 4, oy + y - 4, True) for x, y in dots]
        party = self.party_point
        dest = self.data.point(self.avail[self.dest]) if self.dest is not None else None
        if self.walk is not None:
            if dest is not None:
                ops.append(self.sprite("cross", dest, self.walk.cross_frame))
        elif not self.intro:
            for loc in self.avail:
                p = self.data.point(loc)
                if p != party:
                    ops.append(self.sprite("missionflag" if p == dest else "flagonmap", p))
        if party is not None:
            ops.append(self.sprite("flag" if self.intro else "yourflag", party))
        if not self.intro and self.title:
            ops.append(Text(self.title, ox + M.TEXT_X, oy + M.TITLE_Y, 4, M.TITLE_GRADIENT, 2, 1))
            for i, line in enumerate(self.lines):
                ops.append(Text(line, ox + M.TEXT_X, oy + M.DESC_Y + M.DESC_LINE * i, 2, "mapdesc", 2, 1))
        return Scene(ops)
