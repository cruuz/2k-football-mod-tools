"""Last build phase: one core clone batch, then named content edits and readback."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import zlib

from mod_editor.core import apf2k8_book_identity as identity
from mod_editor.core import apf2k8_book_clone as clone
from mod_editor.core.errors import ValidationError
from . import playcalling_service as service


def _outside_hash(path, excluded):
    """Hash every retained byte, streaming even a multi-gigabyte pack."""
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        cursor = 0
        for start, end in sorted(excluded) + [(path.stat().st_size, path.stat().st_size)]:
            if start < cursor or end < start:
                raise ValidationError("CPU book build allocations overlap")
            remaining = start - cursor
            while remaining:
                data = stream.read(min(remaining, 1024 * 1024))
                if not data:
                    raise ValidationError("CPU book build pack was truncated")
                sha.update(data)
                remaining -= len(data)
            stream.seek(end)
            cursor = end
    return sha.hexdigest()


def finalize(index, modification, progress=lambda *_: None, *, backend=None):
    """Only receives the private, already verified build staging directory."""
    events = service.read_profile(modification)
    engine = service.PlayCallingService(backend)
    session = SimpleNamespace(source=SimpleNamespace(index_0a=index), modifications=(), staged_splb_changes=lambda: ())
    original = engine.backend.load(session)
    state = original
    for event in events:
        state, checked = engine.apply(state, event["request"], index)
        if checked != event:
            raise ValidationError("Build inputs changed a reviewed CPU Play Calling edit; review it again")
        if checked["warning"] and engine.backend.lineup_callers != "non_cpu":
            raise ValidationError(checked["warning"])
    assignments = [row for e in events if e["request"]["kind"] == "clones" for row in e["request"]["assignments"]]
    clone_receipt = None
    if assignments:
        progress("Inserting all team books in one archive pass", 0, len(assignments))
        requests = tuple(engine.backend.clone.CloneRequest(r["label_id"], r["team_index"],
                                                           r["donor_name"], r["clone_name"])
                         for r in assignments)
        plan = engine.backend.clone.compile_unlock(index, requests)
        if {c.name for c in plan.clones} != {r["clone_name"] for r in assignments}:
            raise ValidationError("Compiled clone names differ from the reviewed own-book table")
        with tempfile.TemporaryDirectory(prefix=".apf-team-books-", dir=index.parent.parent) as scratch:
            output = Path(scratch) / "clones"
            clone_receipt = engine.backend.clone.build_new_folder(plan, output, lambda text: progress(text, 0, 1))
            for path in output.iterdir():
                os.replace(path, index.parent / path.name)
    # The directory may have been sorted again. Every resource is looked up by
    # filename hash after the insertion, never by a pre-insertion outer index.
    replacements = []
    for name, body in state.books.items():
        if body != original.books.get(name):
            replacements.append((identity.filename_id(name), "spb", "SPLB", body))
    if state.master != original.master:
        replacements.append((zlib.crc32(b"PLAYBOOK_MASTER.IFF"), "mpb", "PLAY", state.master))
    if state.rost != original.rost:
        import apf_roster
        replacements.append((apf_roster.OUTER_NAME_ID, "roster", "ROST", state.rost))
    compiled, excluded = [], {}
    for name_id, inner, type_name, body in replacements:
        source = identity.read_resource(index, name_id, inner, type_name)
        entry_bytes, transport = clone.rebuild_resource(source, body)
        entry = source[1]
        if len(entry_bytes) != entry.size:
            raise ValidationError("CPU book content did not fit its compiled allocation")
        compiled.append((name_id, inner, type_name, body, entry, entry_bytes, transport))
        for segment in entry.segments:
            excluded.setdefault(segment.pack_name, []).append((segment.pack_offset, segment.pack_offset + segment.size))
    before = {pack: _outside_hash(index.parent / pack, spans) for pack, spans in excluded.items()}
    for name_id, inner, type_name, body, entry, entry_bytes, transport in compiled:
        cursor = 0
        for segment in entry.segments:
            with (index.parent / segment.pack_name).open("r+b") as stream:
                stream.seek(segment.pack_offset)
                stream.write(entry_bytes[cursor:cursor + segment.size])
            cursor += segment.size
        if identity.read_resource(index, name_id, inner, type_name)[3] != body:
            raise ValidationError("CPU Play Calling content failed build readback")
    for pack, spans in excluded.items():
        if _outside_hash(index.parent / pack, spans) != before[pack]:
            raise ValidationError("CPU Play Calling changed bytes outside its resource allocations")
    category_names = {row.id: row.name for row in engine.backend.model.category_table(state.master)}
    formation_names = {row["index"]: row["name"] for row in state.inventory.get("formations", ())}
    receipt = {"schema": "apf_playcalling_build/v1", "events": events, "clones": assignments,
               "removed_formations": [{"book": e["request"]["book"], "formation_id": e["request"]["formation"],
                                       "formation_name": formation_names.get(e["request"]["formation"], str(e["request"]["formation"]))}
                                      for e in events if e["request"]["kind"] == "remove"],
               "retired_categories": [{"book": e["request"]["book"], "id": category, "name": category_names[category]}
                                      for e in events for category in e["retired"]],
               "teams_now_own_books": list(dict.fromkeys(r["team_name"] for r in assignments)),
               "clone_verification": clone_receipt, "runtime_status": "UNWITNESSED",
               "verification": {"content_reparsed": True, "outside_content_allocations_identical": True,
                                "resources_resolved_by_name_after_insertion": True},
               "resources": [{"name_id": name_id, "outer_index": entry.table_index,
                              "body_sha256": service.digest(body), "transport": transport}
                             for name_id, _, _, body, entry, _, transport in compiled]}
    (index.parent / "book-content-receipt.json").write_bytes((json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
    return receipt
