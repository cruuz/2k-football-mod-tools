"""Reproduce the rev 3 patch artifacts and offline image/legacy audit.

Run from the repository root with PYTHONPATH=. on cores 24..31. Owned image
bytes are only decoded in memory; no game image or disc is written.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import types

from mod_editor.core import apf2k8_charge_abilities as p
from mod_editor.core.apf2k8_xex import reconstruct_tu
from tools.apf_charge_abilities_probe import load_owned_image

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent
XEX = Path(os.environ.get("APF_RETAIL_XEX", ROOT / "extracted/All-Pro Football 2K8 (USA)/default.xex"))
TU = Path(os.environ.get("APF_RETAIL_TU", "/home/noah/Downloads/uranus/TU_1A58207_0000008000000.0000000000082"))
WITNESS = Path("/media/noah/Storage/.b76-research/ax")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def scan_text(image, profile):
    pe = struct.unpack_from("<I", image, 0x3C)[0]
    count = struct.unpack_from("<H", image, pe + 6)[0]
    size = struct.unpack_from("<H", image, pe + 20)[0]
    for index in range(count):
        off = pe + 24 + size + index * 40
        if image[off:off + 8].rstrip(b"\0") == b".text":
            length, start = struct.unpack_from("<II", image, off + 8)
            break
    else:
        raise AssertionError("Missing .text section")
    callers, cave_targets = [], []
    for off in range(start, start + length - 3, 4):
        word = struct.unpack_from(">I", image, off)[0]
        if word >> 26 == 18 and not word & 2:
            delta = word & 0x3FFFFFC
            if delta & (1 << 25):
                delta -= 1 << 26
            target = off + p.IMAGE_BASE + delta
            if target == p.address(0x848C4D48, profile) and word & 1:
                callers.append(f"{off + p.IMAGE_BASE:08X}")
            if p.CAVE <= target < p.CAVE_LIMIT:
                cave_targets.append(f"{off + p.IMAGE_BASE:08X}")
    assert not cave_targets
    assert callers == (["848E7FB4", "8490376C"] if profile == p.PROFILES[0] else ["848E8E3C", "84904634"])
    return {"profile": profile.name, "text_start": f"{start + p.IMAGE_BASE:08X}",
            "text_end": f"{start + length + p.IMAGE_BASE:08X}", "downgrade_callers": callers,
            "direct_branch_targets_in_reservation": cave_targets,
            "reservation": [f"{p.CAVE:08X}", f"{p.CAVE_LIMIT:08X}"]}


def main():
    output = OUTPUT / "patches"
    output.mkdir(exist_ok=True)
    old = types.ModuleType("mod_editor.core._apf2_rev2")
    old.__package__ = "mod_editor.core"
    sys.modules[old.__name__] = old
    exec(subprocess.check_output(["git", "show", "b640f9e5:mod_editor/core/apf2k8_charge_abilities.py"], cwd=ROOT), old.__dict__)
    base, _ = load_owned_image(XEX)
    updated, _ = reconstruct_tu(base, XEX.read_bytes(), TU.read_bytes())
    records, scans = [], []
    for image, profile in zip((base, updated), p.PROFILES):
        assert sha(image) == profile.sha256
        doc = p.PatchDocument(profile, True)
        p.verify_image(image, doc)
        assert p.revert_image(p.apply_image(image, doc), doc) == image
        scans.append(scan_text(image, profile))
        legacy = []
        for revision in (1, 2):
            for enabled in (False, True):
                previous = old.PatchDocument(profile, enabled, revision).as_toml().encode()
                current = p.PatchDocument(profile, enabled, revision)
                assert previous == current.as_toml().encode()
                assert p.parse_payload(previous) == current
                assert p.revert_image(p.apply_image(image, current), current) == image
                legacy.append({"revision": revision, "enabled": enabled, "sha256": sha(previous)})
        hooks = []
        for check, cave, code in p.move_trampolines(profile):
            site = p.move_address(check, profile)
            original = b"".join(struct.pack(">I", word) for word in check[2])
            assert image[site - p.IMAGE_BASE:site - p.IMAGE_BASE + 8] == original
            # Independently match 20 bytes around the BASE hook to TU.
            off = check[0] - p.IMAGE_BASE
            signature = base[off - 8:off + 12]
            begin, end = off - 0x100, off + 0x2000
            matches = []
            while (begin := image.find(signature, begin, end)) >= 0:
                matches.append(begin + 8 + p.IMAGE_BASE)
                begin += 1
            assert matches == [site], matches
            hooks.append({"site": f"{site:08X}", "base_site": f"{check[0]:08X}",
                          "family": check[-1], "original_pair": original.hex(),
                          "cave": f"{cave:08X}", "length": len(code),
                          "signature_matches": [f"{a:08X}" for a in matches]})
        path = output / f"54540807-charge-abilities-{profile.name}.patch.toml"
        p.write_patch(doc, path)
        receipt = path.with_suffix(path.suffix + ".receipt.json")
        records.append({"profile": profile.name, "module_hash": profile.module_hash,
                        "image_sha256": profile.sha256, "path": str(path.relative_to(ROOT)),
                        "sha256": sha(path.read_bytes()), "receipt_sha256": sha(receipt.read_bytes()),
                        "revision": 3, "word_count": len(doc.words), "exact_revert": True,
                        "legacy_payloads_match_baseline": legacy, "move_hooks": hooks})
    evidence_paths = [WITNESS / "AX_REPORT.md", *sorted(WITNESS.glob("CONTACT_SHEET_*.png")),
                      *sorted((WITNESS / "sheet").glob("*.png")),
                      Path("/home/noah/2k-worktrees/beta-76/B76_APF_REPORT.md")]
    evidence = [{"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path.read_bytes())}
                for path in evidence_paths]
    (OUTPUT / "input-evidence.json").write_text(json.dumps({"classification": "PROVED OFFLINE", "inputs": evidence}, indent=2) + "\n")
    manifest = {"classification": "PROVED OFFLINE", "baseline": "b640f9e5c1b8141d67e96d635a7b56ee0ace580d",
                "cpu_affinity": sorted(os.sched_getaffinity(0)), "patches": records}
    (OUTPUT / "patch-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (OUTPUT / "static-scan.json").write_text(json.dumps({"classification": "PROVED OFFLINE",
        "scope": "Aligned relative b/bl scan of the pinned .text; computed targets are not ruled out.",
        "profiles": scans}, indent=2) + "\n")
    print(json.dumps({"classification": "PROVED OFFLINE", "profiles": [r["profile"] for r in records],
                      "patch_sha256": [r["sha256"] for r in records], "legacy_comparisons": 8,
                      "apply_revert": "PASS", "independently_matched_hooks": 16}, indent=2))


if __name__ == "__main__":
    main()
