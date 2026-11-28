"""b81 league-aging, review M1 (11/26): the in-place routes leave every other owner as it was.

The routes (update-v09, edit-sim-qb, edit-gadget) carry player development's current revision onto an earlier disc
(mod_build._league_aging_upgrade). nfl2k5_progression rewrites the aging curves at 0x4F31D0, and nfl2k5_star_career
holds a table built from those curves; before the fix star_career and the twelve owners that look through its class
loop hooks read "foreign" on the output. Each route runs in preflight on the real released v0.9 executable and on the
8b180ed5 candidate (update-v09 only on v0.9, the disc it is for), once as shipped and once with the league-aging step
switched off. Every core owner's one-argument status is swept over the source, both outputs (a process pool):
  - with the step, only progression, weekly progression and star_career may read differently from without it, and
    those three read applied;
  - every owner the route itself does not write (same status with the step off as on the source) keeps its status.
Fixtures: NFL2K5_V09_RELEASED_XBE, NFL2K5_V09_XISO (the update-v09 route and the gadget books),
B81_HISTORY_POOL_FULL_XBE (8b180ed5). About 15-25 minutes with 8 workers (NFL2K5_SWEEP_WORKERS).
"""
from __future__ import annotations

import importlib
import inspect
import os
import pkgutil
import tempfile
import unittest
from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

AGING_OWNERS = ("nfl2k5_progression", "nfl2k5_weekly_progression", "nfl2k5_star_career")
# The owners the review found reading foreign after the step (star_career's class-loop neighbours).
NEIGHBOURS = ("nfl2k5_star_career", "nfl2k5_my_career", "nfl2k5_my_career_mode", "nfl2k5_my_career_home",
              "nfl2k5_letter_grades_attributes", "nfl2k5_module_loader", "nfl2k5_music_playlist",
              "nfl2k5_franchise_autosave", "nfl2k5_franchise_edit_player", "nfl2k5_franchise_practice",
              "nfl2k5_player_star", "nfl2k5_practice_reserves", "nfl2k5_practice_squad_screen")

_PATHS: dict[str, str] = {}


def _init(paths):
    _PATHS.update(paths)


def _status_of(name):
    """{(function, payload key): status} for one core module (its own one-argument status / xbe_status)."""
    try:
        module = importlib.import_module("mod_editor.core." + name)
    except Exception:  # noqa: BLE001 - a module that does not import has no status to compare
        return name, {}
    out = {}
    payloads = {key: Path(path).read_bytes() for key, path in _PATHS.items()}
    for function in ("status", "xbe_status"):
        fn = getattr(module, function, None)
        if not callable(fn) or getattr(fn, "__module__", "") != module.__name__:
            continue
        try:
            required = [p for p in inspect.signature(fn).parameters.values()
                        if p.default is inspect.Parameter.empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        except (TypeError, ValueError):
            continue
        if len(required) != 1:
            continue
        for key, payload in payloads.items():
            try:
                result = fn(payload)
            except Exception as exc:  # noqa: BLE001 - an exception is a state too, compared like any other
                result = "EXC:" + type(exc).__name__
            out[(function, key)] = result if isinstance(result, str) else repr(result)[:200]
    return name, out


def sweep(payloads: dict[str, bytes]) -> dict[str, dict[tuple[str, str], str]]:
    import mod_editor.core as core
    names = sorted(m.name for m in pkgutil.iter_modules(core.__path__) if m.name.startswith("nfl2k5_"))
    with tempfile.TemporaryDirectory() as folder:
        paths = {}
        for key, payload in payloads.items():
            paths[key] = os.path.join(folder, key + ".xbe")
            Path(paths[key]).write_bytes(payload)
        workers = int(os.environ.get("NFL2K5_SWEEP_WORKERS", "8"))
        with ProcessPoolExecutor(workers, initializer=_init, initargs=(paths,)) as pool:
            return dict(pool.map(_status_of, names))


def _fixture(variable):
    path = Path(os.environ.get(variable, "") or "missing")
    return path if path.is_file() else None


def run_route(kind, original, *, aging=True, v09_disc=None, books=None):
    """The route's executable in preflight: the output of its last in-place step (the history pool upgrade)."""
    from mod_editor.core import mod_build as mb
    seen = []
    real = mb._history_pool_upgrade

    def last(payload):
        out = real(payload)
        seen.append(out[0])
        return out
    with ExitStack() as stack:
        stack.enter_context(patch.object(mb, "_history_pool_upgrade", side_effect=last))
        if not aging:
            stack.enter_context(patch.object(mb, "_league_aging_upgrade", side_effect=lambda p: (p, None)))
        receipt = {"steps": [], "result": {}}
        if kind == "edit-sim-qb":
            mb._edit_installed_sim_qb(mb.sim_qb_disc_edit("s.iso", "t.iso", "realistic"), Path("s.iso"), Path("t.iso"),
                                      original, receipt, lambda *_: None, preflight=True, consume=False, reference=None)
        elif kind == "edit-gadget":
            stack.enter_context(patch.object(mb, "_gadget_resources", return_value=books))
            mb._edit_installed_gadget(mb.gadget_disc_edit("s.iso", "t.iso"), Path("s.iso"), Path("t.iso"), original,
                                      receipt, lambda *_: None, preflight=True, consume=False, reference=None)
        else:
            plan = mb.v09_disc_update(str(v09_disc), str(Path(tempfile.gettempdir()) / "never-written-v09.iso"),
                                      backfield_cards=True)
            mb._update_v09_disc(plan, lambda *_: None, preflight=True, project=False)
    return seen[-1]


class InPlaceRoutesKeepEveryOtherOwner(unittest.TestCase):
    def test_every_route_on_v09_and_8b180ed5(self):
        from mod_editor.core import mod_build as mb
        v09_xbe, v09_disc = _fixture("NFL2K5_V09_RELEASED_XBE"), _fixture("NFL2K5_V09_XISO")
        candidate = _fixture("B81_HISTORY_POOL_FULL_XBE")
        if not (v09_xbe and v09_disc and candidate):
            self.skipTest("the released v0.9 executable and disc and the 8b180ed5 executable are required")
        books = mb._gadget_resources(v09_disc)
        payloads, cases = {}, []
        for exe, path in (("v09", v09_xbe), ("8b180ed5", candidate)):
            original = path.read_bytes()
            payloads[f"{exe}.source"] = original
            for kind in ("update-v09", "edit-sim-qb", "edit-gadget"):
                if kind == "update-v09" and exe != "v09":
                    continue
                for aging in (False, True):
                    payloads[f"{exe}.{kind}.{'with' if aging else 'without'}"] = run_route(
                        kind, original, aging=aging, v09_disc=v09_disc, books=books)
                cases.append((exe, kind))
        states = sweep(payloads)
        for exe, kind in cases:
            for name, by in states.items():
                for function in {f for f, _k in by}:
                    source = by.get((function, f"{exe}.source"))
                    without = by.get((function, f"{exe}.{kind}.without"))
                    with_step = by.get((function, f"{exe}.{kind}.with"))
                    with self.subTest(executable=exe, route=kind, owner=f"{name}.{function}"):
                        if name in AGING_OWNERS:
                            self.assertEqual(with_step, "applied")
                        else:
                            self.assertEqual(with_step, without)
                        if without == source and name not in AGING_OWNERS:
                            self.assertEqual(with_step, source)
            for name in NEIGHBOURS:
                with self.subTest(executable=exe, route=kind, neighbour=name):
                    self.assertEqual(states[name][("status", f"{exe}.{kind}.with")],
                                     "applied" if name == "nfl2k5_star_career"
                                     else states[name][("status", f"{exe}.source")])


if __name__ == "__main__":
    unittest.main()
