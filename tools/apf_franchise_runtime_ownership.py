#!/usr/bin/env python3
"""Generate deterministic APF franchise/Season runtime-ownership evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


BASE = 0x82000000
TEXT_FIRST = 0x84630000
TEXT_AFTER_LAST = 0x84D0904C
PDATA_FIRST = 0x844DBE00
PDATA_AFTER_LAST = 0x84500000

EXPECTED_XEX_SHA256 = "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
EXPECTED_PE_SHA256 = "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
EXPECTED_INPUT_HASHES = {
    "inner_candidates": "26dd77660c91568773519f616e7120c6b8c23dc3613880e5a5831c18ee34a0d3",
    "menu_state": "ecd93117a3a808a16697c23ae10e3225953bcb4dabda30afabdc5c02911974f1",
    "cross_layout": "de9c693cd6e5805265dcfc12de6b2622aadbcb0cc79bfe495e33377a2d8b8b45",
    "localization_json": "7638b9210c620ac4a82f7fc37139a38800aec836c913db526f94476ef0fdafdc",
    "localization_tsv": "16693a0d7bbe6b16e40b8366c8400dc920332322a379840e6e9959168514e721",
    "toolchain_strings": "d2b408c8150ae0746258d65df4b0d43b54b7384fdbf592f88407eea2fa51a0ba",
}


def hx(value: int) -> str:
    return f"0x{value & 0xFFFFFFFF:08X}"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 << 20):
            hasher.update(block)
    return hasher.hexdigest()


def expect(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label}: expected {expected!r}, got {actual!r}")


class Image:
    def __init__(self, path: Path):
        self.path = path
        self.data = path.read_bytes()

    def offset(self, address: int) -> int:
        result = address - BASE
        if result < 0 or result >= len(self.data):
            raise ValueError(f"address outside APF PE: {hx(address)}")
        return result

    def u32(self, address: int) -> int:
        return struct.unpack_from(">I", self.data, self.offset(address))[0]

    def span(self, first: int, after_last: int) -> bytes:
        return self.data[self.offset(first) : self.offset(after_last - 1) + 1]

    def utf16(self, address: int, limit: int = 512) -> str:
        output: list[str] = []
        cursor = self.offset(address)
        for _ in range(limit):
            code = struct.unpack_from(">H", self.data, cursor)[0]
            cursor += 2
            if code == 0:
                return "".join(output)
            output.append(chr(code))
        raise ValueError(f"unterminated UTF-16BE string at {hx(address)}")

    def occurrences(self, needle: bytes, aligned: bool = False) -> list[int]:
        output: list[int] = []
        cursor = 0
        while True:
            cursor = self.data.find(needle, cursor)
            if cursor < 0:
                return output
            address = BASE + cursor
            if not aligned or address % 4 == 0:
                output.append(address)
            cursor += 1

    def fullwords(self, value: int) -> list[int]:
        return self.occurrences((value & 0xFFFFFFFF).to_bytes(4, "big"), True)

    def branch(self, address: int) -> tuple[int, bool]:
        word = self.u32(address)
        if word >> 26 != 18:
            raise ValueError(f"not b/bl at {hx(address)}: {hx(word)}")
        displacement = word & 0x03FFFFFC
        if displacement & 0x02000000:
            displacement -= 0x04000000
        target = displacement if word & 2 else address + displacement
        return target & 0xFFFFFFFF, bool(word & 1)

    def direct_branch_sites(self, target: int) -> list[dict[str, str]]:
        output: list[dict[str, str]] = []
        for address in range(TEXT_FIRST, TEXT_AFTER_LAST, 4):
            word = self.u32(address)
            if word >> 26 != 18:
                continue
            displacement = word & 0x03FFFFFC
            if displacement & 0x02000000:
                displacement -= 0x04000000
            actual = (displacement if word & 2 else address + displacement) & 0xFFFFFFFF
            if actual == target:
                output.append({"site": hx(address), "kind": "call" if word & 1 else "jump"})
        return output

    def constructions(self, target: int, window: int = 12) -> list[dict[str, str]]:
        wanted = target & 0xFFFFFFFF
        output: list[dict[str, str]] = []
        for address in range(TEXT_FIRST, TEXT_AFTER_LAST - window * 4, 4):
            first = self.u32(address)
            if first >> 26 != 15 or ((first >> 16) & 31) != 0:
                continue
            source_register = (first >> 21) & 31
            high = ((struct.unpack(">h", (first & 0xFFFF).to_bytes(2, "big"))[0] << 16) & 0xFFFFFFFF)
            for distance in range(1, window + 1):
                site = address + distance * 4
                second = self.u32(site)
                opcode = second >> 26
                computed: int | None = None
                kind = ""
                if opcode == 14 and ((second >> 16) & 31) == source_register:
                    low = struct.unpack(">h", (second & 0xFFFF).to_bytes(2, "big"))[0]
                    computed = (high + low) & 0xFFFFFFFF
                    kind = "lis/addi"
                elif opcode == 24 and ((second >> 21) & 31) == source_register:
                    computed = (high | (second & 0xFFFF)) & 0xFFFFFFFF
                    kind = "lis/ori"
                if computed == wanted:
                    output.append(
                        {
                            "lis": hx(address),
                            "low": hx(site),
                            "kind": kind,
                            "destination_register": f"r{(second >> 21) & 31}",
                        }
                    )
        return output


def pdata(image: Image) -> dict[int, dict[str, Any]]:
    output: dict[int, dict[str, Any]] = {}
    for slot in range(PDATA_FIRST, PDATA_AFTER_LAST, 8):
        address = image.u32(slot)
        metadata = image.u32(slot + 4)
        end = address + ((metadata >> 8) & 0xFFFF) * 4
        if not (TEXT_FIRST <= address < end <= TEXT_AFTER_LAST):
            continue
        output[address] = {
            "address": hx(address),
            "end_exclusive": hx(end),
            "metadata": hx(metadata),
            "pdata_slot": hx(slot),
            "raw_sha256": digest(image.span(address, end)),
        }
    return output


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def incoming(image: Image, target: int, pdata_slot: int | None = None) -> dict[str, Any]:
    fullwords = image.fullwords(target)
    non_pdata = [address for address in fullwords if address != pdata_slot]
    return {
        "direct_branches": image.direct_branch_sites(target),
        "classic_materializations": image.constructions(target),
        "fullword_sites": [hx(value) for value in fullwords],
        "non_pdata_fullword_sites": [hx(value) for value in non_pdata],
    }


ARCHIVE_REQUESTS = [
    {
        "archive": "franchise.iff",
        "function": 0x84A1FD00,
        "body": 0x84A1FD08,
        "call_site": 0x84A1FD6C,
        "request_object": 0x84E44510,
        "request_hash": 0x68F0ED58,
        "string": 0x845FD7E8,
    },
    {
        "archive": "season.iff",
        "function": 0x84A54A00,
        "body": 0x84A54A00,
        "call_site": 0x84A54A7C,
        "request_object": 0x84E56508,
        "request_hash": 0x001C9C2F,
        "string": 0x8460AF2C,
    },
    {
        "archive": "trophyroom.iff",
        "function": 0x84A6A980,
        "body": 0x84A6A980,
        "call_site": 0x84A6A9D8,
        "request_object": 0x84E605A8,
        "request_hash": 0x1CB126F7,
        "string": 0x84613288,
    },
    {
        "archive": "franchise_show.iff",
        "function": 0x84AEF1C0,
        "body": 0x84AEF1C8,
        "call_site": 0x84AEF220,
        "request_object": 0x852AA578,
        "request_hash": 0xDACF91F0,
        "string": 0x84626428,
    },
    {
        "archive": "franchise_show_intro.iff",
        "function": 0x84AEF3F8,
        "body": 0x84AEF3F8,
        "call_site": 0x84AEF450,
        "request_object": 0x852AA818,
        "request_hash": 0x30ADB203,
        "string": 0x8462651C,
    },
    {
        "archive": "franchise_show_outro.iff",
        "function": 0x84AEF4B8,
        "body": 0x84AEF4B8,
        "call_site": 0x84AEF510,
        "request_object": 0x852AA878,
        "request_hash": 0x38F5973D,
        "string": 0x84626550,
    },
]


OLD_STATE_NAMES = [
    "FranchiseMenu_CoachGameplan",
    "FranchiseMenu_CoachsDesk",
    "FranchiseMenu_SimpleCoachsDesk",
    "FranchiseMenu_PlaySetupPortal",
    "FranchiseMenu_PlayScript",
    "FranchiseMenu_SituationalPlays",
    "FranchiseMenu_LivePractice",
    "FranchiseMenu_Weekly",
    "FranchiseMenu_TeamSelect",
]


SELECTED_LOCALIZATION = [
    "NFL",
    "Free Agents",
    "PRESENTED BY ESPN",
    "Franchise/",
    "Contract Details",
    "CAREER",
    "Playoff Picture",
    "Draft",
    "Team Salary",
    "Next week on SportsCenter",
    "OFF-SEASON",
    "TRADE REQUESTS",
]


PORTME = [
    {
        "address": "0x849DF2F0/0x820E0BC8",
        "text": "recover a real retail or computed owner for the standalone franchise initializer and Coach's Desk descriptor; static branch, fullword, and classic lis/addi scans currently find none",
    },
    {
        "address": "0x84F3FB28/0x849DF2F8",
        "text": "name the mode selector and prove all franchise-core global/save-data prerequisites before attempting to invoke the retained entry",
    },
    {
        "address": "0x84AECE18/0x84B00948/0x820FAB68",
        "text": "recover the live caller of the unowned Wrapup route root, or prove the franchise-show callback graph is disabled in retail",
    },
    {
        "address": "0x820FAAE0/0x820FAAF8",
        "text": "execute and instrument Wrapup events 1 and 3 to prove which franchise/franchise_show requests occur in an unmodified retail session",
    },
    {
        "address": "0x84691C68/0x84761A08",
        "text": "recover TXT text_id source keys and call sites before claiming that retained NFL/ESPN/franchise localization rows are displayed",
    },
]


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    expect(file_digest(args.apf_xex), EXPECTED_XEX_SHA256, "APF XEX SHA-256")
    image = Image(args.apf_pe)
    expect(digest(image.data), EXPECTED_PE_SHA256, "APF PE SHA-256")

    inputs = {
        "inner_candidates": args.inner_candidates,
        "menu_state": args.menu_state,
        "cross_layout": args.cross_layout,
        "localization_json": args.localization_json,
        "localization_tsv": args.localization_tsv,
        "toolchain_strings": args.toolchain_strings,
    }
    for label, path in inputs.items():
        expect(file_digest(path), EXPECTED_INPUT_HASHES[label], f"{label} SHA-256")

    pdata_rows = pdata(image)
    expected_boundaries = {
        0x849DF2F0: (0x849DF3E0, 0x40003C03),
        0x84A1FD00: (0x84A1FDCC, 0x40003303),
        0x84A54A00: (0x84A54AA0, 0x40002805),
        0x84A54BB0: (0x84A54C7C, 0x40003304),
        0x84A55B50: (0x84A55EAC, 0x4000D704),
        0x84A6A980: (0x84A6AA08, 0x40002204),
        0x84AEE800: (0x84AEE9E8, 0x40007A06),
        0x84AEE9E8: (0x84AEEA90, 0x40002A04),
        0x84AEEA90: (0x84AEEC50, 0x40007005),
        0x84AEF100: (0x84AEF164, 0x40001904),
        0x84AEF1C0: (0x84AEF340, 0x40006003),
        0x84AEFB40: (0x84AEFBE0, 0x40002804),
        0x84B00948: (0x84B01574, 0x40030B03),
    }
    boundaries: list[dict[str, Any]] = []
    for address, (end, metadata) in expected_boundaries.items():
        row = pdata_rows[address]
        expect(row["end_exclusive"], hx(end), f"PDATA end {hx(address)}")
        expect(row["metadata"], hx(metadata), f"PDATA metadata {hx(address)}")
        boundaries.append(row)

    requests: list[dict[str, Any]] = []
    for item in ARCHIVE_REQUESTS:
        expect(image.utf16(item["string"]), item["archive"], f"archive string {item['archive']}")
        expect(image.branch(item["call_site"]), (0x8468DA70, True), f"archive request call {item['archive']}")
        requests.append(
            {
                "archive": item["archive"],
                "function": hx(item["function"]),
                "decompiler_body": hx(item["body"]),
                "call_site": hx(item["call_site"]),
                "callee": "0x8468DA70",
                "manager": "0x84F43800",
                "request_object": hx(item["request_object"]),
                "request_hash": hx(item["request_hash"]),
                "filename_address": hx(item["string"]),
                "filename": image.utf16(item["string"]),
                "filename_materializations": image.constructions(item["string"]),
            }
        )

    manifest_rows = read_tsv(args.inner_candidates)
    archive_inventory: list[dict[str, Any]] = []
    for name in [item["archive"] for item in ARCHIVE_REQUESTS]:
        rows = [row for row in manifest_rows if row["outer_name_candidate"] == name]
        expect(len({row["outer_table_index"] for row in rows}), 1, f"outer count {name}")
        archive_inventory.append(
            {
                "archive": name,
                "outer_index": int(rows[0]["outer_table_index"]),
                "outer_name_id": rows[0]["outer_name_id"],
                "inner_file_count": len(rows),
                "type_counts": dict(sorted(Counter(row["type_name"] for row in rows).items())),
                "inner_names": [row["inner_name"] for row in rows],
            }
        )
    expected_counts = {
        "franchise.iff": (810, 118),
        "season.iff": (1215, 19),
        "trophyroom.iff": (108, 61),
        "franchise_show.iff": (730, 15),
        "franchise_show_intro.iff": (1221, 4),
        "franchise_show_outro.iff": (941, 1),
    }
    for row in archive_inventory:
        expect(
            (row["outer_index"], row["inner_file_count"]),
            expected_counts[row["archive"]],
            f"archive inventory {row['archive']}",
        )

    old_states: list[dict[str, Any]] = []
    for name in OLD_STATE_NAMES:
        needle = name.encode("utf-16-be") + b"\0\0"
        hits = image.occurrences(needle)
        expect(len(hits), 1, f"old state string count {name}")
        string_address = hits[0]
        pointer_sites = image.fullwords(string_address)
        expect(len(pointer_sites), 1, f"old state pointer count {name}")
        descriptor = pointer_sites[0] - 4
        old_states.append(
            {
                "name": name,
                "name_address": hx(string_address),
                "name_pointer_site": hx(pointer_sites[0]),
                "descriptor_candidate": hx(descriptor),
            }
        )

    menu = json.loads(args.menu_state.read_text())
    main_rows = menu["apf2k8"]["navigation_rows"]
    season_main_row = next(row for row in main_rows if row["label"] == "Season")
    expect(season_main_row["target_descriptor"], "0x820F4308", "retail main Season target")
    expect(season_main_row["type"], 11, "retail main Season route type")
    expect(image.u32(0x84E57408), 0x820F4308, "raw retail main Season target")
    expect(image.utf16(image.u32(0x820F4308)), "Season", "Season descriptor title")
    expect(image.u32(0x820F4324), 0x84E57220, "Season load/new row base")
    expect(image.utf16(image.u32(0x84E57224)), "Load", "Season Load label")
    expect(image.utf16(image.u32(0x84E57284)), "New", "Season New label")
    expect(image.u32(0x84E572E8), 0x820F42C0, "Season New target")

    expect(image.u32(0x84E562D0), 0x820F3FC0, "SeasonNav Gameplan target")
    expect(image.utf16(image.u32(0x820F3FC0)), "GAMEPLAN", "Season Gameplan title")
    expect(image.utf16(image.u32(0x820F3FC4)), "SeasonNavMenu_Gameplan", "Season Gameplan state")
    expect(image.u32(0x820F3FDC), 0x84E55DE8, "Season Gameplan rows")
    expect(image.u32(0x84E55F10), 0x820E0B80, "old CoachGameplan target")
    expect(image.utf16(image.u32(0x820E0B84)), "FranchiseMenu_CoachGameplan", "old Gameplan state")

    franchise_entry = incoming(image, 0x849DF2F0, pdata_rows[0x849DF2F0]["pdata_slot"] and int(pdata_rows[0x849DF2F0]["pdata_slot"], 16))
    expect(franchise_entry["direct_branches"], [], "standalone franchise entry branches")
    expect(franchise_entry["classic_materializations"], [], "standalone franchise entry materializations")
    expect(franchise_entry["non_pdata_fullword_sites"], [], "standalone franchise entry pointers")
    expect(image.branch(0x849DF3B8), (0x846F8A60, True), "simple CoachDesk push")
    expect(image.branch(0x849DF3D0), (0x846F8A60, True), "franchise CoachDesk push")
    expect(image.u32(0x849DF3B4) & 0xFFFF, 0x0C10, "Simple CoachDesk low immediate")
    expect(image.u32(0x849DF3CC) & 0xFFFF, 0x0BC8, "Franchise CoachDesk low immediate")

    franchise_loader_callers = image.direct_branch_sites(0x84A1FD00)
    expect(
        franchise_loader_callers,
        [
            {"site": "0x84A1FE74", "kind": "jump"},
            {"site": "0x84A20048", "kind": "call"},
            {"site": "0x84AEF138", "kind": "call"},
        ],
        "franchise loader true-entry callers",
    )
    # Shared-save bodies may call body entry +8 directly.
    franchise_loader_body_callers = image.direct_branch_sites(0x84A1FD08)
    expect(franchise_loader_body_callers, [], "franchise loader body callers")
    expect(image.branch(0x84A1FCDC), (0x84A1FB80, True), "companion franchise loader call")
    expect(image.branch(0x84AEE9FC), (0x84AEFB40, True), "Wrapup event3 resource-state call")
    expect(image.branch(0x84AEFBC8), (0x84AEF100, True), "Wrapup state1 cleanup call")
    expect(image.branch(0x84AEF138), (0x84A1FD00, True), "Wrapup-to-franchise loader call")

    expect(image.u32(0x820FAAE0), 1, "Wrapup event1 key")
    expect(image.u32(0x820FAAE4), 0x84AEE800, "Wrapup event1 callback")
    expect(image.u32(0x820FAAF8), 3, "Wrapup event3 key")
    expect(image.u32(0x820FAAFC), 0x84AEE9E8, "Wrapup event3 callback")
    expect(image.u32(0x820FAB68), 0x84614CEC, "Wrapup title pointer")
    expect(image.utf16(image.u32(0x820FAB6C)), "WrapupMenu_Menu", "Wrapup state name")
    expect(image.branch(0x84AEE8A0), (0x84AEF1C0, True), "Wrapup event1 show request owner")
    expect(image.branch(0x84B00A58), (0x84AEEA90, True), "Wrapup route helper")
    wrapup_root = incoming(image, 0x84B00948, int(pdata_rows[0x84B00948]["pdata_slot"], 16))
    expect(wrapup_root["direct_branches"], [{"site": "0x84AECE18", "kind": "jump"}], "Wrapup root branches")
    expect(wrapup_root["classic_materializations"], [], "Wrapup root materializations")
    expect(wrapup_root["non_pdata_fullword_sites"], [], "Wrapup root pointers")
    expect(image.fullwords(0x84AECE18), [], "orphan Wrapup wrapper pointers")
    expect(image.direct_branch_sites(0x84AECE18), [], "orphan Wrapup wrapper callers")

    layout = json.loads(args.cross_layout.read_text())
    apf_franchise_layouts = [
        row for row in layout["layouts"]
        if row["platform"] == "apf2k8" and row["outer_index"] == 810
    ]
    nfl_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in layout["layouts"]:
        if row["platform"] == "nfl2k5":
            nfl_by_name[row["layout_name"].casefold()].append(row)
    matches = []
    for row in apf_franchise_layouts:
        peers = nfl_by_name.get(row["layout_name"].casefold(), [])
        if peers:
            matches.append(
                {
                    "layout_name": row["layout_name"],
                    "apf_sha256": row["sha256"],
                    "nfl_sha256": [peer["sha256"] for peer in peers],
                    "byte_identical": any(peer["sha256"] == row["sha256"] for peer in peers),
                }
            )
    expect(len(apf_franchise_layouts), 29, "franchise LAYT count")
    expect(len(matches), 22, "cross-title franchise layout-name matches")
    expect(sum(row["byte_identical"] for row in matches), 0, "byte-identical matched layouts")

    localization_meta = json.loads(args.localization_json.read_text())
    expect(
        localization_meta["executable_evidence"]["english_request"],
        "default.xex:0x84691C68 requests resource ID 0xe33e3b9c, CRC32('English')",
        "English startup request",
    )
    localization_rows = [
        row for row in read_tsv(args.localization_tsv)
        if row["outer_index"] == "1127" and row["table_name"] == "English"
    ]
    selected_localization: list[dict[str, Any]] = []
    for text in SELECTED_LOCALIZATION:
        rows = [row for row in localization_rows if row["text"] == text]
        if not rows:
            raise ValueError(f"missing selected English localization text {text!r}")
        selected_localization.append(
            {
                "text": text,
                "records": [
                    {
                        "text_id": row["text_id"],
                        "record_index": int(row["record_index"]),
                        "direct_fullword_sites_in_xex": [hx(value) for value in image.fullwords(int(row["text_id"], 16))],
                        "classic_materializations_in_xex": image.constructions(int(row["text_id"], 16)),
                    }
                    for row in rows
                ],
                "display_call_site_proved": False,
            }
        )

    retained_strings = [
        (0x845F3268, "Congratulations for completing the All-Pro Football 2K8 franchise. Try again to improve your record!"),
        (0x845F3400, "Your time as a coach is over. No more user teams exist. You should quit your Franchise game and try again."),
        (0x8461F500, "Congratulations! You are a true champion! Your football skills will save us all! You're the greatest! Okay, all that might be pushing it a bit. Nevertheless, you have completed ESPN NFL 2K5's \"Basic Training\" mode and you're likely a better person because of it."),
        (0x8461F730, "Welcome to ESPN NFL 2K5's \"Basic Training\" mode. Here you will be put through a series of drills that will help you gain a basic understanding of how to play this game."),
    ]
    retained_rows = []
    for address, text in retained_strings:
        expect(image.utf16(address), text, f"retained executable string {hx(address)}")
        retained_rows.append(
            {
                "address": hx(address),
                "text": text,
                "fullword_sites": [hx(value) for value in image.fullwords(address)],
                "classic_materializations": image.constructions(address),
                "retail_display_proved": False,
            }
        )

    toolchain = read_tsv(args.toolchain_strings)
    toolchain_values = {row["value"] for row in toolchain}
    required_paths = [
        "nfl_clean_opt",
        "c:/work/maincodeline/intermediates/vcsports/us/bin/xenon/nfl/nfl_clean_opt.xex",
        "c:/work/maincodeline/vcsports/nfl/code/menus/oldmenus/franchisemenu_coachsdesk.vcc",
        "c:/work/maincodeline/vcsports/nfl/code/menus/oldmenus/franchisemenu_playsetup.mvcc",
        "c:/work/maincodeline/vcsports/nfl/code/menus/seasonmenus.mvcc",
        "c:/work/maincodeline/vcsports/nfl/code/menus/trophyroommenu.mvcc",
        "c:/work/maincodeline/vcsports/nfl/code/wrapup/wrapupresource.vcc",
    ]
    for value in required_paths:
        expect(value in toolchain_values, True, f"toolchain/source path {value}")

    trace = args.trace.read_text()
    pseudo = args.pseudo.read_text()
    for needle in [
        "Program MD5: 217eea6084c3d03f0f1143802b1f5636",
        "true_entry=0x849DF2F0 body_entry=0x849DF2F8 end_exclusive=0x849DF3E0",
        "0x84A1FD6C raw=0x4BC6DD05 instruction=bl 0x8468da70",
        "0x84AEF220 raw=0x4BB9E851 instruction=bl 0x8468da70",
    ]:
        expect(needle in trace, True, f"Ghidra trace needle {needle}")
    for needle in [
        "Function_846F8A60(param_1,0xffffffff820e0bc8)",
        "Function_846F8A60(param_1,0xffffffff820e0c10)",
        "0xffffffff845fd7e8",
        "0xffffffff84626428",
        "0xffffffff8462651c",
        "0xffffffff84626550",
    ]:
        expect(needle in pseudo, True, f"Ghidra pseudo needle {needle}")

    report = {
        "schema": "vc_apf_franchise_runtime_ownership/v1",
        "scope": {
            "franchise_assets_only": False,
            "franchise_code_compiled_proved": True,
            "franchise_archive_request_compiled_proved": True,
            "standalone_franchise_entry_compiled_proved": True,
            "standalone_franchise_static_owner_proved": False,
            "standalone_franchise_main_menu_route_proved": False,
            "half_finished_franchise_playable_proved": False,
            "retail_season_main_route_proved": True,
            "retail_season_old_franchise_gameplan_link_proved": True,
            "wrapup_descriptor_owns_franchise_requests_proved": True,
            "wrapup_retail_root_proved": False,
            "selected_nfl_espn_localization_display_proved": False,
            "launches_original_game": False,
            "writes_executable": False,
            "writes_ghidra_project": False,
        },
        "classification": {
            "result": "substantial APF-adapted franchise code and resources are compiled, but the standalone Coach's Desk entry is statically unowned; retail Season reuses at least one old franchise menu, and Wrapup owns conditional franchise/franchise_show request paths whose retail root remains unproved",
            "not_assets_only_reason": "nine old FranchiseMenu state records, a real franchise-core initializer, archive-request code, and descriptor-owned callback graphs coexist with the archives",
            "not_playable_franchise_reason": "no Main-menu row or static incoming owner reaches the standalone initializer at 0x849DF2F0",
        },
        "source": {
            "xex": args.apf_xex.name,
            "xex_sha256": file_digest(args.apf_xex),
            "reconstructed_pe": args.apf_pe.name,
            "reconstructed_pe_size": len(image.data),
            "reconstructed_pe_sha256": digest(image.data),
            "inputs": {label: {"path": str(path), "sha256": file_digest(path)} for label, path in inputs.items()},
        },
        "retained_source_identity": {
            "required_strings": required_paths,
            "source_paths_are_runtime_reachability_proof": False,
        },
        "recovered_boundaries": boundaries,
        "old_franchise_states": old_states,
        "standalone_franchise_entry": {
            "function": "0x849DF2F0",
            "decompiler_body": "0x849DF2F8..0x849DF3DF",
            "mode_selector_global": "0x84F3FB28",
            "mode_zero_target": "0x820E0BC8",
            "mode_nonzero_target": "0x820E0C10",
            "stack_push": "0x846F8A60",
            "incoming_static_audit": franchise_entry,
            "status": "compiled exact initializer with no static incoming owner",
        },
        "archive_requests": requests,
        "archive_inventory": archive_inventory,
        "franchise_loader_ownership": {
            "loader": "0x84A1FD00",
            "direct_callers_to_true_entry": franchise_loader_callers,
            "wrapup_event3_conditional_chain": [
                {"site": "0x820FAAFC", "edge": "event 3 callback -> 0x84AEE9E8"},
                {"site": "0x84AEE9FC", "edge": "call 0x84AEFB40"},
                {"site": "0x84AEFBC8", "edge": "state==1 call 0x84AEF100"},
                {"site": "0x84AEF138", "edge": "resource-present call 0x84A1FD00"},
                {"site": "0x84A1FD6C", "edge": "request franchise.iff"},
            ],
            "retail_execution_proved": False,
        },
        "retail_season_reuse": {
            "main_row": season_main_row,
            "main_row_target_site": "0x84E57408",
            "season_descriptor": "0x820F4308",
            "load_new_rows": "0x84E57220",
            "new_select_team_target": "0x820F42C0",
            "season_nav_gameplan_target_site": "0x84E562D0",
            "season_nav_gameplan_descriptor": "0x820F3FC0",
            "old_gameplan_target_site": "0x84E55F10",
            "old_gameplan_descriptor": "0x820E0B80",
            "old_gameplan_state": "FranchiseMenu_CoachGameplan",
        },
        "wrapup_ownership": {
            "descriptor": "0x820FAB68",
            "state_name": "WrapupMenu_Menu",
            "event_1_callback": "0x84AEE800",
            "event_1_franchise_show_request_call": "0x84AEF220",
            "event_3_callback": "0x84AEE9E8",
            "event_3_franchise_request_chain": ["0x84AEFB40", "0x84AEF100", "0x84A1FD00"],
            "route_function": "0x84B00948",
            "orphan_tail_wrapper": "0x84AECE18",
            "route_static_audit": wrapup_root,
            "orphan_wrapper_fullword_sites": [],
            "orphan_wrapper_direct_callers": [],
            "retail_root_status": "unproved; descriptor-owned callbacks are exact but the only direct route edge begins at an unowned no-PDATA tail wrapper",
        },
        "cross_title_franchise_layouts": {
            "apf_layout_count": len(apf_franchise_layouts),
            "same_name_nfl_layout_count": len(matches),
            "byte_identical_count": sum(row["byte_identical"] for row in matches),
            "matches": matches,
            "interpretation": "same-name layouts with different payload hashes support a converted/evolved Xenon lineage, not byte-identical Xbox asset carryover",
        },
        "selected_localization": {
            "english_startup_request": localization_meta["executable_evidence"]["english_request"],
            "records": selected_localization,
            "interpretation": "resource presence is exact; per-row display ownership remains unproved",
        },
        "retained_executable_strings": retained_rows,
        "ghidra": {
            "read_only": True,
            "trace_sha256": digest(trace.encode()),
            "pseudo_sha256": digest(pseudo.encode()),
            "transient_rebuild_count": trace.count("true_entry="),
            "pseudo_warning_count": pseudo.count("WARNING:"),
            "pseudo_portme_count": pseudo.count("// PORTME:"),
        },
        "portme": PORTME,
    }
    expect(report["ghidra"]["transient_rebuild_count"], 11, "Ghidra rebuild count")
    return report


def write_tsv(path: Path, report: dict[str, Any]) -> None:
    rows: list[tuple[str, str, str, str, str]] = []
    for key, value in report["scope"].items():
        rows.append(("scope", key, str(value).lower(), "", ""))
    for row in report["archive_requests"]:
        rows.append(("archive_request", row["archive"], row["call_site"], row["request_hash"], row["function"]))
    for row in report["old_franchise_states"]:
        rows.append(("old_state", row["name"], row["descriptor_candidate"], row["name_address"], row["name_pointer_site"]))
    for row in report["portme"]:
        rows.append(("portme", row["address"], row["text"], "", ""))
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(["kind", "name_or_address", "value_or_status", "detail_a", "detail_b"])
        writer.writerows(rows)


def write_portme(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "/* Generated APF franchise runtime ownership blockers. */",
        "#include <stdint.h>",
        "",
    ]
    for index, row in enumerate(report["portme"]):
        lines.extend(
            [
                f"void vc_apf_franchise_portme_{index}(uintptr_t runtime) {{",
                "    (void)runtime;",
                f"    // PORTME: {row['address']}: {row['text']}",
                "}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apf-xex", type=Path, required=True)
    parser.add_argument("--apf-pe", type=Path, required=True)
    parser.add_argument("--inner-candidates", type=Path, required=True)
    parser.add_argument("--menu-state", type=Path, required=True)
    parser.add_argument("--cross-layout", type=Path, required=True)
    parser.add_argument("--localization-json", type=Path, required=True)
    parser.add_argument("--localization-tsv", type=Path, required=True)
    parser.add_argument("--toolchain-strings", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--pseudo", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--tsv-out", type=Path, required=True)
    parser.add_argument("--portme-c-out", type=Path, required=True)
    args = parser.parse_args()

    report = build_report(args)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_tsv(args.tsv_out, report)
    write_portme(args.portme_c_out, report)
    print(
        "APF_FRANCHISE_RUNTIME_OWNERSHIP_GENERATED "
        f"states={len(report['old_franchise_states'])} "
        f"archives={len(report['archive_requests'])} "
        f"portme={len(report['portme'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
