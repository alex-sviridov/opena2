"""The character generator panel (docs/engine/chargen.md; the original's panel `+0x36c`, ctor `0x42d39d`): what follows PreCreate.  The hero keeps the template's
attributes and a free pool of 0; the player moves points between the four attributes at the marginal cost of `cost(v) = trunc(0.349 (v-1)^1.15 + 0.5)`
(min 15, max 45), picks one of four weapon classes / spheres (the school), and presses Accept, Reset (25 x4, pool 100) or Back.

`ChargenState` is the pure model (rules of chargen.md 2.2 / 2.3); `CharGen` is the screen: the four child panels at their absolute rects, draw order back to
front, stat buttons and class columns that act on the **press**, text buttons that act on the release over the same button (CONFIRMED rects, pictures and sounds
of chargen.md 1).  Accept builds the campaign (`CampaignGame.new_game` with the chosen `HeroChoice`; the creation call `0x49183e` + the town stand-in) and goes on
to `locations`.

DECISIONs: the quadrant (480..640, 238..480) that nothing draws in the original keeps the last PreCreate pixels (CONFIRMED mechanism, chargen.md 1): `MainArea.bmp`, the right torch (a frozen frame, here 7) and the hovered OK button `okl`; the hint window (tips
`#tips5` / `#tips6`, `#tips7` after the first class click) is the exe's tips window (chargen.md 1.5, CONFIRMED rects: frame, text box, Close, check box "Show tips next time"
that writes Settings.tips at once); the preview (child 2) lists Life / Mana (`progression.derived_vitals` of the template with the current attributes) and the attributes;
the idle shimmer, the tooltips of slot 5 and the Esc key (the panel ignores it) are not built."""

from allods2.formats.progression import derived_vitals, skills_of, start_pools  # noqa: F401  (skills_of for the preview)
from allods2.graphics import load_bmp
from allods2.text import decode_text

from .events import Key, Move, Press, Release
from .scene import Image, Scene, Text
from .screen import Screen
from .tipswin import TipsWindow

BASE = "graphics/interface/chrgen/"
INN = "graphics/interface/inn/"
LEFTUP = "main/graphics/chrgen/leftup.bmp"
PRECREATE_DIR = BASE + "precreate/"
PRECREATE = PRECREATE_DIR + "mainarea.bmp"
STAT_FONT, TEXT_FONT = 4, 2
MIN_ATTR, MAX_ATTR, RESET_POOL, RESET_VALUE = 15, 45, 100, 25
ATTR_NAMES = ("Body", "Agility", "Mind", "Spirit")
TEMPLATE = {"MF": (40, 36, 25, 17), "FF": (37, 39, 21, 25), "MM": (28, 20, 41, 32), "FM": (19, 23, 30, 42)}      # units.md: the Start_* templates (body, reaction, mind, spirit)
CODE_KEY = {0x00: "MF", 0x40: "MM", 0x80: "FF", 0xC0: "FM"}      # `window+0x484` (newgame.HERO_CODE) -> the template key
ROW_Y = 54                                           # row i: value box (82, 54 + 32 i), plus (107, ..), minus (132, ..), 20x20 each
VALUE_X, PLUS_X, MINUS_X, BOX = 82, 107, 132, 20
POOL = (46, 181, 77, 22)
BUTTONS = ((484, 44, 140, 46), (484, 91, 140, 46), (484, 138, 140, 46))      # Accept, Reset, Back
BUTTON_TEXT = (0xEE, 0xEF, 0x104)                    # main.txt
BUTTON_SOUNDS = ("sfx/click_ok.wav", "sfx/sbros.wav", "sfx/back.wav")
CHANGE_SOUND = "sfx/chrgen/+_-.wav"
COLUMN_AT = (160, 0)
CLASSES = {"fighter": ("sword", "axe", "mace", "pike", "bow"), "mag": ("fire", "water", "air", "earth", "astral")}
CLASS_SOUNDS = {"fighter": ("fsword", "faxe", "fclub", "fpike"), "mag": ("mfire", "mwater", "mair", "mearth")}
# per column k = 0..4: the mask palette index and the picture's (x, y) on the screen (chrgen.md 1.3)
MASK = {"fighter": ((0xFF, 248, 93), (0xBF, 252, 126), (0x98, 248, 182), (0x7F, 244, 225), (0x66, 248, 250)),
        "mag": ((0x7F, 360, 150), (0x66, 232, 165), (0xFF, 292, 98), (0x98, 300, 228), (0xBF, 296, 158))}
PICKABLE = 4                                         # the hit loops are `< 4`: bow and astral cannot be picked
HINT = (160, 280, 312, 200)                          # the tips window `0x4dec24(0x467, 0, 0x118, 0x138, 0x1e0)`: SetRect (l, t, r, b) relative to the class column (160, 0); layout in tipswin.py
TIPS_LINE = {5: 8, 6: 10, 7: 12}                     # `#tipsN` header lines of town.txt (the text is the next line)


def font2(shell):
    from allods2.graphics import Font
    f = getattr(shell, "_font2", None)
    if f is None:
        f = shell._font2 = Font.load("graphics/font2/font2", shell.fs)
    return f


def measure_font2(shell, text):
    from allods2.graphics.font import font_bytes
    return font2(shell).measure(font_bytes(text))


def wrap_font2(shell, text, width):
    """The tips text wrapped to `width` with font2 (the lines as str)."""
    f = font2(shell)
    return [b.decode("cp866", "replace") if isinstance(b, bytes) else b for b in f.wrap(text, width)]


def cost(v):
    """`FUN_004f250e`: the point cost of an attribute value."""
    return int(0.349 * (v - 1) ** 1.15 + 0.5)


class ChargenState:
    """The panel's numbers (chargen.md 2.2 / 2.3): four attributes (body, reaction, mind, spirit), the free pool, the chosen school 1..4."""

    def __init__(self, start="MF"):
        self.start = start
        self.values = list(TEMPLATE[start])
        self.pool = 0
        self.school = 1                              # the template's best school (sword / fire); `game+0x4ac - 1` selected at show
        self.clicked = False                         # a class was clicked (the hint changes to `#tips7`)

    @property
    def mage(self):
        return self.start[1] == "M"

    def up(self, i):
        return cost(self.values[i] + 1) - cost(self.values[i])

    def down(self, i):
        return cost(self.values[i]) - cost(self.values[i] - 1)

    def can_plus(self, i):
        return self.values[i] < MAX_ATTR and self.pool >= self.up(i)

    def can_minus(self, i):
        return self.values[i] > MIN_ATTR

    def plus(self, i):
        if not self.can_plus(i):
            return False
        self.pool -= self.up(i)
        self.values[i] += 1
        return True

    def minus(self, i):
        if not self.can_minus(i):
            return False
        self.pool += self.down(i)
        self.values[i] -= 1
        return True

    def reset(self):
        """`0x42dfee`: 25 x4 and a pool of 100 (not the template)."""
        self.values = [RESET_VALUE] * 4
        self.pool = RESET_POOL

    def pick(self, k):
        if 0 <= k < PICKABLE:
            self.school = k + 1
            self.clicked = True
            return True
        return False

    def choice(self, name):
        from engine.campaign import HeroChoice
        return HeroChoice(self.start, tuple(self.values), self.school, name)


def rect_has(r, x, y):
    return r[0] <= x < r[0] + r[2] and r[1] <= y < r[1] + r[3]


class CharGen(Screen):
    name = "chargen"
    music = None                                     # the PreCreate music keeps playing (chargen.md 2.1)

    def __init__(self, shell):
        super().__init__(shell)
        self.state = ChargenState()
        self.masks = {}
        self.main = self.town = None
        self.vitals_cache = {}

    # -- enter ---------------------------------------------------------------------------------------------------------------------
    def enter(self, **params):
        self.player = {k: params.get(k) for k in ("name", "hero", "hero_code", "difficulty")}
        self.state = ChargenState(CODE_KEY[params.get("hero_code", 0)])
        self.kind = "mag" if self.state.mage else "fighter"
        if self.kind not in self.masks:
            m = load_bmp(BASE + self.kind + "/mask.bmp", self.shell.fs)
            import numpy as np
            self.masks[self.kind] = np.asarray(m.index if m.index is not None else m.rgb[..., 0])
        if self.main is None:
            from engine.ui.orders import MainText
            self.main = MainText.load(self.shell.fs)
            self.town = decode_text(self.shell.fs.read("main/text/town.txt")).split("\r\n")
        self.hover = None                            # ("plus", i) / ("minus", i) / ("class", k) / ("button", i) / ("close",)
        self.pressed = None
        self.hint = self.shell.settings.tips
        self.tips_win = TipsWindow(HINT, self.main, self.wrap, lambda t: measure_font2(self.shell, t))
        self.vitals_cache = {}

    # -- geometry / hit testing (screen coordinates; the panel is 640x480 at `origin`) ---------------------------------------------
    def _local(self, x, y):
        ox, oy = self.origin
        return x - ox, y - oy

    def hit(self, x, y):
        x, y = self._local(x, y)
        if self.hint:
            h = self.tips_win.hit(x, y)
            if h:
                return (h,)
        for i in range(4):
            if rect_has((PLUS_X, ROW_Y + 32 * i, BOX, BOX), x, y):
                return ("plus", i)
            if rect_has((MINUS_X, ROW_Y + 32 * i, BOX, BOX), x, y):
                return ("minus", i)
        for i, b in enumerate(BUTTONS):
            if rect_has(b, x, y):
                return ("button", i)
        mask = self.masks[self.kind]
        mx = x - COLUMN_AT[0]
        if 0 <= mx < 320 and 0 <= y < 480:
            v = int(mask[y, mx])
            for k in range(PICKABLE):
                if MASK[self.kind][k][0] == v:
                    return ("class", k)
        return None

    # -- input ---------------------------------------------------------------------------------------------------------------------
    def event(self, ev):
        if isinstance(ev, Move):
            self.hover = self.hit(ev.x, ev.y)
        elif isinstance(ev, Press) and ev.button == 1:
            self.hover = h = self.hit(ev.x, ev.y)
            self.pressed = h
            if h is None:
                return None
            if h[0] in ("plus", "minus"):
                if (self.state.plus if h[0] == "plus" else self.state.minus)(h[1]):      # the press applies it, no auto-repeat (`0x429e3e`)
                    self.shell.play(CHANGE_SOUND)
            elif h[0] == "class":
                if self.state.pick(h[1]):
                    self.shell.play("sfx/chrgen/skill/%s.wav" % CLASS_SOUNDS[self.kind][h[1]])
            elif h[0] == "button":
                self.shell.play(BUTTON_SOUNDS[h[1]])
        elif isinstance(ev, Release) and ev.button == 1:
            down, self.pressed = self.pressed, None
            self.hover = h = self.hit(ev.x, ev.y)
            if down is not None and down == h:
                if h[0] == "close":
                    self.hint = False
                elif h[0] == "tips":                 # message 0x46e: TipsMode := the box state (in memory at once; the engine saves with the settings)
                    self.shell.settings.tips = self.tips_win.toggle()
                    self.shell.services.save_settings(self.shell.settings)
                elif h[0] == "button":
                    return self._button(h[1])
        elif isinstance(ev, Key) and not ev.ctrl and ev.name == "return":
            self.shell.play(BUTTON_SOUNDS[0])
            return self._accept()
        return None

    def _button(self, i):
        if i == 0:
            return self._accept()
        if i == 1:
            self.state.reset()
            return None
        return "newgame"                              # Back: message `0x446` -> PreCreate (the shell's newgame screen is rebuilt with its defaults)

    def _accept(self):
        """Message `0x445` -> `0x40d480` + `0x49183e`: the creation call with the panel's values; the town stand-in follows (`locations`)."""
        import time
        from engine.campaign import CampaignGame
        p = self.player
        camp = CampaignGame(install=self.shell.fs, seed=time.time_ns() & 0xFFFFFFFF, difficulty=p["difficulty"])
        camp.new_game(self.state.choice(p["name"] or "Hero"))
        self.shell.campaign = camp
        self.shell.log("new campaign: %s, attributes %s, school %d, difficulty %d" % (p["name"], tuple(self.state.values), self.state.school, p["difficulty"]))
        return "locations"

    # -- drawing -------------------------------------------------------------------------------------------------------------------
    def vitals(self):
        """(max HP, max mana) of the preview hero, None without the data: `derived_vitals` of the start template with the current body / spirit and school."""
        key = (tuple(self.state.values), self.state.school)
        if key not in self.vitals_cache:
            try:
                from allods2.assets import AssetCache
                from engine.party import START
                assets = getattr(self.shell, "assets", None) or AssetCache(self.shell.fs)
                self.shell.assets = assets
                t = assets.unit_stats().lookup(True, START[self.state.start])
                sk = [skills_of(t)[0], 0, 0, 0, 0, 10]
                sk[self.state.school] = 20
                self.vitals_cache[key] = derived_vitals(t, tuple(sk), attrs=(self.state.values[0], self.state.values[3]))
            except Exception:                         # noqa: BLE001  the preview is decoration
                self.vitals_cache[key] = None
        return self.vitals_cache[key]

    def tips_text(self):
        n = 7 if self.state.clicked else 6 if self.state.mage else 5
        return self.town[TIPS_LINE[n] + 1] if len(self.town) > TIPS_LINE[n] + 1 else ""

    def wrap(self, text, width):
        return wrap_font2(self.shell, text, width)

    def scene(self):
        ox, oy = self.origin
        s, k = self.state, self.kind
        ops = [Image(PRECREATE, ox, oy), Image(PRECREATE_DIR + "torch2/t20007.bmp", ox + 589, oy + 200), Image(PRECREATE_DIR + "okl.bmp", ox + 548, oy + 400),
               Image(LEFTUP, ox, oy), Image(BASE + "fullstatsl.bmp", ox, oy + 238), Image(INN + "buttonsarea.bmp", ox + 480, oy),
               Image(BASE + k + "/column.bmp", ox + COLUMN_AT[0], oy + COLUMN_AT[1])]
        for i in range(4):
            y = ROW_Y + 32 * i
            ops.append(Text("%d" % s.values[i], ox + VALUE_X + 2, oy + y + 4, STAT_FONT, "gold", 0, 1))
            for kind, x, enabled, names in (("plus", PLUS_X, s.can_plus(i), ("pnloff", "ploff", "plon", "pdisable")),
                                            ("minus", MINUS_X, s.can_minus(i), ("mnloff", "mloff", "mlon", "mdisable"))):
                mine = self.hover == (kind, i)
                state = 3 if not enabled else 2 if mine and self.pressed == (kind, i) else 1 if mine else 0
                ops.append(Image(BASE + "buttons/%s.bmp" % names[state], ox + x, oy + y))
        ops.append(Text("%d" % s.pool, ox + POOL[0] + POOL[2] // 2, oy + POOL[1] + POOL[3] // 2 + 2, STAT_FONT, "gold", 0xA, 1))
        for c in range(PICKABLE + 1):                 # the class pictures: selected `on`, hovered `shine_off`, both `shine_on` (bow / astral are never selected or hovered)
            sel, hot = s.school == c + 1 and c < PICKABLE, self.hover == ("class", c)
            if sel or hot:
                ops.append(Image(BASE + "%s/%s/%s.bmp" % (k, CLASSES[k][c], "shine_on" if sel and hot else "on" if sel else "shine_off"),
                                 ox + MASK[k][c][1], oy + MASK[k][c][2], True))
        for i, (x, y, w, h) in enumerate(BUTTONS):
            mine = self.hover == ("button", i)
            held = mine and self.pressed == ("button", i)
            ops.append(Image(INN + "button%d%s.bmp" % (i + 1, "on" if held else "off"), ox + x, oy + y))
            ops.append(Text(self.main.line(BUTTON_TEXT[i]), ox + x + w // 2, oy + y + h // 2 + (1 if held else 0), STAT_FONT, "yellow" if mine else "gold", 0xA, 1))
        ops += self.preview_ops(ox, oy)
        if self.hint:
            ops += self.tips_win.ops(self.tips_text(), self.hover[0] if self.hover else None, self.pressed[0] if self.pressed else None, ox, oy)
        return Scene(ops)

    def preview_ops(self, ox, oy):
        """The preview panel (child 2): the hero's Life / Mana and attributes (DECISION: a small text list instead of the in-game info panel)."""
        s = self.state
        ops = [Text(self.player.get("name") or "", ox + 14, oy + 248, TEXT_FONT, "header", 0, 1)]
        v = self.vitals()
        rows = []
        if v is not None:
            rows.append(("Life", str(v[0])))
            if s.mage:
                rows.append(("Mana", str(v[1])))
        rows += [(n, str(s.values[i])) for i, n in enumerate(ATTR_NAMES)]
        for n, (label, value) in enumerate(rows):
            ops.append(Text(label, ox + 14, oy + 272 + 16 * n, TEXT_FONT, "label", 0, 1))
            ops.append(Text(value, ox + 120, oy + 272 + 16 * n, TEXT_FONT, "value", 0, 1))
        return ops
