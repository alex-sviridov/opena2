"""Audio settings file (docs/engine/audio.md 6).  `~/.config/allods2-engine/settings.json` (`$XDG_CONFIG_HOME`; `ALLODS2_SETTINGS` overrides), never in the repo.
No pygame."""

import json
import os
import tempfile
from dataclasses import asdict, dataclass

from .mix import mb_to_percent, percent_to_mb

DEFAULT_PERCENT = 74            # about the exe's -700 mB default (`percent_to_mb(74)` = -676)
ENV = "ALLODS2_SETTINGS"


@dataclass
class Settings:
    sfx: int = DEFAULT_PERCENT
    speech: int = DEFAULT_PERCENT
    music: int = DEFAULT_PERCENT
    mute: bool = False
    music_enabled: bool = True

    def bus_mb(self, bus):
        """mB offset of a bus (`sfx`, `speech`, `music`)."""
        return percent_to_mb(getattr(self, bus))

    def override(self, mute=None, sfx=None, music=None, speech=None):
        """A copy with the command-line overrides of a run (`--mute`, `--sfx-volume`, ...); None keeps the stored value."""
        s = Settings(**asdict(self))
        for k, v in (("mute", mute), ("sfx", sfx), ("music", music), ("speech", speech)):
            if v is not None:
                setattr(s, k, v)
        return s


def path(env=None):
    env = os.environ if env is None else env
    if env.get(ENV):
        return env[ENV]
    base = env.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "allods2-engine", "settings.json")


def _clean(d):
    """Valid fields only: volumes clamp to 0..100, bools coerce; anything else keeps the default."""
    s = Settings()
    for k in ("sfx", "speech", "music"):
        v = d.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            setattr(s, k, max(0, min(100, int(v))))
    for k in ("mute", "music_enabled"):
        if isinstance(d.get(k), bool):
            setattr(s, k, d[k])
    return s


def load(p=None):
    """The stored settings; a missing or unreadable file = defaults."""
    try:
        with open(p or path(), encoding="utf-8") as f:
            d = json.load(f)
        return _clean(d) if isinstance(d, dict) else Settings()
    except (OSError, ValueError):
        return Settings()


def save(s, p=None):
    """Atomic write (temp file in the same folder + rename); returns False when the folder is not writable."""
    p = p or path()
    try:
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p) or ".", prefix=".settings-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(asdict(s), f, indent=1, sort_keys=True)
            f.write("\n")
        os.replace(tmp, p)
        return True
    except OSError:
        return False


__all__ = ["Settings", "load", "save", "path", "percent_to_mb", "mb_to_percent"]
