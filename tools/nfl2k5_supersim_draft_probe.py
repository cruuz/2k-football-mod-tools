"""Read-only, bounded retail instruction evidence; no game boot or save writer.

python3 -m tools.nfl2k5_supersim_draft_probe --output receipt.json
The optional --prior-year probe is slow. It runs real fixture/stat/season code
with per-call instruction caps and records every completed week/stage. It does
not simulate a Senior Bowl launch, input, renderer, save or console timing.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import struct
import sys

from mod_editor.core import nfl2k5_draft_start as draft
from mod_editor.core import nfl2k5_draft_ai as ai
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_senior_bowl as bowl
from mod_editor.core import nfl2k5_supersim as sim
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
from tests.nfl2k5_supersim_draft_fixture import (
    Machine, retail_bytes, retail_roster, signed_save, sim_machine, read_sim,
)

PIN_SPANS = {
    "pause_simulate_row": (0x4E8D08, 52),
    "pause_simulate_handler": (0x6EFE0, 0x70),
    "pause_finish_sequence": (0x6EE50, 0x60),
    "visual_simulator_controls": (0xEC390, 0x2E0),
    "visual_simulator_speed": (0x27B820, 0xC0),
    "play_callback_table": (0xA96930, 19*4),
    "play_step": (0x10B250, 0x30),
    "sim_initializer": (0x10B280, 0x6C0),
    "sim_wrappers": (0x10B940, 0xB0),
    "terminal_finalizer": (0x1053B0, 0x39),
    "scenario_restore": (0x10BD80, 0x284),
    "inner_game_update": (0x11A7C0, 0x130),
    "outer_game_update": (0x64CD0, 0x550),
    "franchise_start": (0x13EE10, 0x240),
    "stage_table": (0x515140, 10*16),
    "year_rollover": (0x247B40, 0x1C2),
    "advance_stage": (0x2480B0, 0x600),
    "draft_class_generator": (0x2BE900, 0x4B),
    "match_roster_clone": (0x61730, 0xAB),
    "generic_uniform_names": (0x615A0, 0x164),
    "draft_on_clock": (0x3254D0, 0x20),
    "draft_cpu_pick_and_sign": (0x325B50, 0x1AE),
    "played_fixture_commit": (0xC5D60, 0x4F),
}


def audit(payload):
    if hashlib.sha256(payload).hexdigest() != RETAIL_SHA256:
        raise ValueError("audit requires the pinned retail executable")
    image = XbeImage(payload)
    spans = {name: {"va": hex(va), "size": size,
                    "sha256": hashlib.sha256(image.read(va, size)).hexdigest()}
             for name, (va, size) in PIN_SPANS.items()}
    row = struct.unpack("<13I", image.read(0x4E8D08, 52))
    return {"retail_xbe_sha256": RETAIL_SHA256, "spans": spans,
            "pause_row": {"kind": row[0], "text": hex(row[1]), "action": hex(row[10])},
            "pause_text": image.read(row[1], 32).decode("utf-16-le").rstrip("\0"),
            "callback_table": [hex(n) for n in struct.unpack("<19I", image.read(0xA96930, 76))]}


def stop_proof(payload):
    results = {}
    for target in sim.StopAt:
        m = sim_machine(payload)
        start = read_sim(m)
        run = sim.advance(lambda: m.call(sim.STEP, budget=1000000), lambda: read_sim(m),
                          until=target, target_side=1-start.offense)
        results[target.value] = asdict(run)
    return results


def projection_proof(payload):
    document = rr.RosterDocument(signed_save(), base=rr.SAVE_BLOCK_OFFSET)
    players = bowl.prospects_from_document(document)
    reservation = draft.reserve(players, year=0, franchise_id=b"draft-start-test",
                                position=0)
    document, reservation, receipt = draft.inject(
        document, reservation, draft.Creation("Noah", "Rookie", 0, 1),
        year=0, franchise_id=reservation.franchise_id)
    m = Machine(payload, trace_writes=False)
    m.load_franchise(document.to_body())
    m.seed(12345)
    m.put(0xE5FF80, 0)  # Exhibition context; no franchise result commit is called.
    m.put(0xE6000C, 5)
    m.put(0xE60010, 5)
    template = bytes(m.uc.mem_read(m.team_base+51*500, 500))
    squads = draft.squads_for(bowl.prospects_from_document(document), reservation)
    native_squads = tuple(squads[side] for side in draft.NATIVE_TO_EVENT_SIDES)
    donors = (m.ARENA+0x100000, m.ARENA+0x100000+500)
    primary = m.get(m.root+4)
    for address, indices in zip(donors, native_squads):
        m.uc.mem_write(address, draft.project_native_team(
            template, indices, primary_base=primary, primary_count=m.get(m.root)))
    before = bytes(m.uc.mem_read(m.ARENA, len(document.body)))
    # Prohibit even temporary writes to every byte of the source franchise.
    m.uc.mem_protect(m.ARENA, (len(document.body)+4095) & ~4095, m.u.UC_PROT_READ)
    m.call(draft.CLONE_TEAMS, ecx=donors[0], edx=donors[1])
    aliases = []
    cloned = []
    for side, indices in enumerate(native_squads):
        pool = 0xB30C4C + side*65*84
        for slot, index in enumerate(indices):
            source = primary+index*84
            target = pool+slot*84
            original = bytearray(m.uc.mem_read(source, 84))
            original[0x34] = side+1
            cloned.append(bytes(m.uc.mem_read(target, 84)) == original)
            aliases.append(m.get(target+0x30) == m.get(source+0x30))
    m.call(0x77AE0, ecx=donors[0])
    m.call(0x77B20, ecx=donors[1])
    m.call(sim.INIT, ecx=donors[0], edx=donors[1], args=(0, 1, 0, 0, 0, 0), budget=3000000)
    personnel = []
    rebound = []
    for side, indices in enumerate(native_squads):
        pool = 0xB30C4C + side*65*84
        allowed = {pool+i*84 for i in range(53)}
        personnel.append(all(m.get(0xA96B70+side*0x318+i*4) in allowed for i in range(33)))
        rebound.extend(m.get(pool+slot*84+0x30) != m.get(primary+index*84+0x30)
                       for slot, index in enumerate(indices))
    m.call(0x615A0, budget=100000)
    kits = [bytes(m.uc.mem_read(va, 32)).decode("utf-16-le").split("\0")[0]
            for va in (0xB30710, 0xB30730)]
    m.call(sim.STEP, budget=1000000)
    run = sim.advance(lambda: m.call(sim.STEP, budget=1000000), lambda: read_sim(m),
                      until=sim.StopAt.END_OF_HALF)
    second_half = sim.advance(lambda: m.call(sim.STEP, budget=1000000), lambda: read_sim(m),
                              until=sim.StopAt.END_OF_HALF)
    finish = second_half
    if finish.reason == "target" and finish.final.quarter >= 4:
        finish = sim.advance(lambda: m.call(sim.STEP, budget=1000000), lambda: read_sim(m),
                             until=sim.StopAt.END_OF_HALF)
    if finish.reason != "game_end":
        raise AssertionError("prospect simulator did not finish within the bounded second half")
    m.call(sim.FINALIZE, ecx=5, budget=3000000)
    after = bytes(m.uc.mem_read(m.ARENA, len(document.body)))
    return {"creation": receipt, "squads": squads, "native_to_event_sides": draft.NATIVE_TO_EVENT_SIDES,
            "cloned_records": sum(cloned),
            "initial_history_aliases": sum(aliases), "stat_pointer_rebindings": sum(rebound),
            "all_33_personnel_from_each_squad": personnel, "kits": kits,
            "stop": asdict(run), "second_half": asdict(second_half), "finish": asdict(finish),
            "source_arena_read_only": True,
            "source_arena_sha256_before": hashlib.sha256(before).hexdigest(),
            "source_arena_sha256_after": hashlib.sha256(after).hexdigest(), "leaves": m.leaves}


def draft_proof(payload):
    patched = ai.apply(payload)[0]
    m = Machine(patched, trace_writes=False)
    m.load_franchise(signed_save())
    m.put(0xE576A4, 5)
    m.put(0xE3C0A8, 0)
    m.put(0xE3C0A4, 0)
    # The installed AI consults the actual 32 clubs, actual class and PRNG.
    # This samples candidate selection at a fixed on-clock slot, not 32 drafts.
    choices = {}
    for seed in range(1, 33):
        m.seed(seed)
        p = m.call(0x31E0F0, ecx=m.team_base, edx=1, budget=3000000)
        choices[str(seed)] = (p-m.get(m.root+4))//84
    m.seed(12345)
    m.put(0xE60134, 1)  # Native auto rookie signing, including the human club.
    m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress text/render only; native draft and contract code executes")
    team = m.call(0x3254D0)
    before = m.uc.mem_read(team+0x11C, 1)[0]
    m.call(draft.DRAFT_PICK, ecx=0, budget=10000000)
    after = m.uc.mem_read(team+0x11C, 1)[0]
    if after != before+1:
        raise AssertionError("native auto-sign did not append exactly one player")
    player = m.get(team+before*4)
    return {"draft_ai_sha256": hashlib.sha256(patched).hexdigest(),
            "fixed_club_candidate_by_seed": choices, "distinct_candidates": len(set(choices.values())),
            "native_sign": {"club": (team-m.team_base)//500,
                            "ordinal": (player-m.get(m.root+4))//84,
                            "count_before": before, "count_after": after,
                            "flags": m.uc.mem_read(player+8, 1)[0],
                            "contract_word": hex(m.get(player+0x24))}, "leaves": m.leaves}


def full_draft_proof(payload, seeds=(1, 2, 3, 4, 5, 6, 7, 8)):
    """Seven native rounds, native contracts and undrafted-FA cleanup per seed."""
    document = rr.RosterDocument(signed_save(), base=rr.SAVE_BLOCK_OFFSET)
    reservation = draft.reserve(bowl.prospects_from_document(document), year=0,
                                franchise_id=b"draft-start-test", position=0)
    document, reservation, _ = draft.inject(
        document, reservation, draft.Creation("Noah", "Rookie", 0, 1),
        year=0, franchise_id=reservation.franchise_id)
    patched = ai.apply(payload)[0]
    results = []
    for seed in seeds:
        m = Machine(patched, trace_writes=False)
        m.load_franchise(document.to_body())
        m.seed(seed)
        m.put(0xE576A4, 5)
        m.put(0xE60134, 1)
        m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress text/render only")
        m.call(0x325A30)
        player = m.get(m.root+4)+84*reservation.index
        landing = None
        for pick in range(224):
            team = m.call(0x3254D0)
            count = m.uc.mem_read(team+0x11C, 1)[0]
            m.call(draft.DRAFT_PICK, ecx=0, budget=10000000)
            if m.uc.mem_read(team+0x11C, 1)[0] > count and m.get(team+count*4) == player:
                if landing is not None:
                    raise AssertionError("MyPlayer was drafted twice")
                club = (team-m.team_base)//500
                landing = {"club": club, "club_name": document.teams[club].display, "overall_pick": pick+1}
            m.call(0x325A50)
        if m.call(0x325D00) != 1:
            raise AssertionError("native seven-round completion check failed")
        m.call(0x31E430, budget=10000000)
        free = m.get(m.root+0x3C)
        free_count = m.get(m.root+0x38)
        occurrences = sum(m.get(free+i*4) == player for i in range(free_count))
        if occurrences != (1 if landing is None else 0):
            raise AssertionError("native draft cleanup lost or duplicated MyPlayer")
        if m.uc.mem_read(player+8, 1)[0] & 0x10:
            raise AssertionError("prospect flag survived native draft cleanup")
        results.append({"seed": seed, "ordinal": reservation.index, "landing": landing,
                        "free_agent_occurrences": occurrences, "free_agent_count": free_count,
                        "rounds_completed": m.get(0xE3C0A8), "leaves": m.leaves})
    return results


def fresh_start_proof(payload):
    m = Machine(payload, trace_writes=False)
    body = retail_roster()
    m.load_retail_roster(body)
    m.seed(12345)
    m.put(0xE5FF80, 4)
    m.put(0xE60120, 0)
    m.put(0xE6000C, 5)
    m.put(0xE60010, 5)
    m.call(draft.NATIVE_START, budget=150000000)
    classes = [i for i in range(m.get(m.root))
               if m.uc.mem_read(m.get(m.root+4)+i*84+8, 1)[0] & 0x34 == 0x14]
    result = {"roster_sha256": hashlib.sha256(body).hexdigest(),
              "stage": m.get(0xE576A4), "stage_weeks": m.get(0xE576B0),
              "week": m.get(0xE576B4), "year": m.get(0xE576B8),
              "class_count": len(classes), "leaves": m.leaves.copy()}
    m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress text/render only")
    visits = Counter()
    for address in (sim.STEP, 0x1356D0):
        m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_, a=address: visits.update([a]), begin=address, end=address)
    value = m.call(0xC7A20, ecx=0, edx=0, args=(0,), budget=200000000)
    result["first_fixture"] = {"return": value, "fixture_hex": m.uc.mem_read(0xE57C40, 8).hex(),
                               "native_ticks": visits[sim.STEP], "native_commits": visits[0x1356D0],
                               "leaves": m.leaves.copy()}
    return result


def prior_year_proof(payload):
    """Real hidden prior year through Combine/Draft entry, without game UI.

    Register a temporary native club owner at the postseason exit: the native
    zero-owner branch ends the franchise. This does not assign MyPlayer there.
    A zero-depth synthetic menu context services native stack-pop no-ops. Only
    progress rendering and informational dialog presentation are substituted.
    """
    m = Machine(payload, trace_writes=False)
    m.load_retail_roster(retail_roster())
    m.seed(12345)
    for address, value in ((0xE5FF80, 4), (0xE60120, 0), (0xE6000C, 5), (0xE60010, 5)):
        m.put(address, value)
    m.call(draft.NATIVE_START, budget=150000000)
    menu = m.ARENA+0x1A0000
    notifications = []
    def notice():
        pointer = m.reg("EDX")
        value = bytes(m.uc.mem_read(pointer, 512)).decode("utf-16-le", "replace").split("\0")[0]
        notifications.append(value)
        m.ret()
    m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress text/render only")
    m.leaf(0x14E520, notice, reason="informational dialog display/acknowledgement only")
    def unexpected_dialog(*_):
        raise AssertionError(f"unexpected decision dialog at caller {m.get(m.reg('ESP')):#x}")
    m.uc.hook_add(m.u.UC_HOOK_CODE, unexpected_dialog, begin=0x14E440, end=0x14E440)
    visits = Counter()
    for address in (0xC7A20, 0x1356D0, draft.GENERATE_CLASS, 0x247B40):
        m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_, a=address: visits.update([a]), begin=address, end=address)
    def state():
        return {key: m.get(address) for key, address in
                (("stage", 0xE576A4), ("week", 0xE576B4), ("end_week", 0xE576B0), ("year", 0xE576B8))}
    rows = [state()]
    for _ in range(32):
        current = state()
        if current["stage"] == 4:
            break
        if current["stage"] in (7, 8, 9) and current["week"] < current["end_week"]:
            m.call(draft.ADVANCE_WEEK, ecx=menu, budget=3000000000)
        else:
            if current["stage"] == 9:
                m.call(0xC4D30, ecx=m.team_base, edx=1)
            m.call(draft.ADVANCE_STAGE, ecx=menu, budget=3000000000)
        after = state()
        if after == current:
            raise AssertionError(f"native stage refused progress: {after}; notices={notifications}")
        rows.append(after)
        print(f"native prior year: stage {after['stage']}, week {after['week']}, year {after['year']}",
              file=sys.stderr, flush=True)
    if state()["stage"] != 4 or state()["year"] != 1:
        raise AssertionError(f"prior-year step cap reached: {state()}")
    def current_class():
        primary = m.get(m.root+4)
        owned = {m.get(m.team_base+t*500+i*4) for t in range(32)
                 for i in range(m.uc.mem_read(m.team_base+t*500+0x11C, 1)[0])}
        return tuple(bowl.Prospect(i, m.uc.mem_read(primary+i*84+0x35, 1)[0],
                                   m.uc.mem_read(primary+i*84+8, 1)[0], primary+i*84 in owned)
                     for i in range(m.get(m.root))
                     if m.uc.mem_read(primary+i*84+8, 1)[0] & 0x34 == 0x14)
    before = current_class()
    squads = bowl.select_squads(before, seed=1)
    m.call(draft.ADVANCE_STAGE, ecx=menu, budget=3000000000)
    if state()["stage"] != 5 or current_class() != before:
        raise AssertionError("Combine-to-Draft regenerated or lost the prospect class")
    return {"transitions": rows+[state()], "class_count": len(before),
            "squad_sizes": [len(s) for s in squads], "class_stable_at_draft_entry": True,
            "native_calls": {hex(k): v for k, v in visits.items()},
            "notifications": notifications, "leaves": m.leaves,
            "temporary_club_owner": 0, "myplayer_assigned_to_temporary_club": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--prior-year", action="store_true", help="slow full native season/offseason proof")
    args = parser.parse_args(argv)
    payload = retail_bytes()
    result = {"schema": 1, "experimental": True, "runtime_witnessed": False, "audit": audit(payload)}
    if args.prior_year:
        result["prior_year"] = prior_year_proof(payload)
    else:
        result.update(stops=stop_proof(payload), prospect_projection=projection_proof(payload),
                      draft=draft_proof(payload), full_drafts=full_draft_proof(payload),
                      fresh_start=fresh_start_proof(payload))
    text = json.dumps(result, indent=2, sort_keys=True)+"\n"
    if args.output:
        # Small derived receipt only; the existing bounded atomic writer refuses
        # SAVEGAME.DAT, EXTRA and DEFAULT.XBE and closes handles before replace.
        bowl.atomic_write(args.output, text.encode("utf-8"))
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
