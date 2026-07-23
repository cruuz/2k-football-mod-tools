"""Focused product tests for APF's bounded roster-name writer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from mod_editor.apf_studio.build import ApfBuildService, EXPECTED_0A_SHA256
from mod_editor.apf_studio.catalog import build_capability_cards
from mod_editor.apf_studio.facade import (
    ApfStudioFacade,
    FacadeError,
    ROSTER_IDENTITY_RUNTIME_LOCK_MESSAGE,
)
from mod_editor.apf_studio.models import ApfSource, ApfStatus, Modification
from mod_editor.apf_studio.project import (
    encode_text_payload,
    save_project as save_project_archive,
)
from mod_editor.apf_studio.session import ApfSession, SessionError

import apf_roster_identity_patch as writer
import apf_inner
import apf_outer
import apf_player_rating_patch as rating_writer
import apf_roster
import apf_roster_composite_patch as roster_compositor
import apf_texture_patch


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"


def _source(root: Path) -> ApfSource:
    return ApfSource(
        selected_path=root,
        game_root=root,
        index_0a=root / "0A",
        source_sha256=EXPECTED_0A_SHA256,
        source_size=(root / "0A").stat().st_size,
        xex_sha256="e" * 64,
        display_name="APF roster identity fixture",
    )


def _allocation() -> writer.RosterIdentityAllocation:
    owner = writer.RosterIdentityOwner("team", 7, "display_name")
    return writer.RosterIdentityAllocation(
        asset_id="apf:roster-name:123",
        pool_index=123,
        text="SOURCE",
        allocation_bytes=14,
        maximum_utf16_units=6,
        known_owners=(owner,),
        owner_fingerprint=hashlib.sha256(owner.owner_id.encode("utf-8")).hexdigest(),
        editable=True,
        note="One fixed UTF-16BE roster identity allocation.",
    )


def _player_allocation() -> writer.RosterIdentityAllocation:
    owner = writer.RosterIdentityOwner("player", 7, "last_name")
    return writer.RosterIdentityAllocation(
        asset_id="apf:roster-name:124",
        pool_index=124,
        text="PLAYER",
        allocation_bytes=14,
        maximum_utf16_units=6,
        known_owners=(owner,),
        owner_fingerprint=hashlib.sha256(owner.owner_id.encode("utf-8")).hexdigest(),
        editable=True,
        note="One fixed UTF-16BE roster identity allocation.",
    )


def _scoped_allocation(
    *owners: writer.RosterIdentityOwner,
    asset_id: str = "apf:roster-name:200",
    text: str = "ALIAS",
    maximum_utf16_units: int = 5,
    editable: bool = True,
) -> writer.RosterIdentityAllocation:
    owner_fingerprint = hashlib.sha256(
        "\n".join(sorted(owner.owner_id for owner in owners)).encode("utf-8")
    ).hexdigest()
    return writer.RosterIdentityAllocation(
        asset_id=asset_id,
        pool_index=writer.parse_asset_id(asset_id),
        text=text,
        allocation_bytes=(maximum_utf16_units + 1) * 2,
        maximum_utf16_units=maximum_utf16_units,
        known_owners=tuple(owners),
        owner_fingerprint=owner_fingerprint,
        editable=editable,
        note="Synthetic scope fixture.",
    )


def _manifest_keys(value: object) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        result.update(str(key) for key in value)
        for child in value.values():
            result.update(_manifest_keys(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            result.update(_manifest_keys(child))
    return result


@unittest.skipUnless(SOURCE.is_file(), "private APF source is unavailable")
class RetailRosterWriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.allocations = writer.inventory(SOURCE)

    def test_inventory_has_exact_identity_coverage_and_alias_contract(self) -> None:
        self.assertEqual(len(self.allocations), 3_273)
        self.assertEqual(sum(item.editable for item in self.allocations), 3_272)
        self.assertEqual(
            sum(item.known_owner_count for item in self.allocations), 4_628
        )
        self.assertTrue(any(item.known_owner_count > 10 for item in self.allocations))
        product_team_names = tuple(
            item
            for item in self.allocations
            if item.editable
            and item.known_owners
            and all(
                owner.entity_kind == "team" and owner.field == "display_name"
                for owner in item.known_owners
            )
        )
        self.assertEqual(len(product_team_names), 40)
        self.assertEqual(
            sum(
                writer.roster_identity_edit_scope(item)
                == writer.PLAYER_NAME_EDIT_SCOPE
                for item in self.allocations
            ),
            3_191,
        )
        self.assertEqual(
            sum(
                writer.roster_identity_is_product_editable(item)
                for item in self.allocations
            ),
            3_231,
        )
        self.assertTrue(
            all(
                "offset" not in field
                for field in writer.allocation_metadata(self.allocations[0])
            )
        )
        self.assertEqual(
            writer.JERSEY_NUMBER_FINDING["status"], "read_only_unmapped"
        )

    def test_changed_team_name_rebuild_is_bounded_reparsed_and_source_safe(self) -> None:
        selected = next(
            allocation
            for allocation in self.allocations
            if any(
                owner.owner_id == "team:0:display_name"
                for owner in allocation.known_owners
            )
        )
        replacement = "X" if selected.text != "X" else "Y"
        before = SOURCE.stat()
        result = writer.build_patch(SOURCE, {selected.pool_index: replacement})
        after = SOURCE.stat()
        self.assertEqual(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns),
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
        )
        self.assertEqual(result.outer_index, 1126)
        self.assertEqual(result.manifest["mode"], "patched")
        self.assertEqual(result.manifest["edit_count"], 1)
        self.assertTrue(
            result.manifest["validation"]["fixed_outer_allocation_preserved"]
        )
        transport = result.manifest["output"]["h7a_transport"]
        self.assertEqual(transport["strategy"], "retail-token-preserving")
        self.assertEqual(transport["retail_token_count"], 284_015)
        self.assertEqual(
            transport["retail_tokens_preserved_semantically"], 284_004
        )
        self.assertEqual(transport["retail_tokens_split_or_replaced"], 11)
        self.assertEqual(
            hashlib.sha256(result.entry_bytes).hexdigest(),
            "2af1660548cf0e7c599df6ed56894d74f2bc5c696de7bc4cc8690348aa93d79a",
        )
        manifest_text = json.dumps(result.manifest, sort_keys=True)
        self.assertNotIn(replacement, manifest_text)
        self.assertTrue(
            {"pack_offset", "byte_offset", "preimage", "source_text"}.isdisjoint(
                _manifest_keys(result.manifest)
            )
        )

    def test_player_name_and_rating_compose_into_one_disjoint_roster_entry(
        self,
    ) -> None:
        selected = next(
            allocation
            for allocation in self.allocations
            if any(
                owner.owner_id == "player:788:last_name"
                for owner in allocation.known_owners
            )
        )
        self.assertEqual(
            writer.roster_identity_edit_scope(selected),
            writer.PLAYER_NAME_EDIT_SCOPE,
        )
        replacement = "CODEX"
        self.assertLessEqual(len(replacement), selected.maximum_utf16_units)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identity_payload = encode_text_payload(replacement)
            rating_payload = rating_writer.encode_replacement_payload(99)
            identity_path = root / "identity.json"
            rating_path = root / "rating.json"
            identity_path.write_bytes(identity_payload)
            rating_path.write_bytes(rating_payload)
            identity_modification = Modification(
                asset_id=selected.asset_id,
                kind="roster_identity_text",
                replacement_path=identity_path,
                replacement_sha256=hashlib.sha256(identity_payload).hexdigest(),
                metadata=writer.allocation_metadata(selected),
            )
            rating_target = rating_writer.target_for(788, "speed")
            rating_modification = Modification(
                asset_id=rating_target.asset_id,
                kind="player_base_rating",
                replacement_path=rating_path,
                replacement_sha256=hashlib.sha256(rating_payload).hexdigest(),
                metadata=rating_writer.target_metadata(rating_target),
            )
            result, receipt = ApfBuildService(
                SimpleNamespace(index_0a=SOURCE)
            )._compile_roster_composite_groups(
                (identity_modification,), (rating_modification,)
            )

        self.assertEqual(
            receipt["kind"], "roster_identity_and_player_rating_batch"
        )
        self.assertEqual(
            set(receipt["asset_ids"]),
            {selected.asset_id, rating_target.asset_id},
        )
        self.assertTrue(
            result.manifest["validation"]["component_decoded_deltas_disjoint"]
        )
        archive = apf_outer.parse_archive(SOURCE)
        entry = archive.entries[apf_roster.OUTER_TABLE_INDEX]
        memory = apf_texture_patch.BytesReader(result.entry_bytes)
        record = apf_inner.parse_iff(memory, entry)
        block = apf_inner.decode_block(
            memory, record, 0, roster_compositor.MAX_DECOMPRESSED
        )
        part = record.files[0].parts[0]
        body = block[part.offset : part.offset + part.length]
        rating_offset = (
            apf_roster.ROOT_SIZE
            + 788 * apf_roster.PLAYER_STRIDE
            + rating_target.record_relative_offset
        )
        self.assertEqual(body[rating_offset], 99)
        refreshed = writer.inventory_from_decoded(body)
        self.assertEqual(
            next(
                row for row in refreshed if row.pool_index == selected.pool_index
            ).text,
            replacement,
        )


class H7ATokenPreservationTests(unittest.TestCase):
    def test_changed_literal_keeps_original_token_grid(self) -> None:
        retail_decoded = b"ABCDEFGH"
        retail_payload = b"\x00ABCDEFGH"
        wanted = b"ABCXEFGH"
        encoded, metrics = apf_inner.encode_h7a_preserving_tokens(
            retail_payload,
            retail_decoded,
            wanted,
            10,
        )
        self.assertEqual(encoded, b"\x00ABCXEFGH")
        self.assertEqual(apf_inner.decompress_h7a(encoded, 8, 10), wanted)
        self.assertEqual(metrics["retail_token_count"], 8)
        self.assertEqual(metrics["retail_tokens_preserved_semantically"], 7)
        self.assertEqual(metrics["retail_tokens_split_or_replaced"], 1)

    def test_invalidated_match_splits_only_that_retail_token(self) -> None:
        retail_decoded = b"ABCABC"
        retail_payload = b"\x08ABC\x00\x03"
        wanted = b"ABCABX"
        encoded, metrics = apf_inner.encode_h7a_preserving_tokens(
            retail_payload,
            retail_decoded,
            wanted,
            10,
        )
        self.assertEqual(apf_inner.decompress_h7a(encoded, 6, 10), wanted)
        self.assertEqual(metrics["retail_token_count"], 4)
        self.assertEqual(metrics["retail_tokens_preserved_semantically"], 3)
        self.assertEqual(metrics["retail_tokens_split_or_replaced"], 1)
        self.assertEqual(metrics["output_token_count"], 6)


class RosterIdentityProductScopeTests(unittest.TestCase):
    def test_pure_team_and_player_aliases_are_admitted(self) -> None:
        team = _allocation()
        player = _player_allocation()
        shared_player = _scoped_allocation(
            writer.RosterIdentityOwner("player", 4, "first_name"),
            writer.RosterIdentityOwner("player", 19, "last_name"),
        )
        self.assertEqual(
            writer.roster_identity_edit_scope(team),
            writer.TEAM_DISPLAY_NAME_EDIT_SCOPE,
        )
        self.assertEqual(
            writer.roster_identity_edit_scope(player),
            writer.PLAYER_NAME_EDIT_SCOPE,
        )
        self.assertEqual(
            writer.roster_identity_edit_scope(shared_player),
            writer.PLAYER_NAME_EDIT_SCOPE,
        )
        self.assertTrue(writer.roster_identity_is_product_editable(shared_player))

    def test_abbreviation_mixed_zero_capacity_and_unknown_are_locked(self) -> None:
        abbreviation = _scoped_allocation(
            writer.RosterIdentityOwner("team", 2, "abbreviation")
        )
        mixed = _scoped_allocation(
            writer.RosterIdentityOwner("team", 2, "display_name"),
            writer.RosterIdentityOwner("player", 9, "first_name"),
        )
        zero_capacity = _scoped_allocation(
            writer.RosterIdentityOwner("player", 9, "last_name"),
            text="",
            maximum_utf16_units=0,
            editable=True,
        )
        unknown = _scoped_allocation()
        future_field = _scoped_allocation(
            writer.RosterIdentityOwner("player", 9, "nickname")
        )
        for allocation in (
            abbreviation,
            mixed,
            zero_capacity,
            unknown,
            future_field,
        ):
            with self.subTest(
                asset_id=allocation.asset_id,
                owners=allocation.known_owners,
            ):
                self.assertIsNone(writer.roster_identity_edit_scope(allocation))
                self.assertFalse(
                    writer.roster_identity_is_product_editable(allocation)
                )


class RosterIdentitySessionProjectTests(unittest.TestCase):
    def test_replace_value_individual_revert_and_project_roundtrip(self) -> None:
        allocation = _allocation()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "game"
            game.mkdir()
            (game / "0A").write_bytes(b"fixture")
            first = ApfSession(
                _source(game), SimpleNamespace(), cache_root=root / "cache-first"
            )
            try:
                with patch.object(writer, "inventory", return_value=(allocation,)):
                    modification = first.replace_roster_identity_text(
                        allocation.asset_id, "MOD"
                    )
                    self.assertEqual(modification.kind, "roster_identity_text")
                    self.assertEqual(
                        first.roster_identity_value(allocation.asset_id), "MOD"
                    )
                    project = first.save_project(root / "names.apf2k8mod")
                    self.assertTrue(first.revert(allocation.asset_id))
                    self.assertEqual(
                        first.roster_identity_value(allocation.asset_id),
                        allocation.text,
                    )
            finally:
                first.close()

            with zipfile.ZipFile(project) as archive:
                manifest = json.loads(archive.read("project.json"))
                row = manifest["replacements"][0]
                self.assertEqual(row["kind"], "roster_identity_text")
                self.assertEqual(
                    set(row["metadata"]),
                    {
                        "pool_index",
                        "maximum_utf16_units",
                        "known_owner_count",
                        "owner_fingerprint",
                    },
                )
                self.assertNotIn(allocation.text, json.dumps(manifest))
                self.assertFalse(
                    manifest["distribution"]["contains_original_game_bytes"]
                )
                self.assertFalse(
                    manifest["distribution"]["contains_original_preimages"]
                )

            imported = ApfSession(
                _source(game), SimpleNamespace(), cache_root=root / "cache-import"
            )
            try:
                with patch.object(writer, "inventory", return_value=(allocation,)):
                    self.assertEqual(imported.load_project(project), 1)
                    self.assertEqual(
                        imported.roster_identity_value(allocation.asset_id), "MOD"
                    )
            finally:
                imported.close()

    def test_human_readable_limit_and_nul_errors(self) -> None:
        allocation = _allocation()
        with self.assertRaisesRegex(writer.RosterIdentityError, "at most 6"):
            writer.validate_replacement(allocation, "TOO-LONG")
        with self.assertRaisesRegex(writer.RosterIdentityError, "NUL"):
            writer.validate_replacement(allocation, "NO\0PE")

    def test_product_session_accepts_player_name_and_keeps_team_wrapper(
        self,
    ) -> None:
        allocation = _player_allocation()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "game"
            game.mkdir()
            (game / "0A").write_bytes(b"fixture")
            session = ApfSession(
                _source(game), SimpleNamespace(), cache_root=root / "cache"
            )
            try:
                with patch.object(writer, "inventory", return_value=(allocation,)):
                    self.assertEqual(
                        session.roster_identity_edit_scope(allocation.asset_id),
                        writer.PLAYER_NAME_EDIT_SCOPE,
                    )
                    self.assertTrue(
                        session.roster_identity_is_product_editable(
                            allocation.asset_id
                        )
                    )
                    self.assertFalse(
                        session.roster_identity_is_team_display_name(
                            allocation.asset_id
                        )
                    )
                    session.replace_roster_identity_text(
                        allocation.asset_id, "MOD"
                    )
                    self.assertEqual(
                        session.roster_identity_value(allocation.asset_id), "MOD"
                    )
            finally:
                session.close()

    def test_player_name_project_roundtrip_revert_and_privacy_contract(self) -> None:
        allocation = _player_allocation()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "game"
            game.mkdir()
            (game / "0A").write_bytes(b"fixture")
            authored = ApfSession(
                _source(game), SimpleNamespace(), cache_root=root / "cache-authored"
            )
            imported = ApfSession(
                _source(game), SimpleNamespace(), cache_root=root / "cache-imported"
            )
            try:
                with patch.object(writer, "inventory", return_value=(allocation,)):
                    authored.replace_roster_identity_text(
                        allocation.asset_id, "MOD"
                    )
                    project = authored.save_project(
                        root / "player-name.apf2k8mod"
                    )
                    self.assertEqual(imported.load_project(project), 1)
                    self.assertEqual(
                        imported.roster_identity_value(allocation.asset_id), "MOD"
                    )
                    self.assertTrue(imported.revert(allocation.asset_id))
                    self.assertEqual(
                        imported.roster_identity_value(allocation.asset_id),
                        allocation.text,
                    )
                with zipfile.ZipFile(project) as archive:
                    manifest = json.loads(archive.read("project.json"))
                    manifest_text = json.dumps(manifest, sort_keys=True)
                    self.assertNotIn(allocation.text, manifest_text)
                    self.assertNotIn("player:7:last_name", manifest_text)
                    self.assertEqual(
                        set(manifest["replacements"][0]["metadata"]),
                        {
                            "pool_index",
                            "maximum_utf16_units",
                            "known_owner_count",
                            "owner_fingerprint",
                        },
                    )
            finally:
                authored.close()
                imported.close()

    def test_product_session_and_project_reject_team_abbreviation(self) -> None:
        allocation = _scoped_allocation(
            writer.RosterIdentityOwner("team", 7, "abbreviation"),
            asset_id="apf:roster-name:124",
            text="ABBR",
            maximum_utf16_units=4,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "game"
            game.mkdir()
            (game / "0A").write_bytes(b"fixture")
            payload = root / "abbreviation.json"
            data = encode_text_payload("MOD")
            payload.write_bytes(data)
            project = save_project_archive(
                root / "locked-abbreviation.apf2k8mod",
                source_sha256=EXPECTED_0A_SHA256,
                modifications=(
                    Modification(
                        asset_id=allocation.asset_id,
                        kind="roster_identity_text",
                        replacement_path=payload,
                        replacement_sha256=hashlib.sha256(data).hexdigest(),
                        metadata=writer.allocation_metadata(allocation),
                    ),
                ),
            )
            session = ApfSession(
                _source(game), SimpleNamespace(), cache_root=root / "cache"
            )
            try:
                with patch.object(writer, "inventory", return_value=(allocation,)):
                    self.assertIsNone(
                        session.roster_identity_edit_scope(allocation.asset_id)
                    )
                    with self.assertRaisesRegex(SessionError, "runtime-locked"):
                        session.replace_roster_identity_text(
                            allocation.asset_id, "MOD"
                        )
                    with self.assertRaisesRegex(SessionError, "runtime-locked"):
                        session.load_project(project)
                self.assertEqual(session.modifications, ())
            finally:
                session.close()

    def test_project_import_rechecks_live_owner_fingerprint(self) -> None:
        allocation = _allocation()
        changed = writer.RosterIdentityAllocation(
            **{
                **allocation.__dict__,
                "owner_fingerprint": "f" * 64,
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "game"
            game.mkdir()
            (game / "0A").write_bytes(b"fixture")
            session = ApfSession(
                _source(game), SimpleNamespace(), cache_root=root / "cache-one"
            )
            try:
                with patch.object(writer, "inventory", return_value=(allocation,)):
                    session.replace_roster_identity_text(allocation.asset_id, "MOD")
                    project = session.save_project(root / "names.apf2k8mod")
            finally:
                session.close()
            imported = ApfSession(
                _source(game), SimpleNamespace(), cache_root=root / "cache-two"
            )
            try:
                with patch.object(writer, "inventory", return_value=(changed,)):
                    with self.assertRaisesRegex(SessionError, "allocation changed"):
                        imported.load_project(project)
            finally:
                imported.close()


class RosterIdentityBuildAndRegistryTests(unittest.TestCase):
    @staticmethod
    def _tiny_game(root: Path) -> dict[str, tuple[int, str]]:
        sizes = {
            "0A": 4,
            "0B": 5,
            "1A": 6,
            "1B": 7,
            "default.xex": 8,
            "$SystemUpdate/su20076000_00000000": 9,
        }
        result: dict[str, tuple[int, str]] = {}
        for index, (relative, size) in enumerate(sizes.items(), start=1):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(bytes((index,)) * size)
            result[relative] = (size, hashlib.sha256(path.read_bytes()).hexdigest())
        return result

    def test_roster_batch_is_composed_into_transactional_copied_game(self) -> None:
        allocation = _player_allocation()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "game"
            game.mkdir()
            tree = self._tiny_game(game)
            payload = root / "replacement.json"
            data = encode_text_payload("MOD")
            payload.write_bytes(data)
            modification = Modification(
                asset_id=allocation.asset_id,
                kind="roster_identity_text",
                replacement_path=payload,
                replacement_sha256=hashlib.sha256(data).hexdigest(),
                metadata=writer.allocation_metadata(allocation),
            )
            patch_result = writer.RosterIdentityPatchResult(
                outer_index=1126,
                entry_bytes=b"MOD!",
                manifest={
                    "schema": writer.SCHEMA,
                    "mode": "patched",
                    "edits": (
                        {
                            "asset_id": allocation.asset_id,
                            **writer.allocation_metadata(allocation),
                        },
                    ),
                },
            )
            entries = [SimpleNamespace() for _ in range(1127)]
            entries[1126] = SimpleNamespace(
                size=4,
                segments=(SimpleNamespace(pack_name="0A", pack_offset=0),),
            )

            def fake_hash(path: Path, *_args: object, **_kwargs: object) -> str:
                path = Path(path)
                if path == game / "0A":
                    return EXPECTED_0A_SHA256
                return hashlib.sha256(path.read_bytes()).hexdigest()

            output = root / "output"
            with patch(
                "mod_editor.apf_studio.build.EXPECTED_TREE", tree
            ), patch(
                "mod_editor.apf_studio.build.sha256_file", side_effect=fake_hash
            ), patch(
                "mod_editor.apf_studio.build.apf_outer.parse_archive",
                return_value=SimpleNamespace(entries=entries),
            ), patch.object(
                writer, "inventory", return_value=(allocation,)
            ), patch.object(
                writer, "build_patch", return_value=patch_result
            ), patch.object(
                ApfBuildService, "_verify_composed", return_value="9" * 64
            ):
                receipt = ApfBuildService(_source(game)).build(
                    (modification,), output
                )
            self.assertEqual((game / "0A").read_bytes(), b"\x01" * 4)
            self.assertEqual((output / "0A").read_bytes(), b"MOD!")
            self.assertEqual(receipt.changed_outer_entries, (1126,))
            manifest = json.loads(receipt.manifest.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["edits"][0]["kind"], "roster_identity_text_batch"
            )
            self.assertTrue(manifest["output"]["published_atomically"])

    def test_capability_is_editable_only_with_narrow_scope_note(self) -> None:
        card = {
            item.capability_id: item for item in build_capability_cards()
        }["apf2k8.players.roster"]
        self.assertIs(card.status, ApfStatus.EDITABLE)
        findings = " ".join(card.findings)
        self.assertIn("team display-name", findings)
        self.assertIn("token-preserving", findings)
        self.assertIn("player first/last", findings.casefold())
        self.assertIn("jersey numbers", findings.casefold())
        self.assertTrue(hasattr(ApfStudioFacade, "replace_roster_identity_text"))
        self.assertTrue(hasattr(ApfStudioFacade, "revert"))

    def test_public_facade_allows_runtime_proved_roster_identity_replacement(
        self,
    ) -> None:
        facade = ApfStudioFacade()
        calls: list[tuple[str, str]] = []
        result = SimpleNamespace(asset_id="apf:roster-name:123")
        facade.session = SimpleNamespace(
            roster_identity_edit_scope=(
                lambda _asset_id: writer.PLAYER_NAME_EDIT_SCOPE
            ),
            roster_identity_is_product_editable=lambda _asset_id: True,
            replace_roster_identity_text=lambda asset_id, value: (
                calls.append((asset_id, value)) or result
            ),
        )
        facade.last_build = SimpleNamespace()
        progress: list[tuple[str, int, int]] = []
        self.assertIs(
            facade.replace_roster_identity_text(
                "apf:roster-name:123",
                "MOD",
                lambda stage, completed, total: progress.append(
                    (stage, completed, total)
                ),
            ),
            result,
        )
        self.assertEqual(calls, [("apf:roster-name:123", "MOD")])
        self.assertEqual(
            facade.roster_identity_edit_scope("apf:roster-name:123"),
            writer.PLAYER_NAME_EDIT_SCOPE,
        )
        self.assertTrue(
            facade.roster_identity_is_product_editable(
                "apf:roster-name:123"
            )
        )
        self.assertEqual(progress[-1][1:], (1, 1))
        self.assertIsNone(facade.last_build)

        facade.session = SimpleNamespace(
            roster_identity_is_product_editable=lambda _asset_id: False,
        )
        with self.assertRaisesRegex(FacadeError, "Team abbreviations"):
            facade.replace_roster_identity_text(
                "apf:roster-name:124", "MOD"
            )
        self.assertIn(
            "team abbreviations", ROSTER_IDENTITY_RUNTIME_LOCK_MESSAGE.casefold()
        )

    def test_public_build_refuses_only_locked_roster_name_modification(self) -> None:
        facade = ApfStudioFacade()
        facade.session = SimpleNamespace(
            modifications=(
                Modification(
                    asset_id="apf:roster-name:123",
                    kind="roster_identity_text",
                    replacement_path=Path("unused-replacement.json"),
                    replacement_sha256="a" * 64,
                    metadata={},
                ),
            ),
            roster_identity_is_product_editable=lambda _asset_id: False,
        )
        with self.assertRaisesRegex(FacadeError, "Revert the locked roster edit"):
            facade.build(Path("unused-output"))

    def test_public_build_admits_player_name_to_transactional_service(self) -> None:
        facade = ApfStudioFacade()
        modification = Modification(
            asset_id="apf:roster-name:124",
            kind="roster_identity_text",
            replacement_path=Path("unused-replacement.json"),
            replacement_sha256="a" * 64,
            metadata={},
        )
        facade.session = SimpleNamespace(
            modifications=(modification,),
            roster_identity_is_product_editable=lambda _asset_id: True,
        )
        facade.source = SimpleNamespace()
        receipt = SimpleNamespace(output_game=Path("output"))
        with patch.object(ApfBuildService, "build", return_value=receipt) as build:
            self.assertIs(facade.build(Path("output")), receipt)
        self.assertEqual(build.call_args.args[0], (modification,))


if __name__ == "__main__":
    unittest.main()
