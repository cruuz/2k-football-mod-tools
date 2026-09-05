"""Executable patches for Madden NFL 09 (PS2): the whole interface, every translation refused.

A gameplay change that no data file carries has to be a change to the boot ELF
``SLUS_217.70`` -- 32-bit MIPS words at EE addresses, delivered as a PCSX2
``.pnach`` first, exactly as the sibling PS2 module delivers its own.  This
lane is that pipeline, complete and tested, with **nothing mapped**: a future
PR that locates one site fills in a single entry of :data:`TRANSLATIONS` and
changes nothing else.

**Why the catalogue looks like this.**  There is no host tool with a Madden 09
patch list to read, the way the sibling module reads the Xbox studio's own
panel.  Inventing addresses would be worse than having none, so the catalogue
is the *subject areas* the owner's Madden 09 static-analysis work has opened
[S] -- named, described, and each one carrying the plain statement that no
word has been located for it.  A target here is a question, not a capability,
and :meth:`Madden09CodePatchLane.translation` refuses every one of them by
name.  The registry files this lane ``unknown``, so the studio draws no
editor for it at all; the page states the classification and the reason.

**No retail address and no code byte appears in this file.**  What is measured
here comes from the user's own image at run time: the ELF's program headers,
its SHA-256 and its PCSX2 CRC.

Run it without a window::

    python3 -m mod_editor.games.madden09_ps2.code_patches --selftest
    python3 -m mod_editor.games.madden09_ps2.code_patches --source DISC.iso

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from mod_editor.games._formats import ps2_elf
from mod_editor.games.contract import (
    Artifact,
    Catalogue,
    CodePatch,
    Edit,
    Field,
    GameIdentity,
    MipsPatch,
    MipsWord,
    Plan,
    Receipt,
    Refusal,
    Target,
    Verdict,
    require,
)

from . import containers

_ROOT = Path(__file__).resolve().parents[3]
_TOOLS = _ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import ps2_iso9660 as iso_lib  # noqa: E402

CAPABILITY_ID = "madden09ps2.gameplay.executable_patches"
#: Deliberately not ``gameplay.executable_patches``, which is what the sibling
#: PS2 module calls its own: the conformance harness gives each lane a working
#: directory named after its ``lane_id`` and shares one root across every
#: hosted game, so two games using the same short id collide on it.  Capability
#: ids are already game-scoped; this keeps the short id distinct too, and says
#: what the lane patches while it is at it.
LANE_ID = "gameplay.boot_elf_patches"
SURFACE = "gameplay_tuning_sliders"
RECIPE_SCHEMA = "madden09_ps2_code_patch_recipe/v1"
CATALOG_SCHEMA = "madden09_ps2_code_patch_catalog/v1"
WRITE_SCHEMA = "madden09_ps2_code_patch_write/v1"

NOT_MAPPED = (
    "{patch_id} is not mapped to MIPS yet: no site in {boot} has been located for it, so "
    "there is nothing to translate. A recipe may carry hand-authored words while a "
    "translation is being proved; see docs/product/PS2_CODE_PATCH_PIPELINE.md."
)

#: The subject areas a Madden 09 executable patch would reach, as the owner's
#: own static-analysis repository has opened them [S]: each name below is one
#: of that work's requirement documents, restated here as a question this lane
#: cannot yet answer.  **No address, offset or code byte is carried** -- only
#: the name of the behaviour and the fact that nothing is located.
PROPOSED_PATCHES: tuple[tuple[str, str, str], ...] = (
    ("ai_play_calling",
     "AI play calling",
     "Which play the CPU coach selects, and the weights behind it."),
    ("block_dominance",
     "Blocking dominance",
     "How a one-on-one block resolves between a blocker and a rusher."),
    ("blocking_intent",
     "Blocking assignment intent",
     "Which defender each blocker picks up before the snap resolves."),
    ("catch_and_fumble",
     "Catch and fumble outcomes",
     "The reception and ball-security rolls at the catch point."),
    ("defense_fatigue",
     "Defensive fatigue",
     "How fast defenders tire, and what tiring costs them."),
    ("double_team",
     "Double teams",
     "When two blockers commit to one rusher and when one peels off."),
)

#: patch_id -> translator(parameters) -> words.  **Empty: nothing is mapped.**
#: A future PR adds one entry per proved patch and its tests; the rest of this
#: file does not change.
TRANSLATIONS: Dict[str, Callable[[Mapping[str, Any]], tuple[MipsWord, ...]]] = {}

#: The synthetic executable the conformance harness proves the lane on.  Seven
#: real R5900 words of a do-nothing leaf function, written here from the
#: instruction encoding, not lifted from any image.
SYNTHETIC_BASE = 0x00100000
SYNTHETIC_WORDS = (0x27BDFFF0, 0xAFBF0000, 0x24020001, 0x8FBF0000,
                   0x27BD0010, 0x03E00008, 0x00000000)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hex(value: int) -> str:
    return f"{value & 0xFFFFFFFF:08X}"


def _word_value(value: Any, what: str) -> int:
    if isinstance(value, bool):
        raise Refusal(f"{what} must be a 32-bit word, not a boolean.")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 16) if not value.lower().startswith("0x") else int(value, 0)
        except ValueError as exc:
            raise Refusal(
                f"{what} is {value!r}, which is not a 32-bit hexadecimal word; write it "
                f"as eight hex digits."
            ) from exc
    raise Refusal(f"{what} is {value!r}; give a 32-bit word as an int or eight hex digits.")


def _words_from(values: Sequence[Any], patch_id: str) -> tuple[MipsWord, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or not values:
        raise Refusal(f"{patch_id}: 'mips' must be a non-empty list of word rows.")
    words: List[MipsWord] = []
    for number, row in enumerate(values):
        if not isinstance(row, Mapping):
            raise Refusal(f"{patch_id}: word {number} must be a mapping with address, original and replacement.")
        unknown = sorted(set(row) - {"address", "original", "replacement"})
        if unknown:
            raise Refusal(f"{patch_id}: word {number} carries {', '.join(unknown)}; give address, original and replacement only.")
        words.append(MipsWord(
            address=_word_value(row.get("address"), f"{patch_id} word {number} address"),
            original=_word_value(row.get("original"), f"{patch_id} word {number} original"),
            replacement=_word_value(row.get("replacement"), f"{patch_id} word {number} replacement"),
        ))
    return tuple(words)


def proposed_patches() -> tuple[CodePatch, ...]:
    """The lane's catalogue: named questions, every one unmapped."""

    return tuple(
        CodePatch(
            patch_id=patch_id,
            title=title,
            surface=SURFACE,
            parameters={"enabled": {"type": "bool", "default": False}},
            host_site={
                "executable": containers.BOOT_FILE,
                "serial": containers.SERIAL,
                "kind": "code",
                "flag": patch_id,
                "catalogue": "proposal; no host tool carries a Madden 09 patch list",
                "applier": None,
            },
            note=f"{note} No word has been located for it.",
        )
        for patch_id, title, note in PROPOSED_PATCHES
    )


class Madden09CodePatchLane:
    """The executable-patch lane for SLUS-21770: interface complete, nothing translated."""

    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = SURFACE
    page = "gameplay"
    title = "Executable patches (pnach-first; no translation mapped yet)"
    classification = "unknown"
    recipe_schema = RECIPE_SCHEMA
    validators = (
        "tools/validate_madden09_ps2_code_patches.sh",
        "tools/validate_madden09_ps2_code_patches.bat",
    )
    fixed_allocation = False

    def __init__(self, identity: GameIdentity) -> None:
        self.identity = identity

    # -- the code-patch protocol ---------------------------------------

    def patches(self) -> tuple[CodePatch, ...]:
        return proposed_patches()

    def translation(self, patch_id: str, parameters: Mapping[str, Any]) -> MipsPatch:
        known = {patch.patch_id for patch in self.patches()}
        require(patch_id in known,
                f"{patch_id!r} is not one of this lane's {len(known)} proposed patches; "
                f"choose one of {', '.join(sorted(known))}.")
        translator = TRANSLATIONS.get(patch_id)
        if translator is None:
            raise Refusal(NOT_MAPPED.format(patch_id=patch_id, boot=containers.BOOT_FILE))
        return MipsPatch(patch_id, translator(parameters), self._retail_identity(),
                         parameters, "translated")

    def emit_pnach(self, patches: Sequence[MipsPatch], crc: str) -> str:
        require(bool(patches), "A pnach needs at least one patch.")
        comments = [f"{patch.patch_id}: {patch.note or 'translated'}" for patch in patches]
        comments.append(
            "Emitted by the PS2 Madden 09 module's executable-patch lane; every word was "
            "checked against the boot ELF it names."
        )
        words = [ps2_elf.PnachPatch(word.address, word.replacement)
                 for patch in patches for word in patch.words]
        return ps2_elf.emit_pnach(f"Madden NFL 09 ({containers.SERIAL})", crc, words, comments)

    def verify_pnach(self, pnach_text: str, source: Path,
                     expected: Sequence[MipsPatch]) -> Verdict:
        try:
            document = ps2_elf.parse_pnach(pnach_text)
        except ps2_elf.PnachError as exc:
            return Verdict(False, f"Verification failed: {exc}")
        try:
            elf, _boot = ps2_elf.read_boot_elf(Path(source))
            segments = ps2_elf.parse_program_headers(elf, containers.BOOT_FILE)
        except Refusal as exc:
            return Verdict(False, f"Verification failed: {exc}")
        crc = ps2_elf.pcsx2_crc(elf)
        if document.crc != crc:
            return Verdict(False, f"Verification failed: the pnach names CRC {document.crc} "
                                  f"but this boot ELF's CRC is {crc}.")
        wanted = {word.address: word for patch in expected for word in patch.words}
        found = {patch.address: patch for patch in document.patches}
        missing = sorted(set(wanted) - set(found))
        extra = sorted(set(found) - set(wanted))
        if missing or extra:
            return Verdict(False, "Verification failed: the pnach declares "
                           + (f"undeclared addresses {[_hex(a) for a in extra]}" if extra else "")
                           + (" and " if extra and missing else "")
                           + (f"misses {[_hex(a) for a in missing]}" if missing else "") + ".")
        for address, word in wanted.items():
            if found[address].value != word.replacement:
                return Verdict(False, f"Verification failed: {_hex(address)} writes "
                                      f"{_hex(found[address].value)}, not {_hex(word.replacement)}.")
            if not found[address].enabled:
                return Verdict(False, f"Verification failed: the line for {_hex(address)} is disabled.")
            try:
                original = ps2_elf.read_word(elf, segments, address)
            except ps2_elf.PnachError as exc:
                return Verdict(False, f"Verification failed: {exc}")
            if original != word.original:
                return Verdict(False, f"Verification failed: the ELF holds {_hex(original)} at "
                                      f"{_hex(address)}, not the {_hex(word.original)} the recipe expects.")
        return Verdict(True,
                       f"{len(wanted)} word(s) verified against the boot ELF (CRC {crc}); "
                       f"nothing else declared.",
                       {"result": "PASS", "crc": crc, "words": len(wanted)})

    # -- the lane protocol ---------------------------------------------

    def _retail_identity(self) -> Dict[str, Any]:
        return {
            "serial": containers.SERIAL,
            "boot_file": containers.BOOT_FILE,
            "sha256": self.identity.executable_sha256[0] if self.identity.executable_sha256 else None,
            "pcsx2_crc": containers.RETAIL_ELF_CRC,
        }

    def _elf(self, source: Path):
        elf, boot = ps2_elf.read_boot_elf(Path(source))
        segments = ps2_elf.parse_program_headers(elf, boot.get("boot_file") or containers.BOOT_FILE)
        digest = _sha256(elf)
        editions = {
            containers.RETAIL_BOOT_ELF_SHA256: containers.RETAIL_EDITION,
            containers.DELUXE_BOOT_ELF_SHA256: containers.DELUXE_EDITION,
        }
        identity = {
            "serial": boot.get("serial"),
            "boot_file": boot.get("boot_file"),
            "sha256": digest,
            "pcsx2_crc": ps2_elf.pcsx2_crc(elf),
            "edition": editions.get(digest, "unknown"),
            "retail": digest in self.identity.executable_sha256,
            "segments": [
                {"index": s.index, "offset": s.offset, "vaddr": s.vaddr,
                 "filesz": s.filesz, "memsz": s.memsz, "executable": s.executable}
                for s in segments
            ],
        }
        return elf, segments, identity

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue:
        if progress is not None:
            progress("Reading the boot ELF…")
        _elf, _segments, identity = self._elf(Path(source))
        rows: List[Dict[str, Any]] = []
        targets: List[Target] = []
        for patch in self.patches():
            mapped = patch.patch_id in TRANSLATIONS
            row = {
                "patch_id": patch.patch_id,
                "title": patch.title,
                "surface": patch.surface,
                "mapped": mapped,
                "note": patch.note,
            }
            rows.append(row)
            targets.append(Target(
                key=patch.patch_id,
                label=f"{patch.title} — {'translated' if mapped else 'no site located yet'}",
                detail=patch.note,
                budget="32-bit words at EE addresses inside the boot ELF; delivered as a pnach",
                searchable=f"{patch.patch_id} {patch.title}",
                raw=row,
                fields=(
                    Field("enabled", "bool", "Enabled",
                          "Turn the patch on. It cannot be translated yet, so this is refused."),
                    Field("mips", "note", "Hand-authored words",
                          "A maintainer proving a translation may hand this lane its own "
                          "address/original/replacement rows through the recipe.",
                          read_only=True),
                ),
            ))
        document = {
            "schema": CATALOG_SCHEMA,
            "elf": identity,
            "patches": rows,
            "translations_available": sum(1 for row in rows if row["mapped"]),
        }
        return Catalogue(CATALOG_SCHEMA, self.lane_id, str(source), tuple(targets), document)

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        unknown = sorted(set(values) - {"enabled", "parameters", "mips"})
        if unknown:
            return (f"{target.key}: {', '.join(unknown)} is not something this lane takes; "
                    f"give parameters, or hand-authored mips words.")
        if values.get("mips") is not None:
            try:
                _words_from(values["mips"], target.key)
            except Refusal as exc:
                return str(exc)
            return None
        parameters = values.get("parameters", {})
        if not isinstance(parameters, Mapping):
            return f"{target.key}: parameters must be a mapping of parameter names to values."
        if not target.raw.get("mapped"):
            return NOT_MAPPED.format(patch_id=target.key, boot=containers.BOOT_FILE)
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows = []
        for edit in edits:
            row: Dict[str, Any] = {
                "patch": edit.target_key,
                "parameters": dict(edit.values.get("parameters", {}) or {}),
            }
            if edit.values.get("mips") is not None:
                row["mips"] = [
                    {"address": _hex(_word_value(item["address"], "address")),
                     "original": _hex(_word_value(item["original"], "original")),
                     "replacement": _hex(_word_value(item["replacement"], "replacement"))}
                    for item in edit.values["mips"]
                ]
            if edit.note:
                row["note"] = edit.note
            rows.append(row)
        return {"schema": RECIPE_SCHEMA, "patches": rows}

    def _entries(self, recipe: Mapping[str, Any]) -> List[Dict[str, Any]]:
        require(isinstance(recipe, Mapping) and recipe.get("schema") == RECIPE_SCHEMA,
                f"recipe schema is "
                f"{recipe.get('schema') if isinstance(recipe, Mapping) else recipe!r}, "
                f"expected {RECIPE_SCHEMA}")
        rows = recipe.get("patches")
        require(isinstance(rows, list) and rows, "a recipe must carry a non-empty 'patches' list")
        seen: set = set()
        entries = []
        for number, row in enumerate(rows):
            require(isinstance(row, Mapping) and isinstance(row.get("patch"), str) and row["patch"],
                    f"patch {number} must name the patch it translates")
            require(set(row) <= {"patch", "parameters", "mips", "note"},
                    f"patch {number} carries unknown keys")
            require(row["patch"] not in seen,
                    f"{row['patch']} appears twice; one patch is delivered once")
            seen.add(row["patch"])
            entries.append(dict(row))
        return entries

    def _mips(self, entry: Mapping[str, Any], identity: Mapping[str, Any]) -> MipsPatch:
        parameters = entry.get("parameters") or {}
        require(isinstance(parameters, Mapping), f"{entry['patch']}: parameters must be a mapping")
        if entry.get("mips") is not None:
            return MipsPatch(entry["patch"], _words_from(entry["mips"], entry["patch"]),
                             identity, parameters, str(entry.get("note") or "hand-authored"))
        return self.translation(entry["patch"], parameters)

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        entries = self._entries(recipe)
        elf, segments, identity = self._elf(Path(source))
        catalogued = catalogue.document.get("elf", {})
        require(identity["sha256"] == catalogued.get("sha256"),
                "the boot ELF changed since it was catalogued; rebuild the catalogue from this image")
        patches = []
        seen_addresses: set = set()
        for entry in entries:
            catalogue.target(entry["patch"])  # the catalogue's own sentence for an unknown patch
            patch = self._mips(entry, identity)
            for word in patch.words:
                require(word.address not in seen_addresses,
                        f"{patch.patch_id}: {_hex(word.address)} is written twice in this recipe")
                seen_addresses.add(word.address)
                try:
                    actual = ps2_elf.read_word(elf, segments, word.address)
                except ps2_elf.PnachError as exc:
                    raise Refusal(f"{patch.patch_id}: {exc}") from exc
                require(actual == word.original,
                        f"{patch.patch_id}: the ELF holds {_hex(actual)} at {_hex(word.address)}, "
                        f"not the {_hex(word.original)} the recipe expects; these words were not "
                        f"derived against this executable")
            patches.append(patch)
        return Plan(self.lane_id, tuple(entry["patch"] for entry in entries), (), {
            "crc": identity["pcsx2_crc"],
            "elf_sha256": identity["sha256"],
            "patches": [self._patch_row(patch) for patch in patches],
        })

    @staticmethod
    def _patch_row(patch: MipsPatch) -> Dict[str, Any]:
        return {"patch_id": patch.patch_id, "note": patch.note,
                "parameters": dict(patch.parameters),
                "words": [{"address": _hex(w.address), "original": _hex(w.original),
                           "replacement": _hex(w.replacement)} for w in patch.words]}

    @staticmethod
    def _patches_from_rows(rows: Sequence[Mapping[str, Any]],
                           identity: Mapping[str, Any]) -> List[MipsPatch]:
        return [MipsPatch(row["patch_id"], _words_from(row["words"], row["patch_id"]),
                          identity, row.get("parameters", {}), str(row.get("note", "")))
                for row in rows]

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        source, destination = Path(source), Path(destination)
        require(destination.resolve() != source.resolve(),
                f"{destination} is the source image; a pnach is a NEW file beside it.")
        require(not destination.exists(),
                f"destination {destination} already exists; refusing to overwrite")
        planned = self.plan(source, recipe, catalogue)
        identity = dict(catalogue.document["elf"])
        patches = self._patches_from_rows(planned.document["patches"], identity)
        payload = self.emit_pnach(patches, planned.document["crc"]).encode("utf-8")
        try:
            with open(destination, "xb") as handle:  # exclusive: never overwrites
                handle.write(payload)
        except FileExistsError as exc:
            raise Refusal(f"destination {destination} appeared meanwhile; refusing to overwrite") from exc
        digest = _sha256(payload)
        document = {
            "schema": WRITE_SCHEMA,
            "source": str(source),
            "destination": str(destination),
            "crc": planned.document["crc"],
            "elf": {k: v for k, v in identity.items() if k != "segments"},
            "patches": list(planned.document["patches"]),
            "pnach_sha256": digest,
            "delivery": "pnach",
            "note": "Drop the file in PCSX2's patches folder as <CRC>.pnach; nothing on the disc changed.",
        }
        return Receipt(WRITE_SCHEMA, self.lane_id, str(source), str(destination), (), document,
                       artifacts=(Artifact(str(destination), digest, "pnach"),))

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        destination = Path(destination)
        try:
            payload = destination.read_bytes()
        except OSError as exc:
            return Verdict(False, f"Verification failed: {exc}")
        for artifact in receipt.artifacts:
            if Path(artifact.path) == destination and _sha256(payload) != artifact.sha256:
                return Verdict(False, "Verification failed: the pnach on disk is not the file "
                                      "the receipt recorded.")
        try:
            expected = self._patches_from_rows(receipt.document.get("patches", []),
                                               dict(receipt.document.get("elf", {})))
        except Refusal as exc:
            return Verdict(False, f"Verification failed: the receipt is malformed: {exc}")
        if not expected:
            return Verdict(False, "Verification failed: the receipt declares no patches.")
        return self.verify_pnach(payload.decode("utf-8", "replace"), Path(source), expected)

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        elf = ps2_elf.build_synthetic_elf(SYNTHETIC_WORDS, base_vaddr=SYNTHETIC_BASE)
        boot = (f"BOOT2 = cdrom0:\\{containers.BOOT_FILE};1\r\nVER = 1.00\r\n"
                f"VMODE = NTSC\r\n").encode("ascii")
        image = iso_lib.build_synthetic_iso(
            files=[
                (b"SYSTEM.CNF;1", boot),
                (f"{containers.BOOT_FILE};1".encode("ascii"), elf),
            ],
            sub_name=b"DATA",
            sub_files=[(b"GAMEDATA.DAT;1", bytes(2048))],
        )
        path = Path(work_dir) / "madden09-ps2-code-synthetic.iso"
        path.write_bytes(image)
        return path

    def conformance_edits(self, catalogue: Catalogue) -> tuple[Edit, ...]:
        first = catalogue.targets[0].key
        return (Edit(first, {"mips": [{
            "address": _hex(SYNTHETIC_BASE + 8),
            "original": _hex(SYNTHETIC_WORDS[2]),
            "replacement": _hex(SYNTHETIC_WORDS[2] ^ 0x1),
        }]}, note="conformance: hand-authored words against the synthetic ELF"),)


# --------------------------------------------------------------------------
# Command line and self-test
# --------------------------------------------------------------------------

def _lane() -> Madden09CodePatchLane:
    from . import IDENTITY  # this module's identity; imported here so the file stays a plain module

    return Madden09CodePatchLane(IDENTITY)


def selftest() -> int:
    """Prove the whole pipeline on a synthetic ELF; needs no game data."""

    import tempfile

    lane = _lane()
    failures: List[str] = []
    with tempfile.TemporaryDirectory() as work:
        room = Path(work)
        source = lane.synthetic_source(room)
        catalogue = lane.build_catalogue(source)
        if not catalogue.targets:
            failures.append("the catalogue named no patches")
        for patch in lane.patches():
            try:
                lane.translation(patch.patch_id, {})
            except Refusal as exc:
                if "not mapped" not in str(exc):
                    failures.append(f"{patch.patch_id}: unexpected refusal {exc}")
            else:
                failures.append(f"{patch.patch_id}: a translation exists but TRANSLATIONS is empty")
        edits = lane.conformance_edits(catalogue)
        recipe = lane.compose_recipe(edits)
        plan = lane.plan(source, recipe, catalogue)
        if not plan.document["patches"]:
            failures.append("the plan declared no words")
        out = room / "madden09.pnach"
        receipt = lane.build(source, out, recipe, catalogue)
        verdict = lane.verify(source, out, receipt)
        if not verdict.passed:
            failures.append(f"verify failed: {verdict.summary}")
        tampered = out.read_text(encoding="utf-8").replace(
            _hex(SYNTHETIC_WORDS[2] ^ 0x1), _hex(SYNTHETIC_WORDS[2] ^ 0x2))
        bad = room / "tampered.pnach"
        bad.write_text(tampered, encoding="utf-8", newline="\n")
        if lane.verify(source, bad, receipt).passed:
            failures.append("verify passed a tampered pnach")
        try:
            lane.build(source, out, recipe, catalogue)
        except Refusal:
            pass
        else:
            failures.append("build overwrote an existing destination")
    for line in failures:
        print(f"FAIL {line}", file=sys.stderr)
    print("CODE_PATCH_SELFTEST %s patches=%d translations=%d"
          % ("PASS" if not failures else "FAIL", len(PROPOSED_PATCHES), len(TRANSLATIONS)))
    return 1 if failures else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mod_editor.games.madden09_ps2.code_patches",
        description="Madden NFL 09 (PS2) executable patches: catalogue and pnach pipeline.",
    )
    parser.add_argument("--source", help="the user's own SLUS-21770 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--selftest", action="store_true",
                        help="prove the pipeline on a synthetic ELF; needs no game data")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    if arguments.selftest:
        return selftest()
    if not arguments.source:
        parser.error("give --source DISC.iso, or --selftest")
    lane = _lane()
    try:
        catalogue = lane.build_catalogue(Path(arguments.source))
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = dict(catalogue.document)
    if arguments.out:
        Path(arguments.out).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
    elf = document["elf"]
    print("CODE_PATCHES patches=%d mapped=%d edition=%s crc=%s"
          % (len(document["patches"]), document["translations_available"],
             elf["edition"], elf["pcsx2_crc"]))
    return 0


__all__ = ["CAPABILITY_ID", "CATALOG_SCHEMA", "LANE_ID", "Madden09CodePatchLane",
           "NOT_MAPPED", "PROPOSED_PATCHES", "RECIPE_SCHEMA", "SURFACE",
           "SYNTHETIC_BASE", "SYNTHETIC_WORDS", "TRANSLATIONS", "WRITE_SCHEMA",
           "proposed_patches", "selftest"]


if __name__ == "__main__":
    raise SystemExit(main())
