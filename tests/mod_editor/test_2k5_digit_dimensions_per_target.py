"""Digit dimensions are a property of the target, not of the family.

A modder reported Titans arm/shoulder numbers missing from the uniform preview.
The assets were catalogued the whole time; what was wrong was their size.
``_component_specs`` assigned one constant per family -- jersey 64, helmet 32,
arm 64 -- but retail did not author them that way:

===============  ==============  =============
family           majority size   minority
===============  ==============  =============
``arm_digit``    5,960 x 64x64   **380 x 32x32**
``helmet_digit`` 6,140 x 32x32   **200 x 64x64**
``jersey_digit`` 6,340 x 64x64   none
===============  ==============  =============

So 580 targets were handed the wrong dimensions, and everything downstream --
preview, Replace, Team Kit export, manifest dimensions -- inherited it. Titans
28H0, 28H7 and 28H8 are three of the 32x32 arm packages.

The existing catalog suite passed with the bug live because it only ever asked
about the Giants, who are in the majority for every family
(``test_nfl2k5_uniform_catalog.py``). These tests therefore *derive* their
expectations from the same compatibility report the decoder resolves against,
rather than restating a second set of constants that could drift the same way,
and pin the specific packages a human reported.

``nameplate_atlas`` is the deliberate exception. The catalog ships 1024x32
because that is the real horizontal character strip; the report still carries the
pre-fix transposed 32x1024. Letting the report win there would reintroduce the
scrambled export that transposition originally caused, so a negative control
guards it.
"""

from __future__ import annotations

import collections
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core.nfl2k5_uniform_catalog import (  # noqa: E402
    DIGIT_DIMENSION_FAMILIES,
    Nfl2k5UniformCatalog,
    _authored_digit_dimensions,
)

_REPORT = (
    _REPO_ROOT / "reports/assets/nfl2k5_live_numbers_nameplate_compatibility.json"
)
_HAVE_REPORT = _REPORT.is_file()
_HAVE_CATALOG = (
    _REPO_ROOT / "reports/assets/nfl2k5_team_select_card_inventory.json"
).is_file()
_PRIVATE_INVENTORY = (
    _REPO_ROOT / "reports/assets/nfl2k5_resource_chunks_v2.json"
)
_PACK0 = _REPO_ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"


def _catalog() -> Nfl2k5UniformCatalog:
    return Nfl2k5UniformCatalog.load()


@unittest.skipUnless(_HAVE_REPORT and _HAVE_CATALOG,
                     "private reports/assets inventory is not present")
class DigitDimensionsFollowTheReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = _catalog()
        cls.by_id = {item.asset_id: item for item in cls.catalog.assets}
        rows = json.loads(_REPORT.read_text(encoding="utf-8"))["resources"]
        cls.expected: dict[tuple[str, str, int, str, int], tuple[int, int]] = {}
        for row in rows:
            family = row.get("family")
            if family not in DIGIT_DIMENSION_FAMILIES or row.get("digit") is None:
                continue
            selector, layout = row["selector"], row["layout"]
            cls.expected[(
                str(selector["asset_code"]), str(selector["side"]),
                int(selector["variant"]), str(family), int(row["digit"]),
            )] = (int(layout["width"]), int(layout["height"]))

    def test_every_catalogued_digit_matches_its_authored_size(self) -> None:
        """The whole point: no target may carry a family constant instead."""

        short_family = {"arm_digit": "arm", "helmet_digit": "helmet",
                        "jersey_digit": "jersey"}
        wrong: list[str] = []
        for key, (width, height) in self.expected.items():
            code, side, variant, family, digit = key
            asset_id = (
                f"nfl2k5.uniform.{code}{side}{variant}".lower()
                + f".digit.{short_family[family]}.{digit}"
            )
            asset = self.by_id.get(asset_id)
            if asset is None:
                continue
            if (asset.width, asset.height) != (width, height):
                wrong.append(
                    f"{asset_id}: catalog {asset.width}x{asset.height} "
                    f"!= authored {width}x{height}"
                )
        self.assertEqual(wrong[:12], [], f"{len(wrong)} digit target(s) mis-sized")

    def test_the_reported_titans_packages_are_32_square(self) -> None:
        """The three packages a human actually reported."""

        for selector in ("28h0", "28h7", "28h8"):
            asset = self.by_id[f"nfl2k5.uniform.{selector}.digit.arm.0"]
            with self.subTest(selector=selector):
                self.assertEqual((asset.width, asset.height), (32, 32))

    def test_titans_sets_include_sleeves_and_every_arm_number_route(self) -> None:
        """No Titans component is omitted from inventory or provider import."""

        for selector, variant in (("28H0", 0), ("28H7", 7), ("28H8", 8)):
            assets = self.catalog.assets_for_set(selector)
            by_id = {asset.asset_id: asset for asset in assets}
            with self.subTest(selector=selector):
                self.assertEqual(len(assets), 39)
                sleeve = by_id[f"nfl2k5.uniform.{selector.lower()}.sleeve"]
                self.assertEqual(sleeve.target_selector, f"{selector}:sleeve")
                self.assertEqual(sleeve.provider_edit("sleeve.png"), {
                    "asset_code": "28",
                    "clean_png": "sleeve.png",
                    "kind": "sleeve",
                    "mud_mode": "darken_60",
                    "mud_png": None,
                    "side": "H",
                    "variant": variant,
                })
                arm_digits = [
                    by_id[
                        f"nfl2k5.uniform.{selector.lower()}.digit.arm.{digit}"
                    ]
                    for digit in range(10)
                ]
                self.assertEqual(
                    [asset.target_selector for asset in arm_digits],
                    [f"{selector}:arm_digit:{digit}" for digit in range(10)],
                )
                self.assertTrue(all(asset.dimensions == (32, 32)
                                    for asset in arm_digits))
                self.assertEqual(
                    [asset.provider_edit(f"arm-{digit}.png") for digit, asset
                     in enumerate(arm_digits)],
                    [{
                        "asset_code": "28",
                        "digit": digit,
                        "family": "arm",
                        "kind": "live_number_nameplate",
                        "png": f"arm-{digit}.png",
                        "side": "H",
                        "variant": variant,
                    } for digit in range(10)],
                )

    def test_a_majority_size_package_is_unchanged(self) -> None:
        """A control: the fix must not move the 5,960 arm digits that were right."""

        asset = self.by_id["nfl2k5.uniform.23h0.digit.arm.0"]
        self.assertEqual((asset.width, asset.height), (64, 64))

    def test_the_minority_sizes_are_actually_present_in_the_catalog(self) -> None:
        """Guards against a lookup that silently returns only family defaults."""

        counts = collections.Counter(
            (item.family, item.width, item.height)
            for item in self.catalog.assets if item.digit is not None
        )
        self.assertEqual(counts[("arm", 32, 32)], 380)
        self.assertEqual(counts[("arm", 64, 64)], 5960)
        self.assertEqual(counts[("helmet", 64, 64)], 200)
        self.assertEqual(counts[("helmet", 32, 32)], 6140)
        # jersey_digit really is uniform; a split here would mean a bad join.
        self.assertEqual(counts[("jersey", 64, 64)], 6340)

    def test_the_nameplate_atlas_keeps_the_catalog_orientation(self) -> None:
        """The report is the stale side here -- 1024x32 is the real strip."""

        asset = self.by_id["nfl2k5.uniform.28h0.nameplate"]
        self.assertEqual((asset.width, asset.height), (1024, 32))
        self.assertNotIn("nameplate_atlas", DIGIT_DIMENSION_FAMILIES)

    def test_the_lookup_is_built_once(self) -> None:
        """A 63 MB parse per asset would be unusable; it must be memoized."""

        first = _authored_digit_dimensions()
        self.assertIs(first, _authored_digit_dimensions())
        self.assertGreater(len(first), 18_000)


@unittest.skipUnless(
    _PACK0.is_file() and _PRIVATE_INVENTORY.is_file(),
    "private extracted NFL 2K5 fixture is absent",
)
class TitansRealSourceRoundTripTests(unittest.TestCase):
    def test_every_reported_sleeve_and_arm_number_exports_and_reimports(self) -> None:
        """The actual 33 Titans PNGs satisfy the editor's import contract."""

        from mod_editor.core.nfl2k5_asset_io import Nfl2k5AssetIO

        catalog = _catalog()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            io = Nfl2k5AssetIO(SimpleNamespace(
                inventory=_PRIVATE_INVENTORY,
                pack0=_PACK0,
                originals=root / "originals",
                source=SimpleNamespace(sha256="retail-fixture"),
            ))
            exercised: list[str] = []
            for selector in ("28h0", "28h7", "28h8"):
                component_ids = (
                    "sleeve",
                    *(f"digit.arm.{digit}" for digit in range(10)),
                )
                for component_id in component_ids:
                    asset = catalog.get_asset(
                        f"nfl2k5.uniform.{selector}.{component_id}"
                    )
                    exported = io.export_original(
                        asset,
                        root / f"{selector}-{component_id}.png",
                    )
                    payload, rgba = io.validate_replacement(asset, exported)
                    self.assertEqual(payload, exported.read_bytes())
                    self.assertEqual(
                        len(rgba),
                        asset.width * asset.height * 4,
                    )
                    edit = asset.provider_edit(exported)
                    self.assertEqual(edit["kind"], asset.kind)
                    exercised.append(asset.asset_id)
            self.assertEqual(len(exercised), 33)


class GracefulWithoutTheReportTests(unittest.TestCase):
    def test_a_missing_report_yields_no_overrides_rather_than_an_error(self) -> None:
        """``reports/assets`` is gitignored, so a clean clone has no report.

        Losing the per-target sizes there is acceptable; failing to build a
        catalog at all is not.
        """

        import mod_editor.core.nfl2k5_uniform_catalog as catalog

        _authored_digit_dimensions.cache_clear()
        try:
            import nfl_live_numbers_nameplate_targets as live_targets
        except Exception:  # pragma: no cover - tooling absent
            self.skipTest("live-art targets module unavailable")
        original = live_targets.DEFAULT_REPORT
        live_targets.DEFAULT_REPORT = Path("/nonexistent/no-such-report.json")
        try:
            self.assertEqual(catalog._authored_digit_dimensions(), {})
        finally:
            live_targets.DEFAULT_REPORT = original
            _authored_digit_dimensions.cache_clear()

    def test_the_family_mapping_is_shared_with_the_target_selector(self) -> None:
        """One mapping, so a selector and a dimension cannot disagree."""

        source = (
            _REPO_ROOT / "mod_editor" / "core" / "nfl2k5_uniform_catalog.py"
        ).read_text(encoding="utf-8")
        self.assertIn("_REPORT_FAMILIES", source)
        # The literal dict must not be duplicated inside _target_selector again.
        self.assertEqual(source.count('"arm": "arm_digit"'), 1)


if __name__ == "__main__":
    unittest.main()
