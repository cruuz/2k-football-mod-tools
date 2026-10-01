"""Offline catalog preparation and review of E2's retained lab witnesses."""
from pathlib import Path
import argparse
import json
import os
import re
import struct
import sys

ROOT = Path(os.environ.get("E2_STACK", Path(__file__).resolve().parents[1]))
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from lab_memory import canonical_play, make_catalog, sha


def verify_witness(directory, disc, output):
    """Review available sides without upgrading an incomplete run to acceptance."""
    directory = Path(directory)
    row = json.loads((directory / "capture.json").read_text())
    retained = {}
    for span in row["ranges"]:
        raw = (directory / span["file"]).read_bytes()
        if len(raw) != span["size"] or sha(raw) != span["sha256"]:
            raise ValueError(f"missing or changed retained memory: {span['file']}")
        retained[span["file"].split("-", 1)[1]] = (span, raw)
    if row["phase"] != "books":
        raise ValueError("expected a retained book witness")
    catalog = make_catalog(disc, None)
    text = lambda raw: raw.decode("utf-16le").split("\0", 1)[0]
    mode = struct.unpack("<I", retained["mode.bin"][1])[0]
    sides = {}
    for side in ("home", "away"):
        if f"{side}-PLAY.bin" not in retained:
            continue
        span, body = retained[f"{side}-PLAY.bin"]
        pointer = struct.unpack("<I", retained[f"{side}-bound-book.bin"][1])[0]
        if span["address"] != pointer:
            raise ValueError(f"{side}: PLAY slice differs from bound pointer")
        filename = text(retained[f"{side}-book-filename.bin"][1])
        franchise = text(retained[f"{side}-match-team-franchise.bin"][1])
        category = struct.unpack_from("<I", retained[f"{side}-match-team.bin"][1], 0x128)[0]
        expected = ("E2R-" if mode == 8 or category == 4 else "") + franchise + "-pb.iff"
        if filename != expected:
            raise ValueError(f"{side}: wrong book filename {filename}, expected {expected}")
        entry = catalog["books"][filename]
        digest = sha(canonical_play(body, pointer))
        if digest != entry["canonical_sha256"]:
            raise ValueError(f"{side}: PLAY differs from installed book after native group setup")
        sides[side] = dict(filename=filename, pointer=pointer, canonical_sha256=digest,
                           installed_resource_sha256=entry["resource_sha256"], content_matches=True)
    if not sides:
        raise ValueError("no retained PLAY body")
    result = dict(classification="PROVED OFFLINE", retained_books_verified=True,
                  complete_capture=row["ok"] and len(sides) == 2, full_run_verified=False,
                  original_capture_ok=row["ok"], original_error=row.get("error"),
                  normalization=catalog["normalization"], xbe_sha256=catalog["xbe_sha256"], books=sides)
    Path(output).write_text(json.dumps(result, indent=2) + "\n")
    return result


def verify(run, case):
    run = Path(run)
    captures = []
    for path in sorted((run / "witnesses").glob("*/capture.json")):
        row = json.loads(path.read_text())
        if not row["ok"]:
            raise ValueError(f"failed capture: {path}: {row.get('error')}")
        for span in row["ranges"]:
            raw = (path.parent / span["file"]).read_bytes()
            if len(raw) != span["size"] or sha(raw) != span["sha256"]:
                raise ValueError(f"missing or changed retained memory: {path.parent / span['file']}")
        row["directory"] = str(path.parent)
        captures.append(row)
    books = [r for r in captures if r["phase"] == "books"]
    if len(books) < 2:
        raise ValueError("need loaded and later book witnesses")
    ordinals = {"original": 0, "super_bowl": 14, "moment50": 49}
    names = {"original": ("E2R-GB-pb.iff", "E2R-DAL-pb.iff"),
             "super_bowl": ("E2R-NYG-pb.iff", "E2R-BUF-pb.iff"),
             "moment50": ("E2R-KC-pb.iff", "E2R-SF-pb.iff")}
    for row in books:
        pair = tuple(row["books"][side]["filename"] for side in ("home", "away"))
        if case == "mixed":
            if (row["mode"] != 4 or pair[0] != "E2R-CHI-pb.iff" or pair[1].startswith("E2R-")
                    or row["books"]["home"]["team"]["category"] != 4
                    or row["books"]["away"]["team"]["category"] == 4):
                raise ValueError("wrong mixed Quick Game sides")
        elif row["mode"] != 8 or row["ordinal"] != ordinals[case] or pair != names[case]:
            raise ValueError(f"wrong moment or sides for {case}: {pair}")
        for side, item in row["books"].items():
            span = next(s for s in row["ranges"] if s["file"].endswith(f"-{side}-PLAY.bin"))
            raw = (Path(row["directory"]) / span["file"]).read_bytes()
            if (not item["content_matches"] or item["filename"] != item["expected_filename"]
                    or sha(canonical_play(raw, item["pointer"])) != item["expected_sha256"]):
                raise ValueError(f"bound {side} PLAY content did not verify")
    result = dict(memory_verified=True, case=case, book_captures=len(books),
                  filenames=books[0]["books"], rendered_review_required=True)
    if case != "mixed":
        previews = [r for r in captures if r["phase"] == "preview"]
        if len(previews) != 1 or previews[0]["mode"] != 8 or previews[0]["ordinal"] != ordinals[case]:
            raise ValueError("missing exact preview witness")
        venue = previews[0]["historic_venue"]
        ocr = (run / "screens/named-preview.txt").read_text()
        normalize = lambda text: re.sub(r"[^A-Z0-9]", "", text.upper())
        result.update(venue=venue, venue_ocr_match=normalize(venue) in normalize(ocr))
    (run / "e2-verification.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    catalog = sub.add_parser("catalog")
    catalog.add_argument("disc")
    catalog.add_argument("output")
    check = sub.add_parser("verify")
    check.add_argument("run")
    check.add_argument("case", choices=("original", "super_bowl", "moment50", "mixed"))
    witness = sub.add_parser("witness", help="review retained sides against the installed disc; never accepts a full run")
    witness.add_argument("directory")
    witness.add_argument("disc")
    witness.add_argument("output")
    args = parser.parse_args()
    if args.command == "catalog":
        result = make_catalog(args.disc, args.output)
        print(f"PROVED OFFLINE: catalog pins {len(result['books'])} books and the installed venue table")
    elif args.command == "witness":
        result = verify_witness(args.directory, args.disc, args.output)
        print("PROVED OFFLINE: retained sides verified:", ", ".join(result["books"]))
        print("DESIGN: this partial-witness review does not accept a complete lab run")
    else:
        result = verify(args.run, args.case)
        print("PROVED OFFLINE: retained memory verified", args.case,
              "venue OCR match:", result.get("venue_ocr_match", "not a moment"))
        print("DESIGN: main reviews named-preview, loading/intro and after-play frames for rendered acceptance")
        if result.get("venue_ocr_match") is False:
            print("DESIGN: venue OCR did not match; inspect the saved preview frame before accepting")
            return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
