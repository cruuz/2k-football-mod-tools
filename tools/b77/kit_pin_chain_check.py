#!/usr/bin/env python3
"""Replay the Studio's late uniform steps offline and check every pinned kit span against the project's output.

The Studio build runs, after the project copy and the roster, moment and historic-spare steps:

  era kits (a5k) -> Unc Bowl finish (strict) -> Giants shoulder numbers -> kit fixes uf1, uf2, uf3, sea1, ov1
  -> pants hem (pa1)

Each step pins its inputs. A pin that no longer matches what the project build produces either stops the build
(the Unc Bowl finish and the Giants numbers refuse) or silently leaves the art unfinished (the kit fixes and the hem
skip a texture they do not recognise). The real build reaches these steps after about three hours; this check
takes minutes.

Inputs: the build's verified project manifest (``*-verified-project-manifest.json``; every project span with its
target and hash), the retail disc (read only) and one or more reference discs that hold the same project spans
(byte sources, matched by SHA-256; read only). The kit packages are rebuilt as retail plus the project spans, the
historic spare styles as retail style-0 copies, and the real step code then runs on them in memory.

  kit_pin_chain_check.py --manifest onuser-verified-project-manifest.json \
      --retail "ESPN NFL 2K5 (USA).xiso.iso" --reference "SOFTDRINK 2K28 v0.6 (2026-10-09).xiso.iso" \
      [--only 06H5 22A4 ...] [--report out.json]

Exit status 1 when a step would stop the build or a kit cannot be rebuilt from the given byte sources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_bump_texture_writer as bump  # noqa: E402
from mod_editor.core import nfl2k5_era_kits as era  # noqa: E402
from mod_editor.core import nfl2k5_kit_fixes_2026 as kit  # noqa: E402
from mod_editor.core import nfl2k5_nyg_numbers as nyg  # noqa: E402
from mod_editor.core import nfl2k5_pants_hem_2026 as hem  # noqa: E402
from mod_editor.core import nfl2k5_unc_bowl_uniforms as unc  # noqa: E402
from nfl_outer import PACK_NAMES  # noqa: E402

KIT_DOCUMENTS = (("kit_fixes_2026", kit.DATA), ("kit_fixes_2026_alts", kit.DATA_ALTS),
                 ("kit_fixes_2026_uf3", kit.DATA_UF3), ("kit_fixes_2026_sea1", kit.DATA_SEA1),
                 ("kit_fixes_2026_ov1", kit.DATA_OV1))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def selectors_in_scope():
    """Every kit package a late uniform step reads or writes, in no particular order."""
    names = set(era.needed_packages()[0])
    names |= set(unc.OWNED) | {"22H0.IFF"}
    names.add(nyg.pins()["resource"])
    for _label, path in KIT_DOCUMENTS:
        document = kit.spec(path)
        names |= {s + ".IFF" for s in kit.selectors(document)}
        names |= {s + ".IFF" for s in kit.donor_kits(document)}
    names |= {s + ".IFF" for s in hem.selectors()}
    return sorted(names)


class Disc:
    """A read-only disc image and its logical resource extents."""

    def __init__(self, path):
        self.path = Path(path)
        self._image = bump._Image.open(self.path, writable=False)
        self.image = self._image.__enter__()
        self.index = bump._parsed_index(self.image)
        self.entries = {}
        for entry in self.index.entries:
            self.entries.setdefault(bump.logical_name_for(entry.name_id), []).append(entry)

    def close(self):
        self._image.__exit__(None, None, None)

    def extent(self, name):
        entries = self.entries.get(name, [])
        if len(entries) != 1:
            return None
        parts = self.index.sub_extents(entries[0], 0, entries[0].size)
        return parts if len(parts) == 1 else None

    def read(self, name):
        entries = self.entries.get(name, [])
        if len(entries) != 1:
            return None
        return self.image.read_segments(self.index.sub_extents(entries[0], 0, entries[0].size))


def project_edits(manifest_path):
    document = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    edits = {}
    for edit in document["edits"]:
        target = edit["target"]
        edits.setdefault(target["pack_path"], []).append(
            (target["pack_offset"], edit["replacement"]["span_size"], edit["replacement"]["span_sha256"],
             target["retail_span_sha256"], edit["selector"], edit["order"], edit.get("project_edit") or {}))
    return edits


def _unif_colour(span, project_edit):
    """A project Unif colour edit is two ARGB words (facemask, turtleneck); no turtleneck means the facemask colour
    (nfl2k5_unif_color_writer.build_unif_color_imports)."""
    if project_edit.get("kind") != "unif_color" or len(span) != 8 or not project_edit.get("facemask"):
        return None
    from mod_editor.core.nfl2k5_unif_color_writer import parse_color
    facemask = parse_color(project_edit["facemask"])
    return struct.pack("<II", facemask, parse_color(project_edit.get("turtleneck") or project_edit["facemask"]))


def rebuild_stage(names, retail, references, edits):
    """{name: project-stage bytes}, {name: problem} for kits a reference cannot supply exact span bytes for."""
    stage, problems, provenance = {}, {}, {}
    reference_cache = {}
    for name in names:
        extent = retail.extent(name)
        if extent is None:
            # Not a retail package: the historic-styles spare copy of the retail style-0 kit of the same side.
            code, side = name[:2], name[2]
            sibling = f"{code}{side}0.IFF"
            raw = retail.read(sibling)
            if raw is None:
                problems[name] = "absent from retail and no style-0 sibling"
                continue
            stage[name] = raw
            provenance[name] = dict(source="historic spare copy of retail " + sibling, project_spans=0)
            continue
        ordinal, at, size = extent[0]
        raw = bytearray(retail.image.read_segments(extent))
        pack = "vc_53450030/" + PACK_NAMES[ordinal]
        used, missing = 0, []
        for offset, length, want, retail_hash, selector, order, project_edit in edits.get(pack, []):
            if not at <= offset < at + size:
                continue
            local = offset - at
            if local + length > size or sha(bytes(raw[local:local + length])) != retail_hash:
                missing.append(dict(order=order, selector=selector, reason="span does not lie on the retail package"))
                continue
            computed = _unif_colour(bytes(raw[local:local + length]), project_edit)
            if computed is not None and sha(computed) == want:
                raw[local:local + length] = computed
                used += 1
                continue
            for disc in references:
                key = (disc.path, name)
                if key not in reference_cache:
                    reference_cache[key] = disc.read(name)
                other = reference_cache[key]
                if other is not None and len(other) == size and sha(other[local:local + length]) == want:
                    raw[local:local + length] = other[local:local + length]
                    used += 1
                    break
            else:
                missing.append(dict(order=order, selector=selector, offset=local, length=length, sha256=want))
        if missing:
            # Partial: those spans stay retail, so only rows elsewhere in the kit are checked byte for byte; the rows
            # on these spans are judged by hashes (hash_level).
            problems[name] = dict(reason="project span bytes not found in any reference disc", spans=missing)
        stage[name] = bytes(raw)
        provenance[name] = dict(source="retail + project spans", project_spans=used, unresolved_spans=len(missing))
    return stage, problems, provenance


_RETAIL_CACHE = {}


def _input_kind(raw, stage, retail, selector, row, problems=None):
    """Why a pinned texture was not recognised: what the step actually saw in its span."""
    at, n = row["offset"], row["length"]
    for span in ((problems or {}).get(selector + ".IFF") or {}).get("spans", []):
        if "offset" in span and span["offset"] < at + n and at < span["offset"] + span["length"]:
            return "unresolved project span (no reference bytes; see hash_level)"
    name = selector + ".IFF"
    if name not in _RETAIL_CACHE:
        _RETAIL_CACHE[name] = retail.read(name)
    original = _RETAIL_CACHE[name]
    seen = sha(raw[at:at + n])
    if original is not None and len(original) == len(raw) and seen == sha(original[at:at + n]):
        return "retail (the pinned input comes from a layer this build does not apply)"
    if seen == sha(stage.get(name, b"")[at:at + n]):
        return "project art that differs from the pinned input"
    return "changed by an earlier late step into something other than the pinned input"


def roster_labels_softdrink():
    """The SOFTDRINK roster edits label every era slot with its era years (checked on the v0.6 disc)."""
    return {(r["code"], r["style"]): tuple(r["label"]) for r in era.recipes()}


def replay(stage, retail, *, only=None, problems=None):
    """Run the late uniform steps on a copy of ``stage``; returns (final kits, step reports, errors)."""
    kits = dict(stage)
    reports, errors = [], []

    def wanted(selector):
        return only is None or selector in only

    # 1. era kits
    retail_parts = {name: retail.read(name) for name in era.needed_packages()[1]}
    if all(n in kits for n in era.needed_packages()[0]):
        try:
            rows = era.plan(kits, roster_labels_softdrink(), retail_parts)
        except ValueError as exc:
            errors.append(dict(step="era_kits", error=str(exc)))
            rows = []
        for selector, data, row in rows:
            if data is not None:
                kits[selector + ".IFF"] = data
            reports.append(dict(step="era_kits", selector=selector, state=row["state"],
                                pinned_inputs=row.get("pinned_inputs")))
            if row["state"] not in ("composed", "applied"):
                errors.append(dict(step="era_kits", selector=selector, error="era kit not composed: " + row["state"]))
            elif row["state"] == "composed" and not row["pinned_inputs"]:
                errors.append(dict(step="era_kits", selector=selector,
                                   error="donor inputs differ from the pins (later pins chain from the v0.6 kits)",
                                   inputs=row["inputs"]))
    else:
        errors.append(dict(step="era_kits", error="era kit packages missing from the rebuilt stage"))
    # 2. Unc Bowl (strict in the Studio build)
    if all(n in kits for n in unc.OWNED + ("22H0.IFF",)):
        try:
            specs = {name: unc.validate_owned(name, kits[name]) for name in unc.OWNED}
            fixed = {"06H5.IFF": unc.finish_cincinnati(kits["06H5.IFF"]),
                     "22A4.IFF": unc.finish_pittsburgh(kits["22A4.IFF"], kits["22H0.IFF"])}
            for name, data in fixed.items():
                unc.require(all(unc.sha(data[p["offset"]:p["offset"] + p["length"]]) == p["after_sha256"]
                                for p in specs[name]["spans"]), "compiled Unc Bowl uniform differs from output pins")
            for name, data in fixed.items():
                reports.append(dict(step="unc_bowl_uniforms", selector=name[:-4],
                                    state="applied" if data == kits[name] else "finished"))
                kits[name] = data
        except ValueError as exc:
            errors.append(dict(step="unc_bowl_uniforms", error=str(exc), states={
                name: [("before" if unc.sha(kits[name][p["offset"]:p["offset"] + p["length"]]) == p["before_sha256"]
                        else "after" if unc.sha(kits[name][p["offset"]:p["offset"] + p["length"]]) == p["after_sha256"]
                        else "other") + ":" + p["label"] for p in json.loads(unc.PINS.read_text())["resources"][name]["spans"]]
                for name in unc.OWNED}))
    else:
        errors.append(dict(step="unc_bowl_uniforms", error="Unc Bowl kit packages missing from the rebuilt stage"))
    # 3. Giants shoulder numbers (refuses a partly known kit even in the Studio)
    name = nyg.pins()["resource"]
    if name in kits and wanted(name[:-4]):
        try:
            replacements, receipt = nyg.compile_resource(kits[name], strict=False)
            data = bytearray(kits[name])
            for offset, new in replacements:
                data[offset:offset + len(new)] = new
            kits[name] = bytes(data)
            reports.append(dict(step="nyg_shoulder_numbers", selector=name[:-4], state=receipt["state"]))
        except ValueError as exc:
            errors.append(dict(step="nyg_shoulder_numbers", selector=name[:-4], error=str(exc)))
    # 4. kit fixes, then 5. pants hem (Studio mode: unknown textures are skipped, a compile mismatch stops the build)
    steps = [(label, kit.compile_resource, kit.spec(path)) for label, path in KIT_DOCUMENTS]
    steps.append(("pants_hem_2026", hem.compile_resource, hem.spec()))
    for label, compile_resource, document in steps:
        print("replaying", label, file=sys.stderr, flush=True)
        donors = {s: kits.get(s + ".IFF") for s in (kit.donor_kits(document) if compile_resource is kit.compile_resource else [])}
        rows_by_selector = {}
        for row in document["textures"]:
            rows_by_selector.setdefault(row["selector"], []).append(row)
        for selector, rows in sorted(rows_by_selector.items()):
            if not wanted(selector):
                continue
            raw = kits.get(selector + ".IFF")
            if raw is None:
                reports.append(dict(step=label, selector=selector, state="not_rebuilt"))
                continue
            try:
                if compile_resource is kit.compile_resource:
                    replacements, receipt = compile_resource(selector, raw, strict=False, document=document, kits=donors)
                else:
                    replacements, receipt = compile_resource(selector, raw, strict=False, document=document)
            except ValueError as exc:
                errors.append(dict(step=label, selector=selector, error=str(exc)))
                continue
            data = bytearray(raw)
            for offset, new in replacements:
                data[offset:offset + len(new)] = new
            kits[selector + ".IFF"] = bytes(data)
            skipped = receipt.get("skipped_textures", [])
            entry = dict(step=label, selector=selector, state=receipt["state"], skipped_chunks=skipped,
                         pinned_rows=len(rows), compiled=len(replacements))
            if skipped:
                entry["skipped_detail"] = [dict(chunk=r["chunk"], texture=r.get("texture"),
                                                input=_input_kind(raw, stage, retail, selector, r, problems))
                                           for r in rows if r["chunk"] in skipped]
            reports.append(entry)
    return kits, reports, errors


def hash_level(names, retail, edits):
    """Pinned rows of kits that could not be rebuilt, judged by hashes alone.

    The project-stage hash of a row's span is the manifest span hash when a project edit covers exactly that span,
    the retail hash when no edit touches it, else unknown. Rows chain through the documents in build order (a row's
    pinned output becomes the next document's input for the same span). Strict steps (the Giants numbers) and rows
    whose input is not their pinned input are reported; byte-level compiles cannot be checked here.
    """
    out = []
    current = {}
    for name in names:
        extent = retail.extent(name)
        if extent is None:
            continue
        ordinal, at, size = extent[0]
        raw = retail.image.read_segments(extent)
        pack = "vc_53450030/" + PACK_NAMES[ordinal]
        spans = [(o - at, n, h) for o, n, h, *_rest in edits.get(pack, []) if at <= o < at + size]

        def stage_hash(offset, length, spans=spans, raw=raw):
            hits = [(o, n, h) for o, n, h in spans if o < offset + length and offset < o + n]
            if not hits:
                return sha(raw[offset:offset + length])
            if len(hits) == 1 and hits[0][:2] == (offset, length):
                return hits[0][2]
            return None
        current[name] = stage_hash
    selector_names = {n[:-4] for n in current}
    seen = {}
    nyg_pins = nyg.pins()
    if nyg_pins["resource"][:-4] in selector_names:
        hashes = [current[nyg_pins["resource"]](p["offset"], p["length"]) for p in nyg_pins["digits"]]
        before = [h == p["before_sha256"] for h, p in zip(hashes, nyg_pins["digits"])]
        after = [h == p["after_sha256"] for h, p in zip(hashes, nyg_pins["digits"])]
        donors = [current[nyg_pins["resource"]](p["donor_offset"], p["donor_length"]) == p["donor_sha256"]
                  for p in nyg_pins["digits"]]
        state = ("applied" if all(after) else "compile" if all(before) and all(donors)
                 else "would refuse the build" if any(before) or any(after) else "other_uniform (skipped)")
        out.append(dict(step="nyg_shoulder_numbers", selector=nyg_pins["resource"][:-4], state=state,
                        before_matches=sum(before), after_matches=sum(after), donor_matches=sum(donors)))
    for label, path in KIT_DOCUMENTS + (("pants_hem_2026", hem.DATA),):
        document = hem.spec() if label == "pants_hem_2026" else kit.spec(path)
        for row in document["textures"]:
            if row["selector"] not in selector_names:
                continue
            key = (row["selector"], row["offset"], row["length"])
            have = seen.get(key) or current[row["selector"] + ".IFF"](row["offset"], row["length"])
            state = ("before" if have == row["before_sha256"] else "after" if have == row["after_sha256"]
                     else "unknown" if have is None else "other")
            if state in ("before", "after"):
                seen[key] = row["after_sha256"]
            out.append(dict(step=label, selector=row["selector"], chunk=row["chunk"], state=state))
    return out


def summarize(reports):
    out = {}
    for r in reports:
        key = (r["step"], r["state"])
        out[key] = out.get(key, 0) + 1
    skipped = [(r["step"], r["selector"], [(d["chunk"], d["input"]) for d in r["skipped_detail"]])
               for r in reports if r.get("skipped_chunks")]
    return out, skipped


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--retail", type=Path, required=True)
    parser.add_argument("--reference", type=Path, action="append", default=[])
    parser.add_argument("--only", nargs="*", help="kit selectors to replay in the late steps (era kits and the Unc "
                                                  "Bowl always run)")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    started = time.monotonic()
    only = set(args.only) if args.only else None
    names = selectors_in_scope()
    if only is not None:
        keep = set(era.needed_packages()[0]) | set(unc.OWNED) | {"22H0.IFF"} | {s + ".IFF" for s in only}
        for _label, path in KIT_DOCUMENTS:
            keep |= {s + ".IFF" for s in kit.donor_kits(kit.spec(path))}
        names = sorted(n for n in names if n in keep)
    retail = Disc(args.retail)
    references = [Disc(p) for p in args.reference]
    try:
        edits = project_edits(args.manifest)
        stage, problems, provenance = rebuild_stage(names, retail, references, edits)
        _kits, reports, errors = replay(stage, retail, only=only, problems=problems)
        hashed = hash_level(sorted(problems), retail, edits)
    finally:
        for disc in [retail] + references:
            disc.close()
    for name, problem in sorted(problems.items()):
        if name in set(era.needed_packages()[0]) | set(unc.OWNED) | {"22H0.IFF"}:
            errors.append(dict(step="rebuild", selector=name[:-4], error=problem))
    for row in hashed:
        if row["state"] == "would refuse the build":
            errors.append(dict(step=row["step"], selector=row["selector"], error="hash-level: " + row["state"]))
    counts, skipped = summarize(reports)
    result = dict(schema="b773/kit-pin-chain-check/v1", manifest=str(args.manifest), retail=str(args.retail),
                  references=[str(p) for p in args.reference], kits=len(names), rebuilt=len(stage),
                  seconds=round(time.monotonic() - started, 1), ok=not errors, errors=errors,
                  counts={f"{s}:{st}": n for (s, st), n in sorted(counts.items())}, reports=reports,
                  provenance=provenance, not_rebuilt={n[:-4]: p for n, p in sorted(problems.items())},
                  hash_level=hashed)
    if args.report:
        args.report.write_text(json.dumps(result, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(dict(ok=result["ok"], kits=len(names), rebuilt=len(stage), seconds=result["seconds"],
                          counts=result["counts"], errors=len(errors)), indent=1))
    for error in errors[:40]:
        print("ERROR", json.dumps(error, default=str)[:600])
    for step, selector, chunks in skipped[:80]:
        print("SKIPPED", step, selector, chunks)
    if problems:
        print("NOT REBUILT (no reference disc holds their project spans; judged by hashes):",
              " ".join(sorted(n[:-4] for n in problems)))
    for row in hashed:
        if row["state"] not in ("before", "after"):
            print("HASH", json.dumps(row))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
