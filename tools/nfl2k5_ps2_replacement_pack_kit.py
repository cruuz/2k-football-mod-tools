#!/usr/bin/env python3
"""Wrap an exported NFL 2K5 PS2 replacement pack as a kit per emulator.

One pack, three emulators, three different sets of words.  The files an export
writes are the same bytes whichever build loads them -- there is one spelling
of a GS identity -- but PCSX2 v1.7.4034 began hashing only a texture's clamped
draw region, and PenguinScreen2's ``ClassicTextureNames`` restores the original
whole-texture hashing, so what a user must switch on differs.  A pack's receipt
records the one emulator it was exported for.  Handing the same pack to a
second build (to compare them, or because two people run different ones) means
carrying the other build's instructions by hand, which is where the wrong
setting gets copied.

This tool does that carrying.  Given an exported pack it writes, per requested
target::

    <out>/<target>/
        HOW-TO.txt        what to do, in this emulator's terms
        settings.ini      the setting lines to paste, and nothing else
        kit.v1.json       what this kit is, and of what
        pack/             a byte-identical copy of the exported pack

``pack/`` is copied file for file, digest for digest -- receipt and mapping
manifest included -- so the copy is still exactly what
``nfl2k5_ps2_replacement_pack_verify.py`` verifies (point it at ``<kit>/pack``)
and what ``..._audit.py`` audits.  The kit's own three files sit *outside* it,
because the verifier fails a pack holding anything it does not list, and being
kittable must not cost a pack its verifiability.

Nothing here rewrites a pack.  If a kit's target is not the target the receipt
names, ``HOW-TO.txt`` says so in as many words -- the files are the same, the
settings are not -- rather than quietly implying the pack was made for it.

Like the verifier, this tool restates each target's settings instead of
importing them from the exporter: a copy that derives its facts from the thing
it is packaging agrees with it by construction.  A pack whose receipt names
settings this table does not is refused, so the restatement cannot rot in
silence.  ``--selftest`` proves all of it against synthetic fixtures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

SERIAL = "SLUS-20919"
RECEIPT_NAME = "nfl2k5-ps2-export-receipt.v1.json"
KIT_NAME = "kit.v1.json"
KIT_SCHEMA = "nfl2k5-ps2-replacement-pack-kit.v1"
REPLACEMENTS_DIR = ("textures", SERIAL, "replacements")

TARGET_PENGUINSCREEN2_CLASSIC = "penguinscreen2_classic"
TARGET_PCSX2_MODERN = "pcsx2_modern"
TARGET_PCSX2_LEGACY = "pcsx2_legacy"
EMULATOR_TARGETS = (
    TARGET_PENGUINSCREEN2_CLASSIC, TARGET_PCSX2_MODERN, TARGET_PCSX2_LEGACY,
)

CLASSIC_NAMES_SETTING = "ClassicTextureNames=true"
LOAD_REPLACEMENTS_SETTING = "LoadTextureReplacements=true"

#: The settings each emulator needs, restated rather than imported. A stock
#: PCSX2 has no Classic Texture Names at all, so naming it there is not a
#: harmless extra -- it sends the reader hunting through a menu that has no
#: such row.
TARGET_SETTINGS = {
    TARGET_PENGUINSCREEN2_CLASSIC: (
        CLASSIC_NAMES_SETTING, LOAD_REPLACEMENTS_SETTING,
    ),
    TARGET_PCSX2_MODERN: (LOAD_REPLACEMENTS_SETTING,),
    TARGET_PCSX2_LEGACY: (LOAD_REPLACEMENTS_SETTING,),
}

#: Who each kit is for, in one line.
TARGET_AUDIENCE = {
    TARGET_PENGUINSCREEN2_CLASSIC: "PenguinScreen2 with Classic Texture Names on",
    TARGET_PCSX2_MODERN: "stock PCSX2 v1.7.4034 and later, including every 2.x release",
    TARGET_PCSX2_LEGACY: "PCSX2 builds older than v1.7.4034",
}

#: Why the settings are what they are. Measured, and said as measured: the
#: clamped-hash class exists and this manifest's names were not observed in it,
#: which is a different claim from "it cannot happen".
TARGET_NOTE = {
    TARGET_PENGUINSCREEN2_CLASSIC: (
        "Classic Texture Names restores the whole-texture hashing these "
        "filenames were computed with (and the old TCC flag in the name, and a "
        "crop at injection), so every file here is looked up whatever the game "
        "does with the texture. This is the emulator these packs have actually "
        "been witnessed rendering on."
    ),
    TARGET_PCSX2_MODERN: (
        "From v1.7.4034 PCSX2 identifies a texture by hashing only its clamped "
        "draw region, so a pack file for a texture the game draws clamped "
        "would be skipped. Measured across the 60 dumps on the test rig: 584 "
        "distinct identities fall in that class, and none of this studio's "
        "texture names is among them -- so every name in this pack is looked "
        "up. Three stock builds (v2.7.469, v2.6.0, v2.9.30) loaded it with "
        "identical pixel counts. There is no Classic Texture Names setting in "
        "stock PCSX2; do not go looking for one."
    ),
    TARGET_PCSX2_LEGACY: (
        "Builds before v1.7.4034 hash the whole texture, which is how these "
        "filenames were computed, so every file matches however the game draws "
        "it. (v1.7.5606 later stopped printing the texture's TCC flag into bit "
        "14 of the last number, but the loader ignores that bit, so the same "
        "files load on newer builds too.)"
    ),
}


class PackKitError(RuntimeError):
    """A pack that cannot be kitted honestly, or an output that already exists."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_receipt(pack: Path) -> Dict[str, Any]:
    receipt_path = pack / RECEIPT_NAME
    if not receipt_path.is_file():
        raise PackKitError(f"no export receipt in {pack}: {RECEIPT_NAME} is missing")
    try:
        document = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PackKitError(f"the export receipt is not readable JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise PackKitError("the export receipt is not a JSON object")
    return document


def _pack_files(pack: Path) -> List[Path]:
    """Every real file in the pack, relative, sorted, links refused.

    A kit is a copy, and a copy that follows a symlink out of the folder is how
    something that was never in the pack ends up in one.
    """

    found: List[Path] = []
    for path in sorted(pack.rglob("*")):
        if path.is_symlink():
            raise PackKitError(f"the pack holds a link, which a kit will not copy: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise PackKitError(f"the pack holds something that is not a file: {path}")
        found.append(path.relative_to(pack))
    if not found:
        raise PackKitError(f"there is nothing in {pack}")
    return found


def check_pack(pack: Path) -> Dict[str, Any]:
    """Read the receipt and prove the folder still matches it.

    Not a substitute for ``nfl2k5_ps2_replacement_pack_verify.py`` -- that tool
    re-derives the filenames themselves. This is the narrower question a copier
    has to ask before copying: does every PNG still hash to what the receipt
    says, and does the receipt name an emulator whose settings this tool knows?
    Kitting a pack that already disagrees with its own receipt would multiply a
    broken pack by three.
    """

    document = _read_receipt(pack)
    target = document.get("emulator_target")
    if target not in EMULATOR_TARGETS:
        raise PackKitError(
            "the receipt does not name an emulator this tool knows: "
            + repr(target) + "; expected one of " + ", ".join(EMULATOR_TARGETS)
        )
    instructions = document.get("instructions")
    if not isinstance(instructions, dict):
        raise PackKitError("the receipt carries no instructions block")
    claimed = tuple(instructions.get("settings") or ())
    expected = TARGET_SETTINGS[target]
    if tuple(claimed) != expected:
        raise PackKitError(
            "the receipt's settings are not " + target + "'s: it names "
            + (", ".join(claimed) or "none") + "; this target needs "
            + ", ".join(expected)
        )

    rows = document.get("files")
    if not isinstance(rows, list) or not rows:
        raise PackKitError("the receipt lists no files")
    files: List[Tuple[str, str]] = []
    for row in rows:
        name = str(row.get("pcsx2_png", ""))
        recorded = str(row.get("sha256", ""))
        if not name or not recorded:
            raise PackKitError("a receipt row has no filename or no digest")
        path = pack.joinpath(*REPLACEMENTS_DIR, name)
        if not path.is_file():
            raise PackKitError(f"the receipt lists a file the pack does not hold: {name}")
        actual = _sha256(path)
        if actual != recorded:
            raise PackKitError(
                f"{name} does not hash to what the receipt recorded "
                f"({actual} vs {recorded}); kit nothing until that is explained"
            )
        files.append((name, recorded))
    return {"receipt": document, "emulator_target": target, "files": files}


def how_to_text(target: str, receipt_target: str) -> str:
    """The kit's instructions, in this emulator's terms.

    When the kit's target is not the one the receipt names, the difference is
    stated rather than papered over: the files are the same, the settings are
    not, and a reader who spots the mismatch in the receipt deserves to find it
    already explained instead of wondering which is wrong.
    """

    settings = TARGET_SETTINGS[target]
    lines = [
        f"NFL 2K5 (PS2) replacement pack -- for {TARGET_AUDIENCE[target]}",
        "",
        "1. Copy the 'textures' folder inside pack/ into your emulator's",
        f"     texture directory, keeping the {'/'.join(REPLACEMENTS_DIR)}",
        "     path intact.",
        "2. Turn on:",
    ]
    lines.extend(f"     * {row}" for row in settings)
    lines.extend([
        "   With texture replacement off the game draws the retail art and the",
        "   pack looks like it did nothing.",
        f"3. Boot your own {SERIAL} disc and go to a moment where the art you",
        "   edited is on screen.",
        "",
        "Why these settings and not others:",
        "  " + TARGET_NOTE[target],
    ])
    if receipt_target != target:
        lines.extend([
            "",
            "About this pack's receipt:",
            f"  pack/{RECEIPT_NAME} records that it was exported for",
            f"  {TARGET_AUDIENCE[receipt_target]}. That is not a mistake and the",
            "  pack has not been altered: the files are the same bytes under the",
            "  same names for every emulator. Only the settings above differ.",
        ])
    return "\n".join(lines) + "\n"


def settings_text(target: str) -> str:
    """The setting lines alone, for pasting into an emulator ini."""

    header = [
        "; NFL 2K5 (PS2) replacement pack -- " + TARGET_AUDIENCE[target],
        "; Paste under [EmuCore/GS] in your emulator's ini, or set the same",
        "; rows in the GUI. Nothing else in this kit needs changing.",
        "",
    ]
    return "\n".join(header + list(TARGET_SETTINGS[target])) + "\n"


def build_kit(pack: Path, out_dir: Path, targets: Sequence[str] = EMULATOR_TARGETS,
              ) -> Dict[str, Any]:
    """Write one kit per target under ``out_dir``. Never overwrites."""

    pack = Path(pack)
    out_dir = Path(out_dir)
    unknown = [row for row in targets if row not in EMULATOR_TARGETS]
    if unknown:
        raise PackKitError("no such emulator target: " + ", ".join(unknown))
    if not targets:
        raise PackKitError("no target asked for; there is nothing to write")

    checked = check_pack(pack)
    receipt_target = checked["emulator_target"]
    members = _pack_files(pack)

    written: Dict[str, Any] = {}
    for target in targets:
        kit_root = out_dir / target
        if kit_root.exists():
            raise PackKitError(f"there is already something there: {kit_root}")
        # Each kit is built whole or not at all: a half-copied pack that looks
        # complete is worse than a refusal.
        staging = Path(tempfile.mkdtemp(prefix=".kit-", dir=str(_ensure(out_dir))))
        try:
            copied = []
            for member in members:
                destination = staging / "pack" / member
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(pack / member, destination)
                copied.append({
                    "path": member.as_posix(), "sha256": _sha256(destination),
                })
            (staging / "HOW-TO.txt").write_text(
                how_to_text(target, receipt_target), encoding="utf-8")
            (staging / "settings.ini").write_text(
                settings_text(target), encoding="utf-8")
            (staging / KIT_NAME).write_text(json.dumps({
                "schema": KIT_SCHEMA,
                "serial": SERIAL,
                # Two targets, deliberately: what this kit's words are for, and
                # what the pack inside it was exported for. They are allowed to
                # differ; they are never allowed to be confused.
                "kit_target": target,
                "receipt_emulator_target": receipt_target,
                "settings": list(TARGET_SETTINGS[target]),
                "pack": {
                    "source": str(pack),
                    "receipt_sha256": _sha256(pack / RECEIPT_NAME),
                    "files": copied,
                },
            }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            staging.replace(kit_root)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        written[target] = {
            "path": str(kit_root),
            "files": len(copied),
            "settings": list(TARGET_SETTINGS[target]),
        }
    return {
        "pack": str(pack),
        "receipt_emulator_target": receipt_target,
        "kits": written,
    }


def _ensure(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


# --------------------------------------------------------------------------
# Selftest


def _synthetic_pack(root: Path, target: str = TARGET_PENGUINSCREEN2_CLASSIC) -> Path:
    """A pack shaped like a real one: two PNGs, a receipt, a manifest copy."""

    # A 1x1 PNG. The kit copies bytes and never decodes them, but a real PNG
    # keeps the fixture honest for anything downstream that does.
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c6300010000050001"
        "0d0a2db40000000049454e44ae426082"
    )
    pack = root / "pack"
    replacements = pack.joinpath(*REPLACEMENTS_DIR)
    replacements.mkdir(parents=True)
    rows = []
    for name in ("0011223344556677-0000000000000000-00001234.png",
                 "1122334455667788-99aabbccddeeff00-00005678.png"):
        (replacements / name).write_bytes(png)
        rows.append({
            "pcsx2_png": name,
            "sha256": hashlib.sha256(png).hexdigest(),
            "xbox_asset_id": "nfl2k5.uniform.demo",
            "source_target": "demo",
        })
    (pack / "nfl2k5-xbox-map.v1.json").write_text('{"rows": []}\n', encoding="utf-8")
    (pack / RECEIPT_NAME).write_text(json.dumps({
        "schema": "nfl2k5-ps2-export-receipt.v1",
        "serial": SERIAL,
        "emulator_target": target,
        "instructions": {
            "settings": list(TARGET_SETTINGS[target]),
            "lines": ["1. Copy it.", "2. Turn it on."],
        },
        "files": rows,
        "provenance": {"disc": SERIAL},
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return pack


def _expect_refusal(what: str, call) -> str:
    try:
        call()
    except PackKitError as exc:
        return str(exc)
    raise AssertionError("a kit was built from " + what + ", and should not have been")


def selftest() -> int:
    """Prove the promises against synthetic fixtures. No game data needed."""

    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        pack = _synthetic_pack(root)
        report = build_kit(pack, root / "kits")
        assert set(report["kits"]) == set(EMULATOR_TARGETS), report

        # 1. The pack inside every kit is the pack, byte for byte -- receipt
        #    and manifest included. A kit that edited the pack would be a
        #    different pack wearing its receipt.
        original = {
            member.as_posix(): (pack / member).read_bytes()
            for member in _pack_files(pack)
        }
        for target in EMULATOR_TARGETS:
            inside = root / "kits" / target / "pack"
            copy = {
                member.as_posix(): (inside / member).read_bytes()
                for member in _pack_files(inside)
            }
            assert copy == original, target

        # 2. Each kit names its own emulator's settings and no others.
        for target in EMULATOR_TARGETS:
            kit_root = root / "kits" / target
            how_to = (kit_root / "HOW-TO.txt").read_text(encoding="utf-8")
            settings = (kit_root / "settings.ini").read_text(encoding="utf-8")
            for row in TARGET_SETTINGS[target]:
                assert row in how_to and row in settings, target
            if target != TARGET_PENGUINSCREEN2_CLASSIC:
                assert CLASSIC_NAMES_SETTING not in how_to, target
                assert CLASSIC_NAMES_SETTING not in settings, target
            document = json.loads((kit_root / KIT_NAME).read_text(encoding="utf-8"))
            assert document["kit_target"] == target, document
            assert document["receipt_emulator_target"] == \
                TARGET_PENGUINSCREEN2_CLASSIC, document
            assert len(document["pack"]["files"]) == len(original), document

        # 3. A kit for another emulator says so, and one for its own does not
        #    need to.
        crossed = (root / "kits" / TARGET_PCSX2_MODERN / "HOW-TO.txt").read_text("utf-8")
        assert "was exported for" in crossed, crossed
        same = (root / "kits" / TARGET_PENGUINSCREEN2_CLASSIC / "HOW-TO.txt").read_text("utf-8")
        assert "was exported for" not in same, same

        rejects = []
        # 4. An output that already exists is refused, not merged into.
        _expect_refusal("an occupied output",
                        lambda: build_kit(pack, root / "kits"))
        rejects.append("existing-output")

        # 5. A pack whose bytes no longer match its receipt is refused.
        mutated = _synthetic_pack(root / "mutated")
        victim = next(mutated.joinpath(*REPLACEMENTS_DIR).glob("*.png"))
        victim.write_bytes(victim.read_bytes() + b"\x00")
        _expect_refusal("a mutated pack",
                        lambda: build_kit(mutated, root / "kits-mutated"))
        rejects.append("mutated-byte")

        # 6. A receipt naming an emulator this tool does not know is refused,
        #    rather than kitted with a guess.
        unknown = _synthetic_pack(root / "unknown")
        document = json.loads((unknown / RECEIPT_NAME).read_text(encoding="utf-8"))
        document["emulator_target"] = "dolphin"
        (unknown / RECEIPT_NAME).write_text(json.dumps(document), encoding="utf-8")
        _expect_refusal("an unknown emulator",
                        lambda: build_kit(unknown, root / "kits-unknown"))
        rejects.append("unknown-emulator-target")

        # 7. A receipt whose settings are not its target's is refused: the
        #    restated table and the exporter disagreeing is exactly the drift
        #    this tool must not paper over.
        crossed_pack = _synthetic_pack(root / "crossed")
        document = json.loads((crossed_pack / RECEIPT_NAME).read_text(encoding="utf-8"))
        document["instructions"]["settings"] = [LOAD_REPLACEMENTS_SETTING]
        (crossed_pack / RECEIPT_NAME).write_text(json.dumps(document), encoding="utf-8")
        _expect_refusal("a receipt with another target's settings",
                        lambda: build_kit(crossed_pack, root / "kits-crossed"))
        rejects.append("crossed-settings")

        # 8. A pack with no receipt at all is refused.
        bare = root / "bare"
        bare.joinpath(*REPLACEMENTS_DIR).mkdir(parents=True)
        _expect_refusal("a pack with no receipt",
                        lambda: build_kit(bare, root / "kits-bare"))
        rejects.append("no-receipt")

    print(
        "NFL2K5_PS2_REPLACEMENT_PACK_KIT_SELFTEST_PASS "
        "targets=" + ",".join(EMULATOR_TARGETS)
        + " copies=byte-identical rejects=" + ",".join(rejects)
    )
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--pack", type=Path, help="the exported replacement pack folder")
    parser.add_argument("--out", type=Path, help="where the kits are written")
    parser.add_argument(
        "--target", action="append", choices=list(EMULATOR_TARGETS),
        help="kit only this emulator; repeatable, defaults to all three",
    )
    parser.add_argument(
        "--selftest", action="store_true",
        help="prove the promises against synthetic fixtures; no game data needed",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.selftest:
        return selftest()
    if not args.pack or not args.out:
        parser.error("--pack and --out are required unless --selftest is given")
    try:
        report = build_kit(args.pack, args.out, tuple(args.target or EMULATOR_TARGETS))
    except PackKitError as exc:
        print("nfl2k5_ps2_replacement_pack_kit: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
