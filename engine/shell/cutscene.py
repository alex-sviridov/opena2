"""The cutscene player (m1, docs/engine/cutscenes.md 4; REA cutscenes-rea.md 1-3): plays videos back to back, then goes on to `then`.

Params: `codes` (chapter videos: each marks its seen-mask bit when it starts, then plays `video\\<cutpaths line>\\NN.smk`, `0x48f919`) or `paths` (the start-up
chain: `publisher`, `nival`, `intro`), `then` / `then_params` (the screen after the last frame or an abort).  A key press or a left / right button press aborts
**everything** still to play (`0x48fc2e` returns 0 and the callers stop; an abort in a logo also skips the intro).  The music is stopped first and not
restarted (the next screen asks for its own), the cursor is hidden, the screen is black around the picture, 640x360 pictures sit 60 px down
(`0x493df0`), the last frame ends the video at once.  Frames are never skipped (the exe spins `SmackWait`): when late, every due frame is decoded and the newest shown."""

from engine import cutscene as C

from .events import Key, Press
from .scene import Scene, Video
from .screen import Screen


class Cutscene(Screen):
    name = "cutscene"

    def enter(self, codes=(), paths=(), then="menu", then_params=None, **params):
        self.then, self.then_params = then, then_params or {}
        self.queue = []                                     # [(seen-mask code or None, path)]
        fs = self.shell.fs
        for p in paths:
            self.queue.append((None, p))
        for code in codes:
            files = C.video_paths(fs, code) if fs is not None else []
            if fs is not None and files:
                self.queue.append((code, files[0]))
                self.queue.extend((None, f) for f in files[1:])
            elif fs is not None and not self.shell.services.video:
                self.shell.log("video skipped: code %d" % code)
        self.run = None
        self.frame = None                                   # the CutFrame on screen
        self.elapsed = 0.0
        self.shown = 0                                      # frames of the current video decoded so far
        self.done = False
        self.shell.services.music(None)                     # step 1 of `0x48f919`: the hard stop, even when nothing plays
        self._next_video()

    def exit(self):
        self.shell.services.pcm_stop()

    # -- the queue -----------------------------------------------------------------------------------------------------------------
    def _next_video(self):
        while self.queue:
            code, path = self.queue.pop(0)
            if code is not None:                            # the seen bit is set and saved before the first frame (`0x48f988`, `0x440cd2`)
                st = self.shell.settings
                st.videos_seen |= 1 << code
                self.shell.services.save_settings(st)
            try:
                self.run = C.Run(self.shell.fs, path)
            except (KeyError, OSError, ValueError) as e:
                self.shell.log("video failed: %s (%s)" % (path, e))
                continue
            self.shell.log("video: %s" % path)
            self.elapsed, self.shown = 0.0, 0
            return True
        self.run = None
        self.done = True
        return False

    def _finish(self):
        self.queue = []
        self.done = True
        return (self.then, self.then_params) if self.then_params else self.then

    # -- input / time --------------------------------------------------------------------------------------------------------------
    def event(self, ev):
        if isinstance(ev, (Key, Press)):                    # `WM_KEYDOWN` / `WM_SYSKEYDOWN` / left / right button down; releases, moves and the wheel do nothing
            self.shell.log("video aborted")
            return self._finish()
        return None

    def update(self, dt_ms):
        if self.run is None:
            return self._finish() if self.done else None
        self.elapsed += dt_ms
        due = int(self.elapsed // self.run.frame_ms) + 1
        while self.run is not None and self.shown < due:
            f = self.run.step()
            if f is None:
                if not self._next_video():
                    return self._finish()
                break
            self.shown += 1
            self.frame = f
            if f.audio is not None and not self.shell.settings.mute:
                self.shell.services.pcm(f.audio, self.run.sample_rate)
            if f.index + 1 >= self.run.frames:              # the last frame is shown and the video ends at once
                if not self._next_video():
                    return self._finish()
                break
        self.shell.services.pcm(None, 22050)                # keep the audio queue fed
        return None

    def scene(self):
        if self.frame is None:
            return Scene([], cursor=False)
        h, w = self.frame.pixels.shape
        ox, oy = self.origin
        return Scene([Video(self.frame.pixels, self.frame.palette, ox + (640 - w) // 2, oy + (0 if h == 480 else 60))], cursor=False)
