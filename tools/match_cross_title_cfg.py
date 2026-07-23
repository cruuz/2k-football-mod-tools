#!/usr/bin/env python3
"""Cross-ISA function matching for NFL 2K5 (x86) and APF 2K8 (PPC).

The automatic half of this tool only produces candidates.  It deliberately
does not treat a score as proof of lineage.  A small, explicit audit table at
the bottom records pairs whose pseudo-C was compared manually; those records
are emitted separately from the machine-ranked candidates.

The fingerprint avoids opcodes and binary bytes.  It combines:

* normalized structured-control tokens (an approximation of CFG shape),
* architecture-independent constants and C operators,
* function/caller/callee degree buckets and one-hop degree histograms,
* pseudo-C statement/call counts, and
* a bounded neighborhood around the independently established string anchor.

This is intended to survive x86/PPC instruction selection, PowerPC fixed-width
code, endian-dependent packed-field shifts, and moderate source evolution.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable


NFL_ROOT = Path("research/functions/nfl2k5")
APF_ROOT = Path("research/functions/apf2k8")

HEX_OR_DECIMAL_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:0x[0-9a-fA-F]+|[0-9]+)(?:[uUlL]+)?(?![A-Za-z0-9_])"
)
COMMENT_RE = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)
STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
CALL_RE = re.compile(
    r"\b(?:FUN_|Function_|thunk_FUN_)[0-9A-Fa-f]+\s*\(|\(\s*\*[^;\n]*?\)\s*\("
)
CONTROL_RE = re.compile(
    r"\b(?:else\s+if|if|else|switch|case|default|for|while|do|goto|return|break|continue)\b"
)
OPERATOR_RE = re.compile(r">>|<<|==|!=|<=|>=|&&|\|\||[&|^%*/<>+-]")


@dataclass
class Function:
    title: str
    index: int
    address: str
    name: str
    size: int
    classification: str
    caller_count: int
    callers: tuple[str, ...]
    callee_count: int
    callees: tuple[str, ...]
    pseudo_path: str
    pseudo: str


@dataclass
class Fingerprint:
    address: str
    control_tokens: tuple[str, ...]
    control_counts: Counter[str]
    constants: Counter[int]
    operators: Counter[str]
    statement_count: int
    source_line_count: int
    call_site_count: int
    unique_callee_count: int
    self_degree: tuple[int, int]
    caller_degree_histogram: Counter[str]
    callee_degree_histogram: Counter[str]
    digest: str


def parse_address_list(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item).upper().replace("X", "x") for item in value)
    result: list[str] = []
    for item in str(value or "").split(";"):
        address, separator, _name = item.partition(":")
        if separator and address:
            result.append(address.upper().replace("X", "x"))
    return tuple(result)


def canonical_address(value: str) -> str:
    return f"0x{int(value, 16):08X}"


def parse_nfl_chunks(root: Path) -> dict[str, str]:
    chunks: dict[str, str] = {}
    start_re = re.compile(r"(?m)^/\*\n \* index: \d+\n \* address: (0x[0-9A-Fa-f]+)\n")
    for path in sorted((root / "pseudo_c").glob("*.c")):
        text = path.read_text(encoding="utf-8", errors="replace")
        matches = list(start_re.finditer(text))
        for position, match in enumerate(matches):
            end = matches[position + 1].start() if position + 1 < len(matches) else len(text)
            chunks[canonical_address(match.group(1))] = text[match.start():end].rstrip()
    return chunks


def parse_apf_chunks(root: Path) -> dict[str, str]:
    chunks: dict[str, str] = {}
    start_re = re.compile(r"(?m)^/\* APF2K8_FUNCTION (0x[0-9A-Fa-f]+)\n")
    for path in sorted((root / "pseudo_c").glob("*.c")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in start_re.finditer(text):
            address = canonical_address(match.group(1))
            marker = f"/* APF2K8_END_FUNCTION {address} */"
            end = text.find(marker, match.end())
            if end < 0:
                raise ValueError(f"missing APF end marker for {address} in {path}")
            chunks[address] = text[match.start():end + len(marker)]
    return chunks


def load_nfl(path: Path, root: Path) -> list[Function]:
    chunks = parse_nfl_chunks(root)
    result: list[Function] = []
    with path.open("r", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if row["external"] == "true" or row["game_code_candidate"] != "true":
                continue
            address = canonical_address(row["address"])
            result.append(
                Function(
                    title="nfl2k5",
                    index=int(row["index"]),
                    address=address,
                    name=row["name"],
                    size=int(row["size"]),
                    classification=row["classification"],
                    caller_count=int(row["caller_count"]),
                    callers=parse_address_list(row["callers"]),
                    callee_count=int(row["callee_count"]),
                    callees=parse_address_list(row["callees"]),
                    pseudo_path=row["pseudo_c_file"],
                    pseudo=chunks.get(address, ""),
                )
            )
    return result


def load_apf(directory: Path, root: Path) -> list[Function]:
    chunks = parse_apf_chunks(root)
    result: list[Function] = []
    for path in sorted(directory.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if row["classification"] in ("import", "helper"):
                    continue
                if str(row["decompile_status"]).startswith("error"):
                    continue
                address = canonical_address(row["address"])
                result.append(
                    Function(
                        title="apf2k8",
                        index=int(row["index"]),
                        address=address,
                        name=row["name"],
                        size=int(row["size"]),
                        classification=row["classification"],
                        caller_count=int(row["caller_count"]),
                        callers=parse_address_list(row["callers"]),
                        callee_count=int(row["callee_count"]),
                        callees=parse_address_list(row["callees"]),
                        pseudo_path=row["pseudo_c_shard"],
                        pseudo=chunks.get(address, ""),
                    )
                )
    return result


def clean_pseudo(text: str) -> str:
    text = COMMENT_RE.sub(" ", text)
    return STRING_RE.sub(" STR ", text)


def normalize_control_token(value: str) -> str:
    value = " ".join(value.split())
    return "elif" if value == "else if" else value


def parse_integer(value: str) -> int:
    value = re.sub(r"[uUlL]+$", "", value)
    return int(value, 16 if value.lower().startswith("0x") else 10)


def constant_is_architecture_neutral(value: int) -> bool:
    # Pointers and absolute image addresses are excluded.  32-bit all-ones and
    # sign-extension masks are also compiler artifacts, not semantic anchors.
    if value > 0x00FFFFFF:
        return False
    if value in (0, 1, 0xFF, 0xFFFF):
        return False
    return True


def degree_bucket(value: int) -> int:
    return min(7, int(math.log2(value + 1)))


def neighbor_histogram(
    addresses: Iterable[str], lookup: dict[str, Function]
) -> Counter[str]:
    result: Counter[str] = Counter()
    for address in addresses:
        try:
            normalized = canonical_address(address)
        except ValueError:
            result["external"] += 1
            continue
        neighbor = lookup.get(normalized)
        if neighbor is None:
            result["unknown"] += 1
        else:
            result[
                f"{degree_bucket(neighbor.caller_count)}:{degree_bucket(neighbor.callee_count)}"
            ] += 1
    return result


def make_fingerprint(function: Function, lookup: dict[str, Function]) -> Fingerprint:
    clean = clean_pseudo(function.pseudo)
    controls = tuple(normalize_control_token(match.group(0)) for match in CONTROL_RE.finditer(clean))
    constants: Counter[int] = Counter()
    for match in HEX_OR_DECIMAL_RE.finditer(clean):
        value = parse_integer(match.group(0))
        if constant_is_architecture_neutral(value):
            constants[value] += 1
    operators = Counter(match.group(0) for match in OPERATOR_RE.finditer(clean))
    lines = [line.strip() for line in clean.splitlines() if line.strip()]
    statement_count = clean.count(";")
    call_site_count = len(CALL_RE.findall(clean))
    payload = {
        "control": controls,
        "control_counts": sorted(Counter(controls).items()),
        "constants": sorted(constants.items()),
        "operators": sorted(operators.items()),
        "statements": statement_count,
        "calls": call_site_count,
        "degree": [degree_bucket(function.caller_count), degree_bucket(function.callee_count)],
    }
    digest = hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]
    return Fingerprint(
        address=function.address,
        control_tokens=controls,
        control_counts=Counter(controls),
        constants=constants,
        operators=operators,
        statement_count=statement_count,
        source_line_count=len(lines),
        call_site_count=call_site_count,
        unique_callee_count=function.callee_count,
        self_degree=(function.caller_count, function.callee_count),
        caller_degree_histogram=neighbor_histogram(function.callers, lookup),
        callee_degree_histogram=neighbor_histogram(function.callees, lookup),
        digest=digest,
    )


def multiset_jaccard(left: Counter[object], right: Counter[object]) -> float:
    keys = set(left) | set(right)
    if not keys:
        return 1.0
    intersection = sum(min(left[key], right[key]) for key in keys)
    union = sum(max(left[key], right[key]) for key in keys)
    return intersection / union


def ratio_similarity(left: int, right: int) -> float:
    if left == right == 0:
        return 1.0
    return min(left, right) / max(1, max(left, right))


def degree_similarity(left: int, right: int) -> float:
    return 1.0 / (1.0 + abs(degree_bucket(left) - degree_bucket(right)))


def weighted_constant_similarity(
    left: Counter[int],
    right: Counter[int],
    nfl_frequency: Counter[int],
    apf_frequency: Counter[int],
) -> tuple[float, list[int], list[int]]:
    shared = sorted(set(left) & set(right))
    if not shared:
        return 0.0, [], []
    weighted_shared = 0.0
    weighted_union = 0.0
    union = set(left) | set(right)
    for value in union:
        # Cross-title inverse document frequency; constants recurring in many
        # functions contribute little, exact masks such as 0x2c66 contribute a lot.
        weight = 1.0 / math.sqrt(
            max(1, nfl_frequency.get(value, 0)) * max(1, apf_frequency.get(value, 0))
        )
        weighted_union += weight
        if value in left and value in right:
            weighted_shared += weight
    rare = [
        value
        for value in shared
        if nfl_frequency[value] <= 8 and apf_frequency[value] <= 8
    ]
    return weighted_shared / weighted_union, shared, rare


def score_pair(
    left: Function,
    right: Function,
    left_fp: Fingerprint,
    right_fp: Fingerprint,
    nfl_frequency: Counter[int],
    apf_frequency: Counter[int],
) -> dict[str, object]:
    control_sequence = SequenceMatcher(
        None, left_fp.control_tokens, right_fp.control_tokens, autojunk=False
    ).ratio()
    control_multiset = multiset_jaccard(left_fp.control_counts, right_fp.control_counts)
    constant_score, shared_constants, rare_constants = weighted_constant_similarity(
        left_fp.constants, right_fp.constants, nfl_frequency, apf_frequency
    )
    operator_score = multiset_jaccard(left_fp.operators, right_fp.operators)
    statement_score = ratio_similarity(left_fp.statement_count, right_fp.statement_count)
    call_site_score = ratio_similarity(left_fp.call_site_count, right_fp.call_site_count)
    caller_degree_score = degree_similarity(left.caller_count, right.caller_count)
    callee_degree_score = degree_similarity(left.callee_count, right.callee_count)
    caller_neighborhood_score = multiset_jaccard(
        left_fp.caller_degree_histogram, right_fp.caller_degree_histogram
    )
    callee_neighborhood_score = multiset_jaccard(
        left_fp.callee_degree_histogram, right_fp.callee_degree_histogram
    )
    components = {
        "control_sequence": control_sequence,
        "control_multiset": control_multiset,
        "weighted_constants": constant_score,
        "operators": operator_score,
        "statements": statement_score,
        "call_sites": call_site_score,
        "caller_degree": caller_degree_score,
        "callee_degree": callee_degree_score,
        "caller_neighborhood": caller_neighborhood_score,
        "callee_neighborhood": callee_neighborhood_score,
    }
    # CFG and rare semantic constants dominate.  Degree evidence is deliberately
    # light because indirect PPC calls and function pointers depress Ghidra counts.
    score = (
        0.25 * control_sequence
        + 0.13 * control_multiset
        + 0.22 * constant_score
        + 0.08 * operator_score
        + 0.08 * statement_score
        + 0.06 * call_site_score
        + 0.04 * caller_degree_score
        + 0.04 * callee_degree_score
        + 0.05 * caller_neighborhood_score
        + 0.05 * callee_neighborhood_score
    )
    return {
        "score": round(score, 6),
        "components": {key: round(value, 6) for key, value in components.items()},
        "shared_constants": [f"0x{value:X}" for value in shared_constants],
        "rare_shared_constants": [f"0x{value:X}" for value in rare_constants],
    }


def control_bucket(fp: Fingerprint) -> tuple[int, ...]:
    names = ("if", "elif", "else", "switch", "case", "default", "for", "while", "do", "goto", "return")
    return tuple(fp.control_counts.get(name, 0) for name in names)


def function_frequency(fingerprints: Iterable[Fingerprint]) -> Counter[int]:
    result: Counter[int] = Counter()
    for fingerprint in fingerprints:
        result.update(fingerprint.constants.keys())
    return result


def corpus_digest(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        digest.update(path.as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def automatic_candidate_pairs(
    nfl: list[Function],
    apf: list[Function],
    nfl_fp: dict[str, Fingerprint],
    apf_fp: dict[str, Fingerprint],
    nfl_frequency: Counter[int],
    apf_frequency: Counter[int],
) -> dict[tuple[str, str], set[str]]:
    candidates: dict[tuple[str, str], set[str]] = defaultdict(set)

    nfl_by_constant: dict[int, list[str]] = defaultdict(list)
    apf_by_constant: dict[int, list[str]] = defaultdict(list)
    for function in nfl:
        for value in nfl_fp[function.address].constants:
            nfl_by_constant[value].append(function.address)
    for function in apf:
        for value in apf_fp[function.address].constants:
            apf_by_constant[value].append(function.address)
    for value in sorted(set(nfl_by_constant) & set(apf_by_constant)):
        if len(nfl_by_constant[value]) > 8 or len(apf_by_constant[value]) > 8:
            continue
        for left in nfl_by_constant[value]:
            for right in apf_by_constant[value]:
                candidates[(left, right)].add(f"rare_constant:0x{value:X}")

    nfl_by_cfg: dict[tuple[int, ...], list[str]] = defaultdict(list)
    apf_by_cfg: dict[tuple[int, ...], list[str]] = defaultdict(list)
    for function in nfl:
        fp = nfl_fp[function.address]
        if len(fp.control_tokens) >= 4:
            nfl_by_cfg[control_bucket(fp)].append(function.address)
    for function in apf:
        fp = apf_fp[function.address]
        if len(fp.control_tokens) >= 4:
            apf_by_cfg[control_bucket(fp)].append(function.address)
    for bucket in sorted(set(nfl_by_cfg) & set(apf_by_cfg)):
        if len(nfl_by_cfg[bucket]) > 20 or len(apf_by_cfg[bucket]) > 20:
            continue
        for left in nfl_by_cfg[bucket]:
            for right in apf_by_cfg[bucket]:
                candidates[(left, right)].add("exact_control_multiset")

    # The only seed is the independently established two-string match.  Every
    # cross product in this bounded window is scored; no address-offset formula
    # or expected pair list participates in automatic ranking.
    nfl_anchor_index = next(item.index for item in nfl if item.address == "0x000BB8D0")
    apf_anchor_index = next(item.index for item in apf if item.address == "0x848A4DB8")
    nfl_window = [item for item in nfl if nfl_anchor_index - 2 <= item.index <= nfl_anchor_index + 25]
    apf_window = [item for item in apf if apf_anchor_index - 2 <= item.index <= apf_anchor_index + 25]
    for left in nfl_window:
        for right in apf_window:
            candidates[(left.address, right.address)].add("confirmed_anchor_neighborhood")

    return candidates


# Manually reviewed pseudo-C pairs.  This table is an audit annotation, never an
# input to candidate generation or scoring.  The first row is the pre-existing
# calibration anchor; all remaining one-to-one rows are additional findings.
MANUAL_CONFIRMED: tuple[tuple[str, str, str, str], ...] = (
    (
        "0x000BB8D0", "0x848A4DB8", "calibration_anchor",
        "same 1/2, 3-6, 7/8 switch partition and four-result side-label table; packed-field extraction changes from low five bits to high five bits",
    ),
    (
        "0x000BB830", "0x848A4CD8", "additional",
        "same type 2/3/4 field decode, negative sentinel, per-type subfield decode, one helper transform, and indexed side-label return",
    ),
    (
        "0x000BBA60", "0x848A5068", "additional",
        "same nonzero tagged roster ID to one of two base arrays, ((id-2)>>1)*stride arithmetic; player stride evolves from 0x54 to 0x14c",
    ),
    (
        "0x000BBAA0", "0x848A50D8", "additional",
        "inverse roster pointer-to-tagged-ID mapping using the same two bases, parity encoding, +2 bias, and title-specific 0x54/0x14c stride",
    ),
    (
        "0x000BBB00", "0x848A51A8", "additional",
        "same fallback between byte fields at +0xd/+0xc, call to roster-ID mapper, then packed team-side test; packed field moves from +0x34 byte to +0x10 bits",
    ),
    (
        "0x000BBB80", "0x848A5250", "additional",
        "same current-record lookup, exact 0x2c66 type mask, 3-bit range 1..4, type-5 exception, and subtraction of byte at word index 4 or 1",
    ),
    (
        "0x000BBBD0", "0x848A52F8", "additional",
        "same current-record decode, exact 0x3820 type mask, decoded pair, threshold 10, descriptor assembly, and formatter call",
    ),
    (
        "0x000BBC70", "0x848A53D8", "additional",
        "same expanded current-record formatting path with exact 0x3820 type mask, three decoded values, nested thresholds, descriptor selection, and formatter call",
    ),
    (
        "0x000BBD50", "0x848A5540", "additional",
        "same context decode plus current-record lookup and 7-bit packed-field extraction; bit position changes with packed layout/endian ABI",
    ),
    (
        "0x000BBD80", "0x848A5578", "additional",
        "same context decode with one decoded value decremented, current-record lookup, and the same 7-bit field extraction",
    ),
    (
        "0x000BBDB0", "0x848A55B8", "additional",
        "same signed index modulo 128 into a packed-record table and 13-bit field extraction; PPC decompiler expands signed-remainder normalization",
    ),
    (
        "0x000BBDD0", "0x848A55E8", "additional",
        "same cached-index special case, otherwise index+1 modulo 128, followed by the same 13-bit packed-field extraction",
    ),
    (
        "0x000BBE00", "0x848A5630", "additional",
        "same modulo-128 packed-record lookup, one-bit flag test, and selection between two static results; flag bit position changes with packing",
    ),
    (
        "0x000BBE30", "0x848A5678", "additional",
        "same modulo-128 packed-record lookup returning a one-bit field; shift changes from 0x15 to 10 with packed-field layout",
    ),
    (
        "0x000BBE50", "0x848A56A8", "additional",
        "same modulo-128 packed-record lookup returning the low stored byte as a floating value",
    ),
    (
        "0x000BBE80", "0x848A56E0", "additional",
        "same modulo-128 packed-record lookup returning a four-bit field; shift changes from 0x16 to 6",
    ),
    (
        "0x000BBEA0", "0x848A5710", "additional",
        "same modulo-128 packed-record lookup returning a three-bit field; shift changes from 0x1a to 3",
    ),
    (
        "0x000BBEC0", "0x848A5740", "additional",
        "same modulo-128 packed-record lookup returning the terminal three-bit field; x86 high bits become PPC low bits",
    ),
    (
        "0x000BBEE0", "0x848A5770", "additional",
        "same range start/end derivation, packed eligibility test, forward scan through current records, per-record flag rejection, and -1 sentinel",
    ),
    (
        "0x001EC750", "0x84960538", "additional",
        "same three-way integer bucket: values below -11 map to 0, -11 through 10 map to 1, and values above 10 map to 2; also the respective sole helper called by the matched 0x000BB830/0x848A4CD8 pair",
    ),
    (
        "0x001EC770", "0x84960588", "additional",
        "exact semantic switch preserved across ISAs: default->0, 3/4->1, 5/6->2, and 7/8->3",
    ),
    (
        "0x001163C0", "0x84969FF0", "additional",
        "same global-state base helper followed by table[param*12] load at exact offset 0x3908; normalized pseudo-C expressions are equivalent",
    ),
    (
        "0x00116480", "0x8496A170", "additional",
        "same global-state base helper followed by table[param*12] load at exact offset 0x3910; normalized pseudo-C expressions are equivalent",
    ),
)


AMBIGUOUS_FAMILIES: tuple[dict[str, object], ...] = (
    {
        "nfl_addresses": ["0x000BBFB0", "0x000BBFE0"],
        "apf_addresses": ["0x848A59B8", "0x848A5A18"],
        "status": "manual_family_match_not_one_to_one",
        "evidence": (
            "both titles contain two equivalent wrappers: call the forward-scan helper, "
            "range-check against the cached end, fetch the current record, negate a byte, "
            "otherwise return zero; duplicate bodies make a unique pairing unjustified"
        ),
    },
)


def function_record(function: Function, fp: Fingerprint) -> dict[str, object]:
    return {
        "address": function.address,
        "index": function.index,
        "name": function.name,
        "size": function.size,
        "classification": function.classification,
        "pseudo_c": function.pseudo_path,
        "caller_count": function.caller_count,
        "callee_count": function.callee_count,
        "fingerprint": {
            "digest": fp.digest,
            "control_tokens": list(fp.control_tokens),
            "control_counts": dict(sorted(fp.control_counts.items())),
            "constants": {f"0x{key:X}": value for key, value in sorted(fp.constants.items())},
            "statement_count": fp.statement_count,
            "source_line_count": fp.source_line_count,
            "call_site_count": fp.call_site_count,
            "caller_degree_histogram": dict(sorted(fp.caller_degree_histogram.items())),
            "callee_degree_histogram": dict(sorted(fp.callee_degree_histogram.items())),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nfl", type=Path, default=NFL_ROOT / "functions.tsv")
    parser.add_argument("--nfl-root", type=Path, default=NFL_ROOT)
    parser.add_argument("--apf-ledger", type=Path, default=APF_ROOT / "ledger")
    parser.add_argument("--apf-root", type=Path, default=APF_ROOT)
    parser.add_argument("--json", type=Path, default=Path("reports/cross_title/cfg_candidates.json"))
    parser.add_argument("--tsv", type=Path, default=Path("reports/cross_title/cfg_candidates.tsv"))
    parser.add_argument("--limit", type=int, default=256)
    args = parser.parse_args()

    nfl = load_nfl(args.nfl, args.nfl_root)
    apf = load_apf(args.apf_ledger, args.apf_root)
    nfl_lookup = {item.address: item for item in nfl}
    apf_lookup = {item.address: item for item in apf}
    missing_nfl = [item.address for item in nfl if not item.pseudo]
    missing_apf = [item.address for item in apf if not item.pseudo]
    if missing_nfl or missing_apf:
        raise ValueError(
            f"missing pseudo-C chunks: nfl={missing_nfl[:4]} apf={missing_apf[:4]}"
        )

    nfl_fp = {item.address: make_fingerprint(item, nfl_lookup) for item in nfl}
    apf_fp = {item.address: make_fingerprint(item, apf_lookup) for item in apf}
    nfl_frequency = function_frequency(nfl_fp.values())
    apf_frequency = function_frequency(apf_fp.values())

    sources = automatic_candidate_pairs(
        nfl, apf, nfl_fp, apf_fp, nfl_frequency, apf_frequency
    )
    machine_records: list[dict[str, object]] = []
    for (nfl_address, apf_address), pair_sources in sources.items():
        left = nfl_lookup[nfl_address]
        right = apf_lookup[apf_address]
        score = score_pair(
            left, right, nfl_fp[nfl_address], apf_fp[apf_address],
            nfl_frequency, apf_frequency,
        )
        if float(score["score"]) < 0.48:
            continue
        machine_records.append(
            {
                "status": "candidate_unreviewed",
                **score,
                "candidate_sources": sorted(pair_sources),
                "nfl": function_record(left, nfl_fp[nfl_address]),
                "apf": function_record(right, apf_fp[apf_address]),
                "warning": "machine-ranked cross-ISA candidate; not proof of common source or byte identity",
            }
        )
    machine_records.sort(
        key=lambda row: (
            -float(row["score"]),
            str(row["nfl"]["address"]),
            str(row["apf"]["address"]),
        )
    )
    machine_candidates_above_threshold = len(machine_records)
    machine_records = machine_records[: args.limit]
    rank_lookup = {
        (str(row["nfl"]["address"]), str(row["apf"]["address"])): index + 1
        for index, row in enumerate(machine_records)
    }

    confirmed: list[dict[str, object]] = []
    for nfl_address, apf_address, finding_kind, evidence in MANUAL_CONFIRMED:
        left = nfl_lookup[nfl_address]
        right = apf_lookup[apf_address]
        confirmed.append(
            {
                "status": "manual_semantic_match",
                "finding_kind": finding_kind,
                "confidence": "strong",
                "nfl": function_record(left, nfl_fp[nfl_address]),
                "apf": function_record(right, apf_fp[apf_address]),
                "automatic_score": score_pair(
                    left, right, nfl_fp[nfl_address], apf_fp[apf_address],
                    nfl_frequency, apf_frequency,
                ),
                "automatic_top_rank": rank_lookup.get((nfl_address, apf_address)),
                "manual_evidence": evidence,
                "claim_boundary": (
                    "semantic/common-source homology supported by pseudo-C behavior and local "
                    "ordering; not a byte-identical-body claim and not yet a source-perfect match"
                ),
            }
        )

    candidate_source_counts = Counter(
        source.split(":", 1)[0]
        for pair_sources in sources.values()
        for source in pair_sources
    )
    confirmed_address_pairs = {(left, right) for left, right, _kind, _evidence in MANUAL_CONFIRMED}
    confirmed_generated = sum(pair in sources for pair in confirmed_address_pairs)
    confirmed_above_threshold = sum(
        pair in sources
        and float(
            score_pair(
                nfl_lookup[pair[0]], apf_lookup[pair[1]],
                nfl_fp[pair[0]], apf_fp[pair[1]], nfl_frequency, apf_frequency,
            )["score"]
        ) >= 0.48
        for pair in confirmed_address_pairs
    )
    result = {
        "schema": "vc_cross_title_cfg_candidates/v2",
        "inputs": {
            "nfl_functions_tsv_sha256": corpus_digest([args.nfl]),
            "nfl_pseudo_c_corpus_sha256": corpus_digest(
                (args.nfl_root / "pseudo_c").glob("*.c")
            ),
            "apf_ledger_corpus_sha256": corpus_digest(args.apf_ledger.glob("*.jsonl")),
            "apf_pseudo_c_corpus_sha256": corpus_digest(
                (args.apf_root / "pseudo_c").glob("*.c")
            ),
        },
        "method": {
            "candidate_generation": (
                "rare shared semantic constants, non-generic exact structured-control multisets, "
                "and an address-independent bounded neighborhood around the separately confirmed "
                "two-string anchor"
            ),
            "ranking": (
                "normalized control-token sequence/multiset, IDF-weighted constants, C operators, "
                "statement and call-site ratios, degree buckets, and one-hop degree histograms"
            ),
            "architecture_exclusions": (
                "no opcode bytes, absolute pointers, relocation addresses, or raw binary-size equality; "
                "large constants and common sign-extension masks are excluded"
            ),
            "confirmation_policy": (
                "automatic scores remain candidates; only explicit side-by-side pseudo-C review "
                "appears in manual_confirmed_pairs"
            ),
        },
        "summary": {
            "nfl_functions_fingerprinted": len(nfl),
            "apf_functions_fingerprinted": len(apf),
            "candidate_pairs_before_threshold": len(sources),
            "candidate_source_memberships": dict(sorted(candidate_source_counts.items())),
            "threshold": 0.48,
            "candidate_limit": args.limit,
            "machine_candidates_above_threshold": machine_candidates_above_threshold,
            "machine_candidates_emitted": len(machine_records),
            "manual_confirmed_pairs": len(confirmed),
            "manual_additional_pairs": sum(
                row[2] == "additional" for row in MANUAL_CONFIRMED
            ),
            "ambiguous_manual_families": len(AMBIGUOUS_FAMILIES),
            "manual_pairs_reached_by_candidate_generation": confirmed_generated,
            "manual_pairs_generated_and_above_threshold": confirmed_above_threshold,
        },
        "manual_confirmed_pairs": confirmed,
        "manual_ambiguous_families": list(AMBIGUOUS_FAMILIES),
        "machine_candidates": machine_records,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    fields = [
        "status", "finding_kind", "confidence", "score", "rank",
        "nfl_address", "nfl_index", "nfl_name", "nfl_size", "nfl_fingerprint",
        "apf_address", "apf_index", "apf_name", "apf_size", "apf_fingerprint",
        "candidate_sources", "shared_constants", "rare_shared_constants", "evidence",
        "claim_boundary",
    ]
    args.tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.tsv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t")
        writer.writeheader()
        for row in confirmed:
            writer.writerow(
                {
                    "status": row["status"],
                    "finding_kind": row["finding_kind"],
                    "confidence": row["confidence"],
                    "score": row["automatic_score"]["score"],
                    "rank": row["automatic_top_rank"] or "",
                    "nfl_address": row["nfl"]["address"],
                    "nfl_index": row["nfl"]["index"],
                    "nfl_name": row["nfl"]["name"],
                    "nfl_size": row["nfl"]["size"],
                    "nfl_fingerprint": row["nfl"]["fingerprint"]["digest"],
                    "apf_address": row["apf"]["address"],
                    "apf_index": row["apf"]["index"],
                    "apf_name": row["apf"]["name"],
                    "apf_size": row["apf"]["size"],
                    "apf_fingerprint": row["apf"]["fingerprint"]["digest"],
                    "candidate_sources": "manual_audit",
                    "shared_constants": json.dumps(row["automatic_score"]["shared_constants"]),
                    "rare_shared_constants": json.dumps(row["automatic_score"]["rare_shared_constants"]),
                    "evidence": row["manual_evidence"],
                    "claim_boundary": row["claim_boundary"],
                }
            )
        for rank, row in enumerate(machine_records, 1):
            writer.writerow(
                {
                    "status": row["status"],
                    "score": row["score"],
                    "rank": rank,
                    "nfl_address": row["nfl"]["address"],
                    "nfl_index": row["nfl"]["index"],
                    "nfl_name": row["nfl"]["name"],
                    "nfl_size": row["nfl"]["size"],
                    "nfl_fingerprint": row["nfl"]["fingerprint"]["digest"],
                    "apf_address": row["apf"]["address"],
                    "apf_index": row["apf"]["index"],
                    "apf_name": row["apf"]["name"],
                    "apf_size": row["apf"]["size"],
                    "apf_fingerprint": row["apf"]["fingerprint"]["digest"],
                    "candidate_sources": json.dumps(row["candidate_sources"]),
                    "shared_constants": json.dumps(row["shared_constants"]),
                    "rare_shared_constants": json.dumps(row["rare_shared_constants"]),
                    "evidence": row["warning"],
                    "claim_boundary": "candidate only",
                }
            )

    print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
