"""The simulation's RNG: `engine.rng.Rng`, owned by `World.rng` (the class lives one layer down so `World` can create it)."""

from engine.rng import DEFAULT_SEED, Rng

__all__ = ["DEFAULT_SEED", "Rng"]
