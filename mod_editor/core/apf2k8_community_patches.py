"""Community Xenia patches for APF 2K8 Title Update 1.1 by Basileus Maximus.

Three patches from his "apf-2k8-patches-pack v.1", shared with Noah's
permission for the official Studio:

* play calling by package fixed,
* all packages in substitution menu,
* hidden formations revealed.

Upstream, the first two place their code caves inside 0x84D0D400..0x84D0D7E7,
which the Studio's charge-abilities patch owns (``data/apf2k8/patch_reservations.json``).
Enabled together they would overwrite each other.  The Studio therefore ships
relocated copies: every cave word moves to Studio-reserved padding, relative
branches (``b``/``bl``/``bc``) are re-encoded for their new address and the
declared ``lis``/``addi`` absolute table pairs are rewritten.  Everything else
is the author's bytes.  ``verify_relocation`` re-decodes both versions with
Capstone and proves they are the same instruction stream.

The upstream words, cave layout and retail hook originals live in
``mod_editor/data/apf2k8_community_patches.v1.json``.  TU 1.1 only: the hook
addresses are those of the TU image, and no BASE translation is offered.
Off by default; nothing is installed without the consent dialog.  In-game
results inside Studio builds are UNWITNESSED.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import struct
import tomllib

from .errors import ValidationError

DATA = Path(__file__).resolve().parents[1] / "data" / "apf2k8_community_patches.v1.json"
RESERVATIONS = Path(__file__).resolve().parents[2] / "data" / "apf2k8" / "patch_reservations.json"
AUTHOR = "Basileus Maximus"
CLASSIFICATION = "COMMUNITY"
DEFAULT_ENABLED = False
IMAGE_BASE = 0x82000000
# Executable padding after the TU 1.1 .text virtual end, up to the .data section.
PADDING_START, PADDING_LIMIT = 0x84D0A01C, 0x84D10000


def _int(text: str) -> int:
    return int(text, 16)


@dataclass(frozen=True)
class Region:
    start: int
    end: int  # exclusive
    kind: str  # "code" or "data"
    new_start: int

    def contains(self, address: int) -> bool:
        return self.start <= address < self.end

    def moved(self, address: int) -> int:
        return address - self.start + self.new_start


@dataclass(frozen=True)
class Definition:
    key: str
    filename: str
    upstream_file: str
    upstream_sha256: str
    name: str
    desc: str
    reservation_owners: tuple[str, ...]
    regions: tuple[Region, ...]
    absolute_pairs: tuple[tuple[int, int], ...]
    hook_originals: tuple[tuple[int, int], ...]
    upstream_words: tuple[tuple[int, int], ...]

    def region(self, address: int) -> Region | None:
        return next((r for r in self.regions if r.contains(address)), None)

    def map(self, address: int) -> int:
        region = self.region(address)
        return address if region is None else region.moved(address)


def load_document(path: Path = DATA) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_definitions(path: Path = DATA) -> tuple[Definition, ...]:
    document = load_document(path)
    if document.get("schema") != "apf2k8_community_patches/v1" or document.get("author") != AUTHOR:
        raise ValidationError("Community patch definitions changed schema or author")
    out = []
    for row in document["patches"]:
        out.append(Definition(
            row["key"], row["filename"], row["upstream_file"], row["upstream_sha256"], row["name"], row["desc"],
            tuple(row["reservation_owners"]),
            tuple(Region(_int(r["start"]), _int(r["end"]), r["kind"], _int(r["new_start"])) for r in row["regions"]),
            tuple((_int(a), _int(b)) for a, b in row["absolute_pairs"]),
            tuple((_int(a), _int(v)) for a, v in row["hook_originals"].items()),
            tuple((_int(a), _int(v)) for a, v in row["words"])))
    return tuple(out)


def _signed(value: int, bits: int) -> int:
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def _branch_target(address: int, word: int) -> int | None:
    """Target of a relative I-form or B-form branch; None for anything else (absolute branches included)."""
    op = word >> 26
    if op == 18 and not word & 2:
        return address + _signed(word & 0x03FFFFFC, 26)
    if op == 16 and not word & 2:
        return address + _signed(word & 0xFFFC, 16)
    return None


def _retarget(address: int, word: int, target: int) -> int:
    delta = target - address
    if word >> 26 == 18:
        if delta & 3 or not -(1 << 25) <= delta < (1 << 25):
            raise ValidationError(f"Relocated branch at {address:08X} is out of range")
        return (word & ~0x03FFFFFC) | (delta & 0x03FFFFFC)
    if delta & 3 or not -(1 << 15) <= delta < (1 << 15):
        raise ValidationError(f"Relocated conditional branch at {address:08X} is out of range")
    return (word & ~0xFFFC) | (delta & 0xFFFC)


def _absolute(hi: int, lo: int) -> int:
    """Address built by ``lis rX,imm`` and ``addi rX,rX,imm`` (or ``ori``)."""
    if hi >> 26 != 15 or (hi >> 16) & 31 != 0:
        raise ValidationError("Absolute pair does not start with lis")
    if lo >> 26 == 14:
        return ((hi & 0xFFFF) << 16) + _signed(lo & 0xFFFF, 16) & 0xFFFFFFFF
    if lo >> 26 == 24:
        return ((hi & 0xFFFF) << 16) | (lo & 0xFFFF)
    raise ValidationError("Absolute pair does not end with addi or ori")


def _encode_absolute(hi: int, lo: int, address: int) -> tuple[int, int]:
    if lo >> 26 == 14:
        upper = ((address + 0x8000) >> 16) & 0xFFFF
    else:
        upper = (address >> 16) & 0xFFFF
    return (hi & 0xFFFF0000) | upper, (lo & 0xFFFF0000) | (address & 0xFFFF)


def relocate(definition: Definition) -> tuple[tuple[int, int], ...]:
    """The upstream words with every cave word moved to its Studio-reserved address."""
    upstream = dict(definition.upstream_words)
    if len(upstream) != len(definition.upstream_words):
        raise ValidationError("Community patch writes one address twice")
    pairs = {}
    for hi, lo in definition.absolute_pairs:
        if hi not in upstream or lo not in upstream:
            raise ValidationError("Declared absolute pair is not part of the patch")
        target = _absolute(upstream[hi], upstream[lo])
        pairs[hi], pairs[lo] = _encode_absolute(upstream[hi], upstream[lo], definition.map(target))
    out = []
    for address, word in definition.upstream_words:
        region = definition.region(address)
        if PADDING_START <= address < PADDING_LIMIT and region is None:
            raise ValidationError(f"Cave word {address:08X} has no declared region")
        new_address = definition.map(address)
        if region is not None and region.kind == "data":
            out.append((new_address, word))
            continue
        if address in pairs:
            out.append((new_address, pairs[address]))
            continue
        if word >> 26 == 15 and (word >> 16) & 31 == 0 and (word & 0xFFFF) in (0x84D0, 0x84D1):
            raise ValidationError(f"Undeclared absolute cave reference at {address:08X}")
        target = _branch_target(address, word)
        if target is not None:
            word = _retarget(new_address, word, definition.map(target))
        out.append((new_address, word))
    return tuple(out)


def verify_relocation(definition: Definition, words=None) -> dict:
    """Capstone side-by-side proof that the relocated stream equals the upstream one.

    Data words must be identical.  Code words must decode to the same mnemonic;
    their operands must be identical except branch targets, which must equal the
    upstream target mapped through the declared regions, and the declared
    absolute pairs, whose computed address must equal the mapped upstream address.
    """
    try:
        from capstone import Cs, CS_ARCH_PPC, CS_MODE_64, CS_MODE_BIG_ENDIAN
    except ImportError as exc:
        raise ValidationError("Capstone is required to verify relocated community patches") from exc
    md = Cs(CS_ARCH_PPC, CS_MODE_64 | CS_MODE_BIG_ENDIAN)
    words = relocate(definition) if words is None else tuple(words)
    if len(words) != len(definition.upstream_words):
        raise ValidationError("Relocated patch has a different word count")
    pair_words = {a for pair in definition.absolute_pairs for a in pair}
    code_new = [r for r in definition.regions if r.kind == "code"]
    data_new = [r for r in definition.regions if r.kind == "data"]
    counts = {"words": len(words), "identical": 0, "branches_retargeted": 0, "branches_unchanged": 0,
              "absolute_pairs_rewritten": 0, "data_words": 0, "moved_words": 0}
    rows = []
    for (old_address, old_word), (new_address, new_word) in zip(definition.upstream_words, words):
        if new_address != definition.map(old_address):
            raise ValidationError(f"Relocated address for {old_address:08X} is wrong")
        counts["moved_words"] += new_address != old_address
        region = definition.region(old_address)
        if region is not None and region.kind == "data":
            if new_word != old_word:
                raise ValidationError(f"Data word {old_address:08X} changed in relocation")
            counts["data_words"] += 1
            counts["identical"] += 1
            rows.append((old_address, old_word, new_address, new_word, "data"))
            continue
        old = list(md.disasm(struct.pack(">I", old_word), old_address))
        new = list(md.disasm(struct.pack(">I", new_word), new_address))
        if len(old) != 1 or len(new) != 1 or old[0].mnemonic != new[0].mnemonic:
            raise ValidationError(f"Relocated instruction at {old_address:08X} decodes differently")
        old_target = _branch_target(old_address, old_word)
        if old_target is not None:
            mapped = definition.map(old_target)
            if _branch_target(new_address, new_word) != mapped:
                raise ValidationError(f"Relocated branch at {old_address:08X} reaches the wrong target")
            if (old_word ^ new_word) & ~(0x03FFFFFC if old_word >> 26 == 18 else 0xFFFC):
                raise ValidationError(f"Relocated branch at {old_address:08X} changed more than its offset")
            if old[0].op_str.replace(f"0x{old_target:x}", f"0x{mapped:x}") != new[0].op_str:
                raise ValidationError(f"Capstone operands differ for relocated branch at {old_address:08X}")
            target_region = definition.region(old_target)
            if target_region is not None and target_region.kind != "code":
                raise ValidationError(f"Branch at {old_address:08X} targets data")
            if target_region is None and PADDING_START <= mapped < PADDING_LIMIT:
                raise ValidationError(f"Branch at {old_address:08X} targets undeclared padding")
            moved = mapped != old_target or new_address != old_address
            counts["branches_retargeted" if new_word != old_word else "branches_unchanged"] += 1
            rows.append((old_address, old_word, new_address, new_word, "branch" if moved else "same"))
            continue
        if old_address in pair_words:
            counts["absolute_pairs_rewritten"] += old_word != new_word
            rows.append((old_address, old_word, new_address, new_word, "pair"))
            continue
        if new_word != old_word or old[0].op_str != new[0].op_str:
            raise ValidationError(f"Non-branch instruction at {old_address:08X} changed in relocation")
        counts["identical"] += 1
        rows.append((old_address, old_word, new_address, new_word, "same"))
    upstream, relocated = dict(definition.upstream_words), dict(words)
    for hi, lo in definition.absolute_pairs:
        before = _absolute(upstream[hi], upstream[lo])
        after = _absolute(relocated[definition.map(hi)], relocated[definition.map(lo)])
        if after != definition.map(before):
            raise ValidationError("Relocated absolute table address is wrong")
        for old_address in (hi, lo):
            old = next(md.disasm(struct.pack(">I", upstream[old_address]), old_address))
            new = next(md.disasm(struct.pack(">I", relocated[definition.map(old_address)]), definition.map(old_address)))
            if old.mnemonic != new.mnemonic or old.op_str.split(",")[:-1] != new.op_str.split(",")[:-1]:
                raise ValidationError("Absolute pair registers changed in relocation")
    for region in code_new + data_new:
        end = region.new_start + region.end - region.start
        if not PADDING_START <= region.new_start < end <= PADDING_LIMIT:
            raise ValidationError("Relocated region leaves the executable padding")
    counts["capstone_redecoded"] = True
    counts["rows"] = rows
    return counts


def reservation_ranges(path: Path = RESERVATIONS) -> list[tuple[str, int, int]]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))["ranges"]
    return [(r["owner"], _int(r["start"]), _int(r["end_inclusive"]) + 1) for r in rows]


def check_reservations(definition: Definition, words=None, path: Path = RESERVATIONS) -> dict:
    """Every cave word must sit inside one of this patch's own reserved owners, and nowhere else."""
    words = relocate(definition) if words is None else words
    ranges = reservation_ranges(path)
    own = [(o, s, e) for o, s, e in ranges if o in definition.reservation_owners]
    if {o for o, _, _ in own} != set(definition.reservation_owners):
        raise ValidationError(f"Reservation owners missing for {definition.key}")
    for address, _ in words:
        holders = [o for o, s, e in ranges if s <= address < e]
        if PADDING_START <= address < PADDING_LIMIT:
            if len(holders) != 1 or holders[0] not in definition.reservation_owners:
                raise ValidationError(f"{definition.key} cave word {address:08X} is outside its reservation ({holders})")
        elif holders:
            raise ValidationError(f"{definition.key} hook {address:08X} lands in reserved space {holders}")
    return {"owners": list(definition.reservation_owners), "cave_words": sum(PADDING_START <= a < PADDING_LIMIT for a, _ in words)}


def _toml_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


@dataclass(frozen=True)
class PatchDocument:
    definition: Definition
    enabled: bool = DEFAULT_ENABLED

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValidationError("Choose a boolean enable flag")

    @property
    def words(self) -> tuple[tuple[int, int], ...]:
        return relocate(self.definition)

    def as_toml(self) -> str:
        document = load_document()
        lines = [f'title_name = {_toml_string(document["title_name"])}', f'title_id = "{document["title_id"]}"',
                 f'hash = "{document["module_hash"]}"', "", "[[patch]]",
                 f"name = {_toml_string(self.definition.name)}",
                 f"desc = {_toml_string(self.definition.desc)}",
                 f"author = {_toml_string(AUTHOR)}", f"is_enabled = {str(self.enabled).lower()}"]
        for address, value in self.words:
            lines += ["", "[[patch.be32]]", f"address = 0x{address:08X}", f"value = 0x{value:08X}"]
        return "\n".join(lines) + "\n"

    @property
    def receipt(self) -> dict:
        proof = verify_relocation(self.definition)
        proof.pop("rows")
        return {"schema": "apf2k8_community_patch/v1", "key": self.definition.key, "author": AUTHOR,
                "classification": CLASSIFICATION, "profile": "tu_1_1", "enabled": self.enabled,
                "upstream_file": self.definition.upstream_file, "upstream_sha256": self.definition.upstream_sha256,
                "relocation": proof, "reservations": check_reservations(self.definition),
                "status": "UNWITNESSED in Studio builds"}


class _Profile:
    """Matches the (profile, enabled) contract the launcher's other validators return."""

    name = "tu_1_1"


PROFILE = _Profile()


def definition(key: str) -> Definition:
    for row in load_definitions():
        if row.key == key:
            return row
    raise ValidationError(f"Unknown community patch {key!r}")


def parse_payload(payload: bytes, key: str) -> PatchDocument:
    try:
        parsed = tomllib.loads(payload.decode("utf-8"))
        rows = parsed["patch"]
        if not isinstance(rows, list) or len(rows) != 1:
            raise ValueError("expected one patch entry")
        document = PatchDocument(definition(key), rows[0]["is_enabled"])
        if parsed != tomllib.loads(document.as_toml()):
            raise ValueError("Metadata or instructions differ from the Studio's relocated patch")
        return document
    except (UnicodeError, ValueError, TypeError, KeyError) as exc:
        raise ValidationError(f"Choose the Studio's relocated community patch: {exc}") from exc


def canonical_payload(payload: bytes, key: str):
    document = parse_payload(payload, key)
    return PROFILE, document.enabled


def upstream_conflicts(folder: Path) -> list[str]:
    """Upstream (unrelocated) copies in a Xenia patches folder; they collide with the charge-abilities caves."""
    import hashlib
    found = []
    known = {row.upstream_sha256: row for row in load_definitions()}
    try:
        candidates = sorted(Path(folder).glob("*.patch.toml"))
    except OSError:
        return found
    for path in candidates:
        try:
            if path.is_file() and not path.is_symlink() and path.stat().st_size < 1 << 20:
                if hashlib.sha256(path.read_bytes()).hexdigest() in known:
                    found.append(path.name)
        except OSError:
            continue
    return found


def verify_image(image: bytes, document: PatchDocument) -> dict:
    """Check a user's TU 1.1 image: hook originals match and every relocated cave is still zero."""
    from .apf2k8_playcall_patch import PROFILES, check_image
    if check_image(image) != PROFILES[1]:
        raise ValidationError("Community patches target Title Update 1.1 only")
    for address, original in document.definition.hook_originals:
        if struct.unpack_from(">I", image, address - IMAGE_BASE)[0] != original:
            raise ValidationError(f"Community patch hook {address:08X} differs from the pinned TU 1.1 image")
    for address, _ in document.words:
        if PADDING_START <= address < PADDING_LIMIT and image[address - IMAGE_BASE:address - IMAGE_BASE + 4] != bytes(4):
            raise ValidationError(f"Community patch cave {address:08X} is not empty padding")
    return document.receipt


def write_patch(document: PatchDocument, output: Path) -> dict:
    import os
    output = Path(output)
    if output.is_symlink() or not output.name.endswith(".patch.toml"):
        raise ValidationError("Choose a regular .patch.toml output file")
    payload = document.as_toml().encode("utf-8")
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
    if parse_payload(output.read_bytes(), document.definition.key) != document:
        raise ValidationError("Community patch readback differs")
    return document.receipt


KEYS = ("play_calling_by_package", "all_packages_in_substitution", "hidden_formations_revealed")
