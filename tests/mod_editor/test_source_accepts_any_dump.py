"""Accepting a disc should not depend on having seen that exact dump before.

Two separate questions get conflated by a hash list:

1. **Is the right game inside this file?** A dump of an Xbox disc is not one
   canonical file -- where the game partition starts, whether trailing padding is
   kept, and how the ripper closed the image all change the whole-file SHA-256
   without changing a byte of the game. ``CONTAINED_FINGERPRINTS`` answers this
   by hashing ``default.xbe`` instead of the container, so any legal dump of a
   supported game is accepted.

2. **What is this disc, when it is not one we support?** A hash list can only
   name dumps somebody has already pinned, so every other Xbox disc came back as
   "Hash is not in the reviewed fingerprint list" -- true, and useless. An XBE
   certificate is self-describing: title ID at ``+0x08`` and a UTF-16LE title
   name at ``+0x0C``, reachable from the header's load base (``+0x104``) and
   certificate address (``+0x118``). ``disc_title`` reads it, so an unsupported
   disc can be named rather than merely rejected.

The distinction that matters: naming a disc is **not** authorising it. Every
writer targets byte offsets derived from one specific game, so ``recognized``
stays false for anything outside the pinned list. Knowing the title makes the
refusal actionable; it does not loosen the gate. These tests pin both halves,
because a future change that made identification imply support would be a
security-shaped regression rather than a feature.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mod_editor.core import sources  # noqa: E402
from mod_editor.core.model import GameId  # noqa: E402

_DISC = _REPO_ROOT / "ESPN NFL 2K5 (USA).xiso.iso"


class DiscTitleTests(unittest.TestCase):
    def test_a_non_disc_file_is_not_guessed_at(self) -> None:
        self.assertIsNone(sources.disc_title(_REPO_ROOT / "README.md"))

    def test_a_missing_file_returns_none_rather_than_raising(self) -> None:
        self.assertIsNone(sources.disc_title(_REPO_ROOT / "no-such-image.iso"))

    def test_the_title_renders_with_its_id(self) -> None:
        title = sources.DiscTitle(0x53450030, "ESPN NFL 2K5")
        self.assertEqual(title.title_id_hex, "0x53450030")
        self.assertEqual(str(title), "ESPN NFL 2K5 (0x53450030)")

    def test_an_unnamed_title_still_renders(self) -> None:
        self.assertEqual(str(sources.DiscTitle(0x1234, "")),
                         "unnamed title (0x00001234)")

    @unittest.skipUnless(_DISC.is_file(), "retail 2K5 disc image not present")
    def test_the_real_disc_names_itself(self) -> None:
        title = sources.disc_title(_DISC)
        self.assertIsNotNone(title)
        assert title is not None
        self.assertEqual(title.title_name, "ESPN NFL 2K5")
        # The title ID is also the name of the disc's own asset directory
        # (``vc_53450030``), which is an independent check on the parse.
        self.assertEqual(title.title_id_hex, "0x53450030")


def _synthetic_xbe(title_id: int, title: str, *, magic: bytes = b"XBEH") -> bytes:
    """A minimal but structurally honest XBE: header, then a certificate.

    Load base `0x00010000`, certificate at `0x00010180`, so the certificate lands
    at file offset `0x180` exactly as a real one does.
    """

    import struct as _struct

    image = bytearray(0x2000)
    image[0:4] = magic
    _struct.pack_into("<I", image, 0x104, 0x00010000)
    _struct.pack_into("<I", image, 0x118, 0x00010180)
    cert = 0x180
    _struct.pack_into("<I", image, cert, 0x100)             # certificate size
    _struct.pack_into("<I", image, cert + 0x08, title_id)
    encoded = title.encode("utf-16-le")[:78]
    image[cert + 0x0C:cert + 0x0C + len(encoded)] = encoded
    return bytes(image)


class LooseExecutableTests(unittest.TestCase):
    """Games arrive as folders too, not only as disc images."""

    def test_a_bare_xbe_is_read(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "default.xbe"
            path.write_bytes(_synthetic_xbe(0x53450022, "ESPN Football 2004"))
            title = sources.disc_title(path)
            self.assertIsNotNone(title)
            assert title is not None
            self.assertEqual(title.title_name, "ESPN Football 2004")
            self.assertEqual(title.title_id_hex, "0x53450022")

    def test_a_directory_holding_one_is_read(self) -> None:
        """An "HDD ready" extraction is a folder; refusing it would be pickiness."""

        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "default.xbe").write_bytes(
                _synthetic_xbe(0x4D530031, "Some Other Game"))
            title = sources.disc_title(root)
            self.assertIsNotNone(title)
            assert title is not None
            self.assertEqual(title.title_name, "Some Other Game")

    def test_a_file_with_the_wrong_magic_is_refused(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "default.xbe"
            path.write_bytes(_synthetic_xbe(1, "Nope", magic=b"NOPE"))
            self.assertIsNone(sources.disc_title(path))

    def test_a_directory_without_an_executable_is_refused(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(sources.disc_title(Path(directory)))


class UnsupportedDiscIsNamedButNotAuthorisedTests(unittest.TestCase):
    """The refusal should say what the disc is, and still refuse."""

    def setUp(self) -> None:
        self._original = sources.disc_title

    def tearDown(self) -> None:
        sources.disc_title = self._original  # type: ignore[assignment]

    def _inspect_with_title(self, title: sources.DiscTitle | None):
        sources.disc_title = lambda _path: title  # type: ignore[assignment]
        # README.md is deliberately not any pinned fingerprint, so inspection
        # falls through to the unrecognised path this test is about.
        return sources.SourceInspector().inspect(_REPO_ROOT / "README.md")

    def test_an_unsupported_disc_is_named_in_the_refusal(self) -> None:
        record = self._inspect_with_title(sources.DiscTitle(0x4D530033, "NFL 2K3"))
        self.assertFalse(record.recognized)
        self.assertIn("NFL 2K3", record.note)
        self.assertIn("0x4D530033", record.note)
        self.assertIn("not a supported source", record.note)

    def test_naming_a_disc_does_not_mark_it_recognized(self) -> None:
        """The regression that would matter: identification implying support."""

        record = self._inspect_with_title(sources.DiscTitle(0x4D530034, "NFL 2K4"))
        self.assertFalse(record.recognized)
        self.assertIsNone(record.fingerprint_id)
        self.assertIsNone(record.detected_game)

    def test_the_refusal_says_which_games_are_supported(self) -> None:
        record = self._inspect_with_title(sources.DiscTitle(0x1234, "Some Game"))
        self.assertIn("ESPN NFL 2K5", record.note)
        self.assertIn("All-Pro Football 2K8", record.note)

    def test_a_file_that_is_not_a_disc_keeps_the_old_message(self) -> None:
        record = self._inspect_with_title(None)
        self.assertFalse(record.recognized)
        self.assertIn("reviewed fingerprint list", record.note)


class AnyLegalDumpIsAcceptedTests(unittest.TestCase):
    def test_the_contained_fingerprint_targets_the_executable(self) -> None:
        """Identity must come from the game, not the container around it."""

        rows = [row for row in sources.CONTAINED_FINGERPRINTS
                if row.game == GameId.NFL2K5]
        self.assertTrue(rows, "2K5 has no contained fingerprint")
        for row in rows:
            self.assertEqual(row.contained_path, "default.xbe")

    @unittest.skipUnless(_DISC.is_file(), "retail 2K5 disc image not present")
    def test_the_real_disc_resolves_through_its_executable(self) -> None:
        contained = sources.contained_identity(_DISC)
        self.assertIsNotNone(contained)
        assert contained is not None
        self.assertEqual(contained.fingerprint_id, "nfl2k5-usa-retail-xiso")
        self.assertEqual(contained.contained_path, "default.xbe")


if __name__ == "__main__":
    unittest.main()
