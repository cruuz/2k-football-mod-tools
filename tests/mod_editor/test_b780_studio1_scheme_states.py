"""b780 studio1: the Rosters page reads four patch states, not the whole Build disc read.

``rr.inspect_states`` (the Rosters page's position scheme detection) called ``mod_build.inspect`` for four values: about 150
status functions, 50 s on a retail disc and over 3 minutes on the released v0.8 disc (730 s before the validation memo), on
the window's own thread, so opening the Rosters page with a disc open froze the Studio.  ``mod_build.inspect_scheme_states``
reads the executable once and runs only the four.  The mock tests below need nothing private; the parity tests hold the short
read to the full one on real files and skip when those are absent.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

KEYS = ("position_pools", "edge_rename", "edge_rename_disc", "scheme_labels")
RETAIL_EXTRACTION = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)")
RETAIL_XBE = RETAIL_EXTRACTION / "default.xbe"
RETAIL_XISO = Path(os.environ.get("NFL2K5_RETAIL_XISO", ""))
V08_XBE = Path(os.environ.get("NFL2K5_V08_XBE", ""))


class RostersDoNotRunTheFullDiscReadTests(unittest.TestCase):
    def test_detection_asks_for_the_four_states_and_never_runs_inspect(self) -> None:
        states = {"position_pools": "applied", "edge_rename": "applied",
                  "edge_rename_disc": {"status": "partial"}, "scheme_labels": "applied"}
        with mock.patch.object(mod_build, "inspect", side_effect=AssertionError("the full disc read ran")), \
                mock.patch.object(mod_build, "_inspect", side_effect=AssertionError("the full disc read ran")), \
                mock.patch.object(mod_build, "inspect_scheme_states", return_value=dict(states)) as short:
            found = rr.inspect_states("disc.iso")
        short.assert_called_once()
        self.assertEqual(found, states)
        self.assertEqual(rr.detect_scheme_from_states(found)["scheme"], "one_pool")

    def test_a_read_that_fails_is_none_and_detection_falls_back_to_the_records(self) -> None:
        for error in (ValueError("not a disc"), OSError("gone"), RuntimeError("anything")):
            with mock.patch.object(mod_build, "inspect_scheme_states", side_effect=error):
                self.assertIsNone(rr.inspect_states("disc.iso"), repr(error))

    def test_the_short_read_names_exactly_the_keys_the_detection_uses(self) -> None:
        report = {"container": "xiso", "edge_rename": "applied", "edge_rename_disc": {"status": "applied"},
                  "scheme_labels": "applied"}
        with mock.patch.object(mod_build.tt, "read_scheme_states", return_value=report), \
                mock.patch.object(mod_build, "_xbe_bytes", return_value=b"xbe"), \
                mock.patch.object(mod_build, "_core_module") as core:
            core.return_value.status.return_value = "applied"
            states = mod_build.inspect_scheme_states("disc.iso")
        self.assertEqual(sorted(states), sorted(KEYS))
        self.assertEqual(states["position_pools"], "applied")
        self.assertEqual(states["edge_rename_disc"], {"status": "applied"})
        # a bare executable has no pool status of its own and no disc half, exactly as inspect() reports it
        with mock.patch.object(mod_build.tt, "read_scheme_states",
                               return_value={"container": "xbe", "edge_rename": "retail", "scheme_labels": "retail"}):
            bare = mod_build.inspect_scheme_states("default.xbe")
        self.assertEqual(bare, {"position_pools": "n/a", "edge_rename": "retail", "edge_rename_disc": None,
                                "scheme_labels": "retail"})

    def test_an_unreadable_pool_status_reads_foreign_as_inspect_does(self) -> None:
        with mock.patch.object(mod_build.tt, "read_scheme_states",
                               return_value={"container": "xiso", "edge_rename": "retail", "edge_rename_disc": {},
                                             "scheme_labels": "retail"}), \
                mock.patch.object(mod_build, "_xbe_bytes", side_effect=ValueError("no executable")), \
                mock.patch.object(mod_build, "_core_module"):
            self.assertEqual(mod_build.inspect_scheme_states("disc.iso")["position_pools"], "foreign")


def _full(path: Path) -> dict:
    report = mod_build.inspect(path)
    return {key: report.get(key) for key in KEYS}


class ShortReadMatchesTheFullReadTests(unittest.TestCase):
    """Each takes as long as one full read of its file (the retail executable ~10 s, a disc ~50 s, the grown v0.8 executable ~1 min)."""

    @unittest.skipUnless(RETAIL_XBE.is_file(), "private retail executable missing")
    def test_the_retail_executable(self) -> None:
        self.assertEqual(mod_build.inspect_scheme_states(RETAIL_XBE), _full(RETAIL_XBE))

    @unittest.skipUnless(V08_XBE.is_file(), "private v0.8 executable missing")
    def test_the_grown_v08_executable(self) -> None:
        short = mod_build.inspect_scheme_states(V08_XBE)
        self.assertEqual(short, _full(V08_XBE))
        self.assertEqual(short["position_pools"], "n/a")        # a bare executable carries no pool status of its own, so the scheme
        self.assertEqual(rr.detect_scheme_from_states(short)["scheme"], "edge")     # reads the EDGE rename; the disc says one_pool

    @unittest.skipUnless(RETAIL_XISO.is_file(), "private retail disc missing")
    def test_the_retail_disc(self) -> None:
        short = mod_build.inspect_scheme_states(RETAIL_XISO)
        self.assertEqual(short, _full(RETAIL_XISO))
        self.assertEqual(rr.inspect_states(RETAIL_XISO), short)
        self.assertEqual(short["position_pools"], "retail")


if __name__ == "__main__":
    unittest.main()
