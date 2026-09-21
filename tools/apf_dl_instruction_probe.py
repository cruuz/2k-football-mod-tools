"""Read-only b75-a1 DL research. Owned inputs stay outside the repository.

Run with python -m tools.apf_dl_instruction_probe --help. Native results are
bounded function proofs, not a match simulation or a witnessed Xenia result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from mod_editor.core.apf2k8_play_codec import (
    Book, MASTER_SHA256, PLAY_BASE, PLAY_SIZE, NODE_BASE,
)
from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body
from tools.apf_playcall_research_probe import (
    Machine, MASTER, MANAGER, STATE, TEAM, GAME, HISTORY, OUTPUT,
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def defensive_snapshot(master):
    """Hash descriptors and resolved chains, catching edits to shared nodes."""
    book = Book.from_bytes(master)
    plays = {}
    for pi, play in enumerate(book.plays):
        if play.type_nibble != 1:
            continue
        slots = []
        for si, assignment in enumerate(play.assignments):
            chain = b"".join(node.to_bytes() for node in book.chain(pi, si))
            slots.append({
                "slot": si, "owned": bool(assignment.descriptor & 0x800),
                "descriptor": f"{assignment.descriptor:08x}",
                "chain_sha256": sha(chain),
            })
        plays[str(pi)] = {"name": book.play_name(pi), "slots": slots,
                          "record_sha256": sha(play.to_bytes())}
    return {"master_sha256": sha(master), "plays": plays}


def compare_masters(before, after):
    a, b = defensive_snapshot(before), defensive_snapshot(after)
    changed = []
    for pi in sorted(a["plays"].keys() | b["plays"].keys(), key=int):
        if a["plays"].get(pi) != b["plays"].get(pi):
            changed.append({"play": int(pi), "before": a["plays"].get(pi),
                            "after": b["plays"].get(pi)})
    return {"before_master_sha256": a["master_sha256"],
            "after_master_sha256": b["master_sha256"],
            "defensive_play_count": len(a["plays"]), "changed": changed}


def defensive_books(index):
    from mod_editor.core.apf2k8_book_identity import (
        read_disc_roster, parse_roster_identity, read_resource, filename_id,
    )
    import apf_outer
    identity = parse_roster_identity(read_disc_roster(index))
    names = sorted({label.kind for label in identity.labels if label.side == "defense"}
                   | {"USER-d", "global-d"})
    available = {e.name_id for e in apf_outer.parse_archive(index).entries}
    return {name: sha(read_resource(index, filename_id(name), "spb", "SPLB")[3])
            if filename_id(name) in available else None for name in names}


class DLMachine(Machine):
    def va(self, address):
        if self.updated and 0x847F6000 <= address < 0x84801000:
            return address + 0xCA0
        return super().va(address)


def native_proof(image, master, patch_words=()):
    if sha(master) != MASTER_SHA256:
        raise ValueError("Native retail proof requires the pinned retail MASTER")
    book = Book.from_bytes(master)
    m = DLMachine(image, master)
    patch_words = tuple(patch_words)
    if patch_words:
        patched = bytearray(image)
        for address, word in patch_words:
            struct.pack_into(">I", patched, address - 0x82000000, word)
            m.put(address, word)
        m.image = bytes(patched)
    m.configure()
    # Only assignment-pointer relocation is needed by these leaf calls. This
    # explicit fixture setup does not claim to execute the MASTER initializer.
    for pi, play in enumerate(book.plays):
        for si, a in enumerate(play.assignments):
            field = PLAY_BASE + pi * PLAY_SIZE + 16 + si * 8
            m.put(MASTER + field, MASTER + NODE_BASE + a.start(field) * 8)
    runtime = 0x390000
    def assignment(pi, si):
        return MASTER + PLAY_BASE + pi * PLAY_SIZE + 12 + si * 8

    # Retail coverage partners own slots 4..10; a full front in the second
    # component instead owns 0..3 and must win there. No selector is stubbed.
    pairs = []
    ownership_checks = 0
    for second, play in enumerate(book.plays):
        if play.type_nibble != 1:
            continue
        for si in range(4):
            take_second = m.call(m.va(0x848006F8), assignment(277, si), assignment(second, si))
            expected = second != 277 and bool(play.assignments[si].descriptor & 0x800)
            assert take_second == expected, (second, si, take_second)
            ownership_checks += 1
    for second in (278, 283, 288, 289):
        chosen = []
        for si in range(11):
            take_second = m.call(m.va(0x848006F8), assignment(277, si), assignment(second, si))
            expected = si >= 4 if second in (278, 283) else True
            assert take_second == expected, (second, si, take_second)
            chosen.append(second if take_second else 277)
        pairs.append({"first": 277, "second": second, "selected_by_slot": chosen})

    reads = []
    for pi in (277, 284, 285, 288, 289):
        for mirror in (False, True):
            modes, lanes = [], []
            for si in range(4):
                m.cpu.mem_write(runtime, bytes(0x80))
                m.put(runtime, assignment(pi, si))
                m.put(runtime + 4, 0x100 if mirror else 0)
                m.call(m.va(0x8482DA88), runtime, 0xFFFFFFFF)
                node = next(n for n in book.chain(pi, si) if n.op == 0x0B)
                values = []
                for operand in (0, 1):
                    assert m.call(m.va(0x8482DCA0), runtime, 0x0B, operand, OUTPUT) == 1
                    values.append(m.get(OUTPUT))
                mode, lane = node.operands[:2]
                expected_lane = 16 - lane if mirror and lane != 17 else lane
                assert values == [mode, expected_lane], (pi, si, mirror, values)
                modes.append(values[0]); lanes.append(values[1])
            reads.append({"play": pi, "name": book.play_name(pi), "mirror": mirror,
                          "modes": modes, "lanes": lanes})

    # Resolve a CPU defender's lane from his real assignment. The formation
    # position provider is an explicit boundary; nearest-lane search, input
    # control check and lane arithmetic execute natively.
    callsite = m.va(0x847F72D0)
    word = m.get(callsite)
    displacement = word & 0x03FFFFFC
    if displacement & 0x02000000:
        displacement -= 0x04000000
    position_provider = callsite + displacement
    player, control, physics = 0x3A0000, 0x3A1000, 0x3A2000
    m.put(player + 0x10, control)
    m.put(player + 0x1C, physics)
    m.put(player + 0x28, runtime - 0x804)
    m.put(control, 0xFFFFFFFF)
    def position(z):
        z.cpu.mem_write(z.reg(4), bytes(16))
        z.ret(z.reg(4))
    m.boundaries[position_provider] = position
    cpu_lanes = []
    for pi in (277, 285, 288, 289):
        for x in (-152.4, 0.0, 152.4):
            lanes = []
            for si in range(4):
                m.cpu.mem_write(runtime, bytes(0x80))
                m.put(runtime, assignment(pi, si))
                m.call(m.va(0x8482DA88), runtime, 0xFFFFFFFF)
                m.putf(physics + 0x30, x)
                assert m.call(m.va(0x847F7208), player, OUTPUT) == 1
                lane = m.get(OUTPUT)
                original = next(n for n in book.chain(pi, si) if n.op == 0x0B).operands[1]
                shift = -2 if x < 0 else 2 if x > 0 else 0
                assert lane == max(0, min(16, original + shift)), (pi, si, x, lane)
                lanes.append(lane)
            cpu_lanes.append({"play": pi, "design_x_input": 0.0,
                              "actual_x_input": x, "lanes": lanes})
    del m.boundaries[position_provider]

    # Exercise the native CPU-team guards with an otherwise eligible phase.
    delta = 0x30 if m.updated else 0
    m.put(GAME + delta + 4, MANAGER)
    m.put(MANAGER + 0xC, TEAM)
    m.put(MANAGER + 0x38, 1)
    m.put(MANAGER + 0x40, 0)
    m.put(GAME + delta + 0x38, 12)
    m.put(HISTORY + delta + 0x640, 0x80000000)
    m.put(TEAM + 0xC4, 5)
    guards = []
    for entry in (0x848667D8, 0x848668C8, 0x84867EF0):
        m.call(m.va(entry))
        assert m.get(TEAM + 0xC4) == 5
        assert m.va(0x8485A7D0) not in m.visited
        guards.append(f"{m.va(entry):08x}")

    # The classifier and RNG are explicit inputs at callee boundaries. The
    # table lookup, floating arithmetic, field-position gate and return run
    # natively. These class IDs have not been given gameplay labels.
    m.put(STATE + 0x18, 0)
    distributions = []
    class_address = m.va(0x8485A4C8)
    for kind in range(6):
        m.boundaries[class_address] = lambda z, k=kind: z.ret(k)
        for strength in range(3):
            counts = [0] * 6
            for sample in range(100):
                m.random_boundaries((sample + .5) / 100, delta=0xFD0 if m.updated else 0)
                result = m.call(m.va(0x8485A7D0), strength)
                assert 0 <= result < 6
                counts[result] += 1
            distributions.append({"class_input": kind, "strength_input": strength,
                                  "counts_100": counts})
    del m.boundaries[class_address]
    return {"image_sha256": sha(image), "executed_image_sha256": sha(m.image),
            "installed_patch_word_count": len(patch_words), "master_sha256": sha(master),
            "profile": "TU 1.1" if m.updated else "BASE", "pairs": pairs,
            "front_ownership_checks": ownership_checks,
            "operand_reads": reads, "human_team_guard_entries": guards,
            "cpu_lane_resolutions": cpu_lanes,
            "position_provider_boundary": f"{position_provider:08x}",
            "shift_distributions": distributions,
            "adapted_pcs": [f"{pc:08x}" for pc in sorted(m.adapted)],
            "limits": ["Explicit relocation and minimal synthetic match state",
                       "Shift classifier, RNG and design position are supplied boundaries",
                       "No full player update, Xenia frame or tester-folder reproduction"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retail-index", type=Path, required=True)
    parser.add_argument("--built-index", type=Path)
    parser.add_argument("--pe", type=Path, help="Pinned BASE or TU flat image for native proof")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    master = read_master_play_body(args.retail_index)
    result = {"snapshot": defensive_snapshot(master)}
    if args.built_index:
        result["comparison"] = compare_masters(master, read_master_play_body(args.built_index))
        before, after = defensive_books(args.retail_index), defensive_books(args.built_index)
        result["defensive_books"] = {"before": before, "after": after,
                                     "changed": [n for n in sorted(before.keys() | after.keys())
                                                 if before.get(n) != after.get(n)]}
    if args.pe:
        result["native"] = native_proof(args.pe.read_bytes(), master)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
