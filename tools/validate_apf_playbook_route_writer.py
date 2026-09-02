#!/usr/bin/env python3
"""Retail-free structural validation for the bounded APF route-clone writer."""

from __future__ import annotations

from pathlib import Path
import struct
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.apf_studio.backend import ensure_tools_importable  # noqa: E402
from mod_editor.core.apf2k8_playbook_route_writer import (  # noqa: E402
    RouteCloneRequest,
    compile_route_clones,
    verify_route_clones,
)


ensure_tools_importable()
import playbook_inventory  # type: ignore  # noqa: E402


def relative(target: int, field: int) -> bytes:
    return struct.pack(">i", target - field + 1)


def fixture() -> bytes:
    data = bytearray(playbook_inventory.APF_BODY_SIZE)
    data[0x0C:0x10] = b"YALP"
    struct.pack_into("<II", data, 0x10, 0x20, 0)
    data[0x20:0x28] = "mpb".encode("utf-16be") + b"\0\0"
    struct.pack_into(">IIII", data, 0x34, 1, 2, 1, 2)
    cursor = playbook_inventory.APF_STRING_BASE
    names: list[int] = []
    for value in ("MASTER", "Form", "Play A", "Play B", "Pass"):
        names.append(cursor)
        encoded = value.encode("utf-16be") + b"\0\0"
        data[cursor : cursor + len(encoded)] = encoded
        cursor += len(encoded)
    data[0x30:0x34] = relative(names[0], 0x30)
    category = playbook_inventory.APF_CATEGORY_BASE
    formation = playbook_inventory.APF_FORMATION_BASE
    data[category : category + 4] = relative(names[4], category)
    data[formation : formation + 4] = relative(names[1], formation)
    nodes = (
        playbook_inventory.APF_ROUTE_BASE,
        playbook_inventory.APF_ROUTE_BASE + playbook_inventory.ROUTE_NODE_SIZE,
    )
    data[nodes[0] : nodes[0] + 8] = b"NODEZERO"
    data[nodes[1] : nodes[1] + 8] = b"NODE_ONE"
    for play_index in range(2):
        play = (
            playbook_inventory.APF_PLAY_BASE
            + play_index * playbook_inventory.APF_PLAY_SIZE
        )
        data[play : play + 4] = relative(names[2 + play_index], play)
        for slot in range(playbook_inventory.SLOT_COUNT):
            descriptor = play + 0x0C + slot * 8
            pointer = descriptor + 4
            struct.pack_into(">I", data, descriptor, 0x10000 + play_index * 16 + slot)
            data[pointer : pointer + 4] = relative(
                nodes[(play_index + slot) % 2], pointer
            )
    return bytes(data)


def main() -> int:
    source = fixture()
    request = RouteCloneRequest(0, 0, 1, 0)
    compiled = compile_route_clones(source, (request,))
    verified = verify_route_clones(source, compiled.replacement, (request,))
    if (
        verified["replacement_sha256"] != compiled.replacement_sha256
        or compiled.parsed_replacement["plays"][0]["slots"][0][
            "route_node_index"
        ]
        != 1
        or not compiled.report["claims"]["assignment_chain_start_set_preserved"]
    ):
        raise SystemExit("APF route-clone validation failed")
    print("APF_PLAYBOOK_ROUTE_WRITER_VALIDATION_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
