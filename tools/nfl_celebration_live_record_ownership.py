#!/usr/bin/env python3
"""Reproduce the NFL 2K5 celebration live-record ownership/type trace.

This pass deliberately separates the edge that is statically closed from the
edge that is not: a successful state-word 0x34 selector dispatch is backed by
an actor-owned tag-2 scoring record, but the record's concrete type (and thus
selected-name playback mode 1) is not fixed by the shipped static path.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import struct


EXPECTED_XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"
STATE_CALLBACK_TABLE_VA = 0x00AABEF8
STATE_CALLBACK_TABLE_SIZE = 0x274
CELEBRATION_HANDLER_VA = 0x0018D6D0
PROFILE_LABEL_TABLE_VA = 0x005858D0
PROFILE_LABEL_COUNT = 37

EXPECTED_RANGES = (
    ("tag2_forwarder", 0x000A05F0, 0x000A0653,
     "9d1ae18abe93e5a7e30d1f8a316fec90f6165b6344dd85b0d4f2ee94634365b8"),
    ("score_point_effects", 0x000B8400, 0x000B8621,
     "a5ff147caf84e99f66ec3a642f2e24397cc34260405726d29ad357a6e3707e7a"),
    ("profile_selector_setter", 0x00142390, 0x001423A6,
     "d20d4bf2bc8563d76686b6b175672627b3e45a3ff209398cce30d184f8c01c66"),
    ("spatial_classifier", 0x0017C0E0, 0x0017C187,
     "76fc15c822f19875c018d76c68de7424b3d7298cbd81961dde55961dc56ed776"),
    ("actor_spatial_classifier", 0x0017C3C0, 0x0017C3F2,
     "3abc3f3b0fa23542d72a0ca0ebb7becb053f3f736de2a49b26b4c86994df046d"),
    ("state34_handler", 0x0018D6D0, 0x0018D831,
     "038269fc928922d280656baaab2e16fa0a1bbb7fd133857568c65986b42c1595"),
    ("actor_state_dispatcher", 0x0018EC40, 0x0018EC9F,
     "a6391fed20582d34d21034343c1ee11712a0fceb6f3eac7a3d8fd6ae28087da1"),
    ("non_tag2_writer_tags_4_and_5", 0x00185EDB, 0x00185FB2,
     "803564bd6d36eaa12fb2f2ba85c95a3c51f9c800a4b2121e9dae2fde74c42c91"),
    ("non_tag2_writer_tag_7_a", 0x0019E87B, 0x0019E8AE,
     "05e22de678c6c2b77304569eac3760079509d9fc03b1331ad2e81b5e3c5af74a"),
    ("non_tag2_writer_tag_1", 0x001A01BA, 0x001A01DE,
     "9cf4f033548b3ce0e1b3a7cfa220d1fdc4a490e4b334db11940d6153713a280e"),
    ("non_tag2_writer_tag_7_b", 0x001A5EB0, 0x001A5F1A,
     "6e6bd96cf34eb31b0f46bc3f19920fb0c5dc8d0265a202a96d21da4185a13455"),
    ("celebration_callback", 0x001ABF30, 0x001AC010,
     "6088236847fd1c01942c26a43bdf474eeaaa2252c5d7a8613477e654d44cbb9c"),
    ("tag2_writer", 0x001CF250, 0x001CF2E1,
     "2252f7d50fdb61954776324a64de6d7af3af8567bf18da97fbf8fe8e8418fa69"),
    ("non_tag2_writer_tag_3", 0x001D009B, 0x001D00BC,
     "105f9279cd26aac9361d0e814446604a4992ea347ff71b40b5aa3a2ab7d596a7"),
    ("ring_insert", 0x0020F0D0, 0x0020F179,
     "07d00b6ca2e9ed0d07ddd9eeb40ea81d24adb5b65bb8a752227c7ec334781542"),
    ("ring_insert_wrapper", 0x0020F220, 0x0020F22D,
     "6df4fccc80cc79595aa43e84d9bce20eda0bdc3b1d8fd061ab241c6b729f65db"),
    ("ring_newest_by_tag", 0x0020F230, 0x0020F269,
     "e9961c631c824afb35462a2e768854ff19837f3fd974b9f75488fe46e2de591e"),
    ("score_type_setters", 0x0022DFB0, 0x0022E044,
     "38b405ace541693de77a6f4f18d24cd0df0fc9d928f78a7d9d9bfb26b6505575"),
    ("score_event_dispatch", 0x0022E2D0, 0x0022E398,
     "952b63458ac2ccb600f26714a37a901db68e6fe248bc9f64124ab535dd0f84dc"),
    ("celebration_state_callback", 0x002DDB10, 0x002DDCB9,
     "5b47e65e5041f49bc4876ff76324223ce08748d95952ed1f9c69677dd72dcc60"),
    ("nonmode1_special_guard", 0x002DDD90, 0x002DDDAA,
     "e23bbddf0cb6d97ffc3ed2ff57b9b37804562bdb34dd43bdba6064e5398484f2"),
    ("spatial_gate", 0x002DDDB0, 0x002DDDBD,
     "f7b050bef3fb8bf7ee9c9a73106932e8a497b325a1e989af7ef593b5f0f63ba5"),
    ("callback_installed_state", 0x002DE170, 0x002DE2F6,
     "075435d18548c31177cb421e5b94474d563fab3d0e19cb9478e774bd0cce7850"),
    ("actor_owned_constructor", 0x002DE300, 0x002DE42B,
     "2bf347ef183954193eb7b56122c4abdcfea5c42fb371ce03b3d5344734c26783"),
    ("other_owned_constructor", 0x002DE620, 0x002DE75E,
     "385d47a227458f4928a24f4475fd8082cabd37d26872516d12f533cb0c06074d"),
    ("playback_mode_resolver", 0x002DE7A0, 0x002DE7F8,
     "87bd7781e3634ad166f19a33360b780087f20b52c4e965e013e5f0e7a6a91f3f"),
    ("record_state_dispatch", 0x002DE800, 0x002DE922,
     "1fa6c70b6c3f78e4dc3eb41ea1584b53de6c46695dde0eb4d7f72e57c71c9642"),
    ("selector_dispatch", 0x002DE9C0, 0x002DE9FE,
     "24c4fc66406e14292bfe4dcb859a6d072156a559f1966f5a5a518c59ed9ac3a1"),
    ("profile_choice_dense_to_row", 0x00369650, 0x00369688,
     "1d987ce123319c71ef0cba941c25aa0deea5b4c4b88d5ffcd956566183500a70"),
    ("profile_selector_setter_caller", 0x00369AC0, 0x00369B1F,
     "67192ea609116ba4792915c1b017377398e1117f363d0125eb5d21aa7e08e474"),
    ("mode_jump_table", 0x002DE7E4, 0x002DE7F8,
     "929e6fd26438afcf463f8df749beea4da9df37e7a9c5cd713d310b82f6004608"),
    ("spatial_gate_table", 0x00530170, 0x00530184,
     "90e87ed2bfb13891ce9f3cb39928051e1bf1187030c43cdaaa1b5a3a9183dbee"),
    ("profile_label_table", 0x005858D0, 0x005859F8,
     "93f83eff0105e6435f2ae1549d5bafd4c10ec1ab01370e7ae3e51e74f14773c8"),
    ("type1_scoring_reaction_root", 0x00708188, 0x007081BC,
     "408254ada4a1c8ac436339eb53261a6461b0e46fa6770d1b0c30e3fcf389dc0b"),
    ("type1_scoring_reaction_event_sentinel", 0x00706B38, 0x00706B3C,
     "ad95131bc0b799c0b1af477fb14fcf26a6a9f76079e48bf090acb7e8367bfd0e"),
    ("state_callback_table", 0x00AABEF8, 0x00AAC16C,
     "c2d49816fbc3d7bd80b5f63c873eb18a20f6255c971547e2e268280aa64978d1"),
    ("selector_row_2", 0x0050CFE0, 0x0050CFEC,
     "c657d61d062fdcd39e866ac4ce6ee99f6c35191392ed4f4c752a8781a7581d65"),
)


class EvidenceError(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class XbeView:
    def __init__(self, xbe_path: Path, header_path: Path) -> None:
        self.path = xbe_path
        self.data = xbe_path.read_bytes()
        self.header = json.loads(header_path.read_text(encoding="utf-8"))
        actual = hashlib.md5(self.data).hexdigest()
        if actual != EXPECTED_XBE_MD5:
            raise EvidenceError(f"unexpected XBE MD5 {actual}")

    def file_offset(self, va: int, size: int) -> int:
        for section in self.header["sections"]:
            start = int(section["virtual_address"])
            raw_size = int(section["raw_size"])
            if start <= va and va + size <= start + raw_size:
                return int(section["raw_address"]) + va - start
        raise EvidenceError(f"VA 0x{va:08x}+0x{size:x} is not file-backed")

    def at(self, va: int, size: int) -> bytes:
        offset = self.file_offset(va, size)
        result = self.data[offset:offset + size]
        if len(result) != size:
            raise EvidenceError(f"short read at VA 0x{va:08x}")
        return result

    def utf16z(self, va: int) -> str:
        offset = self.file_offset(va, 2)
        raw = bytearray()
        for _ in range(512):
            unit = self.data[offset:offset + 2]
            offset += 2
            if len(unit) != 2:
                break
            if unit == b"\0\0":
                return raw.decode("utf-16le")
            raw.extend(unit)
        raise EvidenceError(f"unterminated UTF-16 string at 0x{va:08x}")


def require_phrases(text: str, phrases: tuple[str, ...], label: str) -> None:
    for phrase in phrases:
        if phrase not in text:
            raise EvidenceError(f"{label}: missing exact evidence {phrase!r}")


def reference_sources(trace: str, target: int) -> list[int]:
    prefix = f"0x{target:08X} direct="
    lines = [line for line in trace.splitlines() if line.startswith(prefix)]
    if len(lines) != 1:
        raise EvidenceError(f"expected one focused-reference line for {prefix}")
    refs = lines[0].split(" refs=", 1)[1]
    return [int(match, 16) for match in re.findall(r"(0x[0-9A-F]{8})\(", refs)]


def type_rows() -> list[dict[str, object]]:
    return [
        {"record_type": 1, "score_points": 6, "score_dispatch_callsite": "0x0022e306",
         "resolver_target": "0x002de7cf", "actor_owned_playback_mode": 1,
         "gate_2": "admitted; gate is normalized to 0", "gate_0_or_1": "admitted",
         "selected_name_mode": True},
        {"record_type": 2, "score_points": 2, "score_dispatch_callsite": "0x0022e340",
         "resolver_target": "0x002de7c7", "actor_owned_playback_mode": 14,
         "gate_2": "rejected at 0x002de893", "gate_0_or_1": "admitted",
         "selected_name_mode": False},
        {"record_type": 3, "score_points": 3, "score_dispatch_callsite": "0x0022e323",
         "resolver_target": "0x002de7b6", "actor_owned_playback_mode": 2,
         "gate_2": "rejected at 0x002de893", "gate_0_or_1": "admitted",
         "selected_name_mode": False},
        {"record_type": 4, "score_points": 1, "score_dispatch_callsite": "0x0022e37a",
         "resolver_target": "0x002de7b6", "actor_owned_playback_mode": 2,
         "gate_2": "rejected at 0x002de893", "gate_0_or_1": "admitted",
         "selected_name_mode": False},
        {"record_type": 5, "score_points": 2, "score_dispatch_callsite": "0x0022e35d",
         "resolver_target": "0x002de7cf", "actor_owned_playback_mode": 1,
         "gate_2": "admitted; gate is normalized to 0", "gate_0_or_1": "admitted",
         "selected_name_mode": True},
    ]


def path_rows() -> list[dict[str, object]]:
    return [
        {"step": 1, "source": "score result event +0x74/+0x78/+0x7c",
         "target": "0x000a05f0", "instruction": "0x0022e2d0..0x0022e37a",
         "meaning": "five exact branches pass type 1..5, owner, and companion"},
        {"step": 2, "source": "0x000a05f0", "target": "0x001cf250",
         "instruction": "0x000a05f7..0x000a05fc",
         "meaning": "forwards type on stack, owner in EDX, companion in ECX"},
        {"step": 3, "source": "0x001cf250", "target": "tag-2 0x30-byte record",
         "instruction": "0x001cf29d..0x001cf2ad",
         "meaning": "+0x00 tag=2, +0x10 owner, +0x14 companion, +0x18 type"},
        {"step": 4, "source": "tag-2 record", "target": "every live actor runtime+0x490 ring",
         "instruction": "0x001cf26c..0x001cf2b8",
         "meaning": "writer walks the player pool and calls the sole ring insert wrapper"},
        {"step": 5, "source": "actor runtime+0x490", "target": "newest tag-2 record",
         "instruction": "0x002de81f..0x002de82a",
         "meaning": "state construction requests tag 2 through 0x0020f230"},
        {"step": 6, "source": "record+0x10", "target": "playback mode resolver",
         "instruction": "0x002de872..0x002de877",
         "meaning": "resolver consumes owner at +0x00 and type at +0x08"},
        {"step": 7, "source": "resolved record", "target": "actor-owned constructor",
         "instruction": "0x002de8ec..0x002de900",
         "meaning": "0x002de300 is called only when record owner equals current actor"},
        {"step": 8, "source": "0x002de300", "target": "callback 0x002de170 and state+0xa0",
         "instruction": "0x002de31d/0x002de35c",
         "meaning": "unique constructor installs callback and stores resolved playback mode"},
        {"step": 9, "source": "callback 0x002de170", "target": "callback 0x002ddb10",
         "instruction": "0x002de1da",
         "meaning": "the only static 0x002ddb10 installation is this transition"},
        {"step": 10, "source": "actor state word", "target": "callback table 0x00aabef8",
         "instruction": "0x0018ec63..0x0018ec7f",
         "meaning": "dispatcher indexes the table by actor state+0x1c"},
        {"step": 11, "source": "state word 0x34", "target": "0x002de9c0(actor,2)",
         "instruction": "0x0018d6e4/0x0018d804..0x0018d80b",
         "meaning": "shared handler maps 0x34 to selector slot 2"},
        {"step": 12, "source": "0x002de9c0", "target": "celebration selector",
         "instruction": "0x002de9d1..0x002de9e8",
         "meaning": "selection is admitted only for callback 0x002de170 or 0x002ddb10"},
        {"step": 13, "source": "successful state-0x34 selection", "target": "record owner",
         "instruction": "unique reverse chain 0x002de9c0 -> 0x002de170/0x002ddb10 -> 0x002de300 -> 0x002de8ec",
         "meaning": "record owner is exactly the current actor"},
        {"step": 14, "source": "state word 0x34", "target": "record type/playback mode",
         "instruction": "0x002dddb0/0x002de882..0x002de895",
         "meaning": "not closed: gate 0/1 admits types 2/3/4 as well as mode-1 types 1/5"},
    ]


def profile_rows() -> list[dict[str, object]]:
    return [
        {"step": 1, "source": "UI dense choice ordinal in EDX", "target": "raw selector row",
         "instruction": "0x00369ae6..0x00369aed", "meaning": "0x00369650 skips unavailable rows and returns a 0..36 row"},
        {"step": 2, "source": "global 0x00cc2ee4", "target": "setter ECX",
         "instruction": "0x00369af3", "meaning": "supplies profile index"},
        {"step": 3, "source": "global 0x00cc2ed8", "target": "setter EDX",
         "instruction": "0x00369aed", "meaning": "supplies selector slot"},
        {"step": 4, "source": "raw selector row", "target": "profile selector table",
         "instruction": "0x00369af9..0x00369afa -> 0x00142390",
         "meaning": "direct caller writes base+(profile*0xf9e+slot)*4"},
        {"step": 5, "source": "default slot 2 = row 2", "target": "saved/runtime mutation",
         "instruction": "0x0014239c", "meaning": "row 2 is not immutable; it is exact only for a new or unmodified profile"},
    ]


def build(args: argparse.Namespace) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    xbe = XbeView(args.xbe, args.xbe_header)
    trace = args.trace.read_text(encoding="utf-8")
    pseudo = args.pseudo.read_text(encoding="utf-8")
    selector = json.loads(args.selector_report.read_text(encoding="utf-8"))
    if selector.get("schema") != "nfl2k5_celebration_selector_producer/v1":
        raise EvidenceError("unexpected selector-producer report schema")
    if not selector["result"]["selector_index_2_default_producer_proved"]:
        raise EvidenceError("selector-producer report no longer proves default row 2")

    ranges = []
    for name, start, end, expected in EXPECTED_RANGES:
        actual = sha256(xbe.at(start, end - start))
        if actual != expected:
            raise EvidenceError(f"{name}: expected {expected}, got {actual}")
        ranges.append({"name": name, "start": f"0x{start:08x}",
                       "end_exclusive": f"0x{end:08x}", "size": end - start,
                       "file_offset": xbe.file_offset(start, end - start),
                       "sha256": actual})

    callback_entries = []
    for state_word in (0x33, 0x34, 0x8E):
        entry_va = STATE_CALLBACK_TABLE_VA + state_word * 4
        callback, = struct.unpack("<I", xbe.at(entry_va, 4))
        if callback != CELEBRATION_HANDLER_VA:
            raise EvidenceError(f"state 0x{state_word:x} callback differs")
        callback_entries.append({"state_word": f"0x{state_word:08x}",
                                 "entry_va": f"0x{entry_va:08x}",
                                 "callback_va": f"0x{callback:08x}"})

    mode_targets = list(struct.unpack("<5I", xbe.at(0x002DE7E4, 20)))
    if mode_targets != [0x002DE7CF, 0x002DE7C7, 0x002DE7B6, 0x002DE7B6, 0x002DE7CF]:
        raise EvidenceError(f"mode jump table differs: {mode_targets}")
    gate_values = list(struct.unpack("<5I", xbe.at(0x00530170, 20)))
    if gate_values != [1, 0, 2, 0, 1]:
        raise EvidenceError(f"spatial gate table differs: {gate_values}")
    score_targets = list(struct.unpack("<5I", xbe.at(0x0022E388, 20)))
    if score_targets != [0x0022E2F6, 0x0022E330, 0x0022E313, 0x0022E36A, 0x0022E34D]:
        raise EvidenceError(f"score jump table differs: {score_targets}")
    reaction_root = list(struct.unpack("<13I", xbe.at(0x00708188, 52)))
    if reaction_root[9:12] != [0x00706D30, 0x00706B40, 0x00706B38]:
        raise EvidenceError("type-1 scoring-reaction root pointers differ")
    if xbe.at(reaction_root[11], 4) != b"\xff\xff\xff\xff":
        raise EvidenceError("type-1 scoring-reaction event stream is no longer empty")

    labels = []
    for index in range(PROFILE_LABEL_COUNT):
        unlock_id, label_va = struct.unpack("<II", xbe.at(PROFILE_LABEL_TABLE_VA + index * 8, 8))
        labels.append({"selector_row": index, "availability_id": unlock_id,
                       "label_va": f"0x{label_va:08x}", "label": xbe.utf16z(label_va)})
    if labels[2]["label"] != "Chest Pound" or labels[-1]["label"] != "The Wap":
        raise EvidenceError("profile celebration label table differs")

    left, right, opaque = struct.unpack("<III", xbe.at(0x0050CFE0, 12))
    if left != 0 or xbe.utf16z(right) != "ANM_CELEBRATE_USER_34" or opaque != 21:
        raise EvidenceError("selector row 2 differs")

    require_phrases(trace, (
        "Program MD5: 444064a9ec984dd29d2c05a43f5c96e8",
        "STATE_WORD_0X34_DIRECT_WRITE_SCAN\nmatches=0",
        "0x001CF29D MOV dword ptr [ESP + 0x10],0x2",
        "0x001CF2A5 MOV dword ptr [ESP + 0x20],EBX",
        "0x001CF2A9 MOV dword ptr [ESP + 0x24],EAX",
        "0x001CF2AD MOV dword ptr [ESP + 0x28],EDI",
        "0x00185EE6 MOV dword ptr [ESP + 0x60],0x4",
        "0x00185F87 MOV dword ptr [ESP + 0xa0],0x5",
        "0x0019E888 MOV dword ptr [ESP + 0x20],0x7",
        "0x001A01C9 MOV dword ptr [ESP + 0x10],0x1",
        "0x001A5EBD MOV dword ptr [ESP + 0x50],0x7",
        "0x001D00A0 MOV dword ptr [ESP + 0x10],0x3",
        "0x002DE82A CALL 0x0020f230",
        "0x002DE877 CALL 0x002de7a0",
        "0x002DE893 JZ 0x002de849",
        "0x002DE8EC CMP dword ptr [EBP],EDI",
        "0x002DE900 CALL 0x002de300",
        "0x002DE31D MOV dword ptr [ESI],0x2de170",
        "0x002DE35C MOV dword ptr [ESI + 0xa0],ECX",
        "0x002DE1DA MOV dword ptr [EDI],0x2ddb10",
        "0x0018D6E4 CMP dword ptr [EBP + 0x1c],0x34",
        "0x0018D804 MOV EDX,0x2",
        "0x0018D80B CALL 0x002de9c0",
        "0x002DE9D1 CMP EAX,0x2de170",
        "0x002DE9DF CMP EAX,0x2ddb10",
        "0x00369AFA CALL 0x00142390",
        "0x005858D0 length=296 bytes=",
        "0x00708188 length=52 bytes=",
        "0x00706B38 length=4 bytes=ffffffff",
    ), "trace")
    require_phrases(pseudo, (
        "/* 0x001CF250:FUN_001cf250 */",
        "/* 0x0020F230:FUN_0020f230 */",
        "/* 0x002DDDB0:FUN_002dddb0 */",
        "/* 0x002DE300:FUN_002de300 */",
        "*puVar4 = &LAB_002de170;",
        "puVar4[0x28] = param_1;",
        "/* 0x002DE9C0:FUN_002de9c0 */",
        "/* 0x00369650:FUN_00369650 */",
        "// PORTME: no saved Ghidra function boundary at 0x0018D6D0",
        "// PORTME: no saved Ghidra function boundary at 0x002DE800",
    ), "pseudo-C")

    expected_refs = {
        0x000A05F0: [0x0022E306, 0x0022E323, 0x0022E340, 0x0022E35D, 0x0022E37A],
        0x00142390: [0x00369AFA],
        0x001CF250: [0x000A05FC],
        0x0020F220: [0x00185F56, 0x00185FAD, 0x0019E8A9, 0x001A01D9, 0x001A5F15, 0x001CF2B8, 0x001D00B7],
        0x002DDB10: [0x002DE1DA],
        0x002DE170: [0x002DE31D],
        0x002DE300: [0x002DE900],
    }
    for target, expected in expected_refs.items():
        actual = reference_sources(trace, target)
        if actual != expected:
            raise EvidenceError(f"0x{target:08x} refs differ: {actual}")

    types = type_rows()
    paths = path_rows()
    profiles = profile_rows()
    report = {
        "schema": "nfl2k5_celebration_live_record_ownership/v1",
        "result": {
            "successful_state_0x34_dispatch_actor_owned_record_proved": True,
            "record_tag": 2,
            "record_domain": "scoring result",
            "record_type_domain": [1, 2, 3, 4, 5],
            "concrete_record_type_for_state_0x34_proved": False,
            "mode_one_record_types": [1, 5],
            "playback_mode_one_for_state_0x34_proved": False,
            "full_previous_portme_closed": False,
            "closure": "ownership exact; type/playback-mode partial",
        },
        "executable": {"path": str(args.xbe), "md5": EXPECTED_XBE_MD5,
                       "sha256": file_sha256(args.xbe), "ranges": ranges},
        "tag2_record": {
            "writer_va": "0x001cf250", "sole_forwarder_va": "0x000a05f0",
            "ring_insert_wrapper_va": "0x0020f220", "ring_lookup_va": "0x0020f230",
            "ring_base_from_actor_runtime": "actor+0x20 then +0x490",
            "ring_capacity": 4, "record_stride": 48, "cursor_offset": "0xc0",
            "layout": {"0x00": "tag = 2", "0x10": "owner actor",
                       "0x14": "companion/side object", "0x18": "scoring result type"},
            "writer_is_only_tag2_ring_insertion_callsite": True,
            "writer_replicates_to_every_live_player_actor": True,
            "scoring_dispatch_va": "0x0022e2d0",
        },
        "ownership_closure": {
            "state_callback_table_va": "0x00aabef8",
            "state_callback_table_size": STATE_CALLBACK_TABLE_SIZE,
            "entries": callback_entries,
            "state_0x34_selector_slot": 2,
            "selector_dispatch_accepted_callbacks": ["0x002de170", "0x002ddb10"],
            "callback_0x002ddb10_only_static_installer": "0x002de1da in callback 0x002de170",
            "callback_0x002de170_only_static_installer": "0x002de31d in constructor 0x002de300",
            "constructor_0x002de300_only_static_callsite": "0x002de900",
            "owner_equality_guard_va": "0x002de8ec",
            "claim": "a successful state-word 0x34 selector dispatch has an actor-owned newest tag-2 scoring record",
        },
        "type_and_mode_boundary": {
            "mode_jump_table": [f"0x{value:08x}" for value in mode_targets],
            "spatial_gate_function_va": "0x002dddb0",
            "spatial_classifier_va": "0x0017c3c0",
            "spatial_gate_table_values_by_classifier_index": gate_values,
            "gate_2_rejects_non_mode_1_va": "0x002de890..0x002de893",
            "gate_2_normalizes_mode_1_va": "0x002de882..0x002de88e",
            "gate_2_for_state_0x34_proved": False,
            "handler_0x0018d6d0_reads_record_type": False,
            "handler_0x0018d6d0_reads_state_plus_a0": False,
            "direct_immediate_state_0x34_write_matches_in_saved_listing": 0,
            "negative_result": "state 0x34 and accepted callback do not distinguish type 1/5 from statically admissible types 2/3/4 when gate is 0 or 1",
            "types": types,
        },
        "profile_selector_mutation": {
            "setter_va": "0x00142390", "direct_callsite_va": "0x00369afa",
            "caller_saved_function_boundary_present": False,
            "profile_index_global_va": "0x00cc2ee4",
            "selector_slot_global_va": "0x00cc2ed8",
            "dense_choice_to_row_va": "0x00369650",
            "label_table_va": "0x005858d0", "label_count": PROFILE_LABEL_COUNT,
            "labels": labels, "row_2_display_label": labels[2]["label"],
            "row_2_resource_name": "ANM_CELEBRATE_USER_34",
            "default_row_2_immutable": False,
            "scope": "newly initialized or otherwise unmodified profile selector slot 2",
        },
        "worked": [
            "closed actor ownership through the unique 0x002de300 -> 0x002de170 -> 0x002ddb10 callback chain",
            "proved the tag-2 layout, four-record ring, unique scoring writer, five type values, and exact point effects",
            "proved playback modes 1,14,2,2,1 for actor-owned types 1..5",
            "found and proved the real profile-selector setter call at 0x00369afa and its 37-label UI table",
        ],
        "failed_trails": [
            "the embedded type-1 scoring-reaction root at 0x00708188 has an immediate 0xffffffff event sentinel, so it cannot emit state 0x34",
            "no direct immediate write of 0x34 to a +0x1c state field exists in the saved Ghidra listing",
        ],
        "blocking": [
            "// PORTME(0x002DDDB0): bind the live state-word 0x34 dispatch to classifier index 2/gate value 2, or capture the concrete tag-2 record type; without that, types 2/3/4 remain admissible and mode 1 is not proved.",
            "// PORTME(0x0018C9C0/0x0018D6D0): recover the dynamic or data-driven producer that writes actor state+0x1C = 0x34; the saved listing has no direct immediate write.",
            "// PORTME(0x00369AC0): recover persistence/load history only when claiming a particular saved profile value; direct runtime mutation at 0x00369AFA is already proved.",
        ],
        "source_pins": {
            "xbe_header": {"path": str(args.xbe_header), "sha256": file_sha256(args.xbe_header)},
            "selector_report": {"path": str(args.selector_report), "sha256": file_sha256(args.selector_report)},
            "ghidra_trace": {"path": str(args.trace), "sha256": file_sha256(args.trace)},
            "ghidra_pseudo_c": {"path": str(args.pseudo), "sha256": file_sha256(args.pseudo)},
            "ghidra_script": {"path": str(args.ghidra_script), "sha256": file_sha256(args.ghidra_script)},
        },
    }
    return report, paths, types, profiles


def write_tsv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), dialect="excel-tab", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("xbe", type=Path)
    parser.add_argument("--xbe-header", required=True, type=Path)
    parser.add_argument("--selector-report", required=True, type=Path)
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--pseudo", required=True, type=Path)
    parser.add_argument("--ghidra-script", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--path-tsv", required=True, type=Path)
    parser.add_argument("--type-tsv", required=True, type=Path)
    parser.add_argument("--profile-tsv", required=True, type=Path)
    args = parser.parse_args()
    report, paths, types, profiles = build(args)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_tsv(args.path_tsv, paths)
    write_tsv(args.type_tsv, types)
    write_tsv(args.profile_tsv, profiles)
    print("NFL_CELEBRATION_LIVE_RECORD_OWNERSHIP_COMPLETE ownership=exact type=partial modes=5 paths=14 profile_steps=5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
