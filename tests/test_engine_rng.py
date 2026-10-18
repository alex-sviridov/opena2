"""RNG (I1): the exe's CRT generator, one per world, no other random source in sim/.
Spec: docs/engine/simulation.md section 10."""

import ast
import os

import numpy as np

from engine.sim import Simulation
from engine.sim.rng import DEFAULT_SEED, Rng
from engine.world import World

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_unseeded_stream_is_the_msvc_crt_sequence():
    r = Rng(1)
    assert [r.rand15() for _ in range(6)] == [41, 18467, 6334, 26500, 19169, 15724]


def test_default_seed_is_the_crt_initial_state():
    assert DEFAULT_SEED == 1 and Rng().state == 1


def test_srand_replaces_the_state():
    r = Rng(5)
    a = [r.rand15() for _ in range(4)]
    r.srand(5)
    assert [r.rand15() for _ in range(4)] == a


def test_rand_n_is_inclusive_and_scaled_from_the_15_bit_value():
    r = Rng(1)
    ref = Rng(1)
    for n in (1, 5, 100, 200):
        raw = ref.rand15()
        assert r.rand(n) == (raw * (n + 1)) >> 15


def test_rand_zero_draws_nothing():
    r = Rng(7)
    s = r.state
    assert r.rand(0) == 0 and r.state == s


def test_rand_covers_the_whole_inclusive_range_and_no_more():
    r = Rng(3)
    seen = {r.rand(8) for _ in range(5000)}
    assert seen == set(range(9))


def test_state_is_32_bit_and_seed_is_truncated():
    r = Rng(0x1_0000_0005)
    assert r.state == 5


def world():
    return World(np.zeros((16, 16), np.uint16), np.zeros((16, 16), np.int8), "syn")


def test_world_owns_one_rng_seeded_per_game():
    a, b = world(), World(np.zeros((16, 16), np.uint16), np.zeros((16, 16), np.int8), "syn", seed=9)
    assert a.rng.state == DEFAULT_SEED and b.rng.state == 9
    assert a.rng is not b.rng


def test_dump_is_unchanged_until_the_rng_is_used():
    w = world()
    before = w.dump_hash()
    w.rng.rand15()
    assert "rng" in w.dump() and w.dump_hash() != before
    assert "rng" not in world().dump()


def test_two_worlds_with_one_seed_stay_in_step():
    a, b = world(), world()
    for _ in range(10):
        assert a.rng.rand(100) == b.rng.rand(100)
    assert a.dump_hash() == b.dump_hash()


def test_simulation_keeps_the_seed_for_the_log():
    w = World(np.zeros((16, 16), np.uint16), np.zeros((16, 16), np.int8), "syn", seed=1234)
    assert Simulation(w).seed == 1234


def test_nothing_in_sim_uses_python_random():
    """No `random` import, no `numpy.random`, no `os.urandom`, no `secrets` anywhere under engine/sim/."""
    bad = []
    base = os.path.join(ROOT, "engine", "sim")
    for name in sorted(os.listdir(base)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(base, name)
        tree = ast.parse(open(path, encoding="utf-8").read())
        for n in ast.walk(tree):
            mods = []
            if isinstance(n, ast.Import):
                mods = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                mods = [n.module or ""] + [(n.module or "") + "." + a.name for a in n.names]
            for m in mods:
                if m == "random" or m.startswith("random.") or m in ("secrets", "numpy.random") or m.startswith("numpy.random"):
                    bad.append("%s imports %s" % (name, m))
            if isinstance(n, ast.Attribute) and n.attr in ("random", "urandom") and isinstance(n.value, ast.Name) \
                    and n.value.id in ("np", "numpy", "os"):
                bad.append("%s uses %s.%s" % (name, n.value.id, n.attr))
    assert bad == []
