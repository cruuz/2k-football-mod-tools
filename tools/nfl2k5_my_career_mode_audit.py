"""Read-only, bounded USA-XBE evidence for ASTRA_MYCAREER_MODE_DESIGN.md.

No runtime owner or save-space reservation is created by this audit. In
particular, a copied opaque tail is not automatically free save storage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage
from mod_editor.core import nfl2k5_my_career as career
from mod_editor.core import nfl2k5_my_career_code as assembly
from mod_editor.core import nfl2k5_franchise_save as franchise

MAX_XBE_BYTES = 16 * 1024**2
SAVE_TAIL_START = franchise.SEASON_BLOCK + franchise.S_TAIL
SAVE_TAIL_SIZE = franchise.S_TAIL_SIZE
PINS = (
    (0x3461F0, 134, "8c016c8fb8b61b493ae6bfa40e5454e6499e9d33186600618f428217dbaac2c7"),
    (0xBFF50, 55, "59da9305f464222f507853c301f9e264621dffd953eadd4ced2d050560c26452"),
    (0xC0A80, 185, "65e0538d1596a8077ad72612b6cc459c16ab07b0cdcc9b9f86dca2627ba81179"),
    (0x148CC0, 37, "e8c92274fb785cc5ebdd9d9772077d11f76e4c6d4ccd771a3fdccc47b82679fe"),
    (0xC5310, 1251, "cabefe10c96c5b7f9caa46115a8870067790b4dd05590331a60e8e9130375507"),
    (0xC5800, 1020, "e2e538336b1a9a4545a39ad2f9adac65c09771bd89f0667926dec2fb22d4f7db"),
    (0x1346A0, 753, "ab1a5cf74e0855f28f9388bf34d8b8459dae29bf8c2d8f9745560a051b2268e2"),
    (0x1349A0, 697, "ac4a3cf3401cd148eaffc95c0785dc447cba0c78874869069ed493a9641bb78b"),
    (0x63810, 37, "20565dfdbf745b27e9b17cfc41d3ac39c7b743a047a6817dfb077cf4c7cf5336"),
)
WORDS = {
    "game_modes_fpp_target": (0x50149C, 0x526948),
    "created_player_list_target": (0x525768, 0x56E9C4),
    "creator_list_accept": (0x56E7DC, 0x3461F0),
    "creator_details_handler": (0x56F058, 0xF40F0),
    "creator_appearance_target": (0x56EDD0, 0x56ED80),
    "creator_equipment_target": (0x56EBF0, 0x56EBA0),
    "franchise_advance": (0x5009DC, 0x148CC0),
    "desk_handler": (0x522198, 0xF3E90),
    "desk_rows": (0x5221A0, 0x521F20),
    "desk_schedule_action": (0x521F48, 0x142880),
    "schedule_enter": (0x5227B4, 0x327A00),
    "desk_quit_action": (0x522150, 0xC8190),
}


def audit(payload: bytes) -> dict:
    if not isinstance(payload, bytes) or len(payload) > MAX_XBE_BYTES:
        raise ValueError("USA XBE evidence must be bounded bytes, at most 16 MiB")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != RETAIL_SHA256:
        raise ValueError("USA retail XBE evidence pin differs; no inference made")
    image = XbeImage(payload)
    spans = []
    for va, size, expected in PINS:
        actual = hashlib.sha256(image.read(va, size)).hexdigest()
        if actual != expected:
            raise ValueError(f"native route pin differs at {va:#x}")
        spans.append({"va": hex(va), "size": size, "sha256": actual, "evidence": "PROVED bytes"})
    words = {}
    for name, (va, expected) in WORDS.items():
        actual = struct.unpack("<I", image.read(va, 4))[0]
        if actual != expected:
            raise ValueError(f"native descriptor differs at {va:#x}")
        words[name] = {"va": hex(va), "value": hex(actual), "evidence": "PROVED bytes"}
    return {
        "schema": "nfl2k5_my_career_mode_audit/v1",
        "experimental": True, "runtime_witnessed": False,
        "retail_sha256": digest, "native_spans": spans, "descriptor_words": words,
        "existing_owner": {
            "requests": career.REQUESTS, "instructions_and_literals": len(assembly.CODE),
            "with_setup": len(assembly.CODE) + career.STATE_SIZE,
            "checkpoint_location": "64 separate U:\\MyCareerXX.dat journal slots",
            "embedded_franchise_checkpoint": False,
        },
        "save_candidate": {
            "file_start": "0x9967c", "file_end_exclusive": "0x996fc", "size": 128,
            "native_ram_start": "0xe5fb80", "normal_roundtrip": "PROVED by native route suite",
            "empty_season": "PROVED serializer clears the tail when substate is 3",
            "ownership": "HYPOTHESIS; copying and zero samples do not establish vacancy",
            "production_allocation_authorized_by_evidence": False,
        },
        "scope": "Prerequisite evidence, not an installed in-game MyCareer mode",
    }


def audit_save(payload: bytes) -> dict:
    """Inspect an opaque region, never allocate it or publish a modified save.

    A bare SAVEGAME.DAT does not include its EXTRA signature, so this receipt
    expressly makes no authenticity claim. Even an all-zero sample is NOT a
    vacancy proof. One occupied sample defeats unconditional tail reuse.
    """
    if not isinstance(payload, bytes) or len(payload) != franchise.FRANCHISE_SAVE_SIZE:
        raise ValueError("expected a complete 720,044-byte franchise save")
    if payload[0x2E0:0x2E4] != b"ROST" or payload[franchise.SEASON_BLOCK] != 2:
        raise ValueError("expected native ROST and Franchise markers")
    tail = payload[SAVE_TAIL_START:SAVE_TAIL_START + SAVE_TAIL_SIZE]
    head = payload[franchise.SEASON_BLOCK:franchise.SEASON_BLOCK + 11]
    return {
        "schema": "nfl2k5_my_career_save_candidate/v1",
        "save_sha256": hashlib.sha256(payload).hexdigest(),
        "size": len(payload), "signature_checked": False, "modified": False,
        "stage": head[1], "substate": head[2], "week": head[5], "year_field": head[6],
        "tail_start": hex(SAVE_TAIL_START), "tail_size": SAVE_TAIL_SIZE,
        "tail_sha256": hashlib.sha256(tail).hexdigest(),
        "nonzero_bytes": sum(value != 0 for value in tail),
        "occupied_words": [{"relative_offset": hex(offset), "value": hex(value)}
                           for offset in range(0, len(tail), 4)
                           if (value := struct.unpack_from("<I", tail, offset)[0])],
        "allocation_allowed": False,
        "verdict": "OCCUPIED: preserve native data" if any(tail)
                   else "ZERO SAMPLE: ownership remains unproved",
        "runtime_witnessed": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xbe", type=Path)
    parser.add_argument("--save", action="append", type=Path, default=[],
                        help="read-only candidate occupancy audit of a bare SAVEGAME.DAT; repeatable")
    args = parser.parse_args(argv)
    # The bounded read also refuses a file that grows after stat().
    with args.xbe.open("rb") as source:
        payload = source.read(MAX_XBE_BYTES + 1)
    receipt = audit(payload)
    if args.save:
        receipt["save_samples"] = []
        for path in args.save:
            with path.open("rb") as source:
                save = source.read(franchise.FRANCHISE_SAVE_SIZE + 1)
            receipt["save_samples"].append({"source": str(path), **audit_save(save)})
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
