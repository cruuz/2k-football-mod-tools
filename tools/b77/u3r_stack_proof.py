#!/usr/bin/env python3
"""Beta 77 u3r: static proof that the u3r spans stack with every other uniform job's spans.

  u3r_stack_proof.py --u3r MANIFEST --other MANIFEST [--other ...] [--w1-spans w1_kit_spans.json] --receipt OUT.json

Every span is (resource, resource offset, length). For each u3r span the proof lists the other jobs' spans that touch
the same resource and byte range: an identical span is a supersede (u3r's ``also_before_sha256`` must then hold that
job's ``after_sha256``, so u3r applies on top of it); a partial overlap is a conflict and the run fails. Other jobs'
manifests are the Studio-compile manifests of u1, u2a to u2d, u3s and u3a to u3e; w1's kit span list is read in its
own format (``selector``, ``chunk``, ``resource_offset``, ``length``).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def spans_of(manifest: dict) -> list[tuple[str, int, int, str]]:
    return [(resource, p["offset"], p["length"], p["after_sha256"])
            for resource, patches in manifest["resources"].items() for p in patches]


def w1_spans(doc: dict) -> list[tuple[str, int, int, str]]:
    return [(f"{s['selector']}.IFF", s["resource_offset"], s["length"], s["after_sha256"]) for s in doc["spans"]]


def prove(u3r: dict, others: dict[str, list[tuple[str, int, int, str]]]) -> dict:
    index: dict[str, list[tuple[str, int, int, str, str]]] = {}
    for name, spans in others.items():
        for resource, offset, length, after in spans:
            index.setdefault(resource, []).append((name, offset, length, after, resource))
    rows, conflicts = [], []
    for resource, patches in u3r["resources"].items():
        for p in patches:
            o0, o1 = p["offset"], p["offset"] + p["length"]
            same, partial = [], []
            for name, offset, length, after, _ in index.get(resource, []):
                if offset < o1 and o0 < offset + length:
                    if (offset, length) == (p["offset"], p["length"]):
                        same.append({"job": name, "after_sha256": after,
                                     "accepted": after in p.get("also_before_sha256", []) or after == p["after_sha256"]})
                    else:
                        partial.append({"job": name, "offset": offset, "length": length})
            row = {"resource": resource, "offset": p["offset"], "length": p["length"], "label": p["label"],
                   "supersedes": same, "partial_overlaps": partial}
            rows.append(row)
            if partial or any(not s["accepted"] for s in same):
                conflicts.append(row)
    return {"spans": len(rows), "conflicts": conflicts,
            "superseded_spans": sum(1 for r in rows if r["supersedes"]), "rows": rows}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--u3r", type=Path, required=True)
    p.add_argument("--other", type=Path, action="append", default=[])
    p.add_argument("--w1-spans", type=Path)
    p.add_argument("--receipt", type=Path, required=True)
    a = p.parse_args(argv)
    others = {str(path): spans_of(json.loads(path.read_text())) for path in a.other}
    if a.w1_spans:
        others["w1"] = w1_spans(json.loads(a.w1_spans.read_text()))
    proof = prove(json.loads(a.u3r.read_text()), others)
    proof["other_manifests"] = {k: len(v) for k, v in others.items()}
    a.receipt.write_text(json.dumps(proof, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"spans": proof["spans"], "superseded": proof["superseded_spans"],
                      "conflicts": len(proof["conflicts"]), "others": len(others)}))
    return 1 if proof["conflicts"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
