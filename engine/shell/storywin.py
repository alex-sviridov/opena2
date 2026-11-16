"""The story window over a town scene (`FUN_0041d15e`, ui-layout 11.5): an NPC click in the scene shows the `town.txt` section `#<key>` page by page, Ok (button, Enter) shows the next page and
voices it, ESC or the last page closes it.  The inn has its own copy of this window (`shell/inn.py`, which also knows the inn's persons as speakers); here the speaker is a roster hero or the
dummy doll of `story.dummy_doll_path`.  Modal: nothing reaches the scene under it."""

from types import SimpleNamespace

from engine import inn as I
from engine.ui import story
from engine.ui.widgets import widget_rect

from .events import Key, Move, Press, Release
from .inn import CLICK_UI, Wrapper
from .scene import Button, Frame, Portrait, Text


class StoryWindow:
    def __init__(self, shell, text, key, main):
        self.shell, self.main, self.wrap = shell, main, Wrapper(shell)
        camp = shell.campaign
        flags = story.hero_flags(camp.is_female, camp.is_mage) if camp is not None else 0
        exists = shell.fs.exists if shell.fs is not None else None
        self.dialogue = I.Dialogue(text, key, flags, exists)
        self.hot = self.pressed = False
        self.closed = False
        self._voice()

    def _voice(self):
        v = self.dialogue.voice
        self.shell.log("town: page %d of %s -> %s" % (self.dialogue.n, self.dialogue.key, v))
        if v:
            self.shell.services.speech(v)

    def rects(self):
        lay, d = SimpleNamespace(size=self.shell.size), self.dialogue
        return (widget_rect(lay, "story.frame"), widget_rect(lay, "story.text_npc" if d.wide else "story.text"), widget_rect(lay, "story.ok"),
                widget_rect(lay, "story.picture") if d.wide else None)

    def _ok(self):
        self.shell.play(CLICK_UI)
        if self.dialogue.advance():
            self._voice()
        else:
            self.closed = True

    def event(self, ev):
        ok = self.rects()[2]
        if isinstance(ev, Move):
            self.hot = ok.contains(ev.x, ev.y)
        elif isinstance(ev, Press) and ev.button == 1:
            self.pressed = ok.contains(ev.x, ev.y)
        elif isinstance(ev, Release) and ev.button == 1:
            down, self.pressed = self.pressed, False
            if down and ok.contains(ev.x, ev.y):
                self._ok()
        elif isinstance(ev, Key) and not ev.ctrl:
            if ev.name == "escape":
                self.closed = True
            elif ev.name == "return":
                self._ok()

    def _speaker(self, npc):
        """The roster hero with that number, else the dummy doll of the 0x51..0x64 speakers; (spec, type id)."""
        camp = self.shell.campaign
        assets = getattr(camp, "assets", None)
        hero = next((e for e in camp.roster if e.number == npc), None) if camp is not None else None
        if hero is not None and assets is not None:
            t = assets.unit_stats().lookup(True, hero.server_id)
            return I.hero_portrait(assets, hero), (t.unit_type if t is not None else 1)
        if 0x51 <= npc <= 0x64:
            return ("doll", (story.dummy_doll_path(npc),)), 1
        return None, 1

    def ops(self):
        d = self.dialogue
        frame, text, ok, pic = self.rects()
        ops = [Frame(frame.x, frame.y, frame.w, frame.h)]
        if pic is not None:
            spec, type_id = self._speaker(d.npc)
            if spec is not None:
                ops.append(Portrait(spec, pic.x, pic.y, None, True, type_id))
        for i, line in enumerate(self.wrap(d.text, text.w)):
            ops.append(Text(line, text.x, text.y + i * 17, 1, "highlight", 0, 1))
        ops.append(Button(ok.x, ok.y, ok.w, ok.h, self.main.line(0x4D), True, self.hot, self.hot and self.pressed))
        return ops
