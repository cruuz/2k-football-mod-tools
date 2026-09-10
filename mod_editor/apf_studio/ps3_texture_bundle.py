"""Import APFe texture exports into the existing Xbox 360 staging contracts.

No PS3 archive offsets or compressed bytes reach a writer. Identity is the
outer entry hash PLUS semantic layer name; a numeric subfile index is never
interpreted as l0/l1. Alternative exports stay explicit variants.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from typing import Iterable, Mapping
import unicodedata
import zipfile

from PIL import Image

from .ps3_texture_codec import MAX_TEXTURE_BYTES, decode_dds, decode_gtf

SCHEMA = "apf2k8_ps3_texture_bundle/v1"
STATUS = "PS3 bundle staging verified offline; build allocation checks required; in-game UNWITNESSED"
LAYER_SIZE = {"logo": (512, 512), "endzone": (2048, 512)}
LAYER_RE = re.compile(r"^(?:\d+_)?(logo|endzone)_l([01])\.(dds|gtf)$", re.I)
MAX_FILES = 10000
MAX_BUNDLE_BYTES = 512 * 1024 * 1024


class BundleError(ValueError):
    pass


def normalize_name(name: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", name).casefold() if c.isalnum())


NFL_TEAMS = (
    "Atlanta Falcons", "Buffalo Bills", "Chicago Bears", "Cincinnati Bengals", "Cleveland Browns",
    "Dallas Cowboys", "Denver Broncos", "Detroit Lions", "Green Bay Packers", "Houston Oilers",
    "Indianapolis Colts", "Kansas City Chiefs", "Los Angeles Raiders", "Los Angeles Rams",
    "Miami Dolphins", "Minnesota Vikings", "New England Patriots", "New Orleans Saints",
    "New York Giants", "New York Jets", "Philadelphia Eagles", "Phoenix Cardinals",
    "Pittsburgh Steelers", "San Diego Chargers", "San Francisco 49ers", "Seattle Seahawks",
    "Tampa Bay Buccaneers", "Washington Redskins",
)
TEAM_ALIASES = {normalize_name(team): team for team in NFL_TEAMS}
TEAM_ALIASES.update({normalize_name(alias): team for alias, team in (
    ("Cincinati Bengals", "Cincinnati Bengals"), ("Detriot Lions", "Detroit Lions"),
    ("Philadelia Eagles", "Philadelphia Eagles"), ("San Deigo Chargers", "San Diego Chargers"),
    ("San Franciso 49ers", "San Francisco 49ers"),
)})


def canonical_team(name: str) -> str:
    try:
        return TEAM_ALIASES[normalize_name(name)]
    except KeyError as exc:
        raise BundleError(f"Unknown early-1990s NFL team: {name}") from exc


def _hash(value: object) -> int:
    try:
        result = int(value, 0) if isinstance(value, str) else value
        if type(result) is not int or not 0 <= result <= 0xFFFFFFFF:
            raise ValueError()
        return result
    except (TypeError, ValueError) as exc:
        raise BundleError(f"Invalid entryHash: {value!r}") from exc


def _safe_name(name: str) -> str:
    path = PurePosixPath(name)
    if not name or "\\" in name or path.is_absolute() or any(p in (".", "..") or ":" in p for p in name.split("/")):
        raise BundleError(f"Unsafe bundle member: {name}")
    return name


@contextmanager
def _members(source: Path):
    """Never extract ZIPs; reject traversal, case collisions, and symlinks."""
    source = source.expanduser()
    if source.is_dir():
        paths = {}
        for path in source.rglob("*"):
            if path.is_symlink():
                raise BundleError(f"Symlink in bundle: {path}")
            if path.is_file():
                paths[path.relative_to(source).as_posix()] = path
                if len(paths) > MAX_FILES:
                    raise BundleError("Too many bundle members")
        names = list(paths)
        def read(name):
            path = paths[name]
            if path.stat().st_size > MAX_TEXTURE_BYTES:
                raise BundleError(f"Oversize bundle member: {name}")
            # Recheck resolution in case a directory changed during discovery.
            if not path.resolve().is_relative_to(source.resolve()) or path.is_symlink():
                raise BundleError(f"Bundle member escaped source: {name}")
            with path.open("rb") as stream:
                data = stream.read(MAX_TEXTURE_BYTES + 1)
            if len(data) > MAX_TEXTURE_BYTES:
                raise BundleError(f"Oversize bundle member: {name}")
            return data
        _validate_names(names)
        yield names, read
    else:
        with zipfile.ZipFile(source) as archive:
            infos = [i for i in archive.infolist() if not i.is_dir()]
            names = [i.filename for i in infos]
            _validate_names(names)
            if any(stat.S_ISLNK(i.external_attr >> 16) or i.flag_bits & 1 for i in infos):
                raise BundleError("Symlink or encrypted bundle member")
            by_name = {i.filename: i for i in infos}
            def read(name):
                if by_name[name].file_size > MAX_TEXTURE_BYTES:
                    raise BundleError(f"Oversize bundle member: {name}")
                with archive.open(by_name[name]) as stream:
                    data = stream.read(MAX_TEXTURE_BYTES + 1)
                if len(data) > MAX_TEXTURE_BYTES:
                    raise BundleError(f"Oversize bundle member: {name}")
                return data
            yield names, read


def _validate_names(names: list[str]) -> None:
    if len(names) > MAX_FILES:
        raise BundleError("Too many bundle members")
    seen = set()
    for name in names:
        key = _safe_name(name).casefold()
        if key in seen:
            raise BundleError(f"Duplicate/case-colliding bundle member: {name}")
        seen.add(key)


@dataclass(frozen=True)
class TextureLayer:
    layer: str
    image: Image.Image
    source_path: str
    manifest_row: dict

    def receipt(self) -> dict:
        return {"layer": self.layer, "source_path": self.source_path,
                "width": self.image.width, "height": self.image.height, "mode": "RGBA",
                "decoded_pixels_sha256": hashlib.sha256(self.image.tobytes()).hexdigest(),
                "source_manifest_row": self.manifest_row}


@dataclass(frozen=True)
class TexturePair:
    pair_id: str
    team: str
    original_folder: str
    kind: str
    variant: str
    entry_hash: int | None
    layers: tuple[TextureLayer, TextureLayer]

    def receipt(self) -> dict:
        return {"pair_id": self.pair_id, "team": self.team, "original_folder": self.original_folder,
                "kind": self.kind, "variant": self.variant,
                "entry_hash": None if self.entry_hash is None else f"0x{self.entry_hash:08x}",
                "layers": [layer.receipt() for layer in self.layers]}


@dataclass(frozen=True)
class TextureBundle:
    source: str
    pairs: tuple[TexturePair, ...]
    ignored_files: tuple[str, ...]
    rejected_pairs: tuple[dict, ...] = ()

    @property
    def teams(self) -> tuple[str, ...]:
        return tuple(sorted({pair.team for pair in self.pairs}))

    def receipt(self) -> dict:
        return {"schema": SCHEMA, "source": self.source, "teams": list(self.teams),
                "pairs": [p.receipt() for p in self.pairs], "ignored_files": list(self.ignored_files),
                "rejected_pairs": list(self.rejected_pairs)}


def read_bundle(source: Path) -> TextureBundle:
    source = Path(source)
    grouped = defaultdict(dict)
    ignored = []
    total, decoded_total = 0, 0
    with _members(source) as (names, read):
        lookup = {n.casefold(): n for n in names}
        for name in sorted(names):
            path = PurePosixPath(name)
            match = LAYER_RE.fullmatch(path.name)
            if not match:
                if path.suffix.casefold() != ".json":
                    ignored.append(name)
                continue
            kind, number, extension = (p.lower() for p in match.groups())
            if extension == "gtf" and str(path.with_suffix(".dds")).casefold() in lookup:
                continue
            components = list(path.parts[:-1])
            if source.is_dir():
                components.insert(0, source.name)
            positions = [i for i, p in enumerate(components) if normalize_name(p) in TEAM_ALIASES]
            if len(positions) != 1:
                raise BundleError(f"Texture must be inside exactly one recognized team folder: {name}")
            team_index = positions[0]
            original = components[team_index]
            team = canonical_team(original)
            variant_parts = components[team_index + 1:]
            if variant_parts and variant_parts[-1].startswith("selected_subfile_"):
                variant_parts.pop()
            variant = "/".join(variant_parts) or "default"
            layer = f"{kind}_l{number}"
            manifest_name = lookup.get(str(path.parent / "manifest.json").casefold())
            row = {}
            if manifest_name:
                raw_manifest = read(manifest_name)
                if len(raw_manifest) > 1024 * 1024:
                    raise BundleError(f"Oversize manifest: {manifest_name}")
                try:
                    document = json.loads(raw_manifest)
                    row = document["row"]
                    if not isinstance(row, dict):
                        raise ValueError("row must be an object")
                    if row.get("type") != "TXTR" or row.get("subfileName") != layer:
                        raise ValueError("manifest layer/type disagrees with filename")
                    for field in ("entryIndex", "byteLength"):
                        if type(row.get(field)) is not int or row[field] < (1 if field == "byteLength" else 0):
                            raise ValueError(f"invalid {field}")
                    _hash(row["entryHash"])
                    listed = document.get("files")
                    if not isinstance(listed, list) or path.name not in listed:
                        raise ValueError("texture missing from manifest files")
                except (KeyError, TypeError, ValueError) as exc:
                    raise BundleError(f"Invalid manifest {manifest_name}: {exc}") from exc
            entry_hash = _hash(row["entryHash"]) if row else None
            key = (team, original, kind, variant, entry_hash)
            if number in grouped[key]:
                raise BundleError(f"Duplicate {layer} variant: {name}")
            data = read(name)
            total += len(data)
            if total > MAX_BUNDLE_BYTES:
                raise BundleError("Bundle exceeds decoded-input byte budget")
            try:
                image = decode_dds(data) if extension == "dds" else decode_gtf(data)
            except ValueError as exc:
                raise BundleError(f"Cannot decode {name}: {exc}") from exc
            if image.size != LAYER_SIZE[kind]:
                raise BundleError(f"{name}: expected {LAYER_SIZE[kind]}, got {image.size}")
            decoded_total += image.width * image.height * 4
            if decoded_total > MAX_BUNDLE_BYTES:
                raise BundleError("Bundle exceeds decoded RGBA byte budget")
            grouped[key][number] = TextureLayer(layer, image, name, row)
        pairs, rejected, pair_ids = [], [], set()
        for (team, original, kind, variant, entry_hash), layers in grouped.items():
            if set(layers) != {"0", "1"}:
                rejected.append({"team": team, "original_folder": original, "kind": kind, "variant": variant,
                                 "reason": "Incomplete pair; need l0 AND l1", "layers": [l.receipt() for l in layers.values()]})
                continue
            l0, l1 = layers["0"], layers["1"]
            if l0.image.tobytes() == l1.image.tobytes():
                rejected.append({"team": team, "original_folder": original, "kind": kind, "variant": variant,
                                 "reason": "Identical/mirrored layers violate the six-region rule",
                                 "layers": [l0.receipt(), l1.receipt()]})
                continue
            if l0.manifest_row and l0.manifest_row["entryIndex"] != l1.manifest_row["entryIndex"]:
                raise BundleError(f"{team} {kind}: sibling manifest entry indices disagree")
            pair_id = f"{team}/{kind}/{variant}/{entry_hash:08x}" if entry_hash is not None else f"{team}/{kind}/{variant}/no-hash"
            if pair_id in pair_ids:
                raise BundleError(f"Aliased team folders repeat a source pair: {pair_id}")
            pair_ids.add(pair_id)
            pairs.append(TexturePair(pair_id, team, original, kind, variant, entry_hash, (l0, l1)))
    if not pairs:
        raise BundleError("No valid APFe pairs found (incomplete or identical/mirrored layers are rejected)")
    return TextureBundle(str(source), tuple(sorted(pairs, key=lambda p: p.pair_id)), tuple(ignored), tuple(rejected))


@dataclass(frozen=True)
class DestinationSlot:
    slot_id: str
    label: str
    kind: str
    outer_index: int
    entry_hash: int
    asset_ids: tuple[str, str]
    inner_indices: tuple[int, int]
    crest_asset_index: int | None = None
    writable: bool = True


def destination_slots(index_0a: Path) -> tuple[DestinationSlot, ...]:
    """Live archive identities, with writer-owned slot and label tables."""
    from .backend import ensure_tools_importable
    from .field_art import endzone_team_labels
    ensure_tools_importable()
    import apf_outer
    import apf_inner
    import apf_team_crests
    import apf_field_art_patch
    import zlib
    archive = apf_outer.parse_archive(Path(index_0a))
    crest_hashes = {zlib.crc32(f"UNIFORM_LOGO_{i:02d}.IFF".encode()): i for i in range(118)}
    teams = {t.asset_index: t.team for t in apf_team_crests.TEAM_CRESTS}
    labels = endzone_team_labels()
    slots = []
    with apf_inner.ArchiveReader(archive) as reader:
        for entry in archive.entries:
            if entry.head_hex != "ff3bef94":
                continue
            record = apf_inner.parse_iff(reader, entry)
            by_name = {f.name: f for f in record.files if f.type_name == "TXTR"}
            for kind in LAYER_SIZE:
                if not all(f"{kind}_l{i}" in by_name for i in (0, 1)):
                    continue
                index = crest_hashes.get(entry.name_id) if kind == "logo" else None
                if kind == "logo" and index is None:
                    continue
                indices = tuple(by_name[f"{kind}_l{i}"].index for i in (0, 1))
                writable = kind == "logo" or all((entry.table_index, i) in apf_field_art_patch._CONTRACTS for i in indices)
                label = teams.get(index, f"Logo slot {index:02d}") if kind == "logo" else labels.get(entry.table_index, f"Unidentified endzone {entry.table_index}")
                slots.append(DestinationSlot(f"{kind}:{entry.table_index}", label, kind, entry.table_index,
                             entry.name_id, tuple(f"apf:outer:{entry.table_index}:inner:{i}" for i in indices),
                             indices, index, writable))
    return tuple(slots)


@dataclass(frozen=True)
class Assignment:
    """One chosen pair to one slot. Use pair_id to choose source variants."""
    pair_id: str
    destination_slot: str


@dataclass(frozen=True)
class StagedTexture:
    destination_asset_id: str
    layer: str
    image: Image.Image
    source_path: str
    receipt: dict


@dataclass(frozen=True)
class StagingPlan:
    items: tuple[StagedTexture, ...]
    assignments: tuple[tuple[TexturePair, DestinationSlot], ...]
    receipt: dict


def build_plan(bundle: TextureBundle, slots: Iterable[DestinationSlot],
               assignments: Iterable[Assignment] | None = None) -> StagingPlan:
    destinations = {s.slot_id: s for s in slots}
    sources = {p.pair_id: p for p in bundle.pairs}
    if assignments is None:
        automatic = []
        for pair in bundle.pairs:
            matches = [s for s in destinations.values() if s.entry_hash == pair.entry_hash and s.kind == pair.kind]
            if len(matches) != 1:
                raise BundleError(f"Choose a destination for {pair.pair_id}: hash has {len(matches)} matches")
            automatic.append(Assignment(pair.pair_id, matches[0].slot_id))
        assignments = automatic
    items, resolved, rows = [], [], []
    used_sources, used_destinations = set(), set()
    for assignment in assignments:
        if assignment.pair_id not in sources or assignment.destination_slot not in destinations:
            raise BundleError(f"Unknown source/destination in mapping: {assignment}")
        pair, slot = sources[assignment.pair_id], destinations[assignment.destination_slot]
        if pair.pair_id in used_sources or slot.slot_id in used_destinations:
            raise BundleError("Mapping repeats a source pair or destination slot; choose one variant")
        if pair.kind != slot.kind or not slot.writable:
            raise BundleError(f"Destination {slot.slot_id} has no compatible proved pair writer")
        used_sources.add(pair.pair_id)
        used_destinations.add(slot.slot_id)
        method = "entry_hash_and_layer_name" if pair.entry_hash == slot.entry_hash else "chosen_destination_and_layer_name"
        row = {"source_pair": pair.receipt(), "destination_slot": slot.slot_id,
               "destination_label": slot.label, "destination_entry_hash": f"0x{slot.entry_hash:08x}",
               "mapping_method": method, "mips": "regenerated",
               "allocation_policy": "fixed allocation; endzones try safe optimal H7A, RGB endpoint simplification, then 2x/4x top-mip reduction; receipt records any reduction",
               "writer": "apf_logo_patch.build_patch_rgba + linked logocache" if pair.kind == "logo" else "apf_field_art_patch.build_field_art_patch_many"}
        for index, layer in enumerate(pair.layers):
            if layer.layer != f"{pair.kind}_l{index}" or layer.image.size != LAYER_SIZE[pair.kind]:
                raise BundleError("Source pair dimensions/layer order changed")
            receipt = {**layer.receipt(), "destination_asset_id": slot.asset_ids[index], "mapping_method": method}
            items.append(StagedTexture(slot.asset_ids[index], layer.layer, layer.image, layer.source_path, receipt))
        if pair.layers[0].image.tobytes() == pair.layers[1].image.tobytes():
            raise BundleError("Identical/mirrored layers cannot be staged")
        resolved.append((pair, slot))
        rows.append(row)
    if not resolved:
        raise BundleError("Mapping table is empty")
    return StagingPlan(tuple(items), tuple(resolved), {"schema": SCHEMA, "status": STATUS, "source": bundle.source,
                       "rejected_pairs": list(bundle.rejected_pairs),
                       "assignment_count": len(rows), "texture_count": len(items), "assignments": rows,
                       "textures": [i.receipt for i in items]})


def verify_plan(plan: StagingPlan) -> None:
    """Detect mutated in-memory images/receipts before any session staging."""
    if len(plan.items) != 2 * len(plan.assignments) or not plan.items:
        raise BundleError("Staging plan pair count changed")
    if len({item.destination_asset_id for item in plan.items}) != len(plan.items):
        raise BundleError("Staging plan repeats a destination asset")
    for ordinal, (pair, slot) in enumerate(plan.assignments):
        if pair.layers[0].image.tobytes() == pair.layers[1].image.tobytes():
            raise BundleError("Staging plan contains identical/mirrored layers")
        for index, layer in enumerate(pair.layers):
            item = plan.items[ordinal * 2 + index]
            if (item.layer != f"{slot.kind}_l{index}" or item.destination_asset_id != slot.asset_ids[index]
                    or item.image.mode != "RGBA" or item.image.size != LAYER_SIZE[slot.kind]
                    or item.image.tobytes() != layer.image.tobytes()
                    or hashlib.sha256(item.image.tobytes()).hexdigest() != item.receipt["decoded_pixels_sha256"]):
                raise BundleError("Staging plan pixels or destination changed after review")


def team_mapping(bundle: TextureBundle, slots: Iterable[DestinationSlot], table: Iterable[Mapping]) -> tuple[Assignment, ...]:
    """Rows: team, kind, destination (slot id or exact label), optional pair_id.

    No geographic guesses join crest and endzone owners. A full team import
    therefore uses two rows, one for each writer, with independent selectors.
    """
    slots = tuple(slots)
    result, seen = [], set()
    for row in table:
        if not isinstance(row, Mapping) or set(row) - {"team", "kind", "destination", "pair_id"} or not {"team", "kind", "destination"} <= set(row):
            raise BundleError("Mapping row needs team, kind, destination and optional pair_id")
        team, kind = canonical_team(str(row["team"])), row["kind"]
        if kind not in LAYER_SIZE or (team, kind) in seen:
            raise BundleError("Invalid/repeated team and kind in mapping")
        seen.add((team, kind))
        pairs = [p for p in bundle.pairs if p.team == team and p.kind == kind and ("pair_id" not in row or p.pair_id == row["pair_id"])]
        targets = [s for s in slots if s.kind == kind and (s.slot_id == row["destination"] or s.label == row["destination"])]
        if len(pairs) != 1 or len(targets) != 1:
            raise BundleError(f"Ambiguous/missing source variant or destination for {team} {kind}")
        result.append(Assignment(pairs[0].pair_id, targets[0].slot_id))
    build_plan(bundle, slots, result)  # all batch collisions checked before staging
    return tuple(result)


def stage_plan(session, plan: StagingPlan) -> tuple:
    """Feed the existing session writers; temporary PNGs are decoded/reparsed.

    Each successful operation creates one existing session undo snapshot;
    on failure those operations are undone before returning the exception.
    The immutable input bundle and all retail volumes remain read-only.
    """
    from .helmet_crest_design import RETAIL_CREST_PROFILE
    verify_plan(plan)
    # Rebind the plan to the selected live source; do not trust stale slot IDs.
    live = {s.slot_id: s for s in destination_slots(session.source.index_0a)}
    for pair, slot in plan.assignments:
        if live.get(slot.slot_id) != slot:
            raise BundleError(f"Destination changed since planning: {slot.slot_id}")
    if any(m.metadata.get("profile") == "front_crown_to_rear_v1" for m in session.modifications):
        raise BundleError("Revert the shared full-shell crest profile before a PS3 bundle import")
    count, modifications = 0, []
    try:
        with tempfile.TemporaryDirectory(prefix="apf-ps3-stage-") as directory:
            for ordinal, (pair, slot) in enumerate(plan.assignments):
                paths = []
                for index, layer in enumerate(pair.layers):
                    path = Path(directory) / f"{ordinal}-{index}.png"
                    layer.image.save(path, "PNG")
                    with Image.open(path) as reread:
                        if reread.convert("RGBA").tobytes() != layer.image.tobytes():
                            raise BundleError("Staging PNG did not reparse exactly")
                    paths.append(path)
                if pair.kind == "logo":
                    modifications.append(session.replace_helmet_crest_design(paths[0], profile=RETAIL_CREST_PROFILE,
                                         crest_asset_index=slot.crest_asset_index, crest_outer_entry_index=slot.outer_index,
                                         detail_png=paths[1]))
                    count += 1
                else:
                    for index, path in enumerate(paths):
                        modifications.append(session.replace_field_art((slot.outer_index, slot.inner_indices[index]), path))
                        count += 1
    except BaseException:
        for _ in range(count):
            session.undo()
        raise
    return tuple(modifications)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--index-0a", type=Path)
    parser.add_argument("--mapping", type=Path, help="JSON list of team/kind/destination rows")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    bundle = read_bundle(args.source)
    receipt = bundle.receipt()
    if args.index_0a:
        slots = destination_slots(args.index_0a)
        assignments = team_mapping(bundle, slots, json.loads(args.mapping.read_text())) if args.mapping else None
        receipt = build_plan(bundle, slots, assignments).receipt
    elif args.mapping:
        parser.error("--mapping requires --index-0a")
    with args.receipt.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
