"""Sound events of the simulation (docs/engine/audio.md 2, 5): `World.sound_events` gets a `SoundEvent` where the original's client plays a sound.  Not part of
`dump()` / the hash; **no random draw** (every sim-side sound has one candidate: variants belong to the audio layer).  Layer 4: reads `engine.world` and the unit
data of `world.assets` (units.reg `Sound`: attack, blow, easy, hard, dead); a world without assets (synthetic tests) emits nothing for unit slots."""

from engine.audio import events as ev
from engine.audio.events import SoundEvent, hurt_kind
from engine.audio.voices import bank_of, is_voice_hero

ATTACK, BLOW, EASY, HARD, DEAD = range(5)       # units.reg `Sound` list order (soundtable.SLOTS)
FLASH_BASE = ev.SPELL_BASE


def unit_slot(world, u, i):
    """sfx.reg id of slot `i` of the unit type's `Sound` list, 0 when the slot is empty or unknown."""
    sets = world.sound_sets
    snd = sets.get(u.type_id)
    if snd is None:
        types = world.assets.unit_types() if world.assets is not None else {}
        t = types.get(u.type_id)
        snd = sets[u.type_id] = tuple(t.values.get("Sound") or ()) if t is not None else ()
    return snd[i] if i < len(snd) and snd[i] > 0 else 0


def pos(u):
    return u.x * 256 + u.sub_x, u.y * 256 + u.sub_y


def emit(world, kind, uid, x, y, sound, bus=ev.SFX, hero=False, k=0, owner=0):
    world.sound_events.append(SoundEvent(world.tick, kind, uid, x, y, sound, bus, hero, k, owner))


def swing(world, u):
    """The swing or shot lands (animate modes 3 and 7 at the hit frame, `0x46617c` -> `0x467cd2`): the attacker's slot [attack]; a bow's sound is this slot too."""
    s = unit_slot(world, u, ATTACK)
    if s:
        emit(world, ev.SWING, u.id, *pos(u), s, owner=u.owner)


def cast(world, u, spell):
    """The cast frame (`0x467da8`): `sfx[500 + spell]`; the id is emitted whatever the table holds (the player skips null slots)."""
    emit(world, ev.CAST, u.id, *pos(u), ev.SPELL_BASE + spell, owner=u.owner)


def spell_object(world, x, y, projectile, uid=0):
    """A spell object is made by a cast message (`0x86` / `0x8b` / `0x8c`, `0x4151b7`...): `sfx[500 + projectile id]` at the object, not for id 23."""
    if projectile != 23:
        emit(world, ev.SPELL, uid, x, y, ev.SPELL_BASE + projectile)


def blizzard(world, x, y):
    """The Blizzard object reaches step 8 (`0x46c955`): `sfx[523]`."""
    emit(world, ev.BLIZZARD, 0, x, y, ev.SPELL_BASE + 23)


def hurt(world, u, old, new):
    """Message `0x73` reached the client (`0x412a6c`): kind 0 (HP unchanged: the slot [blow]), 1 easy / 2 hard (heroes and classes: the voice bank)."""
    k = hurt_kind(old, new, u.hp_max)
    if k is None:
        return
    bank = bank_of(u)
    if k and is_voice_hero(u):
        if bank is not None:
            emit(world, ev.HURT, u.id, *pos(u), ("hero", bank, "easy" if k == 1 else "hard"), ev.SPEECH, True, k, u.owner)
    elif k == 0:
        s = unit_slot(world, u, BLOW)
        if s:
            emit(world, ev.HURT, u.id, *pos(u), s, ev.SFX, False, 0, u.owner)
    else:
        s = unit_slot(world, u, EASY if k == 1 else HARD)
        if s:
            emit(world, ev.HURT, u.id, *pos(u), s, ev.SPEECH, False, k, u.owner)


def death(world, u):
    """The death animation starts (`0x4106be` -> `0x467e42(3)`): slot [dead] (heroes: the bank's `dead`), speech bus."""
    bank = bank_of(u)
    if is_voice_hero(u):
        if bank is not None:
            emit(world, ev.DEATH, u.id, *pos(u), ("hero", bank, "dead"), ev.SPEECH, True, 3, u.owner)
    else:
        s = unit_slot(world, u, DEAD)
        if s:
            emit(world, ev.DEATH, u.id, *pos(u), s, ev.SPEECH, False, 3, u.owner)


def skillup(world, hero):
    """A hero's skill rose (`0x92` sub 2, `0x40e689`): table id 15 `message`, flat."""
    emit(world, ev.SKILLUP, hero.id, *pos(hero), ev.MESSAGE_SOUND, ev.SFX, False, 0, hero.owner)
