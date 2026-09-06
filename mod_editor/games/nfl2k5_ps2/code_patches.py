"""Executable patches for ESPN NFL 2K5 (PS2): the whole interface, with every translation refused.

The host ships gameplay patches that rewrite x86 code in the Xbox executable
(``mod_editor/core/mod_build.py`` applies the flags the panel
``mod_editor/gui/gameplay_patches_panel_qt.py`` lists).  The PS2 equivalent is
32-bit MIPS words in the boot ELF ``SLUS_209.19``.  Translating a patch means
locating its site in that ELF -- research nobody has done, and no Xbox address
transfers (the repository's own rule).  This lane exists so that a future PR
only fills in :data:`TRANSLATIONS`: everything around a translation is real
and tested today.

* :func:`host_patches` reads the host's semantic catalogue *as the host stores
  it* -- the literal tuples in the panel module, parsed from source so no Qt
  is imported -- into :class:`~mod_editor.games.contract.CodePatch` rows.
* :meth:`Ps2CodePatchLane.translation` returns a ``MipsPatch`` for a mapped
  patch or refuses with the reason; today it refuses everything.
* A recipe may also carry **hand-authored** words (``"mips": [...]``), the
  form a maintainer uses while a translation is being proved.  Planning checks
  every word against the user's own ELF: the address must be file-backed and
  the original word must match, or the plan refuses.
* Delivery is a PCSX2 / PenguinScreen2 ``.pnach`` -- emulator-side first, the
  way textures ship as a replacement pack.  ``verify`` re-parses the pnach and
  re-reads the ELF independently: the CRC the file names must be the ELF's,
  every address must be in the ELF, every original word as expected, and
  nothing else may be declared.  On-disc ELF patching through the
  fixed-allocation ISO writer is the optional second delivery, not built here.

No retail address or code byte appears in this file.  Standard library only.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Optional, Sequence

from mod_editor.games._formats import ps2_elf
from mod_editor.games.contract import (
    Artifact,
    Catalogue,
    CodePatch,
    ContractError,
    Edit,
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

_ROOT = Path(__file__).resolve().parents[3]
_TOOLS = _ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import ps2_iso9660 as iso_lib  # noqa: E402

SERIAL = "SLUS-20919"
BOOT_FILE = "SLUS_209.19"
#: PCSX2 keys the retail disc's patch file by this CRC (an identity, like the serial).
RETAIL_PCSX2_CRC = "42F9D5AF"

CAPABILITY_ID = "nfl2k5ps2.gameplay.executable_patches"
SURFACE = "gameplay_tuning_sliders"
RECIPE_SCHEMA = "nfl2k5_ps2_code_patch_recipe/v1"
CATALOG_SCHEMA = "nfl2k5_ps2_code_patch_catalog/v1"
WRITE_SCHEMA = "nfl2k5_ps2_code_patch_write/v1"

HOST_CATALOGUE = "mod_editor/gui/gameplay_patches_panel_qt.py"
HOST_APPLIER = "mod_editor/core/mod_build.py"
HOST_PIN_MODULE = "mod_editor/core/nfl2k5_bump_strength.py"
HOST_THROW_MODULE = "mod_editor/core/nfl2k5_throw_tuning.py"
HOST_EXECUTABLE = "default.xbe"

NOT_MAPPED = (
    "{patch_id} is not mapped to MIPS yet: no {boot} site has been located for it, so nothing can be "
    "translated. A recipe may carry hand-authored words while a translation is proved; see "
    "docs/product/PS2_CODE_PATCH_PIPELINE.md for the pipeline that fills this in."
)

#: patch_id -> translator(parameters) -> words.  Empty: nothing is mapped today.
#: A future PR adds one entry per proved patch and its tests; nothing else changes.
TRANSLATIONS: dict[str, Callable[[Mapping[str, Any]], tuple[MipsWord, ...]]] = {}

#: The synthetic executable the conformance harness proves the lane on.
SYNTHETIC_BASE = 0x00100000
SYNTHETIC_WORDS = (0x27BDFFF0, 0xAFBF0000, 0x24020001, 0x8FBF0000, 0x27BD0010, 0x03E00008, 0x00000000)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------
# The host's catalogue, read as the host stores it
# --------------------------------------------------------------------------

def _value(node: ast.AST, source: str) -> Any:
    """A literal's value; for any other expression, its source text.

    The host's catalogue is mostly literals, but since Beta 61 an entry may
    quote another module's constant for its on-screen words (``tt.some_patch
    .UI_TEXT``).  That is still the host's catalogue, read as the host stores
    it: the entry's key and title are literals, and the expression's own text
    stands in for the words this reader will not import Qt to resolve.
    """

    if isinstance(node, ast.Tuple):
        return tuple(_value(item, source) for item in node.elts)
    if isinstance(node, ast.List):
        return [_value(item, source) for item in node.elts]
    if isinstance(node, ast.Dict):
        return {_value(key, source): _value(value, source) for key, value in zip(node.keys, node.values)}
    try:
        return ast.literal_eval(node)
    except ValueError:
        return ast.get_source_segment(source, node) or type(node).__name__


def _literal(tree: ast.Module, name: str, path: Path, source: str = "") -> Any:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                if source and isinstance(node.value, (ast.Tuple, ast.List, ast.Dict)):
                    return _value(node.value, source)
                continue
    raise Refusal(f"{path} no longer defines a literal {name}; the host's patch catalogue moved.")


def host_patches(repo_root: Path = _ROOT) -> tuple[CodePatch, ...]:
    """The host tool's executable patches, from its own catalogue module, without importing Qt."""

    path = repo_root / HOST_CATALOGUE
    if not path.is_file():
        raise Refusal(f"The host's patch catalogue {HOST_CATALOGUE} is not in this tree.")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    code_rows = _literal(tree, "PATCHES", path, source)
    text_rows = _literal(tree, "TEXT_PATCHES", path, source)
    string_toggles = _literal(tree, "STRING_TOGGLES", path, source)
    executable_sha256 = None
    pin_path = repo_root / HOST_PIN_MODULE
    if pin_path.is_file():
        try:
            executable_sha256 = _literal(ast.parse(pin_path.read_text(encoding="utf-8")), "RETAIL_XBE_SHA256", pin_path)
        except Refusal:
            executable_sha256 = None
    rows: list[CodePatch] = []
    for kind, entries in (("code", code_rows), ("text", text_rows)):
        for key, title, explanation in entries:
            if key in string_toggles:
                parameters = {key: {"type": "string", "default": string_toggles[key],
                                    "note": "the host writes this profile name when the toggle is on"}}
            else:
                parameters = {"enabled": {"type": "bool", "default": False}}
            rows.append(CodePatch(
                patch_id=key,
                title=title,
                surface=SURFACE,
                parameters=parameters,
                host_site={
                    "executable": HOST_EXECUTABLE,
                    "executable_sha256": executable_sha256,
                    "flag": key,
                    "kind": kind,
                    "catalogue": HOST_CATALOGUE,
                    "applier": HOST_APPLIER,
                },
                note=explanation,
            ))
    throw_path = repo_root / HOST_THROW_MODULE
    if throw_path.is_file():
        throw_tree = ast.parse(throw_path.read_text(encoding="utf-8"))
        try:
            low = _literal(throw_tree, "MIN_MAX_DEEP_YARDS", throw_path)
            high = _literal(throw_tree, "MAX_MAX_DEEP_YARDS", throw_path)
            retail = _literal(throw_tree, "RETAIL_MAX_DEEP_YARDS", throw_path)
        except Refusal:
            low, high, retail = None, None, None
        rows.append(CodePatch(
            patch_id="throw_tuning",
            title="Throw tuning: deep ceiling, arc, realistic flight, arc by distance",
            surface=SURFACE,
            parameters={
                "max_deep_yards": {"type": "float", "min": low, "max": high, "default": retail},
                "arc": {"type": "float", "min": 0.0, "max": 1.0, "default": 0.0},
                "realistic_flight": {"type": "bool", "default": False},
                "arc_by_distance": {"type": "bool", "default": False},
            },
            host_site={
                "executable": HOST_EXECUTABLE,
                "executable_sha256": executable_sha256,
                "flag": "throw",
                "kind": "code",
                "catalogue": HOST_THROW_MODULE,
                "applier": HOST_APPLIER,
            },
            note="The host rewrites named pass-trajectory curves inside the executable's data tables.",
        ))
    return tuple(sorted(rows, key=lambda row: row.patch_id))


# --------------------------------------------------------------------------
# The lane
# --------------------------------------------------------------------------

def _word_value(value: Any, what: str) -> int:
    if isinstance(value, bool):
        raise Refusal(f"{what} must be a 32-bit word, not a boolean.")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 16) if value.lower().startswith("0x") else int(value, 0)
        except ValueError as exc:
            raise Refusal(f"{what} {value!r} is not a hexadecimal word.") from exc
    raise Refusal(f"{what} must be an integer or a hexadecimal string.")


def _words_from(values: Sequence[Any], patch_id: str) -> tuple[MipsWord, ...]:
    require(isinstance(values, (list, tuple)) and values, f"{patch_id}: 'mips' must be a non-empty list of words")
    words = []
    for number, item in enumerate(values):
        require(isinstance(item, Mapping) and set(item) <= {"address", "original", "replacement", "note"}
                and {"address", "original", "replacement"} <= set(item),
                f"{patch_id}: word {number} must carry address, original and replacement")
        try:
            words.append(MipsWord(
                _word_value(item["address"], f"{patch_id} word {number} address"),
                _word_value(item["original"], f"{patch_id} word {number} original"),
                _word_value(item["replacement"], f"{patch_id} word {number} replacement"),
            ))
        except ContractError as exc:
            raise Refusal(f"{patch_id}: {exc}") from exc
    return tuple(words)


def _hex(value: int) -> str:
    return f"0x{value:08X}"


class Ps2CodePatchLane:
    """The executable-patch lane for SLUS-20919: interface complete, translations pending."""

    lane_id = "gameplay.executable_patches"
    capability_id = CAPABILITY_ID
    surface = SURFACE
    title = "Executable patches (pnach-first; no translation mapped yet)"
    classification = "unknown"
    recipe_schema = RECIPE_SCHEMA
    validators = (
        "mod_editor/games/nfl2k5_ps2/validate_code_patches.sh",
        "mod_editor/games/nfl2k5_ps2/validate_code_patches.bat",
    )
    fixed_allocation = False

    def __init__(self, identity: GameIdentity, repo_root: Path = _ROOT) -> None:
        self.identity = identity
        self.repo_root = repo_root
        self._patches: Optional[tuple[CodePatch, ...]] = None

    # -- the code-patch protocol ---------------------------------------

    def patches(self) -> tuple[CodePatch, ...]:
        if self._patches is None:
            self._patches = host_patches(self.repo_root)
        return self._patches

    def translation(self, patch_id: str, parameters: Mapping[str, Any]) -> MipsPatch:
        known = {patch.patch_id for patch in self.patches()}
        require(patch_id in known, f"{patch_id!r} is not one of the host's {len(known)} executable patches.")
        translator = TRANSLATIONS.get(patch_id)
        if translator is None:
            raise Refusal(NOT_MAPPED.format(patch_id=patch_id, boot=BOOT_FILE))
        return MipsPatch(patch_id, translator(parameters), self._retail_identity(), parameters, "translated")

    def emit_pnach(self, patches: Sequence[MipsPatch], crc: str) -> str:
        require(bool(patches), "A pnach needs at least one patch.")
        comments = [f"{patch.patch_id}: {patch.note or 'translated'}" for patch in patches]
        comments.append("Emitted by 2K5 Mod Studio's PS2 executable-patch lane; every word was checked against the boot ELF it names.")
        words = [ps2_elf.PnachPatch(word.address, word.replacement) for patch in patches for word in patch.words]
        return ps2_elf.emit_pnach(f"ESPN NFL 2K5 ({SERIAL})", crc, words, comments)

    def verify_pnach(self, pnach_text: str, source: Path, expected: Sequence[MipsPatch]) -> Verdict:
        try:
            document = ps2_elf.parse_pnach(pnach_text)
        except ps2_elf.PnachError as exc:
            return Verdict(False, f"Verification failed: {exc}")
        try:
            elf, _boot = ps2_elf.read_boot_elf(source)
            segments = ps2_elf.parse_program_headers(elf, BOOT_FILE)
        except Refusal as exc:
            return Verdict(False, f"Verification failed: {exc}")
        crc = ps2_elf.pcsx2_crc(elf)
        if document.crc != crc:
            return Verdict(False, f"Verification failed: the pnach names CRC {document.crc} but the boot ELF's CRC is {crc}.")
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
                return Verdict(False, f"Verification failed: {_hex(address)} writes {_hex(found[address].value)}, not {_hex(word.replacement)}.")
            if not found[address].enabled:
                return Verdict(False, f"Verification failed: the line for {_hex(address)} is disabled.")
            try:
                original = ps2_elf.read_word(elf, segments, address)
            except ps2_elf.PnachError as exc:
                return Verdict(False, f"Verification failed: {exc}")
            if original != word.original:
                return Verdict(False, f"Verification failed: the ELF holds {_hex(original)} at {_hex(address)}, not the {_hex(word.original)} the recipe expects.")
        return Verdict(True, f"{len(wanted)} word(s) verified against the boot ELF (CRC {crc}); nothing else declared.",
                       {"result": "PASS", "crc": crc, "words": len(wanted)})

    # -- the lane protocol ---------------------------------------------

    def _retail_identity(self) -> dict[str, Any]:
        return {"serial": SERIAL, "boot_file": BOOT_FILE,
                "sha256": self.identity.executable_sha256[0] if self.identity.executable_sha256 else None,
                "pcsx2_crc": RETAIL_PCSX2_CRC}

    def _elf(self, source: Path) -> tuple[bytes, tuple[ps2_elf.Segment, ...], dict[str, Any]]:
        elf, boot = ps2_elf.read_boot_elf(Path(source))
        segments = ps2_elf.parse_program_headers(elf, boot.get("boot_file") or BOOT_FILE)
        sha = _sha256(elf)
        identity = {
            "serial": boot.get("serial"),
            "boot_file": boot.get("boot_file"),
            "sha256": sha,
            "pcsx2_crc": ps2_elf.pcsx2_crc(elf),
            "retail": sha in self.identity.executable_sha256,
            "segments": [
                {"index": s.index, "offset": s.offset, "vaddr": s.vaddr, "filesz": s.filesz, "memsz": s.memsz,
                 "executable": s.executable}
                for s in segments
            ],
        }
        return elf, segments, identity

    def build_catalogue(self, source: Path, *, progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        if progress is not None:
            progress("Reading the boot ELF…")
        _elf, _segments, identity = self._elf(source)
        rows = []
        targets = []
        for patch in self.patches():
            mapped = patch.patch_id in TRANSLATIONS
            row = {"patch_id": patch.patch_id, "title": patch.title, "surface": patch.surface, "mapped": mapped,
                   "kind": patch.host_site.get("kind"), "flag": patch.host_site.get("flag")}
            rows.append(row)
            targets.append(Target(
                key=patch.patch_id,
                label=f"{patch.title} — {'translated' if mapped else 'not mapped to MIPS yet'}",
                detail=f"host flag {patch.host_site.get('flag')} in {HOST_EXECUTABLE}",
                budget="32-bit words at EE addresses inside the boot ELF; delivered as a pnach",
                searchable=f"{patch.patch_id} {patch.title}",
                raw=row,
            ))
        document = {"schema": CATALOG_SCHEMA, "elf": identity, "patches": rows,
                    "translations_available": sum(1 for row in rows if row["mapped"])}
        return Catalogue(CATALOG_SCHEMA, self.lane_id, str(source), tuple(targets), document)

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        unknown = sorted(set(values) - {"parameters", "mips"})
        if unknown:
            return f"{target.key}: {', '.join(unknown)} is not something this lane takes; give parameters, or hand-authored mips words."
        if values.get("mips") is not None:
            try:
                _words_from(values["mips"], target.key)
            except Refusal as exc:
                return str(exc)
            return None
        parameters = values.get("parameters", {})
        if not isinstance(parameters, Mapping):
            return f"{target.key}: parameters must be a mapping of the host's parameter names to values."
        if not target.raw.get("mapped"):
            return NOT_MAPPED.format(patch_id=target.key, boot=BOOT_FILE)
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows = []
        for edit in edits:
            row: dict[str, Any] = {"patch": edit.target_key, "parameters": dict(edit.values.get("parameters", {}) or {})}
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

    def _entries(self, recipe: Mapping[str, Any]) -> list[dict[str, Any]]:
        require(isinstance(recipe, Mapping) and recipe.get("schema") == RECIPE_SCHEMA,
                f"recipe schema is {recipe.get('schema') if isinstance(recipe, Mapping) else recipe!r}, expected {RECIPE_SCHEMA}")
        rows = recipe.get("patches")
        require(isinstance(rows, list) and rows, "a recipe must carry a non-empty 'patches' list")
        seen: set[str] = set()
        entries = []
        for number, row in enumerate(rows):
            require(isinstance(row, Mapping) and isinstance(row.get("patch"), str) and row["patch"],
                    f"patch {number} must name the host patch it translates")
            require(set(row) <= {"patch", "parameters", "mips", "note"}, f"patch {number} carries unknown keys")
            require(row["patch"] not in seen, f"{row['patch']} appears twice; one patch is delivered once")
            seen.add(row["patch"])
            entries.append(dict(row))
        return entries

    def _mips(self, entry: Mapping[str, Any], identity: Mapping[str, Any]) -> MipsPatch:
        parameters = entry.get("parameters") or {}
        require(isinstance(parameters, Mapping), f"{entry['patch']}: parameters must be a mapping")
        if entry.get("mips") is not None:
            return MipsPatch(entry["patch"], _words_from(entry["mips"], entry["patch"]), identity, parameters,
                             str(entry.get("note") or "hand-authored"))
        return self.translation(entry["patch"], parameters)

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        entries = self._entries(recipe)
        elf, segments, identity = self._elf(source)
        catalogued = catalogue.document.get("elf", {})
        require(identity["sha256"] == catalogued.get("sha256"),
                "the boot ELF changed since it was catalogued; rebuild the catalogue from this image")
        patches = []
        seen_addresses: set[int] = set()
        for entry in entries:
            catalogue.target(entry["patch"])  # refuses an unknown patch with the catalogue's sentence
            patch = self._mips(entry, identity)
            for word in patch.words:
                require(word.address not in seen_addresses, f"{patch.patch_id}: {_hex(word.address)} is written twice in this recipe")
                seen_addresses.add(word.address)
                try:
                    actual = ps2_elf.read_word(elf, segments, word.address)
                except ps2_elf.PnachError as exc:
                    raise Refusal(f"{patch.patch_id}: {exc}") from exc
                require(actual == word.original,
                        f"{patch.patch_id}: the ELF holds {_hex(actual)} at {_hex(word.address)}, not the "
                        f"{_hex(word.original)} the recipe expects; these words were not derived against this executable")
            patches.append(patch)
        return Plan(self.lane_id, tuple(entry["patch"] for entry in entries), (), {
            "crc": identity["pcsx2_crc"], "elf_sha256": identity["sha256"],
            "patches": [self._patch_row(patch) for patch in patches],
        })

    @staticmethod
    def _patch_row(patch: MipsPatch) -> dict[str, Any]:
        return {"patch_id": patch.patch_id, "note": patch.note, "parameters": dict(patch.parameters),
                "words": [{"address": _hex(w.address), "original": _hex(w.original), "replacement": _hex(w.replacement)}
                          for w in patch.words]}

    @staticmethod
    def _patches_from_rows(rows: Sequence[Mapping[str, Any]], identity: Mapping[str, Any]) -> list[MipsPatch]:
        return [MipsPatch(row["patch_id"], _words_from(row["words"], row["patch_id"]), identity,
                          row.get("parameters", {}), str(row.get("note", ""))) for row in rows]

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any], catalogue: Catalogue,
              *, work_dir: Optional[Path] = None) -> Receipt:
        source, destination = Path(source), Path(destination)
        require(destination.resolve() != source.resolve(), f"{destination} is the source image; a pnach is a NEW file beside it.")
        require(not destination.exists(), f"destination {destination} already exists; refusing to overwrite")
        planned = self.plan(source, recipe, catalogue)
        identity = dict(catalogue.document["elf"])
        patches = self._patches_from_rows(planned.document["patches"], identity)
        text = self.emit_pnach(patches, planned.document["crc"])
        payload = text.encode("utf-8")
        try:
            with open(destination, "xb") as handle:  # exclusive: never overwrites
                handle.write(payload)
        except FileExistsError as exc:
            raise Refusal(f"destination {destination} appeared meanwhile; refusing to overwrite") from exc
        digest = _sha256(payload)
        document = {
            "schema": WRITE_SCHEMA, "source": str(source), "destination": str(destination),
            "crc": planned.document["crc"], "elf": {k: v for k, v in identity.items() if k != "segments"},
            "patches": list(planned.document["patches"]), "pnach_sha256": digest,
            "delivery": "pnach", "note": "Drop the file in PCSX2's patches folder as <CRC>.pnach; nothing on the disc changed.",
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
                return Verdict(False, "Verification failed: the pnach on disk is not the file the receipt recorded.")
        try:
            expected = self._patches_from_rows(receipt.document.get("patches", []), dict(receipt.document.get("elf", {})))
        except Refusal as exc:
            return Verdict(False, f"Verification failed: the receipt is malformed: {exc}")
        if not expected:
            return Verdict(False, "Verification failed: the receipt declares no patches.")
        return self.verify_pnach(payload.decode("utf-8", "replace"), Path(source), expected)

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        elf = ps2_elf.build_synthetic_elf(SYNTHETIC_WORDS, base_vaddr=SYNTHETIC_BASE)
        image = iso_lib.build_synthetic_iso(
            files=[
                (b"SYSTEM.CNF;1", f"BOOT2 = cdrom0:\\{BOOT_FILE};1\r\nVER = 1.01\r\nVMODE = NTSC\r\n".encode("ascii")),
                (f"{BOOT_FILE};1".encode("ascii"), elf),
            ],
            sub_name=b"VC_20919",
            sub_files=[(b"0.;1", bytes(2048))],
        )
        path = Path(work_dir) / "nfl2k5-ps2-code-synthetic.iso"
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

def _lane() -> Ps2CodePatchLane:
    from . import IDENTITY  # the module's identity; imported here so this file stays a plain module

    return Ps2CodePatchLane(IDENTITY)


def selftest() -> int:
    import tempfile

    lane = _lane()
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as work:
        room = Path(work)
        source = lane.synthetic_source(room)
        catalogue = lane.build_catalogue(source)
        if not catalogue.targets:
            failures.append("the host catalogue is empty")
        if catalogue.document["translations_available"] != 0:
            failures.append("a translation exists but this self-test still assumes none")
        try:
            lane.translation(catalogue.targets[0].key, {})
            failures.append("translation did not refuse")
        except Refusal as exc:
            if "not mapped to MIPS yet" not in str(exc):
                failures.append(f"unexpected refusal wording: {exc}")
        recipe = lane.compose_recipe(lane.conformance_edits(catalogue))
        destination = room / "synthetic.pnach"
        receipt = lane.build(source, destination, recipe, catalogue)
        verdict = lane.verify(source, destination, receipt)
        if not verdict.passed:
            failures.append(f"a correct pnach failed verification: {verdict.summary}")
        tampered = destination.read_text(encoding="utf-8").replace("word,24020000", "word,24020002")
        (room / "tampered.pnach").write_text(tampered, encoding="utf-8", newline="\n")
        if lane.verify(source, room / "tampered.pnach", receipt).passed:
            failures.append("a tampered pnach verified")
    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    if failures:
        return 1
    print("NFL2K5_PS2_CODE_PATCHES_SELFTEST_OK translations=0")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--list", action="store_true", help="list the host's patches and whether each is mapped")
    parser.add_argument("--crc", type=Path, metavar="ISO", help="print the boot ELF's PCSX2 CRC and digest (read-only)")
    parser.add_argument("--source", type=Path, metavar="ISO")
    parser.add_argument("--destination", type=Path, metavar="OUT.pnach")
    parser.add_argument("--recipe", type=Path)
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    lane = _lane()
    try:
        if args.list:
            for patch in lane.patches():
                state = "mapped" if patch.patch_id in TRANSLATIONS else "not mapped"
                print(f"{patch.patch_id:<20} {state:<11} {patch.title}")
            return 0
        if args.crc:
            _elf, _segments, identity = lane._elf(args.crc)
            print(json.dumps({k: v for k, v in identity.items() if k != "segments"}, indent=2, sort_keys=True))
            return 0
        if not (args.source and args.destination and args.recipe):
            parser.error("--source, --destination and --recipe are required (or --selftest / --list / --crc)")
        catalogue = lane.build_catalogue(args.source)
        recipe = json.loads(args.recipe.read_text(encoding="utf-8"))
        receipt = lane.build(args.source, args.destination, recipe, catalogue)
        verdict = lane.verify(args.source, args.destination, receipt)
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(verdict.summary)
    return 0 if verdict.passed else 1


__all__ = [
    "CAPABILITY_ID",
    "CATALOG_SCHEMA",
    "HOST_CATALOGUE",
    "NOT_MAPPED",
    "Ps2CodePatchLane",
    "RECIPE_SCHEMA",
    "RETAIL_PCSX2_CRC",
    "SURFACE",
    "SYNTHETIC_BASE",
    "SYNTHETIC_WORDS",
    "TRANSLATIONS",
    "WRITE_SCHEMA",
    "host_patches",
]


if __name__ == "__main__":
    raise SystemExit(main())
