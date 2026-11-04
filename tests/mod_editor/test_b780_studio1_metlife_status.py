"""b780 studio1: reading a disc's MetLife state never loops.

``nfl2k5_modern_metlife.image_status`` asks ``nfl2k5_metlife_model.image_status`` when the skin reads foreign or mixed
and the roster is applied, and the model's fallback asked ``modern_metlife.image_status`` again.  On a disc whose bundles
are neither the skin nor the model (Modern colour over the skin: the SOFTDRINK pack) the two called each other, each
turn re-reading the disc, until RecursionError.  The released v0.8 disc took 23 minutes to fail that way, and the
Studio's 180 second limit on reading a disc ended Build's option read first.  Synthetic discs only.
"""

from __future__ import annotations

import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_metlife_model as model  # noqa: E402
from mod_editor.core import nfl2k5_modern_metlife as skin  # noqa: E402

BUNDLE_SIZE, CROWD_SIZE = 64, 32


class _Entry:
    name_id, size, virtual_offset = 7, BUNDLE_SIZE, 0


class _CrowdEntry:
    name_id, size, virtual_offset = 8, CROWD_SIZE, 0


class _Archive:
    """An image whose one bundle holds bytes that are neither the skin's nor the model's, and one crowd outer."""

    def __init__(self, bundle: bytes, crowd: bytes) -> None:
        self.entries = [_Entry(), _CrowdEntry()]
        self._bundle, self._crowd = bundle, crowd

    def read(self, offset: int, length: int) -> bytes:
        return (self._bundle if length == 16 else self._crowd)[:length]


def _pins(crowd_retail: bytes) -> dict:
    return {
        "schema": model.PINS_SCHEMA,
        "bundles": [{"outer": 0, "name_id": 7, "size": BUNDLE_SIZE, "offset": 0, "length": 16,
                     "skin_sha256": model.sha(b"S" * 16), "model_sha256": model.sha(b"M" * 16)}],
        "crowd": [{"outer": 1, "name_id": 8, "size": CROWD_SIZE, "offset": 0, "length": 8,
                   "retail_sha256": model.sha(crowd_retail), "applied_sha256": model.sha(b"A" * 8)}],
    }


@contextmanager
def _disc(skin_state: str, crowd: bytes, *, roster: str = "applied"):
    archive = _Archive(b"X" * 16, crowd)

    @contextmanager
    def opened(_source):
        yield archive

    with mock.patch.object(model, "model_pins", return_value=_pins(b"R" * 8)), \
            mock.patch.object(skin, "_outer_image", return_value=opened), \
            mock.patch.object(skin, "_skin_status", return_value=skin_state), \
            mock.patch.object(skin, "_rost_state", return_value=roster):
        yield


class MetLifeStatusDoesNotLoopTests(unittest.TestCase):
    def test_a_disc_that_is_neither_the_skin_nor_the_model_reads_foreign(self) -> None:
        with _disc("foreign", b"R" * 8):
            self.assertEqual(skin.image_status("disc.iso"), "foreign")
            self.assertEqual(model.image_status("disc.iso"), "foreign")
        with _disc("mixed", b"R" * 8):
            self.assertEqual(skin.image_status("disc.iso"), "mixed")

    def test_the_depth_of_the_calls_is_flat(self) -> None:
        depth = []
        original = model.image_status

        def counted(source):
            depth.append(1)
            if len(depth) > 4:
                raise AssertionError("the model's status asked the skin's status, which asked it again")
            return original(source)

        with _disc("foreign", b"R" * 8), mock.patch.object(model, "image_status", counted):
            self.assertEqual(skin.image_status("disc.iso"), "foreign")
        self.assertEqual(len(depth), 1)

    def test_a_disc_the_skin_has_not_touched_still_reads_retail(self) -> None:
        with _disc("retail", b"R" * 8):
            self.assertEqual(model.image_status("disc.iso"), "retail")
        with _disc("foreign", b"R" * 8, roster="retail"):
            self.assertEqual(model.image_status("disc.iso"), "foreign")   # the skin ran (or something else did)
        with _disc("retail", b"Q" * 8):
            self.assertEqual(model.image_status("disc.iso"), "foreign")   # crowd scenes changed: not retail


if __name__ == "__main__":
    unittest.main()
