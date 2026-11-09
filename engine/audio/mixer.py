"""The exe's voice allocation as a model (docs/engine/audio.md 3.1; CONFIRMED `0x45aa2f`, `0x45ab9c`): 16 global voices, 16 duplicate buffers per sound,
strict priority stealing.  Deterministic and device-free: time is an explicit millisecond clock and the caller says how long a play lasts (the decoded
length), so overlap is modelled without a device.  The backend plays on the channel the model returns."""

from dataclasses import dataclass

VOICES = 16                     # table `0x61f63c`
DUPLICATES = 16                 # `DuplicateSoundBuffer` copies per sound (`0x45a3f4`)
LOOP = None                     # `duration` of a looping play: until `stop`


@dataclass
class Played:
    """One request and its fate.  `result`: `played`, `stolen:<channel>` (played, a lower-priority voice was cut), `dropped:busy` (all 16
    duplicates of the sound are playing), `dropped:voices` (no voice free, none of lower priority); the Director adds `dropped:fog` / `dropped:cooldown`."""
    now: int
    sound: object
    priority: int
    volume: int                 # mB after the bus value, clamped
    pan: int
    channel: int                # -1 when dropped
    result: str
    loop: bool = False

    @property
    def audible(self):
        return self.result == "played" or self.result.startswith("stolen")


class VoiceMixer:
    """`play(now, sound, duration_ms, priority, volume, pan)` -> `Played`.  A voice is busy while `now < end`.  Free voice = lowest free index;
    otherwise the voice of the lowest priority (ties: the lowest index, INFERRED) is stolen if its priority is strictly lower than the new one."""

    def __init__(self, voices=VOICES, duplicates=DUPLICATES):
        self.n, self.dups = voices, duplicates
        self.end = [0] * voices             # ms at which the voice is free again (None = loop)
        self.prio = [0] * voices
        self.snd = [None] * voices
        self.busy = [False] * voices        # voice holds a sound (until its end passes or `stop`)
        self.drops = 0
        self.history = []

    def _active(self, i, now):
        if not self.busy[i]:
            return False
        e = self.end[i]
        return e is None or now < e

    def playing(self, now):
        """[(channel, sound, priority)] of the voices busy at `now`."""
        return [(i, self.snd[i], self.prio[i]) for i in range(self.n) if self._active(i, now)]

    def play(self, now, sound, duration_ms, priority, volume=0, pan=0):
        loop = duration_ms is LOOP
        act = [i for i in range(self.n) if self._active(i, now)]
        if sum(1 for i in act if self.snd[i] == sound) >= self.dups:
            return self._rec(Played(now, sound, priority, volume, pan, -1, "dropped:busy", loop))
        free = [i for i in range(self.n) if i not in act]
        result = "played"
        if free:
            ch = free[0]
        else:
            ch = min(act, key=lambda i: (self.prio[i], i))
            if self.prio[ch] >= priority:
                return self._rec(Played(now, sound, priority, volume, pan, -1, "dropped:voices", loop))
            result = "stolen:%d" % ch
        self.busy[ch], self.prio[ch], self.snd[ch] = True, priority, sound
        self.end[ch] = None if loop else now + max(0, int(duration_ms))
        return self._rec(Played(now, sound, priority, volume, pan, ch, result, loop))

    def stop(self, channel):
        self.busy[channel] = False

    def stop_all(self):
        self.busy = [False] * self.n

    def _rec(self, p):
        if not p.audible:
            self.drops += 1
        self.history.append(p)
        if len(self.history) > 4096:
            del self.history[:2048]
        return p
