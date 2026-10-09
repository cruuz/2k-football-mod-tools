#!/usr/bin/env python3
"""Beta 77 u3r: turn a re-compiled alternate's manifest (``u3s_alternates.py compile``) into a stacked u3r manifest.

An alternate that u3r redoes was already installed by its own job (u3a, u3b, ...). Re-compiling it gives spans whose
``before`` is the shipped v0.5 bytes. This tool keeps only the spans that really change (their ``after`` differs from
what the earlier job's manifest wrote at the same place), and records the earlier job's ``after`` as an accepted
``also_before_sha256``, so ``tools/b77/u3r_repair.py`` applies on top of the earlier repair (and on a plain v0.5 disc).
A span that overlaps an earlier span without being identical to it is a conflict and stops the run.

  u3r_restack.py --new NEW_MANIFEST --prior PRIOR_MANIFEST [--prior ...] --out OUT_DIR [--into EXISTING_U3R_MANIFEST]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

SCHEMA = "b77/u3r/texture-repair/v1"


def restack(new: dict, new_dir: Path, priors: list[tuple[dict, Path]], out: Path, into: dict | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    resources = {k: list(v) for k, v in (into or {}).get("resources", {}).items()}
    earlier = {}
    for doc, _ in priors:
        for resource, patches in doc["resources"].items():
            for p in patches:
                earlier.setdefault((resource, p["offset"], p["length"]), []).append(p["after_sha256"])
    kept = dropped = 0
    for resource, patches in new["resources"].items():
        for p in patches:
            key = (resource, p["offset"], p["length"])
            for (r, off, ln), _after in earlier.items():
                if r == resource and off < p["offset"] + p["length"] and p["offset"] < off + ln and (off, ln) != (p["offset"], p["length"]):
                    raise ValueError(f"{resource}: span {p['offset']}+{p['length']} overlaps an earlier span {off}+{ln}")
            prior_after = earlier.get(key, [])
            if p["after_sha256"] in prior_after:
                dropped += 1                    # the earlier job already wrote exactly these bytes
                continue
            src = new_dir / p["replacement"]
            shutil.copyfile(src, out / p["replacement"])
            resources.setdefault(resource, []).append(dict(
                p, also_before_sha256=sorted(set(prior_after) - {p["before_sha256"]})))
            kept += 1
    for patches in resources.values():
        patches.sort(key=lambda p: p["offset"])
    return {"schema": SCHEMA, "key": "u3r", "set": (into or {}).get("set", "u3r"), "resources": resources,
            "restack": {"kept": kept, "dropped_unchanged": dropped}}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--new", type=Path, required=True)
    p.add_argument("--prior", type=Path, action="append", default=[])
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--into", type=Path)
    a = p.parse_args(argv)
    new = json.loads(a.new.read_text())
    priors = [(json.loads(x.read_text()), x.parent) for x in a.prior]
    into = json.loads(a.into.read_text()) if a.into else None
    a.out.mkdir(parents=True, exist_ok=True)
    if into:
        for patches in into["resources"].values():
            for patch in patches:
                src = a.into.parent / patch["replacement"]
                if src.exists() and not (a.out / patch["replacement"]).exists():
                    shutil.copyfile(src, a.out / patch["replacement"])
    manifest = restack(new, a.new.parent, priors, a.out, into)
    (a.out / "native_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                                                encoding="utf-8", newline="\n")
    print(json.dumps(manifest["restack"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
