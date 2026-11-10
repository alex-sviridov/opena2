"""The Director (docs/engine/audio.md 5): turns what the simulation, the commands and the camera say into `VoiceMixer` plays.  Pure and device-free: the clock is
passed in (wall clock live, `tick * 1000 / rate` in a replay: `replay_ms`), the file durations come from `duration_ms(path)` (the decoded length), the audio
layer's own `Rng` makes every random choice.

    d = Director(table, banks, duration_ms, settings)
    plays = d.frame(now_ms, world, view, commands)     # drains world.sound_events (set `keep_sound_events=True` on the Simulation, the Director clears the list)
    plays += d.ui(2)                                   # a UI click

Results are the mixer's (`played`, `stolen:N`, `dropped:busy`, `dropped:voices`) plus `dropped:fog`, `dropped:cooldown` (the 1500 ms wound throttle, the hero
cooldowns) and `dropped:missing` (a null table slot or a missing file: the exe plays nothing).  Loops report `played`, `updated`, `stopped`."""

from engine.rng import Rng

from . import events as ev
from .ambience import Ambience
from .mix import UI_PRIORITY, Mix, View, flat, positional, volume_mb
from .mixer import LOOP, Played, VoiceMixer
from .music import MusicState
from .settings import Settings
from .voices import COMMAND_VOICE, Voices, voice_path

HURT_THROTTLE_MS = 1500             # `FUN_00467e42`: kinds 1 and 2 per unit (`view+0x1bc`)
SEEN = 0x4000                       # fog tile bit: in sight now (docs/engine/vision.md)
SKILLUP_PRIORITY = 100              # `0x40e689`: flat, priority 100
UNIT_KINDS = (ev.SWING, ev.CAST, ev.HURT, ev.DEATH)      # sounds of unit view objects: fog gated (audio.md 3.4)
CELL_PX = 32


def replay_ms(tick, rate):
    """Virtual clock of a replay: the tick's time in ms at `rate` ticks per second."""
    return tick * 1000 // rate


def view_of(camera):
    """`View` (cells) of a camera object (`x`, `y` px, `view_w`, `view_h` px; 32 px per cell, size floored)."""
    return View(int(camera.x) // CELL_PX, int(camera.y) // CELL_PX, max(1, camera.view_w // CELL_PX), max(1, camera.view_h // CELL_PX))


class Director:
    def __init__(self, table=None, banks=None, duration_ms=None, settings=None, seed=1, log=None, viewer=1, mixer=None):
        self.table, self.banks = table, banks or {}
        self.duration_ms = duration_ms or (lambda path: 1000)
        self.settings = settings or Settings()
        self.rng = Rng(seed)                        # the audio layer's own stream: never `World.rng`
        self.mixer = mixer or VoiceMixer()
        self.voices = Voices(self.banks, self.rng)
        self.music = MusicState(self.rng, self.settings.music_enabled)
        self.ambience = Ambience(self.rng, getattr(table, "ids", None))
        self.log, self.viewer = log, viewer
        self.hurt_stamp = {}
        self.loops = {}                             # ambience name -> channel of the running loop
        self.now = 0

    # -- resolution -------------------------------------------------------
    def path_of(self, sound):
        if isinstance(sound, str):
            return sound                                # a literal game path (the shell's `SFX\\ChrGen\\Ok.wav`)
        if isinstance(sound, tuple):
            return voice_path(sound)
        return self.table.path(sound) if self.table is not None else None

    def _row(self, tick, source, event, uid, sound, path, x, y, p):
        if self.log is not None:
            self.log.row(tick, self.now, source, event, uid, sound, path or "", x, y, p.volume, p.pan, p.priority, p.channel, p.result)

    def _play(self, tick, source, event, uid, sound, bus, mix, x=0, y=0, loop=False):
        path = self.path_of(sound)
        vol = volume_mb(mix.att, self.settings.bus_mb(bus))
        dur = self.duration_ms(path) if path else None
        if dur is None:
            p = Played(self.now, sound, mix.priority, vol, mix.pan, -1, "dropped:missing", loop)
        else:
            p = self.mixer.play(self.now, sound, LOOP if loop else dur, mix.priority, vol, mix.pan)
        self._row(tick, source, event, uid, sound, path, x, y, p)
        return p

    def _drop(self, tick, source, event, e, reason):
        p = Played(self.now, e.sound, 0, 0, 0, -1, reason)
        self._row(tick, source, event, e.uid, e.sound, self.path_of(e.sound), e.x, e.y, p)
        return p

    # -- sim events -------------------------------------------------------
    def _seen(self, world, e):
        """Audio.md 3.4 (INFERRED): a unit event of another player's unit plays only on a cell in sight; the viewer's own units are always seen."""
        fog = getattr(world, "fog", None)
        if fog is None or e.owner == self.viewer:
            return True
        x, y = e.x >> 8, e.y >> 8
        return not (0 <= y < fog.shape[0] and 0 <= x < fog.shape[1]) or bool(fog[y, x] & SEEN)

    def event(self, e, world, view):
        """One `SoundEvent` -> a `Played`."""
        if e.kind in UNIT_KINDS and not self._seen(world, e):
            return self._drop(e.tick, "sim", e.kind, e, "dropped:fog")
        if e.kind == ev.SKILLUP:
            if e.owner != self.viewer:
                return None
            return self._play(e.tick, "sim", e.kind, e.uid, e.sound, e.bus, flat(SKILLUP_PRIORITY))
        if e.kind == ev.HURT and e.k in (1, 2):
            if self.now - self.hurt_stamp.get(e.uid, -(1 << 31)) < HURT_THROTTLE_MS:
                return self._drop(e.tick, "sim", e.kind, e, "dropped:cooldown")
            self.hurt_stamp[e.uid] = self.now
        return self._play(e.tick, "sim", e.kind, e.uid, e.sound, e.bus, positional(e.x, e.y, view), e.x, e.y)

    def drain(self, world, view):
        out = []
        for e in world.sound_events:
            p = self.event(e, world, view)
            if p is not None:
                out.append(p)
        del world.sound_events[:]
        return out

    # -- commands (order / select voices) ---------------------------------
    def command(self, cmd, world, view, skip=False):
        """`FUN_0041da16` for a command of the viewing player (AI commands and other players' commands are silent)."""
        name = type(cmd).__name__
        if name not in COMMAND_VOICE or getattr(cmd, "ai", False) or getattr(cmd, "player_id", None) != self.viewer:
            return None
        units = [u for u in (world.units.get(i) for i in getattr(cmd, "unit_ids", ())) if u is not None]
        u, sound, res = self.voices.voice(name, units, self.now, skip)
        if sound is None:
            if res == "dropped:cooldown":
                p = Played(self.now, None, 0, 0, 0, -1, res)
                self._row(world.tick, "cmd", name, u.uid, None, "", 0, 0, p)
                return p
            return None
        X, Y = u.x * 256 + u.sub_x, u.y * 256 + u.sub_y
        return self._play(world.tick, "cmd", name, u.uid, sound, ev.SPEECH, positional(X, Y, view), X, Y)

    # -- UI ---------------------------------------------------------------
    def ui(self, sound_id, priority=UI_PRIORITY, tick=0, now_ms=None):
        """A flat UI sound (table id, priority `0xdc` unless given; the message line uses 100)."""
        if now_ms is not None:
            self.now = now_ms
        return self._play(tick, "ui", "ui", 0, sound_id, ev.SFX, flat(priority))

    # -- ambience ---------------------------------------------------------
    def ambient(self, world, view, clock=None):
        """The ambience pass (`FUN_0041b311`): loops start / update / stop, one-shots play."""
        out = []
        clock = world.tick if clock is None else clock
        for a in self.ambience.update(self.now, world, view, clock):
            ch = self.loops.get(a.name)
            if a.action == "stop":
                if ch is not None:
                    self.mixer.stop(ch)
                    del self.loops[a.name]
                    out.append(Played(self.now, a.sound, 0, 0, 0, ch, "stopped", True))
            elif a.action == "loop":
                vol = volume_mb(a.att, self.settings.bus_mb(ev.SFX))
                if ch is not None and self.mixer.busy[ch] and self.mixer.snd[ch] == a.sound:
                    out.append(Played(self.now, a.sound, self.mixer.prio[ch], vol, a.pan, ch, "updated", True))
                else:
                    p = self._play(world.tick, "amb", a.name, 0, a.sound, ev.SFX, Mix(a.att, a.pan, (10000 - abs(a.att)) // 100), loop=True)
                    if p.audible:
                        self.loops[a.name] = p.channel
                    out.append(p)
            else:
                out.append(self._play(world.tick, "amb", a.name, 0, a.sound, ev.SFX, Mix(0, a.pan, 100)))
        return out

    def stop_ambient(self):
        """Mission teardown (`0x41bddd`)."""
        for ch in self.loops.values():
            self.mixer.stop(ch)
        self.loops.clear()
        self.ambience.cell, self.ambience.next = None, 0

    # -- one frame ----------------------------------------------------------
    def frame(self, now_ms, world, view, commands=(), ambient=False, skip_voice=False):
        """Everything of one frame at `now_ms`: the drained sim events, the viewer's order voices, optionally the ambience pass."""
        self.now = now_ms
        out = self.drain(world, view)
        for c in commands:
            p = self.command(c, world, view, skip_voice)
            if p is not None:
                out.append(p)
        if ambient:
            out += self.ambient(world, view)
        return out
