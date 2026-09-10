"""Pinned, deterministic APF play/formation authoring inside MASTER's capacity.

Plans contain user-authored text, indices and numeric edits only. Source game
data stays in memory. Build always compiles against a pinned baseline; applying
an identical result twice is a no-op, and unrelated current bytes are refused.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import struct
from typing import Mapping

from . import apf2k8_play_codec as c
from .apf2k8_playbook_route_writer import RouteCloneRequest, compile_route_clones
from .errors import ValidationError

SCHEMA = "apf2k8_play_design/v1"
PROVIDER_KIND = "apf_play_design"
SELECTOR = "play-design:apf:playbook:180:0"
STATUS = "Offline verified; experimental / UNWITNESSED in-game; CPU books only"
MAX_PLAN_BYTES = 256 * 1024


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _keys(value: object, keys: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValidationError(f"{label} has missing or unsupported fields.")
    return value


def _name(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValidationError("Enter a nonempty name without leading/trailing spaces.")
    try:
        size = len(value.encode("utf-16be")) // 2
    except UnicodeError as exc:
        raise ValidationError("The name contains an invalid Unicode character.") from exc
    if size > 40 or any(ord(ch) < 32 for ch in value):
        raise ValidationError("Names must use at most 40 UTF-16 units and no control characters.")
    return value


def normalize_plan(value: Mapping) -> dict:
    doc = _keys(value, {"schema", "source_sha256", "plays", "formations", "cpu_calls"}, "Design plan")
    if doc["schema"] != SCHEMA:
        raise ValidationError("Unsupported APF design plan schema.")
    digest = doc["source_sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValidationError("A design plan requires its source SHA-256.")
    for kind in ("plays", "formations", "cpu_calls"):
        if not isinstance(doc[kind], list) or len(doc[kind]) > 176:
            raise ValidationError(f"{kind} must be a bounded list.")
    out = {"schema": SCHEMA, "source_sha256": digest, "plays": [], "formations": [], "cpu_calls": []}
    for kind in ("plays", "formations"):
        seen = set()
        for raw in doc[kind]:
            fields = {"mode", "target", "donor", "name"} | ({"copies", "nodes"} if kind == "plays" else {"positions"})
            r = dict(_keys(raw, fields, kind))
            if r["mode"] not in ("edit", "append", "replace"):
                raise ValidationError("Choose edit, append or explicit slot replacement.")
            maximum = c.PLAY_CAPACITY - 1 if kind == "plays" else c.FORMATION_CAPACITY - 1
            for key in ("target", "donor"):
                c.bounded(r[key], 0, maximum, key)
            if r["target"] in seen:
                raise ValidationError("Two designs target the same slot.")
            seen.add(r["target"])
            if r["mode"] == "edit" and r["target"] != r["donor"]:
                raise ValidationError("An edit must keep its original donor/index.")
            if r["name"] is not None:
                _name(r["name"])
            if r["mode"] != "edit" and r["name"] is None:
                raise ValidationError("New and replacement designs require a custom name.")
            for key, length in (("copies", 2), ("nodes", 4)) if kind == "plays" else (("positions", 4),):
                if not isinstance(r[key], list) or len(r[key]) > 165:
                    raise ValidationError(f"{key} must be a bounded list.")
                rows = []
                row_keys = set()
                for row in r[key]:
                    if not isinstance(row, (list, tuple)) or len(row) != length:
                        raise ValidationError(f"Invalid {key} row.")
                    row = list(row)
                    c.bounded(row[0], 0, 10, "Player slot")
                    if key == "copies":
                        c.bounded(row[1], 0, c.PLAY_CAPACITY - 1, "Donor play")
                        unique = row[0]
                    elif key == "nodes":
                        c.bounded(row[1], 0, 14, "Node position")
                        if not isinstance(row[2], str) or type(row[3]) is not int:
                            raise ValidationError("Node edits need a field name and integer value.")
                        unique = tuple(row[:3])
                    else:
                        c.bounded(row[1], 0, 2, "Alignment variant")
                        for coordinate in row[2:]:
                            c.bounded(coordinate, -32768, 32767, "Alignment coordinate")
                        unique = tuple(row[:2])
                    if unique in row_keys:
                        raise ValidationError(f"Duplicate {key} edit.")
                    row_keys.add(unique)
                    rows.append(row)
                r[key] = rows
            out[kind].append(r)
    for raw in doc["cpu_calls"]:
        r = dict(_keys(raw, {"outer", "record", "play", "formation", "donor_record"}, "CPU call"))
        for key, maximum in (("outer", 1542), ("record", 175), ("play", c.PLAY_CAPACITY - 1), ("formation", 175)):
            c.bounded(r[key], 0, maximum, key)
        if r["donor_record"] is not None:
            c.bounded(r["donor_record"], 0, 175, "CPU donor record")
        out["cpu_calls"].append(r)
    if not any(out[k] for k in ("plays", "formations", "cpu_calls")):
        raise ValidationError("Choose at least one design or CPU book addition.")
    return out


def encode_plan(plan: Mapping) -> bytes:
    payload = (json.dumps(normalize_plan(plan), sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(payload) > MAX_PLAN_BYTES:
        raise ValidationError("APF design plan is too large.")
    return payload


def decode_plan(data: bytes) -> dict:
    if len(data) > MAX_PLAN_BYTES:
        raise ValidationError("APF design plan is too large.")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValidationError(f"Duplicate plan field {key!r}.")
            result[key] = value
        return result
    try:
        return normalize_plan(json.loads(data.decode("utf-8"), object_pairs_hook=pairs))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValidationError(f"Invalid APF design plan: {exc}") from exc


def empty_plan(source: bytes) -> dict:
    return {"schema": SCHEMA, "source_sha256": sha(source), "plays": [], "formations": [], "cpu_calls": []}


@dataclass(frozen=True)
class CompiledDesign:
    replacement: bytes
    report: dict
    plan: dict


def _compile(source: bytes, plan: dict) -> tuple[bytes, list[tuple[int, int]], list[dict]]:
    book = c.Book.from_bytes(source)
    body = bytearray(source)
    allowed: list[tuple[int, int]] = []
    receipt = []
    # Names are rebuilt in their existing order. Replacing a name must not
    # leave an unreferenced string in the strict sequential name pool.
    names = dict(book.names)
    field_names = {48: names[47 + book.book_name_pointer]}
    for base, stride, records in ((c.CATEGORY_BASE, 16, book.categories), (c.FORMATION_BASE, c.FORMATION_SIZE, book.formations), (c.PLAY_BASE, c.PLAY_SIZE, book.plays)):
        for i, r in enumerate(records):
            pointer = r[0] if base == c.CATEGORY_BASE else r.name_pointer
            field_names[base + i * stride] = names[base + i * stride - 1 + pointer]
    name_order = sorted(field_names, key=lambda field: field - 1 + struct.unpack_from(">i", source, field)[0])
    names_changed = False
    for kind, base, stride, original_count, capacity in (
        ("formations", c.FORMATION_BASE, c.FORMATION_SIZE, len(book.formations), c.FORMATION_CAPACITY),
        ("plays", c.PLAY_BASE, c.PLAY_SIZE, len(book.plays), c.PLAY_CAPACITY),
    ):
        count = original_count
        for r in plan[kind]:
            target, donor = r["target"], r["donor"]
            c.bounded(donor, 0, original_count - 1, "Source donor")
            if r["mode"] == "append":
                if target != count or count >= capacity:
                    raise ValidationError(f"Append {kind} at the next free index {count}; capacity {capacity}.")
                if any(body[base + target * stride:base + (target + 1) * stride]):
                    raise ValidationError("The requested record capacity is not zero padding.")
                count += 1
                name_order.append(base + target * stride)
            else:
                c.bounded(target, 0, original_count - 1, "Existing target")
            if r["mode"] == "replace":
                if kind == "plays" and book.plays[target].type_nibble != book.plays[donor].type_nibble:
                    raise ValidationError("Replacement must preserve the destination play type/side for existing CPU calls.")
                if kind == "formations":
                    old, new = book.formations[target], book.formations[donor]
                    if (old.category_index, old.eligible_order, old.slot_order) != (new.category_index, new.eligible_order, new.slot_order):
                        raise ValidationError("Replacement formation must preserve personnel category and slot ordering for existing CPU calls.")
            at, donor_at = base + target * stride, base + donor * stride
            if r["mode"] != "edit":
                body[at:at + stride] = source[donor_at:donor_at + stride]
                allowed.append((at, at + stride))
                if kind == "plays":
                    for slot, assignment in enumerate(book.plays[donor].assignments):
                        field = at + 16 + slot * 8
                        start = assignment.start(donor_at + 16 + slot * 8)
                        struct.pack_into(">i", body, field, c.relative_token(field, c.NODE_BASE + start * 8))
                else:
                    # This relation's meaning is unresolved. Clone the donor's
                    # entire opaque row for a NEW formation; replacements retain
                    # the destination's row. Never manufacture membership bits.
                    if r["mode"] == "append":
                        dst = c.RELATION_BASE + target * c.RELATION_STRIDE
                        src = c.RELATION_BASE + donor * c.RELATION_STRIDE
                        body[dst:dst + c.RELATION_STRIDE] = source[src:src + c.RELATION_STRIDE]
                        allowed.append((dst, dst + c.RELATION_STRIDE))
            if r["name"] is not None:
                field_names[at] = r["name"]
                names_changed = True
            if kind == "formations":
                for slot, variant, x, y in r["positions"]:
                    for field, value in ((at + 32 + slot * 14 + variant * 2, x), (at + 38 + slot * 14 + variant * 2, y)):
                        struct.pack_into(">h", body, field, value)
                        allowed.append((field, field + 2))
            receipt.append({"kind": kind, "mode": r["mode"], "target": target, "donor": donor})
        offset = 0x34 if kind == "formations" else 0x38
        if count != original_count:
            struct.pack_into(">I", body, offset, count)
            allowed.append((offset, offset + 4))
    if names_changed:
        cursor = c.STRING_BASE
        body[c.STRING_BASE:c.STRING_END] = bytes(c.STRING_END - c.STRING_BASE)
        allowed.append((c.STRING_BASE, c.STRING_END))
        for field in name_order:
            text = field_names[field].encode("utf-16be") + b"\0\0"
            if cursor + len(text) > c.STRING_END:
                raise ValidationError("The names do not fit MASTER's fixed string pool.")
            struct.pack_into(">i", body, field, c.relative_token(field, cursor))
            allowed.append((field, field + 4))
            body[cursor:cursor + len(text)] = text
            cursor += len(text)
    # Reparse after record/name creation before delegating shared route copies.
    current = c.Book.from_bytes(bytes(body))
    copies = []
    for r in plan["plays"]:
        for slot, donor in r["copies"]:
            c.bounded(donor, 0, len(book.plays) - 1, "Assignment donor")
            if book.plays[donor].type_nibble != current.plays[r["target"]].type_nibble:
                raise ValidationError("Assignment copies must stay on the same play type/side.")
            # Sequential plans must not silently observe another design's donor
            # rewrite. Resolve all copies before applying any node edits.
            if any(other["target"] == donor and other["mode"] != "edit" for other in plan["plays"]):
                raise ValidationError("A replaced/appended play cannot also be an assignment donor.")
            target = r["target"]
            if current.chain(target, slot) == current.chain(donor, slot) and current.plays[target].assignments[slot].descriptor == current.plays[donor].assignments[slot].descriptor:
                continue
            copies.append(RouteCloneRequest(target, slot, donor, slot))
    if copies:
        compiled = compile_route_clones(bytes(body), copies)
        body = bytearray(compiled.replacement)
        allowed.extend(compiled.changed_ranges)
    # Ownership is measured AFTER all pointer copies. Shared nodes get a private
    # chain appended to proved zero capacity; unique chains are patched in place.
    current = c.Book.from_bytes(bytes(body))
    used = len(current.nodes)
    for r in plan["plays"]:
        grouped: dict[int, list] = {}
        for change in r["nodes"]:
            grouped.setdefault(change[0], []).append(change)
        for slot, changes in sorted(grouped.items()):
            target = r["target"]
            chain = list(current.chain(target, slot))
            original_chain = tuple(chain)
            for _, node, field, value in changes:
                c.bounded(node, 0, len(chain) - 1, "Node within assignment")
                chain[node] = chain[node].with_field(field, value)
            if tuple(chain) == original_chain:
                continue
            pointer_field = c.PLAY_BASE + target * c.PLAY_SIZE + 16 + slot * 8
            start = current.plays[target].assignments[slot].start(pointer_field)
            shared = any(current.references(start + j) != ((target, slot),) for j in range(len(chain)))
            if shared:
                if used + len(chain) > c.NODE_CAPACITY:
                    raise ValidationError("Private assignment does not fit the remaining node pool.")
                start = used
                used += len(chain)
                if any(body[c.NODE_BASE + start * 8:c.NODE_BASE + used * 8]):
                    raise ValidationError("Private node capacity contains nonzero bytes.")
                struct.pack_into(">i", body, pointer_field, c.relative_token(pointer_field, c.NODE_BASE + start * 8))
                allowed.append((pointer_field, pointer_field + 4))
            at = c.NODE_BASE + start * 8
            body[at:at + len(chain) * 8] = b"".join(n.to_bytes() for n in chain)
            allowed.append((at, at + len(chain) * 8))
            receipt.append({"kind": "assignment", "play": target, "slot": slot, "strategy": "private chain" if shared else "in place", "node_count": len(chain)})
    if used != len(current.nodes):
        struct.pack_into(">I", body, 0x40, used)
        allowed.append((0x40, 0x44))
    return bytes(body), allowed, receipt


def verify_design(source: bytes, replacement: bytes, plan: Mapping) -> dict:
    plan = normalize_plan(plan)
    if sha(source) != plan["source_sha256"]:
        raise ValidationError("The design baseline SHA-256 does not match this source.")
    before = c.Book.from_bytes(source)
    after = c.Book.from_bytes(replacement)
    expected, allowed, operations = _compile(source, plan)
    if expected != replacement:
        raise ValidationError("Reparsed design differs from the requested transformation.")
    owned = bytearray(len(source))
    for start, end in allowed:
        owned[start:end] = b"\1" * (end - start)
    changed = [i for i, (a, b) in enumerate(zip(source, replacement, strict=True)) if a != b]
    if any(not owned[i] for i in changed):
        raise ValidationError("Design changed an unowned byte.")
    # Independent semantic checks, in addition to deterministic reproduction.
    for r in plan["plays"]:
        for slot, node, field, value in r["nodes"]:
            actual = after.chain(r["target"], slot)[node]
            if actual.with_field(field, value) != actual:
                raise ValidationError("Reparsed assignment does not contain the requested field.")
    for r in plan["formations"]:
        formation = after.formations[r["target"]]
        for slot, variant, x, y in r["positions"]:
            if formation.slots[slot].x[variant] != x or formation.slots[slot].y[variant] != y:
                raise ValidationError("Reparsed formation alignment differs from the design.")
    for kind, records in (("plays", after.plays), ("formations", after.formations)):
        for r in plan[kind]:
            actual = after.play_name(r["target"]) if kind == "plays" else after.formation_name(r["target"])
            if r["name"] is not None and actual != r["name"]:
                raise ValidationError("Reparsed name differs from the authored name.")
    return {"schema": SCHEMA, "source_sha256": sha(source), "replacement_sha256": sha(replacement),
        "changed_byte_count": len(changed), "counts_before": [len(before.formations), len(before.plays), len(before.nodes)],
        "counts_after": [len(after.formations), len(after.plays), len(after.nodes)], "operations": operations,
        "independent_reparse": True, "opaque_relation_policy": "preserved; new formation copies donor row; meaning unresolved",
        "runtime_status": STATUS, "contains_retail_bytes": False}


def compile_design(source: bytes, plan: Mapping, *, current: bytes | None = None) -> CompiledDesign:
    plan = normalize_plan(plan)
    if sha(source) != plan["source_sha256"]:
        raise ValidationError("The design baseline SHA-256 does not match this source.")
    replacement, _, _ = _compile(source, plan)
    report = verify_design(source, replacement, plan)
    if current is not None and current not in (source, replacement):
        raise ValidationError("Current MASTER differs from both the pinned baseline and this design.")
    report["already_applied"] = current == replacement
    return CompiledDesign(replacement, report, plan)
