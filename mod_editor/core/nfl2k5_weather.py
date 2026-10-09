"""Bounded stadium climate authoring. EXPERIMENTAL, default Off, UNWITNESSED.

Edits the existing ROST data only. Seven slots, not twelve independent months;
snow is derived from temperature, not a second probability column. Source
artwork, roofs, stadium identities, code and saves are never modified here.
"""
from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path
import struct

from . import nfl2k5_roster_records as rr
from .nfl2k5_espn25_scenarios import read_json, write_json, _writable_image

LABEL = "EXPERIMENTAL / UNWITNESSED"
BUILD_CAPTION = "Use saved stadium climate edits (experimental)"
HELP_TEXT = (
    "Edits temperature, precipitation chance and wind in the stadium climate data. "
    "Rain or snow follows the game's temperature test; July and August share a slot. "
    "Edits the disc roster. Test with a new franchise; existing-save adoption is unproved. "
    "Indoor weather is suppressed by retail. Off in every preset. Gameplay and appearance are unwitnessed."
)
DEFAULT_ENABLED = False
REQUESTS = ()
SCHEMA = "nfl2k5.weather.edits.v1"
MAX_RESOURCE = 8 * 1024 * 1024
COUNT, STRIDE = 82, 128
MONTHS = (8, 9, 10, 11, 12, 1, 2)
MONTH_TO_SLOT = {7: 0, **{month: slot for slot, month in enumerate(MONTHS)}}
# This conversion is also used by the native wind display (see research receipt).
CM_PER_SECOND_PER_MPH = 44.704
FIELDS = {"temperature_f": (0x28, -60, 130),
          "precipitation_pct": (0x44, 0, 100),
          "wind_mph": (0x60, 0, 60)}
SHAPE_SHA256 = "ab4df547810a558fd3563b6bf4187b88a03b02111437b35a1f37e726a68cf85f"
# b76-u6: the same rows with the Chargers row (s24) and the first Super Bowl row (s40, Super Bowl LXI) roofed and on
# turf, as SoFi Stadium writes them (nfl2k5_sofi_venue); the Rams row (s23) is roofed and on turf in retail. Only those
# words differ from the retail shape.
SOFI_SHAPE_SHA256 = "a4cfb9327f9ad9a3ecccf22d24ea9841467f040778e5dfe89cad2292b7a9ae49"


# W1/W2 (beta 77): "make it rain less often". Retail rolls precipitation per game from the stadium row's percent
# (precipitation iff 100 U <= percent) and decides rain or snow afterwards from the generated temperature (rain iff above
# 35 F), so rain and snow share one roll. The retail percents put visible rain in about 24 percent of 2026 outdoor
# games. The only real-world rate sourced here is PFF "The Factors" (2017): of 1,400 outdoor games from 2009 to 2017,
# 229 (16.4 percent) had any rain at game time, 22 of them moderate (1.6 percent). Rain-dominant cells are cut by
# RAIN_CUT x r^2, where r is the share of that cell's precipitation that falls as rain (baseline temperature plus the
# retail time-of-day offsets at 0x4F6564, weighted by the 2026 schedule's day/afternoon/night mix). Pure rain cells lose
# 60 percent, mixed cells less, snow cells nothing, domes nothing.
RAIN_CUT = 0.6
RAIN_LINE_F = 35.0
TOD_OFFSETS_F = ((-5.0, 15.0), (-10.0, 10.0), (-20.0, 0.0))  # day, afternoon, night: baseline + [low, high)
TOD_WEIGHTS = (0.55, 0.225, 0.225)  # 150 day, 61 afternoon, 61 night of the 272 games in data/nfl_2026_schedule.json


class WeatherError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise WeatherError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def integer(value, low, high, label):
    require(type(value) is int and low <= value <= high, f"{label}: expected {low}..{high}")
    return value


def relative(data, at):
    require(0 <= at <= len(data)-4, "Truncated climate pointer")
    value = struct.unpack_from("<i", data, at)[0]
    require(value != 0, "Missing climate pointer")
    return at + value - 1


def text_at(data, at):
    require(at % 2 == 0 and 0 <= at < len(data), "Climate text pointer is outside the roster")
    for end in range(at, min(len(data)-1, at+512), 2):
        if data[end:end+2] == b"\0\0":
            try:
                return data[at:end].decode("utf-16le")
            except UnicodeError as exc:
                raise WeatherError("Invalid climate text; select a supported USA roster") from exc
    raise WeatherError("Unterminated climate text; select a supported USA roster")


def scalar_bytes(field, value):
    require(field in FIELDS, "Unknown climate field")
    _, low, high = FIELDS[field]
    require(type(value) in (int, float) and low <= value <= high and math.isfinite(value),
            f"{field}: enter a finite value from {low} to {high}")
    if field == "wind_mph":
        value *= CM_PER_SECOND_PER_MPH
    return struct.pack("<f", value)


def rain_share(baseline_f):
    """Share of this cell's precipitation that falls as rain (0 snow, 1 rain), averaged over time of day."""
    total = 0.0
    for (low, high), weight in zip(TOD_OFFSETS_F, TOD_WEIGHTS):
        need = (RAIN_LINE_F - baseline_f - low) / (high - low)  # rain iff the uniform draw exceeds this
        total += weight * min(1.0, max(0.0, 1.0 - need))
    return total


def less_rain_percent(percent, baseline_f):
    """The precipitation percent after the rain cut; snow-dominant cells return unchanged."""
    if percent <= 0:
        return percent
    share = rain_share(baseline_f)
    return round(percent * (1.0 - RAIN_CUT * share * share), 1)


def inspect_resource(data, *, strict=True):
    """Resolve the live ROST pool; tolerate relocations, never guess fixed offsets.

    strict=False skips only the retail stadium-shape pin, for a repair that must read a SOFTDRINK ROST whose stadium
    rows were renamed (the repair pins its own owned floats instead)."""
    require(isinstance(data, bytes) and 0x40 <= len(data) <= MAX_RESOURCE, "Expected a bounded ROST resource")
    require(data[:4] == data[0x2C:0x30] == b"ROST", "Not a main ROST resource")
    require(struct.unpack_from("<II", data, 4) == (len(data)-32, len(data)-32) and
            data[12:32] == bytes(20) and struct.unpack_from("<I", data, 0x30)[0] == 17,
            "Unsupported ROST wrapper or version")
    root = relative(data, 0x34)
    require(0x40 <= root <= len(data)-0x70, "ROST pool is outside the resource")
    count = struct.unpack_from("<I", data, root+0x10)[0]
    at = relative(data, root+0x14)
    require(count == COUNT and root+0x70 <= at <= len(data)-COUNT*STRIDE,
            "Unsupported stadium table; expected 82 complete USA stadium rows")
    geometry = b"".join(data[o+24:o+40]+data[o+124:o+128]
                        for o in range(at, at+COUNT*STRIDE, STRIDE))
    require(not strict or sha(geometry) in (SHAPE_SHA256, SOFI_SHAPE_SHA256),
            "Stadium roof, identity or record layout changed; reopen the supported source")
    rows = []
    for index in range(count):
        pos = at + index*STRIDE
        names = {name: text_at(data, relative(data, pos+offset))
                 for name, offset in (("stadium", 0), ("city", 8), ("asset_code", 12))}
        require(names["asset_code"].startswith("s") and names["asset_code"][1:].isdigit(),
                "Unknown stadium asset code")
        slots = []
        for slot, month in enumerate(MONTHS):
            values = {}
            for field, (offset, _, _) in FIELDS.items():
                value = struct.unpack_from("<f", data, pos+offset+4*slot)[0]
                if field == "wind_mph":
                    value /= CM_PER_SECOND_PER_MPH
                scalar_bytes(field, value)  # finite/domain check before presentation or writes
                values[field] = value
            slots.append(dict(month=month, **values))
        rows.append(dict(index=index, offset=pos, asset_id=data[pos+0x7C],
                         indoor=bool(struct.unpack_from("<I", data, pos+0x18)[0]),
                         months=slots, **names))
    return dict(label=LABEL, root=root, table_offset=at, rows=rows,
                resource_sha256=sha(data), runtime_witnessed=False)


def _changes(data, plan):
    require(isinstance(plan, dict) and set(plan) == {"schema", "changes"} and plan["schema"] == SCHEMA,
            "Unsupported climate plan; save edits again")
    changes = plan["changes"]
    require(isinstance(changes, list) and len(changes) <= COUNT*7*3, "Too many climate changes")
    catalog = inspect_resource(data)
    used, result, states = set(), [], set()
    for change in changes:
        require(isinstance(change, dict) and set(change) ==
                {"stadium_index", "asset_code", "month", "field", "before", "after"},
                "Invalid climate change fields")
        index = integer(change["stadium_index"], 0, COUNT-1, "Stadium")
        month = integer(change["month"], 1, 12, "Month")
        require(month in MONTH_TO_SLOT, "March through June have no supported climate slot")
        row = catalog["rows"][index]
        require(change["asset_code"] == row["asset_code"], "Climate plan targets another stadium")
        field = change["field"]
        require(isinstance(field, str) and field in FIELDS, "Unknown climate field")
        slot = MONTH_TO_SLOT[month]
        at = row["offset"] + FIELDS[field][0] + 4*slot
        require(at not in used, "Duplicate climate field (July and August share one slot)")
        used.add(at)
        old, new = (scalar_bytes(field, change[key]) for key in ("before", "after"))
        require(old != new, "Unchanged climate entry; remove it from the saved plan")
        current = data[at:at+4]
        require(current in (old, new), f"{row['stadium']}, month {month}, {field}: source changed; reopen and save edits again")
        states.add("ready" if current == old else "applied")
        result.append((at, old, new))
    require(len(states) <= 1, "Partly applied climate plan; rebuild from the original source")
    return result, next(iter(states), "applied")


def status(data, plan):
    try:
        return _changes(data, plan)[1]
    except (ValueError, TypeError, KeyError, struct.error):
        return "foreign"


def verify(data, plan, *, before=None):
    """Reparse written floats and identities, and check the complete diff if supplied."""
    changes, state = _changes(data, plan)
    require(state == "applied", "Climate values do not match the saved edits")
    if before is not None:
        original, _ = _changes(before, plan)
        require(len(before) == len(data) and [a for a, _, _ in original] == [a for a, _, _ in changes],
                "Climate resource or table moved while writing")
        restored = bytearray(data)
        for at, _, _ in original:
            restored[at:at+4] = before[at:at+4]
        require(bytes(restored) == before, "Bytes outside the requested climate fields changed")
    return dict(label=LABEL, state=state, fields=len(changes), resource_sha256=sha(data),
                runtime_witnessed=False, xbe_changed=False)


def apply(data, plan):
    changes, state = _changes(data, plan)
    output = bytearray(data)
    for at, _, new in changes:
        output[at:at+4] = new
    output = bytes(output)
    return output, dict(verify(output, plan, before=data), already_applied=state == "applied")


class WeatherDraft:
    """UI-independent editing session with per-action Undo, no source writes."""
    def __init__(self, resource):
        self.resource = resource
        self.catalog = inspect_resource(resource)
        self._values, self._undo = {}, []

    def set_value(self, stadium_index, month, field, value):
        index = integer(stadium_index, 0, COUNT-1, "Stadium")
        integer(month, 1, 12, "Month")
        require(month in MONTH_TO_SLOT, "March through June have no supported climate slot")
        require(isinstance(field, str) and field in FIELDS, "Unknown climate field")
        scalar_bytes(field, value)
        key = (index, MONTHS[MONTH_TO_SLOT[month]], field)
        previous = self._values.copy()
        row = self.catalog["rows"][index]
        old = row["months"][MONTH_TO_SLOT[month]][field]
        if scalar_bytes(field, value) == scalar_bytes(field, old):
            self._values.pop(key, None)
        else:
            self._values[key] = value
        if self._values != previous:
            self._undo.append(previous)

    def milder_outdoor_preset(self):
        """Authored +2 F sensitivity preset, NOT measured modern climatology.

        Sets the 32 retail NFL home rows from the source baseline. Repeating it
        does not accumulate warming. Other fields/rows retain their draft values.
        """
        previous, depth = self._values.copy(), len(self._undo)
        try:
            for row in self.catalog["rows"][:32]:
                if not row["indoor"]:
                    for values in row["months"]:
                        self.set_value(row["index"], values["month"], "temperature_f",
                                       min(130, values["temperature_f"]+2))
        except BaseException:
            self._values = previous
            del self._undo[depth:]
            raise
        del self._undo[depth:]
        if self._values != previous:
            self._undo.append(previous)

    def less_rain_preset(self):
        """Cut rain frequency toward the sourced real-world rate (see RAIN_CUT). Idempotent against the loaded source:
        values are always computed from the source percent, never from an earlier draft value; roofed rows are skipped."""
        previous, depth = self._values.copy(), len(self._undo)
        try:
            for row in self.catalog["rows"]:
                if row["indoor"]:
                    continue
                for values in row["months"]:
                    self.set_value(row["index"], values["month"], "precipitation_pct",
                                   min(100, less_rain_percent(values["precipitation_pct"], values["temperature_f"])))
        except BaseException:
            self._values = previous
            del self._undo[depth:]
            raise
        del self._undo[depth:]
        if self._values != previous:
            self._undo.append(previous)

    def undo(self):
        if not self._undo:
            return False
        self._values = self._undo.pop()
        return True

    def plan(self):
        changes = []
        for (index, month, field), value in sorted(self._values.items()):
            row = self.catalog["rows"][index]
            changes.append(dict(stadium_index=index, asset_code=row["asset_code"], month=month,
                                field=field, before=row["months"][MONTH_TO_SLOT[month]][field], after=value))
        return copy.deepcopy(dict(schema=SCHEMA, changes=changes))


def load_resource(source):
    source = Path(source)
    if source.name == "0":
        source = source.parent
    with rr._outer_image()(source) as archive:
        require(len(archive.entries) > 5, "Main roster is missing from this disc")
        entry = archive.entries[5]
        require(0x40 <= entry.size <= MAX_RESOURCE, "Main roster exceeds the supported size")
        result = archive.read(entry.virtual_offset, entry.size)
    inspect_resource(result)
    return result


def apply_to_image(target, plan):
    """Build-only: target must be the caller's disposable output, before publication."""
    original = load_resource(target)
    result, receipt = apply(original, plan)
    with _writable_image(target) as archive:
        entry = archive.entries[5]
        require(entry.size == len(original) and archive.read(entry.virtual_offset, entry.size) == original,
                "Roster changed after climate preflight")
        if result != original:
            require(archive.write(entry.virtual_offset, result) == len(result), "Short climate write")
        verify(archive.read(entry.virtual_offset, entry.size), plan, before=original)
    return receipt


def less_rain_plan(resource):
    """A saved-plan document (nfl2k5.weather.edits.v1) that applies the rain cut to every outdoor row of this ROST."""
    draft = WeatherDraft(resource)
    draft.less_rain_preset()
    return draft.plan()


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Author the less-frequent-rain climate plan (copy-only, no source writes).")
    parser.add_argument("source", type=Path, help="supported USA disc image or extracted game folder")
    parser.add_argument("plan", type=Path, help="new .json plan to write")
    args = parser.parse_args(argv)
    require(args.plan.suffix.lower() == ".json" and not args.plan.exists(), "Choose a new .json file for the plan")
    plan = less_rain_plan(load_resource(args.source))
    require(bool(plan["changes"]), "Nothing to change")
    write_json(args.plan, plan)
    print(f"{len(plan['changes'])} precipitation edits written to {args.plan}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
