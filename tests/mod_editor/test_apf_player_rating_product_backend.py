"""Product/session/project coverage for runtime-proved APF 0..99 ratings."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from mod_editor.apf_studio.backend import ensure_tools_importable
from mod_editor.apf_studio.build import ApfBuildService
from mod_editor.apf_studio.facade import ApfStudioFacade
from mod_editor.apf_studio.models import Modification
from mod_editor.apf_studio.project import ProjectError, load_project
from mod_editor.apf_studio.session import ApfSession, SessionError


ensure_tools_importable()
import apf_inner  # type: ignore  # noqa: E402
import apf_outer  # type: ignore  # noqa: E402
import apf_player_rating_patch as rating_writer  # type: ignore  # noqa: E402
import apf_roster  # type: ignore  # noqa: E402
import apf_roster_composite_patch as compositor  # type: ignore  # noqa: E402
import apf_roster_identity_patch as identity_writer  # type: ignore  # noqa: E402
import apf_texture_patch  # type: ignore  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"


def _source_body(value: int = 40) -> bytearray:
    body = bytearray(apf_roster.EXPECTED_LENGTH)
    target = rating_writer.target_for(7, "speed")
    absolute = (
        apf_roster.ROOT_SIZE
        + target.player_index * apf_roster.PLAYER_STRIDE
        + target.record_relative_offset
    )
    body[absolute] = value
    return body


def _player_tables() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            offset=apf_roster.ROOT_SIZE,
            count=rating_writer.EXPECTED_PLAYER_COUNT,
            stride=apf_roster.PLAYER_STRIDE,
        )
    ]


class PlayerRatingSessionProjectTests(unittest.TestCase):
    def test_replace_value_revert_and_retail_free_project_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = SimpleNamespace(
                index_0a=root / "source-0A",
                source_sha256="a" * 64,
            )
            first = ApfSession(source, SimpleNamespace(), cache_root=root / "cache-a")
            second = ApfSession(source, SimpleNamespace(), cache_root=root / "cache-b")
            try:
                with (
                    patch.object(apf_roster, "load_roster", return_value=(bytes(_source_body()), {})),
                    patch.object(apf_roster, "parse_root", return_value=(_player_tables(), {})),
                ):
                    self.assertEqual(first.player_base_rating_value(7, "speed"), 40)
                    modification = first.replace_player_base_rating(7, "speed", 99)
                    self.assertEqual(
                        modification.asset_id, "apf:player-rating:7:speed"
                    )
                    self.assertEqual(modification.kind, "player_base_rating")
                    self.assertEqual(first.player_base_rating_value(7, "speed"), 99)
                    self.assertEqual(
                        json.loads(modification.replacement_path.read_text()),
                        {
                            "schema": "apf2k8_player_rating_replacement/v1",
                            "value": 99,
                        },
                    )
                    self.assertEqual(
                        modification.metadata,
                        {
                            "player_index": 7,
                            "field_id": "speed",
                            "record_relative_offset": 0xBA,
                            "public_minimum": 0,
                            "public_maximum": 99,
                        },
                    )
                    project = first.save_project(root / "ratings.apf2k8mod")
                    with zipfile.ZipFile(project) as archive:
                        manifest = json.loads(archive.read("project.json"))
                        self.assertEqual(manifest["replacement_count"], 1)
                        row = manifest["replacements"][0]
                        self.assertEqual(row["asset_id"], modification.asset_id)
                        self.assertEqual(row["kind"], "player_base_rating")
                        self.assertEqual(
                            set(row["metadata"]),
                            {
                                "player_index",
                                "field_id",
                                "record_relative_offset",
                                "public_minimum",
                                "public_maximum",
                            },
                        )
                        self.assertEqual(
                            set(json.loads(archive.read(row["payload"]))),
                            {"schema", "value"},
                        )
                        self.assertTrue(
                            {
                                "source_value",
                                "preimage",
                                "record",
                                "record_bytes",
                                "byte_offset",
                                "pack_offset",
                            }.isdisjoint(row["metadata"])
                        )
                    self.assertEqual(second.load_project(project), 1)
                    self.assertEqual(second.player_base_rating_value(7, "speed"), 99)
                    asset_id = modification.asset_id
                    self.assertTrue(second.revert(asset_id))
                    self.assertEqual(second.player_base_rating_value(7, "speed"), 40)
            finally:
                first.close()
                second.close()

    def test_rating_input_is_strict_integer_0_to_99(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = SimpleNamespace(index_0a=root / "0A", source_sha256="a" * 64)
            session = ApfSession(source, SimpleNamespace(), cache_root=root / "cache")
            try:
                with (
                    patch.object(apf_roster, "load_roster", return_value=(bytes(_source_body()), {})),
                    patch.object(apf_roster, "parse_root", return_value=(_player_tables(), {})),
                ):
                    for value in (-1, 100, True, 50.0, "50"):
                        with self.subTest(value=value):
                            with self.assertRaisesRegex(SessionError, "0 to 99"):
                                session.replace_player_base_rating(7, "speed", value)  # type: ignore[arg-type]
                    with self.assertRaisesRegex(SessionError, "Unknown"):
                        session.replace_player_base_rating(7, "not_a_field", 50)
            finally:
                session.close()

    def test_project_rejects_noncanonical_or_retargeted_rating(self) -> None:
        payload = rating_writer.encode_replacement_payload(99)
        target = rating_writer.target_for(7, "speed")
        from mod_editor.apf_studio.models import Modification
        from mod_editor.apf_studio.project import save_project

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "rating.json"
            path.write_bytes(payload)
            bad = Modification(
                asset_id=target.asset_id,
                kind="player_base_rating",
                replacement_path=path,
                replacement_sha256=hashlib.sha256(payload).hexdigest(),
                metadata={**rating_writer.target_metadata(target), "player_index": 8},
            )
            with self.assertRaisesRegex(ProjectError, "target metadata changed"):
                save_project(
                    root / "bad.apf2k8mod",
                    source_sha256="a" * 64,
                    modifications=(bad,),
                )

    def test_facade_delegates_value_replace_and_invalidates_last_build(self) -> None:
        session = SimpleNamespace(
            player_base_rating_value=lambda player, field: (player, field, 41)[2],
            replace_player_base_rating=lambda player, field, value: (
                player,
                field,
                value,
            ),
        )
        facade = ApfStudioFacade()
        facade.session = session  # type: ignore[assignment]
        facade.last_build = SimpleNamespace()
        events: list[tuple[str, int, int]] = []
        self.assertEqual(facade.player_base_rating_value(2, "catch"), 41)
        self.assertEqual(
            facade.replace_player_base_rating(
                2, "catch", 88, lambda *event: events.append(event)
            ),
            (2, "catch", 88),
        )
        self.assertEqual(
            events,
            [
                ("Checking player base rating", 0, 1),
                ("Checking player base rating", 1, 1),
            ],
        )
        self.assertIsNone(facade.last_build)


@unittest.skipUnless(SOURCE.is_file(), "private APF source is unavailable")
class RealRosterCompositionTests(unittest.TestCase):
    def test_team_name_and_rating_compose_into_one_disjoint_runtime_entry(self) -> None:
        allocations = identity_writer.inventory(SOURCE)
        team_name = next(
            row
            for row in allocations
            if any(
                owner.entity_kind == "team"
                and owner.entity_index == 0
                and owner.field == "display_name"
                for owner in row.known_owners
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identity_payload = (
                b'{"schema":"apf2k8_text_replacement/v1","text":"CODEXTEAM"}\n'
            )
            rating_payload = rating_writer.encode_replacement_payload(99)
            identity_path = root / "identity.json"
            rating_path = root / "rating.json"
            identity_path.write_bytes(identity_payload)
            rating_path.write_bytes(rating_payload)
            identity_modification = Modification(
                asset_id=team_name.asset_id,
                kind="roster_identity_text",
                replacement_path=identity_path,
                replacement_sha256=hashlib.sha256(identity_payload).hexdigest(),
                metadata=identity_writer.allocation_metadata(team_name),
            )
            rating_target = rating_writer.target_for(788, "speed")
            rating_modification = Modification(
                asset_id=rating_target.asset_id,
                kind="player_base_rating",
                replacement_path=rating_path,
                replacement_sha256=hashlib.sha256(rating_payload).hexdigest(),
                metadata=rating_writer.target_metadata(rating_target),
            )
            service = ApfBuildService(SimpleNamespace(index_0a=SOURCE))
            result, receipt = service._compile_roster_composite_groups(
                (identity_modification,), (rating_modification,)
            )
        self.assertEqual(
            receipt["kind"], "roster_identity_and_player_rating_batch"
        )
        self.assertEqual(set(receipt["asset_ids"]), {
            team_name.asset_id,
            "apf:player-rating:788:speed",
        })
        self.assertEqual(
            receipt["runtime_status"],
            "runtime_proved_token_preserving_roster_consumers",
        )
        self.assertEqual(result.outer_index, apf_roster.OUTER_TABLE_INDEX)
        self.assertEqual(result.manifest["mode"], "patched")
        output = result.manifest["output"]
        self.assertGreater(output["identity_changed_byte_count"], 0)
        self.assertEqual(output["player_rating_changed_byte_count"], 1)
        self.assertEqual(
            output["decoded_changed_byte_count"],
            output["identity_changed_byte_count"] + 1,
        )
        self.assertTrue(
            result.manifest["validation"]["component_decoded_deltas_disjoint"]
        )

        archive = apf_outer.parse_archive(SOURCE)
        entry = archive.entries[apf_roster.OUTER_TABLE_INDEX]
        memory = apf_texture_patch.BytesReader(result.entry_bytes)
        record = apf_inner.parse_iff(memory, entry)
        block = apf_inner.decode_block(memory, record, 0, compositor.MAX_DECOMPRESSED)
        part = record.files[0].parts[0]
        body = block[part.offset : part.offset + part.length]
        rating_offset = apf_roster.ROOT_SIZE + 788 * apf_roster.PLAYER_STRIDE + 0xBA
        self.assertEqual(body[rating_offset], 99)
        refreshed = identity_writer.inventory_from_decoded(body)
        self.assertEqual(
            next(row for row in refreshed if row.pool_index == team_name.pool_index).text,
            "CODEXTEAM",
        )


if __name__ == "__main__":
    unittest.main()
