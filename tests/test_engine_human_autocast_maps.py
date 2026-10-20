"""Player-owned auto-cast on a real campaign map (game files, skipped without the install).  Map 73: the party's mage (`2M_Knight3`, book with
Shield) casts on its own once the party-AI byte allows it (message 0x46 sub 3) and the AI pass runs; with the byte clear it does not.
Spec: docs/engine/ai.md 12.8."""

from allods2.assets import AssetCache
from allods2.cli import open_map
from engine.sim import SetAutoCast, Simulation, ai, spells
from engine.world import CastStarted, World

from helpers import GFS, needs_data

pytestmark = needs_data
TICKS = 300


def play(flags, seed=3):
    w = World.from_map(open_map("73"), AssetCache(GFS), seed=seed)
    mage = next(u for u in w.units.values() if w.players[u.owner].human and spells.known_mask(u))
    sim = Simulation(w, ai=True)
    sim.step([SetAutoCast(mage.owner, flags)])
    for _ in range(TICKS - 1):
        sim.step()
    return w, mage


def test_the_party_mage_shields_itself_when_the_byte_allows_it():
    w, mage = play(ai.AUTO_HEAL | ai.AUTO_BUFF | ai.AUTO_PROT | ai.FRIEND_OWN)
    assert any(isinstance(e, CastStarted) and e.caster == mage.id for e in w.fight_log)
    assert mage.effect_mask & 1 << spells.SHIELD
    assert w.check_consistency() == []


def test_with_the_byte_clear_the_party_casts_nothing_by_itself():
    w, mage = play(0)
    assert not [e for e in w.fight_log if isinstance(e, CastStarted)]
    assert not mage.effect_mask & 1 << spells.SHIELD


def test_the_run_is_deterministic():
    a, _ = play(0x3F)
    b, _ = play(0x3F)
    assert a.dump_hash() == b.dump_hash()
