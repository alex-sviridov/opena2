"""Rectangle picking of drawn units (docs/engine/ui-layout.md section 7).  No pygame here."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PickRect:
    entity: int
    x1: int
    y1: int
    x2: int
    y2: int


def pick_at(picks, x, y):
    """Entity of the last pick whose rect meets the box (x-1, y-1, x+1, y+1), or None
    (FUN_004180c6: IntersectRect is non-empty when max(left) < min(right), likewise for y)."""
    for r in reversed(picks):
        if max(r.x1, x - 1) < min(r.x2, x + 1) and max(r.y1, y - 1) < min(r.y2, y + 1):
            return r.entity
    return None


def pick_in_rect(picks, rect, min_area=11):
    """Entities (draw order) whose rect overlaps `rect` (x1, y1, x2, y2) by at least `min_area` px^2."""
    x1, y1, x2, y2 = rect
    out = []
    for r in picks:
        w = min(r.x2, x2) - max(r.x1, x1)
        h = min(r.y2, y2) - max(r.y1, y1)
        if w > 0 and h > 0 and w * h >= min_area:
            out.append(r.entity)
    return out
