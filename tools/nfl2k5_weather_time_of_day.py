#!/usr/bin/env python3
"""Read-only weather audit, climate plan authoring and copy-only resource CLI."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_weather as weather
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256

PINS = (
    (0x133FC0, 124, "schedule climate initializer"),
    (0x15DB50, 146, "franchise game setup caller"),
    (0xEC870, 382, "climate generator"),
    (0x4F6530, 52, "month lookup"),
    (0x4F6564, 24, "time temperature ranges"),
    (0xE3150, 312, "Play Now weather generator"),
    (0x4F2524, 24, "weather label pointers"),
    (0x77BB0, 95, "snow and rain classifiers"),
    (0xE3130, 31, "night and afternoon predicates"),
    (0x62BE0, 276, "stadium suffixes and indoor reset"),
    (0x2C1140, 211, "mode and network weather row suppression"),
    (0x85EF0, 160, "haze reader"),
    (0x86190, 35, "haze camera dispatch"),
    (0x2B9E0, 44, "camera haze fields"),
    (0xA867F0, 60, "three haze parameter rows"),
    (0x17A84B, 73, "conditional precipitation penalty candidate"),
    (0x1C75B7, 69, "wet ball contact interpolation"),
    (0x1DA057, 27, "wet handling candidate"),
    (0x1CB7C5, 90, "wind vector candidate"),
    (0x1CBA1E, 95, "second wind vector candidate"),
    (0xAA4020, 896, "28 effective-rating descriptors; precipitation flag bit 0"),
    (0x25E3D4, 137, "wind display divides native speed by 44.704"),
    (0x4F267C, 4, "wind units per mph"),
    (0xE8B490, 60, "wind display format with mph unit"),
    (0x14C110, 82, "weather menu previous/next callbacks"),
    (0x2C2CA0, 82, "second weather menu previous/next callbacks"),
    (0x340410, 82, "third weather menu previous/next callbacks"),
    (0xF2F90, 112, "menu row disable and event dispatch"),
    (0x2C1200, 32, "mode filter jump table"),
    (0x502A38, 32, "quick-game weather menu descriptor"),
    (0x526BAC, 32, "weather menu descriptor"),
    (0x526EC4, 32, "alternate weather menu descriptor"),
    (0x54FCC8, 32, "additional weather menu descriptor"),
    (0x20CBD0, 160, "ESPN scenario environment loads"),
    (0x17A6D0, 452, "effective-attribute loop through precipitation block"),
    (0x1DB968, 124, "weather-dependent rating table blend"),
    (0xE610A0, 46, "stadium and created-field filename formats"),
    (0x1C7659, 123, "contact value through hold-onto-ball and Fumble slider tables to random test"),
    (0x1C5550, 34, "native probability random comparison"),
)


def read_xbe(path):
    path = Path(path)
    weather.require(path.stat().st_size == 11948032, "Native audit requires the retail USA default.xbe")
    payload = path.read_bytes()
    weather.require(weather.sha(payload) == RETAIL_SHA256, "Native audit retail XBE hash changed")
    return payload


def archive_inventory(source):
    """Read every TXTR wrapper in all 477 decoded sNN{d,a,n}{d,r,s} bundles.

    Only hashes/metadata leave this function. Bounded full TXTR decompression
    verifies the sky texture name; no pixels are exported or rendered.
    """
    from nfl_txtr import HEADER, parse_chunks, decode_chunk
    entries, skies = [], []
    with weather.rr._outer_image()(source) as archive:
        lookup = {entry.name_id: entry for entry in archive.entries}
        for code in range(100):
            for tod in "dan":
                for kind in "drs":
                    name = f"s{code:02}{tod}{kind}.iff"
                    identity = zlib.crc32(name.upper().encode("utf-16le"))
                    if identity not in lookup:
                        continue
                    entry = lookup[identity]
                    entries.append(dict(name=name, outer=entry.index if hasattr(entry, "index") else archive.entries.index(entry),
                                        id=f"{identity:08x}", virtual_offset=entry.virtual_offset, size=entry.size))
                    offset, ordinal = 0, 0
                    while offset < entry.size:
                        weather.require(ordinal < 128 and offset+32 <= entry.size, "Unsupported stadium chunk layout")
                        header = archive.read(entry.virtual_offset+offset, 32)
                        tag, size, *_ = HEADER.unpack(header)
                        weather.require(0 < size <= entry.size-offset-32, "Invalid stadium wrapper size")
                        if tag == b"TXTR":
                            weather.require(size <= 1024*1024, "Texture exceeds bounded inventory size")
                            span = header+archive.read(entry.virtual_offset+offset+32, size)
                            decoded, _ = decode_chunk(span, parse_chunks(span)[0])
                            label = weather.text_at(decoded, 32)
                            if any(word in label.lower() for word in ("sky", "cloud", "fog", "dusk", "overcast")):
                                skies.append(dict(bundle=name, outer=entries[-1]["outer"], chunk=ordinal,
                                                  offset=offset, name=label, span_sha256=weather.sha(span),
                                                  decoded_sha256=weather.sha(decoded)))
                        offset += 32+size
                        ordinal += 1
    return dict(stadium_bundle_count=len(entries), bundles=entries, sky_textures=skies,
                sky_names=dict(Counter(s["name"] for s in skies)),
                unique_decoded_sky_textures=len({s["decoded_sha256"] for s in skies}),
                scope="s00..s99 x day/afternoon/night x dry/rain/snow. Not an exhaustive arbitrary-filename oracle.")


def audit(source, xbe_path, *, assets=False):
    payload = read_xbe(xbe_path)
    image = XbeImage(payload)
    resource = weather.load_resource(source)
    catalog = weather.inspect_resource(resource)
    pins = [dict(va=f"0x{va:08x}", file_offset=image.offset(va, size), size=size,
                 sha256=weather.sha(image.read(va, size)), purpose=purpose)
            for va, size, purpose in PINS]
    result = dict(schema="nfl2k5.weather.audit.v1", label=weather.LABEL,
                  xbe_sha256=weather.sha(payload), native_spans=pins,
                  climate=catalog, month_slots=list(struct.unpack("<13i", image.read(0x4F6530, 52))),
                  temperature_ranges=list(struct.unpack("<6f", image.read(0x4F6564, 24))),
                  runtime_witnessed=False)
    import re
    result["rating_weather_flags"] = []
    for index in range(28):
        _, _, reader, _, flags, *_ = struct.unpack("<8I", image.read(0xAA4020+32*index, 32))
        code = image.read(reader, 110)
        match = re.search(b"\x8a\x46(.)", code, re.S)
        weather.require(match is not None, "Rating reader no longer has its pinned byte load")
        offset = match[1][0]
        result["rating_weather_flags"].append(dict(index=index, reader=hex(reader),
            reader_sha256=weather.sha(code), raw_offset=hex(offset),
            rating=weather.rr.RATING_BYTE_ORDER[offset-0x36], flags=hex(flags),
            precipitation_penalty=bool(flags & 1)))
    # Team pointers belong to the roster, not a hard-coded city-to-club mapping.
    root = catalog["root"]
    count = struct.unpack_from("<I", resource, root+0x18)[0]
    at = weather.relative(resource, root+0x1C)
    weather.require(32 <= count <= 256 and at+count*weather.rr.TEAM_SIZE <= len(resource), "Unsupported team table")
    # Resolve only the 32 NFL team records. Stadium association uses +114.
    by_offset = {row["offset"]: row["index"] for row in catalog["rows"]}
    result["nfl_team_stadium_rows"] = []
    for index in range(32):
        field = at+index*weather.rr.TEAM_SIZE+0x114
        target = weather.relative(resource, field)
        weather.require(target in by_offset, "Team stadium pointer is not a climate row")
        result["nfl_team_stadium_rows"].append(by_offset[target])
    if assets:
        result["assets"] = archive_inventory(source)
    return result


def native_receipt(source, xbe_path):
    from nfl2k5_weather_native_probe import Machine
    from mod_editor.core import nfl2k5_weather_haze as haze
    payload = read_xbe(xbe_path)
    resource = weather.load_resource(source)
    row = weather.inspect_resource(resource)["rows"][5]
    machine = Machine(payload, resource[row["offset"]:row["offset"]+128])
    schedule = []
    for hour in (0, 1, 4, 6, 8, 9, 10, 11, 12):
        machine.seed(7)
        values = machine.schedule(12, hour, week=3, game=4)
        suffix = machine.suffixes()
        schedule.append(dict(hour=hour, tod=values[0], temperature=values[1], precipitation=values[2], suffixes=suffix))
    cases = []
    for month in weather.MONTHS:
        for tod in range(3):
            machine.seed(17)
            cases.append(dict(month=month, tod=tod, outputs=machine.climate(month, tod)))
    draft = weather.WeatherDraft(resource)
    draft.set_value(5, 12, "temperature_f", 15)
    draft.set_value(5, 12, "precipitation_pct", 100)
    draft.set_value(5, 12, "wind_mph", 12)
    changed, receipt = weather.apply(resource, draft.plan())
    edited = Machine(payload, changed[row["offset"]:row["offset"]+128])
    edited.seed(7)
    selected = edited.schedule(12, 8)
    suffixes = edited.suffixes()
    patched, haze_receipt = haze.apply(payload)
    altered = Machine(patched, resource[row["offset"]:row["offset"]+128])
    haze_cases = []
    for temperature, precip, amount, indoor in ((70, 0, .25, False), (70, 0, 0, False),
                                               (70, .8, .25, False), (20, .8, .25, False),
                                               (70, 0, .25, True)):
        values = []
        for m in (machine, altered):
            m.conditions(temperature=temperature, precipitation=precip, haze=amount, indoor=indoor)
            m.haze()
            values.append(m.camera_haze())
        haze_cases.append(dict(temperature=temperature, precipitation=precip, haze=amount,
                               indoor=indoor, retail_camera=values[0], patched_camera=values[1]))
    penalty_cases = []
    for temperature, precipitation, flags in ((70, 0, 1), (70, .5, 1), (20, .5, 1), (20, .5, 0)):
        machine.conditions(temperature=temperature, precipitation=precipitation)
        machine.f32(machine.STACK+0x10, .8)
        machine.run(0x17A84B, ebx=flags, stop=0x17A894)
        penalty_cases.append(dict(temperature=temperature, precipitation=precipitation,
                                  descriptor_flags=flags, base=.8,
                                  result=machine.readf(machine.STACK+0x10)))
    contact_cases = []
    for temperature, precipitation in ((70, 0), (70, .5), (20, .5)):
        machine.conditions(temperature=temperature, precipitation=precipitation)
        machine.f32(machine.STACK+0x18, .05)
        machine.run(0x1C75B7, stop=0x1C7659)
        contact_cases.append(dict(temperature=temperature, precipitation=precipitation,
                                  base=.05, intermediate=machine.readf(machine.STACK+0x18)))
    return dict(schema="nfl2k5.weather.native.v1", label=weather.LABEL, runtime_witnessed=False, schedule=schedule,
                climate_samples=cases, edited_climate=dict(values=selected, suffixes=suffixes, verifier=receipt),
                haze_cases=haze_cases, haze_verifier=haze_receipt, rating_penalty_cases=penalty_cases,
                contact_weather_cases=contact_cases,
                limits="Retail RNG with synthetic seeds and stadium rows; native selector and camera field copies. "
                       "No frontend/controller lifecycle, save reload, GPU submission, rendering or gameplay witness.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "preset", "audit", "native"):
        sub = commands.add_parser(name)
        sub.add_argument("source", type=Path)
        sub.add_argument("output", type=Path)
        if name in ("audit", "native"):
            sub.add_argument("--xbe", required=True, type=Path)
        if name == "audit":
            sub.add_argument("--assets", action="store_true")
    sub = commands.add_parser("apply-resource", help="Apply a saved plan to a new ROST resource file")
    sub.add_argument("source", type=Path)
    sub.add_argument("plan", type=Path)
    sub.add_argument("output", type=Path)
    sub = commands.add_parser("haze", help="Write the optional haze coefficient to a new XBE file")
    sub.add_argument("source", type=Path)
    sub.add_argument("output", type=Path)
    sub.add_argument("--off", action="store_true", help="Restore the recognized retail coefficient")
    args = parser.parse_args(argv)
    if args.command == "haze":
        from mod_editor.core import nfl2k5_weather_haze as haze
        weather.require(args.source.stat().st_size <= 32*1024*1024, "Select a bounded default.xbe")
        after, receipt = haze.apply(args.source.read_bytes(), enabled=not args.off)
        with args.output.open("xb") as stream:
            stream.write(after)
        haze.verify(args.output.read_bytes(), enabled=not args.off)
        print(json.dumps(receipt, indent=2))
        return 0
    if args.command == "apply-resource":
        weather.require(args.source.stat().st_size <= weather.MAX_RESOURCE, "Select an exported ROST resource")
        before = args.source.read_bytes()
        plan = weather.read_json(args.plan)
        after, receipt = weather.apply(before, plan)
        with args.output.open("xb") as stream:
            stream.write(after)
        weather.verify(args.output.read_bytes(), plan, before=before)
        print(json.dumps(receipt, indent=2))
        return 0
    if args.command == "audit":
        result = audit(args.source, args.xbe, assets=args.assets)
    elif args.command == "native":
        result = native_receipt(args.source, args.xbe)
    else:
        resource = weather.load_resource(args.source)
        if args.command == "preset":
            draft = weather.WeatherDraft(resource)
            draft.milder_outdoor_preset()
            result = draft.plan()
        else:
            result = weather.inspect_resource(resource)
    # A report destination must not overwrite the input or any existing file.
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
