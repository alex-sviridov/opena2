"""Debug flags: UI state only (never a sim command).  F1/F2/F3 toggle them in the
backend event loop; the view turns them into overlay items."""

from dataclasses import dataclass

NAMES = ("passability", "markers", "depth", "paths", "combat", "ai")


@dataclass
class DebugFlags:
    passability: bool = False       # tint of blocked cells (walker mask 0x41)
    markers: bool = False           # footprint cell outlines + hotspot crosses
    depth: bool = False             # the draw-order key as text
    paths: bool = False             # selected units: cells the last plans searched, static path, current hop
    combat: bool = False            # one log line per blow on the console (tick, attacker, target, roll, damage, HP)
    ai: bool = False                # selected monsters: sight (aggro area), pool radius ring, post, target, mode label

    def toggle(self, name):
        if name not in NAMES:
            raise ValueError("unknown debug flag %r" % (name,))
        setattr(self, name, not getattr(self, name))

    @classmethod
    def parse(cls, text):
        """From a comma list such as "passability,depth" (CLI --debug); ValueError on unknown names."""
        flags = cls()
        for name in filter(None, (t.strip() for t in (text or "").split(","))):
            if name not in NAMES:
                raise ValueError("unknown debug flag %r (choose from %s)" % (name, ", ".join(NAMES)))
            setattr(flags, name, True)
        return flags

    def any(self):
        return self.passability or self.markers or self.depth or self.paths or self.combat or self.ai
