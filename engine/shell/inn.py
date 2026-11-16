"""The Inn window (L7, docs/engine/town-inn.md, town-hero.md; `engine.inn` is the pure model): the left sheet of the selected person, the buttons panel (Hire / Fire, Talk,
Exit), the centre panel (the inn scene, the figure cells, the ambient animations) and the unit info panel of the shown hero with its two arrows, all at the 640x480 window
origin `O`; the dialogue (story) window opens over it for the NPC texts, with its Ok pages and voices.

Input as the exe's: a button acts on the release over the pressed one (Exit also plays `Out.wav` on the press), a press on a figure selects and the release acts at once (Hire / Fire
for a mercenary, Talk for an NPC), ESC = Exit, the hero arrows wrap; while the dialogue is open it is modal (ESC closes the whole window, Enter = Ok).  The screen opens and closes
through `TownCore` (`close_window` = the `0x445` -> `0x44c` -> `0x42e` chain).

DECISIONs (INFERRED, town.md 5 "L7 as built"): the info panel shows the hero's paper doll and the two arrows only (no name rows, no book / mode buttons); the left sheet's rows are
every `FUN_0046aa1d` row at detail 7 over a world-free unit (`engine.inn.person_rows`); the druid / Kaarg centre panels draw their water / taverner objects (`Ambient.objects`, CONFIRMED positions); a missing install falls back to the labels."""

from allods2.text import decode_text

from engine import inn as I
from engine import townscene as TS
from engine.ui import story
from engine.ui.layout import Rect
from engine.ui.orders import MainText
from engine.ui.widgets import widget_rect

from .events import Key, Move, Press, Release
from .scene import Button, Frame, Image, Portrait, Scene, Sprite, Text
from .screen import Screen
from .tipswin import TipsWindow

D = "graphics/interface/inn/"
CENTRE_BACK = {1: D + "centerarea.bmp", 2: "graphics/interface/inn_kaarg/tavernmain.bmp", 3: "graphics/interface/inn_druid/tavernmain.bmp"}
HERO_BACK = "graphics/interface/HumanBackR.bmp"
HERO_BACK_TEXT = "graphics/interface/TextBackR.bmp"
MODE_FILES = ("graphics/interface/TextMode.bmp", "graphics/interface/HumanMode.bmp")        # drawn in text mode / picture mode at (0x80, 4) of the panel (`0x4af659`-`0x4af6d3`)
ARROW_FILES = ("graphics/interface/ar1.bmp", "graphics/interface/ar2.bmp")
CLICK_UI = 1                                        # the info panel's arrow click (`0x4aebc8`: `FUN_00420eb0(1)` = sfx.reg id 1 = Click00, priority `0xdc`): CONFIRMED
STEP_MS = 125                                       # `0x4980b0`: the selected figure's frame step
TIPS_RECT = (160, 0, 312, 200)                      # `0x49ad49`: the tips window in the centre panel
FIGURE_FRAMES = 8
SPRITE_COUNT = {}


class Wrapper:
    """font1 line breaker for the dialogue text (our rule, the exe's `FUN_0045ccbb` measure); one line per paragraph without an install."""

    def __init__(self, shell):
        self.shell = shell
        self.font = None
        if shell.fs is not None:
            try:
                from allods2.graphics import Font
                self.font = Font.load("graphics/font1/font1", shell.fs)
            except Exception:                           # noqa: BLE001  no font (synthetic file systems)
                self.font = None

    def __call__(self, text, width):
        if self.font is None:
            return text.split("\n")
        return [b.decode("cp866", "replace") if isinstance(b, bytes) else b for b in self.font.wrap(text, width)]


class Inn(Screen):
    name, view = "inn", "inn"
    music = None                                    # the scene's playlist keeps playing (town-hero 6)

    def __init__(self, shell):
        super().__init__(shell)
        self.state = None
        self.hover = self.pressed = None
        self.dialogue = None

    @property
    def core(self):
        return self.shell.town_core()

    # -- enter / exit ---------------------------------------------------------------------------------------------------------------
    def enter(self, **params):
        sh = self.shell
        core = self.core
        fs = sh.fs
        self.main = MainText.load(fs) if fs is not None else MainText()
        self.unit_names = MainText.load(fs, "main/text/unitname.txt") if fs is not None else MainText()
        self.town_lines = []
        self.town_text = ""
        if fs is not None:
            try:
                self.town_text = decode_text(fs.read(TS.TOWN_TEXT))
                self.town_lines = self.town_text.split("\r\n")
            except (KeyError, OSError):
                pass
        self.assets = None
        if fs is not None:
            try:
                self.assets = sh.campaign.assets
            except Exception:                           # noqa: BLE001  no install behind the campaign: labels only
                self.assets = None
        self.state = I.InnState(sh.campaign, core.town, types="auto" if self.assets is not None else None)
        self.hover = self.pressed = None
        self.info_text = False                          # the info panel's mode flag `+0x70` (ctor 1 = picture; mission run-time state is not carried: INFERRED default)
        self.dialogue = None
        self.wrap = Wrapper(sh)
        self.clock = self.stamp = 0                      # ms; `0x6275c8` the shared frame-step stamp
        self.frames = [0] * self.state.count             # `+0x24c` / `+0x260`
        self.sprite_frames = [self._frames_of(p) for p in self.state.persons]
        self.ambient = I.Ambient(core.town, sh.rng, self._ambient_frames())
        self.hint = sh.settings.tips
        self.tips_win = TipsWindow(TIPS_RECT, self.main, self._tips_wrap, self._tips_measure)
        self.portrait_cache = {}
        sh.play(I.ENTER[core.town])                      # `+0xa4`: the open sound at the end of the load
        sh.services.loop(self.ambient.loop)              # `FUN_004a0ff0(+0x90)`: the ambient loop (human `water.wav`)

    def exit(self):
        self.dialogue = None
        self.shell.services.loop(None)

    def _frames_of(self, p):
        """The frame count of a figure's sprite file (measured on the install, 8 / 5 as the files have)."""
        if self.shell.fs is None:
            return FIGURE_FRAMES
        path = p.sprite
        if path not in SPRITE_COUNT:
            try:
                from allods2.graphics import SpriteFile
                SPRITE_COUNT[path] = len(SpriteFile.load(path, self.shell.fs).sprites)
            except Exception:                           # noqa: BLE001
                SPRITE_COUNT[path] = FIGURE_FRAMES
        return SPRITE_COUNT[path]

    def _ambient_frames(self):
        fs = self.shell.fs
        if fs is None:
            return None
        out = {}
        for key, d in (("candle", "candle"), ("cauldron", "cauldron"), ("drink", "tender/drink"), ("breath", "tender/breath")):
            try:
                out[key] = len(fs.listdir(D + d))
            except Exception:                           # noqa: BLE001
                pass
        return out

    def _tips_wrap(self, text, width):
        if self.shell.fs is None:
            return text.split("\n")
        from .chargen import wrap_font2
        return wrap_font2(self.shell, text, width)

    def _tips_measure(self, text):
        if self.shell.fs is None:
            return 7 * len(text)
        from .chargen import measure_font2
        return measure_font2(self.shell, text)

    def tips_text(self):
        """`#tips2` of town.txt (the line after its header)."""
        for i, line in enumerate(self.town_lines):
            if line.strip().lower() == "#tips2":
                return self.town_lines[i + 1] if i + 1 < len(self.town_lines) else ""
        return ""

    # -- geometry / hit testing (window-relative points) ----------------------------------------------------------------------------
    def _local(self, x, y):
        ox, oy = self.origin
        return x - ox, y - oy

    def hit(self, x, y):
        x, y = self._local(x, y)
        if self.hint:
            h = self.tips_win.hit(x, y)
            if h:
                return (h,)
        b = I.button_at(x, y)
        if b is not None:
            return ("button", b)
        for k, r in enumerate(I.ARROWS):
            if I.rect_has(r, x, y):
                return ("arrow", k)
        if I.rect_has(I.MODE_BUTTON, x, y):
            return ("mode",)
        f = I.cell_at(x, y, self.state.count)
        return None if f is None else ("figure", f)

    def point_of(self, kind, i):
        """Screen coordinates of the middle of a button / figure / arrow (tests, scripted clicks)."""
        ox, oy = self.origin
        r = I.BUTTONS[i] if kind == "button" else I.ARROWS[i] if kind == "arrow" else I.cell_rect(i)
        return ox + r[0] + r[2] // 2, oy + r[1] + r[3] // 2

    # -- the dialogue window ---------------------------------------------------------------------------------------------------------
    def _flags(self):
        g = self.shell.campaign
        return story.hero_flags(g.is_female, g.is_mage)

    def open_dialogue(self, key):
        """`FUN_0041d15e(key)`: the story window on the `town.txt` section; page 1 and its voice at once."""
        exists = self.shell.fs.exists if self.shell.fs is not None else None
        self.dialogue = I.Dialogue(self.town_text, key, self._flags(), exists)
        self.dlg_pressed = False
        self._voice()

    def _voice(self):
        v = self.dialogue.voice
        self.shell.log("inn: page %d of %s -> %s" % (self.dialogue.n, self.dialogue.key, v))
        if v:
            self.shell.services.speech(v)

    def dialogue_frame(self):
        from types import SimpleNamespace
        return widget_rect(SimpleNamespace(size=self.shell.size), "story.frame")

    def dialogue_rects(self):
        from types import SimpleNamespace
        lay = SimpleNamespace(size=self.shell.size)
        d = self.dialogue
        return (widget_rect(lay, "story.frame"), widget_rect(lay, "story.text_npc" if d.wide else "story.text"), widget_rect(lay, "story.ok"),
                widget_rect(lay, "story.picture") if d.wide else None)

    def _dialogue_ok(self):
        """Message `0x470`: the next page, or the window closes."""
        self.shell.play(CLICK_UI)
        if self.dialogue.advance():
            self._voice()
        else:
            self.dialogue = None

    def _dialogue_event(self, ev):
        _, _, ok, _ = self.dialogue_rects()
        if isinstance(ev, Move):
            self.hover = ("ok",) if ok.contains(ev.x, ev.y) else None
        elif isinstance(ev, Press) and ev.button == 1:
            self.dlg_pressed = ok.contains(ev.x, ev.y)
        elif isinstance(ev, Release) and ev.button == 1:
            down, self.dlg_pressed = self.dlg_pressed, False
            if down and ok.contains(ev.x, ev.y):
                self._dialogue_ok()
        elif isinstance(ev, Key) and not ev.ctrl:
            if ev.name == "escape":                       # `FUN_004dc595` -> `0x446`: the whole window closes
                self.dialogue = None
            elif ev.name == "return":
                self._dialogue_ok()
        return None

    # -- input -----------------------------------------------------------------------------------------------------------------------
    def event(self, ev):
        if self.dialogue is not None:
            return self._dialogue_event(ev)
        if isinstance(ev, Move):
            self.hover = self.hit(ev.x, ev.y)
        elif isinstance(ev, Press) and ev.button == 1:
            self.hover = h = self.hit(ev.x, ev.y)
            self.pressed = h
            if h is None:
                return None
            if h[0] == "button" and h[1] == 2:
                self.shell.play(I.SLOTS["out"])          # `0x496b41`: the Exit press plays Out.wav at once
            elif h[0] == "figure":
                self.state.select(h[1])                  # `0x49a347` -> `0x4946b6`
        elif isinstance(ev, Release) and ev.button == 1:
            down, self.pressed = self.pressed, None
            self.hover = h = self.hit(ev.x, ev.y)
            if h is None:
                return None
            if h[0] == "arrow" and (down is None or down[0] in ("arrow", "figure")):     # `0x4aebc8`: the release inside the arrow rect acts, the press is not consulted (sound id 1, prio 0xdc, then 0x414 / 0x415)
                self.shell.play(CLICK_UI)
                self.state.hero_prev() if h[1] == 0 else self.state.hero_next()
                return None
            if h[0] == "mode" and down == h:                 # `0x4aebc8` `0x4aef0a`: mode & 0x600 == 0 (the inn is mode 4) -> message `0x412`: sound id 1 (prio 0xdc), `+0x70` toggles
                self.shell.play(CLICK_UI)
                self.info_text = not self.info_text
                return None
            if h[0] == "figure" and (down is None or down[0] in ("figure", "arrow")):    # `0x49a197` -> `0x49a347`: the release re-runs the hit test at its own point; a press elsewhere does not matter
                self._apply(self.state.figure_release(h[1]))
                return None
            if down is None:
                return None
            if down[0] == "close" and h == down:
                self.hint = False
            elif down[0] == "tips" and h == down:
                self.shell.settings.tips = self.tips_win.toggle()
                self.shell.services.save_settings(self.shell.settings)
            elif down[0] == "button" and h == down:
                if h[1] == 2:
                    return self.exit_window()
                self._apply(self.state.button_release(h[1]))
        elif isinstance(ev, Key) and not ev.ctrl and ev.name == "escape":
            return self.exit_window()
        return None

    def exit_window(self):
        """The Exit button / ESC (`0x49b69b`): `0x445` -> `0x44c`, `0x42e` at mask exactly 4 -> the scene."""
        self.core.close_window()
        return self.shell.town_screen()

    def _apply(self, effects):
        """The handler's effects in the exe's order: the dialogue window on the text key, the sound."""
        for e in effects:
            if e.kind == "text":
                self.open_dialogue(e.value)
            elif e.kind == "sound":
                self.shell.play(I.SLOTS[e.value])
        self.shell.log("inn: " + " ".join("%s=%s" % (e.kind, e.value) for e in effects))

    # -- time -----------------------------------------------------------------------------------------------------------------------------
    def update(self, dt_ms):
        self.clock += dt_ms
        self.ambient.advance(dt_ms)
        for path in self.ambient.take_events():
            self.shell.play(path)
        sel = self.state.sel                              # the window keeps drawing under the dialogue
        if sel >= 0 and self.clock - self.stamp > STEP_MS:
            self.frames[sel] = (self.frames[sel] + 1) % max(1, self.sprite_frames[sel])
            self.stamp = self.clock
        return None

    # -- drawing ---------------------------------------------------------------------------------------------------------------------
    def _portrait(self, key, make):
        if key not in self.portrait_cache:
            try:
                self.portrait_cache[key] = make() if self.assets is not None else None
            except Exception:                           # noqa: BLE001  the picture is decoration
                self.portrait_cache[key] = None
        return self.portrait_cache[key]

    def _tables(self):
        """The item and spell tables for the left sheet's derived rows (None, None without an install)."""
        if self.assets is None:
            return None, None
        try:
            return self.assets.items(), self.assets.spells()
        except Exception:                               # noqa: BLE001  the rows then show the template's plain numbers
            return None, None

    def _hero_rows(self, entry):
        """The info panel's text mode: `FUN_0046aa1d` rows of the shown hero (cached per hero state)."""
        key = ("hr", entry.number, id(entry.state), id(entry.spec))
        if key not in self.portrait_cache:
            try:
                self.portrait_cache[key] = I.hero_rows(self.assets, entry, self.main, self.unit_names) if self.assets is not None else []
            except Exception:                           # noqa: BLE001  decoration only
                self.portrait_cache[key] = []
        return self.portrait_cache[key]

    def scene(self):
        ox, oy = self.origin
        st = self.state
        ops = []
        # left panel (0x44d): the two bitmaps, the rows, the portrait
        for path, x, y in I.LEFT_BITMAPS:
            ops.append(Image(path, ox + x, oy + y))
        p = st.person()
        if p is None:
            ops += [Text(self.main.line(I.MAIN_NO_UNITS), ox + 88, oy + 54, 1, "label", 2, 1), Text(self.main.line(I.MAIN_SELECTED), ox + 88, oy + 66, 1, "label", 2, 1)]
        else:
            for text, x, y, flags, table in I.person_rows(p, self.main, self.unit_names, *self._tables()):
                ops.append(Text(text, ox + 12 + x, oy + y, 2, table, flags, 1))
            spec = self._portrait(("p", st.sel, p.a), lambda: I.person_portrait(self.assets, p))
            if spec is not None:
                ops.append(Portrait(spec, ox + I.PORTRAIT_AT[0], oy + I.PORTRAIT_AT[1], (0, 0, 160 - I.PORTRAIT_AT[0], 240)))
        # buttons panel (0x44e)
        ops.append(Image(D + "buttonsarea.bmp", ox + 480, oy))
        for i, (x, y, w, h) in enumerate(I.BUTTONS):
            mine = self.hover == ("button", i)
            held = mine and self.pressed == ("button", i)
            ops.append(Image(D + "button%d%s.bmp" % (i + 1, "on" if held else "off"), ox + x, oy + y))
            line = st.caption(i)
            if line is not None:
                ops.append(Text(self.main.line(line), ox + x + w // 2, oy + y + h // 2 + (1 if held else 0), 4, "yellow" if mine else "gold", 0xA, 1))
        # centre panel (0x450)
        cx, cy = I.CENTRE_AT
        ops.append(Image(CENTRE_BACK[self.core.town], ox + cx, oy + cy))
        if self.core.town == 1:
            a = self.ambient
            ops.append(Image(D + "candle/t%04d.bmp" % a.candle, ox + cx + 0x30, oy + cy, True))
            ops.append(Image(D + "cauldron/t%04d.bmp" % a.cauldron, ox + cx + 0x104, oy + cy + 0xA0, True))
            t = a.tender_ops()
            if t:
                ops.append(Image(t, ox + cx + 0x50, oy + cy + 0x98, True))
        else:
            for path, x, y in self.ambient.objects():                  # the druid water / taverner, the Kaarg taverner objects (`0x49cf22`, `0x49f467`)
                ops.append(Image(path, ox + cx + x, oy + cy + y, True))
        for i, person in enumerate(st.persons):
            fx, fy, fw, fh = I.cell_rect(i)
            talk = person.kind == "npc" and st.sel == i
            ops.append(Image(D + ("manbacktalk.bmp" if talk else "manback.bmp"), ox + fx, oy + fy))
            ops.append(Sprite(person.sprite, self.frames[i] if self.frames[i] < self.sprite_frames[i] else 0, ox + fx, oy + fy))
            if person.kind == "merc" and st.taken(i):
                ops.append(Text(self.main.line(I.MAIN_HIRED), ox + fx + fw // 2, oy + fy + fh // 2, 2, "red", 0xA, 1))
        for path, x, y in I.EDGE_STRIPS:
            ops.append(Image(path, ox + x, oy + y, True))
        # the unit info panel (window 7) at (480, 238)
        ix, iy, _, _ = I.INFO_PANEL
        ops.append(Image(HERO_BACK_TEXT if self.info_text else HERO_BACK, ox + ix, oy + iy))
        ops.append(Image(MODE_FILES[0 if self.info_text else 1], ox + ix + 0x80, oy + iy + 4, True))
        entry = st.shown_hero()
        if entry is not None and self.info_text:
            for text, x, y, flags, table in self._hero_rows(entry):
                ops.append(Text(text, ox + ix + x, oy + iy + y, 2, table, flags, 1))
        elif entry is not None:
            spec = self._portrait(("h", entry.number, id(entry.state)), lambda: I.hero_portrait(self.assets, entry))
            if spec is not None:
                ops.append(Portrait(spec, ox + ix, oy + iy + 2))
        for k, (x, y, w, h) in enumerate(I.ARROWS):
            ops.append(Image(ARROW_FILES[k], ox + x, oy + y, True))
        if self.hint:
            ops += self.tips_win.ops(self.tips_text(), self.hover[0] if self.hover and len(self.hover) == 1 else None, self.pressed[0] if self.pressed and len(self.pressed) == 1 else None, ox, oy)
        if self.dialogue is not None:
            ops += self._dialogue_ops()
        return Scene(ops)

    def _dialogue_ops(self):
        d = self.dialogue
        frame, text, ok, pic = self.dialogue_rects()
        ops = [Frame(frame.x, frame.y, frame.w, frame.h)]
        if pic is not None:
            spec, type_id = self._speaker(d.npc)
            if spec is not None:
                ops.append(Portrait(spec, pic.x, pic.y, None, True, type_id))
        for i, line in enumerate(self.wrap(d.text, text.w)):
            ops.append(Text(line, text.x, text.y + i * 17, 1, "highlight", 0, 1))
        mine = self.hover == ("ok",)
        ops.append(Button(ok.x, ok.y, ok.w, ok.h, self.main.line(0x4D), True, mine, mine and self.dlg_pressed))
        return ops

    def _speaker(self, npc):
        """`FUN_0041d48d(npc)`: the person with that number (a unit in the window), else the dummy female mage (`story.dummy_doll_path`); (spec, type id for the crop)."""
        p = next((q for q in self.state.persons if q.a == npc), None)
        if p is not None and p.template is not None:
            return self._portrait(("s", npc), lambda: I.person_portrait(self.assets, p)), p.template.unit_type
        hero = next((e for e in self.shell.campaign.roster if e.number == npc), None)
        if hero is not None and self.assets is not None:
            t = self.assets.unit_stats().lookup(True, hero.server_id)
            return self._portrait(("sh", npc), lambda: I.hero_portrait(self.assets, hero)), (t.unit_type if t is not None else 1)
        if 0x51 <= npc <= 0x64:
            return ("doll", (story.dummy_doll_path(npc),)), 1
        return None, 1
