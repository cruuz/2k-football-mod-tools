#!/usr/bin/env python3
"""Build the exact NFL 2K5 celebration-selector producer evidence report."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct


EXPECTED_XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"
ROW2_VA = 0x0050CFE0
ROW2_NAME = "ANM_CELEBRATE_USER_34"
STATE_CALLBACK_TABLE_VA = 0x00AABEF8
STATE_CALLBACK_TABLE_SIZE = 0x274
CELEBRATION_HANDLER_VA = 0x0018D6D0

EXPECTED_RANGES = (
    ("game_mode_guard", 0x00070870, 0x00070888,
     "ec23e173c5c01e3fdcba6aa22ecc32a5aab14b5160bb587967fa7b0ad90410f0"),
    ("player_profile_pointer", 0x00077280, 0x0007728A,
     "74f091c4d6b9a61b4d0d66013f3f4aab344c9979e42fd47e1b8c2114e039437f"),
    ("profile_default_initializer", 0x0013F770, 0x0013F902,
     "306f7afd1e6d4d7056820423105854e21f3afaad6cbca8452879c43c4512c276"),
    ("selector_getter", 0x00142380, 0x00142390,
     "d8bf29bd7d956ab22f86aeaad7acdef965bbce2112a3496f572a0757ad759dbe"),
    ("selector_setter", 0x00142390, 0x001423A6,
     "d20d4bf2bc8563d76686b6b175672627b3e45a3ff209398cce30d184f8c01c66"),
    ("profile_pointer_to_index", 0x00191CE0, 0x00191CFC,
     "d6ea7b1090ad46d257c7eda7c40b4d811778c9274d9dd4f43b0b03f39feb6466"),
    ("new_profile_default_call_slice", 0x00191DF6, 0x00191E1E,
     "f356f35f054011417faa5fe678fa24fd0131fe4ad9a6bf750237c89ac7a68fbb"),
    ("celebration_event_handler", 0x0018D6D0, 0x0018D831,
     "038269fc928922d280656baaab2e16fa0a1bbb7fd133857568c65986b42c1595"),
    ("celebration_callback", 0x001ABF30, 0x001AC010,
     "6088236847fd1c01942c26a43bdf474eeaaa2252c5d7a8613477e654d44cbb9c"),
    ("celebration_selector", 0x001B6B50, 0x001B6C45,
     "7a8a6aee666fc177ee58353f56fb8040cd3f2bb9ad4ea6a810f5925eb45d64de"),
    ("celebration_handler_registration", 0x00212A00, 0x00212CAA,
     "bd3b58ed251ebc5df2da7d7cc7cf0ce69c825e37ebd7537b4f08dbb97355f9d5"),
    ("celebration_state_constructor", 0x002DE300, 0x002DE42B,
     "2bf347ef183954193eb7b56122c4abdcfea5c42fb371ce03b3d5344734c26783"),
    ("celebration_playback_mode_resolver", 0x002DE7A0, 0x002DE7F8,
     "87bd7781e3634ad166f19a33360b780087f20b52c4e965e013e5f0e7a6a91f3f"),
    ("celebration_state_construct_dispatch", 0x002DE800, 0x002DE922,
     "1fa6c70b6c3f78e4dc3eb41ea1584b53de6c46695dde0eb4d7f72e57c71c9642"),
    ("celebration_state_dispatch", 0x002DE9C0, 0x002DE9FE,
     "24c4fc66406e14292bfe4dcb859a6d072156a559f1966f5a5a518c59ed9ac3a1"),
    ("selector_row_2", 0x0050CFE0, 0x0050CFEC,
     "c657d61d062fdcd39e866ac4ce6ee99f6c35191392ed4f4c752a8781a7581d65"),
    ("state_callback_table", 0x00AABEF8, 0x00AAC16C,
     "c2d49816fbc3d7bd80b5f63c873eb18a20f6255c971547e2e268280aa64978d1"),
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
            if len(unit) != 2:
                break
            offset += 2
            if unit == b"\0\0":
                return raw.decode("utf-16le")
            raw.extend(unit)
        raise EvidenceError(f"unterminated UTF-16 string at 0x{va:08x}")


def require_phrases(text: str, phrases: tuple[str, ...], label: str) -> None:
    for phrase in phrases:
        if phrase not in text:
            raise EvidenceError(f"{label}: missing exact evidence {phrase!r}")


def dispatch_rows() -> list[dict[str, object]]:
    return [
        {
            "kind": "state_word",
            "input": "0x0000008e",
            "selector_slot": 1,
            "argument_instruction": "0x0018d7ec MOV EDX,0x1",
            "callsite": "0x0018d7f3",
            "proof": "((state-0x33)-1)-0x5a == 0",
        },
        {
            "kind": "state_word",
            "input": "0x00000034",
            "selector_slot": 2,
            "argument_instruction": "0x0018d804 MOV EDX,0x2",
            "callsite": "0x0018d80b",
            "proof": "(state-0x33)-1 == 0",
        },
        {
            "kind": "state_word_default",
            "input": "other accepted state words",
            "selector_slot": 0,
            "argument_instruction": "0x0018d81c XOR EDX,EDX",
            "callsite": "0x0018d820",
            "proof": "neither special comparison matched",
        },
        {
            "kind": "dedicated_handler",
            "input": "vtable field 0x00aac160",
            "selector_slot": 3,
            "argument_instruction": "0x0018d861 MOV EDX,0x3",
            "callsite": "0x0018d868",
            "proof": "direct immediate",
        },
        {
            "kind": "dedicated_handler",
            "input": "vtable field 0x00aac164",
            "selector_slot": 4,
            "argument_instruction": "0x0018d881 MOV EDX,0x4",
            "callsite": "0x0018d888",
            "proof": "direct immediate",
        },
    ]


def playback_mode_rows() -> list[dict[str, object]]:
    return [
        {"record_type": 1, "record_owner": "current actor", "resolver_target": "0x002de7cf", "playback_mode": 1, "additional_gate": "none", "reaches_constructor_0x002de300": True},
        {"record_type": 2, "record_owner": "current actor", "resolver_target": "0x002de7c7", "playback_mode": 14, "additional_gate": "event code from 0x002dddb0 must not equal 2", "reaches_constructor_0x002de300": True},
        {"record_type": 3, "record_owner": "current actor", "resolver_target": "0x002de7b6", "playback_mode": 2, "additional_gate": "event code from 0x002dddb0 must not equal 2", "reaches_constructor_0x002de300": True},
        {"record_type": 4, "record_owner": "current actor", "resolver_target": "0x002de7b6", "playback_mode": 2, "additional_gate": "event code from 0x002dddb0 must not equal 2", "reaches_constructor_0x002de300": True},
        {"record_type": 5, "record_owner": "current actor", "resolver_target": "0x002de7cf", "playback_mode": 1, "additional_gate": "none", "reaches_constructor_0x002de300": True},
    ]


def path_rows() -> list[dict[str, object]]:
    return [
        {"step": 1, "source": "actor event state+0x1c", "target": "state word 0x34",
         "instruction": "0x0018d6e4", "meaning": "0x34 is explicitly admitted by the celebration handler", "confidence": "instruction_exact"},
        {"step": 2, "source": "state word 0x34", "target": "selector slot 2",
         "instruction": "0x0018d7dc..0x0018d80b", "meaning": "branch arithmetic loads EDX=2 and calls 0x002de9c0", "confidence": "instruction_exact"},
        {"step": 3, "source": "0x002de9c0", "target": "0x001b6b50(actor,2)",
         "instruction": "0x002de9d1..0x002de9e8", "meaning": "only celebration callbacks 0x002de170/0x002ddb10 enter selection", "confidence": "instruction_exact"},
        {"step": 4, "source": "new profile creation", "target": "0x0013f770(profile_index)",
         "instruction": "0x00191e0c..0x00191e19", "meaning": "profile creation invokes the default selector initializer", "confidence": "instruction_exact"},
        {"step": 5, "source": "default profile selector slot 2", "target": "selector index 2",
         "instruction": "0x0013f823..0x0013f85d", "meaning": "slots 0..4 initialize to identity values 0..4 at stride 0x3e78", "confidence": "instruction_exact_default_state"},
        {"step": 6, "source": "actor player index", "target": "profile selector table",
         "instruction": "0x001b6b7b..0x001b6bb5", "meaning": "profile pointer maps by 0x1278 stride; null uses profile zero", "confidence": "instruction_exact"},
        {"step": 7, "source": "selector getter(profile,2)", "target": "row index 2",
         "instruction": "0x00142380..0x0014238f", "meaning": "address is 0x00bc8ad0 + (profile*0xf9e+slot)*4", "confidence": "instruction_exact_default_unmodified_profile"},
        {"step": 8, "source": "row index 2", "target": ROW2_NAME,
         "instruction": "0x001b6bd7..0x001b6c31", "meaning": "row left is null, so right name is forced and prefetched under CELEBRATE", "confidence": "instruction_and_data_exact"},
        {"step": 9, "source": "input event code 6", "target": "callback 0x001abf30 -> 0x002de800",
         "instruction": "0x00212ad4/0x00212c14..0x00212c3e and 0x001abfbc", "meaning": "the dispatcher registers the celebration callback, which invokes state construction", "confidence": "instruction_and_switch_table_exact"},
        {"step": 10, "source": "live record type/owner", "target": "state+0xa0 playback mode",
         "instruction": "0x002de7a0..0x002de900 -> 0x002de35c", "meaning": "owner=current and type 1/5 yields mode 1; type 2 yields 14; type 3/4 yields 2", "confidence": "instruction_exact_live_record_type_for_state_0x34_unproved"},
    ]


def build(args: argparse.Namespace) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    xbe = XbeView(args.xbe, args.xbe_header)
    trace = args.trace.read_text(encoding="utf-8")
    pseudo = args.pseudo.read_text(encoding="utf-8")

    ranges = []
    for name, start, end, expected in EXPECTED_RANGES:
        body = xbe.at(start, end - start)
        actual = sha256(body)
        if actual != expected:
            raise EvidenceError(f"{name}: expected {expected}, got {actual}")
        ranges.append({
            "name": name,
            "start": f"0x{start:08x}",
            "end_exclusive": f"0x{end:08x}",
            "size": end - start,
            "file_offset": xbe.file_offset(start, end - start),
            "sha256": actual,
        })

    left, right, opaque = struct.unpack("<III", xbe.at(ROW2_VA, 12))
    if left != 0 or xbe.utf16z(right) != ROW2_NAME or opaque != 21:
        raise EvidenceError("selector row 2 differs")

    callback_entries = []
    for state_word in (0x33, 0x34, 0x8E):
        entry_va = STATE_CALLBACK_TABLE_VA + state_word * 4
        callback_va, = struct.unpack("<I", xbe.at(entry_va, 4))
        if callback_va != CELEBRATION_HANDLER_VA:
            raise EvidenceError(
                f"state callback 0x{state_word:02x}: expected "
                f"0x{CELEBRATION_HANDLER_VA:08x}, got 0x{callback_va:08x}")
        callback_entries.append({
            "state_word": f"0x{state_word:08x}",
            "entry_va": f"0x{entry_va:08x}",
            "callback_va": f"0x{callback_va:08x}",
        })

    require_phrases(trace, (
        "Program MD5: 444064a9ec984dd29d2c05a43f5c96e8",
        "0x0013F82B MOV dword ptr [EAX + 0xbc8ad0],0x0",
        "0x0013F83F MOV dword ptr [EAX + 0xbc8ad8],0x2",
        "0x0013F853 MOV dword ptr [EAX + 0xbc8ae0],0x4",
        "0x00191E19 CALL 0x0013f770",
        "0x0018D6E4 CMP dword ptr [EBP + 0x1c],0x34",
        "0x0018D804 MOV EDX,0x2",
        "0x0018D80B CALL 0x002de9c0",
        "0x002DE35C MOV dword ptr [ESI + 0xa0],ECX",
        "0x00212C1B MOV ECX,0x1abf30",
        "0x001ABFBC CALL 0x002de800",
        "0x002DE7AF JMP dword ptr [ESI*0x4 + 0x2de7e4]",
        "0x002DE8FF PUSH EBX",
        "0x002DE900 CALL 0x002de300",
        "0x001B6BD0 MOV EAX,dword ptr [EAX*0x4 + 0xbe50d0]",
        "0x00AABEF8 length=628 bytes=",
    ), "trace")
    require_phrases(pseudo, (
        "/* 0x0013F770:FUN_0013f770 */",
        "*(undefined4 *)(&DAT_00bc8ad8 + param_1) = 2;",
        "/* 0x00142380:FUN_00142380 */",
        "(param_1 * 0xf9e + param_2) * 4",
        "/* 0x002DE300:FUN_002de300 */",
        "puVar4[0x28] = param_1;",
    ), "pseudo-C")

    dispatch = dispatch_rows()
    modes = playback_mode_rows()
    paths = path_rows()
    report = {
        "schema": "nfl2k5_celebration_selector_producer/v1",
        "result": {
            "selector_index_2_default_producer_proved": True,
            "dispatch_state_word": "0x00000034",
            "selector_slot_argument": 2,
            "default_slot_value": 2,
            "selected_row": 2,
            "selected_name": ROW2_NAME,
            "claim_scope": "newly initialized or otherwise unmodified profile selector table",
            "unconditional_for_all_saved_profiles": False,
        },
        "executable": {
            "path": str(args.xbe),
            "md5": EXPECTED_XBE_MD5,
            "sha256": file_sha256(args.xbe),
            "ranges": ranges,
        },
        "event_dispatch": {
            "handler_start_va": "0x0018d6d0",
            "saved_ghidra_function_boundary_present": False,
            "state_callback_table_base_va": "0x00aabef8",
            "state_callback_table_size_bytes": STATE_CALLBACK_TABLE_SIZE,
            "state_callback_table_index_formula": "base + state_word * 4",
            "state_callback_table_entries": callback_entries,
            "state_word_offset": "0x1c",
            "state_word_0x34_slot_2_callsite": "0x0018d80b",
            "dispatch_rows": dispatch,
            "post_dispatch_state_word_clear_va": "0x0018d812",
        },
        "profile_selection": {
            "player_index_source": "**(actor+0x0c)",
            "player_index_minus_one_rejected": True,
            "profile_pointer_table_base_va": "0x00e5fe98",
            "profile_pointer_stride_bytes": 28,
            "profile_record_base_va": "0x00bdfcf0",
            "profile_record_stride_bytes": 4728,
            "null_profile_pointer_uses_profile_index": 0,
            "selector_table_base_va": "0x00bc8ad0",
            "selector_profile_stride_words": 3998,
            "selector_profile_stride_bytes": 15992,
            "getter_formula": "base + (profile_index * 0x0f9e + selector_slot) * 4",
        },
        "default_initializer": {
            "function_va": "0x0013f770",
            "new_profile_callsite_va": "0x00191e19",
            "slot_values": [0, 1, 2, 3, 4],
            "slot_2_is_selector_index_2": True,
            "setter_function_va": "0x00142390",
            "setter_saved_direct_callers": 0,
            "immutability_claimed": False,
        },
        "selector_row_2": {
            "va": f"0x{ROW2_VA:08x}",
            "file_offset": xbe.file_offset(ROW2_VA, 12),
            "left_pointer": 0,
            "right_pointer": f"0x{right:08x}",
            "right_name": ROW2_NAME,
            "opaque_s32": struct.unpack("<i", struct.pack("<I", opaque))[0],
            "forced_right_because_left_is_null": True,
        },
        "playback_mode_producer": {
            "registration_input_event_code": 6,
            "registered_callback_va": "0x001abf30",
            "callback_state_dispatch_callsite_va": "0x001abfbc",
            "state_construct_dispatch_va": "0x002de800",
            "mode_resolver_va": "0x002de7a0",
            "mode_resolver_jump_table_va": "0x002de7e4",
            "direct_constructor_callsite_va": "0x002de900",
            "indirect_caller_recovered": True,
            "record_owner_must_equal_current_actor_for_0x002de300": True,
            "mode_one_record_types": [1, 5],
            "mode_rows": modes,
            "concrete_record_type_for_state_word_0x34_proved": False,
        },
        "state_constructor_followup": {
            "function_va": "0x002de300",
            "callback_written": "0x002de170",
            "state_plus_a0_source": "first stack argument from EBX at direct caller 0x002de900; stored at 0x002de35c",
            "concrete_argument_for_state_word_0x34_proved": False,
            "why_it_matters": "0x002ddb10 later passes state+0xa0 as playback mode to 0x001b7460",
        },
        "portme": [
            "// PORTME(0x002DE7A0): prove that the live record accompanying the state-word 0x34 path is owned by the actor and has type 1 or 5, making state+0xA0 equal 1.",
            "// PORTME(0x00142390): identify any serialized-profile load or indirect mutation of selector slots before claiming row 2 for every saved profile.",
        ],
        "source_pins": {
            "xbe_header": {"path": str(args.xbe_header), "sha256": file_sha256(args.xbe_header)},
            "ghidra_trace": {"path": str(args.trace), "sha256": file_sha256(args.trace)},
            "ghidra_pseudo_c": {"path": str(args.pseudo), "sha256": file_sha256(args.pseudo)},
            "ghidra_script": {"path": str(args.ghidra_script), "sha256": file_sha256(args.ghidra_script)},
        },
    }
    return report, dispatch, modes, paths


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
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--pseudo", required=True, type=Path)
    parser.add_argument("--ghidra-script", default=Path("tools/ghidra_scripts/NflCelebrationSelectorProducerTrace.java"), type=Path)
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--dispatch-tsv", required=True, type=Path)
    parser.add_argument("--mode-tsv", required=True, type=Path)
    parser.add_argument("--path-tsv", required=True, type=Path)
    args = parser.parse_args()
    report, dispatch, modes, paths = build(args)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_tsv(args.dispatch_tsv, dispatch)
    write_tsv(args.mode_tsv, modes)
    write_tsv(args.path_tsv, paths)
    print("NFL_CELEBRATION_SELECTOR_PRODUCER_COMPLETE state=0x34 slot=2 default_index=2 rows=5 modes=5 path_steps=10")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
