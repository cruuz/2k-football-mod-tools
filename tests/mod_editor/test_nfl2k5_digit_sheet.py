from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_digit_sheet import split_digit_sheet


@dataclass(frozen=True)
class _Target:
    digit: int
    family: str = "arm"
    set_selector: str = "28H0"
    width: int = 32
    height: int = 32

    @property
    def asset_id(self) -> str:
        return f"28H0:arm_digit:{self.digit}"


def _sheet(path: Path, *, vertical: bool = False, scale: int = 4) -> Path:
    cell = 32 * scale
    size = (cell, cell * 10) if vertical else (cell * 10, cell)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    for digit in range(10):
        colour = (digit * 20, 255 - digit * 20, digit, 255)
        box = (
            (0, digit * cell, cell, (digit + 1) * cell)
            if vertical
            else (digit * cell, 0, (digit + 1) * cell, cell)
        )
        image.paste(colour, box)
    image.save(path)
    return path


class DigitSheetTests(unittest.TestCase):
    def test_high_resolution_sheet_becomes_ten_exact_target_pngs(self) -> None:
        for vertical in (False, True):
            with self.subTest(vertical=vertical):
                with tempfile.TemporaryDirectory() as temporary:
                    outputs = split_digit_sheet(
                        _sheet(
                            Path(temporary) / "digits.png", vertical=vertical
                        ),
                        tuple(_Target(digit) for digit in range(10)),
                    )
                self.assertEqual(
                    [row.digit for row in outputs], list(range(10))
                )
                self.assertEqual(len({row.asset_id for row in outputs}), 10)
                for row in outputs:
                    with Image.open(BytesIO(row.png)) as image:
                        self.assertEqual(image.mode, "RGBA")
                        self.assertEqual(image.size, (32, 32))
                        self.assertEqual(
                            image.getpixel((16, 16))[0], row.digit * 20
                        )

    def test_per_target_dimensions_are_used_instead_of_a_family_default(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            targets = tuple(
                _Target(
                    digit,
                    width=32 if digit < 5 else 64,
                    height=32 if digit < 5 else 64,
                )
                for digit in range(10)
            )
            outputs = split_digit_sheet(
                _sheet(Path(temporary) / "digits.png"), targets
            )
        self.assertEqual(
            [(row.width, row.height) for row in outputs],
            [*((32, 32),) * 5, *((64, 64),) * 5],
        )

    def test_missing_digit_or_mixed_family_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = _sheet(Path(temporary) / "digits.png")
            with self.assertRaisesRegex(ValidationError, "exactly the ten"):
                split_digit_sheet(
                    source, tuple(_Target(digit) for digit in range(9))
                )
            mixed = tuple(
                _Target(digit, family="helmet" if digit == 9 else "arm")
                for digit in range(10)
            )
            with self.assertRaisesRegex(ValidationError, "one family"):
                split_digit_sheet(source, mixed)


if __name__ == "__main__":
    unittest.main()
