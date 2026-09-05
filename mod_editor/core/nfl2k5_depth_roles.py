"""Tier 1 depth roles: bounded personnel edits in PLAY books; no XBE patch.

Ordinals are starting (chain, row) pairs, not guaranteed roster identities.
See docs/mod_editor/depth_roles.md for the disagreement and ambiguity policy.
Only digests of private data are shipped. Archives use the studio's existing
OuterImage reader/writer; books use its parser, codec and category compiler.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
from typing import Any, Callable, Mapping

from .errors import ValidationError
from . import nfl2k5_play_codec as codec
from . import nfl2k5_play_library as lib
from . import nfl2k5_playbook_inspector as insp
from . import nfl2k5_special_roles as special
from .nfl2k5_formation_play_writer import compile_personnel_categories
from .nfl2k5_playbook_pack import _outer_image

SCHEMA = "nfl2k5_depth_roles/v2"
WR, CB = 9, 18
DISAGREEMENT_YD = 2.0
RESOURCE_SIZE = insp.RESOURCE_HEADER_SIZE + insp.BODY_SIZE
HISTOGRAMS = ("wr_inner", "nickel_inner", "dime_inner", "nickel_ordinals", "dime_ordinals")
RETAIL_TOTALS = {
    "wr_inner": {"0": 196, "1": 115, "2": 100, "3": 20, "4": 35},
    "nickel_inner": {"2": 66, "3": 5},
    "dime_inner": {"2": 2, "3": 36},
    "nickel_ordinals": {"0,1,2": 66, "0,1,3": 5},
    "dime_ordinals": {"0,1,2,3": 38},
}

# SHA-256 of role-relevant category membership, ordinals and x[0] geometry.
# Front-seven recodes, names, routes and unrelated formations are not owned.
RETAIL_SHA256: dict[str, str] = {
    "ARZ": "5aaf88e46b485039e16ca59858ec1204cc0dc0df08218a09755066ba4c816c6b",
    "ATL": "913f64b9d417c8af828e01b158efa2d8713c262775d269740b50f2088ef6ac7d",
    "BAL": "089585eea9baf2ac0916bcac0432dea6bfe8b10b6cf9c3f4f1dc0b18095eb4ef",
    "BUF": "42919207600560dde750037623f195ad91de705311750fddcf338fccbbd10348",
    "CAR": "cb0b7547a1028656242d8cef8ab90c6c1f3e6812c89228f8e8dcec032beaf4c0",
    "CHI": "57517eba67b7ddc937e82b9338ab500fd89decc5593fda255b2297c5fa671685",
    "CIN": "8a7e8db3f82cfff69e10cd85b4fd8ef2f4a8d3cb0e07ba6b73d90edfddb89da8",
    "CLE": "6e6c40864c711072eb6e1556711c32f05bb044ac24a1566a5ea5d2aaa463a71c",
    "DAL": "95e75aa46482b7e733d3ce4113ef099ea4e468646f367b114cde25d8728ebbfd",
    "DEN": "04f06cd7cb824741f5cde655e15c707b7ff455570787ec29a9cc472bcde2849a",
    "DET": "76552fbdfa5b8c9ac308fa9d5e5dff78ab3d9f2523242535d40d0cb06eb19032",
    "Editor": "71df9fa4374e6208d98a100d69139ef604023ce75fe8e5803fdd6c5cac1c9717",
    "GB": "b108bdc449b7da87a360f3b5bfbbb378a10ad0e6b395f3a55ad65c383bbe4260",
    "GEN": "f769082e6c25d88a75e9aa45d7e36e76c7961a32073885c13bb9a6f56749ae0b",
    "HOU": "efeb8c776c9a8ab5ab51ef46403316be61c95d230b92f1b6de60c837d69701b5",
    "IND": "09b564eec5f57fad7075ce5eaf2cd11746f0aa303953bd6b416e227131c4adbe",
    "JAX": "245331fe2c473b60f1b93429bbe60866d949108abef864d50f633911134724c5",
    "KC": "61cf0ddc67c6f27a17f33a56a1b0fca2e3b4f806ebf7d4c02b311acfd3ed6d2b",
    "MIA": "6f3bbe60f1a5c05fd69fb9f36022c32867e26a344004285b197215a2c2d56cfd",
    "MIN": "03ce47336c6d17376d2d4e31b67b9a58e9e4f0fbcf3ed9d1a037a3bc158ccbf4",
    "NE": "0954ecefb57e8e5e21d597dc060a9793324e55dc7080410cb3aac52db67d6d8b",
    "NO": "a3889482a7a4465f09b6958706a42b29016261bc66bc8ba813f9e85bbefa0995",
    "NYG": "56db25f1cf8569b46194fe4ae51d828de12894278ba6b201a4e49e94b5c443b9",
    "NYJ": "9c733964b0ff4af9172c8c250ec84481d9a9ea2f7b0ae7b0d4866806831c6aa1",
    "OAK": "ab9d495e40a1a0596983444a6db2024a587b82a88f39e53e1bdd23a245513535",
    "PHI": "9c11673ae36e7e9bf5252bd8c92049486b1ae58ee42a698078ac16dae3e42c1e",
    "PIT": "4c50008b42910e30f2e2dfe7f687576b78ea9481f08abc48cfbf5b00e723044a",
    "PRACTICE": "70ccc2e4dde96a05c7c6d1d66cedb6ffc369b94ee1fad928146ab3a27c5cbdac",
    "reference": "e63ff4feec30bf218d8ba9a671c238b1e8ad3c1ba4f956290cae99f1fe4f6986",
    "SD": "c4fa2269c6b2ac11138d31910f8d0b0f7d626d35765ea6f34e7d49e58ec15d15",
    "SEA": "e44addb7341468aabe5099e4e914c3672976956474075530cf92eb0c973cf8a8",
    "SF": "bd626fb39c89466f929c2ca609826625157e8d711893d9783de316be42f39878",
    "STL": "606c427713cc7521ab4862d4e863bfe63707c6b7ed66d46ad1247daf0af312ef",
    "TB": "bfd66adea7b5a191835e0b86f30c91bbeb0ec6b05d869dd56fb1a4a7583f0a3e",
    "TEN": "53bdd4cb53c4e424bdc61934fdd2e0d79a7d13351fecd30406f5945c2db3420e",
    "WAS": "a5197533f0be23b3a61954b7d7efb836c19b9410e1f51de0087f0540a9adbd0d",
    "WCO": "f3df1c4593558cb61d9d01921be38e43772d40b9d7fb4cb5f755526f3fa573ef"
}
APPLIED_SHA256: dict[str, str] = {
    "ARZ": "8a57826ff678912ce5253dd22bef763b9038b3ff568c33313abb40f1ca24a829",
    "ATL": "567a626180570194d8cd79f8969e1462bb00bddcc1b6fb2263a5a342e44bc739",
    "BAL": "1b84774201bb1f0ef19bf3bdcd117917e2dc27cdd42925fd08641dc6002cd992",
    "BUF": "be382a74b1903dfc26d37f85506bdb55312c47d52b76e267e6207ee31edb7eab",
    "CAR": "89bf5cb76b90041d3946b26f58b754718670bc8362ea286554cb2033c013a2af",
    "CHI": "aef4fb6cde25374c23c821a1d9c3a682c8b15542b7330d46122e437b534eed0f",
    "CIN": "6f0bfeb957090067ea1b7679f14e2b16e7d73542dbe2d2cc9c9ab0823445d425",
    "CLE": "a2726f387beeca9575dc7f70057364d261425ee366f66ba9d425f5d4ba2db852",
    "DAL": "5b3166a12cdb1b2765bda0e5a32cbb97fa363a5239daf89419b3756c990bad6b",
    "DEN": "9cf86c85491a4206fc28ae635f807d7199c7ef58598bfde8623dea2312ec5cf1",
    "DET": "98e234d6af7352281519d9c0c1eca7f49a4050c36abb013a4b1e38a8216c3272",
    "Editor": "d622f2d2417bd427c415ca99050cf954b6b3d6fa967fade5303cc125b4db1381",
    "GB": "99d93f5d80a77f99f3e9e334a827be5b14b577773eb56713461a7942f926cb5e",
    "GEN": "492e8fcedc753f8fa506b60c66c0f6f7891c46fd70a49ece708222456f110403",
    "HOU": "42b5aba2bf0944de5f1ef2b66423e8c8de40faf83478af51346ed3188a915138",
    "IND": "863fa9f6361f319c0659b49bd914d63388ace068d5a34184766f9f216b54bc19",
    "JAX": "58adc10f3ba078071ff24c5cfa958c0aad4e987642c61693665583f361f7af3b",
    "KC": "64cf2354907996f7c88d54ae18a21615e859756a844ba32c8a605d7b6cb4e332",
    "MIA": "f840f899b17a9e74a9fe5d7fde140f1ef434775df3c4a7f82e79edd538411c6d",
    "MIN": "cc543ae02531f75f7c6c634139fd4baf87c01f9123bd1d2413369c7c6a19c006",
    "NE": "8baae2309f86c130ed5260daf721a07400a06e1a0ad55fb34da17dec2f2a6f28",
    "NO": "4a512cb54e8991946de4dc7a366822d60a9a17cb3bd21b4fc2d60b24397958fd",
    "NYG": "8057e743fa1800e840961c4ea87f642f6a7442ceb9ad8f240d6170ad4d3e92b7",
    "NYJ": "153f4b6c32c25e89c01377cf093a79216213a5c24cd17e04fe0e6cd9757f6803",
    "OAK": "bf206476f5790009fc551e29f9613d27f38fed38ebf2cc7ba5052f3988bfcbb3",
    "PHI": "b487a99327975dba49991c22389b3a807649e7d4d45ac3df7b390ed480b9e11b",
    "PIT": "d7e714a0c932f79e2633cbbc160436080ba9d354eadac7f8874c92577c53e269",
    "PRACTICE": "14ea1fe55add7bb4b667c8d2e4ef8557a97dea16a77dc4f246b2e2c37d3ec87d",
    "reference": "7791982d1d0602541528ae85ebb8c46f75a4f92b0b78f3963fe00d250cb817b9",
    "SD": "efbf119b4da3daadbeedb8ed16e2fc8104330d7fda8abb3dadd8cf21e839278a",
    "SEA": "a20ce7bba5c9ed62ca70dbbc26066437a288d486d6db7e9de82a57bf6107f626",
    "SF": "1253558ad21a7781c596da1afd520c212e60c3bbe5941b69794870ad992e4882",
    "STL": "92c72c5028c98dc498c52d83cf44dce4d3cd2e7f5a0fe429eb25a4456a7ac4d0",
    "TB": "5956998c16930b4981c8d85ceb6ecb3e77459b37cb852b07e17320afff71997b",
    "TEN": "f594506745153013165844d18b94004c01df47698f8f6698ab7a16393e50c314",
    "WAS": "cc7e621073a139767ba5a549931994eb5ba56f4985fb7f6d8217d35d81536328",
    "WCO": "6d30234bb2f5ff664860d850bc72ea8f792c93d3c8383d22ccde91951480adb5"
}


class DepthRolesError(ValidationError):
    """Malformed book, unrecognised role data, or a failed output gate."""


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise DepthRolesError(message)


def _parse(raw: bytes) -> insp.Nfl2k5Playbook:
    _require(len(raw) == RESOURCE_SIZE, "Expected an exact wrapped PLAY book.")
    head = struct.unpack_from("<4s7I", raw)
    _require(head[:5] == (b"PLAY", insp.BODY_SIZE, insp.BODY_SIZE, 0, 0)
             and head[6:] == (0, 0), "Expected an uncompressed PLAY wrapper.")
    book = insp.parse_playbook_resource(raw, asset_id="book:depth-roles")
    body = raw[insp.RESOURCE_HEADER_SIZE:]
    for form in book.formations:
        cat = lib.formation_category(body, form.index)
        _require(cat < len(book.categories), f"{book.book_name}: formation {form.index} has missing group {cat}.")
        # The inspector decodes low-nine-bit play IDs; require the retail
        # active-link marker too, without rewriting any valid empty sentinel.
        for link in form.play_links:
            _require((link.packed_value & 0xF800) == 0x8000,
                     f"{book.book_name}: formation {form.index} has an invalid link word.")
    for cat in book.categories:
        codes = lib.category_positions(body, cat.index)
        _require(all((c & 31) <= CB for c in codes),
                 f"{book.book_name}: group {cat.index} has an unknown position kind.")
    return book


def _groups(raw: bytes, book: insp.Nfl2k5Playbook) -> list[dict[str, Any]]:
    body = raw[insp.RESOURCE_HEADER_SIZE:]
    uses: dict[int, list[Any]] = defaultdict(list)
    for form in book.formations:
        uses[lib.formation_category(body, form.index)].append(form)
    groups = []
    for cat in book.categories:
        codes = lib.category_positions(body, cat.index)
        for kind in (WR, CB):
            slots = [s for s, c in enumerate(codes) if c & 31 == kind]
            if not (kind == WR and len(slots) >= 3 or kind == CB and len(slots) in (3, 4)):
                continue
            forms = uses[cat.index]
            rows = []
            for form in forms:
                record = lib.formation_record(body, form.index)
                xs = {s: record.slots[s].x[0] for s in slots}
                order = sorted(slots, key=lambda s: (abs(xs[s]), s))
                rows.append({"index": form.index, "name": form.name, "x_cm": xs,
                             "inner_slot": order[0], "inner_ordinal": codes[order[0]] >> 5,
                             "inner_gap_yd": (abs(xs[order[1]]) - abs(xs[order[0]])) / codec.YD_CM})
            means = {s: sum(abs(r["x_cm"][s]) for r in rows) / len(rows) for s in slots} if rows else {}
            signed = {s: sum(r["x_cm"][s] for r in rows) / len(rows) for s in slots} if rows else {}
            inner = min(slots, key=lambda s: (means[s], s)) if rows else None
            disagreement = max((abs(r["x_cm"][inner]) - abs(r["x_cm"][r["inner_slot"]]))
                               / codec.YD_CM for r in rows) if rows else 0.0
            reason = ""
            if not rows:
                reason = "unused_group"
            elif kind == WR and not lib.is_offense_category(codes):
                reason = "non_offensive_wr_group"
            elif kind == WR and len(slots) > 5:
                reason = "more_than_five_receivers"
            elif disagreement > DISAGREEMENT_YD:
                reason = "disagreeing_inner_slot"
            new = list(codes)
            if not reason:
                outer = [s for s in slots if s != inner]
                left = [s for s in outer if signed[s] < 0]
                right = [s for s in outer if signed[s] > 0]
                if not left or not right:
                    reason = "no_distinct_outside_left_and_right"
                else:
                    x = min(left, key=lambda s: (-means[s], s))
                    z = min(right, key=lambda s: (-means[s], s))
                    remainder = sorted((s for s in outer if s not in (x, z)), key=lambda s: (-means[s], s))
                    assignment = {x: 0, z: 1, inner: 2 if kind == WR else len(slots) - 1}
                    assignment.update({s: i for i, s in enumerate(remainder, 3 if kind == WR else 2)})
                    for s, ordinal in assignment.items():
                        new[s] = kind | (ordinal << 5)
            for row in rows:
                # Ambiguity is about WR geometry, independent of its name or
                # the assigned ordinal. Dime's two inside CBs still get gated.
                row["bunch_or_tied"] = kind == WR and row["inner_gap_yd"] <= DISAGREEMENT_YD
                row["excluded_reason"] = reason or ("bunch_or_tied" if row["bunch_or_tied"] else "")
            groups.append({"index": cat.index, "name": cat.name, "kind": kind, "slots": slots,
                           "before": codes, "after": new, "inner_slot": inner,
                           "mean_abs_x_yd": {s: means[s] / codec.YD_CM for s in means},
                           "max_disagreement_yd": disagreement, "refused_reason": reason,
                           "disagreeing": len({r["inner_slot"] for r in rows}) > 1,
                           "formations": rows})
    return groups


def role_digest(raw: bytes) -> str:
    """Pin every relevant group's role slots (including unused groups), and x[0].

    Ignore other position codes so the front-seven pass composes in either
    order. Geometry/membership/ordinal edits require an explicit custom pass.
    """
    book = _parse(raw)
    rows = []
    for group in _groups(raw, book):
        rows.append([group["index"], group["kind"],
                     [(s, group["before"][s]) for s in group["slots"]],
                     [(r["index"], list(r["x_cm"].items())) for r in group["formations"]]])
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode("ascii")).hexdigest()


def book_status(raw: bytes) -> str:
    try:
        book = _parse(raw)
        name = book.book_name
        digest = role_digest(raw)
        extra = special.digest(raw, book)
    except (ValidationError, ValueError, struct.error):
        return "foreign"
    if APPLIED_SHA256.get(name) == digest and special.APPLIED_SHA256.get(name) == extra:
        return "applied"
    if digest in (RETAIL_SHA256.get(name), APPLIED_SHA256.get(name)) and special.RETAIL_SHA256.get(name) == extra:
        return "retail"  # also upgrade a known Tier-1-only book
    return "foreign"


def _audit_book(raw: bytes) -> dict[str, Any]:
    book = _parse(raw)
    groups = _groups(raw, book)
    hist = {key: Counter() for key in HISTOGRAMS}
    gate: dict[str, Any] = {"checked": 0, "excluded": 0, "failures": []}
    for group in groups:
        key = "wr" if group["kind"] == WR else "nickel" if len(group["slots"]) == 3 else "dime"
        expected = 3 if key == "dime" else 2
        ordinal_set = sorted(group["before"][s] >> 5 for s in group["slots"])
        for row in group["formations"]:
            hist[f"{key}_inner"][str(row["inner_ordinal"])] += 1
            if key != "wr":
                hist[f"{key}_ordinals"][",".join(map(str, ordinal_set))] += 1
            if row["excluded_reason"]:
                gate["excluded"] += 1
            else:
                gate["checked"] += 1
                if row["inner_ordinal"] != expected or ordinal_set != list(range(len(group["slots"]))):
                    gate["failures"].append({"group": group["index"], "formation": row["index"],
                                             "kind": key, "expected": expected, "actual": row["inner_ordinal"]})
    gate["ok"] = not gate["failures"]
    return {"name": book.book_name, "status": book_status(raw),
            "counts": {"formations": len(book.formations), "plays": len(book.plays), "nodes": book.node_count,
                       "categories": len(book.categories)},
            "histograms": {k: dict(sorted(v.items())) for k, v in hist.items()},
            "groups": groups, "gate": gate, "special": special.plan(raw, book)}


def _archive_resources(archive: Any) -> list[tuple[Any, bytes]]:
    # Discover PLAY entries, including utility/custom books, rather than just
    # the 32 team names. Malformed PLAY entries fail preflight, never disappear.
    resources = [(e, archive.read_entry(e.index)) for e in archive.entries_with_head(b"PLAY")]
    _require(bool(resources), "The archive contains no PLAY books.")
    return resources


def _resources(source: Any) -> dict[str, bytes]:
    if isinstance(source, (bytes, bytearray)):
        return {"book": bytes(source)}
    if isinstance(source, Mapping):
        return dict(source)
    path = Path(source)
    if path.is_dir() and not (path / "0").is_file() and not (path / "vc_53450030").is_dir():
        books = sorted(p for p in path.iterdir() if p.is_file() and p.suffix.upper() == ".PLAY")
        if books:
            return {p.name: p.read_bytes() for p in books}
    if path.is_file() and path.stat().st_size == RESOURCE_SIZE:
        return {path.name: path.read_bytes()}
    with _outer_image().OuterImage(path) as archive:
        return {str(e.index): raw for e, raw in _archive_resources(archive)}


def audit(pack_or_image: Any) -> dict[str, Any]:
    """Audit an image, extracted pack folder, wrapped book, or mapping of books."""
    books = {key: _audit_book(raw) for key, raw in _resources(pack_or_image).items()}
    _require(bool(books), "No books supplied.")
    hist = {key: Counter() for key in HISTOGRAMS}
    counts: Counter = Counter()
    for book in books.values():
        counts.update(book["counts"])
        for key in HISTOGRAMS:
            hist[key].update(book["histograms"][key])
    return {"schema": SCHEMA, "books": books,
            "totals": {"books": len(books), **dict(counts),
                       "histograms": {k: dict(sorted(v.items())) for k, v in hist.items()},
                       "refused_groups": sum(bool(g["refused_reason"]) for b in books.values() for g in b["groups"]),
                       "gate_checked": sum(b["gate"]["checked"] for b in books.values()),
                       "gate_excluded": sum(b["gate"]["excluded"] for b in books.values()),
                       "gate_ok": all(b["gate"]["ok"] and b["special"]["gate"]["ok"] for b in books.values()),
                       "special_classified": dict(sum((Counter(b["special"]["classified"]) for b in books.values()), Counter())),
                       "special_accepted": dict(sum((Counter(b["special"]["accepted"]) for b in books.values()), Counter())),
                       "special_refused_groups": sum(len(b["special"]["refused"]) for b in books.values())}}


def status(pack_or_image: Any) -> dict[str, Any]:
    """Pinned per-book retail/applied/foreign states; mixed archives are foreign."""
    states = {key: book_status(raw) for key, raw in _resources(pack_or_image).items()}
    values = set(states.values())
    state = next(iter(values)) if len(values) == 1 else "foreign"
    return {"status": state, "books": states}


def _validate_plays(raw: bytes, book: insp.Nfl2k5Playbook) -> None:
    body = raw[insp.RESOURCE_HEADER_SIZE:]
    for play in book.plays:
        flags, chains = lib.play_chains(body, play.index)
        for assignment, (_desc, nodes) in zip(play.assignments, chains):
            _require(assignment.chain_start_index + len(nodes) <= book.node_count,
                     f"{book.book_name}: play {play.index} exceeds the node table.")
            _require(all(len(node) == insp.NODE_SIZE and node[0] in codec.OPCODE_NAMES for node in nodes),
                     f"{book.book_name}: play {play.index} has an unknown or truncated opcode.")
        error = codec.validate_play(flags, chains)
        _require(error is None, f"{book.book_name}: play {play.index} fails the retail validator: {error}")


@dataclass(frozen=True)
class NormalisedBook:
    replacement: bytes
    report: dict[str, Any]


def normalise(raw: bytes) -> NormalisedBook:
    """Pure compiler, also for authored books. Apply only accepted assignments.

    A refused SPECIAL assignment can share slots with an accepted core WR rule;
    refusal does not freeze independently owned roles in that personnel group.

    This does not enforce retail pins: the disc-writing API does that unless
    the caller explicitly permits authored/custom role geometry.
    """
    raw = bytes(raw)
    book = _parse(raw)
    _validate_plays(raw, book)
    before = _audit_book(raw)
    changes = {g["index"]: g["after"] for g in before["groups"] if g["before"] != g["after"]}
    for entry in before["special"]["entries"]:
        if entry["refused_reason"] or entry["before"] == entry["after"]:
            continue
        codes = changes.setdefault(entry["group"], lib.category_positions(raw[32:], entry["group"]))
        for slot, code in entry["after"].items():
            codes[slot] = code
    replacement = compile_personnel_categories(raw, changes)
    after_book = _parse(replacement)
    _validate_plays(replacement, after_book)
    after = _audit_book(replacement)
    _require(after["counts"] == before["counts"], "Depth roles changed book counts.")
    _require(after["gate"]["ok"], f"{book.book_name}: depth-role output gate failed: {after['gate']['failures']}")
    _require(after["special"]["gate"]["ok"], f"{book.book_name}: SPECIAL output gate failed: {after['special']['gate']}")
    # High ordinal bits of accepted role slots; only the two punt gunner slots
    # may also change position kind. Everything else stays byte-exact.
    allowed = {insp.RESOURCE_HEADER_SIZE + insp.CATEGORY_BASE + g["index"] * insp.CATEGORY_SIZE + 5 + s
               for g in before["groups"] if not g["refused_reason"] for s in g["slots"]}
    kinds_allowed = set()
    for entry in before["special"]["entries"]:
        if entry["refused_reason"]:
            continue
        offsets = {32 + insp.CATEGORY_BASE + entry["group"] * insp.CATEGORY_SIZE + 5 + s for s in entry["after"]}
        allowed.update(offsets)
        if entry["role"] == "gunners":
            kinds_allowed.update(offsets)
    differences = [i for i, (a, b) in enumerate(zip(raw, replacement)) if a != b]
    _require(len(raw) == len(replacement) and all(i in allowed and (i in kinds_allowed or raw[i] & 31 == replacement[i] & 31) for i in differences),
             "Depth roles changed an unowned byte or position kind.")
    return NormalisedBook(replacement, {
        "name": book.book_name, "before_status": before["status"], "after_status": after["status"],
        "before_sha256": hashlib.sha256(raw).hexdigest(), "after_sha256": hashlib.sha256(replacement).hexdigest(),
        "changed_bytes": len(differences), "changed_resource_offsets": differences,
        "changed_groups": sorted(changes), "counts": after["counts"],
        "before_histograms": before["histograms"], "after_histograms": after["histograms"],
        "refused_groups": [g for g in before["groups"] if g["refused_reason"]],
        "ambiguous_groups": [g for g in before["groups"] if any(r["bunch_or_tied"] for r in g["formations"])],
        "gate": after["gate"], "special": after["special"],
        "before_special": before["special"], "kind_change_offsets": sorted(kinds_allowed),
        "all_plays_validated": len(book.plays),
    })


def apply_to_archive(archive: Any, *, allow_custom: bool = False,
                     progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Preflight every PLAY book before writing; verify and roll back on failure.

    Uses the same open archive interface as apply_packs_to_archive. Only
    changed personnel spans are written, even across an outer-pack seam.
    """
    say = progress or (lambda _message: None)
    planned = []
    for entry, raw in _archive_resources(archive):
        state = book_status(raw)
        _require(allow_custom or state != "foreign",
                 f"PLAY entry {entry.index}: foreign role data; use allow_custom only for intended authored books.")
        result = normalise(raw)
        planned.append((entry, raw, result))
        say(f"Checked depth roles: {result.report['name']} ({result.report['changed_bytes']} bytes)")
    writes = []
    touched = []
    try:
        for entry, raw, result in planned:
            _require(archive.read_entry(entry.index) == raw, f"PLAY entry {entry.index} changed since preflight.")
            for cat in result.report["changed_groups"]:
                offset = insp.RESOURCE_HEADER_SIZE + insp.CATEGORY_BASE + cat * insp.CATEGORY_SIZE + 5
                address = entry.virtual_offset + offset
                original = raw[offset:offset + 11]
                changed = result.replacement[offset:offset + 11]
                touched.append((address, original))  # include an attempted short write
                _require(archive.write(address, changed) == len(changed), f"PLAY entry {entry.index}: short write.")
                writes.append({"entry": entry.index, "group": cat, "virtual_offset": address, "size": len(changed)})
            _require(archive.read_entry(entry.index) == result.replacement,
                     f"PLAY entry {entry.index}: read-back differs.")
    except Exception as exc:
        rollback_errors = []
        for address, original in reversed(touched):
            try:
                _require(archive.write(address, original) == len(original), "short rollback write")
                _require(archive.read(address, len(original)) == original, "rollback read-back differs")
            except Exception as rollback:
                rollback_errors.append(str(rollback))
        if rollback_errors:
            raise DepthRolesError(f"{exc}; rollback failed: {'; '.join(rollback_errors)}; discard this output copy.") from exc
        raise
    books = [{"outer_index": e.index, **r.report} for e, _raw, r in planned]
    return {"schema": SCHEMA, "status": "applied", "allow_custom": allow_custom, "books": books,
            "changed_bytes": sum(b["changed_bytes"] for b in books), "writes": writes,
            "gate_ok": all(b["gate"]["ok"] and b["special"]["gate"]["ok"] for b in books),
            "refused_groups": sum(len(b["refused_groups"]) + len(b["special"]["refused"]) for b in books)}


def apply(image: Path | str, *, allow_custom: bool = False,
          progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Idempotently edit a disc COPY in place. Loose pack folders are read-only."""
    with _outer_image().OuterImage(image, writable=True) as archive:
        return apply_to_archive(archive, allow_custom=allow_custom, progress=progress)
