"""Optional native accelerators, built on demand with the system C compiler and loaded with ctypes.

Spec: docs/engine/simulation.md 7.5.  No Python build dependency: `planner()` compiles `planner.c` with
`gcc -O2 -shared -fPIC` (or `$CC`, else `cc`) the first time it is needed and whenever the source is newer
than the library, into this directory (or `~/.cache/allods2/native` when it is read-only).  Any failure
(no compiler, compile error, load error) gives None and the callers use their pure-Python code, which stays
the reference.  `ALLODS2_NATIVE=0` forces the Python code, `=1` requires the library (RuntimeError when it
cannot be built or loaded); unset = use it when available.
"""

import ctypes
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLANNER_SRC = os.path.join(HERE, "planner.c")
PLANNER_VERSION = 1             # A2_PLANNER_VERSION in planner.c
_SUFFIX = ".dll" if os.name == "nt" else (".dylib" if sys.platform == "darwin" else ".so")

_cache = {}
_errors = {}


def mode():
    """The ALLODS2_NATIVE switch: '0' (off), '1' (required) or '' (auto)."""
    v = os.environ.get("ALLODS2_NATIVE", "").strip()
    return v if v in ("0", "1") else ""


def _compiler():
    for cc in (os.environ.get("CC"), "gcc", "cc"):
        if cc and shutil.which(cc):
            return shutil.which(cc)
    return None


def _out_dirs():
    yield HERE
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    yield os.path.join(base, "allods2", "native")


def _stale(lib, src):
    return not os.path.exists(lib) or os.path.getmtime(lib) < os.path.getmtime(src)


def build(src=PLANNER_SRC, name="_planner", force=False):
    """Compile `src` into a shared library unless an up-to-date one exists; returns its path.

    Raises RuntimeError (with the compiler output) when no compiler is found or every output directory
    fails.  The library is written to a temporary name and renamed, so concurrent builds are safe."""
    errors = []
    for d in _out_dirs():
        lib = os.path.join(d, name + _SUFFIX)
        if not force and not _stale(lib, src):
            return lib
        cc = _compiler()
        if cc is None:
            raise RuntimeError("no C compiler (gcc / cc / $CC) found")
        try:
            os.makedirs(d, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=name + ".", suffix=_SUFFIX + ".tmp", dir=d)
            os.close(fd)
        except OSError as e:
            errors.append("%s: %s" % (d, e))
            continue
        try:
            p = subprocess.run([cc, "-O2", "-shared", "-fPIC", "-std=c99", "-o", tmp, src],
                               capture_output=True, text=True)
            if p.returncode != 0:
                raise RuntimeError("%s failed:\n%s%s" % (cc, p.stdout, p.stderr))
            os.replace(tmp, lib)
            return lib
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    raise RuntimeError("cannot write the native library: " + "; ".join(errors))


def _load_planner():
    lib = ctypes.CDLL(build())
    if lib.a2_planner_version() != PLANNER_VERSION:
        lib = ctypes.CDLL(build(force=True))         # a stale library from an older source
        if lib.a2_planner_version() != PLANNER_VERSION:
            raise RuntimeError("native planner version mismatch")
    p, i = ctypes.c_void_p, ctypes.c_int
    lib.a2_plan.argtypes = [p, p, i, i, i, i, i, i, i, i, p, p, p, p]
    lib.a2_plan.restype = i
    lib.a2_walk_back.argtypes = [p, p, i, i, i, i, i, p]
    lib.a2_walk_back.restype = i
    return lib


def load_planner():
    """The ctypes planner library whatever ALLODS2_NATIVE says, or None when it cannot be built or loaded
    (the reason: `error()`).  The first attempt is cached for the process."""
    if "planner" not in _cache:
        try:
            _cache["planner"] = _load_planner()
        except Exception as e:                       # noqa: BLE001 - any failure means "use Python"
            _cache["planner"] = None
            _errors["planner"] = "%s: %s" % (type(e).__name__, e)
    return _cache["planner"]


def planner():
    """The planner library the engine should use: None with ALLODS2_NATIVE=0 or when unavailable in auto
    mode; RuntimeError when ALLODS2_NATIVE=1 and it is unavailable."""
    m = mode()
    if m == "0":
        return None
    lib = load_planner()
    if lib is None and m == "1":
        raise RuntimeError("ALLODS2_NATIVE=1 but the native planner is unavailable: %s" % _errors.get("planner"))
    return lib


def error(name="planner"):
    """Why the library `name` is unavailable (None when it loaded or was not tried)."""
    return _errors.get(name)
