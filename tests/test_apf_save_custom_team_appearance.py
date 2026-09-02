"""Safety and real-sample coverage for raw-save custom-team appearance edits."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS = PROJECT_ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import apf_custom_team_appearance_patch as appearance_writer  # noqa: E402
import apf_roster  # noqa: E402
import apf_save_custom_team_appearance as writer  # noqa: E402
import apf_stfs_roster_extract as stfs_reader  # noqa: E402
from mod_editor.apf_studio import save_appearance as service  # noqa: E402


TEAM_START = 0x0B8078
PALETTE_START = 0x1DD04C
SELECTOR_START = 0x1E022C
CONFIG_START = 0x1E7BC0
REAL_RAW_SAVE = Path("/home/noah/Downloads/apfe/Roster.ROS")


def _relative_pointer(field: int, target: int) -> int:
    return (target - field + 1) & 0xFFFFFFFF


def synthetic_save() -> bytes:
    """Build the smallest complete graph accepted by the fail-closed parser."""

    name_start = CONFIG_START + 40 * writer.CONFIG_STRIDE
    data = bytearray(name_start + 0x1000)
    data[:4] = b"TEST"
    for index, count in enumerate(apf_roster.EXPECTED_COUNTS):
        field = writer.ROOT_OFFSET + index * 8
        struct.pack_into(">I", data, field, count)
    for index, target in (
        (writer.TEAM_TABLE_INDEX, TEAM_START),
        (writer.CONFIG_TABLE_INDEX, CONFIG_START),
    ):
        field = writer.ROOT_OFFSET + index * 8 + 4
        struct.pack_into(">I", data, field, _relative_pointer(field, target))

    for palette_index in range(apf_roster.EXPECTED_COUNTS[writer.PALETTE_TABLE_INDEX]):
        offset = PALETTE_START + palette_index * writer.PALETTE_STRIDE
        colors = tuple(
            0xFF000000 | ((palette_index * 29 + color_index * 13) & 0x00FFFFFF)
            for color_index in range(10)
        )
        struct.pack_into(">10I", data, offset, *colors)
        data[offset + 40 : offset + 48] = bytes((palette_index & 0xFF,)) * 8

    next_name = name_start
    for team_index in range(40):
        team = TEAM_START + team_index * writer.TEAM_STRIDE
        config = CONFIG_START + team_index * writer.CONFIG_STRIDE
        config_field = team + writer.TEAM_CONFIG_POINTER
        struct.pack_into(">I", data, config_field, _relative_pointer(config_field, config))
        struct.pack_into(">I", data, team + writer.TEAM_CATEGORY, 2 if team_index >= 32 else 0)
        data[team + writer.TEAM_ROSTER_COUNT] = 42 if team_index == 32 else 0

        name = "Synthetic A's" if team_index == 32 else f"TEAM{team_index + 1}"
        encoded_name = name.encode("utf-16-be") + b"\0\0"
        name_field = team + writer.TEAM_NAME_POINTER
        struct.pack_into(">I", data, name_field, _relative_pointer(name_field, next_name))
        data[next_name : next_name + len(encoded_name)] = encoded_name
        next_name += len(encoded_name)

        for selector_slot in range(writer.SELECTORS_PER_BANK * 2):
            selector_index = team_index * writer.SELECTORS_PER_BANK * 2 + selector_slot
            selector = SELECTOR_START + selector_index * writer.SELECTOR_STRIDE
            pointer_field = config + selector_slot * 4
            struct.pack_into(">I", data, pointer_field, _relative_pointer(pointer_field, selector))
            data[selector : selector + 8] = bytes(
                ((team_index + selector_slot) % 24, 3, 2, 0, 9, 0, 0, 0)
            )
        for bank_index, pointer_offset in enumerate(
            (writer.CONFIG_HOME_PALETTE_POINTER, writer.CONFIG_AWAY_PALETTE_POINTER)
        ):
            palette_index = team_index * 2 + bank_index
            palette = PALETTE_START + palette_index * writer.PALETTE_STRIDE
            pointer_field = config + pointer_offset
            struct.pack_into(">I", data, pointer_field, _relative_pointer(pointer_field, palette))

        for selector_slot in (
            writer.LOGO_SELECTOR_SLOT,
            writer.SELECTORS_PER_BANK + writer.LOGO_SELECTOR_SLOT,
        ):
            selector_index = team_index * writer.SELECTORS_PER_BANK * 2 + selector_slot
            selector = SELECTOR_START + selector_index * writer.SELECTOR_STRIDE
            data[selector : selector + 8] = bytes(
                ((team_index + selector_slot) % 118, 0, 0, 3, 2, 1, 0, 0)
            )
    return bytes(data)


def synthetic_stfs(payload: bytes, magic: bytes = b"CON ") -> bytes:
    """Wrap one raw roster in a hash-valid, deliberately unsigned STFS fixture."""

    if magic not in writer.STFS_MAGICS:
        raise ValueError("unsupported synthetic STFS magic")
    first_table = 0xA000
    block_count = (len(payload) + stfs_reader.BLOCK_SIZE - 1) // stfs_reader.BLOCK_SIZE
    allocated = block_count + 1  # block 0 is the one-block directory table
    if allocated > stfs_reader.MAX_ALLOCATED_BLOCKS:
        raise ValueError("synthetic fixture exceeds the two-level test layout")

    def first_level_backing(block: int) -> int:
        if block < stfs_reader.HASHES_PER_TABLE:
            return 0
        value = (block // stfs_reader.HASHES_PER_TABLE) * 0xAB
        value += 1
        return value

    def data_backing(block: int) -> int:
        value = ((block + stfs_reader.HASHES_PER_TABLE) // stfs_reader.HASHES_PER_TABLE) + block
        if block < stfs_reader.HASHES_PER_TABLE:
            return value
        return value + (value + stfs_reader.HASHES_PER_TABLE**2) // (
            stfs_reader.HASHES_PER_TABLE**2
        )

    data_addresses = [
        first_table + data_backing(block) * stfs_reader.BLOCK_SIZE
        for block in range(allocated)
    ]
    level_zero_addresses = [
        first_table
        + first_level_backing(index * stfs_reader.HASHES_PER_TABLE)
        * stfs_reader.BLOCK_SIZE
        for index in range(
            (allocated + stfs_reader.HASHES_PER_TABLE - 1)
            // stfs_reader.HASHES_PER_TABLE
        )
    ]
    top_level = 0 if allocated <= stfs_reader.HASHES_PER_TABLE else 1
    top_address = first_table + (0 if top_level == 0 else 0xAB) * stfs_reader.BLOCK_SIZE
    size = max(data_addresses + level_zero_addresses + [top_address]) + stfs_reader.BLOCK_SIZE
    data = bytearray(size)

    data[:4] = magic
    struct.pack_into(">I", data, 0x340, first_table)
    data[0x379] = 0x24
    data[0x37B] = 1  # female / single active hash-table copy
    struct.pack_into("<H", data, 0x37C, 1)
    data[0x37E:0x381] = (0).to_bytes(3, "little")
    struct.pack_into(">I", data, 0x395, allocated)
    struct.pack_into(">I", data, 0x399, 0)
    struct.pack_into(">I", data, 0x3A9, 0)

    directory = bytearray(stfs_reader.BLOCK_SIZE)
    name = b"Roster.ROS"
    directory[: len(name)] = name
    directory[0x28] = len(name) | 0x40  # file + consecutive logical blocks
    directory[0x29:0x2C] = block_count.to_bytes(3, "little")
    directory[0x2C:0x2F] = block_count.to_bytes(3, "little")
    directory[0x2F:0x32] = (1).to_bytes(3, "little")
    directory[0x32:0x34] = b"\xFF\xFF"
    struct.pack_into(">I", directory, 0x34, len(payload))
    data[data_addresses[0] : data_addresses[0] + stfs_reader.BLOCK_SIZE] = directory
    for index in range(block_count):
        chunk = payload[
            index * stfs_reader.BLOCK_SIZE : (index + 1) * stfs_reader.BLOCK_SIZE
        ]
        padded = chunk.ljust(stfs_reader.BLOCK_SIZE, b"\0")
        address = data_addresses[index + 1]
        data[address : address + stfs_reader.BLOCK_SIZE] = padded

    level_zero_tables: list[bytes] = []
    table_count = len(level_zero_addresses)
    for table_index in range(table_count):
        table = bytearray(stfs_reader.BLOCK_SIZE)
        first_block = table_index * stfs_reader.HASHES_PER_TABLE
        last_block = min(first_block + stfs_reader.HASHES_PER_TABLE, allocated)
        for block in range(first_block, last_block):
            entry = (block % stfs_reader.HASHES_PER_TABLE) * 0x18
            address = data_addresses[block]
            table[entry : entry + 0x14] = hashlib.sha1(
                data[address : address + stfs_reader.BLOCK_SIZE]
            ).digest()
            table[entry + 0x14] = 0x80
            table[entry + 0x15 : entry + 0x18] = b"\xFF\xFF\xFF"
        frozen = bytes(table)
        level_zero_tables.append(frozen)
        if top_level == 1:
            address = level_zero_addresses[table_index]
            data[address : address + stfs_reader.BLOCK_SIZE] = frozen

    if top_level == 0:
        top_table = level_zero_tables[0]
    else:
        top = bytearray(stfs_reader.BLOCK_SIZE)
        for index, table in enumerate(level_zero_tables):
            entry = index * 0x18
            top[entry : entry + 0x14] = hashlib.sha1(table).digest()
            top[entry + 0x14] = 0x80
            top[entry + 0x15 : entry + 0x18] = b"\xFF\xFF\xFF"
        top_table = bytes(top)
    data[top_address : top_address + stfs_reader.BLOCK_SIZE] = top_table
    data[0x381:0x395] = hashlib.sha1(top_table).digest()
    data[0x32C:0x340] = hashlib.sha1(data[0x344:first_table]).digest()
    return bytes(data)


class RawSaveAppearanceTests(unittest.TestCase):
    def test_parse_maps_user_ids_to_slots_and_occupied_state(self) -> None:
        parsed = writer.parse_save(synthetic_save())
        self.assertFalse(parsed.signed_container)
        self.assertEqual([row.target.slot for row in parsed.slots], list(range(32, 40)))
        self.assertEqual([row.target.user_team_id for row in parsed.slots], list(range(24, 32)))
        self.assertTrue(parsed.slots[0].target.occupied)
        self.assertFalse(parsed.slots[1].target.occupied)
        self.assertEqual(parsed.slots[0].target.display_name, "Synthetic A's")

    def test_eagles_patch_is_bounded_reopens_and_verifies(self) -> None:
        source = synthetic_save()
        parsed = writer.parse_save(source)
        before = parsed.slots[0].appearance
        replacement = appearance_writer.eagles_2017_preset(before)
        output, manifest = writer.make_patch(source, (replacement,))
        verification = writer.verify_patch(source, output, manifest)

        self.assertEqual(hashlib.sha256(source).hexdigest(), manifest["source_sha256"])
        self.assertEqual(manifest["authorized_byte_count"], 112)
        self.assertLessEqual(manifest["changed_byte_count"], 112)
        self.assertTrue(set(manifest["changed_byte_positions"]).issubset(
            {
                position
                for start, length in writer._target_spans(parsed.slots[0].target)
                for position in range(start, start + length)
            }
        ))
        self.assertTrue(verification["verified"])
        self.assertFalse(manifest["claims"]["runtime_in_game_proved"])
        self.assertFalse(verification["claims"]["runtime_in_game_proved"])
        self.assertEqual(writer.parse_save(output).slots[0].appearance, replacement)
        self.assertEqual(writer.parse_save(output).slots[1].appearance, parsed.slots[1].appearance)

    def test_shared_palette_is_rejected(self) -> None:
        data = bytearray(synthetic_save())
        slot_32_config = CONFIG_START + 32 * writer.CONFIG_STRIDE
        slot_33_config = CONFIG_START + 33 * writer.CONFIG_STRIDE
        palette = PALETTE_START + 64 * writer.PALETTE_STRIDE
        field = slot_33_config + writer.CONFIG_HOME_PALETTE_POINTER
        struct.pack_into(">I", data, field, _relative_pointer(field, palette))
        with self.assertRaisesRegex(writer.SaveAppearanceError, "palette is shared"):
            writer.parse_save(bytes(data))
        self.assertNotEqual(slot_32_config, slot_33_config)

    def test_root_count_and_user_category_tampering_are_rejected(self) -> None:
        wrong_count = bytearray(synthetic_save())
        count_field = writer.ROOT_OFFSET + writer.SELECTOR_TABLE_INDEX * 8
        struct.pack_into(">I", wrong_count, count_field, 3723)
        with self.assertRaisesRegex(writer.SaveAppearanceError, "root table 17 count changed"):
            writer.parse_save(bytes(wrong_count))

        wrong_category = bytearray(synthetic_save())
        struct.pack_into(
            ">I",
            wrong_category,
            TEAM_START + 32 * writer.TEAM_STRIDE + writer.TEAM_CATEGORY,
            0,
        )
        with self.assertRaisesRegex(writer.SaveAppearanceError, "not a user-team record"):
            writer.parse_save(bytes(wrong_category))

    def test_stfs_container_magics_extract_verified_roster_but_not_signature(self) -> None:
        raw = synthetic_save()
        for magic in writer.STFS_MAGICS:
            with self.subTest(magic=magic):
                signed = synthetic_stfs(raw, magic)
                parsed = writer.parse_save(signed)
                self.assertTrue(parsed.signed_container)
                self.assertEqual(parsed.container_kind, magic.decode("ascii").strip())
                self.assertEqual(parsed.payload_path, "Roster.ROS")
                self.assertEqual(len(parsed.slots), 8)
                self.assertTrue(parsed.container_hash_tree_verified)
                self.assertFalse(parsed.container_rsa_signature_verified)
                with self.assertRaisesRegex(writer.SaveAppearanceError, "inspect-only"):
                    writer.make_patch(signed, ())

    def test_stfs_extract_and_patched_raw_handoff_reopen_independently(self) -> None:
        raw = synthetic_save()
        container = synthetic_stfs(raw)
        extracted, extract_manifest = writer.make_stfs_extract(container)
        extract_verification = writer.verify_stfs_extract(
            container, extracted, extract_manifest
        )
        self.assertEqual(extracted, raw)
        self.assertTrue(extract_verification["verified"])
        self.assertFalse(
            extract_manifest["claims"]["stfs_rsa_signature_verified"]
        )
        self.assertTrue(extract_manifest["claims"]["external_reinjection_required"])

        appearance = writer.parse_save(container).slots[0].appearance
        replacement = appearance_writer.eagles_2017_preset(appearance)
        handoff, handoff_manifest = writer.make_stfs_handoff(
            container, (replacement,)
        )
        handoff_verification = writer.verify_stfs_handoff(
            container, handoff, handoff_manifest
        )
        self.assertTrue(handoff_verification["verified"])
        self.assertEqual(
            writer.parse_save(handoff).slots[0].appearance,
            replacement,
        )
        self.assertEqual(handoff_manifest["output_layout"], writer.RAW_LAYOUT)
        self.assertFalse(
            handoff_manifest["claims"]["output_is_signed_stfs_container"]
        )
        self.assertFalse(
            handoff_manifest["claims"]["container_resigned"]
        )

    def test_stfs_hash_or_payload_tampering_is_rejected(self) -> None:
        container = bytearray(synthetic_stfs(synthetic_save()))
        parsed = stfs_reader._StfsReader(bytes(container))
        roster = next(
            entry for entry in parsed.directory_entries()
            if entry.path == "Roster.ROS"
        )
        container[parsed.block_address(roster.starting_block)] ^= 1
        with self.assertRaisesRegex(writer.SaveAppearanceError, "SHA-1 does not match"):
            writer.parse_save(bytes(container))

        forged_hash = bytearray(synthetic_stfs(synthetic_save()))
        forged_hash[0x381] ^= 1
        forged_hash[0x32C:0x340] = hashlib.sha1(
            forged_hash[0x344:0xA000]
        ).digest()
        with self.assertRaisesRegex(writer.SaveAppearanceError, "top STFS hash table"):
            writer.parse_save(bytes(forged_hash))

    def test_tampered_output_or_manifest_fails_verification(self) -> None:
        source = synthetic_save()
        current = writer.parse_save(source).slots[0].appearance
        output, manifest = writer.make_patch(
            source, (appearance_writer.eagles_2017_preset(current),)
        )
        tampered = bytearray(output)
        tampered[TEAM_START] ^= 1
        with self.assertRaisesRegex(writer.SaveAppearanceError, "output SHA-256 differs"):
            writer.verify_patch(source, bytes(tampered), manifest)
        forged = json.loads(json.dumps(manifest))
        forged["edits"][0]["display_name"] = "forged"
        with self.assertRaisesRegex(writer.SaveAppearanceError, "display_name differs"):
            writer.verify_patch(source, output, forged)

    def test_service_writes_new_verified_files_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "Roster.ROS"
            source_path.write_bytes(synthetic_save())
            source_before = source_path.read_bytes()
            document = service.inspect_save(source_path)
            replacement = appearance_writer.eagles_2017_preset(document.slots[0].appearance)
            output_path = root / "Roster-Eagles.ROS"
            receipt = service.write_new_save(document, replacement, output_path)

            self.assertTrue(receipt.verification_passed)
            self.assertFalse(receipt.runtime_in_game_proved)
            self.assertEqual(receipt.authorized_byte_count, 112)
            self.assertEqual(source_path.read_bytes(), source_before)
            self.assertTrue(output_path.is_file())
            self.assertTrue(receipt.manifest.is_file())
            written_manifest = json.loads(receipt.manifest.read_text(encoding="utf-8"))
            self.assertTrue(written_manifest["verification"]["verified"])
            self.assertFalse(
                written_manifest["verification"]["claims"]["runtime_in_game_proved"]
            )
            with self.assertRaisesRegex(service.SaveAppearanceServiceError, "refusing to overwrite"):
                service.write_new_save(document, replacement, output_path)

            occupied_manifest = root / "occupied.json"
            occupied_manifest.write_text("keep", encoding="utf-8")
            rejected_output = root / "manifest-conflict.ROS"
            with self.assertRaisesRegex(service.SaveAppearanceServiceError, "refusing to overwrite"):
                service.write_new_save(
                    document,
                    replacement,
                    rejected_output,
                    manifest=occupied_manifest,
                )
            self.assertFalse(rejected_output.exists())
            self.assertEqual(occupied_manifest.read_text(encoding="utf-8"), "keep")

    def test_service_sha_binds_inspection_to_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "Roster.ROS"
            source_path.write_bytes(synthetic_save())
            document = service.inspect_save(source_path)
            source_path.write_bytes(source_path.read_bytes() + b"changed")
            replacement = appearance_writer.eagles_2017_preset(document.slots[0].appearance)
            with self.assertRaisesRegex(service.SaveAppearanceServiceError, "changed after inspection"):
                service.write_new_save(document, replacement, root / "stale-output.ROS")
            self.assertFalse((root / "stale-output.ROS").exists())
            self.assertFalse((root / "stale-output.ROS.appearance.json").exists())

    def test_service_extracts_and_writes_new_stfs_raw_handoffs_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "signed-save.bin"
            source_path.write_bytes(synthetic_stfs(synthetic_save()))
            source_before = source_path.read_bytes()
            document = service.inspect_save(source_path)

            self.assertTrue(document.signed_container)
            self.assertEqual(document.container_kind, "CON")
            self.assertEqual(document.payload_path, "Roster.ROS")
            self.assertTrue(document.container_hash_tree_verified)
            self.assertFalse(document.container_rsa_signature_verified)
            self.assertEqual(len(document.slots), 8)

            extracted_path = root / "extracted.Roster.ROS"
            extracted_receipt = service.extract_raw_save(document, extracted_path)
            self.assertTrue(extracted_receipt.verification_passed)
            self.assertEqual(extracted_path.read_bytes(), synthetic_save())
            self.assertTrue(extracted_receipt.manifest.is_file())

            replacement = appearance_writer.eagles_2017_preset(
                document.slots[0].appearance
            )
            handoff_path = root / "patched.Roster.ROS"
            handoff_receipt = service.write_new_save(
                document, replacement, handoff_path
            )
            self.assertTrue(handoff_receipt.verification_passed)
            self.assertTrue(handoff_receipt.source_was_signed_container)
            self.assertTrue(handoff_receipt.external_reinjection_required)
            self.assertNotIn(handoff_path.read_bytes()[:4], writer.STFS_MAGICS)
            self.assertEqual(source_path.read_bytes(), source_before)
            handoff_manifest = json.loads(
                handoff_receipt.manifest.read_text(encoding="utf-8")
            )
            self.assertEqual(handoff_manifest["schema"], writer.STFS_HANDOFF_SCHEMA)
            self.assertTrue(handoff_manifest["verification"]["verified"])
            self.assertFalse(
                handoff_manifest["claims"]["output_is_signed_stfs_container"]
            )

            with self.assertRaisesRegex(
                service.SaveAppearanceServiceError, "refusing to overwrite"
            ):
                service.extract_raw_save(document, extracted_path)

    @unittest.skipUnless(REAL_RAW_SAVE.is_file(), "private real Roster.ROS is unavailable")
    def test_private_real_raw_save_parses_and_patches_in_memory(self) -> None:
        source = writer.read_source(REAL_RAW_SAVE)
        parsed = writer.parse_save(source)
        self.assertEqual(parsed.slots[0].target.slot, 32)
        self.assertEqual(parsed.slots[0].target.user_team_id, 24)
        self.assertTrue(parsed.slots[0].target.occupied)
        replacement = appearance_writer.eagles_2017_preset(parsed.slots[0].appearance)
        output, manifest = writer.make_patch(source, (replacement,))
        self.assertTrue(writer.verify_patch(source, output, manifest)["verified"])


if __name__ == "__main__":
    unittest.main()
