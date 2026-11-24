#!/usr/bin/env python3
"""Beta 81 release check: on the standard full build every kit, glyph and card row must be applied.

  python3 tools/b81_release_row_check.py RECEIPT.json
      exit 0 and "RELEASE ROW CHECK PASSED" when no art row was skipped;
      exit 1 and one line per skipped row otherwise.

Coordinator, 11/24 (Noah's rule: fix every bug found): an approved art row that silently does not apply in a standard
build must never ship. The 11/21 head build applied kit 07H0 but skipped its sleeve texture (kit_fixes_2026_b81u
07H0 skipped_textures [3]: the row was pinned to the v0.9 sleeve, and the swoosh step writes that sleeve first), and
nothing reported it. The build's non-strict skipping stays, on purpose, for users' own discs (a texture the user's
recipe replaced keeps the user's art, the Edwards relief fix); this check is for the release's own standard build,
run on its Studio receipt at the final clean build (runbook, the final build's capture check).

It reads the receipt's own skip records:
  - receipt["left_out"]: an optional art step that failed and was left out;
  - a step's kept_retail rows (the shared texture project: Team Select cards, minis, helmets and every texture edit
    of the league project that kept the retail picture);
  - on the art steps below: skipped_kits, a kit whose state is not applied, a kit's skipped_textures, skipped_slots,
    a skipped list, a menu slot that is neither applied nor not applicable, and a step state of left_out or failed.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

#: The build's uniform, kit, glyph and menu-picture steps (mod_build.OPTIONAL_STEPS, its first group) and the other
#: steps that write kit art. A step whose name starts with one of these is judged.
ART_STEP_PREFIXES = (
    "kit_fixes_2026", "glyph_fixes_2026", "relief_2026", "sideline_2026", "pants_hem_2026", "nameplate_fixes_2026",
    "team_sleeves", "moment_kits", "era_kits", "unc_bowl_uniforms", "nyg_shoulder_numbers", "menu_icon_",
    "menu_helmet_", "menu_chiefs_", "modern_helmets",
)
#: Kit record states that mean the row's art is on the disc: written now (applied, repaired by the far-player atlas,
#: composed by the era kits), already there (already, already_applied) or nothing to change (unchanged). Every other
#: state is a row the build did not apply: other_uniform, other_image, other_atlas, field_differs, after_differs,
#: absent, retail_label, donor_absent, skipped_all.
APPLIED = ("applied", "already_applied", "already", "repaired", "composed", "unchanged", "filled", "solid")
SLOT_OK = ("applied", "already_applied", "not_applicable")


def is_art_step(name: object) -> bool:
    return isinstance(name, str) and name.startswith(ART_STEP_PREFIXES)


def _items(value):
    if isinstance(value, dict):
        return list(value.items())
    if isinstance(value, (list, tuple)):
        return [(None, item) for item in value]
    return []


def _label(item) -> str:
    if isinstance(item, dict):
        for key in ("selector", "asset_id", "kit", "slot", "member", "name", "message"):
            if item.get(key) is not None:
                return str(item[key])
        return json.dumps(item, sort_keys=True)[:120]
    return str(item)


def problems(receipt: dict) -> list[str]:
    """One plain line per art row the build did not apply; empty when every row applied."""
    out: list[str] = []
    for row in receipt.get("left_out") or ():
        if isinstance(row, dict) and is_art_step(row.get("step")):
            out.append(f"{row['step']}: the whole step was left out ({row.get('reason', 'no reason recorded')})")
    for step in receipt.get("steps") or ():
        if not isinstance(step, dict):
            continue
        name = str(step.get("step", "?"))
        for row in step.get("kept_retail") or ():
            out.append(f"{name}: kept the retail picture for {_label(row)}")
        if not is_art_step(name):
            continue
        for state_key in ("state", "status"):
            if step.get(state_key) in ("left_out", "failed"):
                out.append(f"{name}: step {state_key} {step[state_key]}")
        for key, item in _items(step.get("skipped_kits")):
            out.append(f"{name}: kit {key if key is not None else _label(item)} skipped")
        for kit in step.get("kits") or ():
            if not isinstance(kit, dict):
                continue
            label = _label(kit)
            if kit.get("state") is not None and kit["state"] not in APPLIED:
                out.append(f"{name}: kit {label} {kit['state']}")
            for texture in kit.get("skipped_textures") or ():
                out.append(f"{name}: kit {label} texture {texture} not applied")
        for key in ("skipped_slots", "skipped"):
            for _key, item in _items(step.get(key)):
                out.append(f"{name}: {key[:-1] if key.endswith('s') else key} {_label(item)}")
        for slot in step.get("slots") or ():
            if isinstance(slot, dict) and slot.get("state") is not None and slot["state"] not in SLOT_OK:
                out.append(f"{name}: slot {_label(slot)} {slot['state']}")
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2])
        return 2
    receipt = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    found = problems(receipt)
    judged = sum(1 for step in receipt.get("steps") or () if isinstance(step, dict) and is_art_step(step.get("step")))
    if found:
        print(f"RELEASE ROW CHECK FAILED: {len(found)} art row(s) not applied on this build ({judged} art steps read)")
        for line in found:
            print("  " + line)
        return 1
    print(f"RELEASE ROW CHECK PASSED: every kit, glyph and card row applied ({judged} art steps read)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
