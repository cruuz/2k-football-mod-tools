"""Not every byte in the rating block is a 0-99 magnitude.

Measured over the 1,437 stock records with a populated rating block:

* `0xBD` holds 8 distinct values across 10..90 and `0xC5` holds 17 -- both behave
  like ordinary ratings, even though the executable does not name either.
* Kicking Style (`0xD1`) holds 49 at every field position, 99 for the 30 kickers
  and 1 for the 30 punters. That is an index, not a magnitude.
* `0xD2` holds **0 in 1,433 records and 1 in 2**, plus 50 in the two malformed
  records that also read 50 at `0xD1` and `0xD7`. Also an index.

Offering an index as a free 0-99 slider would let a modder write a value the game
has never been shown, which is the shape of edit this project refuses rather than
ships. The guard lives in the writer so every route in is covered -- desktop
panel, ratings CSV, CLI -- instead of one dropdown in one panel.

Leadership (`0xD3`, constant 50 everywhere) and Consistency (`0xD7`, 99 in 1,435
of 1,437) are recorded as constants but deliberately NOT refused: writing a
different value there is pointless rather than dangerous, and blocking it would
remove capability to prevent nothing. `0xD4` is a quantized axis (1/25/50/99) and
stays free for the same reason -- the game almost certainly thresholds it.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.apf_studio.player_ratings import (  # noqa: E402
    ENUMERATED_DOMAIN,
    load_player_rating_schema,
)

import apf_player_rating_patch as writer  # noqa: E402


SCHEMA = load_player_rating_schema()


def _field(offset: int):
    return next(
        item for item in SCHEMA.fields if item.relative_offset == offset
    )


class ValueDomainTests(unittest.TestCase):
    def test_only_the_style_enum_is_restricted(self) -> None:
        """Exactly one byte is a fixed set.  Restricting more would cost capability."""

        restricted = {
            item.relative_offset_hex
            for item in SCHEMA.fields
            if not item.free_0_99
        }
        self.assertEqual(restricted, {"0xD1", "0xD2"})

    def test_an_index_byte_refuses_an_unobserved_value(self) -> None:
        style = _field(0xD2)
        self.assertEqual(style.label, "Unknown Rating (0xD2)")
        self.assertEqual(style.value_domain, ENUMERATED_DOMAIN)
        self.assertEqual(style.observed_stock_values, (0, 1, 50))
        for allowed in style.observed_stock_values:
            self.assertEqual(
                writer.validate_field_value(style.field_id, allowed), allowed
            )
        for refused in (2, 47, 99):
            with self.subTest(value=refused):
                with self.assertRaisesRegex(
                    writer.PlayerRatingPatchError, "fixed set of values"
                ):
                    writer.validate_field_value(style.field_id, refused)

    def test_an_ordinary_rating_still_takes_any_exact_0_to_99(self) -> None:
        for offset in (0xBA, 0xBD, 0xC5, 0xD4):
            field = _field(offset)
            with self.subTest(field=field.label):
                self.assertTrue(field.free_0_99)
                for value in (0, 1, 47, 99):
                    self.assertEqual(
                        writer.validate_field_value(field.field_id, value), value
                    )

    def test_the_constants_are_recorded_but_not_blocked(self) -> None:
        """Pointless is not the same as dangerous.

        Both bytes carry an executable-proved name (Leadership, Consistency); APF
        simply shipped them unvaried.
        """

        for offset in (0xD3, 0xD7):
            field = _field(offset)
            with self.subTest(field=field.relative_offset_hex):
                self.assertTrue(field.named)
                self.assertEqual(field.value_domain, "constant")
                self.assertTrue(field.free_0_99)
                self.assertEqual(writer.validate_field_value(field.field_id, 42), 42)

    def test_the_range_check_still_applies_to_every_field(self) -> None:
        for offset in (0xBA, 0xD2, 0xD4):
            field = _field(offset)
            with self.subTest(field=field.label):
                for refused in (-1, 100, 255):
                    with self.assertRaises(writer.PlayerRatingPatchError):
                        writer.validate_field_value(field.field_id, refused)
                with self.assertRaises(writer.PlayerRatingPatchError):
                    writer.validate_field_value(field.field_id, "50")

    def test_an_unknown_field_id_is_refused(self) -> None:
        with self.assertRaisesRegex(
            writer.PlayerRatingPatchError, "no player rating"
        ):
            writer.validate_field_value("not_a_rating", 50)

    def test_a_batch_edit_goes_through_the_domain_check(self) -> None:
        """``normalize_replacements`` is the CSV and GUI batch route."""

        style = _field(0xD2)
        with self.assertRaisesRegex(
            writer.PlayerRatingPatchError, "fixed set of values"
        ):
            writer.normalize_replacements({0: {style.field_id: 47}})
        rows = writer.normalize_replacements({0: {style.field_id: 1}})
        self.assertEqual([value for _target, value in rows], [1])

    def test_every_recorded_stock_value_set_is_ascending_and_in_range(self) -> None:
        for field in SCHEMA.fields:
            if not field.observed_stock_values:
                continue
            with self.subTest(field=field.label):
                values = field.observed_stock_values
                self.assertEqual(sorted(set(values)), list(values))
                self.assertTrue(all(0 <= value <= 100 for value in values))


if __name__ == "__main__":
    unittest.main()
