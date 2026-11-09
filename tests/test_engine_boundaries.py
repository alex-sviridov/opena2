"""Import-boundary rules of docs/engine/architecture.md section 1 (AST scan)."""

import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def imports(path):
    """Absolute module names imported by a source file (relative imports resolved)."""
    pkg = os.path.relpath(os.path.dirname(path), ROOT).replace(os.sep, ".")
    out = []
    for n in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
        if isinstance(n, ast.Import):
            out += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            base = n.module or ""
            if n.level:
                parts = pkg.split(".")
                parts = parts[:len(parts) - (n.level - 1)]
                base = ".".join(parts + ([n.module] if n.module else []))
            out.append(base)
            out += [base + "." + a.name for a in n.names]
    return out


def files(rel):
    p = os.path.join(ROOT, rel)
    if p.endswith(".py"):
        return [p]
    return [os.path.join(d, f) for d, _, fs in os.walk(p) for f in fs if f.endswith(".py")]


def hits(rel, forbidden):
    bad = []
    for f in files(rel):
        for m in imports(f):
            if any(m == b or m.startswith(b + ".") for b in forbidden):
                bad.append("%s imports %s" % (os.path.relpath(f, ROOT), m))
    return bad


PYGAME = ("pygame",)
BACKEND = ("engine.backend_pygame",)


def test_core_never_imports_pygame_or_engine():
    assert hits("allods2", PYGAME + ("engine",)) == []
    assert hits("a2res", PYGAME + ("engine",)) == []


def test_world_and_sim_are_below_view_and_ui():
    bad = ("engine.view", "engine.ui") + BACKEND + PYGAME
    assert hits("engine/world.py", bad) == []
    assert hits("engine/sim", bad) == []


def test_view_and_ui_are_pure():
    assert hits("engine/view", PYGAME + BACKEND + ("engine.ui", "engine.sim")) == []
    assert hits("engine/ui", PYGAME + BACKEND) == []


def test_audio_is_pure():
    assert hits("engine/audio", PYGAME + BACKEND + ("engine.view", "engine.ui", "engine.sim", "numpy")) == []


def test_only_the_backend_imports_pygame():
    for rel in ("engine/world.py", "engine/sim", "engine/view", "engine/ui", "engine/__init__.py", "engine/audio"):
        assert hits(rel, PYGAME) == []


def test_scanner_detects_violations(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("import pygame\nfrom engine.view import Camera\nfrom . import y\n")
    got = imports(str(f))
    assert "pygame" in got and "engine.view" in got and "engine.view.Camera" in got
