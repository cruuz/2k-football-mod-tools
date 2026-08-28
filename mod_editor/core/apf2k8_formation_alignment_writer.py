"""Staged APF MASTER formation alignment edits (where each slot stands).

An APF ``MASTER`` formation record is ``0xB8`` bytes. From ``+0x1E`` it carries
eleven 14-byte slot entries, one per on-field slot, each holding a 16-bit tag
and three ``(x, y)`` alignment pairs stored as ``x[0..2]`` then ``y[0..2]``
(signed 16-bit, about 100 units per yard, ``+x`` toward one sideline and ``+y``
downfield). The executable reads entry ``slot`` at
``formation + 0x1E + slot * 14`` and takes ``x[0]`` from ``+0x20 + slot * 14``
and ``y[0]`` from ``+0x26 + slot * 14`` (``0x84A9B914``..``0x84A9B938``,
``0x847D07B4``..``0x847D07C0``). The slot number is the same number the lineup
builder stamps into the on-field player at ``+0x36`` (``0x8485E7E8``) and the
same index the play record uses for its eleven assignment entries
(``0x84A9BA98``..``0x84A9BAC4`` indexes ``play + 0x0C + i * 8`` and
``formation + 0x1E + i * 14`` with one register).

Two ordered lists of slot numbers sit in front of the table: five bytes at
``+0x0C`` (``0xFF`` where a formation has no eligible receivers) and eleven
bytes at ``+0x11``. The eleven-byte list is read one byte at a time and handed
to the by-slot player lookup ``0x8485EA20`` (``0x84927228``, ``0x84A19D78``),
so its entries are slot numbers, not roles. Retail keeps both lists naming the
same physical spots when it relocates a formation's slots, and this writer does
the same by remapping their values through the inverse permutation.

What this writer does NOT do: it does not change which roster player fills a
slot. Roles come from the personnel category record, not from the formation
(see ``category_slot_role_depth``). It does not move play route assignments,
which stay attached to the slot number. Runtime look is unproved offline.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
from typing import Iterable, Mapping, Sequence

from .apf2k8_package_map_writer import (
    APF_FORMATION_BASE,
    APF_FORMATION_COUNT_MAX,
    APF_FORMATION_COUNT_OFFSET,
    APF_FORMATION_SIZE,
    APF_MASTER_BODY_SIZE,
    apf_formation_count,
    read_apf_formation_name,
)
from .apf2k8_playbook_route_writer import (
    MASTER_ASSET_ID,
    encode_master_play_body,
    read_master_play_body,
)
from .errors import ValidationError


PROVIDER_KIND = "formation_alignment"
REPORT_SCHEMA = "apf2k8_formation_alignment/v1"
PAYLOAD_SCHEMA = "apf2k8_formation_alignment_replacement/v1"
MASTER_OUTER_INDEX = 180

APF_FORMATION_ELIGIBLE_ORDER_OFFSET = 0x0C
APF_FORMATION_ELIGIBLE_ORDER_SIZE = 5
APF_FORMATION_SLOT_ORDER_OFFSET = 0x11
APF_FORMATION_SLOT_ORDER_SIZE = 11
APF_FORMATION_SLOT_TABLE_OFFSET = 0x1E
APF_FORMATION_SLOT_ENTRY_SIZE = 14
APF_FORMATION_SLOT_COUNT = 11
APF_FORMATION_DEFAULT_CATEGORY_OFFSET = 0x05
APF_FORMATION_ALIGNMENT_VARIANTS = 3
APF_FORMATION_NO_SLOT = 0xFF

APF_CATEGORY_BASE = 0x0044
APF_CATEGORY_SIZE = 0x10
APF_CATEGORY_COUNT_OFFSET = 0x3C
APF_CATEGORY_PACKAGE_OFFSET = 0x04
APF_CATEGORY_ROLE_OFFSET = 0x05
APF_CATEGORY_ROLE_MASK = 0x1F
APF_CATEGORY_DEPTH_SHIFT = 5

# Proved by instruction scan; see the module docstring and the report.
APF_ROLE_NAMES = {
    0: "QB",
    1: "K",
    2: "P",
    3: "H",
    4: "WR",
    5: "T",
    6: "C",
    7: "G",
    8: "TE",
    9: "WR",
    10: "HB",
    11: "FB",
}

HONESTY = (
    "This moves a formation's per-slot alignment spots inside MASTER PLAY. "
    "The roster player who fills a slot is chosen by the personnel category "
    "and by slot fill order, not by this table, so a swap moves the spot and "
    "not the depth-chart pick. Play route assignments stay attached to the "
    "slot number, so a swapped slot keeps its old route. Runtime look is "
    "unproved offline; check the formation in Xenia after Build."
)


def _require_apf_master_body(raw: bytes) -> None:
    if len(raw) != APF_MASTER_BODY_SIZE:
        raise ValidationError(
            f"APF MASTER PLAY body is {len(raw):,} bytes; "
            f"{APF_MASTER_BODY_SIZE:,} were expected."
        )


def formation_record_offset(formation_index: int) -> int:
    if type(formation_index) is not int or formation_index < 0:
        raise ValidationError(
            f"formation_index must be a non-negative integer; got {formation_index!r}."
        )
    if formation_index >= APF_FORMATION_COUNT_MAX:
        raise ValidationError(
            f"formation_index must be below {APF_FORMATION_COUNT_MAX}; "
            f"got {formation_index}."
        )
    return APF_FORMATION_BASE + formation_index * APF_FORMATION_SIZE


def formation_slot_entry_offset(formation_index: int, slot: int) -> int:
    if type(slot) is not int or not 0 <= slot < APF_FORMATION_SLOT_COUNT:
        raise ValidationError(f"slot must be 0..10; got {slot!r}.")
    return (
        formation_record_offset(formation_index)
        + APF_FORMATION_SLOT_TABLE_OFFSET
        + slot * APF_FORMATION_SLOT_ENTRY_SIZE
    )


def _check_formation_index(raw_body: bytes, formation_index: int) -> None:
    count = apf_formation_count(raw_body)
    if type(formation_index) is not int or not 0 <= formation_index < count:
        raise ValidationError(
            f"formation_index must be 0..{count - 1}; got {formation_index!r}."
        )


@dataclass(frozen=True, slots=True)
class SlotAlignment:
    """One slot's 14-byte alignment entry: tag plus three ``(x, y)`` pairs."""

    tag: int
    x: tuple[int, int, int]
    y: tuple[int, int, int]

    def __post_init__(self) -> None:
        if type(self.tag) is not int or not 0 <= self.tag <= 0xFFFF:
            raise ValidationError(f"Slot tag must be 0..65535; got {self.tag!r}.")
        for label, values in (("x", self.x), ("y", self.y)):
            if len(values) != APF_FORMATION_ALIGNMENT_VARIANTS:
                raise ValidationError(
                    f"Slot {label} needs {APF_FORMATION_ALIGNMENT_VARIANTS} values; "
                    f"got {len(values)}."
                )
            for item in values:
                if type(item) is not int or not -32768 <= item <= 32767:
                    raise ValidationError(
                        f"Slot {label} values must be signed 16-bit; got {item!r}."
                    )
        object.__setattr__(self, "x", tuple(int(v) for v in self.x))
        object.__setattr__(self, "y", tuple(int(v) for v in self.y))

    @property
    def position_id(self) -> int:
        """Tag high nibble. ``0x84A9BAC4`` reads this byte and shifts it right
        four; ``11`` is the sentinel that makes the caller fall back to the raw
        slot number."""

        return (self.tag >> 4) & 0xF

    def to_bytes(self) -> bytes:
        return struct.pack(">H3h3h", self.tag, *self.x, *self.y)

    @classmethod
    def from_bytes(cls, chunk: bytes) -> "SlotAlignment":
        if len(chunk) != APF_FORMATION_SLOT_ENTRY_SIZE:
            raise ValidationError(
                f"A slot entry is {APF_FORMATION_SLOT_ENTRY_SIZE} bytes; "
                f"got {len(chunk)}."
            )
        fields = struct.unpack(">H3h3h", chunk)
        return cls(fields[0], tuple(fields[1:4]), tuple(fields[4:7]))

    def metadata(self) -> dict[str, object]:
        return {"tag": self.tag, "x": list(self.x), "y": list(self.y)}


def read_formation_alignment(
    raw_body: bytes, formation_index: int
) -> tuple[SlotAlignment, ...]:
    _require_apf_master_body(raw_body)
    _check_formation_index(raw_body, formation_index)
    out = []
    for slot in range(APF_FORMATION_SLOT_COUNT):
        offset = formation_slot_entry_offset(formation_index, slot)
        out.append(
            SlotAlignment.from_bytes(
                raw_body[offset : offset + APF_FORMATION_SLOT_ENTRY_SIZE]
            )
        )
    return tuple(out)


def read_formation_slot_order(raw_body: bytes, formation_index: int) -> tuple[int, ...]:
    _require_apf_master_body(raw_body)
    _check_formation_index(raw_body, formation_index)
    base = formation_record_offset(formation_index) + APF_FORMATION_SLOT_ORDER_OFFSET
    return tuple(raw_body[base : base + APF_FORMATION_SLOT_ORDER_SIZE])


def read_formation_eligible_order(
    raw_body: bytes, formation_index: int
) -> tuple[int, ...]:
    _require_apf_master_body(raw_body)
    _check_formation_index(raw_body, formation_index)
    base = (
        formation_record_offset(formation_index)
        + APF_FORMATION_ELIGIBLE_ORDER_OFFSET
    )
    return tuple(raw_body[base : base + APF_FORMATION_ELIGIBLE_ORDER_SIZE])


def read_formation_default_category(raw_body: bytes, formation_index: int) -> int:
    """Formation ``+0x05`` is four times a MASTER category index in retail
    (162/163 records; ``Block Field Goal`` is the lone exception)."""

    _require_apf_master_body(raw_body)
    _check_formation_index(raw_body, formation_index)
    stored = raw_body[
        formation_record_offset(formation_index)
        + APF_FORMATION_DEFAULT_CATEGORY_OFFSET
    ]
    if stored % 4:
        raise ValidationError(
            f"Formation {formation_index} stores {stored} at +0x05, which is not "
            "four times a category index."
        )
    return stored // 4


def apf_category_count(raw_body: bytes) -> int:
    _require_apf_master_body(raw_body)
    count = struct.unpack_from(">I", raw_body, APF_CATEGORY_COUNT_OFFSET)[0]
    if not 1 <= count <= 64:
        raise ValidationError(f"APF MASTER category count {count} is outside 1..64.")
    if APF_CATEGORY_BASE + count * APF_CATEGORY_SIZE > len(raw_body):
        raise ValidationError("APF category table overruns the MASTER body.")
    return count


def category_slot_role_depth(
    raw_body: bytes, category_index: int, slot: int
) -> tuple[int, int]:
    """Return ``(role, depth_ordinal)`` for one personnel-category slot.

    The lineup builder reads this byte at ``category + 5 + slot`` and masks it
    with ``0x1F`` for the role (``0x848605B4``/``0x848605C0``). The roster
    iterators recompute the same byte and shift it right five
    (``0x847B2170``, ``0x847B2538``), then use only bit 0 of that ordinal
    (``0x847B21BC``, ``0x847B2630``) to pick between the two depth-chart lists
    a role owns. Ordinal bits 1 and up are read and discarded.
    """

    _require_apf_master_body(raw_body)
    count = apf_category_count(raw_body)
    if type(category_index) is not int or not 0 <= category_index < count:
        raise ValidationError(
            f"category_index must be 0..{count - 1}; got {category_index!r}."
        )
    if type(slot) is not int or not 0 <= slot < APF_FORMATION_SLOT_COUNT:
        raise ValidationError(f"slot must be 0..10; got {slot!r}.")
    stored = raw_body[
        APF_CATEGORY_BASE
        + category_index * APF_CATEGORY_SIZE
        + APF_CATEGORY_ROLE_OFFSET
        + slot
    ]
    return stored & APF_CATEGORY_ROLE_MASK, stored >> APF_CATEGORY_DEPTH_SHIFT


def category_depth_order(raw_body: bytes, category_index: int, role: int) -> tuple[int, ...]:
    """Slots that carry ``role``, ordered by the stored depth ordinal."""

    rows = []
    for slot in range(APF_FORMATION_SLOT_COUNT):
        got_role, depth = category_slot_role_depth(raw_body, category_index, slot)
        if got_role == role:
            rows.append((depth, slot))
    return tuple(slot for _depth, slot in sorted(rows))


def alignment_ranking_permutation(
    raw_body: bytes, formation_index: int, role: int, *, category_index: int | None = None
) -> tuple[int, ...]:
    """Permutation that lines the stored depth ordinals up with fill order.

    For every slot carrying ``role``, exchange alignment entries so that the
    slot the builder fills first holds the alignment the data marks ordinal 0.
    Slots that do not carry ``role`` keep their own entry.
    """

    if category_index is None:
        category_index = read_formation_default_category(raw_body, formation_index)
    ordered = category_depth_order(raw_body, category_index, role)
    if len(ordered) < 2:
        raise ValidationError(
            f"Category {category_index} has fewer than two role-{role} slots; "
            "there is nothing to reorder."
        )
    fill_order = sorted(ordered)
    permutation = list(range(APF_FORMATION_SLOT_COUNT))
    for target, source in zip(fill_order, ordered, strict=True):
        permutation[target] = source
    return tuple(permutation)


def _invert(permutation: Sequence[int]) -> tuple[int, ...]:
    inverse = [0] * APF_FORMATION_SLOT_COUNT
    for new_slot, old_slot in enumerate(permutation):
        inverse[old_slot] = new_slot
    return tuple(inverse)


def _remap_order(values: Sequence[int], inverse: Sequence[int]) -> tuple[int, ...]:
    out = []
    for value in values:
        if value == APF_FORMATION_NO_SLOT:
            out.append(APF_FORMATION_NO_SLOT)
        elif 0 <= value < APF_FORMATION_SLOT_COUNT:
            out.append(inverse[value])
        else:
            raise ValidationError(
                f"A stored slot-order byte is {value}, which is neither 0..10 nor 0xFF."
            )
    return tuple(out)


def _check_permutation(permutation: Sequence[int]) -> tuple[int, ...]:
    values = []
    for item in permutation:
        if type(item) is not int:
            raise ValidationError(f"Slot permutation entries must be integers; got {item!r}.")
        values.append(item)
    if sorted(values) != list(range(APF_FORMATION_SLOT_COUNT)):
        raise ValidationError(
            "Slot permutation must be a permutation of 0..10 "
            f"(got {list(permutation)})."
        )
    return tuple(values)


def alignment_selector(formation_index: int) -> str:
    return f"apf:alignment:{MASTER_ASSET_ID}:f{int(formation_index)}"


@dataclass(frozen=True, slots=True)
class FormationAlignmentChange:
    """One formation's replacement slot table plus its two ordered slot lists."""

    formation_index: int
    slots: tuple[SlotAlignment, ...]
    slot_order: tuple[int, ...]
    eligible_order: tuple[int, ...]

    def __post_init__(self) -> None:
        if type(self.formation_index) is not int or self.formation_index < 0:
            raise ValidationError(
                f"formation_index must be a non-negative integer; "
                f"got {self.formation_index!r}."
            )
        if len(self.slots) != APF_FORMATION_SLOT_COUNT:
            raise ValidationError(
                f"A formation needs {APF_FORMATION_SLOT_COUNT} slot entries; "
                f"got {len(self.slots)}."
            )
        for item in self.slots:
            if not isinstance(item, SlotAlignment):
                raise ValidationError("Slot entries must be SlotAlignment values.")
        if len(self.slot_order) != APF_FORMATION_SLOT_ORDER_SIZE:
            raise ValidationError(
                f"The slot order list is {APF_FORMATION_SLOT_ORDER_SIZE} bytes; "
                f"got {len(self.slot_order)}."
            )
        if len(self.eligible_order) != APF_FORMATION_ELIGIBLE_ORDER_SIZE:
            raise ValidationError(
                f"The eligible order list is {APF_FORMATION_ELIGIBLE_ORDER_SIZE} "
                f"bytes; got {len(self.eligible_order)}."
            )
        for label, values in (
            ("slot order", self.slot_order),
            ("eligible order", self.eligible_order),
        ):
            for item in values:
                if type(item) is not int or not (
                    0 <= item < APF_FORMATION_SLOT_COUNT
                    or item == APF_FORMATION_NO_SLOT
                ):
                    raise ValidationError(
                        f"The {label} list takes slot numbers 0..10 or 0xFF; "
                        f"got {item!r}."
                    )
        object.__setattr__(self, "slots", tuple(self.slots))
        object.__setattr__(self, "slot_order", tuple(int(v) for v in self.slot_order))
        object.__setattr__(
            self, "eligible_order", tuple(int(v) for v in self.eligible_order)
        )

    @property
    def selector(self) -> str:
        return alignment_selector(self.formation_index)

    def metadata(self) -> dict[str, object]:
        return {
            "formation_index": self.formation_index,
            "slots": [item.metadata() for item in self.slots],
            "slot_order": list(self.slot_order),
            "eligible_order": list(self.eligible_order),
        }


def permute_formation_slots(
    raw_body: bytes,
    formation_index: int,
    permutation: Sequence[int],
) -> FormationAlignmentChange:
    """Relocate slot alignments. ``permutation[new_slot] = old_slot``.

    Both ordered slot lists are remapped through the inverse permutation so
    they keep naming the same physical spots, which is what retail does between
    ``I Load`` and ``I Load Heavy``.
    """

    order = _check_permutation(permutation)
    current = read_formation_alignment(raw_body, formation_index)
    inverse = _invert(order)
    return FormationAlignmentChange(
        formation_index,
        tuple(current[old] for old in order),
        _remap_order(read_formation_slot_order(raw_body, formation_index), inverse),
        _remap_order(read_formation_eligible_order(raw_body, formation_index), inverse),
    )


def swap_formation_slots(
    raw_body: bytes,
    formation_index: int,
    pairs: Iterable[tuple[int, int]],
) -> FormationAlignmentChange:
    """Exchange the alignment entries of one or more slot pairs."""

    permutation = list(range(APF_FORMATION_SLOT_COUNT))
    touched: set[int] = set()
    normalized = tuple(pairs)
    if not normalized:
        raise ValidationError("Name at least one pair of slots to exchange.")
    for left, right in normalized:
        if type(left) is not int or type(right) is not int:
            raise ValidationError("Slot pairs must be integers.")
        if not 0 <= left < APF_FORMATION_SLOT_COUNT or not (
            0 <= right < APF_FORMATION_SLOT_COUNT
        ):
            raise ValidationError(f"Slot pair ({left}, {right}) is outside 0..10.")
        if left == right:
            raise ValidationError(f"Slot pair ({left}, {right}) names one slot twice.")
        if left in touched or right in touched:
            raise ValidationError(
                f"Slot pair ({left}, {right}) reuses a slot named by another pair."
            )
        touched.add(left)
        touched.add(right)
        permutation[left], permutation[right] = permutation[right], permutation[left]
    return permute_formation_slots(raw_body, formation_index, permutation)


def encode_alignment_payload(change: FormationAlignmentChange) -> bytes:
    payload = {
        "schema": PAYLOAD_SCHEMA,
        "selector": change.selector,
        "formation_index": change.formation_index,
        "slots": [item.metadata() for item in change.slots],
        "slot_order": list(change.slot_order),
        "eligible_order": list(change.eligible_order),
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def change_from_mapping(value: Mapping[str, object]) -> FormationAlignmentChange:
    expected = {"formation_index", "slots", "slot_order", "eligible_order"}
    if set(value) != expected:
        raise ValidationError("A formation alignment edit has unsupported fields.")
    formation_index = value.get("formation_index")
    if type(formation_index) is not int:
        raise ValidationError(
            f"formation_index must be an integer; got {formation_index!r}."
        )
    raw_slots = value.get("slots")
    if not isinstance(raw_slots, (list, tuple)):
        raise ValidationError("Alignment slots must be a list of 11 entries.")
    slots = []
    for item in raw_slots:
        if not isinstance(item, Mapping) or set(item) != {"tag", "x", "y"}:
            raise ValidationError("Each alignment slot needs exactly tag, x and y.")
        raw_x = item.get("x")
        raw_y = item.get("y")
        if not isinstance(raw_x, (list, tuple)) or not isinstance(raw_y, (list, tuple)):
            raise ValidationError("Alignment x and y must be lists of three numbers.")
        slots.append(
            SlotAlignment(
                item.get("tag"),  # type: ignore[arg-type]
                tuple(raw_x),  # type: ignore[arg-type]
                tuple(raw_y),  # type: ignore[arg-type]
            )
        )
    raw_order = value.get("slot_order")
    raw_eligible = value.get("eligible_order")
    if not isinstance(raw_order, (list, tuple)) or not isinstance(
        raw_eligible, (list, tuple)
    ):
        raise ValidationError("Both order lists must be lists of slot numbers.")
    return FormationAlignmentChange(
        formation_index, tuple(slots), tuple(raw_order), tuple(raw_eligible)
    )


def decode_alignment_payload(
    raw: bytes, expected_selector: str
) -> FormationAlignmentChange:
    def no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValidationError(
                    f"Alignment payload repeats JSON key {key!r}: {expected_selector}"
                )
            result[key] = value
        return result

    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except ValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("Alignment payload is not JSON.") from exc
    except RecursionError as exc:
        raise ValidationError(
            "Alignment payload is too deeply nested to be JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise ValidationError("Alignment payload is not an object.")
    if payload.get("schema") != PAYLOAD_SCHEMA:
        raise ValidationError("Alignment payload schema changed.")
    if payload.get("selector") != expected_selector:
        raise ValidationError("Alignment payload selector changed.")
    change = change_from_mapping(
        {
            "formation_index": payload.get("formation_index"),
            "slots": payload.get("slots"),
            "slot_order": payload.get("slot_order"),
            "eligible_order": payload.get("eligible_order"),
        }
    )
    if change.selector != expected_selector:
        raise ValidationError("Alignment payload formation index changed.")
    return change


def _changed_ranges(formation_index: int) -> tuple[tuple[int, int], ...]:
    base = formation_record_offset(formation_index)
    return (
        (
            base + APF_FORMATION_ELIGIBLE_ORDER_OFFSET,
            base + APF_FORMATION_ELIGIBLE_ORDER_OFFSET
            + APF_FORMATION_ELIGIBLE_ORDER_SIZE,
        ),
        (
            base + APF_FORMATION_SLOT_ORDER_OFFSET,
            base + APF_FORMATION_SLOT_ORDER_OFFSET + APF_FORMATION_SLOT_ORDER_SIZE,
        ),
        (
            base + APF_FORMATION_SLOT_TABLE_OFFSET,
            base
            + APF_FORMATION_SLOT_TABLE_OFFSET
            + APF_FORMATION_SLOT_COUNT * APF_FORMATION_SLOT_ENTRY_SIZE,
        ),
    )


def build_formation_alignment_patch(
    raw_body: bytes, change: FormationAlignmentChange
) -> bytes:
    _require_apf_master_body(raw_body)
    _check_formation_index(raw_body, change.formation_index)
    out = bytearray(raw_body)
    base = formation_record_offset(change.formation_index)
    start = base + APF_FORMATION_ELIGIBLE_ORDER_OFFSET
    out[start : start + APF_FORMATION_ELIGIBLE_ORDER_SIZE] = bytes(
        change.eligible_order
    )
    start = base + APF_FORMATION_SLOT_ORDER_OFFSET
    out[start : start + APF_FORMATION_SLOT_ORDER_SIZE] = bytes(change.slot_order)
    for slot, entry in enumerate(change.slots):
        start = base + APF_FORMATION_SLOT_TABLE_OFFSET + slot * APF_FORMATION_SLOT_ENTRY_SIZE
        out[start : start + APF_FORMATION_SLOT_ENTRY_SIZE] = entry.to_bytes()
    result = bytes(out)
    if len(result) != len(raw_body):
        raise ValidationError("APF alignment patch changed the MASTER body size.")
    return result


def verify_formation_alignment_patch(
    source: bytes, patched: bytes, change: FormationAlignmentChange
) -> None:
    """Independent check: recompute every whitelisted byte, refuse other drift."""

    _require_apf_master_body(source)
    _require_apf_master_body(patched)
    if len(source) != len(patched):
        raise ValidationError(
            f"Patched MASTER length {len(patched)} != source {len(source)}."
        )
    allowed: set[int] = set()
    for start, end in _changed_ranges(change.formation_index):
        allowed.update(range(start, end))
    for index, (left, right) in enumerate(zip(source, patched, strict=True)):
        if left != right and index not in allowed:
            raise ValidationError(
                f"Byte {index} changed outside APF formation "
                f"{change.formation_index}'s alignment region."
            )
    if read_formation_alignment(patched, change.formation_index) != change.slots:
        raise ValidationError(
            f"Formation {change.formation_index} alignment did not stick."
        )
    if read_formation_slot_order(patched, change.formation_index) != change.slot_order:
        raise ValidationError(
            f"Formation {change.formation_index} slot order did not stick."
        )
    if (
        read_formation_eligible_order(patched, change.formation_index)
        != change.eligible_order
    ):
        raise ValidationError(
            f"Formation {change.formation_index} eligible order did not stick."
        )
    base = formation_record_offset(change.formation_index)
    expected = bytearray(source[base : base + APF_FORMATION_SIZE])
    start = APF_FORMATION_ELIGIBLE_ORDER_OFFSET
    expected[start : start + APF_FORMATION_ELIGIBLE_ORDER_SIZE] = bytes(
        change.eligible_order
    )
    start = APF_FORMATION_SLOT_ORDER_OFFSET
    expected[start : start + APF_FORMATION_SLOT_ORDER_SIZE] = bytes(change.slot_order)
    for slot, entry in enumerate(change.slots):
        start = APF_FORMATION_SLOT_TABLE_OFFSET + slot * APF_FORMATION_SLOT_ENTRY_SIZE
        expected[start : start + APF_FORMATION_SLOT_ENTRY_SIZE] = entry.to_bytes()
    if patched[base : base + APF_FORMATION_SIZE] != bytes(expected):
        raise ValidationError(
            f"Formation {change.formation_index} record does not match an "
            "independently rebuilt record."
        )


def compile_formation_alignments(
    raw_body: bytes, changes: Iterable[FormationAlignmentChange]
) -> tuple[bytes, tuple[tuple[int, int], ...]]:
    normalized = tuple(changes)
    if not normalized:
        raise ValidationError("Select at least one formation alignment to edit.")
    seen: set[int] = set()
    for change in normalized:
        if change.formation_index in seen:
            raise ValidationError(
                f"Two alignment edits name formation {change.formation_index}."
            )
        seen.add(change.formation_index)
    effective = tuple(
        change
        for change in normalized
        if (
            read_formation_alignment(raw_body, change.formation_index) != change.slots
            or read_formation_slot_order(raw_body, change.formation_index)
            != change.slot_order
            or read_formation_eligible_order(raw_body, change.formation_index)
            != change.eligible_order
        )
    )
    if not effective:
        raise ValidationError(
            "These alignments already match the game; nothing would change "
            f"(formations {sorted(seen)})."
        )
    working = raw_body
    ranges: list[tuple[int, int]] = []
    for change in effective:
        patched = build_formation_alignment_patch(working, change)
        verify_formation_alignment_patch(working, patched, change)
        working = patched
        ranges.extend(_changed_ranges(change.formation_index))
    return working, tuple(sorted(ranges))


def build_formation_alignment_edits(
    index_path: Path, changes: Iterable[FormationAlignmentChange]
) -> tuple[int, bytes, dict[str, object]]:
    """Compile alignments into outer 180. Source 0A is not written."""

    normalized = tuple(changes)
    original = read_master_play_body(index_path)
    body, ranges = compile_formation_alignments(original, normalized)
    entry_bytes, h7a = encode_master_play_body(index_path, body)
    rows = []
    for change in normalized:
        before = read_formation_alignment(original, change.formation_index)
        rows.append(
            {
                "formation_index": change.formation_index,
                "formation_name": read_apf_formation_name(
                    original, change.formation_index
                ),
                "old_slots": [item.metadata() for item in before],
                "new_slots": [item.metadata() for item in change.slots],
                "old_slot_order": list(
                    read_formation_slot_order(original, change.formation_index)
                ),
                "new_slot_order": list(change.slot_order),
                "old_eligible_order": list(
                    read_formation_eligible_order(original, change.formation_index)
                ),
                "new_eligible_order": list(change.eligible_order),
                "resource_offset": formation_record_offset(change.formation_index),
            }
        )
    report: dict[str, object] = {
        "schema": REPORT_SCHEMA,
        "kind": "formation_alignment",
        "outer_index": MASTER_OUTER_INDEX,
        "honesty": HONESTY,
        "formations": rows,
        "source_sha256": hashlib.sha256(original).hexdigest(),
        "result_sha256": hashlib.sha256(body).hexdigest(),
        "changed_byte_count": sum(
            1 for left, right in zip(original, body, strict=True) if left != right
        ),
        "changed_ranges": [[start, end] for start, end in ranges],
        "h7a_transport": h7a.get("h7a_transport"),
        "output_entry_size": h7a.get("output_entry_size"),
        "output_entry_sha256": h7a.get("output_entry_sha256"),
        "writer_schema": REPORT_SCHEMA,
        "claims": {
            "alignment_bytes_edited": True,
            "slot_entry_layout_static_proved": True,
            "depth_chart_pick_changed": False,
            "route_assignments_moved": False,
            "runtime_proved": False,
            "source_0a_untouched": True,
        },
    }
    return MASTER_OUTER_INDEX, entry_bytes, report


__all__ = [
    "APF_CATEGORY_BASE",
    "APF_CATEGORY_PACKAGE_OFFSET",
    "APF_CATEGORY_ROLE_MASK",
    "APF_CATEGORY_ROLE_OFFSET",
    "APF_CATEGORY_SIZE",
    "APF_FORMATION_ALIGNMENT_VARIANTS",
    "APF_FORMATION_DEFAULT_CATEGORY_OFFSET",
    "APF_FORMATION_ELIGIBLE_ORDER_OFFSET",
    "APF_FORMATION_ELIGIBLE_ORDER_SIZE",
    "APF_FORMATION_NO_SLOT",
    "APF_FORMATION_SLOT_COUNT",
    "APF_FORMATION_SLOT_ENTRY_SIZE",
    "APF_FORMATION_SLOT_ORDER_OFFSET",
    "APF_FORMATION_SLOT_ORDER_SIZE",
    "APF_FORMATION_SLOT_TABLE_OFFSET",
    "APF_ROLE_NAMES",
    "HONESTY",
    "MASTER_OUTER_INDEX",
    "PAYLOAD_SCHEMA",
    "PROVIDER_KIND",
    "REPORT_SCHEMA",
    "FormationAlignmentChange",
    "SlotAlignment",
    "alignment_ranking_permutation",
    "alignment_selector",
    "apf_category_count",
    "build_formation_alignment_edits",
    "build_formation_alignment_patch",
    "category_depth_order",
    "category_slot_role_depth",
    "change_from_mapping",
    "compile_formation_alignments",
    "decode_alignment_payload",
    "encode_alignment_payload",
    "formation_record_offset",
    "formation_slot_entry_offset",
    "permute_formation_slots",
    "read_formation_alignment",
    "read_formation_default_category",
    "read_formation_eligible_order",
    "read_formation_slot_order",
    "swap_formation_slots",
    "verify_formation_alignment_patch",
]
