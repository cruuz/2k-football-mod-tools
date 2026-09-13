"""Model edit extension of StudioSession, kept in the Models owner boundary.

The base archive is validated by its existing reader. This extension adds one
bounded, hashed member containing sparse changes and the Models check receipts.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

from . import nfl2k5_model_project as P
from . import nfl2k5_models as M
from mod_editor.studio.session import StudioSession, _SessionUndo, _replace_atomic, BACKEND_SCHEMA
from mod_editor.studio import project_archive as archive

MEMBER = "model-edits.json"


def _copy_archive(source, target, document, model_payload=None):
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as new:
        for info in old.infolist():
            if info.filename in {"project.json", MEMBER}:
                continue
            with old.open(info) as src, new.open(archive._zip_info(info.filename), "w", force_zip64=True) as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
        new.writestr(archive._zip_info("project.json"), P.canonical(document))
        if model_payload is not None:
            new.writestr(archive._zip_info(MEMBER), model_payload)
    with open(target, "rb") as stream:
        os.fsync(stream.fileno())


def _read_models(path):
    with zipfile.ZipFile(path) as zipped:
        infos = zipped.infolist()
        P.require(len(infos) <= archive.MAX_PROJECT_MEMBERS + 1
                  and len({i.filename for i in infos}) == len(infos), "Invalid project archive member count or duplicates.")
        P.require(sum(i.file_size for i in infos) <= archive.MAX_PROJECT_EXPANDED_BYTES + P.MAX_BYTES,
                  "Project archive exceeds the expanded size limit.")
        info = zipped.getinfo("project.json")
        P.require(info.file_size <= archive.MAX_MANIFEST_BYTES, "Project manifest is too large.")
        document = json.loads(zipped.read(info), object_pairs_hook=archive._reject_duplicate_json_pairs)
        metadata = document.pop("model_edits", None)
        if metadata is None:
            return document, []
        P.require(isinstance(metadata, dict) and set(metadata) == {"file", "size", "sha256", "count"}
                  and metadata["file"] == MEMBER and type(metadata["count"]) is int
                  and 1 <= metadata["count"] <= 1000, "Malformed model project metadata.")
        info = zipped.getinfo(MEMBER)
        P.require(info.file_size == metadata["size"] and 0 < info.file_size <= P.MAX_BYTES,
                  "Model project payload is too large or its size changed.")
        payload = zipped.read(info)
        P.require(P.sha(payload) == metadata["sha256"], "Saved compiled model changes failed their hash check.")
        rows = json.loads(payload, object_pairs_hook=archive._reject_duplicate_json_pairs)
        P.require(isinstance(rows, list) and len(rows) == metadata["count"], "Model project count changed.")
        for row in rows:
            P.validate_record(row)
        P.require(len({r["target"] for r in rows}) == len(rows), "Project repeats a model set.")
        # An intentional model-only archive becomes a valid empty base archive.
        if not any(value for key, value in document.items() if key not in
                   {"schema", "game", "payload_policy", "empty_project"}):
            document["empty_project"] = True
        return document, rows


class ModelProjectSession(StudioSession):
    def __init__(self, *args, **kwargs):
        self._model_records = {}
        self._model_restore_pending = None
        self.model_source_warnings = ()
        super().__init__(*args, **kwargs)

    @property
    def model_records(self):
        return tuple(copy.deepcopy(self._model_records[k]) for k in sorted(self._model_records))

    @property
    def modified_count(self):
        return super().modified_count + len(self._model_records)

    def _manifest_document(self):
        document = super()._manifest_document()
        records = self._model_restore_pending if self._model_restore_pending is not None else self._model_records
        if records:
            document["model_edits"] = [copy.deepcopy(records[k]) for k in sorted(records)]
        return document

    def stage_model(self, record):
        record = copy.deepcopy(P.validate_record(record))
        warnings = P.recheck_files(record)
        P.require(not warnings, "\n".join(warnings))
        target = record["target"]
        previous = self._model_records.get(target)
        if previous == record:
            return False
        self._model_records[target] = record
        try:
            self._write_manifest()
        except BaseException:
            if previous is None:
                self._model_records.pop(target)
            else:
                self._model_records[target] = previous
            raise
        self._undo_order.append(_SessionUndo("models", "Model: " + record["summary"], (target, previous)))
        return True

    def undo(self):
        if self._undo_order and self._undo_order[-1].source == "models_revert_all":
            action = self._undo_order[-1]
            previous, base_action = action.payload
            P.require(not self.modified_count, "Revert-All undo conflicts with current model changes.")
            self._model_restore_pending = previous
            try:
                if base_action is not None:
                    self._undo_revert_all_transaction(base_action)
                else:
                    self._write_manifest()
            finally:
                self._model_restore_pending = None
            self._model_records = previous
            self._undo_order.pop()
            return action.label
        if not self._undo_order or self._undo_order[-1].source != "models":
            return super().undo()
        action = self._undo_order[-1]
        target, previous = action.payload
        current = self._model_records.get(target)
        if previous is None:
            self._model_records.pop(target, None)
        else:
            self._model_records[target] = previous
        try:
            self._write_manifest()
        except BaseException:
            self._model_records[target] = current
            raise
        self._undo_order.pop()
        return action.label

    def revert_all(self):
        previous = self._model_records
        if not previous:
            return super().revert_all()
        self._model_records = {}
        try:
            count = super().revert_all()
            if not count:
                self._write_manifest()
        except BaseException:
            self._model_records = previous
            raise
        base_action = self._undo_order.pop() if count else None
        self._undo_order.append(_SessionUndo("models_revert_all", "Revert all assets", (previous, base_action)))
        self.model_source_warnings = ()
        return count + len(previous)

    def canonical_document(self):
        if super().modified_count:
            document = super().canonical_document()
        else:
            P.require(bool(self._model_records), "Replace at least one asset before building a modded XISO.")
            document = {"schema": BACKEND_SCHEMA, "purpose": "Built with 2K5 Mod Studio from checked model changes.", "edits": []}
        for number, record in enumerate(self.model_records):
            path = self.replacements / f"model-{number:04d}.json"
            payload = P.canonical(record)
            # The Build timeline observes recipe file revisions. Publishing an
            # unchanged recipe would make a refresh look like a new model edit.
            try:
                unchanged = not path.is_symlink() and path.is_file() and path.read_bytes() == payload
            except OSError:
                unchanged = False
            if not unchanged:
                _replace_atomic(path, payload)
            document["edits"].append({"kind": P.KIND, "target": record["target"], "recipe": str(path)})
        return document

    def save_shareable_project(self, destination, *, replace=False, expected_target=None, allow_empty=False):
        if not self._model_records:
            return super().save_shareable_project(destination, replace=replace,
                                                  expected_target=expected_target, allow_empty=allow_empty)
        destination = archive._destination(Path(destination))
        payload = P.canonical(list(self.model_records))
        P.require(len(payload) <= P.MAX_BYTES, "Model project changes exceed 64 MiB.")
        with tempfile.TemporaryDirectory(prefix=".model-project-", dir=destination.parent) as folder:
            base, staged = Path(folder)/"base.2k5mod", Path(folder)/"complete.2k5mod"
            super().save_shareable_project(base, allow_empty=True)
            with zipfile.ZipFile(base) as zipped:
                document = json.loads(zipped.read("project.json"))
            document.pop("empty_project", None)
            document["model_edits"] = {"file": MEMBER, "size": len(payload), "sha256": P.sha(payload),
                                       "count": len(self._model_records)}
            _copy_archive(base, staged, document, payload)
            archive._publish_archive(staged, destination, replace=replace, expected_target=expected_target)
        return destination

    def load_shareable_project(self, source):
        P.require(not self.modified_count, "Load model edits into a fresh project session.")
        try:
            document, records = _read_models(source)
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
            raise P.ValidationError(f"Cannot read compiled model project {source}: {exc}") from exc
        if not records:
            return super().load_shareable_project(source)
        model_source = M.ModelSource(self.cache.pack0, self.cache.inventory)
        warnings = []
        for record in records:
            for member in record["members"]:
                P.restore_member(model_source, member, record)
            warnings.extend(P.recheck_files(record))
        with tempfile.TemporaryDirectory(prefix=".model-open-", dir=self.root) as folder:
            base = Path(folder)/"base.2k5mod"
            _copy_archive(source, base, document)
            pending = {r["target"]: copy.deepcopy(r) for r in records}
            # Include models in the base loader's headroom check and atomic
            # manifest publication. A second write after it commits would leave
            # artwork loaded and models absent from the manifest on failure.
            self._model_restore_pending = pending
            try:
                count = super().load_shareable_project(base)
            finally:
                self._model_restore_pending = None
        self._model_records = pending
        self.model_source_warnings = tuple(warnings)
        return count + len(records)
