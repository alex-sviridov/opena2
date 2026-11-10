"""`SoundEvent`: what the simulation says should be heard (docs/engine/audio.md 5).  The sim fills `World.sound_events`; the audio layer decides everything else.

Pure data, no imports: the sim, the view and the audio layer all use it.
"""

from dataclasses import dataclass

# kinds (audio.md 5)
SWING, CAST, SPELL, BLIZZARD, HURT, DEATH, SKILLUP = "swing", "cast", "spell", "blizzard", "hurt", "death", "skillup"
KINDS = (SWING, CAST, SPELL, BLIZZARD, HURT, DEATH, SKILLUP)
SFX, SPEECH = "sfx", "speech"           # the two buses an event can name (music is the player's own)
SPELL_BASE = 500                        # sfx.reg id of a spell sound = 500 + spell / projectile id (`0x467da8`, `0x4151b7`)
MESSAGE_SOUND = 15                      # sfx.reg `message`: the skill-up sound (`0x40e689`)


@dataclass(frozen=True)
class SoundEvent:
    """One sound request.  `x`, `y` = position in 1/256 cell; `sound` = an `sfx.reg` id (int) or `("hero", bank, slot)` (a voice file
    `sfx/characters/<bank>/<slot>.wav`); `hero` = the sound is a hero / class voice; `k` = the hurt kind 0 (blow without HP change), 1 easy, 2 hard;
    `owner` = the player id of the unit (0 for object sounds)."""
    tick: int
    kind: str
    uid: int
    x: int
    y: int
    sound: object
    bus: str = SFX
    hero: bool = False
    k: int = 0
    owner: int = 0


def hurt_kind(old_hp, new_hp, hp_max):
    """The wound kind after message `0x73` (`0x412a58`-`0x412ade`, CONFIRMED K11 REA): 0 when the HP did not change; else decided by the view's **old** HP
    (still in `view+0x104` until `0x412ace` overwrites it): None when it is -10 or less, 2 below half of the maximum (`hp_max / 2` truncating), else 1;
    any change counts, a heal too.  The new HP only decides the unchanged case."""
    if new_hp == old_hp:
        return 0
    if old_hp <= -10:
        return None
    return 2 if old_hp < int(hp_max / 2) else 1
