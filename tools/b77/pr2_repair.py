#!/usr/bin/env python3
"""Apply the league's DAL/WAS coach pictures to a known disc copy, with fixed-span receipts.

The project must supply exactly one player_portrait edit for each of 7031 and 7034.
The canonical retail index is the same verified source used by Studio's project importer.
Only the two portrait spans are written. All other project edits are deliberately outside this repair's scope.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_modern_coaches as mc
from tools.b77.co3_repair import file_sha, changed_runs, owned_ranges, write_json
import nfl2k5_visual_mod_project as vp

INPUTS = {
    "520429148f57c29a23f56b5f43c5fe04be39728d01a101210aad8336b60581a4",
    "d60ea6dd42fac32fa2ffb52a83ccf97d1fa555965b8517a0a2ddd40ab251c3cf",
}
INPUT_SIZE = 6_004_408_320


def require(ok, message):
    if not ok:
        raise ValueError("pr2_repair: REFUSED: " + message)


def outside_count(runs, ranges):
    total = 0
    for start, end in runs:
        covered = sum(max(0, min(end, b) - max(start, a)) for a, b, _ in ranges)
        total += end - start - covered
    return total


def compile_project(project_path, index, receipts):
    """Use the real Studio project reader, input pins, and physical portrait compiler."""
    project = vp.read_project(project_path)
    edits = [e for e in project.value["edits"]
             if e.get("kind") == "player_portrait" and e.get("portrait_id") in ("7031", "7034")]
    require(sorted(e["portrait_id"] for e in edits) == ["7031", "7034"], "project must name both reserved pictures once")
    # Pin only this repair's inputs; the complete league project remains available to the full builder.
    from dataclasses import replace
    subset = replace(project, value=dict(project.value, edits=edits))
    pins = vp.pin_project_inputs(subset)
    compiled, proof = {}, []
    with tempfile.TemporaryDirectory(prefix="pr2-compile-", dir=receipts) as temp:
        root = vp.ownership.track_existing(Path(temp), True)
        files = []
        for order, edit in enumerate(edits):
            parts = vp.build_player_portrait_imports(order, edit, subset, pins,
                vp.REPORTS["player_portrait"],
                index, root, files)
            span = b"".join(p[0] for p in parts)
            report = parts[0][2]
            target = report["target"]
            compiled[edit["portrait_id"]] = (span, target)
            for _span, previews, _report, _selector, _target in parts:
                for name, payload in previews:
                    (receipts / name).write_bytes(payload)
            proof.append(dict(portrait_id=edit["portrait_id"], png=report["input_png"],
                              replacement=report["replacement"], target=target))
    write_json(receipts / "league_compile.json", proof)
    return compiled


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("image", "original", "project", "index", "receipts"):
        ap.add_argument("--" + name, required=True, type=Path)
    a = ap.parse_args(argv)
    require(not os.path.samefile(a.image, a.original), "image must be a separate copy")
    require(a.original.stat().st_size == a.image.stat().st_size == INPUT_SIZE, "disc size is unknown")
    original_sha = file_sha(a.original)
    require(original_sha in INPUTS, "unknown original hash " + original_sha)
    a.receipts.mkdir(parents=True, exist_ok=True)
    compiled = compile_project(a.project, a.index, a.receipts)
    plan, rows, equality = [], [], []
    with mc._outer_image()(a.image) as arc:
        for row in mc.pins()["portraits"]:
            after, target = compiled[row["portrait_id"]]
            entry = arc.entries[target["outer_index"]]
            require(entry.name_id == int(target["outer_id"], 16), "portrait aggregate moved")
            at = entry.virtual_offset + target["chunk_offset"]
            before = arc.read(at, target["span_size"])
            require(before[:160] == after[:160] and len(before) == len(after), "portrait wrapper or system changed")
            _site, photo = mc._coach_photo_site(arc, row["team"])
            require(photo == int(row["portrait_id"]), "coach record does not resolve the reserved portrait")
            if before != after:
                plan.append((at, before, after))
            rows.append(dict(kind="portrait", team=row["team"], portrait_id=row["portrait_id"],
                virtual_offset=at, size=len(after), before_sha256=mc.sha(before), after_sha256=mc.sha(after),
                changed_bytes=sum(x != y for x, y in zip(before, after))))
            equality.append(dict(team=row["team"], portrait_id=photo, studio_sha256=mc.sha(after)))
    ranges = owned_ranges(a.image, rows)
    input_sha = file_sha(a.image)
    if input_sha != original_sha:
        require(not plan, "unknown input hash " + input_sha)
        require(outside_count(changed_runs(a.original, a.image), ranges) == 0,
                "replay differs outside the two owned spans")
    with mc._outer_image()(a.image, writable=True) as arc:
        mc._write_all(arc, plan)
        for r, e in zip(rows, equality):
            span = arc.read(r["virtual_offset"], r["size"])
            e.update(disc_sha256=mc.sha(span), equal=span == compiled[r["portrait_id"]][0])
    output_sha = file_sha(a.image)
    write_json(a.receipts / "disc_write.json", dict(input_sha256=input_sha, output_sha256=output_sha,
        written=len(plan), changed_bytes=sum(r["changed_bytes"] for r in rows), parts=rows))
    replay = []
    with mc._outer_image()(a.image) as arc:
        for r in rows:
            if arc.read(r["virtual_offset"], r["size"]) != compiled[r["portrait_id"]][0]:
                replay.append(r["portrait_id"])
    require(not replay, "replay would write")
    write_json(a.receipts / "disc_replay.json", dict(planned_writes=len(replay), written_bytes=0))
    runs = changed_runs(a.original, a.image)
    outside = outside_count(runs, ranges)
    changed = sum(b-a for a,b in runs)
    write_json(a.receipts / "disc_scope.json", dict(original_sha256=original_sha, output_sha256=output_sha,
        compared_bytes=INPUT_SIZE, changed_bytes=changed, changed_runs=len(runs), owned_ranges=ranges,
        changed_outside_owned=outside))
    require(outside == 0, "changed bytes outside owned spans")
    require(all(r["equal"] for r in equality), "Studio equality failed")
    write_json(a.receipts / "disc_studio_equality.json", dict(all_equal=True, parts=equality))
    from mod_editor.core import nfl2k5_coach_ai as ai
    gate = ai.roster_readiness(a.image)
    require(gate["ready"], "coach AI readiness failed")
    write_json(a.receipts / "roster_gate.json", gate)
    final_plan, final_rows = mc.plan_image(a.image)
    require(not final_plan, "the final Studio coach pass would change the league output")
    kept = [r["team"] for r in final_rows if r["kind"] == "portrait" and r["state_before"] == "kept"]
    require(sorted(kept) == ["DAL", "WAS"], "league pictures were not retained")
    write_json(a.receipts / "studio_final_pass.json", dict(planned_writes=0, league_pictures_kept=kept))
    print(f"APPLIED {len(plan)} writes, {sum(r['changed_bytes'] for r in rows)} changed bytes; replay 0 writes")
    print(f"SCOPE {changed} bytes changed, {outside} outside {len(ranges)} owned ranges; compared {INPUT_SIZE} bytes")
    print(f"STUDIO {len(equality)}/{len(equality)} portrait spans equal the league project compiler")
    print(f"COACH AI ready={gate['ready']} checked={gate['checked']}; DAL=7031 WAS=7034")
    print("STUDIO FINAL PASS 0 writes; league pictures kept=2")
    print(f"OUTPUT {output_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
