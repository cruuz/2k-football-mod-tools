"""Conformance suite for the bounded PS2 text catalog, patcher and verifier.

**No game data.** Every image here is built from scratch into a temp directory:
a real ISO9660 volume, a real ``/VC_20919`` pack archive, a real 0x20 chunk
header and a real UTF-16LE ``STRG`` bank with a real record table and a real
string pool.  A CI runner with an empty disk runs all of it green, which is the
only way these checks keep running -- gating them on a 4.3 GB retail disc would
mean nobody ever ran them.

The two most valuable tests in this file are the ones that require a **failure**:

* ``test_verifier_fails_on_a_byte_changed_outside_the_lane`` flips one byte
  somewhere else in the image and requires the verifier to raise.  A verifier
  that cannot fail is a rubber stamp.
* ``test_verifier_fails_when_a_neighbouring_string_also_changed`` rewrites a
  string the recipe never named.  That is the exact shape of the bug this whole
  surface exists to prevent -- an edit that quietly moves or overwrites its
  neighbour -- and it must be caught even though the image is still structurally
  valid and still the right size.

Everything the writer refuses is asserted to leave **no destination behind**.  A
half-written 4.3 GB ISO that looks plausible is worse than no ISO at all.
"""

from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOLS = _REPO_ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import nfl2k5_ps2_text_target_catalog as text_catalog  # noqa: E402
import nfl2k5_ps2_text_patch as text_patch  # noqa: E402
import nfl2k5_ps2_text_verify as text_verify  # noqa: E402
import ps2_iso9660 as iso  # noqa: E402
import ps2_iso9660_verify as iso_verify  # noqa: E402


# The synthetic disc lives in the tool, not here: the lane's validator has to
# prove itself in a shipped tree, where ``tests/`` does not exist, so the
# builder and the claims it supports are reachable as
# ``nfl2k5_ps2_text_target_catalog.py --selftest`` and the patcher's own.  These
# tests drive the same builder, so the two cannot drift.
build_synthetic_iso = text_catalog.build_synthetic_iso
BANK_TEXTS = text_catalog.SYNTHETIC_TEXTS
MENU_INDEX = text_catalog.SYNTHETIC_MENU_INDEX
TOKEN_INDEX = text_catalog.SYNTHETIC_TOKEN_INDEX
PRINTF_INDEX = text_catalog.SYNTHETIC_PRINTF_INDEX
EMPTY_INDEX = text_catalog.SYNTHETIC_EMPTY_INDEX
OPTIONS_INDEX = text_catalog.SYNTHETIC_OPTIONS_INDEX

BANK_ID = text_catalog.SYNTHETIC_BANK_ID


def _recipe(*edits) -> dict:
    return {"edits": [{"bank": BANK_ID, "index": index, "new_text": text}
                      for index, text in edits]}


class _Fixture(unittest.TestCase):
    """A fresh synthetic disc per test, in its own temp directory."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="nfl2k5-ps2-text-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.source = self.root / "source.iso"
        self.source.write_bytes(build_synthetic_iso())
        self.destination = self.root / "output.iso"

    def write_source(self, data: bytes) -> None:
        self.source.write_bytes(data)

    def patch(self, recipe: dict) -> dict:
        return text_patch.patch(source_iso=self.source,
                                destination_iso=self.destination,
                                edits=recipe["edits"])

    def verify(self, recipe: dict, report=None) -> dict:
        return text_verify.verify(
            source_iso=self.source, destination_iso=self.destination,
            recipe=recipe,
            patch_report=report,
            iso_write_report=None if report is None
            else report.get("iso_write_report"))


class CatalogTests(_Fixture):
    def test_it_finds_the_bank_and_decodes_every_string(self) -> None:
        catalog = text_catalog.build_catalog(str(self.source))
        self.assertEqual(catalog["summary"]["bank_count"], 1)
        self.assertEqual(catalog["summary"]["decoded_bank_count"], 1)
        self.assertEqual(catalog["summary"]["string_count"], len(BANK_TEXTS))
        bank = catalog["banks"][0]
        self.assertEqual(bank["bank_id"], BANK_ID)
        self.assertEqual(bank["encoding"], "utf-16le")
        self.assertTrue(bank["rebuild_byte_identical"])
        self.assertFalse(bank["compressed"])
        self.assertFalse(bank["crosses_pack_boundary"])

    def test_a_terminator_only_allocation_is_read_only(self) -> None:
        catalog = text_catalog.build_catalog(str(self.source))
        rows = {row["pool_index"]: row for row in catalog["strings"]}
        self.assertFalse(rows[EMPTY_INDEX]["editable"])
        self.assertEqual(rows[EMPTY_INDEX]["reason_code"], "terminator_only")
        self.assertTrue(rows[MENU_INDEX]["editable"])

    def test_it_records_tokens_and_never_the_text_itself(self) -> None:
        catalog = text_catalog.build_catalog(str(self.source))
        rows = {row["pool_index"]: row for row in catalog["strings"]}
        self.assertEqual(rows[TOKEN_INDEX]["tokens"], ["|CROSS|"])
        self.assertEqual(rows[PRINTF_INDEX]["tokens"], ["%d"])
        blob = json.dumps(catalog)
        for text in BANK_TEXTS:
            if len(text) > 3 and "|" not in text and "%" not in text:
                self.assertNotIn(text, blob,
                                 "the catalog leaked a decoded string")

    def test_a_compressed_bank_is_reported_undecoded(self) -> None:
        self.write_source(build_synthetic_iso(compressed=True))
        catalog = text_catalog.build_catalog(str(self.source))
        bank = catalog["banks"][0]
        self.assertTrue(bank["compressed"])
        self.assertFalse(bank["decoded"])
        self.assertEqual(catalog["summary"]["string_count"], 0)


class PatchAndVerifyTests(_Fixture):
    def test_a_same_length_edit_writes_and_verifies(self) -> None:
        recipe = _recipe((MENU_INDEX, "PLAY"))
        report = self.patch(recipe)
        self.assertTrue(self.destination.exists())
        self.assertEqual(self.destination.stat().st_size,
                         self.source.stat().st_size)
        result = self.verify(recipe, report)
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(len(result["edits"]), 1)
        self.assertTrue(result["checks"]["iso9660_verifier_passed"])

    def test_a_shorter_edit_zero_fills_the_rest_of_its_allocation(self) -> None:
        recipe = _recipe((OPTIONS_INDEX, "OFF"))
        report = self.patch(recipe)
        result = self.verify(recipe, report)
        self.assertEqual(result["verdict"], "pass")
        edit = result["edits"][0]
        self.assertEqual(edit["allocation_bytes"], len("OPTIONS") * 2 + 2)
        self.assertEqual(edit["new_code_units"], 3)
        # "OFF" + terminator + zero fill, read straight out of the image.
        with self.source.open("rb") as stream:
            stream.seek(edit["iso_byte_offset"])
            before = stream.read(edit["allocation_bytes"])
        with self.destination.open("rb") as stream:
            stream.seek(edit["iso_byte_offset"])
            after = stream.read(edit["allocation_bytes"])
        self.assertEqual(after, "OFF".encode("utf-16le") + b"\0\0" + bytes(8))
        self.assertNotEqual(before, after)

    def test_shortening_the_last_string_in_the_pool_verifies(self) -> None:
        """The case the real disc caught and the first synthetic pass missed.

        The last allocation has no following pointer to bound it, so a verifier
        that derives each allocation's end from the *destination* alone reads a
        shortened final string as "the pool shrank" and fails a legitimate
        edit.  The source's boundaries are what settle it.
        """
        last_index = len(BANK_TEXTS) - 1
        self.assertEqual(BANK_TEXTS[last_index], "OPT")
        recipe = _recipe((last_index, "GO"))
        report = self.patch(recipe)
        result = self.verify(recipe, report)
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["edits"][0]["new_code_units"], 2)

    def test_several_edits_in_one_run_all_land(self) -> None:
        recipe = _recipe((MENU_INDEX, "PLAY"), (OPTIONS_INDEX, "SETUP"))
        report = self.patch(recipe)
        result = self.verify(recipe, report)
        self.assertEqual(len(result["edits"]), 2)
        self.assertEqual({edit["pool_index"] for edit in result["edits"]},
                         {MENU_INDEX, OPTIONS_INDEX})

    def test_the_source_image_is_not_touched(self) -> None:
        before = self.source.read_bytes()
        self.patch(_recipe((MENU_INDEX, "PLAY")))
        self.assertEqual(self.source.read_bytes(), before)

    def test_an_edit_carrying_its_token_through_is_allowed(self) -> None:
        recipe = _recipe((TOKEN_INDEX, "Tap |CROSS| now"))
        report = self.patch(recipe)
        result = self.verify(recipe, report)
        self.assertEqual(result["edits"][0]["tokens"], ["|CROSS|"])


class RefusalTests(_Fixture):
    def _refuses(self, recipe: dict, fragment: str) -> None:
        with self.assertRaises(text_patch.TextPatchError) as caught:
            self.patch(recipe)
        self.assertIn(fragment, str(caught.exception).lower())
        self.assertFalse(self.destination.exists(),
                         "a refused run left a destination behind")

    def test_it_refuses_a_replacement_one_character_too_long(self) -> None:
        self._refuses(_recipe((MENU_INDEX, "PLAYS")), "code units")

    def test_it_refuses_an_empty_replacement(self) -> None:
        self._refuses(_recipe((MENU_INDEX, "")), "empty")

    def test_it_refuses_dropping_an_inline_token(self) -> None:
        self._refuses(_recipe((TOKEN_INDEX, "Press start to go")), "drops")

    def test_it_refuses_adding_an_inline_token(self) -> None:
        self._refuses(_recipe((MENU_INDEX, "|L1|")), "introduces")

    def test_it_refuses_dropping_a_printf_conversion(self) -> None:
        self._refuses(_recipe((PRINTF_INDEX, "Score")), "drops")

    def test_it_refuses_a_read_only_allocation(self) -> None:
        self._refuses(_recipe((EMPTY_INDEX, "X")), "read-only")

    def test_it_refuses_an_edit_that_changes_nothing(self) -> None:
        self._refuses(_recipe((MENU_INDEX, "MENU")), "would not change")

    def test_it_refuses_an_unknown_bank(self) -> None:
        recipe = {"edits": [{"bank": "nfl2k5.ps2.text-bank.strg.9.9",
                             "index": 0, "new_text": "X"}]}
        self._refuses(recipe, "does not have")

    def test_it_refuses_an_index_the_bank_does_not_have(self) -> None:
        self._refuses(_recipe((999, "X")), "does not have")

    def test_it_refuses_two_edits_on_one_allocation(self) -> None:
        recipe = _recipe((MENU_INDEX, "PLAY"))
        recipe["edits"].append({"bank": BANK_ID, "index": MENU_INDEX,
                                "new_text": "QUIT"})
        self._refuses(recipe, "both target")

    def test_it_refuses_a_stale_expected_digest(self) -> None:
        recipe = _recipe((MENU_INDEX, "PLAY"))
        recipe["edits"][0]["expect_sha256"] = "0" * 64
        self._refuses(recipe, "expected the string")

    def test_it_refuses_a_compressed_bank_rather_than_recompressing(self) -> None:
        """No text bank on the retail disc is LZ-compressed.

        Rather than carry an unexercised recompress-to-fit path, the patcher
        refuses.  If a disc revision ever compresses one, this refusal is the
        correct answer until that path exists and is proved.
        """
        self.write_source(build_synthetic_iso(compressed=True))
        self._refuses(_recipe((MENU_INDEX, "PLAY")), "compressed")

    def test_it_refuses_when_the_destination_already_exists(self) -> None:
        self.destination.write_bytes(b"not an iso")
        with self.assertRaises(text_patch.TextPatchError):
            self.patch(_recipe((MENU_INDEX, "PLAY")))
        self.assertEqual(self.destination.read_bytes(), b"not an iso")


class VerifierMustBeAbleToFailTests(_Fixture):
    """The tests that make the verifier worth having."""

    def _good_output(self):
        recipe = _recipe((MENU_INDEX, "PLAY"))
        report = self.patch(recipe)
        return recipe, report

    def _flip(self, offset: int) -> None:
        data = bytearray(self.destination.read_bytes())
        data[offset] ^= 0xFF
        self.destination.write_bytes(bytes(data))

    def test_verifier_fails_on_a_byte_changed_inside_the_same_pack(self) -> None:
        """The hardest place to hide a stray byte: the file the writer replaced.

        The ISO writer declares the whole 1 GiB pack extent as written, so the
        ISO-level verifier cannot tell a stray byte in there from an intended
        one.  Only comparing the two images byte for byte can.
        """
        recipe, report = self._good_output()
        self.assertEqual(self.verify(recipe, report)["verdict"], "pass")
        catalog = text_catalog.build_catalog(str(self.source))
        bank = catalog["banks"][0]
        # Just past the bank's body, in the pack's block padding.
        self._flip(bank["iso_byte_offset"] + bank["stored_size"] + 4)
        with self.assertRaises(text_verify.TextVerifyError) as caught:
            self.verify(recipe, report)
        self.assertIn("outside the edited allocations", str(caught.exception))

    def test_verifier_fails_on_a_byte_changed_in_another_file(self) -> None:
        recipe, report = self._good_output()
        self._flip(self.destination.stat().st_size - 1)
        with self.assertRaises(text_verify.TextVerifyError) as caught:
            self.verify(recipe, report)
        self.assertIn("outside the edited allocations", str(caught.exception))

    def test_verifier_fails_when_a_neighbouring_string_also_changed(self) -> None:
        """The failure mode this whole surface exists to prevent.

        The forged edit is the *subtle* one: an exactly-same-length overwrite
        of a string the recipe never mentions.  The pool still tiles, every
        pointer still resolves, the image is still the right size and still a
        valid ISO -- so nothing structural catches it.  Only comparing every
        untouched allocation against the source does.
        """
        recipe, report = self._good_output()
        catalog = text_catalog.build_catalog(str(self.source))
        rows = {row["pool_index"]: row for row in catalog["strings"]}
        bank = catalog["banks"][0]
        neighbour = rows[OPTIONS_INDEX]
        offset = bank["iso_byte_offset"] + neighbour["body_offset"]
        replacement = "SETTING".encode("utf-16le") + b"\0\0"
        self.assertEqual(len(replacement), neighbour["allocation_bytes"],
                         "the forgery must be exactly the same length")
        data = bytearray(self.destination.read_bytes())
        data[offset:offset + len(replacement)] = replacement
        self.destination.write_bytes(bytes(data))
        with self.assertRaises(text_verify.TextVerifyError) as caught:
            self.verify(recipe, report)
        self.assertIn("does not name it", str(caught.exception))

    def test_verifier_fails_when_a_pointer_moved(self) -> None:
        recipe, report = self._good_output()
        catalog = text_catalog.build_catalog(str(self.source))
        bank = catalog["banks"][0]
        record_field = bank["iso_byte_offset"] + bank["descriptor_offset"] + 4 + 8
        data = bytearray(self.destination.read_bytes())
        struct.pack_into("<I", data, record_field, 1)
        self.destination.write_bytes(bytes(data))
        with self.assertRaises(text_verify.TextVerifyError):
            self.verify(recipe, report)

    def test_verifier_fails_when_the_image_changed_size(self) -> None:
        recipe, report = self._good_output()
        with self.destination.open("ab") as stream:
            stream.write(b"\0" * 2048)
        with self.assertRaises(text_verify.TextVerifyError) as caught:
            self.verify(recipe, report)
        self.assertIn("different sizes", str(caught.exception))

    def test_verifier_fails_when_the_recipe_does_not_match_the_output(self) -> None:
        recipe, report = self._good_output()
        wrong = _recipe((MENU_INDEX, "QUIT"))
        with self.assertRaises(text_verify.TextVerifyError):
            self.verify(wrong, report)

    def test_verifier_rejects_a_patch_report_that_disagrees(self) -> None:
        recipe, report = self._good_output()
        forged = json.loads(json.dumps(report))
        forged["edits"][0]["allocation_bytes"] = 4
        with self.assertRaises(text_verify.TextVerifyError) as caught:
            self.verify(recipe, forged)
        self.assertIn("disagree", str(caught.exception))


class IndependenceTests(unittest.TestCase):
    """The verifier must not lean on the code it is checking."""

    def test_the_verifier_imports_neither_the_patcher_nor_the_writers_reader(
            self) -> None:
        source = (_TOOLS / "nfl2k5_ps2_text_verify.py").read_text(encoding="utf-8")
        for forbidden in ("import nfl2k5_ps2_text_patch",
                          "import nfl2k5_ps2_text_target_catalog",
                          "import ps2_iso9660_writer",
                          "import ps2_iso9660\n",
                          "import ps2_iso9660 "):
            self.assertNotIn(forbidden, source,
                             "the verifier imports %r" % forbidden)

    def test_each_tool_has_a_passing_selftest(self) -> None:
        self.assertEqual(text_catalog.selftest(), 0)
        self.assertEqual(text_patch.selftest(), 0)
        self.assertEqual(text_verify.selftest(), 0)


class IsoLevelTests(_Fixture):
    def test_the_iso_verifier_agrees_the_write_was_bounded(self) -> None:
        recipe = _recipe((MENU_INDEX, "PLAY"))
        report = self.patch(recipe)
        outcome = iso_verify.verify_replacement(
            str(self.source), str(self.destination), report["iso_write_report"])
        self.assertTrue(outcome)

    def test_the_directory_tree_is_unchanged(self) -> None:
        self.patch(_recipe((MENU_INDEX, "PLAY")))
        before = iso_verify.inspect(str(self.source))
        after = iso_verify.inspect(str(self.destination))
        self.assertEqual(before["entries"], after["entries"])


if __name__ == "__main__":
    unittest.main()
