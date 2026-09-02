"""Focused tests for the fail-closed family-label promotion wiring.

Proves the product contracts for the deterministic labeling pass:

* reviewed labels and the Menu Back proof are immutable;
* family promotion is deterministic (the pinned artifact binds to the pinned
  audit by SHA-256 and the loader accepts only that exact pairing);
* any missing, stale, or malformed input falls back to provisional labels.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from mod_editor.core.nfl2k5_audo_family_labels import (
    AudoFamilyLabelPromotion,
    FAMILY_LABEL_PREFIX,
    FAMILY_LABEL_REPORT,
    FAMILY_LABEL_REPORT_SCHEMA,
    FAMILY_REVIEWED_CONFIDENCE,
    load_family_label_promotions,
)
from mod_editor.core.nfl2k5_audio_catalog import (
    MENU_BACK_SELECTOR,
    Nfl2k5AudioCatalog,
    apply_family_label_promotions,
)
from mod_editor.core.nfl2k5_audo_fixed_slots import CAPACITY_REPORT
from mod_editor.studio.audio_replacement_pack import (
    FAMILY_REVIEWED_MEANING_STATUS,
    standalone_runtime_meaning_status,
)
from tests.mod_editor.test_nfl2k5_audio_catalog import AudioFixture


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _promotion_row(
    *,
    key: str = "outer_0003_chunk_0100",
    representative_key: str = "outer_0003_chunk_0101",
    label: str = FAMILY_LABEL_PREFIX + "menu-back_01",
) -> dict[str, object]:
    return {
        "key": key,
        "name": "menu-back_01",
        "label": label,
        "confidence": FAMILY_REVIEWED_CONFIDENCE,
        "group_id": "content:syntheticfamily",
        "group_kind": "equal_decoded_content",
        "representative_key": representative_key,
        "representative_name": "menu-back_01",
        "evidence_sha256": "c" * 64,
        "member_count": 2,
    }


class FamilyLabelLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="family-label-test-")
        self.root = Path(self.temporary.name)
        source = self.root / "source"
        source.mkdir()
        self.fixture = AudioFixture(source)
        self.audit_sha256 = hashlib.sha256(
            self.fixture.report.read_bytes()
        ).hexdigest()
        # Consume the fixture's inventory once so later catalog construction
        # sees the same private cache state every time.
        Nfl2k5AudioCatalog(
            self.fixture.cache,
            capacity_report=self.fixture.report,
            expected_count=2,
            expected_report_sha256=None,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_report(
        self, promotions: list[dict[str, object]], *, schema: str | None = None
    ) -> Path:
        path = self.root / "family_labels.json"
        path.write_text(
            json.dumps({
                "schema": schema or FAMILY_LABEL_REPORT_SCHEMA,
                "source_audit_sha256": self.audit_sha256,
                "promotions": promotions,
            }) + "\n",
            encoding="utf-8",
        )
        return path

    def _catalog(self, *, family_report: Path | None, expected_sha: str | None):
        return Nfl2k5AudioCatalog(
            self.fixture.cache,
            capacity_report=self.fixture.report,
            expected_count=2,
            expected_report_sha256=None,
            family_label_report=family_report,
            expected_family_label_sha256=expected_sha,
        )

    def test_valid_report_promotes_only_the_provisional_sibling(self) -> None:
        report = self._write_report([_promotion_row()])
        catalog = self._catalog(family_report=report, expected_sha=_sha256(report))
        provisional, menu_back = catalog.assets
        self.assertEqual(provisional.selector, (3, 100))
        self.assertEqual(menu_back.selector, MENU_BACK_SELECTOR)
        # The provisional cue carries the disclosed family inference...
        self.assertEqual(
            provisional.family_reviewed_label, FAMILY_LABEL_PREFIX + "menu-back_01"
        )
        self.assertEqual(provisional.label_text, provisional.family_reviewed_label)
        promotion = provisional.family_label_promotion
        self.assertIsNotNone(promotion)
        self.assertEqual(promotion.group_id, "content:syntheticfamily")
        self.assertEqual(promotion.group_kind, "equal_decoded_content")
        self.assertEqual(promotion.representative_key, "outer_0003_chunk_0101")
        self.assertEqual(promotion.confidence, FAMILY_REVIEWED_CONFIDENCE)
        self.assertEqual(
            standalone_runtime_meaning_status(provisional),
            FAMILY_REVIEWED_MEANING_STATUS,
        )
        # ...while the Menu Back proof stays byte-for-byte untouched.
        self.assertIsNone(menu_back.family_label_promotion)
        self.assertEqual(menu_back.name, "menu-back_01")
        self.assertEqual(menu_back.label_text, "menu-back_01")
        self.assertEqual(
            standalone_runtime_meaning_status(menu_back),
            "menu_back_route_runtime_unproved",
        )

    def test_reviewed_rows_are_immutable_even_against_a_hostile_report(self) -> None:
        hostile = [
            _promotion_row(key="outer_0003_chunk_0101"),  # the Menu Back proof
        ]
        report = self._write_report(hostile)
        catalog = self._catalog(family_report=report, expected_sha=_sha256(report))
        for asset in catalog.assets:
            self.assertIsNone(asset.family_label_promotion)
            self.assertEqual(asset.label_text, asset.name)

    def test_missing_report_falls_back_to_provisional(self) -> None:
        catalog = self._catalog(
            family_report=self.root / "absent.json", expected_sha="0" * 64
        )
        for asset in catalog.assets:
            self.assertIsNone(asset.family_label_promotion)
        provisional, menu_back = catalog.assets
        self.assertEqual(
            standalone_runtime_meaning_status(provisional),
            "provisional_label_runtime_meaning_unproved",
        )
        self.assertEqual(
            standalone_runtime_meaning_status(menu_back),
            "menu_back_route_runtime_unproved",
        )

    def test_stale_report_hash_falls_back_to_provisional(self) -> None:
        report = self._write_report([_promotion_row()])
        catalog = self._catalog(family_report=report, expected_sha="f" * 64)
        for asset in catalog.assets:
            self.assertIsNone(asset.family_label_promotion)

    def test_stale_source_audit_binding_falls_back_to_provisional(self) -> None:
        path = self.root / "family_labels.json"
        path.write_text(
            json.dumps({
                "schema": FAMILY_LABEL_REPORT_SCHEMA,
                "source_audit_sha256": "a" * 64,
                "promotions": [_promotion_row()],
            }) + "\n",
            encoding="utf-8",
        )
        catalog = self._catalog(family_report=path, expected_sha=_sha256(path))
        for asset in catalog.assets:
            self.assertIsNone(asset.family_label_promotion)

    def test_schema_mismatch_falls_back_to_provisional(self) -> None:
        report = self._write_report(
            [_promotion_row()], schema="nfl2k5_audo_family_labels/v1"
        )
        catalog = self._catalog(family_report=report, expected_sha=_sha256(report))
        for asset in catalog.assets:
            self.assertIsNone(asset.family_label_promotion)

    def test_malformed_rows_fall_back_to_provisional(self) -> None:
        variants = (
            [_promotion_row(label="menu-back_01")],  # missing family: prefix
            [_promotion_row(representative_key="outer_0003_chunk_0100")],  # self rep
            [{**_promotion_row(), "member_count": 1}],
            [_promotion_row(), _promotion_row()],  # duplicate cue key
        )
        for rows in variants:
            with self.subTest(rows=rows):
                report = self._write_report(rows)
                promotions = load_family_label_promotions(
                    self.fixture.report,
                    report=report,
                    expected_sha256=_sha256(report),
                )
                self.assertEqual(promotions, {})

    def test_apply_requires_a_matching_selector(self) -> None:
        catalog = self._catalog(family_report=None, expected_sha=None)
        promotion = AudoFamilyLabelPromotion(
            key="outer_0003_chunk_0100",
            label=FAMILY_LABEL_PREFIX + "menu-back_01",
            group_id="content:syntheticfamily",
            group_kind="equal_decoded_content",
            representative_key="outer_0003_chunk_0101",
            representative_name="menu-back_01",
            confidence=FAMILY_REVIEWED_CONFIDENCE,
            evidence_sha256="c" * 64,
            member_count=2,
        )
        applied = apply_family_label_promotions(
            catalog.assets, {"outer_0003_chunk_0100": promotion}
        )
        self.assertIsNotNone(applied[0].family_label_promotion)
        self.assertIsNone(applied[1].family_label_promotion)
        untouched = apply_family_label_promotions(catalog.assets, {})
        self.assertEqual(untouched, catalog.assets)


@unittest.skipUnless(
    CAPACITY_REPORT.exists() and FAMILY_LABEL_REPORT.exists(),
    "pinned AUDO audit or family-label report not present",
)
class ShippedFamilyLabelTests(unittest.TestCase):
    def test_shipped_report_binds_to_the_shipped_audit(self) -> None:
        promotions = load_family_label_promotions(CAPACITY_REPORT)
        self.assertEqual(set(promotions), {"outer_0009_chunk_0034"})
        promotion = promotions["outer_0009_chunk_0034"]
        self.assertEqual(promotion.label, FAMILY_LABEL_PREFIX + "menu-back_01")
        self.assertEqual(promotion.representative_key, "outer_0003_chunk_0101")
        self.assertEqual(promotion.group_kind, "equal_decoded_content")

    def test_shipped_report_rejects_a_different_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            foreign = Path(tmp) / "foreign.json"
            foreign.write_text("{}", encoding="utf-8")
            self.assertEqual(load_family_label_promotions(foreign), {})


if __name__ == "__main__":
    unittest.main()
