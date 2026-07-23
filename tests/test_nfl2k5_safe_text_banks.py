from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_safe_text_banks import (
    SAFE_TEXT_PROVIDER_KIND,
    SafeTextCatalog,
    encode_fixed_utf16le,
)


SOURCE_SHA256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
CACHE = Path.home() / ".cache" / "2k5-mod-studio" / SOURCE_SHA256
PACK0 = CACHE / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
INVENTORY = CACHE / "indexes/nfl2k5_resource_chunks_v2.json"


class SafeTextBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not PACK0.is_file() or not INVENTORY.is_file():
            raise unittest.SkipTest("recognized private NFL 2K5 cache is not present")
        cls.catalog = SafeTextCatalog.from_paths(PACK0, INVENTORY)

    def test_fixed_utf16_encoder_preserves_exact_allocation(self) -> None:
        result = encode_fixed_utf16le("AB", 10, "Example")
        self.assertEqual(result, b"A\0B\0\0\0\0\0\0\0")
        self.assertEqual(len(result), 10)
        with self.assertRaisesRegex(ValidationError, "cannot be empty"):
            encode_fixed_utf16le("", 10, "Example")
        with self.assertRaisesRegex(ValidationError, "allows 4"):
            encode_fixed_utf16le("ABCDE", 10, "Example")

    def test_real_cache_audit_matches_the_bounded_unlock(self) -> None:
        catalog = self.catalog
        audit = catalog.audit_document()
        self.assertEqual(len(catalog.banks), 5)
        self.assertEqual(len(catalog.assets), 6_873)
        self.assertEqual(sum(asset.editable for asset in catalog.assets), 6_658)
        self.assertEqual(audit["inventory"], {
        "bank_count": 716,
        "bank_kind_counts": {
            "CRED": 1,
            "NAME": 635,
            "ROST": 76,
            "SITU": 1,
            "STRG": 2,
            "TRIV": 1,
        },
        })
        self.assertEqual(
            audit["proved_fixed_allocation_banks"]["editable_counts"], {
        "CRED": 608,
        "SITU": 100,
        "STRG": 1_113,
        "TRIV": 4_837,
            })
        self.assertEqual(
            audit["proved_fixed_allocation_banks"]["read_only_counts"], {
        "CRED": 163,
        "SITU": 50,
        "STRG": 2,
            })
        self.assertEqual(
            sum(bank.read_only_count for bank in catalog.banks if bank.kind == "SITU"),
            50,
        )

    def test_situ_and_strg_edit_resolvers_recheck_private_preimages(self) -> None:
        catalog = self.catalog
        situ = catalog.get_selector("situ:moment:0:title")
        self.assertTrue(situ.editable)
        self.assertEqual(situ.reference_count, 1)
        resolved_situ = catalog.resolve_edit(situ.selector, "MOD")
        self.assertEqual(resolved_situ.pack_name, "0")
        self.assertEqual(resolved_situ.size, situ.allocation_bytes)
        self.assertTrue(resolved_situ.replacement.startswith(b"M\0O\0D\0\0\0"))
        pack = PACK0.parent / resolved_situ.pack_name
        with pack.open("rb") as stream:
            stream.seek(resolved_situ.pack_offset)
            before = stream.read(resolved_situ.size)
        self.assertEqual(
            hashlib.sha256(before).hexdigest(), resolved_situ.preimage_sha256
        )

        aliased = max(
            (asset for asset in catalog.assets if asset.bank_kind == "STRG"),
            key=lambda asset: asset.reference_count,
        )
        self.assertGreater(aliased.reference_count, 1)
        resolved_strg = catalog.resolve_edit(aliased.selector, "M")
        self.assertEqual(resolved_strg.size, aliased.allocation_bytes)
        self.assertTrue(resolved_strg.replacement.startswith(b"M\0\0\0"))

        cred = next(
            asset for asset in catalog.assets
            if asset.bank_kind == "CRED" and asset.editable
        )
        self.assertEqual(catalog.resolve_edit(cred.selector, "M").pack_name, "0")
        trivia = catalog.get_selector("triv:question:0:question")
        self.assertEqual(catalog.resolve_edit(trivia.selector, "M").pack_name, "C")

    def test_public_project_record_contains_only_logical_user_authored_data(self) -> None:
        catalog = self.catalog
        asset = catalog.get_selector("situ:moment:0:title")
        project = asset.public_project_record("MOD")
        self.assertEqual(project, {
        "asset_id": asset.asset_id,
        "kind": "text",
        "value": "MOD",
        })
        encoded = json.dumps(project, sort_keys=True)
        for forbidden in (
            "offset", "preimage", "original", "pack_name", "allocation_bytes",
            asset.value,
        ):
            self.assertNotIn(forbidden, encoded)

        provider = asset.provider_edit("MOD")
        self.assertEqual(provider, {
        "kind": SAFE_TEXT_PROVIDER_KIND,
        "selector": "situ:moment:0:title",
        "text": "MOD",
        })

    def test_audit_document_contains_counts_and_policy_not_retail_payloads(self) -> None:
        audit = self.catalog.audit_document()

        def keys(value: object) -> set[str]:
            if isinstance(value, dict):
                return {
                    str(key)
                    for key in value
                } | set().union(*(keys(item) for item in value.values()))
            if isinstance(value, list):
                return set().union(*(keys(item) for item in value))
            return set()

        self.assertTrue({
            "schema", "inventory", "proved_fixed_allocation_banks",
            "constraints", "unresolved_bank_policy",
        }.issubset(audit))
        self.assertTrue({
            "asset_id", "selector", "value", "label", "original",
            "preimage_sha256", "pack_name", "pack_offset", "body_offset",
        }.isdisjoint(keys(audit)))

    def test_zero_capacity_strg_allocations_fail_closed(self) -> None:
        catalog = self.catalog
        empty = [
            asset for asset in catalog.assets
            if asset.bank_kind == "STRG" and asset.character_limit == 0
        ]
        self.assertEqual(len(empty), 2)
        self.assertTrue(all(not asset.editable for asset in empty))
        with self.assertRaisesRegex(ValidationError, "no nonempty text fits"):
            empty[0].provider_edit("X")

    def test_situ_team_resource_selectors_are_browsable_but_read_only(self) -> None:
        selector = self.catalog.get_selector("situ:moment:0:away_team_asset_code")
        self.assertFalse(selector.editable)
        self.assertIsNone(selector.provider_kind)
        with self.assertRaisesRegex(ValidationError, "team-resource selector"):
            selector.public_project_record("MOD")

    def test_credits_and_trivia_have_exact_product_boundaries(self) -> None:
        credits = [asset for asset in self.catalog.assets if asset.bank_kind == "CRED"]
        trivia = [asset for asset in self.catalog.assets if asset.bank_kind == "TRIV"]
        self.assertEqual(len(credits), 771)
        self.assertEqual(sum(asset.editable for asset in credits), 608)
        self.assertEqual(len(trivia), 691 * 7)
        self.assertTrue(all(asset.editable for asset in trivia))
        self.assertEqual(
            {asset.field_name for asset in trivia},
            {
                "category", "subject", "question", "answer_a", "answer_b",
                "answer_c", "answer_d",
            },
        )

    def test_provider_batch_rejects_duplicates(self) -> None:
        catalog = self.catalog
        edit = {
        "kind": SAFE_TEXT_PROVIDER_KIND,
        "selector": "situ:moment:0:title",
        "text": "MOD",
        }
        with self.assertRaisesRegex(ValidationError, "Duplicate"):
            catalog.resolve_edits([edit, edit])


if __name__ == "__main__":
    unittest.main()
