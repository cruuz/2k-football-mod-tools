"""Read-only, bounded APF d4 assignment and defensive-shell witnesses.

Uses owned pinned BASE/TU flat images and MASTER; emits derived JSON only.
The initializer stops immediately after the real selected-pointer store. Two
unrelated player reset/classification callees have explicit supplied results.
The shell sweep deliberately admits every role at its eligibility boundary,
so its later FS/SS/CB-only gate cannot be attributed to that boundary.
Neither probe simulates a frame or establishes the tester's failing state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from mod_editor.core.apf2k8_play_codec import (
    Book, FORMATION_BASE, FORMATION_SIZE, MASTER_SHA256, NODE_BASE,
    PLAY_BASE, PLAY_SIZE,
)
from mod_editor.core.apf2k8_playcall_patch import IMAGE_BASE, check_image
from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body
from tools.apf_dl_instruction_probe import DLMachine
from tools.apf_playcall_research_probe import GAME, MANAGER, MASTER, OUTPUT, TEAM

SCHEMA = "apf_d4_dl_runtime/v1"
PLAYER, PLAYER_STATE, ACTION_STATE = 0x3A0000, 0x3A1000, 0x3A2000
PHYSICS, CONTROL = 0x3A3000, 0x3A4000
RUNTIME = PLAYER_STATE + 0x804
SHELL_ROLE_TABLE = 0x84DBB218
SHELL_MESSAGES = 0x84DBBB10
MANUAL_SHELL = {"base": 0x84884C40, "tu_1_1": 0x84885A88}
ROLE_NAMES = {12: "DE", 13: "DT", 14: "ILB", 15: "OLB", 16: "FS", 17: "SS", 18: "CB"}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def branch_target(image, address):
    """Decode a direct relative/absolute PPC branch without guessing a TU delta."""
    word = struct.unpack_from(">I", image, address - IMAGE_BASE)[0]
    if word >> 26 != 18:
        raise ValueError(f"Expected a direct branch at {address:08X}")
    displacement = word & 0x03FFFFFC
    if displacement & 0x02000000:
        displacement -= 0x04000000
    return (displacement if word & 2 else address + displacement) & 0xFFFFFFFF


def shell_metadata(image):
    profile = check_image(image)
    pointers = struct.unpack_from(">12I", image, SHELL_MESSAGES - IMAGE_BASE)
    names = []
    for pointer in pointers:
        if not pointer:
            names.append(None)
            continue
        tail = image[pointer - IMAGE_BASE:pointer - IMAGE_BASE + 120]
        names.append(tail.decode("utf-16-be").split("\0", 1)[0])
    # These are native shell alignment variant IDs, never Base/Gap play IDs.
    values = struct.unpack_from(">36I", image, SHELL_ROLE_TABLE - IMAGE_BASE)
    return {
        "profile": profile.name,
        "image_sha256": sha256(image),
        "writer": f"{0x8485EF28 + (0xCA0 if profile.name == 'tu_1_1' else 0):08x}",
        "manual_handler": f"{MANUAL_SHELL[profile.name]:08x}",
        "role_table": f"{SHELL_ROLE_TABLE:08x}",
        "role_table_sha256": sha256(image[SHELL_ROLE_TABLE - IMAGE_BASE:SHELL_ROLE_TABLE - IMAGE_BASE + 144]),
        "message_table": f"{SHELL_MESSAGES:08x}",
        "messages_by_call_flag_bank": [names[:6], names[6:]],
        "alignment_variants_by_call_flag_bank": [
            [list(values[bank * 18 + selector * 3:bank * 18 + selector * 3 + 3])
             for selector in range(6)] for bank in range(2)
        ],
        "alignment_variant_role_order": ["CB", "FS", "SS"],
    }


def _machine(image, master, patch_words):
    if sha256(master) != MASTER_SHA256:
        raise ValueError("Expected the pinned retail MASTER; use archive comparison for custom inputs")
    book = Book.from_bytes(master)
    machine = DLMachine(image, master)
    patch_words = tuple(patch_words)
    patched = bytearray(image)
    for address, word in patch_words:
        if address % 4 or not IMAGE_BASE <= address <= IMAGE_BASE + len(image) - 4:
            raise ValueError("Patch word outside the flat image")
        struct.pack_into(">I", patched, address - IMAGE_BASE, word)
        machine.put(address, word)
    machine.image = bytes(patched)
    machine.configure()
    for pi, play in enumerate(book.plays):
        for si, assignment in enumerate(play.assignments):
            field = PLAY_BASE + pi * PLAY_SIZE + 16 + si * 8
            machine.put(MASTER + field, MASTER + NODE_BASE + assignment.start(field) * 8)
    for fi, formation in enumerate(book.formations):
        field = FORMATION_BASE + fi * FORMATION_SIZE
        machine.put(MASTER + field, MASTER + field - 1 + formation.name_pointer)
    delta = 0x30 if machine.updated else 0
    for address, value in (
        (GAME + delta + 4, MANAGER), (MANAGER + 0xC, TEAM),
        (MANAGER + 4, PLAYER), (MANAGER + 0x38, 1),
        (TEAM + 8, MASTER + FORMATION_BASE + 141 * FORMATION_SIZE),
        (PLAYER + 0x28, PLAYER_STATE), (PLAYER + 0x14, ACTION_STATE),
        (PLAYER + 0x40, MANAGER),
        (PLAYER + 0x1C, PHYSICS), (PLAYER + 0x10, CONTROL), (CONTROL, 0xFFFFFFFF),
    ):
        machine.put(address, value)
    return machine, book


def native_runtime_proof(image, master, patch_words=()):
    metadata = shell_metadata(image)
    patch_words = tuple(patch_words)
    machine, book = _machine(image, master, patch_words)
    writes = []
    def observe_write(cpu, access, address, size, value, data):
        if address in (RUNTIME, RUNTIME + 4, TEAM + 0xC4):
            writes.append({"pc": f"{cpu.reg_read(machine.r.UC_PPC_REG_PC):08x}",
                           "address": f"{address:08x}", "size": size,
                           "value": f"{value:08x}"})
    machine.cpu.hook_add(machine.u.UC_HOOK_MEM_WRITE, observe_write)
    # The first only supplies the unrelated optional player-status result;
    # the second resets a separate state object. Pointer selection is native.
    status = branch_target(image, machine.va(0x8480085C))
    reset = branch_target(image, machine.va(0x84800870))
    machine.boundaries[status] = lambda z: z.ret(0)
    machine.boundaries[reset] = lambda z: z.ret(0)
    # Follow native calls to the unshifted formation coordinate leaf; these
    # families have differing TU deltas, so none is extrapolated here.
    position_provider = branch_target(image, machine.va(0x847F72D0))
    formation_provider = branch_target(image, position_provider + 0x88)
    relative_provider = branch_target(image, formation_provider + 0x88)
    coordinate_leaf = branch_target(image, relative_provider + 0x2C)
    initializer = []
    initial_master = bytes(machine.cpu.mem_read(MASTER, len(master)))
    for second in (278, 283, 288, 289):
        for flags in (0, 4, 0x1004):
            rows = []
            for slot in range(11):
                writes.clear()
                machine.cpu.mem_write(PLAYER_STATE, bytes(0xB00))
                machine.cpu.mem_write(PLAYER + 0x34, bytes((12, 12, slot)))
                machine.put(TEAM + 0x2C, flags)
                machine.put(TEAM + 0x10, MASTER + PLAY_BASE + 277 * PLAY_SIZE)
                machine.put(TEAM + 0x14, MASTER + PLAY_BASE + second * PLAY_SIZE)
                machine.call(machine.va(0x84800798), MANAGER, 0, 0, 0,
                             stop=machine.va(0x848000AC))
                pointer = machine.get(RUNTIME)
                play, remainder = divmod(pointer - MASTER - PLAY_BASE - 12, PLAY_SIZE)
                selected_slot, remainder = divmod(remainder, 8)
                if remainder or play not in (277, second) or not 0 <= selected_slot < 11:
                    raise AssertionError("Initializer stored an unexpected assignment pointer")
                if slot < 4 and second in (278, 283) and play != 277:
                    raise AssertionError("Coverage partner replaced the owned Base front")
                if slot < 4 and second in (288, 289) and play != second:
                    raise AssertionError("Owned second front lost native priority")
                # Call flag 4 enables the native per-assignment slot remap.
                # Sentinel B means the formation's
                # paired slot, then sentinel B there means keep the input slot.
                expected_slot = slot
                if flags & 4:
                    chosen = second if book.plays[second].assignments[slot].descriptor & 0x800 else 277
                    expected_slot = (book.plays[chosen].assignments[slot].descriptor >> 12) & 15
                    if expected_slot == 11:
                        expected_slot = master[FORMATION_BASE + 141 * FORMATION_SIZE + 0x1F + slot * 14] >> 4
                    if expected_slot == 11:
                        expected_slot = slot
                if selected_slot != expected_slot:
                    raise AssertionError(f"Unexpected remap: flags={flags:x}, play={second}, slot={slot}, selected={selected_slot}, expected={expected_slot}")
                if not any(w["pc"] == f"{machine.va(0x848000A0):08x}" for w in writes):
                    raise AssertionError("Actual pointer store was not observed")
                store_writes = list(writes)
                machine.call(machine.va(0x8482DA88), RUNTIME, 0xFFFFFFFF)
                operands = []
                for operand in (0, 1):
                    if machine.call(machine.va(0x8482DCA0), RUNTIME, 0x0B, operand, OUTPUT):
                        operands.append(machine.get(OUTPUT))
                    else:
                        operands.append(None)
                cpu_lanes = []
                if slot < 4:
                    machine.call(coordinate_leaf,
                                 MASTER + FORMATION_BASE + 141 * FORMATION_SIZE,
                                 slot, 0, OUTPUT, int(bool(flags & 4)))
                    design_vector = bytes(machine.cpu.mem_read(OUTPUT, 16))
                    design_x = struct.unpack_from(">f", design_vector)[0]
                    def supplied_design(z, vector=design_vector):
                        z.cpu.mem_write(z.reg(4), vector)
                        z.ret(z.reg(4))
                    machine.boundaries[position_provider] = supplied_design
                    for displacement in (-152.4, 0.0, 152.4):
                        actual_x = design_x + displacement
                        machine.putf(PHYSICS + 0x30, actual_x)
                        result = machine.call(machine.va(0x847F7208), PLAYER, OUTPUT)
                        if result != 1 or not 0 <= machine.get(OUTPUT) <= 16:
                            raise AssertionError("Native CPU rush resolver returned an invalid lane")
                        cpu_lanes.append({"design_x_from_native_formation_leaf": design_x,
                                          "actual_x_input": actual_x,
                                          "displacement_input": displacement,
                                          "resolved_lane": machine.get(OUTPUT)})
                    del machine.boundaries[position_provider]
                rows.append({"input_slot": slot, "selected_play": play,
                             "selected_slot": selected_slot,
                             "selected_assignment": f"{pointer:08x}",
                             "descriptor": f"{book.plays[play].assignments[selected_slot].descriptor:08x}",
                             "mode_lane": operands, "cpu_lane_cases": cpu_lanes,
                             "pointer_store_trace": store_writes})
            initializer.append({"first_play": 277, "second_play": second,
                                "call_flags": f"{flags:08x}", "slots": rows})
    if bytes(machine.cpu.mem_read(MASTER, len(master))) != initial_master:
        raise AssertionError("Native initializer/operand calls mutated relocated MASTER")
    del machine.boundaries[status]
    del machine.boundaries[reset]

    # Force eligibility false (0 means do not skip) before the *native* role
    # gate; movement refresh is recorded without executing a full frame.
    eligibility = machine.va(0x849283C8)
    refresh = branch_target(image, machine.va(0x8485F0B8))
    machine.boundaries[eligibility] = lambda z: z.ret(0)
    refresh_roles = []
    machine.boundaries[refresh] = lambda z: (refresh_roles.append(z.reg(3)), z.ret(0))
    pointer = MASTER + PLAY_BASE + 277 * PLAY_SIZE + 12
    shell = []
    for flags in (0, 0x1000):
        for selector in range(6):
            for role, role_name in ROLE_NAMES.items():
                machine.cpu.mem_write(PLAYER + 0x34, bytes((role,)))
                machine.put(TEAM + 0x2C, flags)
                machine.put(TEAM + 0xC4, 0xFFFFFFFF)
                machine.put(RUNTIME, pointer)
                machine.put(RUNTIME + 4, 0xA500013F)
                writes.clear(); refresh_roles.clear()
                machine.call(machine.va(0x8485EF28), selector)
                expected_variant = metadata["alignment_variants_by_call_flag_bank"][bool(flags)][selector][
                    {18: 0, 16: 1, 17: 2}.get(role, 0)]
                expected_flags = ((0xA500013F & ~0xC0) | expected_variant << 6
                                  if role >= 16 else 0xA500013F)
                if machine.get(RUNTIME) != pointer or machine.get(RUNTIME + 4) != expected_flags:
                    raise AssertionError(f"Unexpected shell write for role {role}")
                if bool(refresh_roles) != (role >= 16):
                    raise AssertionError("Unexpected shell refresh role")
                if machine.get(TEAM + 0xC4) != selector:
                    raise AssertionError("Shell selector not stored")
                shell.append({"call_flags": f"{flags:08x}", "selector": selector,
                              "role": role_name, "role_id": role,
                              "runtime_flags_before": "a500013f",
                              "runtime_flags_after": f"{machine.get(RUNTIME + 4):08x}",
                              "assignment_preserved": True,
                              "refresh_requested": bool(refresh_roles), "writes": list(writes)})
    return {
        "schema": SCHEMA, "classification": "PROVED BOUNDED OFFLINE",
        "gameplay_status": "UNWITNESSED", "metadata": metadata,
        "executed_image_sha256": sha256(machine.image),
        "installed_patch_word_count": len(patch_words),
        "master_sha256": sha256(master), "initializer_cases": initializer,
        "initializer_slot_checks": sum(len(row["slots"]) for row in initializer),
        "cpu_lane_checks": sum(len(slot["cpu_lane_cases"]) for row in initializer for slot in row["slots"]),
        "shell_role_cases": shell, "shell_role_checks": len(shell),
        "base_front_defense_start_displacements": [
            list(next(node for node in book.chain(277, slot) if node.op == 0x1B).operands[2:4])
            for slot in range(4)
        ],
        "boundaries": {"optional_player_status": f"{status:08x}",
                       "separate_player_state_reset": f"{reset:08x}",
                       "design_provider_supplied_from_native_unshifted_formation_leaf": f"{position_provider:08x}",
                       "native_formation_coordinate_leaf": f"{coordinate_leaf:08x}",
                       "shell_eligibility_forced_to_admit_all_roles": f"{eligibility:08x}",
                       "shell_movement_refresh_recorded_only": f"{refresh:08x}"},
        "adapted_pcs": [f"{address:08x}" for address in sorted(machine.adapted)],
        "limits": ["Explicit MASTER pointer relocation and synthetic one-player list",
                   "Initializer ends after native pointer store; subsequent action setup excluded",
                   "Rush design vector supplied from native formation leaf; full provider world transforms excluded",
                   "No team-control lifecycle, full alignment update, frame, or tester-folder reproduction"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pe", type=Path, required=True)
    parser.add_argument("--retail-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = native_runtime_proof(args.pe.read_bytes(), read_master_play_body(args.retail_index))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(f"{result['metadata']['profile']}: {result['initializer_slot_checks']} initializer slots, "
          f"{result['shell_role_checks']} shell role cases; gameplay UNWITNESSED")


if __name__ == "__main__":
    main()
