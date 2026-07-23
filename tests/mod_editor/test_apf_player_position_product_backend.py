"""Product transport, project, inspector, and composition tests for positions."""

from __future__ import annotations

from types import SimpleNamespace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from mod_editor.apf_studio.backend import ensure_tools_importable
from mod_editor.apf_studio.build import ApfBuildService, BuildError
from mod_editor.apf_studio.facade import ApfStudioFacade
from mod_editor.apf_studio.inspectors import inspect_roster
from mod_editor.apf_studio.models import Modification
from mod_editor.apf_studio.project import ProjectError, save_project
from mod_editor.apf_studio.session import ApfSession, SessionError


ensure_tools_importable()
import apf_inner  # type: ignore  # noqa: E402
import apf_outer  # type: ignore  # noqa: E402
import apf_player_position_patch as position_writer  # type: ignore  # noqa: E402
import apf_player_rating_patch as rating_writer  # type: ignore  # noqa: E402
import apf_roster  # type: ignore  # noqa: E402
import apf_roster_composite_patch as compositor  # type: ignore  # noqa: E402
import apf_roster_identity_patch as identity_writer  # type: ignore  # noqa: E402
import apf_texture_patch  # type: ignore  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"


def _source_body(player_index: int = 7, code: int = 0) -> bytearray:
    body = bytearray(apf_roster.EXPECTED_LENGTH)
    start = apf_roster.ROOT_SIZE + player_index * apf_roster.PLAYER_STRIDE
    body[start + 0x34] = body[start + 0x35] = code
    return body


def _player_tables() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            offset=apf_roster.ROOT_SIZE,
            count=position_writer.EXPECTED_PLAYER_COUNT,
            stride=apf_roster.PLAYER_STRIDE,
        )
    ]


class PlayerPositionSessionProjectTests(unittest.TestCase):
    def test_replace_value_revert_and_retail_free_project_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = SimpleNamespace(
                index_0a=root / "source-0A", source_sha256="a" * 64
            )
            first = ApfSession(source, SimpleNamespace(), cache_root=root / "cache-a")
            second = ApfSession(source, SimpleNamespace(), cache_root=root / "cache-b")
            try:
                with (
                    patch.object(
                        apf_roster,
                        "load_roster",
                        return_value=(bytes(_source_body()), {}),
                    ),
                    patch.object(
                        apf_roster, "parse_root", return_value=(_player_tables(), {})
                    ),
                ):
                    self.assertEqual(first.player_position_value(7), 0)
                    modification = first.replace_player_position(7, 3)
                    self.assertEqual(modification.asset_id, "apf:player-position:7")
                    self.assertEqual(modification.kind, "player_position")
                    self.assertEqual(first.player_position_value(7), 3)
                    project = first.save_project(root / "position.apf2k8mod")
                    with zipfile.ZipFile(project) as archive:
                        manifest = json.loads(archive.read("project.json"))
                        row = manifest["replacements"][0]
                        payload = json.loads(archive.read(row["payload"]))
                    self.assertEqual(
                        payload,
                        {
                            "schema": "apf2k8_player_position_replacement/v1",
                            "value": 3,
                        },
                    )
                    self.assertEqual(
                        set(row["metadata"]),
                        {
                            "player_index",
                            "semantic_relative_offset",
                            "mirror_relative_offset",
                            "minimum_code",
                            "maximum_code",
                            "source_mirror_required",
                        },
                    )
                    self.assertTrue(
                        {
                            "source_value",
                            "source_code",
                            "preimage",
                            "record",
                            "record_bytes",
                            "pointer",
                            "pack_offset",
                        }.isdisjoint(row["metadata"])
                    )
                    self.assertEqual(second.load_project(project), 1)
                    self.assertEqual(second.player_position_value(7), 3)
                    self.assertTrue(second.revert(modification.asset_id))
                    self.assertEqual(second.player_position_value(7), 0)
            finally:
                first.close()
                second.close()

    def test_session_rejects_bad_code_and_broken_source_mirror(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = SimpleNamespace(index_0a=root / "0A", source_sha256="a" * 64)
            session = ApfSession(source, SimpleNamespace(), cache_root=root / "cache")
            try:
                with (
                    patch.object(
                        apf_roster,
                        "load_roster",
                        return_value=(bytes(_source_body()), {}),
                    ),
                    patch.object(
                        apf_roster, "parse_root", return_value=(_player_tables(), {})
                    ),
                ):
                    for value in (-1, 17, True, 3.0, "3"):
                        with self.subTest(value=value):
                            with self.assertRaisesRegex(SessionError, "0 to 16"):
                                session.replace_player_position(7, value)  # type: ignore[arg-type]
                broken = _source_body()
                start = apf_roster.ROOT_SIZE + 7 * apf_roster.PLAYER_STRIDE
                broken[start + 0x35] = 1
                session._player_rating_source_body = bytes(broken)
                with self.assertRaisesRegex(SessionError, "mirror"):
                    session.player_position_source_value(7)
            finally:
                session.close()

    def test_project_rejects_retargeted_metadata_and_noncanonical_code(self) -> None:
        target = position_writer.target_for(7)
        payload = position_writer.encode_replacement_payload(3)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "position.json"
            path.write_bytes(payload)
            modification = Modification(
                target.asset_id,
                "player_position",
                path,
                hashlib.sha256(payload).hexdigest(),
                {**position_writer.target_metadata(target), "mirror_relative_offset": 0x36},
            )
            with self.assertRaisesRegex(ProjectError, "target metadata changed"):
                save_project(
                    root / "bad.apf2k8mod",
                    source_sha256="a" * 64,
                    modifications=(modification,),
                )
            path.write_bytes(
                b'{"value":17,"schema":"apf2k8_player_position_replacement/v1"}'
            )
            changed = path.read_bytes()
            modification = Modification(
                target.asset_id,
                "player_position",
                path,
                hashlib.sha256(changed).hexdigest(),
                position_writer.target_metadata(target),
            )
            with self.assertRaisesRegex(ProjectError, "payload is invalid"):
                save_project(
                    root / "bad-code.apf2k8mod",
                    source_sha256="a" * 64,
                    modifications=(modification,),
                )

    def test_facade_delegates_and_invalidates_last_build(self) -> None:
        session = SimpleNamespace(
            player_position_value=lambda player: (player, 4)[1],
            replace_player_position=lambda player, value: (player, value),
        )
        facade = ApfStudioFacade()
        facade.session = session  # type: ignore[assignment]
        facade.last_build = SimpleNamespace()
        events: list[tuple[str, int, int]] = []
        self.assertEqual(facade.player_position_value(2), 4)
        self.assertEqual(
            facade.replace_player_position(
                2, 3, lambda *event: events.append(event)
            ),
            (2, 3),
        )
        self.assertEqual(
            events,
            [
                ("Checking player position", 0, 1),
                ("Checking player position", 1, 1),
            ],
        )
        self.assertIsNone(facade.last_build)

    def test_build_group_rejects_duplicate_player(self) -> None:
        target = position_writer.target_for(7)
        payload = position_writer.encode_replacement_payload(3)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "position.json"
            path.write_bytes(payload)
            modification = Modification(
                target.asset_id,
                "player_position",
                path,
                hashlib.sha256(payload).hexdigest(),
                position_writer.target_metadata(target),
            )
            service = ApfBuildService(SimpleNamespace(index_0a=Path("source/0A")))
            with self.assertRaisesRegex(BuildError, "edited twice"):
                service._compile_player_position_group(
                    (modification, modification)
                )


@unittest.skipUnless(SOURCE.is_file(), "private APF source is unavailable")
class RealPositionInspectorAndCompositionTests(unittest.TestCase):
    @staticmethod
    def _body(entry_bytes: bytes) -> bytes:
        archive = apf_outer.parse_archive(SOURCE)
        entry = archive.entries[apf_roster.OUTER_TABLE_INDEX]
        memory = apf_texture_patch.BytesReader(entry_bytes)
        record = apf_inner.parse_iff(memory, entry)
        block = apf_inner.decode_block(memory, record, 0, compositor.MAX_DECOMPRESSED)
        part = record.files[0].parts[0]
        return block[part.offset : part.offset + part.length]

    def test_roster_inspector_exposes_stable_editor_and_all_choices(self) -> None:
        snapshot = inspect_roster(SimpleNamespace(index_0a=SOURCE))
        player = next(row for row in snapshot.model.rows if row.kind == "player")
        editor = player.fields["position_editor"]
        self.assertEqual(
            editor["asset_id"],
            f"apf:player-position:{player.fields['player_index']}",
        )
        self.assertTrue(editor["editable"])
        self.assertTrue(editor["backend_editable"])
        self.assertEqual(editor["gui_status"], "semantic_dropdown_enabled")
        self.assertEqual(
            (editor["semantic_relative_offset"], editor["mirror_relative_offset"]),
            (0x34, 0x35),
        )
        self.assertEqual(len(editor["choices"]), 17)
        self.assertEqual(editor["choices"][7]["abbreviation"], "HB")
        self.assertEqual(
            editor["runtime_status"],
            "offline_writer_proved_runtime_spot_check_pending",
        )

    def test_position_composes_with_rating_identity_and_all_three(self) -> None:
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
        identity = identity_writer.build_patch(
            SOURCE, {team_name.pool_index: "CODEXTEAM"}
        )
        ratings = rating_writer.build_patch(SOURCE, {788: {"speed": 99}})
        positions = position_writer.build_patch(SOURCE, {788: 3})
        results = (
            compositor.compose_components(
                SOURCE, ratings=ratings, positions=positions
            ),
            compositor.compose_components(
                SOURCE, identity=identity, positions=positions
            ),
            compositor.compose_components(
                SOURCE,
                identity=identity,
                ratings=ratings,
                positions=positions,
            ),
        )
        start = apf_roster.ROOT_SIZE + 788 * apf_roster.PLAYER_STRIDE
        for result in results:
            with self.subTest(schemas=result.manifest["component_schemas"]):
                body = self._body(result.entry_bytes)
                self.assertEqual(body[start + 0x34 : start + 0x36], b"\x03\x03")
                self.assertTrue(
                    result.manifest["validation"][
                        "component_decoded_deltas_disjoint"
                    ]
                )
                self.assertTrue(
                    result.manifest["validation"][
                        "position_semantic_mirror_pair_indivisible"
                    ]
                )
        rating_position_body = self._body(results[0].entry_bytes)
        self.assertEqual(rating_position_body[start + 0xBA], 99)
        all_body = self._body(results[2].entry_bytes)
        refreshed = identity_writer.inventory_from_decoded(all_body)
        self.assertEqual(
            next(row for row in refreshed if row.pool_index == team_name.pool_index).text,
            "CODEXTEAM",
        )

        tampered_manifest = dict(positions.manifest)
        tampered_rows = [dict(row) for row in tampered_manifest["edits"]]
        tampered_rows[0]["mirror_relative_offset"] = 0x36
        tampered_manifest["edits"] = tuple(tampered_rows)
        tampered = position_writer.PlayerPositionPatchResult(
            positions.outer_index, positions.entry_bytes, tampered_manifest
        )
        with self.assertRaisesRegex(
            compositor.RosterCompositeError, "metadata changed"
        ):
            compositor.compose_components(
                SOURCE, ratings=ratings, positions=tampered
            )


if __name__ == "__main__":
    unittest.main()
