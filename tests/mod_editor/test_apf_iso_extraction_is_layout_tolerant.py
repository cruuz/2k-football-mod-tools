"""The APF disc reader must find the filesystem, not guess where it is.

A Windows user on beta-11 hit::

    APF ISO extraction failed: All-Pro Football 2K8 (USA).iso does not appear
    to be a valid xbox iso image

That message comes from the bundled ``extract-xiso``, which probes exactly four
partition offsets -- 0, 0x0FD90000, 0x02080000, 0x18300000 -- and rejects the
image if none of them carries the XDVDFS magic.  It is the same defect the 2K5
source lane was already fixed for: a layout measured on one machine treated as
the only legal layout.  A list of four guesses is still guessing, and the 2K5
side proved that real dumps land outside such lists.

So the APF lane now reads the image with our own XDVDFS reader first, which
*searches* sector-aligned positions for the magic and confirms a candidate by
requiring it at both ends of the header sector.  The bundled tool stays as a
fallback, so nothing that worked before can stop working.

These are synthetic images built in-process.  No retail data is involved.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mod_editor.apf_studio import source as apf_source  # noqa: E402
from tests.mod_editor.test_xiso_layout_tolerance import build_xdvdfs  # noqa: E402

# The four offsets the bundled extractor knows about, from its own C source.
_EXTRACT_XISO_OFFSETS = (0, 0x0FD90000, 0x02080000, 0x18300000)
# One it does not know about, small enough to build in memory.
_UNKNOWN_OFFSET = 0x30000

_PAYLOAD = {
    "default.xex": b"XEX2" + bytes(range(256)) * 4,
    "0a": bytes(range(256)) * 8,
    "0b": b"\xff" * 900,
}
_SIZES = {name: len(blob) for name, blob in _PAYLOAD.items()}


class ApfIsoLayoutToleranceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _image(self, base_offset: int) -> Path:
        path = self.root / f"apf-{base_offset:x}.iso"
        path.write_bytes(build_xdvdfs(_PAYLOAD, base_offset=base_offset))
        return path

    def _extract(self, image: Path) -> tuple[str | None, Path]:
        staging = Path(tempfile.mkdtemp(dir=self.root))
        manager = apf_source.SourceManager(cache_root=self.root / "cache")
        with mock.patch.object(apf_source, "EXPECTED_GAME_FILES", _SIZES):
            outcome = manager._extract_native(image, staging, lambda *_: None)
        return (None if outcome is None else outcome[0]), staging

    def _definitive(self, image: Path) -> bool:
        staging = Path(tempfile.mkdtemp(dir=self.root))
        manager = apf_source.SourceManager(cache_root=self.root / "cache")
        with mock.patch.object(apf_source, "EXPECTED_GAME_FILES", _SIZES):
            outcome = manager._extract_native(image, staging, lambda *_: None)
        return bool(outcome and outcome[1])

    def test_every_offset_the_bundled_tool_knows_is_still_read(self) -> None:
        """No regression: the layouts that worked before must keep working."""
        for base in _EXTRACT_XISO_OFFSETS:
            if base > 1 << 26:  # too large to materialize in a unit test
                continue
            with self.subTest(base=hex(base)):
                reason, staging = self._extract(self._image(base))
                self.assertIsNone(reason, f"0x{base:X} must still extract")
                for name, blob in _PAYLOAD.items():
                    self.assertEqual((staging / name).read_bytes(), blob)

    def test_an_offset_the_bundled_tool_would_reject_is_extracted(self) -> None:
        """The actual bug: a partition somewhere extract-xiso never looks."""
        self.assertNotIn(_UNKNOWN_OFFSET, _EXTRACT_XISO_OFFSETS)
        reason, staging = self._extract(self._image(_UNKNOWN_OFFSET))
        self.assertIsNone(
            reason,
            "a dump whose partition sits outside the four known offsets must "
            "still be read -- refusing it is the reported bug",
        )
        for name, blob in _PAYLOAD.items():
            self.assertEqual((staging / name).read_bytes(), blob)

    def test_extraction_reads_only_the_files_the_editor_needs(self) -> None:
        _, staging = self._extract(self._image(0))
        written = sorted(p.name for p in staging.rglob("*") if p.is_file())
        self.assertEqual(written, sorted(_SIZES))

    def test_a_file_that_is_not_a_disc_image_is_refused_with_a_reason(self) -> None:
        """Negative control: junk must fail, and say something useful."""
        junk = self.root / "not-a-disc.iso"
        junk.write_bytes(b"NOT A DISC" * 4096)
        reason, staging = self._extract(junk)
        self.assertIsNotNone(reason, "junk must not be reported as extracted")
        self.assertEqual([p for p in staging.rglob("*") if p.is_file()], [])

    def test_a_disc_missing_a_needed_file_is_refused_by_name(self) -> None:
        """Negative control: a real filesystem without the game in it."""
        path = self.root / "wrong-game.iso"
        path.write_bytes(
            build_xdvdfs({"default.xex": _PAYLOAD["default.xex"], "readme": b"hi"})
        )
        reason, _ = self._extract(path)
        self.assertIsNotNone(reason)
        self.assertIn("0a", str(reason).lower())

    def test_a_needed_file_of_the_wrong_size_is_refused(self) -> None:
        """Identity still holds: the per-file ledger is the real gate."""
        path = self.root / "wrong-size.iso"
        payload = dict(_PAYLOAD)
        payload["0b"] = b"\x00" * (len(_PAYLOAD["0b"]) - 1)
        path.write_bytes(build_xdvdfs(payload))
        reason, _ = self._extract(path)
        self.assertIsNotNone(reason)
        self.assertIn("size", str(reason).lower())

    def test_the_bundled_extractor_is_no_longer_required_to_exist(self) -> None:
        """A missing bundled binary must not block a readable image.

        It was resolved with ``strict=True`` before any image was looked at, so
        an installation that shipped without it failed on every ISO, including
        ones the native reader handles fine.
        """
        image = self._image(0)
        staging = Path(tempfile.mkdtemp(dir=self.root))
        manager = apf_source.SourceManager(
            cache_root=self.root / "cache2",
            extract_xiso=self.root / "does-not-exist",
        )
        with mock.patch.object(apf_source, "EXPECTED_GAME_FILES", _SIZES):
            self.assertIsNone(manager._extract_native(image, staging, lambda *_: None))

    def test_a_playstation_3_disc_is_named_instead_of_called_invalid(self) -> None:
        """The report that mattered: a PS3 disc of the same game, named .iso.

        extract-xiso answered "does not appear to be a valid xbox iso image",
        which reads as a bad dump, so the user re-dumped a disc that was fine.
        It was the PlayStation 3 release. Say that.
        """
        path = self.root / "ps3.iso"
        blob = bytearray(0x8000 + 4096)
        blob[0x8000:0x8006] = b"\x01CD001"
        blob[0x8028:0x8028 + 6] = b"APF2K8"
        blob[0x9000:0x9000 + 8] = b"PS3_GAME"
        path.write_bytes(bytes(blob))
        reason, _ = self._extract(path)
        self.assertIn("PlayStation 3", str(reason))
        self.assertIn("APF2K8", str(reason))
        self.assertTrue(
            self._definitive(path),
            "a positively identified container must not also run the bundled "
            "extractor, whose vaguer failure would bury the real answer",
        )

    def test_an_unrecognized_file_still_falls_back(self) -> None:
        """Only a positive identification may skip the bundled extractor."""
        junk = self.root / "mystery.iso"
        junk.write_bytes(b"\x00" * (1 << 20))
        self.assertFalse(self._definitive(junk))

    def test_both_failures_are_reported_together(self) -> None:
        """When neither reader works, say so -- don't blame the disc alone."""
        staging = Path(tempfile.mkdtemp(dir=self.root))
        manager = apf_source.SourceManager(
            cache_root=self.root / "cache3",
            extract_xiso=self.root / "does-not-exist",
        )
        with self.assertRaises(apf_source.SourceError) as caught:
            manager._extract_with_bundled_tool(
                self.root / "whatever.iso",
                staging,
                lambda *_: None,
                "no XDVDFS filesystem was found",
            )
        self.assertIn("no XDVDFS filesystem was found", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
