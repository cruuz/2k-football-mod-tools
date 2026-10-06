#!/usr/bin/env python3
"""Finalize the per-team audit from native readbacks and comparable renders."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from PIL import Image

FONT_CODES = {"ARI": "00", "CIN": "06", "DEN": "08", "DET": "09", "HOU": "37",
              "MIA": "14", "MIN": "15", "TEN": "28"}
ARM_SIDES = {"ARI": {"H"}, "CIN": set(), "DEN": set(), "DET": {"H", "A"},
             "HOU": {"H"}, "MIA": {"H", "A"}, "MIN": {"H", "A"}, "TEN": {"H", "A"}}


def check_font_receipt(doc: dict, before: dict, after: dict) -> dict:
    """Require chest/back and visible shoulder fonts, preserving all other spans."""
    code = doc.get("team")
    if doc.get("schema") != "b765/u1/fonts/v1" or code not in FONT_CODES:
        raise ValueError("unsupported follow-up font receipt")
    selectors = {FONT_CODES[code] + side + "0" for side in ("H", "A")}
    if doc.get("families") != ["jersey_digit", "arm_digit"] or set(doc["resources"]) != selectors:
        raise ValueError("follow-up fonts must own both primary jersey/shoulder families")
    measurements = doc["digits"]
    expected = {("jersey_digit", selector, digit) for selector in selectors for digit in range(10)}
    expected.update(("arm_digit", FONT_CODES[code] + side + "0", digit)
                    for side in ARM_SIDES[code] for digit in range(10))
    actual = {(m["family"], m["selector"], m["digit"]) for m in measurements}
    if len(measurements) != len(expected) or actual != expected:
        raise ValueError("follow-up font must contain every jersey and visible shoulder digit")
    for selector in selectors:
        resource = doc["resources"][selector]
        b, a = before[selector], after[selector]
        if (not resource["outside_scope_identical"] or not resource["idempotent"] or
                resource["before_sha256"] != b["resource_sha256"] or
                resource["after_sha256"] != a["resource_sha256"]):
            raise ValueError("font receipt does not match native resource readback")
        ba = {x["chunk_index"]: x for x in b["assets"]}
        aa = {x["chunk_index"]: x for x in a["assets"]}
        spans = {(s["offset"], s["length"]): s for s in resource["spans"]}
        owns_arms = selector[2] in ARM_SIDES[code]
        owned_chunks = set(range(13, 23)) | (set(range(33, 43)) if owns_arms else set())
        if len(resource["spans"]) != len(owned_chunks) or len(spans) != len(owned_chunks):
            raise ValueError("follow-up font must own exactly its jersey/shoulder stored spans")
        for chunk, asset in ba.items():
            native = aa[chunk]
            if chunk in owned_chunks:
                span = spans.get((asset["offset"], asset["length"]))
                if (not span or span["before_sha256"] != asset["span_sha256"] or
                        span["after_sha256"] != native["span_sha256"]):
                    raise ValueError("number font span differs from actual native readback")
            elif asset["span_sha256"] != native["span_sha256"]:
                raise ValueError("follow-up font changed an unowned native component")
    return doc


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_helmet_receipt(doc: dict, before: dict, after: dict) -> dict:
    """Require both Giants shell-C textures and all protected native components."""
    selectors = {"18H0", "18A0"}
    if (doc.get("schema") != "b765/u1/nyg-logo-mips-receipt/v1" or
            set(doc.get("resources", {})) != selectors or doc.get("geometry_edited") is not False):
        raise ValueError("unsupported Giants helmet receipt")
    for selector in selectors:
        r, b, a = doc["resources"][selector], before[selector], after[selector]
        if (r["before_sha256"] != b["resource_sha256"] or
                r["after_sha256"] != a["resource_sha256"] or
                not r["outside_scope_identical"] or not r["idempotent"] or len(r["spans"]) != 1):
            raise ValueError("Giants receipt differs from actual native readback")
        span = r["spans"][0]
        pixel = span["helmet_pixel_scope"]
        if (pixel["family"] != "helmet02" or pixel["mip_levels"] != [1] or
                pixel["protected_changed_texels"] != 0 or not pixel["system_identical"] or
                not pixel["descriptor_identical"] or not pixel["allocation_identical"] or
                len(pixel["levels"]) != 6):
            raise ValueError("Giants mip pixel protection is incomplete")
        for level, row in enumerate(pixel["levels"]):
            width = 256 >> level
            if (row["level"] != level or row["dimensions"] != [width, width] or
                    row["protected_changed_texels"] != 0 or
                    row["protected_before_sha256"] != row["protected_after_sha256"] or
                    (level not in pixel["mip_levels"] and row["changed_texels"] != 0)):
                raise ValueError("Giants protected mip readback differs")
        aa = {x["chunk_index"]: x for x in a["assets"]}
        for x in b["assets"]:
            y = aa[x["chunk_index"]]
            if x["chunk_index"] == 12:
                if (span["offset"] != x["offset"] or span["length"] != x["length"] or
                        span["before_sha256"] != x["span_sha256"] or
                        span["after_sha256"] != y["span_sha256"]):
                    raise ValueError("Giants helmet span differs from native readback")
            elif x["span_sha256"] != y["span_sha256"]:
                raise ValueError("Giants correction changed an unowned component")
    return doc


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scratch", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    p.add_argument("--font-receipt", type=Path, action="append", default=[],
                   help="Jersey/visible-shoulder follow-up receipt; repeat for each corrected team")
    p.add_argument("--helmet-receipt", type=Path, help="Reviewed Giants shell-C logo mip receipt")
    p.add_argument("--readback-export", type=Path)
    p.add_argument("--render-after", type=Path)
    p.add_argument("--contact-sheets", type=Path)
    a = p.parse_args()
    root = a.scratch.resolve()
    before = json.loads((root / "before/export.json").read_text())
    readback_export = a.readback_export or root / "after/export.json"
    after = json.loads(readback_export.read_text())
    audit_path = root / "uniform_audit.json"
    audit = json.loads(audit_path.read_text())
    receipt = json.loads(a.receipt.read_text())
    bmap = {s["selector"]: s for s in before["sets"]}
    amap = {s["selector"]: s for s in after["sets"]}
    assert set(bmap) == set(amap) and len(amap) == 70
    assert len(audit["teams"]) == 32
    changed = {k for k in bmap if bmap[k]["resource_sha256"] != amap[k]["resource_sha256"]}
    font_docs = {}
    for path in a.font_receipt:
        doc = check_font_receipt(json.loads(path.read_text()), bmap, amap)
        if doc["team"] in font_docs:
            raise ValueError("duplicate follow-up font receipt")
        font_docs[doc["team"]] = dict(doc, receipt_path=str(path.resolve()))
    expected_changed = {"16H0", "16A0", "24H0", "24A0"}
    for doc in font_docs.values():
        expected_changed.update(doc["resources"])
    helmet_doc = None
    if a.helmet_receipt:
        helmet_doc = check_helmet_receipt(json.loads(a.helmet_receipt.read_text()), bmap, amap)
        expected_changed.update(helmet_doc["resources"])
    assert changed == expected_changed
    assert all(v["outside_scope_identical"] and v["readback"] for v in receipt["resources"].values())
    out = a.render_after or root / "renders/after"
    contact_sheets = a.contact_sheets or root / "contact_sheets"
    out.mkdir(parents=True, exist_ok=True)
    views = ("front", "side", "back", "helmet")
    notes = {
        "NE": ["Replaced retired jersey numerals with authored modern block contours and silver/red trim.",
               "Aligned shoulder bands across the native UV seam; limited coverage away from the collar.",
               "Changed facemask ARGB FFA20001 to FFC8102E.",
               "Source now explicitly preserves the already-transparent shoulder digits; their native spans are untouched."],
        "LAC": ["Replaced upright generic jersey and helmet numerals with the italic club family: eight embedded font outlines and two official-product traces.",
                "Preserved number colors, 56px jersey/30px helmet heights and baseline registration."]}
    for code in font_docs:
        notes[code] = ["Replaced the retired or generic donor with measured current club jersey-number contours for all ten digits on home and away, and on visible shoulders.",
                       "Preserved existing fills, outlines, native registration, blank shoulder slots and every non-number component."]
    if "MIN" in font_docs:
        notes["MIN"].append("Modern base forms are repaired; first-digit-only horn forms require position-aware binding and remain with the coordinator.")
    if helmet_doc:
        notes["NYG"] = ["Re-filtered only the reviewed near logo mips through the protected native palette; base decal shape/placement and coarse mips remain exact.",
                        "Retained existing shell curvature: measured straight-stroke bow is below real 2026 photo controls. Moving in-game wobble still requires Noah's check."]
    gaps = set(FONT_CODES) - font_docs.keys()
    for team in audit["teams"]:
        code = team["team"]
        team["changes"] = notes.get(code, [])
        team["review_status"] = "corrected_offline" if code in notes else "reviewed_preserved"
        team["font_status_after"] = ("improved_authored_trace_exactness_unconfirmed" if code == "NE" else
                                      "club_outlines_plus_two_product_traces" if code == "LAC" else
                                      "sourced_2026_base_family; conditional_first_digit_horn_handed_off" if code == "MIN" and code in font_docs else
                                      "sourced_2026_jersey_contours" if code in font_docs else
                                      "known_approximation_preserved" if code in gaps else
                                      "full_shape_accuracy_unconfirmed" if code == "JAX" else
                                      "reviewed_existing_family_preserved")
        team["geometry_handoff"] = str(root / "u1_GEOMETRY_HANDOFF.md")
        if code in font_docs:
            team["font_receipt"] = font_docs[code]["receipt_path"]
        if code == "NYG" and helmet_doc:
            team["helmet_receipt"] = str(a.helmet_receipt.resolve())
        if code == "MIN" and code in font_docs:
            team["positional_font_handoff"] = str(root / "fonts_followup/MIN/MIN_POSITIONAL_FORMS.md")
        team["contact_sheet"] = str(contact_sheets / f"{code}_before_after.png")
        for kit in team["sets"]:
            sel = kit["selector"]
            b, r = bmap[sel], amap[sel]
            kit["after_resource_sha256"] = r["resource_sha256"]
            kit["whole_resource_byte_identical"] = sel not in changed
            kit["facemask_before_argb"] = b["facemask_argb"]
            kit["facemask_after_argb"] = r["facemask_argb"]
            kit["changes"] = notes.get(code, [])
            kit["components"] = {
                "helmet_logo_scale_placement": "reviewed offline; native textures preserved",
                "helmet_stripes": "reviewed offline; native textures preserved",
                "facemask_colour": "corrected to Patriots red" if code == "NE" else "reviewed offline; native word preserved",
                "jersey_pant_colour": "reviewed offline; base colors and pants preserved",
                "numbers": team["font_status_after"],
                "sleeve_shoulder": "corrected shoulder bands; sleeve and arm spans preserved" if code == "NE" else
                                   "modern number contours; sleeve texture and blank arm spans preserved" if code in font_docs else
                                   "reviewed offline; native spans preserved",
                "bump_maps": "native spans preserved; writer fixed; smoothing candidate unapplied",
                "facemask_shape": "shared geometry diagnosis handed off; no mesh edit",
                "giants_temporal_wobble": "unresolved runtime cause; shell data matches retail" if code == "NYG" else "not reported"}
            if code == "NYG" and helmet_doc:
                kit["components"]["helmet_logo_scale_placement"] = "native mip0 shape/placement preserved; measured near-mip filter correction"
                kit["components"]["giants_temporal_wobble"] = "near-mip filtering improved offline; runtime wobble unconfirmed; geometry/UV exact"
            kit["after_images"] = {}
            kit["image_hashes"] = {"before": {}, "after": {}}
            kit["after_render_origin"] = "actual_repaired_native_decode" if sel in changed else "identical_before_render_reused"
            if code == "NYG" and helmet_doc:
                kit["after_render_origin"] = "identical_mip0_proxy_reused; actual_stored_mips_rendered_separately"
                kit["filtered_helmet_before"] = str(root / "nyg/uv_research/before_native_mips")
                kit["filtered_helmet_after"] = str(root / "nyg/final_native_mips")
            for view in views:
                src = root / "renders/before" / f"{sel}_{view}.png"
                dst = out / src.name
                if sel not in changed:
                    if dst.exists() and digest(dst) != digest(src):
                        raise ValueError("unchanged resource has a differing after render")
                    shutil.copy2(src, dst)
                with Image.open(dst) as im:
                    im.load()
                kit["after_images"][view] = str(dst)
                kit["image_hashes"]["before"][view] = digest(src)
                kit["image_hashes"]["after"][view] = digest(dst)
            ra = {x["chunk_index"]: x for x in r["assets"]}
            kit["native_component_checklist"] = []
            for x in b["assets"]:
                y = ra[x["chunk_index"]]
                kit["native_component_checklist"].append({"name": x["name"], "chunk": x["chunk_index"],
                    "before_span_sha256": x["span_sha256"], "after_span_sha256": y["span_sha256"],
                    "byte_identical": x["span_sha256"] == y["span_sha256"]})
            boxes = []
            for n in range(10):
                with Image.open(Path(r["art"]) / f"digit_jersey_{n}.png") as im:
                    box = im.convert("RGBA").getchannel("A").point(lambda v: 255 if v > 16 else 0).getbbox()
                boxes.append(box)
            kit["after_number_registration"] = {"boxes": boxes,
                "alpha_threshold": 16,
                "height_range": max(b[3]-b[1] for b in boxes)-min(b[3]-b[1] for b in boxes),
                "baseline_range": max(b[3] for b in boxes)-min(b[3] for b in boxes)}
            assert kit["after_number_registration"]["height_range"] <= 2
            assert kit["after_number_registration"]["baseline_range"] <= 2
    audit.update(phase="native-repaired; offline-reviewed; geometry handed to coordinator" if not gaps else
                       "native-repaired; offline-reviewed; font gaps and geometry handoff remain",
                 evidence="Parent inspected all 32 baseline H/A grids, all eight Rams sets, final native corrected renders and per-team before/after grids. Emulator before captures are evidence, never Noah acceptance.",
                 summary={"teams": 32, "sets": 70, "changed_resources": sorted(changed),
                          "whole_resources_preserved": 70 - len(changed),
                          "native_spans": sum(len(r["spans"]) for r in receipt["resources"].values()),
                          "known_font_gaps": sorted(gaps), "additional_full_family_review": ["JAX"],
                          "positional_font_details_handed_off": ["MIN"] if "MIN" in font_docs else [],
                          "native_bump_maps_preserved": True, "geometry_edited": False},
                 resource_receipt=str(a.receipt.resolve()), source_export=str(root / "before/export.json"),
                 readback_export=str(readback_export.resolve()))
    audit_path.write_text(json.dumps(audit, indent=2) + "\n")
    print(f"audit finalized: 32 teams / 70 sets; {len(changed)} resources changed, {70-len(changed)} byte-identical")


if __name__ == "__main__":
    main()
