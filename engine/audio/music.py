"""The music playlist state machine (docs/engine/audio.md 4.1, formats/sound.md 5; CONFIRMED `0x459a5f`, `0x4754e9`, `0x459067`, `0x4924cd`).  Pure: it
returns decisions, the backend streams the files.  Draws come from the audio layer's own `Rng`."""

import math
from dataclasses import dataclass

from allods2.formats.soundtable import MUSIC_SCREENS, PLAYLIST_MISSION

ZONE_PERIOD = 16                # `0x40bd8b`: `(tick & 15) == 0`
FADE_MS = 2000                  # music off: `0x459d68(2000, 8000)`


@dataclass(frozen=True)
class Decision:
    """`action`: `play` (open `path` now; `gapless` = at a track end), `stop` (hard), `fade` (stop over `fade_ms`)."""
    action: str
    path: str = ""
    index: int = -1
    gapless: bool = False
    fade_ms: int = 0


def nearest_theme(zones, x, y, rng):
    """`0x4754e9`: the nearest zone `(cx, cy, radius, themes)` (units of 1/256 cell) whose distance is below its radius, then `rand` rolls among its 4 theme
    slots until one is not -1 (`rand(3)` = 0..3, INFERRED inclusive like every `FUN_0051fa25`).  Zones at (0, 0) or with four -1 are skipped.  None when no
    zone matches (nothing is written)."""
    best, bd = None, None
    for cx, cy, r, themes in zones:
        if (cx == 0 and cy == 0) or all(t == -1 for t in themes):
            continue
        d = math.hypot(cx - x, cy - y)
        if d < r and (bd is None or d < bd):
            best, bd = themes, d
    if best is None:
        return None
    while True:
        t = best[rng.rand(3)]
        if t != -1:
            return t


class MusicState:
    """One playlist player (`0x459acd` object): `set_playlist` / `start_mission` start a playlist at a random track, `track_ended` goes on, `tick` rolls the zone
    theme in a mission.  A disabled state (`MusicEnabled` 0 / `-nomusic`) never plays; `set_enabled` fades out / restarts the current playlist."""

    def __init__(self, rng, enabled=True):
        self.rng, self.enabled = rng, enabled
        self.playlist, self.index, self.theme, self.zones = (), -1, -1, ()
        self.mission = False
        self.playing = False

    # -- starts ---------------------------------------------------------
    def _open(self, i, gapless=False):
        self.index = i
        if not self.enabled:
            self.playing = False
            return None
        self.playing = True
        return Decision("play", self.playlist[i], i, gapless)

    def _start(self, playlist):
        """`0x459a5f`: store, theme := -1, `rand() % count`, play (only when enabled, `0x459ec5`)."""
        self.playlist, self.theme = tuple(playlist), -1
        return self._open(self.rng.rand15() % len(self.playlist))

    def set_playlist(self, name):
        """A screen playlist: `menu`, `map`, `chrgen`, `credit`, `town` (the exe repeats a one-track list through `(i + 1) % n`)."""
        self.mission, self.zones = False, ()
        p = MUSIC_SCREENS[name]
        return self._start((p,) if isinstance(p, str) else p)

    def start_mission(self, zones=(), view_xy=None):
        """Mission start (`0x4924cd`): all 17 tracks, random start; a zone theme >= 0 at the view switches at once (`0x492688`, `0x4926a9`)."""
        self.mission, self.zones = True, tuple(zones)
        d = self._start(PLAYLIST_MISSION)
        if view_xy is not None:
            t = nearest_theme(self.zones, view_xy[0], view_xy[1], self.rng)
            if t is not None:
                self.theme = t
            if self.theme >= 0:
                return self._open(self.theme)
        return d

    # -- running --------------------------------------------------------
    def tick(self, tick, view_xy):
        """Every 16 ticks in a mission: roll the zone theme and store it (the current track is not interrupted); outside all zones nothing is written."""
        if self.mission and tick & (ZONE_PERIOD - 1) == 0:
            t = nearest_theme(self.zones, view_xy[0], view_xy[1], self.rng)
            if t is not None:
                self.theme = t
        return None

    def track_ended(self):
        """`0x459067` / `0x459198`: the stored theme (>= 0, never cleared) opens gaplessly, else the next track (wraps)."""
        if not self.playlist:
            return None
        if self.theme >= 0:
            return self._open(self.theme, True)
        return self._open((self.index + 1) % len(self.playlist))

    def stop(self):
        """Hard stop (victory `0x48da92`, quit to menu `0x459f2f`)."""
        self.playing, self.mission, self.zones, self.playlist, self.index, self.theme = False, False, (), (), -1, -1
        return Decision("stop")

    def set_enabled(self, on):
        """Options music off (`0x478`): fade 2000 ms when playing; on (`0x477`): start the current playlist."""
        was, self.enabled = self.enabled, bool(on)
        if was and not self.enabled:
            if self.playing:
                self.playing = False
                return Decision("fade", fade_ms=FADE_MS)
            return None
        if not was and self.enabled and self.playlist:
            return self._open(self.index if self.index >= 0 else 0)
        return None
