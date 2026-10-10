"""Historic moments: real rosters. EXPERIMENTAL / UNWITNESSED.

Names and numbers on the 35 shared historic ROSTs used by the retail 25 moments.
Box-score starters and season numbers are sourced; shared-file gaps are listed.
The paired executable fix clears released historic-team pointers on re-entry.
No scenario, saved team pointer or rating edit is made here. Sparse hand cells change only the hand bit.
The image adapter edits only a caller-owned disposable build copy. ``build_image``
provides copy-first publication. No whole image or archive pack is read into RAM.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
from typing import Mapping
import zlib

from . import nfl2k5_roster_records as rr

OWNER = "nfl2k5_espn25_rosters"
SCHEMA = OWNER + "/v1"
REQUESTS = ()
EVIDENCE = "EXPERIMENTAL / UNWITNESSED"
CAPTION = "Historic moments: real rosters"
HELP_TEXT = (
    "Retail: many historic players have position names in shared rosters. "
    "Patch: use Pro Football Reference game starters and season jersey numbers "
    "with the nflverse roster base. Short lists still need named reserves from "
    "nearby seasons. Shared teams cannot match every game. Works with the retail positions or One-pool positions. "
    "The historic-team release repair that ended the Wide Right freeze is installed with it. "
    "EXPERIMENTAL / UNWITNESSED: lab runs only; Noah has not played it."
)
DEFAULT_ENABLED = False
# e1 (2026-09-23): the Wide Right freeze was the practice squad's import guard meeting the retail release's stale
# player pointers (root-caused in a lab run; see RESEARCH_E1_ESPN25_2026-09-23). The 12-byte repair below now ships
# with every practice squad build, and apply_to_image installs it too, so the build hold is lifted. The constant stays
# for callers that read it; an empty reason means "buildable".
BUILD_BLOCK_REASON = ""
DATA_DIR = Path(__file__).resolve().parents[2] / "data/nfl2k5_espn25_moment_rosters"
# Updated deliberately after deterministic offline regeneration; no runtime fetch.
DATASET_SHA256 = "9bccb798f5bf28d5800dcc6f1b84f328cc902297c2a827157a0694ffcff493f7"
MAX_RESOURCE = 1024 * 1024
MAX_MANIFEST = 8 * 1024 * 1024
SITU_OUTER = 22
MAIN_OUTER = 5
RECORDS, STRIDE, COUNT = 0x44, 0x6C, 25
CSV_COLUMNS = ("pool", "index", "first", "last", "position", "jersey", "college") + rr.RATING_BYTE_ORDER
# C2300 is the historic loader's team eviction routine, not a cave. BFF90
# releases the player but preserves EAX=0. Retail left the pointer behind;
# ps_import's reserve_count consequently rejects that supposedly empty team.
# Replace exactly four complete instructions inside the existing release loop:
# mov [esi+edx*4],eax; inc edx; cmp dl,[esi+11c]; jb C2311.
# The byte counter is bounded by the team's byte count (legal maximum 65).
XBE_SITE_VA = 0xC2319
XBE_BEFORE = bytes.fromhex("0fb68e1c010000423bd17cec")
XBE_AFTER = bytes.fromhex("890496423a961c01000072ec")
XBE_GUARDS = (
    (0xC2300, 0x110, "21d5e9825aff0adac9a476bbd117ada85b1fd261fd19aadab1120a2966c9b8e5"),
    (0xBFF90, 9, "4d11d20c170d21fcc60b8741c49c608e695b0885523d348d33aaad174fff714b"),
)

# One-pool positions (Build option position_pools) reclassify all 75 historic ROSTs with the historic 4-3 rule
# before this data pass: tools/nfl2k5_roster_reclassify.py writes the position byte (+0x35, OLB -> ILB) and the
# rank/side word (+0x28) of the front pools. This writer changes names, jerseys and college indices only. The two
# commute byte for byte (e1, 2026-09-23), so the same dataset applies on the reclassified layout. Per resource:
# (reclassify(retail) sha256, reclassify(applied) sha256). tests/mod_editor/test_nfl2k5_espn25_one_pool.py recomputes
# them from the retail resources with the reclassify tool itself.
ONE_POOL_PINS = {
    113: ("a290d74c90a2135bafb8b497e65d9ab29c4e0750edf781cb1077939a03514ce2",
          "88c54b55fff39a83c429271bf2b56d6fe86ef9649a1b62c15ec041bf92f45a50"),
    118: ("740394b3c1ec5087cb24a61935cdaf0386f3a8e9e4a98b7082437a9cfd776ee6",
          "4ac1a5e58c4a09ec6296f560db5905ae85aa4dc7ffe7bebd74d2738d4f9abca9"),
    124: ("0dc8e1e7a8469c4dba62e581473d4635113ea8ec092514b8affcfd6e764c2d12",
          "27d34fdb292a80e5ea0605e60867eff31065a7b0f95158f7e1b154d65d72179b"),
    125: ("13bb4299909bd3ce844615799fe181c4c11c2517780f32e1e357705f7b907352",
          "8c59a4786ce53fd9ce6645ede24280cc33b630d4725c145cb0d73615f75997f1"),
    126: ("d023f2a4ec9220a0edc77e036a5147982544a08cca9786f3308ca27e4b0ee06a",
          "1984e17d584f14e52bb672c9b139c2590a0c1abaa4269c127ef120de5008b83b"),
    129: ("e07fd1bfa463a59374d9d9aff531909cb09a247497852b0ce95dd59c65f6a97a",
          "fc88cba9653ec85a24be6897abcb0d6ced3d6e38928c76c21dbd7c02a6f534a7"),
    130: ("e7e36fe2e536b27f5f75e915f3bbaa11ce8f17d9e8ef61362057f9a5a6a54fa7",
          "ed333718aec7212551e53728ee26d4350a2c177201e4187d65af701478b77279"),
    133: ("dd02b15ca2532b4eb4cdf62b26163274da96b0a33488ed2eaff0627b26002f24",
          "3c850864c4d91cac960c2463def31459d9fc925db92a6b7853025e298c7523ae"),
    134: ("962e11c4f0cc70cf14726f2e60307fbd54e3cca46f7da98a66b92fbe5181207e",
          "5e09ed46b7a6194159fc30bf95fa9637bd14d5123f137dd5cd2c420a6e50e6b6"),
    135: ("f4e9c30871ad6a45e69b156df96997d854970d065d52b89e4d8489139da8d348",
          "9140adaf99ed66fdedfc6345b2a24121d594b5504fa5fe82bd5c2676ac2b4524"),
    136: ("41d02289544dc100ed9e06ae508ddece7ee553bb554fd785993ca593d527ff45",
          "bdb9475c946240eabc2917603b0661ff805cfb1559036ce8ec6c0b9e0997ec73"),
    139: ("3969766a78e86b4b7f4b5b61fe643784ea3a05c43a9c7c403387d41900b2478f",
          "073082e7476122c26c403a22d30c7a12682fa1f8ad3aa6526fd818f9434e9ad6"),
    140: ("99a48364028e04824024fa4382337e1efcf333b9aca7d52932f6300adeb30c33",
          "f464aab72469da6787db58bdde89136a8ddb3bb8af7709ad7557c43ffc0347f7"),
    141: ("5a5e8aaa64ce34fb320b790de6451ccfa81719c7a4c9bd2be2eac94ebb78ec0d",
          "0d07214d112cd27f950135362aff8265db5d82b444ed51a0f79f6150028a7844"),
    142: ("34d4076ccdb849521ff71d7e8aec43a2f1d97760931496ac8381641e4b6966d3",
          "9025f62d672097147569c9e6888927749077c6fc007a81fd3007ffe91523c334"),
    147: ("8ce79ba8d36d3f523aa002d47b36c9b6f07a11610f9054783c8711103f73dd36",
          "8b520daa4153740e5df94fa39bcecbd2b3252d93648555bb74cb47c75252e27a"),
    149: ("cfd4f5e8cf9c22ff60af784dac03acd4d6ee29cf6506a49285a940c97c7034dc",
          "7122e796a1684cb5cf2bd0b5cabb064d12fd2bff0db044c1fc8faf3fdf3f718d"),
    153: ("ce05a6c70e7c690d1770905eaeeeeaa7056555971f83e72b83bb5f3435465341",
          "a4145da35c6a98c07b56f2d8d50617b2def0c7f9ab57acf435bdb78153185bbc"),
    154: ("8c90a93aac5a7e7116c61683cc21b6ba31ee198a00d6c27dd7adb538432f4ed5",
          "1c3053b61c31b4cb81188a6818d4fd0fadda22ab769f8fb2cc9b57f7a95446fe"),
    155: ("6e31f8822ba5f5db1fa8d74b6d0d845076b3742b953adc7cfa77932178890a4d",
          "2b66ea362e85bf921f804c56c4a7b882f644e4b9ed569fc96e714e1e05ad141c"),
    157: ("59e3475033ea5b9e2e2f47e2b98278eef74d9155b8863548de4a50f599b4132a",
          "2d17ebba0b55b93b21ef56407178cde867bf79040db7f8c5799db4fe4c633cbc"),
    158: ("2ba50f24610a52f91d44cb463588f2043d940b2ca5e277da4e37f78bf058b312",
          "23ba7b255f18597a777700ff67136c3425eb657660f44728fd3af72306e621a3"),
    159: ("d2d51050fee314a3463eaf7440baeeca572669aab90cb91a1e33db522876571f",
          "e8b62f20496dcf8533d472ead7fa288cafa0f25781abf25eed943b5110d005af"),
    162: ("8aa16fe442e7a016aa451414cd76889305255639af205f4efabd7a97e7e5eeba",
          "27be14bd8f104dd7886d8068524781ece85fdba552d8e275cc6bc76723026cc8"),
    163: ("ef8e80e295c9ef37887523661155b8c90aea0388737db03e1fb25a442b1420aa",
          "82b80f9e6503d0682b361552a4ff6ab22701f14b74c61e99bfc13094f2d04d73"),
    167: ("14e6aa67aed7c0d66b593ea8ad9196238536bace89642d68d65e217c37f378ad",
          "213849b33ef3f314b0fc369b7feadd5e53d19b2c34b3b3ef5282af2581b8aabe"),
    169: ("ef8399e2d93d51621f8786e240a1a57bec03d34d920e41dce7d9468315a84deb",
          "e53bd57ba4106d858f9ff2102f060d615f66f107dd4c44a0523c431795a714c8"),
    171: ("6e2e76c91883690386ad81270dbdea08817fc72b5a52d94c34783863e11680d0",
          "a87d227edfd70362ca26359b235c4e4a51351088f8219502d7c3b4bf266b470e"),
    172: ("eda6b07dae55bf6e6a00fa62cf121f874ab97fdbd8dab3b2866187de63b442ac",
          "4673f886efb98afe7845d864ebfb32965d76d21305153494437091013e879ebf"),
    174: ("81563cf7596735f989a2e08c9c12199e3f6c0006ee3a6c384f7e0cd4f63593d9",
          "40b6d8028c6e4812bf5bb2c93b5f48bfe5e5d5e44706db7e08c1eff33f0bebc7"),
    177: ("308e893277e48c6896eb163656e0eb3fb3cf5e5d8c53442c4750034ed540cda3",
          "2691c60447c5c78c751e1adf039bc718a035c9123116c674c666f08ba8c089dc"),
    181: ("71044ce334ab3c5ae949ef811d16e92d72ecd7e52fcd640303e10a292ed735f8",
          "2c228fe654f1307cb7e1ef1215082a51f2f2d66c290539763269a49b5b69a77d"),
    182: ("9eb71baea6deaf1edaa8771781b287ba6bb4b6a18192b0b8fe6a4b4035f8ca1b",
          "a9eb46910f41dd375c9724c1c17440ff9f23bd13df7999ca2b5924c15a7b4ef7"),
    183: ("18d4baa452f8ba6bf405f9f013b9b16e24d4ba00ab9e836af84fdfc8e52f6581",
          "b72ca0f24b3bb459b096bdde5e6cc9d0c6d2c2daa07e96ffb6618b3c2dc96320"),
    187: ("e7e04d09661a898f3e43b3326899bce0f4d2ebdeb861ba9b70ead85e8c91495c",
          "afbdd3ff12931c88fa5241ba2e50d6636098b2e48d38db46ffd2eda473fb3e77"),
}
# The historic 4-3 rule's only position recode; every other slot keeps its retail label.
ONE_POOL_POSITIONS = {"OLB": "ILB"}
# The EDGE rename (Build option edge_rename) rewrites the 16-byte "Def End" placeholder surnames of historic players
# to "Edge" in place, before this pass. They are placeholders this dataset replaces anyway, so resource states are read
# on a copy with those exact 16-byte slots put back; the compiled output replaces every name in the pool.
EDGE_PLACEHOLDER_BEFORE = "Def End".encode("utf-16le") + b"\0\0"
EDGE_PLACEHOLDER_AFTER = "Edge".encode("utf-16le") + b"\0\0" + b"\0" * 6



def xbe_status(payload):
    from . import nfl2k5_rdata_sites as sites
    try:
        state = sites.status(payload, [("historic_team_release", XBE_SITE_VA, XBE_BEFORE, XBE_AFTER)])
        if state == "foreign":
            return state
        for va, size, digest in XBE_GUARDS:
            start = sites.offset_of(payload, va)
            raw = bytearray(payload[start:start + size])
            if va <= XBE_SITE_VA < va + size:
                at = XBE_SITE_VA - va
                raw[at:at + len(XBE_BEFORE)] = XBE_BEFORE
            if sha(raw) != digest:
                return "foreign"
        return state
    except (ValueError, TypeError, struct.error, IndexError):
        return "foreign"


def apply_xbe(payload):
    """Pinned in-place lifecycle repair; no cave, allocation or runtime state."""
    from . import nfl2k5_rdata_sites as sites
    require(xbe_status(payload) in ("retail", "applied"), "Historic team reload fix: unrecognized executable")
    result, receipt = sites.apply(payload, [("historic_team_release", XBE_SITE_VA, XBE_BEFORE, XBE_AFTER)],
                                  "Historic team reload fix")
    require(xbe_status(result) == "applied", "historic team reload fix readback differs")
    return result, {**receipt, "owner": OWNER, "evidence": EVIDENCE,
                    "already_applied": result == payload, "growth_bytes": 0}


class XbePatch:
    """Adapter for the shared executable gates and ownership recorder."""
    OWNER = OWNER
    REQUESTS = REQUESTS
    apply = staticmethod(apply_xbe)
    status = staticmethod(xbe_status)


class Espn25RostersError(ValueError):
    """Unrecognized data, source or partial install; nothing may be written."""


def require(ok, message):
    if not ok:
        raise Espn25RostersError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_bounded(path, limit):
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, f"{Path(path).name} exceeds {limit} bytes")
    return raw


def u32(data, at):
    require(0 <= at <= len(data) - 4, "word outside resource")
    return struct.unpack_from("<I", data, at)[0]


def rel(data, at):
    value = u32(data, at)
    require(value != 0, "missing relative pointer")
    return at + struct.unpack_from("<i", data, at)[0] - 1


def utf16(data, at, end=None):
    end = min(len(data), end if end is not None else at + 4096)
    require(0 <= at < end and at % 2 == 0, "text outside resource")
    for stop in range(at, end - 1, 2):
        if data[stop:stop + 2] == b"\0\0":
            return data[at:stop].decode("utf-16le")
    raise Espn25RostersError("unterminated bounded text")


def describe_context(main, situ, entries):
    """Independently decode the retail historical descriptors and moment bindings.

    Ordinary current-team roster edits may coexist. Historic descriptor changes,
    changed title/date/bindings cannot use this dataset. The known expanded profile
    (25 retail rows plus the moments owner's rows, 51 since beta 76.5) is validated by its owner,
    then reduced to this dataset's original 25 bindings.
    Narrative text is used only by the offline generator, never to execute code.
    """
    require(32 < len(main) <= MAX_RESOURCE and main[:4] == b"ROST", "missing main ROST")
    body = main[32:]
    require(body[12:16] == b"ROST" and rel(body, 20) == 64 and u32(body, 0x98) == 75,
            "foreign historical descriptor layout")
    table = rel(body, 0x9C)
    require(0 <= table <= len(body) - 75 * 16, "historic descriptor table outside main ROST")
    by_id = {}
    for e in entries:
        by_id.setdefault(e.name_id, []).append(e.index)
    descriptors = []
    for index in range(75):
        at = table + index * 16
        year = struct.unpack_from("<H", body, at)[0]
        code, selector = utf16(body, at + 4, at + 12), utf16(body, rel(body, at + 12))
        kit = body[at + 2]
        filename = f"h-{code}-{year}-{selector}-{kit}.iff"
        identity = zlib.crc32(filename.upper().encode("utf-16le")) & 0xFFFFFFFF
        hits = by_id.get(identity, ())
        require(len(hits) == 1 and 113 <= hits[0] <= 187, "missing or duplicate historic archive identity")
        descriptors.append(dict(index=index, year=year, kit=kit, code=code,
                                selector=selector, filename=filename, id=identity, outer=hits[0]))
    by_team = {(d["selector"], d["year"]): d for d in descriptors}
    require(len(by_team) == 75 and len({d["outer"] for d in descriptors}) == 75,
            "duplicate historic descriptor")
    require(32 < len(situ) <= MAX_RESOURCE and situ[:4] == b"SITU" and u32(situ, 16) == 0, "foreign SITU wrapper")
    count = u32(situ, 8)
    canonical = None
    if count != COUNT:
        # b77 i1: the expanded profile has exactly the moments owner's row count (25 retail rows plus every authored
        # moment: 51 since beta 76.5 added the Unc Bowl). The old literal (25 or 50) refused every 51-row disc.
        from . import nfl2k5_espn25_more_moments as more
        data = more.Data.load()
        require(count == more.RETAIL_COUNT + len(data.moments), "foreign SITU wrapper")
        require(more.situ_rows(situ, data) == "applied", "foreign expanded SITU profile")
        canonical = dataset()[0]["moments"]
    size = u32(situ, 4)
    require(RECORDS + count * STRIDE <= size <= len(situ) - 32, "SITU span outside entry")
    sb = situ[32:32 + size]
    require(sb[12:16] == b"SITU" and u32(sb, 64) == count, "foreign SITU table")
    moments = []
    for i in range(COUNT):
        at = RECORDS + i * STRIDE
        m = {"moment": i, "title": utf16(sb, rel(sb, at)), "date": utf16(sb, rel(sb, at + 12)),
             "history": utf16(sb, rel(sb, at + 4)), "objective": utf16(sb, rel(sb, at + 8))}
        if canonical is not None:
            # The complete known text profile was checked above. Retain the
            # original roster transaction's title/date context pin.
            m.update(title=canonical[i]["title"], date=canonical[i]["date"])
        for side, pointer, year in (("away", 20, 28), ("home", 24, 32)):
            pair = (utf16(sb, rel(sb, at + pointer)), u32(sb, at + year))
            require(pair in by_team, "unrecognized moment name/year")
            m[side] = dict(by_team[pair])
        moments.append(m)
    colleges = rr.RosterDocument(body).colleges
    return {"descriptors": descriptors, "moments": moments, "colleges": colleges}


def context_sha(context):
    # Narratives may be edited without changing who loads; title/date may not.
    value = {**context, "moments": [{k: v for k, v in m.items() if k not in ("history", "objective")}
                                   for m in context["moments"]]}
    return sha(json.dumps(value, sort_keys=True, ensure_ascii=True).encode())


def parse_csv(text):
    require(isinstance(text, str) and len(text.encode("utf-8")) <= 256 * 1024, "roster CSV exceeds 256 KiB")
    reader = csv.DictReader(io.StringIO(text), strict=True)
    require(tuple(reader.fieldnames or ()) in (CSV_COLUMNS, CSV_COLUMNS + ("hand",)), "unexpected roster CSV columns")
    rows = list(reader)
    require(len(rows) == 53, "each historic roster requires 53 rows")
    names = set()
    for index, row in enumerate(rows):
        require(None not in row and None not in row.values(), "CSV row width differs from header")
        require(row["pool"] == "primary" and row["index"] == str(index), "CSV rows must be primary indices 0..52")
        first, last = row["first"], row["last"]
        require(first and last and rr.validate_name(first) == first and rr.validate_name(last) == last,
                "invalid player name")
        identity = (first.casefold(), last.casefold())
        require(identity not in names, "duplicate player name in one roster")
        names.add(identity)
        require(row["position"] in rr.POSITIONS, "invalid retail position")
        require(row.get("hand", "") in ("", "Left", "Right"), "invalid historic hand")
        for field, maximum in (("jersey", 99), *((r, 255) for r in rr.RATING_BYTE_ORDER)):
            value = row[field]
            require(value.isascii() and value.isdigit() and str(int(value)) == value and int(value) <= maximum,
                    f"invalid {field}")
    return rows


def dataset():
    # Revalidate on every public operation, including a long-lived Studio's
    # availability refresh. A deleted or modified CSV must not use cached data.
    raw = read_bounded(DATA_DIR / "manifest.json", MAX_MANIFEST)
    require(sha(raw) == DATASET_SHA256, "historic roster manifest differs from the shipped dataset")
    manifest = json.loads(raw)
    require(manifest["schema"] == SCHEMA and len(manifest["resources"]) == 35,
            "foreign dataset schema/count")
    require(len({t["outer"] for t in manifest["resources"]}) == 35, "duplicate dataset resource")
    sheets = {}
    for target in manifest["resources"]:
        name = target["csv"]
        require(Path(name).name == name and name == target["filename"][:-4] + ".csv", "foreign CSV path")
        raw = read_bounded(DATA_DIR / name, 256 * 1024)
        require(sha(raw) == target["csv_sha256"], f"{name}: dataset digest mismatch")
        rows = parse_csv(raw.decode("utf-8"))
        require(len(target["players"]) == 53, "missing player provenance")
        for row, provenance in zip(rows, target["players"]):
            require(provenance["slot"] == int(row["index"]) and
                    (row["first"], row["last"]) == (provenance["first"], provenance["last"]),
                    "player identity differs from its provenance")
        sheets[target["outer"]] = rows
    return manifest, sheets


def without_edge_placeholders(payload):
    """A copy with the EDGE rename's exact 16-byte "Edge" placeholder surnames put back to "Def End".

    Only last-name allocations that hold exactly the EDGE rename's bytes change; anything else is returned as is.
    Used to read a resource's state and as the compile input, never written back on its own.
    """
    if not isinstance(payload, (bytes, bytearray)) or len(payload) <= 32 or payload[:4] != b"ROST":
        return payload
    try:
        document = rr.RosterDocument(bytes(payload[32:]))
    except (ValueError, IndexError, KeyError, struct.error):
        return payload
    field = rr.FIELD_BY_NAME["last_name_pointer"]
    out = None
    for player in document.players:
        at = 32 + player.offset + field.offset
        target = at + struct.unpack_from("<i", payload, at)[0] - 1
        if 32 <= target <= len(payload) - 16 and payload[target:target + 16] == EDGE_PLACEHOLDER_AFTER:
            out = out if out is not None else bytearray(payload)
            out[target:target + 16] = EDGE_PLACEHOLDER_BEFORE
    return bytes(out) if out is not None else payload


def without_helmet_equipment(payload, outer):
    """Modern helmets (beta 76 hm) keeps the classic equipment on the historic teams: it writes only the helmet and
    facemask fields of a few records. Those fields are put back to retail before this module reads a state, so the
    two writers compose in either order (their fields are disjoint)."""
    try:
        from . import nfl2k5_modern_helmets as helmets
        return helmets.without_equipment_edits(payload, outer)
    except (ImportError, OSError, ValueError, KeyError):
        return payload


HISTORIC_SPARES = {'00': 9, '01': 14, '02': 4, '03': 10, '04': 3, '05': 7, '06': 8, '07': 10,
    '08': 7, '09': 10, '10': 7, '11': 8, '12': 7, '13': 6, '14': 11, '15': 7, '16': 12, '17': 9,
    '18': 8, '19': 8, '20': 5, '21': 9, '22': 6, '23': 13, '24': 12, '25': 8, '26': 5, '27': 8,
    '28': 9, '29': 10, '30': 5, '37': 3}


def without_historic_styles(payload, target):
    """Normalize only m1's exact USA spare-style transform; full roster pins still decide the state."""
    from . import nfl2k5_historic_styles as styles
    try:
        code, _style = styles.historic_style(payload)
        if code != target['code'] or code not in HISTORIC_SPARES:
            return payload
        spare = HISTORIC_SPARES[code]
        candidate = styles.undo_spare(payload, code, spare)
        return candidate if styles.with_spare(candidate, spare) == payload else payload
    except (ValueError, KeyError, IndexError, struct.error):
        return payload


def resource_status(payload, target, *, colleges=None, source_colleges=None):
    """retail / applied (retail positions), one_pool / one_pool_applied (One-pool reclassified), or foreign.

    The input states are read with the EDGE rename's placeholder surnames put back; the applied states hold no
    placeholder at all (every name is a dataset name).
    """
    if not isinstance(payload, (bytes, bytearray)) or len(payload) != target["size"]:
        return "foreign"
    payload = without_helmet_equipment(payload, target["outer"])
    payload = without_historic_styles(payload, target)
    # Applied resources carry live indices. Normalize only those fields back to
    # the shipped table before comparing the full payload pin. Retail resources
    # are still recognized against their untouched, canonical bytes below.
    applied = payload
    if colleges is not None:
        canonical = dataset()[0]["colleges"] if source_colleges is None else source_colleges
        if colleges != canonical:
            applied = bytearray(payload)
            try:
                document = rr.RosterDocument(payload[32:])
            except (ValueError, IndexError, KeyError, struct.error):
                return "foreign"
            for player in document.players:
                index = player.record.values["college_pointer"]
                if not 0 <= index < len(colleges) or canonical.count(colleges[index]) != 1 or colleges.count(colleges[index]) != 1:
                    applied = b""
                    break
                struct.pack_into("<I", applied, 32 + player.offset + rr.FIELD_BY_NAME["college_pointer"].offset, canonical.index(colleges[index]))
    digest = sha(applied)
    pins = ONE_POOL_PINS.get(target["outer"], (None, None))
    if digest == target["applied_sha256"]:
        return "applied"
    if digest == pins[1]:
        return "one_pool_applied"
    digest = sha(without_edge_placeholders(payload))
    if digest == target["retail_sha256"]:
        return "retail"
    if digest == pins[0]:
        return "one_pool"
    return "foreign"


APPLIED_STATES = ("applied", "one_pool_applied")


def status(resources: Mapping[int, bytes], *, colleges=None):
    """Status of the COMPLETE 35-resource transaction; raw XBE is foreign.

    retail, applied, one_pool or one_pool_applied when every resource agrees; mixed layouts are foreign.
    """
    manifest, _ = dataset()
    if not isinstance(resources, Mapping) or set(resources) != {t["outer"] for t in manifest["resources"]}:
        return "foreign"
    states = {resource_status(resources[t["outer"]], t, colleges=colleges, source_colleges=manifest["colleges"]) for t in manifest["resources"]}
    return states.pop() if len(states) == 1 else "foreign"


def changed_spans(before, after):
    require(len(before) == len(after), "fixed-span writer cannot grow a resource")
    out, start = [], None
    for at in range(len(before) + 1):
        differs = at < len(before) and before[at] != after[at]
        if differs and start is None:
            start = at
        if not differs and start is not None:
            out.append({"offset": start, "before": before[start:at].hex(), "after": after[start:at].hex()})
            start = None
    return out


def compile_resource(raw, rows, colleges, *, layout="retail", source_colleges=None):
    """Existing name allocator + player encoder, inside the discovered retail pool.

    All names move to an existing first allocation before assigning final names;
    this releases the old placeholders through StringPool, avoiding fragmentation
    without inventing free bytes. CSV college text is translated to the main-table
    *index*, because C1030 does not interpret this field as a relative pointer.
    No generic college writer is called on a historic resource.
    """
    require(32 < len(raw) <= 16384 and raw[:4] == b"ROST" and u32(raw, 4) == len(raw) - 32 and
            u32(raw, 16) == 0, "historic ROST must be one complete uncompressed resource")
    document = rr.RosterDocument(raw[32:])
    require(len(document.players) == 53 and len(document.teams) == 1 and document.college_count == 0 and
            all(p.pool == "primary" for p in document.players) and document.teams[0].player_count == 53,
            "foreign historic roster layout")
    require(document.to_body(normalise_commentary=False) == raw[32:], "retail codec round trip differs")
    bounds = (document.names.start, document.names.end)
    original_values = [dict(p.record.values) for p in document.players]
    original_slots = tuple(document.teams[0].slots)
    require(len(rows) == 53, "expected 53 roster rows")
    seed = document.names.blocks[bounds[0]].text
    for p in document.players:
        document.set_name(p, "first", seed)
        document.set_name(p, "last", seed)
    # The importer accepts sparse CSVs. Only these supported editable cells are
    # submitted; ratings and positions are compared to their original slot below.
    stream = io.StringIO()
    writer = csv.DictWriter(stream, ["pool", "index", "first", "last", "jersey"],
                            extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    # This historical author owns names, jerseys, college pointers and explicitly filled hand cells.
    # Defer commentary through preview/apply as well as final serialization;
    # the full Studio save retains its default commentary normalization.
    receipt = rr.import_csv(document, stream.getvalue(), delimiter=",", normalise_commentary=False)
    require(receipt["rows"] == 53 and not receipt["log"], "roster import refused: " + "; ".join(receipt["log"]))
    for p, row, old in zip(document.players, rows, original_values):
        require(row["pool"] == p.pool and int(row["index"]) == p.index, "roster slot identity changed")
        expected = row["position"] if layout == "retail" else ONE_POOL_POSITIONS.get(row["position"], row["position"])
        require(expected == rr.POSITIONS[old["position"]] and
                all(int(row[k]) == old[k] for k in rr.RATING_BYTE_ORDER), "retail slot position/ratings changed")
        require((p.first, p.last) == (row["first"], row["last"]), "name import was incomplete")
        if row.get("hand"):
            p.record.set("hand", rr.HANDS.index(row["hand"]))
        name = row["college"]
        if not name and source_colleges is not None:
            index = old["college_pointer"]
            require(0 <= index < len(source_colleges), "template college index outside source table")
            name = source_colleges[index]
        if name:
            require(colleges.count(name) == 1, f"college must resolve exactly once in the main table: {name!r}")
            p.record.set("college_pointer", colleges.index(name))
    result = raw[:32] + document.to_body(normalise_commentary=False)
    require(len(result) == len(raw) and result[:32] == raw[:32], "resource wrapper/size changed")
    allowed = set(range(32 + bounds[0], 32 + bounds[1]))
    for p in document.players:
        for field in ("first_name_pointer", "last_name_pointer", "jersey", "college_pointer"):
            spec = rr.FIELD_BY_NAME[field]
            allowed.update(range(32 + p.offset + spec.offset, 32 + p.offset + spec.offset + spec.size))
        if rows[p.index].get("hand"):
            at = 32 + p.offset + rr.FIELD_BY_NAME["hand"].offset
            allowed.add(at)
            require((raw[at] ^ result[at]) & ~0x02 == 0, "historic hand edit escaped bit 1")
    require(all(i in allowed for i, (a, b) in enumerate(zip(raw, result)) if a != b), "edit escaped owned roster fields")
    after = rr.RosterDocument(result[32:])
    require(tuple(after.teams[0].slots) == original_slots, "team pointer/depth order changed")
    for p, old, row in zip(after.players, original_values, rows):
        require(all(p.record.values[k] == v for k, v in old.items()
                    if k not in ("first_name_pointer", "last_name_pointer", "jersey", "college_pointer")
                    and not (k == "hand" and row.get("hand"))),
                "rating, appearance or other record bits changed")
    return result


def _compile_resources(resources: Mapping[int, bytes], *, colleges=None):
    """Pure all-or-nothing compilation; replay is byte-identical with zero writes.

    The retail position layout compiles to the pinned applied profile; the One-pool layout (the reclassify already
    ran) compiles to its own pinned profile, which equals reclassify(applied) byte for byte.
    """
    manifest, sheets = dataset()
    colleges = manifest["colleges"] if colleges is None else colleges
    state = status(resources, colleges=colleges)
    require(state in ("retail", "applied", "one_pool", "one_pool_applied"),
            "historic rosters refuse missing, mixed or foreign resources")
    layout = "one_pool" if state.startswith("one_pool") else "retail"
    goal = "one_pool_applied" if layout == "one_pool" else "applied"
    output, receipts = {}, []
    for t in manifest["resources"]:
        before = bytes(resources[t["outer"]])
        after = before if state == goal else compile_resource(without_edge_placeholders(before), sheets[t["outer"]],
                                                              colleges, layout=layout, source_colleges=manifest["colleges"])
        require(resource_status(after, t, colleges=colleges, source_colleges=manifest["colleges"]) == goal, "compiled roster differs from the pinned profile")
        changes = changed_spans(before, after)
        output[t["outer"]] = after
        receipts.append({"outer": t["outer"], "filename": t["filename"], "size": t["size"],
                         "before_sha256": sha(before), "after_sha256": sha(after),
                         "changed_bytes": sum(len(c["before"]) // 2 for c in changes), "changes": changes,
                         "wrapper_identical": True, "compressed": False})
    return output, {"schema": SCHEMA, "owner": OWNER, "evidence": EVIDENCE,
                    "dataset_sha256": DATASET_SHA256, "before": state, "after": goal, "layout": layout,
                    "already_applied": state == goal, "xbe_changed": False, "growth_bytes": 0,
                    "changed_bytes": sum(r["changed_bytes"] for r in receipts), "resources": receipts,
                    "lineups": "Season inference; see per-moment basis and per-player exceptions in manifest.json"}


def require_build_ready():
    # The option writes every moment, so it cannot omit Wide Right safely.
    # Keep read-only inspection and the bounded native repair available for
    # research. There is intentionally no command-line force/override switch.
    require(not BUILD_BLOCK_REASON, BUILD_BLOCK_REASON)


def apply(resources: Mapping[int, bytes], *, colleges=None):
    """Build-facing resource preflight, including the unresolved gameplay hold."""
    require_build_ready()
    return _compile_resources(resources, colleges=colleges)


apply_resources = apply
resources_status = status


def _read_archive(archive, *, with_colleges=False):
    manifest, sheets = dataset()
    outputs, entries = {}, {}
    for t in manifest["resources"]:
        require(t["outer"] < len(archive.entries), "missing historic outer entry")
        e = archive.entries[t["outer"]]
        require(e.name_id == t["id"] and e.size == t["size"], "historic archive identity/size changed")
        entries[e.index] = e
        outputs[e.index] = archive.read(e.virtual_offset, e.size)
    context_raw = {}
    for index in (MAIN_OUTER, SITU_OUTER):
        e = archive.entries[index]
        require(32 < e.size <= MAX_RESOURCE, "context resource exceeds bounded read")
        context_raw[index] = archive.read(e.virtual_offset, e.size)
    context = describe_context(context_raw[5], context_raw[22], archive.entries)
    # Preserve the shipped descriptor and moment-binding pin. College labels
    # outside this transaction may legitimately change; resolve needed names.
    require(context_sha({**context, "colleges": manifest["colleges"]}) == manifest["context_sha256"],
            "moment bindings or main descriptor table changed")
    for name in sorted({r["college"] for rows in sheets.values() for r in rows if r["college"]}):
        require(context["colleges"].count(name) == 1,
                f"college must resolve exactly once in the main table: {name!r}")
    return (outputs, entries, context["colleges"]) if with_colleges else (outputs, entries)


def read_resources(source):
    """Bounded reads from a disc image or an extracted game/pack folder."""
    with rr._outer_image()(source) as archive:
        resources, _ = _read_archive(archive)
    return resources


def _image_xbe(stream):
    from . import nfl2k5_throw_tuning as tuning
    offset, size = tuning._xdvdfs_module().xbe_extent(stream.fileno(), os.fstat(stream.fileno()).st_size)
    require(0 < size <= 16 * 1024**2, "Historic team reload fix: executable exceeds 16 MiB")
    stream.seek(offset)
    payload = stream.read(size)
    require(len(payload) == size, "Historic team reload fix: short executable read")
    return offset, payload


def read_xbe(source):
    source = Path(source)
    if source.is_dir():
        return read_bounded(source / "default.xbe", 16 * 1024**2)
    with source.open("rb") as stream:
        return _image_xbe(stream)[1]


def preflight_image(source):
    """Validate both members of the roster plus native reload repair before copy."""
    require_build_ready()
    with rr._outer_image()(source) as archive:
        resources, _, colleges = _read_archive(archive, with_colleges=True)
    _, receipt = apply(resources, colleges=colleges)
    _, native = apply_xbe(read_xbe(source))
    return {**receipt, "load_fix": native}


def install_image_xbe(stream, offset, before, after):
    """Fixed-span write on an already preflighted private image; no extent growth."""
    require(_image_xbe(stream) == (offset, before), "executable changed after preflight")
    spans = changed_spans(before, after)
    for span in spans:
        stream.seek(offset + span["offset"])
        raw = bytes.fromhex(span["after"])
        require(stream.write(raw) == len(raw), "short historic reload fix write")
    stream.flush()
    os.fsync(stream.fileno())
    require(_image_xbe(stream) == (offset, after), "historic reload fix readback differs")
    return [{**span, "image_offset": offset + span["offset"]} for span in spans]


def image_status(source):
    try:
        with rr._outer_image()(source) as archive:
            raw, _, colleges = _read_archive(archive, with_colleges=True)
        resources = status(raw, colleges=colleges)
        native = xbe_status(read_xbe(source))
        if "foreign" in (resources, native):
            return "foreign"
        # The position layout (retail or One-pool) is not part of the Build status: both read retail/applied.
        if resources in APPLIED_STATES:
            return "needs load fix" if native == "retail" else "applied"
        return "retail"
    except (OSError, ValueError, IndexError, KeyError, struct.error):
        return "foreign"


def apply_to_image(path):
    """Final resource pass on a private build copy, with preflight and readback.

    Rejects every mixed/foreign state before writing. An I/O failure requires
    discarding the private copy; this function is not a power-loss transaction.
    Handles are closed before any caller publishes/replaces the file.
    """
    require_build_ready()
    path = Path(path).resolve(strict=True)
    require(path.is_file(), "image adapter requires a private disc-image file")
    size = path.stat().st_size
    with path.open("r+b") as executable, rr._outer_image()(path, writable=True) as archive:
        xbe_offset, xbe_before = _image_xbe(executable)
        xbe_after, native = apply_xbe(xbe_before)
        original, entries, colleges = _read_archive(archive, with_colleges=True)
        output, receipt = apply(original, colleges=colleges)
        require(archive._read_table() == archive.entries, "archive table changed during roster preflight")
        current, rechecked, current_colleges = _read_archive(archive, with_colleges=True)
        require(path.stat().st_size == size and entries == rechecked and original == current and colleges == current_colleges,
                "image changed during roster preflight")
        require(_image_xbe(executable) == (xbe_offset, xbe_before), "executable changed during roster preflight")
        spans = []
        for index, after in output.items():
            e = entries[index]
            segments = archive._segments(e.virtual_offset, e.size)
            spans.append({"outer": index, "virtual_offset": e.virtual_offset,
                          "segments": [{"pack": p.name, "image_offset": p.image_offset + off, "size": n}
                                       for p, off, n in segments]})
            if after != original[index]:
                require(archive.write(e.virtual_offset, after) == len(after), "short historic roster write")
        verified, _, verified_colleges = _read_archive(archive, with_colleges=True)
        require(path.stat().st_size == size and verified == output and verified_colleges == colleges,
                "historic roster readback differs")
        xbe_spans = install_image_xbe(executable, xbe_offset, xbe_before, xbe_after) if xbe_after != xbe_before else []
    receipt.update(load_fix=native, xbe_changed=bool(xbe_spans), xbe_spans=xbe_spans,
                   already_applied=receipt["already_applied"] and not xbe_spans,
                   changed_bytes=receipt["changed_bytes"] + sum(len(s["after"]) // 2 for s in xbe_spans))
    receipt.update(image_size_before=size, image_size_after=size, image_spans=spans)
    return receipt


def build_image(source, output, *, receipt_path=None):
    """Copy-first publication; an optional receipt is staged before the image.

    Ordinary failures publish neither file. This is not a two-file power-loss
    transaction: a crash between replacements can leave the receipt alone.
    """
    require_build_ready()
    source, output = Path(source).resolve(strict=True), Path(output).resolve()
    require(source.is_file() and source != output and not output.exists(), "output must be a new file distinct from the source image")
    receipt_output = Path(receipt_path).resolve() if receipt_path is not None else None
    if receipt_output is not None:
        require(receipt_output not in (source, output) and not receipt_output.exists(),
                "receipt must be a new path distinct from both images")
    def identity():
        st = source.stat()
        return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns
    source_identity = identity()
    preflight_image(source)  # Compile resources and validate native repair before a large copy.
    require(shutil.disk_usage(output.parent).free - source.stat().st_size > 100 * 1024**3,
            "copy would leave less than 100 GiB free; no image created")
    with ExitStack() as stack:
        temporary = stack.enter_context(tempfile.TemporaryDirectory(prefix="espn25-rosters-", dir=output.parent))
        staged = Path(temporary).resolve() / "image.iso"
        staged_receipt = None
        if receipt_output is not None:
            # Opening the destination directory now rejects an unavailable
            # receipt path before copying, including paths on another volume.
            receipt_directory = stack.enter_context(tempfile.TemporaryDirectory(
                prefix="espn25-receipt-", dir=receipt_output.parent))
            staged_receipt = Path(receipt_directory).resolve() / "receipt.json"
        with source.open("rb") as src, staged.open("xb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
        receipt = apply_to_image(staged)
        require(identity() == source_identity, "source changed during build; no image published")
        require(not output.exists(), "output appeared during build")
        if staged_receipt is not None:
            with staged_receipt.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(receipt, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            require(not receipt_output.exists(), "receipt appeared during build")
            os.replace(staged_receipt, receipt_output)
        try:
            os.replace(staged, output)
        except BaseException:
            if staged_receipt is not None:
                receipt_output.unlink()
            raise
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("status")
    inspect.add_argument("source", type=Path)
    commands.add_parser("validate-dataset")
    build = commands.add_parser("build")
    build.add_argument("source", type=Path)
    build.add_argument("output", type=Path)
    build.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "status":
        state = image_status(args.source)
        print(json.dumps({"owner": OWNER, "status": state, "evidence": EVIDENCE,
                          "build_block_reason": BUILD_BLOCK_REASON}))
        return 1 if state == "foreign" else 0
    if args.command == "validate-dataset":
        manifest, rows = dataset()
        print(json.dumps({"resources": len(rows), "players": sum(map(len, rows.values())),
                          "moments": len(manifest["moments"]), "sha256": DATASET_SHA256,
                          "evidence": EVIDENCE, "default_enabled": DEFAULT_ENABLED,
                          "build_block_reason": BUILD_BLOCK_REASON}))
        return 0
    receipt = build_image(args.source, args.output, receipt_path=args.receipt)
    print(f"{EVIDENCE}: wrote {args.output}; {receipt['changed_bytes']} roster bytes changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
