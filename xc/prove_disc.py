#!/usr/bin/env python3
"""DESIGN: read-only offline checks of an original and its compacted copy."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import mod_build, nfl2k5_music_archive as archive
from mod_editor.core import xdvdfs_compact as compact


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return dict(size=path.stat().st_size, sha256=h.hexdigest())


def normalized(value, disc):
    if isinstance(value, dict):
        return {k: normalized(v, disc) for k, v in value.items()}
    if isinstance(value, list):
        return [normalized(v, disc) for v in value]
    if isinstance(value, str):
        return value.replace(str(disc), "<disc>")
    return value


def inspect(disc, evidence, label, reuse=False):
    print(f"DESIGN: Studio inspection of {label}", flush=True)
    saved = evidence / f"{label}-inspection.json"
    if reuse:
        report = json.loads(saved.read_text())
        assert report['path'] == str(disc)
    else:
        report = mod_build.inspect(disc, screen_timing="D")
        saved.write_text(json.dumps(report, indent=2, default=str) + "\n")
    with archive.Disc(disc, descriptors=()) as reader:
        archive_summary = dict(outer_count=len(reader.archive_entries),
                               virtual_bytes=reader.packs[-1].virtual_end,
                               packs={n: e.size for n, e in reader.pack_extents.items()})
    return normalized(report, disc), archive_summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--reuse-inspections", action="store_true", help="Resume this proof's saved inspections; final disc hashes are still checked")
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    assert shutil.disk_usage(ROOT).free > 100_000_000_000
    original_stat = archive.identity(args.source)
    before, original_archive = inspect(args.source, args.evidence, "source", args.reuse_inspections)
    after, compact_archive = inspect(args.output, args.evidence, "compact", args.reuse_inspections)
    # Geometry is expected to differ; retain the raw reports and compare every
    # status, size pin, setting and identity classification without weakening it.
    geometry = {}
    for label, report in (("source", before), ("compact", after)):
        identity = report['disc_identity']
        geometry[label] = dict(image_size=identity.pop('image_size'), files={})
        for name, row in identity['files'].items():
            geometry[label]['files'][name] = {key: row.pop(key) for key in ('offset', 'at_retail_offset')}
    (args.evidence / 'inspection-geometry.json').write_text(json.dumps(geometry, indent=2) + '\n')
    differences = {k: {"source": before.get(k), "compact": after.get(k)}
                   for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
    (args.evidence / "inspection-differences.json").write_text(json.dumps(differences, indent=2) + "\n")
    assert not differences, differences
    assert original_archive == compact_archive
    print("PROVED OFFLINE: Studio inspection and archive inventory match", flush=True)
    last = 0.0

    def progress(stage, done, total):
        nonlocal last
        if time.monotonic() - last > 10:
            print(f"DESIGN: {stage} ({done}/{total})", flush=True)
            last = time.monotonic()

    scoring = mod_build._check_playbook_scoring(args.output, progress)
    print("PROVED OFFLINE: native play-scoring gate passed", flush=True)
    source_digest, output_digest = digest(args.source), digest(args.output)
    build = json.loads(args.build_receipt.read_text())["result"]
    assert source_digest == {k: build["outcome"]["output"][k] for k in ("size", "sha256")}
    assert archive.identity(args.source) == original_stat
    assert scoring == build["playbook_scoring"]
    result = dict(classification="PROVED OFFLINE", runtime_witnessed=False,
                  source=source_digest, output=output_digest,
                  input_matches_published_build_receipt=True, input_identity_unchanged=True,
                  studio_inspection_equal=True, inspected_top_level_fields=len(before),
                  comparison_exclusions=['disc path', 'disc_identity.image_size',
                                         'disc_identity.files.*.offset', 'disc_identity.files.*.at_retail_offset'],
                  archive=compact_archive, playbook_scoring=scoring,
                  nvme_free_bytes=shutil.disk_usage(ROOT).free,
                  storage_free_bytes=shutil.disk_usage(args.output.parent).free)
    (args.evidence / "disc-proof.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    print("PROVED OFFLINE: " + json.dumps({k: result[k] for k in
          ("source", "output", "studio_inspection_equal", "inspected_top_level_fields")}), flush=True)


if __name__ == "__main__":
    main()
