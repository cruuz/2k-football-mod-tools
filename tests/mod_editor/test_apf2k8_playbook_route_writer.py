from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mod_editor.core.apf2k8_playbook_route_writer import (
    MASTER_ASSET_ID,
    RouteCloneRequest,
    build_relayed_copy_requests,
    compile_route_clones,
    relay_candidates,
    request_from_mapping,
    verify_route_clones,
)
from mod_editor.core.errors import ValidationError
from mod_editor.apf_studio.backend import ensure_tools_importable
from mod_editor.apf_studio.models import ApfSource
from mod_editor.apf_studio.project import load_project
from mod_editor.apf_studio.session import ApfSession


ensure_tools_importable()
import playbook_inventory  # type: ignore  # noqa: E402


def _relative(target: int, field: int) -> bytes:
    return struct.pack(">i", target - field + 1)


def _synthetic_master() -> bytes:
    data = bytearray(playbook_inventory.APF_BODY_SIZE)
    data[0x0C:0x10] = b"YALP"
    struct.pack_into("<I", data, 0x10, 0x20)
    struct.pack_into("<I", data, 0x14, 0)
    data[0x20:0x28] = "mpb".encode("utf-16be") + b"\0\0"
    struct.pack_into(">IIII", data, 0x34, 1, 2, 1, 2)

    names = ("MASTER", "Trips", "Alpha", "Bravo", "Pass")
    cursor = playbook_inventory.APF_STRING_BASE
    offsets: list[int] = []
    for name in names:
        offsets.append(cursor)
        encoded = name.encode("utf-16be") + b"\0\0"
        data[cursor : cursor + len(encoded)] = encoded
        cursor += len(encoded)
    data[0x30:0x34] = _relative(offsets[0], 0x30)

    category = playbook_inventory.APF_CATEGORY_BASE
    formation = playbook_inventory.APF_FORMATION_BASE
    plays = [
        playbook_inventory.APF_PLAY_BASE,
        playbook_inventory.APF_PLAY_BASE + playbook_inventory.APF_PLAY_SIZE,
    ]
    data[category : category + 4] = _relative(offsets[4], category)
    data[formation : formation + 4] = _relative(offsets[1], formation)
    route_nodes = [
        playbook_inventory.APF_ROUTE_BASE,
        playbook_inventory.APF_ROUTE_BASE + playbook_inventory.ROUTE_NODE_SIZE,
    ]
    data[route_nodes[0] : route_nodes[0] + 8] = b"NODEZERO"
    data[route_nodes[1] : route_nodes[1] + 8] = b"NODE_ONE"
    for play_index, play in enumerate(plays):
        data[play : play + 4] = _relative(offsets[2 + play_index], play)
        struct.pack_into(">II", data, play + 4, 0x100 + play_index, 0x200)
        for slot in range(playbook_inventory.SLOT_COUNT):
            descriptor = play + 0x0C + slot * 8
            pointer = descriptor + 4
            struct.pack_into(">I", data, descriptor, 0xA0000000 | play_index << 8 | slot)
            node = route_nodes[(play_index + slot) % 2]
            data[pointer : pointer + 4] = _relative(node, pointer)
    return bytes(data)


def _slot_pointer(play_index: int, slot_index: int) -> int:
    return (
        playbook_inventory.APF_PLAY_BASE
        + play_index * playbook_inventory.APF_PLAY_SIZE
        + 0x0C
        + slot_index * 8
        + 4
    )


def _slot_fields(play_index: int, slot_index: int) -> range:
    start = _slot_pointer(play_index, slot_index) - 4
    return range(start, start + 8)


def _route_node_offset(node_index: int) -> int:
    return (
        playbook_inventory.APF_ROUTE_BASE
        + node_index * playbook_inventory.ROUTE_NODE_SIZE
    )


def _route_every_slot_to(node_index: int, keep: tuple[int, int]) -> bytes:
    body = bytearray(_synthetic_master())
    for play_index in range(2):
        for slot in range(playbook_inventory.SLOT_COUNT):
            if (play_index, slot) == keep:
                continue
            pointer = _slot_pointer(play_index, slot)
            body[pointer : pointer + 4] = _relative(
                _route_node_offset(node_index), pointer
            )
    return bytes(body)


def _three_node_master(unique_on: tuple[int, int]) -> bytes:
    body = bytearray(_synthetic_master())
    struct.pack_into(">IIII", body, 0x34, 1, 2, 1, 3)
    pointer = _slot_pointer(*unique_on)
    body[pointer : pointer + 4] = _relative(_route_node_offset(2), pointer)
    return bytes(body)


class RouteWriterTests(unittest.TestCase):
    def test_clone_copies_descriptor_and_reencodes_only_target_pointer(
        self,
    ) -> None:
        source = _synthetic_master()
        request = RouteCloneRequest(0, 0, 1, 0)
        result = compile_route_clones(source, [request])
        target_descriptor = playbook_inventory.APF_PLAY_BASE + 0x0C
        target_pointer = target_descriptor + 4
        donor_descriptor = (
            playbook_inventory.APF_PLAY_BASE
            + playbook_inventory.APF_PLAY_SIZE
            + 0x0C
        )
        donor_pointer = donor_descriptor + 4

        self.assertEqual(result.asset_id, MASTER_ASSET_ID)
        self.assertEqual(
            result.replacement[target_descriptor : target_descriptor + 4],
            source[donor_descriptor : donor_descriptor + 4],
        )
        self.assertNotEqual(
            result.replacement[target_pointer : target_pointer + 4],
            source[donor_pointer : donor_pointer + 4],
        )
        self.assertTrue(
            all(
                target_descriptor <= index < target_pointer + 4
                for start, end in result.changed_ranges
                for index in range(start, end)
            )
        )
        self.assertEqual(
            result.parsed_replacement["plays"][0]["slots"][0][
                "route_node_index"
            ],
            1,
        )
        self.assertEqual(
            result.parsed_replacement["route_node_blob_sha256"],
            playbook_inventory.parse_apf_body(source, 180, 0)[
                "route_node_blob_sha256"
            ],
        )
        self.assertFalse(result.report["claims"]["contains_retail_bytes"])

    def test_verifier_rejects_even_parseable_unowned_change(self) -> None:
        source = _synthetic_master()
        request = RouteCloneRequest(0, 0, 1, 0)
        result = compile_route_clones(source, [request])
        tampered = bytearray(result.replacement)
        # Another valid descriptor word, outside the selected target slot.
        tampered[playbook_inventory.APF_PLAY_BASE + 0x14] ^= 1
        with self.assertRaisesRegex(ValidationError, "unowned byte"):
            verify_route_clones(source, bytes(tampered), [request])

    def test_rejects_identity_and_duplicate_targets(self) -> None:
        source = _synthetic_master()
        with self.assertRaisesRegex(ValidationError, "different APF donor"):
            compile_route_clones(source, [RouteCloneRequest(0, 0, 0, 0)])
        with self.assertRaisesRegex(ValidationError, "repeats one target"):
            compile_route_clones(
                source,
                [
                    RouteCloneRequest(0, 0, 1, 0),
                    RouteCloneRequest(0, 0, 1, 1),
                ],
            )

    def test_shareable_mapping_has_only_logical_coordinates(self) -> None:
        request = request_from_mapping(
            {
                "asset_id": MASTER_ASSET_ID,
                "target_play_index": 0,
                "target_slot_index": 2,
                "donor_play_index": 1,
                "donor_slot_index": 3,
            }
        )
        self.assertEqual(
            request.provider_edit(),
            {
                "kind": "play_assignment_route",
                "asset_id": MASTER_ASSET_ID,
                "target_play_index": 0,
                "target_slot_index": 2,
                "donor_play_index": 1,
                "donor_slot_index": 3,
            },
        )

    def test_membership_parser_is_msb_first_and_rejects_unused_play_bits(
        self,
    ) -> None:
        source = bytearray(_synthetic_master())
        source[playbook_inventory.APF_FORMATION_MEMBERSHIP_BASE] = 0x40
        rows, table = playbook_inventory.parse_apf_formation_memberships(
            bytes(source), formation_count=1, play_count=2
        )
        self.assertEqual(rows[0]["play_indices"], [1])
        self.assertEqual(
            table["mask_bit_order"], "MSB-first within each byte"
        )
        source[playbook_inventory.APF_FORMATION_MEMBERSHIP_BASE] |= 0x20
        with self.assertRaisesRegex(
            playbook_inventory.PlaybookError, "unused membership"
        ):
            playbook_inventory.parse_apf_formation_memberships(
                bytes(source), formation_count=1, play_count=2
            )

    def test_relayed_copy_batch_preserves_start_set_and_donor_bytes(self) -> None:
        source = _route_every_slot_to(1, keep=(0, 0))
        target = (0, 0)
        donor = (1, 0)
        relay = (0, 1)
        requests = build_relayed_copy_requests(target, donor, relay)
        self.assertEqual(
            [(item.target_play_index, item.target_slot_index) for item in requests],
            [target, relay],
        )
        self.assertEqual(
            [(item.donor_play_index, item.donor_slot_index) for item in requests],
            [donor, target],
        )
        result = compile_route_clones(source, requests)

        def starts(parsed) -> list[int]:
            return sorted(
                int(slot["route_node_index"])
                for play in parsed["plays"]
                for slot in play["slots"]
            )

        self.assertEqual(
            starts(result.parsed_replacement),
            starts(playbook_inventory.parse_apf_body(source, 180, 0)),
        )
        # The target took the donor's route; the target's unique chain now
        # survives on the relay slot.
        self.assertEqual(
            result.parsed_replacement["plays"][0]["slots"][0]["route_node_index"],
            1,
        )
        self.assertEqual(
            result.parsed_replacement["plays"][0]["slots"][1]["route_node_index"],
            0,
        )
        donor_fields = playbook_inventory.APF_PLAY_BASE + playbook_inventory.APF_PLAY_SIZE + 0x0C
        self.assertEqual(
            result.replacement[donor_fields : donor_fields + 8],
            source[donor_fields : donor_fields + 8],
        )
        allowed = set(_slot_fields(*target)) | set(_slot_fields(*relay))
        self.assertTrue(
            all(
                index in allowed
                for start, end in result.changed_ranges
                for index in range(start, end)
            )
        )
        self.assertTrue(
            result.report["claims"]["assignment_chain_start_set_preserved"]
        )
        self.assertFalse(result.report["claims"]["contains_retail_bytes"])
        self.assertFalse(
            result.report["claims"][
                "waypoint_coordinate_or_opcode_semantics_claimed"
            ]
        )
        verify_route_clones(source, result.replacement, requests)

    def test_relay_candidates_exclude_target_donor_and_unique(self) -> None:
        source = _three_node_master(unique_on=(0, 5))
        candidates = relay_candidates(source, 0, 0, 1, 0)
        self.assertNotIn((0, 0), candidates)
        self.assertNotIn((0, 5), candidates)
        self.assertFalse(any(play_index == 1 for play_index, _slot in candidates))
        self.assertEqual(
            candidates,
            tuple((0, slot) for slot in range(1, 11) if slot != 5),
        )
        from_parsed = relay_candidates(
            playbook_inventory.parse_apf_body(source, 180, 0), 0, 0, 1, 0
        )
        self.assertEqual(from_parsed, candidates)
        with self.assertRaisesRegex(ValidationError, "outside APF MASTER PLAY|between 0 and 10"):
            relay_candidates(source, 99, 0, 1, 0)


def _source(root: Path) -> ApfSource:
    path = root / "game" / "0A"
    return ApfSource(
        selected_path=path,
        game_root=path.parent,
        index_0a=path,
        source_sha256="a" * 64,
        source_size=1,
        xex_sha256="b" * 64,
        display_name="Synthetic APF",
    )


class SessionRouteWriterTests(unittest.TestCase):
    def test_session_route_clone_is_undoable_revertible_and_project_safe(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            body = _synthetic_master()
            session = ApfSession(
                _source(tmp_path),
                SimpleNamespace(),
                cache_root=tmp_path / "cache-a",
            )
            with patch(
                "mod_editor.apf_studio.session.read_master_play_body",
                return_value=body,
            ):
                modification = session.replace_play_assignment_route(0, 0, 1, 0)
                self.assertEqual(modification.kind, "play_assignment_route")
                self.assertEqual(
                    modification.asset_id,
                    "play-route:apf:playbook:180:0:p0:s0",
                )
                self.assertEqual(session.modified_count, 1)
                self.assertTrue(session.undo())
                self.assertEqual(session.modified_count, 0)
                session.swap_play_assignment_routes(0, 0, 1, 0)
                self.assertEqual(session.modified_count, 2)
                self.assertTrue(
                    session.revert("play-route:apf:playbook:180:0:p0:s0")
                )
                self.assertEqual(session.modified_count, 1)
                self.assertTrue(session.undo())
                self.assertEqual(session.modified_count, 2)

                project_path = tmp_path / "routes.apf2k8mod"
                session.save_project(project_path)
                _manifest, loaded, _annotations = load_project(
                    project_path,
                    expected_source_sha256="a" * 64,
                    destination_dir=tmp_path / "unpacked",
                )
                self.assertEqual(len(loaded), 2)
                self.assertTrue(
                    all(
                        item.replacement_path.suffix == ".json"
                        for item in loaded
                    )
                )

                imported = ApfSession(
                    _source(tmp_path),
                    SimpleNamespace(),
                    cache_root=tmp_path / "cache-b",
                )
                with patch(
                    "mod_editor.apf_studio.session.read_master_play_body",
                    return_value=body,
                ):
                    self.assertEqual(imported.load_project(project_path), 2)
                    self.assertEqual(imported.modified_count, 2)

    def test_session_rejects_orphaning_a_unique_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            body = bytearray(_synthetic_master())
            # Make target play 0 / slot 0 the only pointer to node 0 by routing
            # all other assignments to node 1.
            for play_index in range(2):
                for slot in range(playbook_inventory.SLOT_COUNT):
                    if (play_index, slot) == (0, 0):
                        continue
                    pointer = (
                        playbook_inventory.APF_PLAY_BASE
                        + play_index * playbook_inventory.APF_PLAY_SIZE
                        + 0x10
                        + slot * 8
                    )
                    body[pointer : pointer + 4] = _relative(
                        playbook_inventory.APF_ROUTE_BASE
                        + playbook_inventory.ROUTE_NODE_SIZE,
                        pointer,
                    )
            session = ApfSession(
                _source(tmp_path),
                SimpleNamespace(),
                cache_root=tmp_path / "cache",
            )
            with patch(
                "mod_editor.apf_studio.session.read_master_play_body",
                return_value=bytes(body),
            ):
                with self.assertRaisesRegex(
                    Exception, "only used on the target play"
                ):
                    session.replace_play_assignment_route(0, 0, 1, 0)
            self.assertEqual(session.modified_count, 0)

    def _relay_session(self, tmp_path: Path) -> ApfSession:
        return ApfSession(
            _source(tmp_path),
            SimpleNamespace(),
            cache_root=tmp_path / "cache",
        )

    def test_session_relayed_copy_stages_pair_and_preserves_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            body = _route_every_slot_to(1, keep=(0, 0))
            session = self._relay_session(tmp_path)
            with patch(
                "mod_editor.apf_studio.session.read_master_play_body",
                return_value=body,
            ):
                first, second = session.copy_play_assignment_route_via_relay(
                    0, 0, 1, 0, 0, 1
                )
                self.assertEqual(
                    first.asset_id, "play-route:apf:playbook:180:0:p0:s0"
                )
                self.assertEqual(
                    second.asset_id, "play-route:apf:playbook:180:0:p0:s1"
                )
                # Both clones land as a single Undo step.
                self.assertEqual(session.modified_count, 2)
                self.assertTrue(session.undo())
                self.assertEqual(session.modified_count, 0)

    def test_session_relayed_copy_candidates_exclude_target_donor_unique(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            body = _three_node_master(unique_on=(0, 5))
            session = self._relay_session(tmp_path)
            with patch(
                "mod_editor.apf_studio.session.read_master_play_body",
                return_value=body,
            ):
                candidates = session.relay_play_assignment_route_candidates(
                    0, 0, 1, 0
                )
                self.assertNotIn((0, 0), candidates)
                self.assertNotIn((0, 5), candidates)
                self.assertFalse(
                    any(play_index == 1 for play_index, _slot in candidates)
                )
                self.assertEqual(
                    candidates,
                    tuple((0, slot) for slot in range(1, 11) if slot != 5),
                )

    def test_session_relayed_copy_refuses_target_donor_and_unique_relay(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            body = _three_node_master(unique_on=(0, 5))
            session = self._relay_session(tmp_path)
            with patch(
                "mod_editor.apf_studio.session.read_master_play_body",
                return_value=body,
            ):
                with self.assertRaisesRegex(
                    Exception, "different from both the target"
                ):
                    session.copy_play_assignment_route_via_relay(
                        0, 0, 1, 0, 0, 0
                    )
                with self.assertRaisesRegex(
                    Exception, "different from both the target"
                ):
                    session.copy_play_assignment_route_via_relay(
                        0, 0, 1, 0, 1, 0
                    )
                with self.assertRaisesRegex(
                    Exception, "another play so the donor play stays"
                ):
                    session.copy_play_assignment_route_via_relay(
                        0, 0, 1, 0, 1, 3
                    )
                with self.assertRaisesRegex(
                    Exception, "relay slot's current route is only used"
                ):
                    session.copy_play_assignment_route_via_relay(
                        0, 0, 1, 0, 0, 5
                    )
            self.assertEqual(session.modified_count, 0)


if __name__ == "__main__":
    unittest.main()
