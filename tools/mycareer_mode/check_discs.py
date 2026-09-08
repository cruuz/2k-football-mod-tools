"""Build two disposable generic discs and cold-load two native-created careers.

Development acceptance only. No disc boot, renderer, audio or physical match.
Each image is removed before the next build and before writing any receipt.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.mycareer_mode import build_disc
from tools.nfl2k5_xbe_space import read_requests
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_my_career as legacy
from mod_editor.core import nfl2k5_my_career_save as save
from mod_editor.core import nfl2k5_franchise_autosave as autosave
from tests.nfl2k5_my_career_played_fixture import Machine
from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster


def check(source, requests):
    roster = retail_roster()
    receipts, executables = [], []
    for name, union in (("minimal", mode.REQUESTS), ("full-reservation-union", requests)):
        before = shutil.disk_usage(Path.cwd().anchor).free
        print(f"Building {name}; root free {before} bytes", flush=True)
        with tempfile.TemporaryDirectory(prefix="mycareer-acceptance-") as folder:
            directory = Path(folder).resolve()
            target = directory / "generic.xiso.iso"
            receipt = build_disc.build(source, target, union)
            with target.open("rb") as image:
                off, length = build_disc.disc.image_xbe_extent(image.fileno(), os.fstat(image.fileno()).st_size)
                if not 0 < length <= 16 * 1024**2:
                    raise ValueError("acceptance XBE exceeds its bounded extent")
                payload = build_disc.io.pread(image.fileno(), length, off)
            for owner in (mode, autosave):
                if owner.status(payload) != "applied" or owner.apply(payload)[0] != payload:
                    raise ValueError("disc owner status or unchanged replay differs")
            if hashlib.sha256(payload).hexdigest() != receipt["output_xbe_sha256"]:
                raise ValueError("acceptance readback hash differs")
            executables.append(payload)
        if directory.exists():
            raise AssertionError("acceptance directory survived cleanup")
        receipt.update(layout=name, root_free_before=before,
                       root_free_after=shutil.disk_usage(Path.cwd().anchor).free,
                       acceptance_image_deleted=True, unchanged_replay=True)
        receipts.append(receipt)
    if legacy.allocations(executables[0]) == legacy.allocations(executables[1]):
        raise AssertionError("the two allocator layouts must differ")
    careers = []
    for club in (2, 3):
        with Machine(executables[0]) as m:
            m.create(roster, club=club, preseason=False)
            career = m.native_save(budget=500000000)
            if career is None or save.read(career) is None:
                raise AssertionError("native creation/save did not produce an inline career")
            careers.append(career)
    if careers[0] == careers[1]:
        raise AssertionError("the two native careers must differ")
    reloads = []
    for layout, payload in enumerate(executables):
        with Machine(payload) as m:
            for club, career in zip((2, 3), careers):
                m.cold(roster, career)
                if m.top() != m.labels["apartment"] or m.get(m.state + 56) != club:
                    raise AssertionError("cold career did not return to its own Apartment/club")
                if not m.call("primary"):
                    raise AssertionError("cold career identity did not resolve")
                m.select(2)
                if m.top() != 0x535E70:
                    raise AssertionError("cold MyPlayer card did not open")
                m.frame(0x200)
                if m.top() != m.labels["apartment"]:
                    raise AssertionError("cold card did not return to Apartment")
                reloads.append({"layout": layout, "club": club,
                                "save_sha256": hashlib.sha256(career).hexdigest(),
                                "inline_bytes": len(save.read(career)),
                                "apartment_and_card_return": True})
    return {"schema": "nfl2k5.mycareer.mode3-disc-check.v1",
            "experimental": True, "runtime_witnessed": False,
            "m2b_accepted": False, "m3_accepted": False,
            "images": receipts, "cold_loads": reloads,
            "all_acceptance_images_deleted": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists() or args.receipt.resolve() == args.source.resolve():
        parser.error("receipt must be a separate new file")
    result = check(args.source, read_requests(args.requests))
    args.receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("Two layouts and four cold loads passed; both acceptance discs deleted.")
