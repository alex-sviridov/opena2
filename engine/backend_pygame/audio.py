"""Audio backend (docs/engine/audio.md 5, 9): the pygame.mixer output of the pure `engine.audio` layer.

`NullAudio` runs the whole model (Director, VoiceMixer, MusicState) with no device: tests, `replay --audio-log`.  `Audio` adds the output: sounds decoded
once by `allods2.formats.sound.to_wav` into cached `mixer.Sound`s played on the channel the model chose, `MusicPlayer` streaming the music wavs through
`pygame.mixer.music`.  A missing file, a failing decode or no device is silence, never an error (the exe's behaviour).  pygame is imported lazily: a
`NullAudio` needs no pygame at all."""

import io
import struct

from allods2.formats import sound as snd
from allods2.formats import soundtable
from engine.audio import mix
from engine.audio.audiolog import AudioLog  # noqa: F401  (re-export for the callers that build the log)
from engine.audio.director import Director, view_of
from engine.audio.mixer import VOICES
from engine.audio.settings import Settings
from engine.sim.clock import DEFAULT_SPEED, tick_period_ms

FREQUENCY, FORMAT, CHANNELS, BUFFER = 22050, -16, 2, 512          # `mixer.init` (audio.md 5)
MUSIC_PX_SCALE = 8                                                 # px -> 1/256 cell (32 px per cell)
MIN_VIEW_PX = 32


def wav_duration_ms(data):
    """Length of a RIFF wav in ms from its headers (PCM: data / frame size; MS ADPCM: the `fact` frame count); None for a file with no samples or no
    readable header."""
    try:
        b = bytes(data)
        by = {}
        for t, o, s in snd.parse_chunks(b):
            by.setdefault(t, (o, s))
        o, _ = by[b"fmt "]
        tag, channels, rate, _bps, align, _bits = struct.unpack_from("<HHIIHH", b, o)
        if b"fact" in by:
            frames = struct.unpack_from("<I", b, by[b"fact"][0])[0]
        elif tag == snd.WAVE_PCM and align:
            frames = by[b"data"][1] // align
        else:
            frames = snd.decode(b).frames
        ms = frames * 1000 // rate if rate else 0
        return ms if ms > 0 else None
    except (KeyError, ValueError, struct.error, snd.SoundError):
        return None


class NullAudio:
    """The model with no device.  `fs`: the game file system, `settings`: `engine.audio.settings.Settings`, `log`: an `AudioLog` or None.  `decisions` collects the
    music decisions (what a device would have been asked to play)."""

    def __init__(self, fs, settings=None, seed=1, log=None, viewer=1):
        self.fs = fs
        self.settings = settings or Settings()
        try:
            table = soundtable.load(fs)
        except (OSError, KeyError, ValueError):
            table = None
        try:
            banks = soundtable.hero_banks(fs)
        except (OSError, KeyError, ValueError):
            banks = {}
        self._dur = {}
        self.director = Director(table, banks, self.duration_ms, self.settings, seed, log, viewer)
        self.decisions = []
        self._music_tick = None

    # -- files ------------------------------------------------------------
    def duration_ms(self, path):
        """Decoded length of a game wav in ms; None = nothing to play (a missing or empty file)."""
        if path not in self._dur:
            try:
                self._dur[path] = wav_duration_ms(self.fs.read(path)) if self.fs.exists(path) else None
            except (OSError, KeyError, ValueError):
                self._dur[path] = None
        return self._dur[path]

    # -- per frame --------------------------------------------------------
    def frame(self, now_ms, world, camera, commands=(), ui_sounds=()):
        """One frame: the drained sim events, the order voices of `commands`, the ambience pass, the UI sounds `[(id, priority)]` and the music ticks (every
        16 ticks, with the camera centre) since the previous frame."""
        plays = self.director.frame(now_ms, world, view_of(camera), commands, ambient=True)
        for sid, prio in ui_sounds:
            plays.append(self.director.ui(sid, prio, world.tick, now_ms))
        self._music_ticks(world.tick, camera)
        self._output(plays)
        return plays

    def _music_ticks(self, tick, camera):
        m = self.director.music
        last = self._music_tick if self._music_tick is not None else tick - 1
        if tick - last > 64:
            last = tick - 64
        xy = ((camera.x + camera.view_w / 2) * MUSIC_PX_SCALE, (camera.y + camera.view_h / 2) * MUSIC_PX_SCALE)
        for t in range(last + 1, tick + 1):
            m.tick(t, xy)
        self._music_tick = tick

    def ui(self, sound_id, priority=mix.UI_PRIORITY, now_ms=None, tick=0):
        p = self.director.ui(sound_id, priority, tick, now_ms)
        self._output([p])
        return p

    # -- music ------------------------------------------------------------
    @staticmethod
    def zone_list(zones):
        """`Map.music()` zones -> the state's `(x, y, radius, themes)` in 1/256 cell."""
        return [(z.x << 8, z.y << 8, z.radius << 8, tuple(z.themes)) for z in zones]

    def start_mission(self, zones=(), camera=None):
        xy = None if camera is None else ((camera.x + camera.view_w / 2) * MUSIC_PX_SCALE, (camera.y + camera.view_h / 2) * MUSIC_PX_SCALE)
        self._decide(self.director.music.start_mission(self.zone_list(zones), xy))

    def set_playlist(self, name):
        self._decide(self.director.music.set_playlist(name))

    def stop_music(self):
        self._decide(self.director.music.stop())

    def set_music_enabled(self, on):
        self._decide(self.director.music.set_enabled(on))

    def _decide(self, decision):
        if decision is not None:
            self.decisions.append(decision)
            self._music(decision)

    def _music(self, decision):
        pass

    def _output(self, plays):
        pass

    def handle_event(self, ev):
        """A pygame event of the window loop (the music end); the null device has none."""
        return False

    def close(self):
        self.director.mixer.stop_all()


class MusicPlayer:
    """Streams the playlist's wavs through `pygame.mixer.music` (PCM stereo, no decode).  `state` = the `MusicState`; the end event (`handle_event`) asks it
    for the next track (`track_ended`), a `Decision` is applied by `apply`.  `fs` reads the game path into memory (a `BytesIO` of the `.res` bytes)."""

    def __init__(self, fs, state, settings):
        import pygame
        self.pg = pygame
        self.fs, self.state, self.settings = fs, state, settings
        self.end_event = pygame.event.custom_type() if hasattr(pygame.event, "custom_type") else pygame.USEREVENT + 1
        self.current = None                        # game path of the track being streamed
        self.opened = []                           # every path started (tests, debugging)
        pygame.mixer.music.set_endevent(self.end_event)
        self.set_volume()

    def gain(self):
        return 0.0 if self.settings.mute else mix.gain(self.settings.bus_mb("music"))

    def set_volume(self):
        self.pg.mixer.music.set_volume(self.gain())

    def apply(self, d):
        m = self.pg.mixer.music
        if d is None:
            return
        if d.action == "stop":
            self.current = None
            m.stop()
        elif d.action == "fade":
            self.current = None
            m.fadeout(d.fade_ms)
        elif d.action == "play":
            self._open(d.path)

    def _open(self, path):
        m = self.pg.mixer.music
        self.current = None
        if self.settings.mute:
            m.stop()
            return
        try:
            data = bytes(self.fs.read(path))
            m.load(io.BytesIO(data), "wav")
            self.set_volume()
            m.play()
        except (self.pg.error, OSError, KeyError, ValueError):
            m.stop()                                # a missing file or no device: silence
            return
        self.current = path
        self.opened.append(path)

    def handle_event(self, ev):
        """A pygame event; True when it was the end of the current track (the next one is started)."""
        if ev.type != self.end_event:
            return False
        return self.track_ended()

    def track_ended(self):
        if self.current is None or self.pg.mixer.music.get_busy():
            return False                            # a stop / fade / a track already restarted: a stale event
        self.current = None
        self.apply(self.state.track_ended())
        return True


class Audio(NullAudio):
    """`NullAudio` + the device.  `Audio.ok` is False when the mixer would not open (SDL has no audio device): everything then stays silent."""

    def __init__(self, fs, settings=None, seed=1, log=None, viewer=1):
        super().__init__(fs, settings, seed, log, viewer)
        self.ok = False
        self.music = None
        self._sounds = {}
        try:
            import pygame
            self.pg = pygame
            if pygame.mixer.get_init():
                pygame.mixer.quit()
            pygame.mixer.init(FREQUENCY, FORMAT, CHANNELS, BUFFER)
            pygame.mixer.set_num_channels(VOICES)
            self.ok = True
            self.music = MusicPlayer(fs, self.director.music, self.settings)
        except Exception:           # noqa: BLE001  pygame.error, a missing driver, ImportError: no device = silent
            self.ok = False

    def sound_of(self, path):
        """The cached `mixer.Sound` of a game wav (decoded through `Sound.to_wav`), None when it cannot be made."""
        if path not in self._sounds:
            s = None
            try:
                s = self.pg.mixer.Sound(file=io.BytesIO(snd.load(bytes(self.fs.read(path))).to_wav()))
            except Exception:       # noqa: BLE001
                s = None
            self._sounds[path] = s
        return self._sounds[path]

    def _output(self, plays):
        if not self.ok or self.settings.mute:
            return
        for p in plays:
            if p.channel < 0:
                continue
            ch = self.pg.mixer.Channel(p.channel)
            if p.result == "stopped":
                ch.stop()
            elif p.result == "updated":
                ch.set_volume(*mix.pan_gains(p.volume, p.pan))
            elif p.audible:
                path = self.director.path_of(p.sound)
                s = self.sound_of(path) if path else None
                if s is None:
                    continue
                ch.set_volume(*mix.pan_gains(p.volume, p.pan))
                ch.play(s, loops=-1 if p.loop else 0)

    def _music(self, decision):
        if self.ok and self.music is not None:
            self.music.apply(decision)

    def handle_event(self, ev):
        return self.music is not None and self.music.handle_event(ev)

    def busy_channels(self):
        return [i for i in range(VOICES) if self.ok and self.pg.mixer.Channel(i).get_busy()]

    def close(self):
        super().close()
        if self.ok:
            self.pg.mixer.stop()
            self.pg.mixer.music.stop()
            self.pg.mixer.quit()
            self.ok = False


def replay_rate(speed=DEFAULT_SPEED):
    """Ticks per second of the replay clock (the default speed: the journal has no speed)."""
    return max(1, round(1000 / tick_period_ms(speed)))
