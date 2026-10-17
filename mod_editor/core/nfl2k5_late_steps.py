"""Scheduling and verified caching for the late build steps (b77.5 fast2).

The late steps (club fan art, Anniversary fields, native play scoring, era
kits, Broadcast greens, 2026 venue art) were once single threaded or capped at a
few workers. They stay byte for byte what the serial code writes: a step
splits its work into independent tasks, ``ordered_map`` runs them in worker
processes, and the caller consumes the results in task order, exactly as the
serial loop did. Nothing here decides content.

Switches (environment):
  NFL2K5_SERIAL_LATE_STEPS=1     every late step runs in this process, one task at a time, with the
                                 old worker caps for the two steps that had them
  NFL2K5_SERIAL_<STEP>=1         the same for one step (FAN_ART, ANNIVERSARY_FIELDS, PLAY_SCORING,
                                 ERA_KITS, BROADCAST_GREENS, VENUE_ART)
  NFL2K5_BUILD_WORKERS=N         worker count for every pool (1 means serial)
  NFL2K5_DISABLE_COMPILE_CACHE=1 no late-step cache reads or writes
  NFL2K5_COMPILE_CACHE_MAX_MB    size cap of each step cache (default 1 GiB)
  NFL2K5_STEP_CACHE_ROOT         cache folder (default: <private cache root>/late-steps)

Workers are started by the caller's default start method, as the stadium pool
always was (fork on Linux, spawn on Windows), so tasks are plain picklable data
and worker functions are top-level.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import zlib

ROOT = Path(__file__).resolve().parents[2]
CACHE_VERSION = 1
SERIAL_ALL = "NFL2K5_SERIAL_LATE_STEPS"
#: Environment that only selects workers, caching or serial fallback; never part of a cache key.
ENV_NOT_IN_KEY = frozenset({"NFL2K5_BUILD_WORKERS", "NFL2K5_DISABLE_COMPILE_CACHE", "NFL2K5_COMPILE_CACHE_MAX_MB",
                            "NFL2K5_STEP_CACHE_ROOT", SERIAL_ALL})
#: Native helpers run as subprocesses: code even though never imported.
NATIVE_HELPERS = ("tools/nfl2k5_equipment_optimal", "tools/nfl2k5_equipment_optimal.c",
                  "tools/nfl2k5_equipment_optimal.exe", "tools/apf_h7a_optimal", "tools/apf_h7a_optimal.c")


# -- workers ---------------------------------------------------------------------------------------------------

def serial_requested(step_env: str | None = None) -> bool:
    """True when the whole group, or this one step, is switched to the serial code path."""
    return os.environ.get(SERIAL_ALL) == "1" or (step_env is not None and os.environ.get(step_env) == "1")


def _available_memory() -> int | None:
    try:
        if sys.platform.startswith("linux"):
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
        if os.name == "nt":
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                            ("total_physical", ctypes.c_ulonglong), ("available_physical", ctypes.c_ulonglong),
                            ("total_page_file", ctypes.c_ulonglong), ("available_page_file", ctypes.c_ulonglong),
                            ("total_virtual", ctypes.c_ulonglong), ("available_virtual", ctypes.c_ulonglong),
                            ("available_extended_virtual", ctypes.c_ulonglong)]
            status = MemoryStatus()
            status.length = ctypes.sizeof(MemoryStatus)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            return int(status.available_physical)
        return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, OSError, ValueError, IndexError):
        return None


def configured_workers() -> int | None:
    """NFL2K5_BUILD_WORKERS as a worker count, or None when unset or not a number."""
    configured = os.environ.get("NFL2K5_BUILD_WORKERS", "").strip()
    if configured:
        try:
            return max(1, int(configured))
        except ValueError:
            return None
    return None


def worker_count(tasks: int, step_env: str | None = None, *, per_worker_mb: int = 700,
                 legacy: int | None = None) -> int:
    """Workers for ``tasks`` independent tasks: NFL2K5_BUILD_WORKERS, else the serial switches, else cores - 1.

    A serial switch means one worker, or ``legacy`` workers for the two steps that already had a pool (their old
    cap). Available memory bounds the default (``per_worker_mb`` each); Windows pools stop at 61.
    """
    count = configured_workers()
    if count is None and serial_requested(step_env):
        count = 1 if legacy is None else legacy
    if count is None and tasks < 2:
        return 1
    if count is None:
        cpus = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)
        count = cpus - 1
        memory = _available_memory()
        if memory is not None:
            count = min(count, memory // (per_worker_mb * 1024 ** 2))
    if os.name == "nt":
        count = min(count, 61)  # WaitForMultipleObjects limit of the process pool
    return max(1, min(count, tasks))


def _run_task(function, task, marks_root):
    """Worker entry point (top level, so it pickles under spawn): the recipe's marks pack travels with the task."""
    from . import nfl2k5_official_marks as official
    return official.run_with_pack(function, task, marks_root)


def ordered_map(function, tasks, workers: int, *, initializer=None, initargs=(), cost=None):
    """Yield ``function(task)`` for each task, in task order.

    One worker, or a single task, runs in this process exactly like a loop. Otherwise a bounded window of tasks is
    in flight in a process pool. An exception raised by ``function`` surfaces when its turn comes, as the serial
    loop would raise it; a pool that cannot start or loses a worker finishes the remaining tasks in this process.
    ``function`` must be a top-level function and tasks must pickle. ``initializer(*initargs)`` runs once in
    each worker (once here for the in-process path) so a large shared input is sent once, not with every task.
    ``cost(task)`` (optional) lets the dearest tasks start first; results are still yielded in task order, and
    every task is queued at once, so use it for a few dozen tasks, not thousands.
    """
    tasks = list(tasks)
    if workers <= 1 or len(tasks) < 2:
        if initializer is not None and tasks:
            initializer(*initargs)
        for task in tasks:
            yield function(task)
        return
    from collections import deque
    from concurrent.futures import ProcessPoolExecutor
    from concurrent.futures.process import BrokenProcessPool
    from . import nfl2k5_official_marks as official
    marks_root = official.selected_root()
    try:
        pool = ProcessPoolExecutor(max_workers=min(workers, len(tasks)), initializer=initializer, initargs=initargs)
    except (OSError, ValueError, NotImplementedError):
        if initializer is not None:
            initializer(*initargs)
        for task in tasks:
            yield function(task)
        return
    window = max(2, 2 * min(workers, len(tasks)))
    pending: deque = deque()
    futures: dict = {}
    submitted = delivered = 0
    try:
        while delivered < len(tasks):
            broken = False
            try:
                if cost is not None and not futures:
                    for position in sorted(range(len(tasks)), key=lambda i: (-cost(tasks[i]), i)):
                        futures[position] = pool.submit(_run_task, function, tasks[position], marks_root)
                elif cost is None:
                    while submitted < len(tasks) and len(pending) < window:
                        pending.append(pool.submit(_run_task, function, tasks[submitted], marks_root))
                        submitted += 1
                result = (futures.pop(delivered) if cost is not None else pending.popleft()).result()
            except BrokenProcessPool:
                broken = True
            if broken:
                if initializer is not None:
                    initializer(*initargs)
                for task in tasks[delivered:]:
                    yield function(task)
                return
            delivered += 1
            yield result
    finally:
        pool.shutdown(wait=True, cancel_futures=True)


# -- content digests -------------------------------------------------------------------------------------------

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    """A JSON-able form with a stable text: arrays and bytes by digest, mappings sorted, paths as text."""
    if isinstance(value, bytes | bytearray | memoryview):
        return {"$bytes": sha(bytes(value)), "n": len(value)}
    if isinstance(value, dict):
        return {"$map": sorted(([canonical(k), canonical(v)] for k, v in value.items()), key=lambda p: json.dumps(p[0]))}
    if isinstance(value, list | tuple):
        return [canonical(v) for v in value]
    if isinstance(value, set | frozenset):
        return {"$set": sorted((canonical(v) for v in value), key=json.dumps)}
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return {"$float": value.hex()}
    tobytes = getattr(value, "tobytes", None)
    if tobytes is not None and hasattr(value, "shape"):
        return {"$array": sha(tobytes()), "shape": list(value.shape), "dtype": str(value.dtype)}
    if hasattr(value, "item"):
        return canonical(value.item())
    raise TypeError(f"cannot digest {type(value).__name__}")


def digest(*parts) -> str:
    return sha(json.dumps(canonical(list(parts)), sort_keys=True, separators=(",", ":")).encode("utf-8"))


# -- code identity ---------------------------------------------------------------------------------------------
#
# A cache entry is only good for the code that wrote it. Each step declares the repository files its work executes
# and the data it reads (STEP_CODE, below). The declarations come from tracing real runs, and
# tests/mod_editor/test_b775_fast2_late_steps.py re-traces them and fails when a step runs a file or reads data
# that is not declared, so a new dependency cannot silently go stale.

STEP_CODE: dict[str, dict] = {
    "fan-art": dict(
        code=(
            "mod_editor/core/errors.py",
            "mod_editor/core/json_stream.py",
            "mod_editor/core/model.py",
            "mod_editor/core/nfl2k5_build_service.py",
            "mod_editor/core/nfl2k5_bump_strength.py",
            "mod_editor/core/nfl2k5_cave_oracle.py",
            "mod_editor/core/nfl2k5_late_steps.py",
            "mod_editor/core/nfl2k5_midfield_art.py",
            "mod_editor/core/nfl2k5_model_fan_art.py",
            "mod_editor/core/nfl2k5_models.py",
            "mod_editor/core/nfl2k5_modern_color.py",
            "mod_editor/core/nfl2k5_modern_metlife.py",
            "mod_editor/core/nfl2k5_modern_venues_2026.py",
            "mod_editor/core/nfl2k5_official_marks.py",
            "mod_editor/core/nfl2k5_project_fit.py",
            "mod_editor/core/nfl2k5_roster_records.py",
            "mod_editor/core/nfl2k5_scne_builder.py",
            "mod_editor/core/nfl2k5_source_cache.py",
            "mod_editor/core/nfl2k5_stadium_cache.py",
            "mod_editor/core/nfl2k5_stadium_shared_art.py",
            "mod_editor/core/nfl2k5_stadium_studio.py",
            "mod_editor/core/nfl2k5_stadium_texture_writer.py",
            "mod_editor/core/platform_compat.py",
            "mod_editor/core/sources.py",
            "tools/nfl2k5_playbook_position_recode.py",
            "tools/nfl_outer.py",
            "tools/nfl_scene_probe.py",
            "tools/nfl_scne_inventory.py",
            "tools/nfl_tset_png_import.py",
            "tools/nfl_txtr.py",
            "tools/nfl_uniform_color_xiso_direct_patch.py",
            "tools/nfl_uniform_inventory.py",
            "tools/nfl_vc_lz_fill.py",
            "tools/xbe_info.py",
        ),
        data=(
            "data/nfl2k5_modern_venues_2026",
            "data/nfl2k5_official_marks_catalog.json",
            "data/nfl2k5_stadium_shared_art",
        )),
    "anniversary-fields": dict(
        code=(
            "mod_editor/core/errors.py",
            "mod_editor/core/json_stream.py",
            "mod_editor/core/model.py",
            "mod_editor/core/nfl2k5_build_service.py",
            "mod_editor/core/nfl2k5_bump_strength.py",
            "mod_editor/core/nfl2k5_cave_oracle.py",
            "mod_editor/core/nfl2k5_espn25_fields.py",
            "mod_editor/core/nfl2k5_historic_styles.py",
            "mod_editor/core/nfl2k5_late_steps.py",
            "mod_editor/core/nfl2k5_models.py",
            "mod_editor/core/nfl2k5_modern_color.py",
            "mod_editor/core/nfl2k5_modern_metlife.py",
            "mod_editor/core/nfl2k5_modern_venues_2026.py",
            "mod_editor/core/nfl2k5_official_marks.py",
            "mod_editor/core/nfl2k5_project_fit.py",
            "mod_editor/core/nfl2k5_source_cache.py",
            "mod_editor/core/nfl2k5_stadium_cache.py",
            "mod_editor/core/nfl2k5_stadium_studio.py",
            "mod_editor/core/nfl2k5_stadium_texture_writer.py",
            "mod_editor/core/nfl2k5_super_bowl_walls.py",
            "mod_editor/core/platform_compat.py",
            "mod_editor/core/sources.py",
            "tools/nfl2k5_playbook_position_recode.py",
            "tools/nfl_outer.py",
            "tools/nfl_scene_probe.py",
            "tools/nfl_scne_inventory.py",
            "tools/nfl_tset_png_import.py",
            "tools/nfl_txtr.py",
            "tools/nfl_uniform_color_xiso_direct_patch.py",
            "tools/nfl_uniform_inventory.py",
            "tools/nfl_vc_lz_fill.py",
            "tools/xbe_info.py",
        ),
        data=(
            "data/nfl2k5_espn25_fields",
            "data/nfl2k5_espn25_fields.json",
            "data/nfl2k5_official_marks_catalog.json",
            "data/nfl2k5_super_bowl_walls",
        )),
    "play-scoring": dict(
        code=(
            "mod_editor/core/errors.py",
            "mod_editor/core/nfl2k5_cave_oracle.py",
            "mod_editor/core/nfl2k5_late_steps.py",
            "mod_editor/core/nfl2k5_play_scoring.py",
            "mod_editor/core/nfl2k5_playbook_inspector.py",
            "mod_editor/core/nfl2k5_universal_asset_index.py",
            "tools/nfl_outer.py",
        ),
        data=(
            "mod_editor/core/nfl2k5_play_scoring_pins.json",
        )),
    "era-kits": dict(
        code=(
            "mod_editor/core/nfl2k5_bump_texture_writer.py",
            "mod_editor/core/nfl2k5_era_kits.py",
            "mod_editor/core/nfl2k5_late_steps.py",
            "tools/nfl_txtr.py",
            "tools/nfl_vc_lz_fill.py",
        ),
        data=(
            "data/nfl2k5_era_kits_pins.json",
            "data/nfl2k5_moment_era_kits.json",
        )),
    "broadcast-greens": dict(
        code=(
            "mod_editor/core/errors.py",
            "mod_editor/core/json_stream.py",
            "mod_editor/core/model.py",
            "mod_editor/core/nfl2k5_broadcast_greens.py",
            "mod_editor/core/nfl2k5_build_service.py",
            "mod_editor/core/nfl2k5_bump_strength.py",
            "mod_editor/core/nfl2k5_cave_oracle.py",
            "mod_editor/core/nfl2k5_compile_cache.py",
            "mod_editor/core/nfl2k5_late_steps.py",
            "mod_editor/core/nfl2k5_models.py",
            "mod_editor/core/nfl2k5_modern_color.py",
            "mod_editor/core/nfl2k5_modern_metlife.py",
            "mod_editor/core/nfl2k5_modern_surfaces.py",
            "mod_editor/core/nfl2k5_modern_venues_2026.py",
            "mod_editor/core/nfl2k5_official_marks.py",
            "mod_editor/core/nfl2k5_project_fit.py",
            "mod_editor/core/nfl2k5_source_cache.py",
            "mod_editor/core/nfl2k5_stadium_cache.py",
            "mod_editor/core/nfl2k5_stadium_studio.py",
            "mod_editor/core/nfl2k5_stadium_texture_writer.py",
            "mod_editor/core/platform_compat.py",
            "mod_editor/core/sources.py",
            "tools/nfl_outer.py",
            "tools/nfl_scene_probe.py",
            "tools/nfl_scne_inventory.py",
            "tools/nfl_tset_png_import.py",
            "tools/nfl_txtr.py",
            "tools/nfl_uniform_color_xiso_direct_patch.py",
            "tools/nfl_uniform_inventory.py",
            "tools/nfl_vc_lz_fill.py",
            "tools/xbe_info.py",
        ),
        data=(
        )),
    "venue-art": dict(
        code=(
            "mod_editor/core/errors.py",
            "mod_editor/core/json_stream.py",
            "mod_editor/core/model.py",
            "mod_editor/core/nfl2k5_build_service.py",
            "mod_editor/core/nfl2k5_bump_strength.py",
            "mod_editor/core/nfl2k5_cave_oracle.py",
            "mod_editor/core/nfl2k5_late_steps.py",
            "mod_editor/core/nfl2k5_midfield_art.py",
            "mod_editor/core/nfl2k5_models.py",
            "mod_editor/core/nfl2k5_modern_color.py",
            "mod_editor/core/nfl2k5_modern_metlife.py",
            "mod_editor/core/nfl2k5_modern_venues_2026.py",
            "mod_editor/core/nfl2k5_official_marks.py",
            "mod_editor/core/nfl2k5_project_fit.py",
            "mod_editor/core/nfl2k5_roster_records.py",
            "mod_editor/core/nfl2k5_scne_builder.py",
            "mod_editor/core/nfl2k5_source_cache.py",
            "mod_editor/core/nfl2k5_stadium_cache.py",
            "mod_editor/core/nfl2k5_stadium_shared_art.py",
            "mod_editor/core/nfl2k5_stadium_studio.py",
            "mod_editor/core/nfl2k5_stadium_texture_writer.py",
            "mod_editor/core/platform_compat.py",
            "mod_editor/core/sources.py",
            "tools/nfl2k5_playbook_position_recode.py",
            "tools/nfl_outer.py",
            "tools/nfl_scene_probe.py",
            "tools/nfl_scne_inventory.py",
            "tools/nfl_tset_png_import.py",
            "tools/nfl_txtr.py",
            "tools/nfl_uniform_color_xiso_direct_patch.py",
            "tools/nfl_uniform_inventory.py",
            "tools/nfl_vc_lz_fill.py",
            "tools/xbe_info.py",
        ),
        data=(
            "data/nfl2k5_modern_venues_2026",
            "data/nfl2k5_official_marks_catalog.json",
            "data/nfl2k5_stadium_shared_art",
        )),
}


def step_code(step: str) -> dict:
    """The ``code`` (repository files) and ``data`` (repository files or data/ folders) declared for a step."""
    return dict(code=STEP_CODE[step]["code"], data=STEP_CODE[step]["data"])


_FILE_SHA: dict[tuple, str | None] = {}


def file_sha(path: Path) -> str | None:
    """SHA-256 of a file, memoized on (path, size, mtime) so an edit is seen but a build hashes once."""
    try:
        info = path.stat()
        key = (str(path), info.st_size, info.st_mtime_ns)
        if key not in _FILE_SHA:
            _FILE_SHA[key] = sha(path.read_bytes())
        return _FILE_SHA[key]
    except OSError:
        return None


def _tree_files(path: Path):
    if path.is_dir():
        for child in sorted(path.rglob("*")):
            if child.is_file() and "__pycache__" not in child.parts:
                yield child
    else:
        yield path


def code_digest(code, data=()) -> str:
    """SHA-256 over the declared sources, the native helpers and the declared data."""
    rows = [[name, file_sha(ROOT / name)] for name in sorted(set(code) | {n for n in NATIVE_HELPERS
                                                                          if (ROOT / n).exists()})]
    for name in sorted(data):
        for child in _tree_files(ROOT / name):
            rows.append([child.relative_to(ROOT).as_posix(), file_sha(child)])
    return digest(rows)


def toolchain() -> dict:
    import platform
    stamp = {"python": sys.version, "implementation": sys.implementation.name, "platform": sys.platform,
             "machine": platform.machine(), "byteorder": sys.byteorder,
             "environment": {name: value for name, value in sorted(os.environ.items())
                             if name.startswith("NFL2K5_") and name not in ENV_NOT_IN_KEY
                             and not name.startswith("NFL2K5_SERIAL_")}}
    for name in ("PIL", "numpy", "unicorn"):
        try:
            stamp[name] = getattr(__import__(name), "__version__", "unknown")
        except ImportError:
            stamp[name] = None
    return stamp


# -- the cache -------------------------------------------------------------------------------------------------

def cache_root() -> Path:
    configured = os.environ.get("NFL2K5_STEP_CACHE_ROOT", "").strip()
    if configured:
        return Path(configured)
    from .nfl2k5_source_cache import default_cache_root
    return default_cache_root() / "late-steps"


class StepCache:
    """Content-addressed results of one late step, checked on every hit.

    The key digests everything the result depends on: the step, the cache version, the toolchain, the code
    closure and the caller's input digests. An entry records the key's parts again and the result's own digest;
    a hit that disagrees with either, or that is corrupt, truncated or oversized, is a miss and is replaced.
    Callers still run their own gates on a hit (a pin, an applied receipt, a read-back).
    """

    def __init__(self, step: str, code, data=(), *, root: Path | None = None):
        from .nfl2k5_compile_cache import CompileCache
        self.step = step
        self.cache = CompileCache(root if root is not None else cache_root() / step)
        self.code, self.data = tuple(code), tuple(data)
        self._code = None
        self.hits = self.misses = self.stored = 0

    @classmethod
    def open(cls, step: str, code, data=(), **options) -> "StepCache | None":
        """The step's cache, or None when NFL2K5_DISABLE_COMPILE_CACHE=1 or the cache folder cannot be used."""
        if os.environ.get("NFL2K5_DISABLE_COMPILE_CACHE") == "1":
            return None
        try:
            cache = cls(step, code, data, **options)
            cache.cache.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            return cache
        except Exception:  # noqa: BLE001 - a cache can never refuse a build
            return None

    def key(self, *parts) -> str | None:
        """The key for these input digests, or None when something in them cannot be digested (no caching then)."""
        try:
            if self._code is None:
                self._code = code_digest(self.code, self.data)
            return digest(CACHE_VERSION, self.step, toolchain(), self._code, list(parts))
        except (TypeError, ValueError, OSError, RecursionError):
            return None

    def get(self, key: str | None):
        """The stored value, or None."""
        from .nfl2k5_compile_cache import _decode
        if key is None:
            self.misses += 1
            return None
        stored = self.cache.get(key)
        value = None
        if isinstance(stored, dict) and stored.get("key") == key:
            try:
                inflater = zlib.decompressobj()
                text = inflater.decompress(stored["zlib"], 256 * 1024 * 1024)
                if inflater.unconsumed_tail or not inflater.eof or sha(text) != stored["sha256"]:
                    raise ValueError("late-step cache record is damaged")
                value = _decode(json.loads(text))
            except (KeyError, TypeError, ValueError, zlib.error, RecursionError):
                value = None
        if value is None:
            if stored is not None:
                self.cache.hits -= 1
                self.cache.misses += 1
            self.misses += 1
            return None
        self.hits += 1
        return value

    def put(self, key: str | None, value) -> bool:
        """Remember a value if it survives a JSON round trip unchanged (otherwise it is not cached)."""
        from .nfl2k5_compile_cache import _decode, _encode
        if key is None:
            return False
        try:
            text = json.dumps(_encode(value), separators=(",", ":"), ensure_ascii=True).encode("ascii")
            if _decode(json.loads(text)) != value:
                return False
            self.cache.put(key, {"key": key, "zlib": zlib.compress(text, 3), "sha256": sha(text)})
        except (TypeError, ValueError, OverflowError, RecursionError):
            return False
        self.stored += 1
        return True
