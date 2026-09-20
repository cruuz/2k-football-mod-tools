"""Beta 74: the import quick check may not refuse artwork that Build fits.

Coach Edwards, 2026-09-20 13:19, importing one near-white sock for the Packers:
"Equipment art needs refit: it cannot fit and missed the 6,928-byte span by 72
bytes ... No fitting smaller size was established in the bounded check. Simplify
the artwork and import it again." His own 09-19 build log had already shown
socks fitting at 16x16, because Build runs the same ladder uncapped.

Reproduced here against the retail pack 0: an INDEPENDENT-palette 64x64 sock with
faint variation is refused by the capped quick check with exactly that message and
no suggestion, while ``auto_refit_group`` (what Build runs) fits it at 16 x 16.

The retail slot is real geometry, not a fixture: socks00 is a 64x64 raw P8 in a
6,848-byte span shared with socks00_mud. Skips without the private retail pack,
so it never runs on CI; it is the local gate for this defect.
"""
import io
import os
from pathlib import Path
import random
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).resolve().parent)]

RETAIL_INDEX = Path(os.environ.get(
    "NFL2K5_RETAIL_INDEX",
    "/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"))
SOCK = "tset:3621:4:0:socks00"


def _near_white_sock_png():
    """64x64, mostly white with faint off-white variation: fits at 16x16, not at 64x64 independent."""
    from PIL import Image
    rng = random.Random(3)
    image = Image.new("RGBA", (64, 64), (255, 255, 255, 255))
    pixels = image.load()
    for i in range(64 * 64):
        if rng.random() < 0.5:
            value = rng.randrange(200, 256)
            pixels[i % 64, i // 64] = (value, value, rng.randrange(200, 256), 255)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue(), image.tobytes()


@unittest.skipUnless(RETAIL_INDEX.is_file(), "private retail pack 0 unavailable")
class ImportDefersToBuildTests(unittest.TestCase):
    def setUp(self):
        from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
        writer.staged_equipment_cache().clear()
        writer._PARSE_CACHE.clear()

    def test_capped_quick_check_refuses_what_uncapped_build_fits(self):
        from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
        from mod_editor.core.nfl2k5_equipment_import_intent import with_import_mode
        payload, rgba = _near_white_sock_png()
        with tempfile.TemporaryDirectory() as folder:
            png = Path(folder) / "sock.png"
            png.write_bytes(with_import_mode(payload, SOCK, rgba, independent=True, scale=1))
            # The capped quick check, as import runs it.
            rows = writer.preflight_project_equipment(RETAIL_INDEX, [(None, SOCK, png)])
            row = next(r for r in rows if r["asset_id"] == SOCK)
            self.assertEqual(row["fit_status"], "needs refit")
            self.assertIsNone(row.get("suggestion"))
            self.assertIn("No fitting smaller size was established", row["fit_error"])
            # The uncapped search, as Build runs it, on the very same bytes.
            fitted, substitutes, refits = writer.auto_refit_group(RETAIL_INDEX, [(SOCK, png)], Path(folder))
            self.assertEqual([r["fit_status"] for r in fitted], ["fits"])
            self.assertEqual([r["asset_id"] for r in refits], [SOCK])
            self.assertIn("16 x 16", refits[0]["fit_summary"])
            self.assertIn(SOCK, substitutes)

    def test_import_stages_that_sock_instead_of_refusing(self):
        # The staging layer must now hand a capped needs-refit to Build rather
        # than raising. Exercised through _checked_rows with a minimal session
        # shaped like the Studio's, so no fixture archive is needed.
        from types import SimpleNamespace
        from mod_editor.core import equipment_staging as staging
        from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
        from mod_editor.core.nfl2k5_equipment_import_intent import with_import_mode
        payload, rgba = _near_white_sock_png()
        by_id, _ = writer.load_targets()
        with tempfile.TemporaryDirectory() as folder:
            png = Path(folder) / "sock.png"
            png.write_bytes(with_import_mode(payload, SOCK, rgba, independent=True, scale=1))
            session = SimpleNamespace(cache=SimpleNamespace(pack0=RETAIL_INDEX,
                                                            source=SimpleNamespace(sha256="a" * 64)),
                                      iter_edits=lambda: iter(()))
            rows = staging._checked_rows(session, {SOCK: png}, by_id, selected=SOCK)
        row = next(r for r in rows if r["asset_id"] == SOCK)
        self.assertEqual(row["fit_status"], "needs refit")


class CappedRowPolicyTests(unittest.TestCase):
    """Jev, 2026-09-20 (0.97): stage measured overflows for Build; refuse
    structural rows at import, since Build cannot cure them and would refuse
    with the same words after minutes of building. No retail data."""

    def _rows(self, row):
        from types import SimpleNamespace
        from unittest.mock import patch
        from mod_editor.core import equipment_staging as staging
        from mod_editor.core import nfl2k5_equipment_lz as lz
        from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
        session = SimpleNamespace(cache=SimpleNamespace(pack0=Path("/nonexistent/pack0"),
                                                        source=SimpleNamespace(sha256="a" * 64)),
                                  iter_edits=lambda: iter(()))
        with patch.object(staging, "_verified_art", return_value="b" * 64), \
                patch("mod_editor.core.nfl2k5_project_fit.equipment_keys", return_value={SOCK: ("k",)}), \
                patch("mod_editor.core.nfl2k5_project_fit.source_hash", return_value="c" * 64), \
                patch.object(writer, "preflight_project_equipment", return_value=[dict(row)]), \
                patch.object(lz, "optimal_fit_is_capped", return_value=True):
            return staging._checked_rows(session, {SOCK: Path("/nonexistent/sock.png")}, {}, selected=SOCK)

    def test_a_capped_measured_overflow_is_staged_for_build(self):
        rows = self._rows(dict(asset_id=SOCK, fit_status="needs refit", budget=6848, required=7639,
                               attempts=(), suggestion=None, required_is_lower_bound=False,
                               fit_error="Equipment art needs refit: it cannot fit and missed the span"))
        self.assertEqual(rows[0]["fit_status"], "needs refit")

    def test_a_capped_structural_refusal_is_raised_at_import(self):
        from mod_editor.core.nfl2k5_uniform_equipment_writer import EquipmentRefitError
        with self.assertRaisesRegex(EquipmentRefitError, "retail loader scratch allowance"):
            self._rows(dict(asset_id=SOCK, fit_status="needs refit", budget=None,
                            fit_error="Equipment cannot fit with the retail loader scratch allowance"))


if __name__ == "__main__":
    unittest.main()
