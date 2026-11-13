"""Settings file (docs/engine/audio.md 6, docs/engine/shell.md 5): the volumes of K11 and the game options the shell's options screens edit (the exe keeps
them in the registry, written at exit `0x440cd2`).  `~/.config/allods2-engine/settings.json` (`$XDG_CONFIG_HOME`; `ALLODS2_SETTINGS` overrides), never in the
repo.  No pygame."""

import json
import os
import tempfile
from dataclasses import asdict, dataclass

from .mix import mb_to_percent, percent_to_mb

DEFAULT_PERCENT = 74            # about the exe's -700 mB default (`percent_to_mb(74)` = -676)
ENV = "ALLODS2_SETTINGS"
BOOLS = ("mute", "music_enabled", "day_night", "smoothing", "shadows", "lighting", "animation", "show_health", "flying_damage", "tips", "message_colours")
RANGES = {"formation": 2, "retreat": 2, "autocasting": 0x3F}       # the party options: formation 0 off / 1 auto / 2 on, retreat mode 0 never / 1 low / 2 medium, the auto-cast byte


@dataclass
class Settings:
    sfx: int = DEFAULT_PERCENT
    speech: int = DEFAULT_PERCENT
    music: int = DEFAULT_PERCENT
    mute: bool = False
    music_enabled: bool = True
    game_speed: int = 4                 # `game+0x41c`, 0..8, default 4 (CONFIRMED `0x48bfaa`, ctor `0x4822c5`)
    day_night: bool = True              # ShowTimeFlow `0x622770` (default 1)
    smoothing: bool = True              # `0x622768`
    shadows: bool = True                # `0x5f17e8`
    lighting: bool = True               # `0x5f17f0`
    animation: bool = True              # `0x5f17ec`: off forces lighting off (`0x442fb7`)
    show_health: bool = False           # ShowAllHitPoints (client `+0xab8`)
    flying_damage: bool = True          # ShowFlyingHP (client `+0xabc`)
    tips: bool = True                   # TipsMode `0x622774` (default 1); stored, nothing reads it until the tips windows are built (shell.md 5.3)
    message_colours: bool = False       # MessageColors `0x622818` (the Game Options check "Join", Ctrl+C): the alternative colour tables are not built
    formation: int = 1                  # Formation Mode `0x62275c`: 0 off, 1 auto (default, CONFIRMED ctor `0x402db0` view+0xab0), 2 on
    retreat: int = 0                    # Retreat Mode `0x622760`: 0 never (default, CONFIRMED client ctor `0x402db0` view+0xab4), 1 low health, 2 medium
    autocasting: int = 0x19             # AutoCasting `0x62277c`, default 0x19 (CONFIRMED): 8 heal, 0x10 / 0x20 buff levels, 1 / 2 / 4 own / allies / neutral

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
    v = d.get("game_speed")
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        s.game_speed = max(0, min(8, int(v)))
    for k in BOOLS:
        if isinstance(d.get(k), bool):
            setattr(s, k, d[k])
    for k, hi in RANGES.items():
        v = d.get(k)
        if isinstance(v, int) and not isinstance(v, bool):
            setattr(s, k, max(0, min(hi, v)))
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
