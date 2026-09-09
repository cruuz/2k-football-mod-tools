"""Resolve authored intent against the last PLAY output. EXPERIMENTAL / UNWITNESSED.

This reader never writes an image. Names locate moved plays; decoded descriptors
and nodes prove identity independently of their relocated pool pointers. Reports
are compiled again, including the native personnel checks, before being returned.
"""
from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping

from .errors import ValidationError
from . import nfl2k5_play_library as library
from . import nfl2k5_playbook_pack as packs
from .nfl2k5_formation_play_writer import PlayCreateRequest, REPORT_SCHEMA


class PlayIntentError(ValidationError):
    """An authored play cannot be certified in the final book."""


def _require(ok, message):
    if not ok:
        raise PlayIntentError(message)


def intent_requests(resource, report):
    """Decode compiler records, retaining only explicitly authored intent."""
    _require(isinstance(resource, bytes) and isinstance(report, Mapping),
             "Expected exact PLAY bytes and a compiler report")
    asset = report.get("asset_id")
    _require(isinstance(asset, str) and asset.startswith("book:"),
             "Authored intent needs an exact book:<team> asset id")
    _require(report.get("schema") in (REPORT_SCHEMA, packs.FINAL_INTENT_REPORT_SCHEMA),
             f"{asset}: unknown PLAY compiler report schema")
    _require(hashlib.sha256(resource).hexdigest() == report.get("replacement_sha256"),
             f"{asset}: stale retained PLAY resource/report pairing")
    book = packs.parse_playbook_resource(resource, asset_id=asset)
    indices = report.get("new_play_indices")
    _require(isinstance(indices, list) and all(type(pi) is int and 0 <= pi < len(book.plays)
                                             for pi in indices),
             f"{asset}: invalid compiler resolved play indices")
    rows = {}
    for key, schema in (("option_intent", library.OPTION_INTENT_SCHEMA),
                        ("spy_intent", library.SPY_INTENT_SCHEMA)):
        intent = report.get(key)
        _require(isinstance(intent, Mapping) and set(intent) == {"schema", "records"}
                 and intent["schema"] == schema and isinstance(intent["records"], list),
                 f"{asset}: expected versioned {key} compiler records")
        for record in intent["records"]:
            _require(isinstance(record, Mapping), f"{asset}: invalid {key} record")
            pi = record.get("play_index")
            _require(type(pi) is int and 0 <= pi < len(book.plays)
                     and pi in indices,
                     f"{asset}: {key} play index is outside the compiler's resolved plays")
            row = rows.setdefault(pi, dict(option_intent=None, spy_slots=[]))
            label = f"{asset}: play {pi} '{book.plays[pi].name}'"
            if key == "option_intent":
                _require(row["option_intent"] is None, f"{label}: duplicate option intent")
                row["option_intent"] = library.option_intent_from(copy.deepcopy(record.get("intent")))
                _require(row["option_intent"] is not None, f"{label}: missing option intent")
            else:
                slot = record.get("slot")
                _require(type(slot) is int and 0 <= slot < 11 and slot not in row["spy_slots"],
                         f"{label}: invalid or duplicate Spy assignment slot")
                row["spy_slots"].append(slot)
    return [PlayCreateRequest(asset, pi, replace_index=pi,
                              option_intent=row["option_intent"],
                              spy_slots=tuple(sorted(row["spy_slots"])))
            for pi, row in sorted(rows.items())]


def native_compiler_pair(resource, report):
    """Revalidate a final compiler report before using its native fixture view.

The view differs only in verified personnel bytes, never in the book/play
names, flags, assignment descriptors or nodes that either runtime consumes.
Legacy compiler pairs keep their existing validation path.
"""
    if not isinstance(report, Mapping) or report.get("schema") != packs.FINAL_INTENT_REPORT_SCHEMA:
        return resource, report
    requests = intent_requests(resource, report)
    compiled, native = packs.recompile_final_intents(
        resource, requests, native_codes=report.get("native_personnel_codes"))
    _require({k: v for k, v in report.items() if k != "resolution"} == compiled.report,
             f"{report['asset_id']}: final PLAY compiler report changed; resolve again")
    return native.replacement, native.report


def table_compiler_pairs(compilations):
    """Return certified compiler views and a map back to their exact final bytes."""
    pairs, final_hashes = [], {}
    for resource, report in compilations:
        native, checked = native_compiler_pair(resource, report)
        pairs.append((native, checked))
        if not isinstance(checked, Mapping):
            continue  # the existing table compiler supplies its typed refusal
        key = (checked.get("asset_id"), checked.get("replacement_sha256"))
        digest = report.get("replacement_sha256")
        _require(key not in final_hashes or final_hashes[key] == digest,
                 f"{key[0]}: conflicting final PLAY pairs")
        final_hashes[key] = digest
    return pairs, final_hashes


def final_table_receipt(receipt, final_hashes):
    """Table hashes use unchanged scripts; diagnostics name the installed resource."""
    for row in receipt["records"]:
        row["resource_sha256"] = final_hashes[(row.get("asset_id"), row["resource_sha256"])]
    return receipt


def certify_read_identities(pairs, receipt):
    """Prove each pointer-independent runtime fingerprint is unique in its book.

    V5 follows team+0x20, then header+0x60 to the live descriptor. The table's
    offset records the final resource index for display, not a guessed runtime
    enumeration. Check every play, including plays without an authored intent,
    so a duplicate name/script or FNV collision cannot silently select a row.
    """
    import struct
    from . import nfl2k5_read_option_runtime as runtime

    def fingerprint(data):
        value = 0x811C9DC5
        for octet in data:
            value = ((value ^ octet) * 0x01000193) & 0xFFFFFFFF
        return value

    books = {report['asset_id']: resource for resource, report in pairs}
    for row in receipt['records']:
        resource = books[row['asset_id']]
        body = resource[32:]
        book = packs.parse_playbook_resource(resource, asset_id=row['asset_id'])
        _, _, qb_hash, back_hash, name_hash, back, *_ = runtime.RECORD.unpack(bytes.fromhex(row['record']))
        matches = []
        for play in book.plays:
            field = 0x33FC + play.index*96
            start = field + struct.unpack_from('<i', body, field)[0] - 1
            if not 0x10840 <= start <= 0x13390-128 or start % 2:
                continue
            end = next((end for end in range(start, start+126, 2)
                        if body[end:end+2] == b'\0\0'), None)
            if end is None or fingerprint(body[start:end]) != name_hash:
                continue
            _, assignments = library.play_chains(body, play.index)
            if all(len(assignments[slot][1]) == 5 and
                   fingerprint(b''.join(assignments[slot][1])) == expected
                   for slot, expected in ((0, qb_hash), (back, back_hash))):
                matches.append(play.index)
        _require(matches == [row['play_index']],
                 f"{row['asset_id']}: ambiguous loaded read fingerprint at plays {matches}")
        row.update(runtime_identity='loaded team book, name and participant scripts',
                   diagnostic_index=row['play_index'], identity_matches=matches,
                   plays_checked=len(book.plays))
    receipt.update(identity_model='loaded_team_book_fingerprints/v5',
                   diagnostic_index='final_resource_index')
    return receipt


def _resolve_play(before, after, request):
    old = before.plays[request.donor_play_index]
    label = f"{request.asset_id}: play {old.index} '{old.name}'"
    if old.index < len(after.plays) and after.plays[old.index].name == old.name:
        return old.index
    matches = [p.index for p in after.plays if p.name == old.name]
    _require(len(matches) == 1,
             f"{label}: final play name is {'missing or renamed' if not matches else 'ambiguous'}")
    return matches[0]


def resolve_final_pairs(image, retained_pairs, progress=None):
    """Read final books once, certify all retained intents, return one pair per team.

Empty/non-intent compilations produce no pair. Conflicting retained intents,
unknown personnel passes and changed authored assignments refuse before any
table is installed. A same-slot name is authoritative; relocation by name must
be unique. Inputs are never modified, including nested intent dictionaries.
"""
    say = progress or (lambda _message: None)
    grouped = {}
    recode = packs._outer_image()
    for resource, report in retained_pairs:
        requests = intent_requests(resource, report)
        if not requests:
            continue
        team = report["asset_id"][5:]
        _require(team in recode.BOOK_ENTRIES, f"{report['asset_id']}: unknown team book")
        # Prove the retained report with the real compiler before consulting final bytes.
        if report["schema"] == packs.FINAL_INTENT_REPORT_SCHEMA:
            native, _ = native_compiler_pair(resource, report)
        else:
            _, certified = packs.recompile_final_intents(resource, requests)
            native = certified.replacement
        grouped.setdefault(team, []).append((resource, report, requests, native))
    if not grouped:
        return []
    result = []
    with recode.OuterImage(image) as archive:
        for team, retained in sorted(grouped.items()):
            asset = f"book:{team}"
            index = recode.BOOK_ENTRIES[team]
            _require(index < len(archive.entries) and archive.entries[index].size == packs.RESOURCE_SIZE,
                     f"{asset}: final PLAY entry is missing or has the wrong size")
            final = archive.read_entry(index)
            final_book = packs.parse_playbook_resource(final, asset_id=asset)
            requests, identities, resolved = [], set(), []
            native_codes = {}
            for resource, report, old_requests, native in retained:
                before = packs.parse_playbook_resource(resource, asset_id=asset)
                _require(before.book_name == final_book.book_name, f"{asset}: final book name changed")
                for cat in before.categories:
                    codes = library.category_positions(native[32:], cat.index)
                    key = str(cat.index)
                    _require(key not in native_codes or native_codes[key] == codes,
                             f"{asset}: retained reports disagree on native personnel group {cat.index}")
                    native_codes[key] = codes
                for request in old_requests:
                    pi = _resolve_play(before, final_book, request)
                    old_pi = request.donor_play_index
                    name = before.plays[old_pi].name
                    label = f"{asset}: play {old_pi} '{name}' (final slot {pi})"
                    _require(pi not in identities, f"{label}: duplicate retained authored play")
                    identities.add(pi)
                    old_flags, old_chains = library.play_chains(resource[32:], old_pi)
                    flags, chains = library.play_chains(final[32:], pi)
                    _require(flags == old_flags, f"{label}: play flags changed")
                    for slot, ((old_desc, old_nodes), (desc, nodes)) in enumerate(zip(old_chains, chains)):
                        _require(desc == old_desc,
                                 f"{label}: assignment {slot} descriptor changed ({old_desc:#010x} -> {desc:#010x})")
                        _require(nodes == old_nodes, f"{label}: assignment {slot} nodes changed")
                    requests.append(PlayCreateRequest(asset, pi, replace_index=pi,
                                                      option_intent=copy.deepcopy(request.option_intent),
                                                      spy_slots=request.spy_slots))
                    resolved.append(dict(name=name, retained_play_index=old_pi, play_index=pi,
                                         retained_sha256=report["replacement_sha256"],
                                         descriptors_equal=True, nodes_equal=True))
            try:
                compiled, _ = packs.recompile_final_intents(final, requests, native_codes=native_codes)
            except (ValidationError, ValueError) as exc:
                names = ", ".join(f"{r['play_index']} '{r['name']}'" for r in resolved)
                raise PlayIntentError(f"{asset}: plays {names}: final compiler refused: {exc}") from exc
            compiled.report["resolution"] = dict(plays=resolved, retained_pairs=len(retained),
                                                   experimental=True, runtime_witnessed=False)
            result.append((compiled.replacement, compiled.report))
            say(f"Paired {len(resolved)} authored plays with the final {team} book")
    return result


def resolution_receipt(pairs):
    """JSON-safe counts and identity evidence for Build's final pairing step."""
    return dict(schema="nfl2k5_final_play_pairs/v1", resolved_books=len(pairs),
                resolved_plays=sum(len(report["resolution"]["plays"]) for _, report in pairs),
                books=[dict(asset_id=report["asset_id"], resource_sha256=report["replacement_sha256"],
                            **report["resolution"]) for _, report in pairs],
                experimental=True, runtime_witnessed=False)
