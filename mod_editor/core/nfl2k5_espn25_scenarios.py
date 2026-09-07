"""EXPERIMENTAL / UNWITNESSED ESPN Anniversary authoring and historic rosters.

Fixed-span resource editor. No XBE owner, profile writes or expanded-table install.
See docs/mod_editor/nfl2k5_espn25_research.md for native evidence and limitations.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import struct
import tempfile
import zlib

from . import nfl2k5_roster_records as rr
from .nfl2k5_safe_text_banks import encode_fixed_utf16le

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data/nfl2k5_espn25_layout.json"
SCHEMA = "nfl2k5.espn25.edits.v1"
PLAN_SCHEMA = "nfl2k5.espn25.plan.v1"
DRAFT_SCHEMA = "nfl2k5.espn25.research.v1"
LABEL = "EXPERIMENTAL / UNWITNESSED"
REQUESTS = ()  # Deliberately no XBE installation until paging and save proof exist.
MAX_JSON = 2 * 1024 * 1024
MAX_RESOURCE = 1024 * 1024
COUNT, RECORDS, STRIDE = 25, 0x44, 0x6C
TEXT = {"title": 0, "description": 4, "objective": 8, "date": 12}
POINTERS = (0, 4, 8, 12, 20, 24)
# offset, native scalar format, conservative authoring bounds
SETUP = {
    "stadium_index": (0x10, "I", 0, 30),
    "human_side": (0x24, "I", 0, 1), "possession_side": (0x28, "I", 0, 1),
    "away_score": (0x2C, "I", 0, 99), "away_historical_score": (0x30, "I", 0, 99),
    "home_score": (0x34, "I", 0, 99), "home_historical_score": (0x38, "I", 0, 99),
    "quarter_index": (0x3C, "I", 0, 3), "ball_yards": (0x40, "f", -49, 49),
    "yards_to_gain": (0x44, "f", 0.01, 99), "down": (0x48, "I", 0, 4),
    "clock_seconds": (0x4C, "f", 0, 900),
    "away_timeouts": (0x50, "I", 0, 3), "home_timeouts": (0x54, "I", 0, 3),
}
APPEARANCE = ("skin", "face", "body", "dreads", "eye_black", "helmet", "face_mask",
              "face_shield", "mouthpiece", "turtleneck", "sleeves", "neck_roll",
              "left_glove", "right_glove", "left_wrist", "right_wrist", "left_elbow",
              "right_elbow", "left_shoe", "right_shoe")
CSV_COLUMNS = ("pool", "index", "first", "last", "position", "jersey", "years_pro",
               "height", "weight", "hand") + APPEARANCE + rr.RATING_BYTE_ORDER


class Espn25Error(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise Espn25Error(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def u32(data, at):
    require(0 <= at <= len(data) - 4, "truncated scalar")
    return struct.unpack_from("<I", data, at)[0]


def rel(data, at):
    require(0 <= at <= len(data) - 4, "truncated pointer")
    return at + struct.unpack_from("<i", data, at)[0] - 1


def utf16(data, at, end=None):
    end = len(data) if end is None else end
    require(0 <= at < end <= len(data) and at % 2 == 0, "invalid text pointer")
    stop = at
    while stop + 1 < end and data[stop:stop + 2] != b"\0\0":
        stop += 2
    require(stop + 1 < end, "unterminated text")
    try:
        return bytes(data[at:stop]).decode("utf-16le")
    except UnicodeError as exc:
        raise Espn25Error("invalid UTF-16 text") from exc


def keys(value, allowed, required=()):
    require(isinstance(value, dict), "expected an object")
    require(set(required) <= set(value) <= set(allowed), "missing or unsupported fields: " + str(sorted(value)))


def integer(value, low, high, label):
    require(type(value) is int and low <= value <= high, f"{label}: expected integer {low}..{high}")
    return value


def text_bytes(value, capacity=16384):
    require(isinstance(value, str) and value.strip() and "\0" not in value, "text must be nonempty without NUL")
    try:
        raw = value.encode("utf-16le") + b"\0\0"
    except UnicodeError as exc:
        raise Espn25Error("invalid Unicode text") from exc
    require(len(raw) <= capacity, f"text needs {len(raw)} bytes; allocation holds {capacity}")
    return raw


def read_json(path):
    # No unbounded read, including hostile input files. Reject duplicate keys and NaN.
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key: " + key)
            result[key] = value
        return result
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_JSON + 1)
    require(len(raw) <= MAX_JSON, "JSON exceeds 2 MiB")
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda x: (_ for _ in ()).throw(Espn25Error("nonfinite JSON number")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Espn25Error("invalid JSON") from exc


def write_json(path, value):
    target = Path(path).resolve()
    raw = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    require(len(raw) <= MAX_JSON, "JSON exceeds 2 MiB; split the edits into smaller plans")
    with tempfile.TemporaryDirectory(prefix="espn25-json-", dir=target.parent) as temporary:
        staged = Path(temporary).resolve() / "result.json"
        staged.write_bytes(raw)
        os.replace(staged, target)


def roster_mask(resource, pin):
    """Only existing codec fields and the proved player-name pool are owned."""
    mask = bytearray(len(resource))
    supported = set(CSV_COLUMNS) | {"first_name_pointer", "last_name_pointer", "weight_raw"}
    supported.update({"skin_low", "skin_high", "left_glove_low", "left_glove_high",
                      "left_wrist_low", "left_wrist_high", "left_elbow_low", "left_elbow_high"})
    for index in range(53):
        base = 32 + pin["primary_table"] + index * rr.PLAYER_SIZE
        for field in rr.FIELDS:
            if field.name in supported:
                bits = field.mask.to_bytes(field.size, "little")
                for i, value in enumerate(bits):
                    mask[base + field.offset + i] |= value
    start, end = pin["names"]
    mask[32 + start:32 + end] = b"\xff" * (end - start)
    return mask


def masked_sha(resource, mask):
    require(len(resource) == len(mask), "resource size changed")
    return sha(bytes(byte & (255 ^ bits) for byte, bits in zip(resource, mask)))


def situ_mask(resource, pin):
    mask = bytearray(len(resource))
    for row in range(COUNT):
        base = 32 + RECORDS + row * STRIDE
        for offset, _, _, _ in SETUP.values():
            mask[base + offset:base + offset + 4] = b"\xff" * 4
        for offset in (0x1C, 0x20):
            mask[base + offset:base + offset + 4] = b"\xff" * 4
        # Known retail bundles only; units/enums stay opaque to authoring.
        mask[base + 0x60:base + 0x6C] = b"\xff" * 12
    for start, size in pin["strings"]:
        mask[32 + start:32 + start + size] = b"\xff" * size
    return mask


class Catalog:
    """Bounded resources, detached from the source handles; safe to host in Qt."""
    def __init__(self, resources, manifest=None):
        self.manifest = read_json(MANIFEST) if manifest is None else manifest
        self.resources = dict(resources)  # outer -> (name_id, resource bytes)
        self.descriptors = self._descriptors()
        self.by_team = {(d["selector"].casefold(), d["year"]): d for d in self.descriptors}
        self.situ = self._validate_situ(self.resource(22))
        # All historic resources are validated before presenting any editing surface.
        for descriptor in self.descriptors:
            self.validate_roster(descriptor["outer"], self.resource(descriptor["outer"]))

    @classmethod
    def load(cls, path):
        source = Path(path)
        if source.name == "0" and source.is_file():
            source = source.parent
        manifest = read_json(MANIFEST)
        resources = {}
        with rr._outer_image()(source) as archive:
            for index in (5, 22, *map(int, manifest["rosters"])):
                require(index < len(archive.entries), f"missing outer entry {index}")
                entry = archive.entries[index]
                require(32 <= entry.size <= MAX_RESOURCE, f"outer {index}: resource exceeds bound")
                resources[index] = (entry.name_id, archive.read(entry.virtual_offset, entry.size))
        return cls(resources, manifest)

    def resource(self, index):
        require(index in self.resources, f"missing resource {index}")
        identity, data = self.resources[index]
        require(isinstance(data, bytes) and 32 <= len(data) <= MAX_RESOURCE, "resource exceeds bound")
        pin = self.manifest["main" if index == 5 else "situ"] if index in (5, 22) else self.manifest["rosters"].get(str(index))
        require(pin is not None and identity == pin["id"] and len(data) == pin["size"], f"outer {index}: foreign identity or size")
        return data

    def _descriptors(self):
        raw = self.resource(5)
        pin = self.manifest["main"]
        require(raw[:32].hex() == pin["header"], "foreign main ROST wrapper")
        body = raw[32:]
        require(body[12:16] == b"ROST" and rel(body, 20) == 64 and u32(body, 0x98) == 75,
                "foreign main historic descriptor layout")
        table = rel(body, 0x9C)
        require(table == pin["table"] and table + 75 * 16 <= len(body), "foreign historic descriptor table")
        descriptors = []
        for index in range(75):
            at = table + 16 * index
            year = struct.unpack_from("<H", body, at)[0]
            selector = utf16(body, rel(body, at + 12))
            code = utf16(body, at + 4, at + 12)
            kit = body[at + 2]
            filename = f"h-{code}-{year}-{selector}-{kit}.iff"
            identity = zlib.crc32(filename.upper().encode("utf-16le")) & 0xFFFFFFFF
            outer = next((int(i) for i, p in self.manifest["rosters"].items() if p["id"] == identity), None)
            require(outer is not None, "unrecognized historic resource selector")
            descriptors.append(dict(index=index, year=year, kit=kit, code=code, selector=selector,
                                    filename=filename, id=identity, outer=outer))
        require(sha(json.dumps(descriptors, sort_keys=True).encode()) == pin["descriptor_sha256"], "foreign historic descriptor content")
        return descriptors

    def validate_roster(self, index, raw):
        pin = self.manifest["rosters"].get(str(index))
        require(pin is not None and len(raw) == pin["size"], "foreign historic ROST size")
        require(masked_sha(raw, roster_mask(raw, pin)) == pin["guard_sha256"], f"outer {index}: foreign historic ROST layout or protected field")
        body = raw[32:]
        start, end = pin["names"]
        targets = set()
        for row in range(53):
            at = pin["primary_table"] + rr.PLAYER_SIZE * row
            for offset in (16, 20):
                target = rel(body, at + offset)
                require(start <= target < end, "player name escapes its owned pool")
                utf16(body, target, end)
                targets.add(target)
            require(body[at + 0x35] < len(rr.POSITIONS), "invalid position")
        try:
            document = rr.RosterDocument(body)
        except (ValueError, IndexError, struct.error) as exc:
            raise Espn25Error("invalid historic roster") from exc
        require(len(document.players) == 53 and len(document.teams) == 1 and
                document.primary_table == pin["primary_table"], "foreign historic roster tables")
        ordered = sorted(targets)
        for target, limit in zip(ordered, ordered[1:] + [end]):
            utf16(body, target, limit)  # distinct live allocations cannot overlap
        # Reopening a shortened first/last allocation must retain all originally
        # owned free space, including the edges the generic codec cannot infer.
        pool = document.names
        if pool.start > start:
            pool._merge(pool.free, start, pool.start - start)
        if pool.end < end:
            pool._merge(pool.free, pool.end, end - pool.end)
        pool.start, pool.end = start, end
        return document

    def _validate_situ(self, raw):
        pin = self.manifest["situ"]
        require(len(raw) == pin["size"] and masked_sha(raw, situ_mask(raw, pin)) == pin["guard_sha256"],
                "foreign SITU layout, wrapper or sibling resource")
        body = raw[32:32 + 29104]
        for start, size in pin["strings"]:
            utf16(body, start, start + size)
        for row in range(COUNT):
            record = body[RECORDS + row * STRIDE:RECORDS + (row + 1) * STRIDE]
            for name, (offset, fmt, low, high) in SETUP.items():
                value = struct.unpack_from("<" + fmt, record, offset)[0]
                require(math.isfinite(value) and low <= value <= high, f"moment {row}: invalid {name}")
            require(record[0x60:0x6C].hex() in pin["conditions"], "unknown condition bundle")
            for side, ptr, year in (("away", 20, 28), ("home", 24, 32)):
                at = RECORDS + row * STRIDE
                require((utf16(body, rel(body, at + ptr)).casefold(), u32(record, year)) in self.by_team,
                        f"moment {row} {side}: no historic name/year match")
        return body

    def moment(self, index):
        integer(index, 0, 24, "moment")
        base = RECORDS + index * STRIDE
        result = {"moment": index, "text": {name: utf16(self.situ, rel(self.situ, base + offset)) for name, offset in TEXT.items()},
                  "setup": {name: struct.unpack_from("<" + fmt, self.situ, base + offset)[0] for name, (offset, fmt, _, _) in SETUP.items()},
                  "conditions_raw": self.situ[base + 0x60:base + 0x6C].hex(), "teams": {}}
        for side, pointer, year in (("away", 20, 28), ("home", 24, 32)):
            result["teams"][side] = {"selector": utf16(self.situ, rel(self.situ, base + pointer)), "year": u32(self.situ, base + year)}
        return result

    def binding(self, moment, side):
        require(side in ("away", "home"), "side must be away or home")
        team = self.moment(moment)["teams"][side]
        return dict(self.by_team[(team["selector"].casefold(), team["year"])])

    def shared_uses(self, index):
        return [{"moment": i, "side": side} for i in range(COUNT) for side in ("away", "home") if self.binding(i, side)["outer"] == index]

    def roster_document(self, moment, side):
        index = self.binding(moment, side)["outer"]
        return self.validate_roster(index, self.resource(index))

    def export_csv(self, moment, side):
        # Use the existing Rosters codec, retaining only supported historic fields.
        original = csv.DictReader(io.StringIO(rr.export_csv(self.roster_document(moment, side))))
        stream = io.StringIO()
        writer = csv.DictWriter(stream, CSV_COLUMNS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(original)
        return stream.getvalue()

    def import_csv(self, moment, side, value):
        require(isinstance(value, str) and len(value.encode("utf-8")) <= 256 * 1024, "CSV exceeds 256 KiB")
        reader = csv.DictReader(io.StringIO(value), strict=True)
        columns = reader.fieldnames or []
        require(len(columns) == len(set(columns)) and {"pool", "index"} <= set(columns) <= set(CSV_COLUMNS), "CSV needs pool/index and supported, unique columns")
        seen = set()
        for row in reader:
            require(None not in row and None not in row.values(), "CSV row width differs from header")
            require(row["pool"] == "primary" and row["index"].isascii() and row["index"].isdigit(), "CSV needs primary pool and numeric index")
            index = integer(int(row["index"]), 0, 52, "player index")
            require(index not in seen, "duplicate CSV player")
            seen.add(index)
            for name in rr.RATING_BYTE_ORDER:
                if row.get(name):
                    try:
                        integer(int(row[name]), 0, 100, name)
                    except ValueError as exc:
                        raise Espn25Error(f"{name}: expected rating 0..100") from exc
            if row.get("jersey"):
                try:
                    integer(int(row["jersey"]), 0, 99, "jersey")
                except ValueError as exc:
                    raise Espn25Error("jersey: expected 0..99") from exc
        require(seen, "CSV has no player rows")
        document = self.roster_document(moment, side)  # isolated; partial codec errors never escape
        receipt = rr.import_csv(document, value, delimiter=",")
        require(not receipt["log"] and receipt["rows"] == len(seen), "CSV refused: " + "; ".join(receipt["log"]))
        index = self.binding(moment, side)["outer"]
        raw = self.resource(index)[:32] + document.to_body()
        self.validate_roster(index, raw)
        return raw, receipt

    def _edit_record(self, body, index, edit, fixed):
        keys(edit, {"moment", "template", "text", "teams", "setup", "conditions_from_moment"})
        base = RECORDS + index * STRIDE
        texts = edit.get("text", {})
        keys(texts, TEXT)
        teams = edit.get("teams", {})
        keys(teams, ("away", "home"))
        replacements = {TEXT[name]: value for name, value in texts.items()}
        for side, team in teams.items():
            keys(team, ("selector", "year"), ("selector", "year"))
            integer(team["year"], 1900, 2100, "roster year")
            require(isinstance(team["selector"], str), "selector must be text")
            key = (team["selector"].casefold(), team["year"])
            require(key in self.by_team, "team/year must name an existing historic roster")
            pointer, year_at = (20, 28) if side == "away" else (24, 32)
            replacements[pointer] = self.by_team[key]["selector"]
            struct.pack_into("<I", body, base + year_at, team["year"])
        if fixed:
            allocations = dict(self.manifest["situ"]["strings"])
            for pointer, value in replacements.items():
                target = rel(body, base + pointer)
                capacity = allocations[target]
                text_bytes(value, capacity)
                body[target:target + capacity] = encode_fixed_utf16le(value, capacity, "Anniversary text")
        setup = edit.get("setup", {})
        keys(setup, SETUP)
        for name, value in setup.items():
            offset, fmt, low, high = SETUP[name]
            require(type(value) in ((int,) if fmt == "I" else (int, float)) and math.isfinite(value) and low <= value <= high,
                    f"{name}: expected finite {'integer' if fmt == 'I' else 'number'} {low}..{high}")
            struct.pack_into("<" + fmt, body, base + offset, value)
        if "conditions_from_moment" in edit:
            source = integer(edit["conditions_from_moment"], 0, 24, "conditions source")
            start = RECORDS + source * STRIDE + 0x60
            body[base + 0x60:base + 0x6C] = self.situ[start:start + 12]
        return replacements

    def prepare(self, edits):
        require(isinstance(edits, dict) and edits.get("schema") == SCHEMA,
                "unsupported edit schema; expanded tables cannot be installed")
        keys(edits, ("schema", "moments", "rosters"), ("schema",))
        moments, rosters = edits.get("moments", []), edits.get("rosters", [])
        require(isinstance(moments, list) and len(moments) <= 25 and isinstance(rosters, list) and len(rosters) <= 75, "edit list exceeds bound")
        replacements = {22: self.resource(22)}
        body, seen = bytearray(self.situ), set()
        for edit in moments:
            keys(edit, ("moment", "text", "teams", "setup", "conditions_from_moment"), ("moment",))
            index = integer(edit["moment"], 0, 24, "moment")
            require(index not in seen, "duplicate moment edit")
            seen.add(index)
            self._edit_record(body, index, edit, True)
        replacements[22] = self.resource(22)[:32] + bytes(body) + self.resource(22)[32 + len(body):]
        # Bind imports to the final selectors, so a team edit and CSV have one meaning.
        edited = Catalog({**self.resources, 22: (self.resources[22][0], replacements[22])}, self.manifest)
        notes = []
        for edit in rosters:
            keys(edit, ("moment", "side", "shared_resource", "csv"), ("moment", "side", "shared_resource", "csv"))
            require(edit["shared_resource"] is True, "historic roster edits require shared_resource: true")
            index = edited.binding(edit["moment"], edit["side"])["outer"]
            require(index not in replacements, "two imports target the same shared historic resource")
            replacements[index], receipt = edited.import_csv(edit["moment"], edit["side"], edit["csv"])
            notes.append({"outer": index, "shared_uses": edited.shared_uses(index), "historic_team_outside_mode": True, "csv": receipt})
        resources = [resource_plan(index, self.resources[index][0], self.resource(index), raw) for index, raw in sorted(replacements.items())]
        return {"schema": PLAN_SCHEMA, "label": LABEL, "main_descriptor_sha256": self.manifest["main"]["descriptor_sha256"],
                "resources": resources, "rosters": notes}

    def research_table(self, draft):
        """Compile an in-memory 26..32 table; no writer accepts this output."""
        keys(draft, ("schema", "append"), ("schema", "append"))
        require(draft["schema"] == DRAFT_SCHEMA, "unsupported research schema")
        appended = draft["append"]
        require(isinstance(appended, list) and 1 <= len(appended) <= 7, "research append count must be 1..7; saves above 32 need migration")
        count = COUNT + len(appended)
        body = bytearray(self.situ[:RECORDS + COUNT * STRIDE])
        rows = [{offset: utf16(self.situ, rel(self.situ, RECORDS + i * STRIDE + offset)) for offset in POINTERS} for i in range(COUNT)]
        for edit in appended:
            keys(edit, ("template", "text", "teams", "setup", "conditions_from_moment"), ("template", "text", "teams", "setup"))
            template = integer(edit["template"], 0, 24, "template")
            keys(edit["text"], TEXT, TEXT)
            keys(edit["teams"], ("away", "home"), ("away", "home"))
            keys(edit["setup"], SETUP, SETUP)
            at = RECORDS + template * STRIDE
            body.extend(self.situ[at:at + STRIDE])
            replacement = self._edit_record(body, len(rows), edit, False)
            rows.append({**rows[template], **replacement})
        struct.pack_into("<I", body, 64, count)
        for index, row in enumerate(rows):
            for offset in POINTERS:
                raw = text_bytes(row[offset])
                at = RECORDS + index * STRIDE + offset
                struct.pack_into("<i", body, at, len(body) - at + 1)
                body.extend(raw)
        body.extend(bytes(-len(body) % 16))  # resource collection siblings start on 16-byte boundaries
        require(len(body) <= 256 * 1024, "research table exceeds 256 KiB")
        wrapper = bytearray(self.resource(22)[:32])
        struct.pack_into("<II", wrapper, 4, len(body), count)
        return bytes(wrapper + body)


def resource_plan(index, identity, before, after):
    require(len(before) == len(after), "fixed-span edits cannot change size")
    changes, start = [], None
    for at in range(len(before) + 1):
        differs = at < len(before) and before[at] != after[at]
        if differs and start is None:
            start = at
        if not differs and start is not None:
            changes.append({"offset": start, "before": before[start:at].hex(), "after": after[start:at].hex()})
            start = None
    return {"outer": index, "id": identity, "size": len(before), "before_sha256": sha(before), "after_sha256": sha(after), "changes": changes}


def resolve_plan(catalog, plan):
    """Preflight every resource and full before/after digest before any write."""
    keys(plan, ("schema", "label", "main_descriptor_sha256", "resources", "rosters"), ("schema", "main_descriptor_sha256", "resources"))
    require(plan["schema"] == PLAN_SCHEMA and plan["main_descriptor_sha256"] == catalog.manifest["main"]["descriptor_sha256"], "foreign plan identity")
    require(isinstance(plan["resources"], list) and 1 <= len(plan["resources"]) <= 76, "invalid plan resource count")
    outputs, states = {}, set()
    for row in plan["resources"]:
        keys(row, ("outer", "id", "size", "before_sha256", "after_sha256", "changes"), ("outer", "id", "size", "before_sha256", "after_sha256", "changes"))
        index = integer(row["outer"], 0, 187, "outer")
        require(index == 22 or str(index) in catalog.manifest["rosters"], "unowned plan resource")
        require(index not in outputs, "duplicate plan resource")
        current = catalog.resource(index)
        require(row["size"] == len(current) and row["id"] == catalog.resources[index][0], "plan resource identity mismatch")
        digest = sha(current)
        require(digest in (row["before_sha256"], row["after_sha256"]), f"outer {index}: stale or foreign bytes")
        state = "before" if digest == row["before_sha256"] else "after"
        if row["before_sha256"] != row["after_sha256"]:
            states.add(state)
        before, after = bytearray(current), bytearray(current)
        require(isinstance(row["changes"], list) and len(row["changes"]) <= len(current), "invalid changes")
        end = 0
        for change in row["changes"]:
            keys(change, ("offset", "before", "after"), ("offset", "before", "after"))
            at = integer(change["offset"], end, len(current) - 1, "change offset")
            try:
                old, new = bytes.fromhex(change["before"]), bytes.fromhex(change["after"])
            except (TypeError, ValueError) as exc:
                raise Espn25Error("invalid change bytes") from exc
            require(0 < len(old) == len(new) <= len(current) - at, "invalid changed span")
            require(current[at:at + len(old)] == (old if state == "before" else new), "changed span differs")
            before[at:at + len(old)], after[at:at + len(new)] = old, new
            end = at + len(old)
        before, after = bytes(before), bytes(after)
        require(sha(before) == row["before_sha256"] and sha(after) == row["after_sha256"], "plan digest does not match changed spans")
        if index != 22:
            catalog.validate_roster(index, before)
            document = catalog.validate_roster(index, after)
            for player in document.players:
                require(player.record.values["jersey"] <= 99, "jersey exceeds 99")
                require(all(value <= 100 for value in player.record.ratings().values()), "rating exceeds 100")
        outputs[index] = after
    require(22 in outputs, "plan must pin scenario bindings")
    require(len(states) <= 1, "mixed before/after resources; no writes performed")
    Catalog({**catalog.resources, **{i: (catalog.resources[i][0], b) for i, b in outputs.items()}}, catalog.manifest)
    return outputs, not states or states == {"after"}


def status(source, plan):
    _, applied = resolve_plan(Catalog.load(source), plan)
    return "applied" if applied else "ready"


@contextmanager
def _writable_image(path):
    archive = rr._outer_image()(path, writable=True)
    try:
        with archive:
            yield archive
    finally:
        # OuterImage.close fsyncs before closing. An fsync failure must still
        # release the descriptor so Windows can delete the disposable copy.
        if archive._fd is not None:
            descriptor, archive._fd = archive._fd, None
            os.close(descriptor)


def apply_to_image(image, plan):
    """Final build pass on a caller-owned disposable image, never the retail source.

    Preflight refuses all mixed/foreign states before mutation. I/O failure may
    leave this disposable copy partial; build_image provides atomic publication.
    """
    catalog = Catalog.load(image)
    outputs, applied = resolve_plan(catalog, plan)
    receipt = {"label": LABEL, "already_applied": applied, "resources": plan["resources"], "xbe_changed": False}
    if applied:
        return receipt
    with _writable_image(image) as archive:
        for index in (5, *outputs):
            entry = archive.entries[index]
            require(entry.name_id == catalog.resources[index][0] and entry.size == len(catalog.resource(index)) and
                    archive.read(entry.virtual_offset, entry.size) == catalog.resource(index), "source changed after preflight")
        for index, after in outputs.items():
            entry = archive.entries[index]
            if after != catalog.resource(index):
                require(archive.write(entry.virtual_offset, after) == len(after), "short resource write")
                require(archive.read(entry.virtual_offset, len(after)) == after, "resource readback differs")
    return receipt


def build_image(source, output, plan):
    source, output = Path(source).resolve(), Path(output).resolve()
    require(source.is_file() and source != output and not output.exists(), "output must be a new file distinct from the source image")
    resolve_plan(Catalog.load(source), plan)
    require(shutil.disk_usage(output.parent).free - source.stat().st_size > 100 * 1024**3,
            "copy would leave less than 100 GB free")
    with tempfile.TemporaryDirectory(prefix="espn25-build-", dir=output.parent) as temporary:
        staged = Path(temporary).resolve() / "image.iso"
        with source.open("rb") as src, staged.open("xb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
        receipt = apply_to_image(staged, plan)
        require(status(staged, plan) == "applied", "final replay verification failed")
        require(not output.exists(), "output appeared during build")
        os.replace(staged, output)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("source")
    export = sub.add_parser("export-csv")
    export.add_argument("source"); export.add_argument("moment", type=int)
    export.add_argument("side", choices=("away", "home")); export.add_argument("output")
    prepare = sub.add_parser("plan")
    prepare.add_argument("source"); prepare.add_argument("edits"); prepare.add_argument("output")
    check = sub.add_parser("status")
    check.add_argument("source"); check.add_argument("plan")
    build = sub.add_parser("build")
    build.add_argument("source"); build.add_argument("plan"); build.add_argument("output")
    research = sub.add_parser("research-check")
    research.add_argument("source"); research.add_argument("draft")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = build_image(args.source, args.output, read_json(args.plan))
        elif args.command == "status":
            result = {"status": status(args.source, read_json(args.plan)), "label": LABEL}
        else:
            catalog = Catalog.load(args.source)
            if args.command == "inspect":
                result = {"label": LABEL, "moments": [{**catalog.moment(i), "bindings": {s: catalog.binding(i, s) for s in ("away", "home")}} for i in range(25)], "csv_columns": CSV_COLUMNS}
            elif args.command == "export-csv":
                Path(args.output).write_text(catalog.export_csv(args.moment, args.side), encoding="utf-8")
                result = {"csv": args.output, "shared_uses": catalog.shared_uses(catalog.binding(args.moment, args.side)["outer"])}
            elif args.command == "plan":
                result = catalog.prepare(read_json(args.edits))
                write_json(args.output, result)
            else:
                table = catalog.research_table(read_json(args.draft))
                result = {"label": LABEL, "installable": False, "count": u32(table, 8), "bytes": len(table), "sha256": sha(table),
                          "blocked_by": ["full menu paging", "saved high completion bits", "reward witness"]}
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 0
    except (ValueError, OSError, csv.Error) as exc:
        parser.exit(2, f"ESPN Anniversary: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
