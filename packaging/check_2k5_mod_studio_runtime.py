#!/usr/bin/env python3
"""Exercise the clean v1 product runtime dependency closure."""

from __future__ import annotations

import ast
import csv
from dataclasses import fields, replace
import hashlib
import importlib
import inspect
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import wave


# A successful clean-stage probe must not mutate the staged application tree.
# Disable local bytecode publication before any product or tool module is
# imported; the post-runtime release gate treats every ``__pycache__`` as an
# undeclared build artifact.
sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
REPORTS = ROOT / "reports/assets"
# Several legacy target adapters intentionally use release-root-relative default
# catalog paths.  Anchor the probe to its own extracted tree so invoking this
# script from any caller directory cannot borrow workspace files or fail merely
# because the shell started elsewhere.
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

REQUIRED_REPORTS = frozenset(
    {
        "nfl2k5_jersey_tset_compatibility.json",
        "nfl2k5_sleeve_tset_compatibility.json",
        "nfl2k5_pants_tset_compatibility.json",
        "nfl2k5_live_helmet_txtr_compatibility.json",
        "nfl2k5_live_numbers_nameplate_compatibility.json",
        "nfl2k5_team_select_card_inventory.json",
        "nfl2k5_player_portrait_compatibility.json",
        "nfl2k5_live_face_texture_compatibility.json",
        "nfl2k5_create_team_field_art_inventory.json",
        "scorebug_presentation_audit.json",
        "nfl2k5_audo_import_capacity.json",
        "nfl2k5_audo_family_labels.json",
        "nfl2k5_p8_texture_inventory.json",
        "menu_state_trace.json",
        "nfl_main_menu_live_state.json",
        "uniform_texture_sharing.v2.json",
    }
)
PRIVATE_INVENTORY = "nfl2k5_resource_chunks_v2.json"
COMPACT_CRIB = ROOT / "mod_editor/data/nfl2k5_crib_catalog.v1.json"
COMPACT_UNIFORM_EQUIPMENT = (
    ROOT / "mod_editor/data/nfl2k5_uniform_equipment_export_catalog.v1.json"
)
STADIUM_GEOMETRY_CATALOG = (
    ROOT / "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json"
)

# These full-corpus totals are resolved only after the user supplies their own
# XISO.  The clean public stage contains the parsers, constraints, and pinned
# metadata needed to reproduce them, never the decoded strings, PLAY bodies,
# Stadium PNGs/glTF, or private inventory that produced the totals.
EXPECTED_PRIVATE_TEXT_COUNTS = {
    "banks": 716,
    "strings": 23_346,
    "editable": 20_074,
    "read_only": 3_272,
    "roster_numbers": 6_522,
}
EXPECTED_PRIVATE_PLAY_COUNTS = {
    "books": 37,
    "formations": 1_533,
    "plays": 9_251,
    "categories": 835,
    "chains": 32_502,
    "nodes": 91_833,
    "slot_references": 101_761,
}
EXPECTED_PRIVATE_STADIUM_TEXTURES = 23_838

# RC29's Audio boundary spans literal-safe UI, cue metadata/archive parsing,
# facade export/handoff, immutable pack preflight, and transactional session
# state. Pin the reviewed final bytes here; these are product runtime
# dependencies, not execution dependencies of the unified XISO provider, so
# widening Nfl2k5UnifiedVisualProvider.module_pins would misstate ownership.
RC29_AUDIO_ANNOTATION_RUNTIME_PINS = {
    "mod_editor/gui/audio_panel_qt.py":
        "b25f669bdbdf8e893db792f1af42c3bf9787a708b7b9d62f1124ef6e4a47b290",
    "mod_editor/gui/studio_qt.py":
        "f481a120910449ad9a3a6dff17d0fe97d243148c1a036ea78f04189e45b87939",
    "mod_editor/studio/audio_annotations.py":
        "c45c94b011d703a24d063138f82477814495705c3b0055a9a867dbab453ba923",
    "mod_editor/studio/audio_replacement_pack.py":
        "68b6887e0778391916a6465a722b062d1c09afe3a376c318026e9db8bd7ed23a",
    "mod_editor/studio/facade.py":
        "8e110e27a57ba22074af408241e07bf980f9cdbb1a0eda4c07d141566ad6fe18",
    "mod_editor/studio/project_archive.py":
        "613e98767acae90e949ca5d4a7dc28611cc8fee12e7c036b9d2c2583154077ee",
    "mod_editor/studio/session.py":
        "34a73dcc42524eef110b2b17c5d1158c4ed5ac45db0f7a3bf0ae50b5e08a27a0",
}

REQUIRED_UNIFIED_PROVIDER_CLOSURE = frozenset(
    {
        "mod_editor/core/nfl2k5_audio_containment_fingerprints.py",
        "mod_editor/core/nfl2k5_audio_origin_authorization.py",
        "mod_editor/core/nfl2k5_audio_source_containment.py",
        "mod_editor/core/nfl2k5_audio_source_fingerprints.py",
        "mod_editor/core/nfl2k5_audio_source_scan.py",
        "mod_editor/core/nfl2k5_audo_family_labels.py",
        "mod_editor/core/nfl2k5_audo_fixed_slots.py",
        "mod_editor/core/nfl2k5_ausb_build_adapter.py",
        "mod_editor/core/nfl2k5_ausb_fixed_slots.py",
        "mod_editor/core/nfl2k5_crib.py",
        "mod_editor/core/nfl2k5_crib_electronics_targets.py",
        "mod_editor/core/nfl2k5_crib_geometry_writer.py",
        "mod_editor/core/nfl2k5_crib_scene_texture_writer.py",
        "mod_editor/core/nfl2k5_crib_standalone_texture_writer.py",
        "mod_editor/core/nfl2k5_formation_play_writer.py",
        "mod_editor/core/nfl2k5_playbook_inspector.py",
        "mod_editor/core/nfl2k5_playbook_route_writer.py",
        "mod_editor/core/nfl2k5_safe_text_banks.py",
        "mod_editor/core/nfl2k5_stadium_texture_writer.py",
        "mod_editor/core/nfl2k5_uniform_equipment_writer.py",
        "tools/apf_inner.py",
        "tools/apf_outer.py",
        "tools/nfl_crib_bar_monitor_png_xiso.py",
        "tools/nfl_scne_gltf.py",
        "tools/nfl_static_gltf.py",
        "tools/string_table_inventory.py",
    }
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _exercise_text(text_module: object) -> None:
    """Prove the source-derived text editor can emit one sparse safe edit."""

    bank = text_module.TextBank(
        "synthetic-bank", "ROST", "Synthetic ROST", 0, 0, True, "mixed", 1,
        "runtime-closure fixture",
    )
    asset = text_module.TextAsset(
        asset_id="synthetic.text.team.city",
        bank_id=bank.bank_id,
        label="Synthetic city",
        value="Old",
        encoding="utf-16le",
        allocation_bytes=16,
        character_limit=7,
        used_utf16_code_units=3,
        access=text_module.TextAccess.EDITABLE,
        reason="fixed-allocation runtime fixture",
        outer_index=0,
        chunk_index=0,
        owner_kind="team",
        owner_index=2,
        field="city",
        reference_count=1,
        provider_kind=text_module.ROSTER_TEAM_PROVIDER_KIND,
        provider_group_id="synthetic-team",
    )
    catalog = text_module.Nfl2k5TextCatalog(
        (bank,), (asset,), (), (), (),
    )
    edits = text_module.Nfl2k5TextEdits(catalog)
    edits.set_text(asset.asset_id, "New")
    provider_edits = edits.provider_edits()
    require(
        provider_edits == ({
            "kind": "roster_team_text",
            "resource_outer_index": 0,
            "team_index": 2,
            "changes": {"city": "New"},
        },),
        "fixed-allocation Text provider route changed",
    )
    edits.revert_all()
    require(edits.modified_count == 0, "Text replacement did not revert")


def _exercise_safe_fixed_text(safe_text_module: object) -> None:
    """Compile one bounded universal-text value and reject an overflow."""

    compiled = safe_text_module.encode_fixed_utf16le(
        "MOD", 10, "synthetic fixed text"
    )
    require(
        compiled == b"M\0O\0D\0\0\0\0\0",
        "universal fixed-text encoding contract changed",
    )
    try:
        safe_text_module.encode_fixed_utf16le(
            "TOO LONG", 10, "synthetic fixed text"
        )
    except safe_text_module.ValidationError:
        pass
    else:
        raise RuntimeError("universal fixed-text allocation overflow was accepted")


def _exercise_per_uniform_colour_project(visual_project: object) -> None:
    """Keep the public project logical and independently addressable per set."""

    adapter = visual_project.unif_color_adapter
    require(
        adapter.parse_color("#123456") == 0xFF123456
        and set(adapter.PACK_PROVENANCE) == set("9ABC"),
        "per-uniform colour adapter provenance contract changed",
    )
    rows = [
        {
            "kind": "unif_color", "selector": "18H0",
            "facemask": "FF123456", "turtleneck": "FFABCDEF",
        },
        {
            "kind": "unif_color", "selector": "18A0",
            "facemask": "FF654321", "turtleneck": "FFFEDCBA",
        },
    ]
    with tempfile.TemporaryDirectory(prefix="2k5-runtime-unif-colour-") as name:
        project = Path(name) / "project.json"
        document = {
            "schema": visual_project.SCHEMA,
            "purpose": "runtime per-uniform colour closure",
            "edits": rows,
        }
        project.write_bytes(visual_project.canonical_json(document))
        parsed = visual_project.read_project(project)
        require(
            [row["selector"] for row in parsed.value["edits"]]
            == ["18H0", "18A0"],
            "multiple per-uniform colour selectors no longer validate",
        )
        document["edits"] = [rows[0], dict(rows[0])]
        project.write_bytes(visual_project.canonical_json(document))
        try:
            visual_project.read_project(project)
        except visual_project.ProjectError:
            pass
        else:
            raise RuntimeError("duplicate per-uniform colour selector was accepted")


def _exercise_audio(audio_module: object, audo_tool: object) -> None:
    """Validate the public WAV contract and its shipped Xbox IMA encoder."""

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(audio_module.NFL_MENU_BACK_AUDIO_CHANNELS)
        stream.setsampwidth(2)
        stream.setframerate(audio_module.NFL_MENU_BACK_AUDIO_SAMPLE_RATE)
        stream.writeframes(
            b"\0\0" * audio_module.NFL_MENU_BACK_AUDIO_FRAME_COUNT
        )
    payload = buffer.getvalue()
    audio_module._validate_strict_wav(payload)
    samples = (0,) * audio_module.NFL_MENU_BACK_AUDIO_FRAME_COUNT
    encoded = audo_tool.encode_xbox_ima(samples)
    require(len(encoded) == audo_tool.PAYLOAD_SIZE,
            "menu-back Xbox IMA payload size changed")
    require(len(audo_tool.decode_xbox_ima(encoded)) == len(samples),
            "menu-back Xbox IMA roundtrip frame count changed")


def _exercise_audio_waveform(waveform_module: object) -> None:
    """Read a bounded synthetic PCM16 waveform without mutating its WAV."""

    with tempfile.TemporaryDirectory(
        prefix="2k5-mod-studio-waveform-runtime-"
    ) as temporary:
        wav_path = Path(temporary) / "synthetic-current.wav"
        frame_count = 4_096
        payload = bytearray()
        for frame_index in range(frame_count):
            left = ((frame_index % 128) - 64) * 400
            payload.extend(struct.pack("<hh", left, -left))
        with wave.open(str(wav_path), "wb") as stream:
            stream.setnchannels(2)
            stream.setsampwidth(2)
            stream.setframerate(22_050)
            stream.writeframes(bytes(payload))

        before_stat = wav_path.stat()
        before_sha = hashlib.sha256(wav_path.read_bytes()).hexdigest()
        envelope = waveform_module.read_pcm16_waveform(
            wav_path,
            max_points=64,
            frames_per_point=128,
        )
        require(
            envelope.channel_count == 2
            and envelope.sample_rate == 22_050
            and envelope.frame_count == frame_count
            and envelope.point_count == 64
            and envelope.sampled_frame_count <= 64 * 128,
            "bounded Audio waveform shape changed",
        )
        require(
            all(
                -1.0 <= minimum <= maximum <= 1.0
                for channel in envelope.channel_peaks
                for minimum, maximum in channel
            ),
            "Audio waveform normalization changed",
        )
        after_stat = wav_path.stat()
        require(
            (before_stat.st_size, before_stat.st_mtime_ns, before_sha)
            == (
                after_stat.st_size,
                after_stat.st_mtime_ns,
                hashlib.sha256(wav_path.read_bytes()).hexdigest(),
            ),
            "read-only Audio waveform mutated its private WAV",
        )
        try:
            waveform_module.read_pcm16_waveform(
                wav_path,
                cancelled=lambda: True,
            )
        except waveform_module.WaveformCancelled:
            pass
        else:
            raise RuntimeError("Audio waveform cancellation was ignored")


def _exercise_playable_audio_catalog(
    audio_catalog_module: object, audio_panel_module: object,
) -> None:
    """Pin the retail-free default playable inventory and canonical order."""

    require(
        audio_catalog_module.EXPECTED_PLAYABLE_AUDIO_COUNT == 54_421
        and audio_catalog_module.PLAYABLE_AUDIO_SCOPE_ID == "playable"
        and audio_catalog_module.PLAYABLE_AUDIO_FAMILIES == (
            ("frontend_ui", "Frontend & franchise UI"),
            ("field_crowd_player", "On-field, crowd & player state"),
            ("team_crowd", "Team crowd variations"),
            ("crib_minigames", "Crib, minigames & trivia"),
            ("music", "Soundtrack & music"),
            ("commentary", "Commentary & speech"),
            ("stadium", "Stadium, PA & coach"),
            ("presentation", "Broadcast & presentation"),
            ("ambient", "Ambient & diagnostics"),
            ("unknown", "Unknown playable audio"),
        ),
        "All Playable Audio constants or family registry changed",
    )
    require(
        audio_panel_module.AUDIO_PLAYABLE_DEFAULT_SCOPE_CONTRACT
        == "default_mixed_54421_standalone_then_streaming_ranges"
        and sum(
            audio_panel_module._FAMILY_COUNTS[
                audio_catalog_module.PLAYABLE_AUDIO_SCOPE_ID
            ].values()
        ) == audio_catalog_module.EXPECTED_PLAYABLE_AUDIO_COUNT,
        "All Playable Audio GUI default or family counts changed",
    )

    # The public catalog cannot be constructed without the user's own XISO.
    # Inspect its shipped constructor AST and exercise its public count property
    # with payload-free sentinels instead of manufacturing retail-derived rows.
    catalog_path = Path(audio_catalog_module.__file__)
    catalog_tree = ast.parse(catalog_path.read_text(encoding="utf-8"))

    def self_attribute(node: ast.AST, name: str) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr == name
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
        )

    playable_assignments = tuple(
        node for node in ast.walk(catalog_tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and (
            any(self_attribute(target, "playable_assets") for target in node.targets)
            if isinstance(node, ast.Assign)
            else self_attribute(node.target, "playable_assets")
        )
    )
    require(
        len(playable_assignments) == 1
        and isinstance(playable_assignments[0].value, ast.BinOp)
        and isinstance(playable_assignments[0].value.op, ast.Add)
        and self_attribute(playable_assignments[0].value.left, "assets")
        and self_attribute(playable_assignments[0].value.right, "streaming_ranges"),
        "playable catalog order is no longer standalone assets then streaming ranges",
    )

    synthetic = object.__new__(audio_catalog_module.Nfl2k5AudioCatalog)
    synthetic.assets = ("synthetic-standalone-0", "synthetic-standalone-1")
    synthetic.streaming_ranges = ("synthetic-range-0", "synthetic-range-1")
    synthetic.streaming_banks = ("synthetic-raw-bank",)
    synthetic.playable_assets = synthetic.assets + synthetic.streaming_ranges
    require(
        synthetic.playable_count == 4
        and synthetic.playable_assets
        == (
            "synthetic-standalone-0",
            "synthetic-standalone-1",
            "synthetic-range-0",
            "synthetic-range-1",
        )
        and synthetic.streaming_banks[0] not in synthetic.playable_assets,
        "playable catalog API included a bank or changed canonical order",
    )


def _exercise_fixed_audo(fixed_module: object, audio_catalog_module: object) -> None:
    """Load all public fixed slots and round-trip the smallest strict WAV."""

    slots = fixed_module.load_editable_slots()
    require(len(slots) == 849, "standalone fixed-AUDO editable count changed")
    require(
        len({slot.asset_id for slot in slots}) == len(slots)
        and sum(slot.legacy_complete_pack_editable for slot in slots) == 152
        and not any(
            slot.selector == audio_catalog_module.MENU_BACK_SELECTOR
            for slot in slots
        ),
        "standalone fixed-AUDO ownership overlaps or duplicates menu-back",
    )
    slot = min(slots, key=lambda row: row.payload_size)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(slot.channels)
        stream.setsampwidth(2)
        stream.setframerate(slot.sample_rate)
        stream.writeframes(bytes(slot.frame_count * slot.channels * 2))
    strict = fixed_module.parse_strict_wav(buffer.getvalue(), slot)
    encoded = fixed_module.encode_xbox_ima(strict, slot)
    decoded = fixed_module.decode_xbox_ima(encoded, slot)
    require(
        len(encoded) == slot.payload_size
        and len(decoded) == slot.frame_count * slot.channels
        and not any(decoded),
        "standalone fixed-AUDO strict WAV/Xbox IMA roundtrip changed",
    )


def _exercise_audio_replacement_pack_v2(
    pack_module: object, audio_catalog_module: object, facade_module: object,
) -> None:
    """Exercise a retail-free mixed selected-audio pack through public routes."""

    selector = audio_catalog_module.MENU_BACK_SELECTOR
    standalone = audio_catalog_module.Nfl2k5AudioAsset(
        asset_id="synthetic.audio.standalone",
        name="Synthetic standalone cue",
        outer_index=selector[0],
        outer_id="standalone-outer-do-not-publish",
        outer_head="standalone-head-do-not-publish",
        outer_size=1,
        chunk_index=selector[1],
        chunk_offset=17,
        stored_size=1,
        system_bytes=0,
        payload_bytes=0,
        tail_bytes=0,
        channels=1,
        sample_rate=16_000,
        frame_count=5_696,
        codec_word="synthetic",
        classification="synthetic",
        classification_reasons=(),
        fixed_slot_authorization="synthetic",
        runtime_selector_owner="synthetic",
        runtime_visibility="synthetic",
        duplicate_name=None,
        equal_payload=None,
        equal_decoded_content=None,
        equal_resource_span=None,
        physical_span_shared=False,
        resource_body_sha256="a" * 64,
        payload_sha256="b" * 64,
        decoded_pcm_sha256="c" * 64,
        replacement_contract=audio_catalog_module.MENU_BACK_CONTRACT,
    )
    bank = audio_catalog_module.Nfl2k5StreamingAudioBank(
        asset_id="synthetic.audio.streaming",
        name="Synthetic streaming bank",
        role_class="music",
        outer_index=1,
        outer_id="streaming-outer-do-not-publish",
        outer_head="streaming-head-do-not-publish",
        outer_size=72,
        chunk_index=2,
        chunk_offset=29,
        stored_size=72,
        external_filename="retail-bank-do-not-publish.bin",
        external_outer_index=3,
        external_outer_id="external-owner-do-not-publish",
        external_size=72,
        entry_count=1,
        sample_rate=16_000,
        channel_word=1,
        unknown_word=0,
        unit_word=0,
        boundaries=(0, 72),
        descriptor_sha256="d" * 64,
        shared_external_descriptor_count=1,
    )
    streaming = audio_catalog_module.Nfl2k5StreamingAudioRange(
        bank, 0, 0, 72
    )
    linked_alias = "synthetic.audio.streaming.alias"

    class SyntheticCatalog:
        assets = (standalone,)
        streaming_banks = (bank,)
        streaming_ranges = (streaming,)

    catalog = SyntheticCatalog()

    class SyntheticAudioService(audio_catalog_module.Nfl2k5AudioService):
        def __init__(self) -> None:
            self.catalog = catalog

        def resolve_editable_audio(self, value: object) -> object:
            requested = getattr(value, "asset_id", value)
            for item in (*catalog.assets, *catalog.streaming_ranges):
                if requested == item.asset_id:
                    return item
            raise RuntimeError("synthetic selected-audio ID was not resolved")

        def audio_affected_asset_ids(self, value: object) -> tuple[str, ...]:
            item = self.resolve_editable_audio(value)
            if item is streaming:
                return streaming.asset_id, linked_alias
            return (standalone.asset_id,)

    selected_service = SyntheticAudioService()

    class SyntheticSource:
        sha256 = "f" * 64

    class SyntheticCache:
        source = SyntheticSource()

    class SyntheticSession:
        cache = SyntheticCache()

        @staticmethod
        def _require_audio_service() -> object:
            return selected_service

        @staticmethod
        def audio_content_origin(_asset: object) -> str:
            return "retail_derived"

    service = pack_module.AudioReplacementPackService(
        catalog, SyntheticSession(), expected_editable_count=None
    )
    with tempfile.TemporaryDirectory(
        prefix="2k5-runtime-selected-audio-pack-"
    ) as temporary:
        template = Path(temporary) / "selected"
        exported = service.export_template(
            template,
            asset_ids=(standalone.asset_id, streaming.asset_id),
        )
        manifest_payload = (
            template / pack_module.AUDIO_REPLACEMENT_MANIFEST
        ).read_bytes()
        manifest = json.loads(manifest_payload)
        rows = manifest.get("assets")
        require(
            exported.asset_count == 2
            and exported.menu_back_count == 1
            and exported.streaming_range_count == 1
            and exported.retail_audio_file_count == 0,
            "selected-audio v2 export counts changed",
        )
        require(
            manifest.get("schema")
            == pack_module.AUDIO_REPLACEMENT_PACK_V2_SCHEMA
            and isinstance(rows, list)
            and [row.get("asset_id") for row in rows]
            == [standalone.asset_id, streaming.asset_id],
            "selected-audio v2 schema or ordering changed",
        )
        expected_row_keys = {
            "asset_id", "contract", "logical_aliases", "path",
            "working_baseline",
        }
        require(
            all(isinstance(row, dict) and set(row) == expected_row_keys for row in rows)
            and rows[1]["logical_aliases"]
            == {"asset_ids": [streaming.asset_id, linked_alias], "count": 2}
            and manifest.get("payload_policy")
            == "metadata-only-template; zero-retail-audio-by-construction",
            "selected-audio v2 public row or alias contract changed",
        )
        released_files = {
            path.relative_to(template).as_posix()
            for path in template.rglob("*") if path.is_file()
        }
        require(
            released_files == {
                pack_module.AUDIO_REPLACEMENT_GUIDE,
                pack_module.AUDIO_REPLACEMENT_MANIFEST,
            }
            and not tuple(template.rglob("*.wav")),
            "selected-audio v2 template contains an audio payload",
        )
        private_markers = (
            standalone.outer_id,
            standalone.outer_head,
            bank.outer_id,
            bank.outer_head,
            bank.external_filename,
            bank.external_outer_id,
            bank.descriptor_sha256,
            temporary,
        )
        manifest_text = manifest_payload.decode("utf-8")
        require(
            all(marker not in manifest_text for marker in private_markers),
            "selected-audio v2 manifest exposed physical or private metadata",
        )
        try:
            service.import_edited(template)
        except pack_module.AudioReplacementPackError as exc:
            require(
                str(exc).startswith("Add at least one authored WAV"),
                "selected-audio v2 empty-pack refusal changed",
            )
        else:
            raise RuntimeError("selected-audio v2 empty pack was accepted")

    # RC13 collection parity: a staged fixed-range WAV may be labeled as the
    # user's replacement, while encoded raw ranges and complete banks may not.
    authored_row = facade_module.bundle_row_for_asset(
        streaming, output_format="wav", content_origin="user_replacement"
    )
    require(
        authored_row.extension == ".wav"
        and authored_row.content_origin == "user_replacement"
        and authored_row.metadata.get("current_status") == "Modified",
        "modified streaming-range collection labeling changed",
    )
    for asset, output_format, expected in (
        (streaming, "bin", "playable WAV"),
        (bank, "bin", "Complete streaming banks"),
    ):
        try:
            facade_module.bundle_row_for_asset(
                asset,
                output_format=output_format,
                content_origin="user_replacement",
            )
        except facade_module.ValidationError as exc:
            require(expected in str(exc), "streaming collection refusal changed")
        else:
            raise RuntimeError(
                "retail-derived streaming bytes accepted a user-replacement label"
            )


def _exercise_audio_annotations(
    annotations_module: object,
    project_archive_module: object,
    session_module: object,
    facade_module: object,
    audio_panel_module: object,
) -> None:
    """Prove the retail-free cue-label boundary from a clean public stage."""

    annotation = annotations_module.validate_audio_cue_annotation(
        "nfl2k5.audio.audo.o0003.c0007",
        "Third-down sting",
        "Heard in menu\r\nRecheck in franchise",
    )
    require(
        annotation.title == "Third-down sting"
        and annotation.note == "Heard in menu\nRecheck in franchise",
        "Audio annotation normalization changed",
    )
    document = annotations_module.annotation_document((annotation,))
    require(
        annotations_module.parse_audio_annotation_document(document)
        == (annotation,)
        and document.get("schema")
        == "2k5_mod_studio_audio_annotations/v1",
        "Audio annotation document roundtrip changed",
    )
    try:
        annotations_module.validate_audio_cue_annotation(
            annotation.cue_id, "unsafe\x00title", ""
        )
    except annotations_module.ValidationError:
        pass
    else:
        raise RuntimeError("Audio annotation accepted a control character")
    try:
        annotations_module.validate_audio_cue_annotation(
            annotation.cue_id, "spoof\u200etitle", ""
        )
    except annotations_module.ValidationError:
        pass
    else:
        raise RuntimeError("Audio annotation accepted a Unicode format control")
    try:
        project_archive_module._reject_duplicate_json_pairs((
            ("title", "first"), ("title", "second"),
        ))
    except project_archive_module.ValidationError:
        pass
    else:
        raise RuntimeError("Project JSON accepted a duplicate object key")

    base_row = facade_module.AudioBundleRow(
        "cue", "Game name", "game-name", ".wav", 44,
        "user_replacement", {"asset_id": "cue"},
    )
    labeled_row = facade_module._with_audio_annotation(base_row, annotation)
    require(
        labeled_row.display_name == annotation.title
        and labeled_row.metadata.get("custom_title") == annotation.title
        and labeled_row.metadata.get("annotation_note") == annotation.note
        and labeled_row.metadata.get("game_catalog_name") == "Game name"
        and labeled_row.suggested_basename == "game-name",
        "Audio annotation local-export metadata overlay changed",
    )

    loaded_fields = {
        field.name for field in fields(project_archive_module.LoadedProject)
    }
    session_type = session_module.StudioSession
    browse_signature = inspect.signature(
        facade_module.Nfl2k5StudioFacade.browse_audio
    )
    export_signature = inspect.signature(
        facade_module.Nfl2k5StudioFacade.export_audio_bundle
    )
    require(
        "audio_annotations" in loaded_fields
        and "audio_annotations" in inspect.signature(
            project_archive_module.save_project_archive
        ).parameters,
        "Shareable project audio-annotation persistence is missing",
    )
    class EmptyCatalog:
        @staticmethod
        def get_asset(_asset_id: str) -> object:
            raise RuntimeError("Empty projects must not resolve a game asset")

    with tempfile.TemporaryDirectory(prefix="2k5-runtime-empty-project-") as root:
        base = Path(root)
        empty_project = project_archive_module.save_project_archive(
            catalog=EmptyCatalog(),
            asset_io=object(),
            edits=(),
            destination=base / "empty.2k5mod",
            allow_empty=True,
        )
        loaded_empty = project_archive_module.load_project_archive(
            source=empty_project,
            catalog=EmptyCatalog(),
            asset_io=object(),
            private_root=base / "private",
        )
        try:
            require(
                loaded_empty.edits == ()
                and loaded_empty.audio_edits == ()
                and loaded_empty.audio_annotations == ()
                and loaded_empty.text_replacements is None,
                "Canonical empty Save/recovery project did not roundtrip",
            )
        finally:
            loaded_empty.cleanup()
    require(
        isinstance(getattr(session_type, "project_metadata_count", None), property)
        and isinstance(getattr(session_type, "audio_annotations", None), property)
        and callable(getattr(session_type, "set_audio_annotation", None))
        and callable(getattr(session_type, "clear_audio_annotation", None))
        and callable(getattr(session_type, "audio_annotation", None))
        and callable(getattr(session_type, "discard_private_workspace", None))
        and "resolve_playable_audio" in inspect.getsource(
            session_type.attach_audio_service
        ),
        "Session audio-annotation CRUD/count API changed",
    )
    require(
        "_audio_annotations" not in inspect.getsource(
            session_type.modified_count.fget
        )
        and "audio_annotations" not in inspect.getsource(
            session_type.canonical_document
        ),
        "Audio annotations leaked into buildable edit state",
    )
    require(
        "labeled_only" in browse_signature.parameters
        and "labeled_only" in export_signature.parameters
        and callable(getattr(
            facade_module.Nfl2k5StudioFacade, "set_audio_annotation", None
        ))
        and callable(getattr(
            facade_module.Nfl2k5StudioFacade, "clear_audio_annotation", None
        )),
        "Facade labeled search/export or annotation CRUD route changed",
    )
    require(
        audio_panel_module.AUDIO_ANNOTATION_CONTRACT
        == "project_metadata_only_stable_logical_cue_id"
        and hasattr(audio_panel_module.AudioPanel, "audio_annotation_changed")
        and callable(getattr(
            audio_panel_module.AudioPanel, "_save_selected_annotation", None
        ))
        and callable(getattr(
            audio_panel_module.AudioPanel, "_clear_selected_annotation", None
        )),
        "Audio annotation GUI contract changed",
    )


def _exercise_audio_replacement_preflight_contract(
    pack_module: object,
    session_module: object,
    facade_module: object,
    audio_panel_module: object,
) -> None:
    """Pin the retail-free Preview -> explicit Apply transaction boundary."""

    preview_type = pack_module.AudioReplacementPackPreflightResult
    require(
        tuple(field.name for field in fields(preview_type)) == (
            "schema",
            "pack_kind",
            "confirmation_token",
            "supplied_count",
            "would_change_count",
            "unique_physical_change_count",
            "already_current_count",
            "would_restore_original_count",
            "unique_physical_restore_count",
            "affected_alias_count",
            "resulting_modified_count",
            "changed_rows",
            "omitted_changed_count",
        ),
        "Audio replacement-pack preflight result fields changed",
    )
    token = "2k5apf1." + "e" * 64
    preview = preview_type(
        schema=pack_module.AUDIO_REPLACEMENT_PACK_V2_SCHEMA,
        pack_kind="selected_audio",
        confirmation_token=token,
        supplied_count=2,
        would_change_count=1,
        unique_physical_change_count=1,
        already_current_count=1,
        would_restore_original_count=0,
        unique_physical_restore_count=0,
        affected_alias_count=0,
        resulting_modified_count=1,
        changed_rows=(),
        omitted_changed_count=0,
    )
    require(
        preview.can_apply
        and token not in repr(preview)
        and getattr(preview_type, "__dataclass_params__").frozen,
        "Audio replacement-pack preview is not frozen or token-opaque",
    )

    session_type = session_module.StudioSession
    require(
        isinstance(session_type.mutation_revision, property)
        and callable(session_type.preflight_audio_batch)
        and callable(session_type.issue_audio_pack_preflight_token)
        and callable(session_type.verify_audio_pack_preflight_token),
        "Audio replacement-pack session revision/token API changed",
    )
    service_type = pack_module.AudioReplacementPackService
    service_preview = inspect.signature(service_type.preflight_edited)
    service_apply = inspect.signature(service_type.import_edited)
    facade_preview = inspect.signature(
        facade_module.Nfl2k5StudioFacade.preflight_audio_replacement_pack
    )
    facade_apply = inspect.signature(
        facade_module.Nfl2k5StudioFacade.import_audio_replacement_pack
    )
    require(
        "source" in service_preview.parameters
        and "confirmation_token" in service_apply.parameters
        and "source" in facade_preview.parameters
        and "confirmation_token" in facade_apply.parameters,
        "Audio replacement-pack Preview/Apply facade API changed",
    )

    apply_source = inspect.getsource(service_type.import_edited)
    revalidate_markers = (
        "with self._validated_edited",
        "self.session.preflight_audio_batch",
        "self.session.verify_audio_pack_preflight_token",
        "self.session.replace_audio_batch",
    )
    marker_offsets = tuple(apply_source.find(marker) for marker in revalidate_markers)
    require(
        all(offset >= 0 for offset in marker_offsets)
        and marker_offsets == tuple(sorted(marker_offsets)),
        "Audio pack Apply no longer revalidates before its atomic session write",
    )
    panel_import_source = inspect.getsource(
        audio_panel_module.AudioPanel._import_audio_replacement_pack
    )
    require(
        audio_panel_module.AUDIO_REPLACEMENT_PREFLIGHT_CONTRACT
        == "fully_validated_read_only_preview_then_explicit_apply"
        and "preflight_audio_replacement_pack" in panel_import_source
        and "QMessageBox.Apply" in panel_import_source
        and "confirmation_token=token" in panel_import_source
        and panel_import_source.count("import_method(") == 1,
        "Audio replacement-pack GUI no longer requires explicit token-bound Apply",
    )


def _exercise_audio_replacement_pack_v3(
    pack_module: object, audio_catalog_module: object,
) -> None:
    """Prove plain v3 and mapped v4 all-850 packs from a clean stage."""

    selector = audio_catalog_module.MENU_BACK_SELECTOR
    menu_back = audio_catalog_module.Nfl2k5AudioAsset(
        asset_id="synthetic.audio.complete.menu-back",
        name="Synthetic Menu Back",
        outer_index=selector[0],
        outer_id="complete-outer-do-not-publish",
        outer_head="complete-head-do-not-publish",
        outer_size=1,
        chunk_index=selector[1],
        chunk_offset=17,
        stored_size=1,
        system_bytes=0,
        payload_bytes=0,
        tail_bytes=0,
        channels=1,
        sample_rate=16_000,
        frame_count=5_696,
        codec_word="synthetic",
        classification="synthetic",
        classification_reasons=(),
        fixed_slot_authorization="synthetic",
        runtime_selector_owner="synthetic",
        runtime_visibility="synthetic",
        duplicate_name=None,
        equal_payload=None,
        equal_decoded_content=None,
        equal_resource_span=None,
        physical_span_shared=False,
        resource_body_sha256="a" * 64,
        payload_sha256="b" * 64,
        decoded_pcm_sha256="c" * 64,
        replacement_contract=audio_catalog_module.MENU_BACK_CONTRACT,
    )
    fixed = tuple(
        replace(
            menu_back,
            asset_id=f"synthetic.audio.complete.fixed-{ordinal:03d}",
            name=f"Synthetic fixed standalone cue {ordinal:03d}",
            outer_index=selector[0] + ordinal,
            chunk_index=0,
            classification=(
                audio_catalog_module.EDITABLE_CLASSIFICATION
                if ordinal <= 152 else "export-only"
            ),
        )
        for ordinal in range(1, 850)
    )
    assets = (menu_back, *fixed)

    class SyntheticCatalog:
        streaming_banks: tuple[object, ...] = ()
        streaming_ranges: tuple[object, ...] = ()

        def __init__(self) -> None:
            self.assets = assets
            self._by_id = {asset.asset_id: asset for asset in assets}

    catalog = SyntheticCatalog()
    require(
        pack_module.complete_standalone_pack_path(
            catalog, assets[0].asset_id
        ) == "replacements/001__selected-audio.wav"
        and pack_module.complete_standalone_pack_path(
            catalog, assets[-1].asset_id
        ) == "replacements/850__selected-audio.wav"
        and pack_module.complete_standalone_pack_path(
            catalog, "synthetic.audio.unknown"
        ) is None,
        "complete standalone Audio-browser pack-path lookup changed",
    )
    meaning_statuses = tuple(
        pack_module.standalone_runtime_meaning_status(asset)
        for asset in assets
    )
    require(
        meaning_statuses.count("menu_back_route_runtime_unproved") == 1
        and meaning_statuses.count(
            "reviewed_label_runtime_meaning_unproved"
        ) == 152
        and meaning_statuses.count(
            "provisional_label_runtime_meaning_unproved"
        ) == 697,
        "standalone Audio meaning-confidence distribution changed",
    )

    class SyntheticAudioService(audio_catalog_module.Nfl2k5AudioService):
        def __init__(self) -> None:
            self.catalog = catalog

        def resolve_editable_audio(self, value: object) -> object:
            asset_id = getattr(value, "asset_id", value)
            try:
                return catalog._by_id[asset_id]
            except (KeyError, TypeError) as exc:
                raise RuntimeError(
                    "synthetic complete-audio ID was not resolved"
                ) from exc

        def audio_affected_asset_ids(self, value: object) -> tuple[str, ...]:
            asset = self.resolve_editable_audio(value)
            return (asset.asset_id,)

    audio_service = SyntheticAudioService()

    class SyntheticSource:
        sha256 = "f" * 64

    class SyntheticCache:
        source = SyntheticSource()

    class SyntheticSession:
        cache = SyntheticCache()

        @staticmethod
        def _require_audio_service() -> object:
            return audio_service

        @staticmethod
        def audio_content_origin(_asset: object) -> str:
            return "retail_derived"

    service = pack_module.AudioReplacementPackService(
        catalog, SyntheticSession(), expected_editable_count=None
    )
    with tempfile.TemporaryDirectory(
        prefix="2k5-runtime-complete-audio-pack-"
    ) as temporary:
        template = Path(temporary) / "complete-850"
        exported = service.export_template(
            template,
            complete_standalone=True,
        )
        manifest_payload = (
            template / pack_module.AUDIO_REPLACEMENT_MANIFEST
        ).read_bytes()
        manifest = json.loads(manifest_payload)
        rows = manifest.get("assets")
        require(
            exported.asset_count == 850
            and exported.fixed_audo_count == 849
            and exported.menu_back_count == 1
            and exported.streaming_range_count == 0
            and exported.retail_audio_file_count == 0,
            "complete standalone v3 export counts changed",
        )
        require(
            manifest.get("schema")
            == pack_module.AUDIO_REPLACEMENT_PACK_V3_SCHEMA
            and isinstance(rows, list)
            and len(rows) == 850
            and [row.get("asset_id") for row in rows]
            == [asset.asset_id for asset in assets],
            "complete standalone v3 schema or canonical order changed",
        )
        require(
            manifest.get("counts") == {
                "complete_standalone_cues": 850,
                "fixed_audo_cues": 849,
                "menu_back_cues": 1,
                "replacement_wavs_in_template": 0,
            }
            and all(
                isinstance(row, dict)
                and set(row) == {
                    "asset_id", "contract", "logical_aliases", "path",
                    "working_baseline",
                }
                and row.get("logical_aliases")
                == {"asset_ids": [row.get("asset_id")], "count": 1}
                for row in rows
            ),
            "complete standalone v3 public row contract changed",
        )
        released_files = {
            path.relative_to(template).as_posix()
            for path in template.rglob("*") if path.is_file()
        }
        require(
            released_files == {
                pack_module.AUDIO_REPLACEMENT_GUIDE,
                pack_module.AUDIO_REPLACEMENT_MANIFEST,
            }
            and not tuple(template.rglob("*.wav"))
            and b"RIFF" not in manifest_payload,
            "complete standalone v3 template contains an audio payload",
        )
        public_text = manifest_payload.decode("utf-8")
        require(
            all(
                marker not in public_text
                for marker in (
                    menu_back.outer_id,
                    menu_back.outer_head,
                    menu_back.resource_body_sha256,
                    menu_back.payload_sha256,
                    menu_back.decoded_pcm_sha256,
                    temporary,
                )
            ),
            "complete standalone v3 exposed private physical metadata",
        )

        mapped_template = Path(temporary) / "complete-850-mapped"
        mapped_exported = service.export_template(
            mapped_template,
            complete_standalone=True,
            with_authoring_map=True,
        )
        mapped_manifest_payload = (
            mapped_template / pack_module.AUDIO_REPLACEMENT_MANIFEST
        ).read_bytes()
        mapped_manifest = json.loads(mapped_manifest_payload)
        cue_map_payload = (
            mapped_template / pack_module.AUDIO_CUE_MAP
        ).read_bytes()
        cue_map_text = cue_map_payload.decode("utf-8")
        cue_rows = list(csv.DictReader(io.StringIO(cue_map_text)))
        cue_columns = (
            "ordinal", "asset_id", "replacement_path", "display_name",
            "family_id", "family_label", "channels", "sample_rate_hz",
            "exact_frame_count", "duration_seconds", "product_edit_status",
            "writer_route", "legacy_v1_pack_member", "alias_status",
            "runtime_meaning_status",
        )
        mapped_rows = mapped_manifest.get("assets")
        require(
            mapped_exported.asset_count == 850
            and mapped_exported.fixed_audo_count == 849
            and mapped_exported.menu_back_count == 1
            and mapped_exported.streaming_range_count == 0
            and mapped_exported.retail_audio_file_count == 0,
            "mapped complete standalone v4 export counts changed",
        )
        require(
            mapped_manifest.get("schema")
            == pack_module.AUDIO_REPLACEMENT_PACK_V4_SCHEMA
            and isinstance(mapped_rows, list)
            and len(mapped_rows) == len(cue_rows) == 850
            and tuple(cue_rows[0]) == cue_columns,
            "mapped complete standalone v4 schema or CSV columns changed",
        )
        require(
            mapped_manifest.get("cue_map") == {
                "path": pack_module.AUDIO_CUE_MAP,
                "row_count": 850,
                "schema": pack_module.AUDIO_CUE_MAP_SCHEMA,
                "sha256": hashlib.sha256(cue_map_payload).hexdigest(),
            }
            and [row["asset_id"] for row in cue_rows]
            == [row["asset_id"] for row in mapped_rows]
            and [row["replacement_path"] for row in cue_rows]
            == [row["path"] for row in mapped_rows],
            "mapped complete standalone v4 map binding changed",
        )
        status_counts: dict[str, int] = {}
        for row in cue_rows:
            status = row["runtime_meaning_status"]
            status_counts[status] = status_counts.get(status, 0) + 1
        require(
            status_counts == {
                "menu_back_route_runtime_unproved": 1,
                "reviewed_label_runtime_meaning_unproved": 152,
                "provisional_label_runtime_meaning_unproved": 697,
            }
            and sum(row["legacy_v1_pack_member"] == "true" for row in cue_rows)
            == 153
            and all(row["product_edit_status"] == "Editable" for row in cue_rows),
            "mapped complete standalone v4 discovery status changed",
        )
        mapped_files = {
            path.relative_to(mapped_template).as_posix()
            for path in mapped_template.rglob("*") if path.is_file()
        }
        require(
            mapped_files == {
                pack_module.AUDIO_REPLACEMENT_GUIDE,
                pack_module.AUDIO_REPLACEMENT_MANIFEST,
                pack_module.AUDIO_CUE_MAP,
            }
            and not tuple(mapped_template.rglob("*.wav"))
            and b"RIFF" not in mapped_manifest_payload
            and b"RIFF" not in cue_map_payload,
            "mapped complete standalone v4 contains an audio payload",
        )
        combined_public_text = (
            mapped_manifest_payload + b"\n" + cue_map_payload
        ).decode("utf-8")
        require(
            all(
                marker not in combined_public_text
                for marker in (
                    menu_back.outer_id,
                    menu_back.outer_head,
                    menu_back.resource_body_sha256,
                    menu_back.payload_sha256,
                    menu_back.decoded_pcm_sha256,
                    temporary,
                )
            )
            and "classification" not in cue_map_text.casefold()
            and "outer_index" not in cue_map_text
            and "chunk_index" not in cue_map_text,
            "mapped complete standalone v4 exposed private physical metadata",
        )
        try:
            service.import_edited(mapped_template)
        except pack_module.AudioReplacementPackError as exc:
            require(
                str(exc).startswith("Add at least one authored WAV"),
                "mapped complete standalone v4 empty-pack refusal changed",
            )
        else:
            raise RuntimeError("mapped complete standalone v4 empty pack was accepted")


def _exercise_stadium_writer(writer_module: object, studio_module: object) -> None:
    """Exercise the public exact target gate without private Stadium assets."""

    texture = studio_module.StadiumTexture(
        texture_id=writer_module.TARGET_TEXTURE_ID,
        scene_id=writer_module.TARGET_SCENE_ID,
        texture_index=writer_module.TEXTURE_INDEX,
        width=64,
        height=64,
        format_name=writer_module.FORMAT_NAME,
        rgba_sha256=writer_module.STOCK_RGBA_SHA256,
        png_sha256=writer_module.STOCK_PNG_SHA256,
        png_path=Path("private-user-cache/cement01.png"),
        mapped_material_names=(writer_module.TARGET_MATERIAL_NAME,),
        mapped_material_count=1,
        access_status="Editable",
    )
    writer = object.__new__(writer_module.Nfl2k5StadiumTextureWriter)
    require(writer.supports(texture), "Stadium P8 writer rejected its exact contract")
    require(
        not writer.supports(replace(texture, width=128))
        and writer_module._mip_dimensions(128, 64, 4)
        == ((128, 64), (64, 32), (32, 16), (16, 8)),
        "Stadium P8 occurrence/dimension boundary changed",
    )
    # The writer source itself is SHA-pinned below.  This marker is its
    # fail-closed private-catalog total; the private rows never ship.
    source_text = Path(writer_module.__file__).read_text(encoding="utf-8")
    require(
        f"len(textures) == {EXPECTED_PRIVATE_STADIUM_TEXTURES:_}"
        in source_text,
        "Stadium private editable-count contract changed",
    )
    geometry_payload = STADIUM_GEOMETRY_CATALOG.read_bytes()
    geometry_catalog = json.loads(geometry_payload)
    require(
        len(geometry_payload) == writer_module.GEOMETRY_CATALOG_SIZE
        and hashlib.sha256(geometry_payload).hexdigest()
        == writer_module.GEOMETRY_CATALOG_SHA256
        and geometry_catalog.get("schema")
        == writer_module.GEOMETRY_CATALOG_SCHEMA
        and len(geometry_catalog.get("targets", ())) == 75
        and callable(writer_module.compile_stadium_geometry_recipe)
        and callable(writer_module.build_unified_stadium_geometry_import)
        and callable(
            writer_module.build_unified_stadium_geometry_and_texture_import
        ),
        "Stadium same-topology geometry-import contract changed",
    )


def _exercise_playbook(playbook_module: object, panel_module: object) -> None:
    """Parse and filter a retail-free PLAY-shaped synthetic resource."""

    body = bytearray(playbook_module.BODY_SIZE)
    body[0x0C:0x10] = b"PLAY"
    body[0x20:0x28] = b"p\0l\0b\0\0\0"
    struct.pack_into("<IIII", body, 0x34, 1, 1, 1, 2)

    def relative(field: int, target: int) -> None:
        struct.pack_into("<i", body, field, target - field + 1)

    for field, target in (
        (0x44, playbook_module.FORMATION_BASE),
        (0x48, playbook_module.FORMATION_AUX_BASE),
        (0x60, playbook_module.PLAY_BASE),
        (0x64, playbook_module.CATEGORY_BASE),
        (0x68, playbook_module.NODE_BASE),
    ):
        relative(field, target)

    cursor = playbook_module.STRING_BASE
    names: dict[str, int] = {}
    for value in ("TEST", "I Pro", "Quick Out", "Ace"):
        names[value] = cursor
        payload = value.encode("utf-16le") + b"\0\0"
        body[cursor:cursor + len(payload)] = payload
        cursor += len(payload)
    relative(0x30, names["TEST"])
    relative(playbook_module.FORMATION_BASE, names["I Pro"])
    relative(playbook_module.PLAY_BASE, names["Quick Out"])
    relative(playbook_module.CATEGORY_BASE, names["Ace"])

    for slot in range(playbook_module.ASSIGNMENT_COUNT):
        assignment = playbook_module.PLAY_BASE + 8 + slot * 8
        struct.pack_into("<I", body, assignment, 0x1000 + slot)
        relative(assignment + 4, playbook_module.NODE_BASE)
    body[playbook_module.NODE_BASE:playbook_module.NODE_BASE + 16] = bytes(
        (0x01, 0x00, 1, 2, 3, 4, 5, 6,
         0x04, 0x02, 7, 8, 9, 10, 11, 12)
    )
    for index in range(playbook_module.FORMATION_PLAY_LINKS):
        struct.pack_into(
            "<H", body, playbook_module.FORMATION_AUX_BASE + index * 2, 0x01FF
        )
    struct.pack_into("<H", body, playbook_module.FORMATION_AUX_BASE, 0)

    wrapper = bytearray(playbook_module.RESOURCE_HEADER_SIZE)
    wrapper[:4] = b"PLAY"
    struct.pack_into("<I", wrapper, 4, playbook_module.BODY_SIZE)
    book = playbook_module.parse_playbook_resource(
        bytes(wrapper + body), asset_id="synthetic.PLAY", outer_index=0
    )
    require(
        playbook_module.corpus_counts((book,)) == {
            "books": 1,
            "formations": 1,
            "plays": 1,
            "categories": 1,
            "chains": 1,
            "nodes": 2,
            "slot_references": 11,
        },
        "PLAY structured parser contract changed",
    )
    filtered = panel_module.filter_playbooks(
        (book,), search="quick out", family_id=0
    )
    require(
        filtered.match_total == 1
        and panel_module.playbook_action_state(
            book, source_ready=True, busy=False
        ).can_export,
        "PLAY inspector filter/export state changed",
    )


def _exercise_scorebug(adapter: object) -> None:
    """Run the unified adapter with a byte-small synthetic typed importer."""

    replacement = b"\x10\x20"
    preview = b"synthetic-user-preview"

    def importer(_index: Path, _audit: Path, target: str, _png: Path):
        return replacement, preview, {
            "schema": adapter.SCOREBUG_IMPORT_SCHEMA,
            "target": {
                "name": target,
                "width": 64,
                "height": 64,
                "pack_path": "private/source-cache/0",
                "xiso_pack_sector": 2,
                "xiso_pack_byte_offset": 4096,
                "pack_size": 8192,
                "pack_sha256": "0" * 64,
                "pack_offset": 128,
                "xiso_absolute_span_offset": 4224,
                "span_size": len(replacement),
                "span_sha256": "1" * 64,
            },
            "rebuild": {
                "span_size": len(replacement),
                "span_sha256": hashlib.sha256(replacement).hexdigest(),
                "changed_runs": [[0, 1]],
                "changed_byte_count": 2,
            },
            "preview": {
                "file_name": "preview.png",
                "sha256": hashlib.sha256(preview).hexdigest(),
                "width": 64,
                "height": 64,
            },
            "claims": {
                "fixed_span_only": True,
                "originals_modified": False,
                "xiso_created": False,
            },
        }

    result = adapter.build_scorebug_texture_import(
        Path("private-index.json"),
        Path("reviewed-scorebug-audit.json"),
        {
            "kind": "scorebug_texture",
            "target": "score_buga",
            "png": "user-authored-scorebug.png",
        },
        importer=importer,
    )
    rebuilt, previews, report, selector, target = result
    require(rebuilt == replacement and previews == [("preview.png", preview)],
            "unified scorebug adapter changed compiled bytes")
    require(selector == "score_buga" and target["xiso_pack_size"] == 8192,
            "unified scorebug adapter aliases changed")
    require(report["unified_adapter"]["retail_bytes_embedded"] is False,
            "unified scorebug adapter safety claim changed")


def _exercise_product_inspections(
    facade_module: object, gameplay_panel_module: object, menus_panel_module: object,
) -> None:
    """Prove the staged product snapshots support both specialized inspectors."""

    gameplay = facade_module.collect_nfl2k5_gameplay_inspection()
    gameplay_model = gameplay_panel_module.build_gameplay_inspection_model(gameplay)
    require(
        len(gameplay_model.sliders) == 21
        and len(gameplay_model.draft_weights) == 17
        and len(gameplay_model.save_containers) == 8
        and len(gameplay_model.franchise_findings) == 5,
        "Gameplay product-inspection snapshot changed",
    )
    require(
        b"fantasy_draft_weight"
        in facade_module.serialize_gameplay_inspection_csv(gameplay),
        "Gameplay CSV export contract changed",
    )

    menu = facade_module.collect_nfl2k5_main_menu_inspection()
    menu_model = menus_panel_module.build_main_menu_inspection_model(menu)
    require(
        len(menu_model.transitions) == 7
        and len(menu_model.layouts) == 2
        and len(menu_model.blockers) == 3,
        "Main Menu product-inspection snapshot changed",
    )
    require(
        b"main_menu_transition"
        in facade_module.serialize_main_menu_inspection_csv(menu),
        "Main Menu CSV export contract changed",
    )


def _exercise_default_provider_controller(
    controller_module: object, provider_module: object, registry: object,
) -> None:
    """Construct the real default provider path so lazy imports cannot be omitted."""

    controller = controller_module.ModEditorController(registry)
    require(
        isinstance(controller.providers, provider_module.ProviderOrchestrator),
        "default ModEditorController omitted the ProviderOrchestrator",
    )
    require(
        controller.provider_supported(
            "apf2k8.scorebug_presentation.digital_font"
        )
        and controller.providers.provider_id(
            "apf2k8.scorebug_presentation.digital_font"
        ) == "apf2k8-digital-font-v1",
        "default provider closure omitted the lazy APF digital_font provider",
    )


def _exercise_universal(universal_module: object) -> None:
    """Normalize one metadata-only resource row without any game payload."""

    record = universal_module._normalize_row({
        "outer_index": 0,
        "outer_id": "0x00000001",
        "outer_head": "TEST",
        "outer_size": 64,
        "chunk_index": 1,
        "chunk_offset": 0,
        "zero_padding_before": 0,
        "kind": "TEST",
        "stored_size": 8,
        "end_offset": 40,
        "word_08": 0,
        "word_0c": 0,
        "word_10": "0x00000000",
        "word_14": 0,
    })
    require(record.raw_size == 40 and record.suggested_filename.endswith("_TEST.bin"),
            "universal asset metadata normalization changed")


def _exercise_workspace_recovery(workspace_module: object) -> None:
    """Prove recent-file and recovery state without retail or GUI access."""

    with tempfile.TemporaryDirectory(prefix="2k5-mod-studio-runtime-") as temporary:
        private_root = Path(temporary) / "state"
        source = Path(temporary) / "synthetic-user-source.xiso"
        source_payload = b"synthetic source placeholder; never retail data"
        source.write_bytes(source_payload)
        source_digest = hashlib.sha256(source_payload).hexdigest()

        store = workspace_module.WorkspaceStateStore(private_root)
        store.record_source(source, source_digest)
        recovery_payload = b"synthetic replacement-only project placeholder"
        store.recovery_path.write_bytes(recovery_payload)
        store.register_recovery(
            source_path=source,
            source_sha256=source_digest,
            project_path=store.recovery_path,
        )
        candidate = store.recovery_candidate()
        state_payload = store.state_path.read_bytes()
        require(
            candidate is not None
            and candidate.source_path == source.resolve(strict=True)
            and candidate.source_sha256 == source_digest
            and candidate.project_path == store.recovery_path
            and source_payload not in state_payload
            and recovery_payload not in state_payload,
            "workspace recovery/source-binding contract changed",
        )
        store.clear_recovery()
        require(
            store.recovery_candidate() is None
            and not store.recovery_path.exists()
            and store.read().recent_sources == (str(source.resolve(strict=True)),),
            "workspace recovery cleanup/recent-source contract changed",
        )


def _exercise_team_kit(
    team_kit_module: object, uniform_catalog: object, facade: object,
) -> None:
    """Exercise the retail-free Team Kit selection and manifest contracts."""

    sets = team_kit_module.select_team_uniform_sets(
        uniform_catalog, asset_code="18", variant=0, sides="BOTH"
    )
    require(
        tuple(item.selector for item in sets) == ("18H0", "18A0"),
        "Team Kit HOME/AWAY selection contract changed",
    )
    assets = tuple(
        asset
        for uniform_set in sets
        for asset in uniform_catalog.assets_for_set(uniform_set.selector)
    )
    paths = tuple(team_kit_module._component_relative(asset) for asset in assets)
    require(
        len(assets) == 78
        and len(set(paths)) == 78
        and all(path.startswith("SETS/") and path.endswith(".png") for path in paths),
        "Team Kit complete-set path contract changed",
    )
    guide = team_kit_module._guide(sets).decode("utf-8")
    require(
        "private working export" in guide
        and "do not upload or distribute" in guide
        and "one Undo action" in guide
        and ".2k5mod" in guide,
        "Team Kit retail/private/Undo guidance changed",
    )
    service = team_kit_module.TeamKitBundleService(uniform_catalog, object())
    require(
        service.catalog is uniform_catalog
        and callable(getattr(facade, "export_team_kit_sets", None))
        and callable(getattr(facade, "export_team_kit", None))
        and callable(getattr(facade, "import_team_kit", None)),
        "Team Kit service or facade routes are missing",
    )


def _exercise_texture_master(texture_master: object) -> None:
    """Round-trip a retail-free master with one native-canvas edit."""

    from PIL import Image

    with tempfile.TemporaryDirectory(prefix="2k5-runtime-master-") as name:
        root = Path(name)
        source = root / "user-source.png"
        Image.new("RGBA", (32, 16), (20, 80, 140, 255)).save(source)
        baseline = root / "baseline.png"
        Image.new("RGBA", (8, 8), (20, 80, 140, 255)).save(baseline)
        final = root / "final.png"
        edited = Image.open(baseline).copy()
        edited.putpixel((1, 2), (255, 20, 90, 128))
        edited.save(final)
        archive = texture_master.save_texture_master_bundle(
            source_image=source,
            destination=root / "fixture.2ktexmaster",
            asset_id="runtime.user.texture",
            editor_target="nfl2k5_xbox",
            native_width=8,
            native_height=8,
            compiled_native_png=final,
            compiled_native_baseline_png=baseline,
            high_resolution_scale=2,
            editor_transform={"operation": "runtime-native-edit"},
        )
        loaded = texture_master.load_texture_master_bundle(archive)
        require(
            loaded.manifest["native_raster_edit"]["changed_pixel_count"] == 1
            and loaded.native_png == final.read_bytes()
            and loaded.native_baseline_png == baseline.read_bytes(),
            "high-resolution texture-master runtime contract changed",
        )


def main() -> int:
    require(REPORTS.is_dir() and not REPORTS.is_symlink(),
            "reviewed target metadata directory is missing")
    actual_reports = {
        path.name for path in REPORTS.iterdir()
        if path.is_file() and not path.is_symlink()
    }
    require(actual_reports == REQUIRED_REPORTS,
            "release reports/assets must contain only the twelve reviewed metadata files")
    require(not os.path.lexists(REPORTS / PRIVATE_INVENTORY),
            "private 55 MiB user-XISO inventory was included in the release")
    require(COMPACT_CRIB.is_file() and not COMPACT_CRIB.is_symlink(),
            "compact retail-free Crib catalog is missing")
    require(
        COMPACT_UNIFORM_EQUIPMENT.is_file()
        and not COMPACT_UNIFORM_EQUIPMENT.is_symlink(),
        "compact uniform-equipment export catalog is missing",
    )
    require(
        STADIUM_GEOMETRY_CATALOG.is_file()
        and not STADIUM_GEOMETRY_CATALOG.is_symlink(),
        "bounded Stadium geometry catalog is missing",
    )
    for forbidden in ("extracted", "assets", "cache", "derived"):
        require(not os.path.lexists(ROOT / forbidden),
                f"private or retail-derived {forbidden} data was included in the release")

    product_modules = (
        "mod_editor.__main__",
        "mod_editor.core.capabilities",
        "mod_editor.core.controller",
        "mod_editor.core.image_fit",
        "mod_editor.core.product_catalog",
        "mod_editor.core.texture_master",
        "mod_editor.core.nfl2k5_source_cache",
        "mod_editor.core.nfl2k5_asset_io",
        "mod_editor.core.nfl2k5_uniform_catalog",
        "mod_editor.core.nfl2k5_extended_visual_catalog",
        "mod_editor.core.nfl2k5_extended_visual_io",
        "mod_editor.core.nfl2k5_build_service",
        "mod_editor.core.nfl2k5_text_catalog",
        "mod_editor.core.nfl2k5_safe_text_banks",
        "mod_editor.core.nfl2k5_audio_catalog",
        "mod_editor.core.nfl2k5_audio_containment_fingerprints",
        "mod_editor.core.nfl2k5_audio_origin_authorization",
        "mod_editor.core.nfl2k5_audio_origin_preparation",
        "mod_editor.core.nfl2k5_audio_source_containment",
        "mod_editor.core.nfl2k5_audio_source_fingerprints",
        "mod_editor.core.nfl2k5_audio_source_scan",
        "mod_editor.core.nfl2k5_audo_fixed_slots",
        "mod_editor.core.nfl2k5_ausb_build_adapter",
        "mod_editor.core.nfl2k5_ausb_fixed_slots",
        "mod_editor.core.nfl2k5_crib",
        "mod_editor.core.nfl2k5_formation_play_writer",
        "nfl2k5_ps2_save_verify",
        "nfl2k5_ps2_save",
        "mod_editor.core.ps2_save_service",
        "mod_editor.gui.ps2_save_dialog_qt",
        "mod_editor.core.nfl2k5_playbook_inspector",
        "mod_editor.core.playbook_package_rule_spike",
        "mod_editor.core.nfl2k5_universal_asset_index",
        "mod_editor.core.nfl2k5_scorebug_unified_adapter",
        "mod_editor.core.nfl2k5_stadium_cache",
        "mod_editor.core.nfl2k5_stadium_studio",
        "mod_editor.core.nfl2k5_stadium_texture_writer",
        "mod_editor.core.nfl_audio",
        "mod_editor.core.nfl_audio_provider",
        "mod_editor.core.providers",
        "mod_editor.studio.audio_annotations",
        "mod_editor.studio.project_archive",
        "mod_editor.studio.session",
        "mod_editor.studio.audio_replacement_pack",
        "mod_editor.studio.uniform_bundle",
        "mod_editor.studio.facade",
        "mod_editor.studio.workspace_state",
        "mod_editor.gui.audio_panel_qt",
        "mod_editor.gui.audio_waveform_qt",
        "mod_editor.gui.crib_panel_qt",
        "mod_editor.gui.gameplay_panel_qt",
        "mod_editor.gui.menus_panel_qt",
        "mod_editor.gui.playbooks_panel_qt",
        "mod_editor.gui.stadium_viewer",
        "mod_editor.core.nfl2k5_models",
        "mod_editor.core.self_update",
        "mod_editor.core.nfl2k5_team_column",
        "mod_editor.core.nfl2k5_rdata_sites",
        "mod_editor.core.nfl2k5_position_row",
        "mod_editor.core.nfl2k5_probowl_order",
        "mod_editor.core.nfl2k5_penalties",
        "mod_editor.core.nfl2k5_uniform_choice",
        "mod_editor.core.nfl2k5_franchise_practice",
        "mod_editor.core.nfl2k5_kick_laces",
        "mod_editor.core.nfl2k5_team_history",
        "mod_editor.core.nfl2k5_prospect_names",
        "mod_editor.core.nfl2k5_seven_on_seven",
        "mod_editor.core.nfl2k5_boot_logo",
        "mod_editor.core.nfl2k5_seven_on_seven_book",
        "mod_editor.gui.models_panel_qt",
        "mod_editor.gui.text_rosters_panel",
        "mod_editor.gui.studio_qt",
    )
    for relative, expected_sha256 in RC29_AUDIO_ANNOTATION_RUNTIME_PINS.items():
        supplied = ROOT / relative
        require(
            supplied.is_file()
            and not supplied.is_symlink()
            and hashlib.sha256(supplied.read_bytes()).hexdigest()
            == expected_sha256,
            f"RC29 Audio annotation runtime pin changed: {relative}",
        )

    modules = {name: importlib.import_module(name) for name in product_modules}
    _exercise_texture_master(modules["mod_editor.core.texture_master"])

    tool_modules = (
        "apf_inner",
        "apf_outer",
        "nfl_resource_scan",
        "nfl2k5_visual_mod_project",
        "nfl_jersey_tset_targets",
        "nfl_sleeve_tset_targets",
        "nfl_pants_tset_targets",
        "nfl_live_helmet_txtr_targets",
        "nfl_live_numbers_nameplate_targets",
        "nfl_team_select_card_targets",
        "nfl_roster",
        "nfl_scorebug_png_import",
        "nfl_audo_wav_xiso_workflow",
        "nfl_crib_bar_monitor_png_xiso",
        "nfl_crib_team_photo_png_import",
        "nfl_crib_team_photo_targets",
        "nfl_scne_embedded_texture_png",
        "nfl_scne_gltf",
        "nfl_scne_inventory",
        "nfl_stadium_studio_cache",
        "nfl_static_gltf",
        "string_table_inventory",
    )
    loaded = {name: importlib.import_module(name) for name in tool_modules}

    capabilities_module = modules["mod_editor.core.capabilities"]
    product_catalog_module = modules["mod_editor.core.product_catalog"]
    registry = capabilities_module.CapabilityRegistryLoader().load(
        allow_sample_fallback=False,
        check_files=False,
    )
    product_catalog = product_catalog_module.build_nfl2k5_product_catalog(registry)
    require(len(registry.capabilities) == 70,
            "canonical capability registry row count changed")
    require(len(product_catalog.sections) == 12,
            "product sidebar category count changed")
    require(len(product_catalog.capabilities) == 32,
            "NFL 2K5 product capability count changed")
    _exercise_default_provider_controller(
        modules["mod_editor.core.controller"],
        modules["mod_editor.core.providers"],
        registry,
    )

    catalog_module = modules["mod_editor.core.nfl2k5_uniform_catalog"]
    uniform_catalog = catalog_module.Nfl2k5UniformCatalog.load()
    require(len(uniform_catalog.uniform_sets) == 634,
            "uniform catalog set count changed")
    require(len(uniform_catalog.assets) == 24_726,
            "uniform catalog asset count changed")
    require(len(uniform_catalog.assets_for_set("18H0")) == 39,
            "Giants home uniform component count changed")
    _exercise_per_uniform_colour_project(
        loaded["nfl2k5_visual_mod_project"]
    )
    require(
        all(
            hasattr(modules["mod_editor.studio.session"].StudioSession, member)
            and hasattr(
                modules["mod_editor.studio.facade"].Nfl2k5StudioFacade, member
            )
            for member in (
                "uniform_colors", "set_uniform_colors", "clear_uniform_colors",
            )
        )
        and modules["mod_editor.studio.project_archive"].MAX_UNIFORM_COLOR_EDITS
        == 634,
        "per-uniform colour GUI/session/project closure changed",
    )

    visual_module = modules["mod_editor.core.nfl2k5_extended_visual_catalog"]
    visual_catalog = visual_module.load_nfl2k5_product_visual_catalog()
    require(len(visual_catalog.extended.assets) == 47_237,
            "extended visual asset count changed")
    require(len(visual_catalog.assets) == 71_963,
            "complete visual asset count changed")
    scorebug = next(
        asset for asset in visual_catalog.extended.assets
        if asset.scorebug_target == "score_buga"
    )
    require(
        scorebug.provider_edit("user-scorebug.png") == {
            "kind": "scorebug_texture",
            "png": "user-scorebug.png",
            "target": "score_buga",
        },
        "extended scorebug asset no longer routes through the unified project",
    )
    equipment = next(
        asset for asset in visual_catalog.extended.assets
        if asset.kind == "uniform_equipment_texture"
        and asset.texture == "socks00"
    )
    require(
        equipment.editable
        and equipment.provider_edit("user-socks.png") == {
            "asset_id": equipment.asset_id,
            "kind": "uniform_equipment_texture",
            "png": "user-socks.png",
        },
        "package-local equipment no longer routes through the unified project",
    )

    crib_module = modules["mod_editor.core.nfl2k5_crib"]
    crib_catalog = crib_module.load_nfl2k5_crib_catalog()
    editable_crib = tuple(asset for asset in crib_catalog.assets if asset.editable)
    editable_scenes = tuple(
        asset for asset in editable_crib
        if asset.storage is crib_module.CribStorage.SCENE_EMBEDDED
    )
    require(
        len(crib_catalog.assets) == len(editable_crib) == 498
        and len(editable_scenes) == 188,
            "compact Crib catalog coverage changed")
    photo = next(
        asset for asset in editable_crib
        if asset.selector.startswith("crib_team_photo:")
    )
    crib_edit = photo.provider_edit("user-crib-photo.png")
    require(crib_edit["kind"] == "crib_team_photo" and len(crib_edit) == 3,
            "Crib photo logical provider route changed")
    standalone = crib_catalog.by_selector("crib_item_texture:00_helmet")
    require(
        standalone.provider_edit("user-crib-item.png") == {
            "kind": "crib_standalone_texture",
            "png": "user-crib-item.png",
            "selector": "crib_item_texture:00_helmet",
        },
        "Crib standalone logical provider route changed",
    )
    bar_monitor = crib_catalog.get(crib_module.BAR_MONITOR_ASSET_ID)
    require(
        bar_monitor.provider_edit("user-bar-monitor.png") == {
            "kind": "crib_scene_texture",
            "png": "user-bar-monitor.png",
            "selector": crib_module.BAR_MONITOR_SELECTOR,
        },
        "Crib bar-monitor logical provider route changed",
    )

    _exercise_text(modules["mod_editor.core.nfl2k5_text_catalog"])
    _exercise_safe_fixed_text(
        modules["mod_editor.core.nfl2k5_safe_text_banks"]
    )
    _exercise_audio(
        modules["mod_editor.core.nfl_audio"],
        loaded["nfl_audo_wav_xiso_workflow"],
    )
    _exercise_fixed_audo(
        modules["mod_editor.core.nfl2k5_audo_fixed_slots"],
        modules["mod_editor.core.nfl2k5_audio_catalog"],
    )
    audio_catalog_module = modules["mod_editor.core.nfl2k5_audio_catalog"]
    audio_panel_module = modules["mod_editor.gui.audio_panel_qt"]
    audio_waveform_module = modules["mod_editor.gui.audio_waveform_qt"]
    crib_panel_module = modules["mod_editor.gui.crib_panel_qt"]
    studio_gui_module = modules["mod_editor.gui.studio_qt"]
    _exercise_audio_waveform(audio_waveform_module)
    _exercise_playable_audio_catalog(audio_catalog_module, audio_panel_module)
    require(
        audio_panel_module.MAX_SHORTLIST_SIZE == 256,
        "Audio all-matching shortlist limit changed",
    )
    require(
        audio_panel_module.AUDIO_DETAIL_MIN_WIDTH == 320
        and audio_panel_module.AUDIO_DETAIL_SCROLL_MIN_HEIGHT == 120
        and audio_panel_module.AUDIO_DETAIL_LAYOUT_CONTRACT
        == "scrollable_pinned_actions",
        "Audio scrollable-detail layout contract changed",
    )
    require(
        audio_panel_module.AUDIO_TOOLBAR_TARGET_WIDTH == 930
        and audio_panel_module.AUDIO_TOOLBAR_LAYOUT_CONTRACT == "two_row_930",
        "Audio two-row toolbar layout contract changed",
    )
    require(
        audio_panel_module.AUDIO_PREVIEW_LIFECYCLE_CONTRACT
        == "selection_source_epoch_owned_process"
        and not hasattr(audio_panel_module, "QDesktopServices"),
        "Audio selection/source-bound preview lifecycle changed",
    )
    require(
        audio_panel_module.AUDIO_WAVEFORM_LIFECYCLE_CONTRACT
        == "explicit_read_only_session_wav"
        and audio_panel_module.AUDIO_MEDIA_INVALIDATION_CONTRACT
        == "selection_source_content_owned"
        and callable(
            getattr(audio_panel_module.AudioPanel, "invalidate_audio_content", None)
        ),
        "Audio waveform/content invalidation lifecycle changed",
    )
    require(
        studio_gui_module.EMBEDDED_AUDIO_TASK_CONTRACT
        == "global_action_guarded_until_drain"
        and studio_gui_module.EMBEDDED_OPERATION_TASK_CONTRACT
        == "audio_crib_mutually_exclusive_until_drain"
        and hasattr(audio_panel_module.AudioPanel, "operation_state_changed")
        and isinstance(
            getattr(audio_panel_module.AudioPanel, "operation_in_progress", None),
            property,
        )
        and hasattr(crib_panel_module.CribPanel, "operation_state_changed")
        and isinstance(
            getattr(crib_panel_module.CribPanel, "operation_in_progress", None),
            property,
        )
        and callable(
            getattr(studio_gui_module.StudioMainWindow,
                    "_refuse_while_audio_busy", None)
        ),
        "embedded Audio task admission contract changed",
    )
    require(
        audio_panel_module.AUDIO_QUERY_LIFECYCLE_CONTRACT
        == "applied_token_debounce_guarded",
        "Audio applied-query debounce lifecycle changed",
    )
    require(
        audio_panel_module.AUDIO_SHORTLIST_CLEAR_CONTRACT
        == "one_level_ordered_restore"
        and audio_panel_module.AUDIO_SOURCE_FAILURE_CONTRACT
        == "transactional_old_catalog_restore",
        "Audio shortlist/source-recovery lifecycle changed",
    )
    _exercise_audio_annotations(
        modules["mod_editor.studio.audio_annotations"],
        modules["mod_editor.studio.project_archive"],
        modules["mod_editor.studio.session"],
        modules["mod_editor.studio.facade"],
        audio_panel_module,
    )
    _exercise_audio_replacement_preflight_contract(
        modules["mod_editor.studio.audio_replacement_pack"],
        modules["mod_editor.studio.session"],
        modules["mod_editor.studio.facade"],
        audio_panel_module,
    )
    _exercise_audio_replacement_pack_v2(
        modules["mod_editor.studio.audio_replacement_pack"],
        audio_catalog_module,
        modules["mod_editor.studio.facade"],
    )
    _exercise_audio_replacement_pack_v3(
        modules["mod_editor.studio.audio_replacement_pack"],
        audio_catalog_module,
    )
    require(
        audio_catalog_module.EXPECTED_STREAMING_BANK_COUNT == 17
        and audio_catalog_module.EXPECTED_STREAMING_RANGE_COUNT == 53_571
        and hasattr(audio_catalog_module, "Nfl2k5StreamingAudioRange")
        and hasattr(
            audio_catalog_module.Nfl2k5AudioService,
            "export_streaming_range_wav",
        )
        and hasattr(
            audio_catalog_module.Nfl2k5AudioService,
            "streaming_range_playback_path",
        )
        and hasattr(
            modules["mod_editor.core.nfl2k5_audio_origin_preparation"],
            "Nfl2k5AudioOriginPreparation",
        )
        and hasattr(audio_panel_module, "filter_audio_ranges")
        and sum(
            audio_panel_module._FAMILY_COUNTS["streaming_ranges"].values()
        ) == 53_571
        and sum(
            count for count in {
                "frontend_ui": 36,
                "field_crowd_player": 13,
                "team_crowd": 680,
                "crib_minigames": 121,
            }.values()
        ) == audio_catalog_module.EXPECTED_AUDIO_COUNT,
        "dedicated Audio browser coverage changed",
    )
    _exercise_scorebug(
        modules["mod_editor.core.nfl2k5_scorebug_unified_adapter"]
    )
    _exercise_universal(
        modules["mod_editor.core.nfl2k5_universal_asset_index"]
    )
    _exercise_workspace_recovery(
        modules["mod_editor.studio.workspace_state"]
    )
    _exercise_playbook(
        modules["mod_editor.core.nfl2k5_playbook_inspector"],
        modules["mod_editor.gui.playbooks_panel_qt"],
    )
    _exercise_product_inspections(
        modules["mod_editor.studio.facade"],
        modules["mod_editor.gui.gameplay_panel_qt"],
        modules["mod_editor.gui.menus_panel_qt"],
    )

    provider_module = modules["mod_editor.core.providers"]
    unified_provider = provider_module.Nfl2k5UnifiedVisualProvider(workspace=ROOT)
    require("scorebug_texture" in unified_provider.backend_known_kinds,
            "unified provider omitted the scorebug texture kind")
    require("crib_team_photo" in unified_provider.backend_known_kinds,
            "unified provider omitted the Crib photo kind")
    require("crib_scene_texture" in unified_provider.backend_known_kinds,
            "unified provider omitted the Crib scene-texture kind")
    require("crib_standalone_texture" in unified_provider.backend_known_kinds,
            "unified provider omitted the Crib standalone-texture kind")
    require("crib_scene_geometry" in unified_provider.backend_known_kinds,
            "unified provider omitted the Crib scene-geometry kind")
    require("play_assignment_route" in unified_provider.backend_known_kinds,
            "unified provider omitted the PLAY assignment-route kind")
    require("universal_fixed_text" in unified_provider.backend_known_kinds,
            "unified provider omitted the universal fixed-text kind")
    require("audo_audio" in unified_provider.backend_known_kinds,
            "unified provider omitted standalone fixed-AUDO kind")
    require("ausb_audio" in unified_provider.backend_known_kinds,
            "unified provider omitted fixed-range streaming-AUSB kind")
    require("stadium_texture" in unified_provider.backend_known_kinds,
            "unified provider omitted the Stadium texture kind")
    require("stadium_geometry" in unified_provider.backend_known_kinds,
            "unified provider omitted the Stadium geometry kind")
    require(
        REQUIRED_UNIFIED_PROVIDER_CLOSURE
        <= set(unified_provider.module_pins),
        "unified provider omitted a required v1 pinned module",
    )
    for relative, expected in {
        **unified_provider.module_pins,
        **unified_provider.data_pins,
    }.items():
        supplied = ROOT / relative
        require(supplied.is_file() and not supplied.is_symlink(),
                f"unified provider dependency is missing: {relative}")
        require(hashlib.sha256(supplied.read_bytes()).hexdigest() == expected,
                f"unified provider dependency pin changed: {relative}")

    stadium_module = modules["mod_editor.core.nfl2k5_stadium_cache"]
    _exercise_stadium_writer(
        modules["mod_editor.core.nfl2k5_stadium_texture_writer"],
        modules["mod_editor.core.nfl2k5_stadium_studio"],
    )
    coordinator = stadium_module.Nfl2k5StadiumCacheCoordinator()
    require(coordinator.worker == ROOT / "tools/nfl_stadium_studio_cache.py",
            "Stadium Studio private worker route changed")
    require(coordinator.worker.is_file() and not coordinator.worker.is_symlink(),
            "Stadium Studio private worker is missing")
    require(stadium_module.PRIVATE_PARENT == "derived"
            and stadium_module.EXPECTED_STADIUM_SCENES == 477,
            "Stadium Studio private-cache contract changed")

    facade_module = modules["mod_editor.studio.facade"]
    require(
        callable(getattr(facade_module.Nfl2k5StudioFacade,
                         "import_stadium_scene_gltf", None)),
        "Stadium edited-glTF facade route is missing",
    )
    facade = facade_module.Nfl2k5StudioFacade(
        uniform_catalog=uniform_catalog,
        visual_catalog=visual_catalog,
        xemu_command=(),
    )
    require(not facade.source_ready and facade.modified_count == 0,
            "fresh product facade state is invalid")
    require(
        isinstance(
            facade._stadium_cache_coordinator,
            stadium_module.Nfl2k5StadiumCacheCoordinator,
        ),
        "product facade omitted the private Stadium Studio coordinator",
    )
    _exercise_team_kit(
        modules["mod_editor.studio.uniform_bundle"], uniform_catalog, facade
    )

    # Exercise the installed desktop command's complete construction route
    # without opening a display or entering Qt's event loop.
    entry_module = modules["mod_editor.__main__"]
    gui_module = modules["mod_editor.gui.studio_qt"]
    captured: dict[str, object] = {}
    original_launch = gui_module.launch_studio

    def capture_launch(
        candidate: object,
        *,
        product_catalog: object,
        uniform_catalog: object,
        extended_visual_catalog: object,
    ) -> int:
        captured["facade"] = candidate
        captured["product_catalog"] = product_catalog
        captured["uniform_catalog"] = uniform_catalog
        captured["extended_visual_catalog"] = extended_visual_catalog
        return 73

    gui_module.launch_studio = capture_launch
    try:
        startup_result = entry_module.main(["--studio"])
    finally:
        gui_module.launch_studio = original_launch
    require(startup_result == 73,
            "desktop --studio route did not reach the Qt launch boundary")
    launched_facade = captured.get("facade")
    require(isinstance(launched_facade, facade_module.Nfl2k5StudioFacade),
            "desktop --studio route did not construct the product facade")
    require(captured.get("uniform_catalog") is not None,
            "desktop --studio route omitted the uniform catalog")
    require(len(getattr(captured.get("extended_visual_catalog"), "assets", ())) == 47_237,
            "desktop --studio route omitted the extended visual catalog")
    launched_catalog = captured.get("product_catalog")
    require(
        getattr(launched_catalog, "sections", ())
        and len(getattr(launched_catalog, "sections")) == 12,
        "desktop --studio route omitted the twelve-section product catalog",
    )
    require(
        isinstance(
            launched_facade._stadium_cache_coordinator,
            stadium_module.Nfl2k5StadiumCacheCoordinator,
        ),
        "desktop --studio route omitted the Stadium Studio coordinator",
    )

    # Exercise every legacy uniform target loader as well as all new product
    # adapters above.  No source image, decoded original, or retail bytes are
    # needed for this clean-stage closure probe.
    loaded["nfl_jersey_tset_targets"].select_target("18", "H", 0)
    loaded["nfl_sleeve_tset_targets"].select_target("18", "H", 0)
    loaded["nfl_pants_tset_targets"].select_target("18", "H", 0)
    loaded["nfl_live_helmet_txtr_targets"].select_target(
        "18", "H", 0, "helmet00"
    )
    loaded["nfl_live_numbers_nameplate_targets"].select_target(
        "jersey", "18", "H", 0, 0
    )
    loaded["nfl_team_select_card_targets"].select_target(
        "unif", "18", "home", 0, 256
    )

    print(
        "2K5_MOD_STUDIO_RUNTIME_CLOSURE_PASS "
        f"product_modules={len(product_modules)} tool_modules={len(tool_modules)} "
        "registry=70 sections=12 nfl2k5_capabilities=32 "
        "reports=16 reviewed_metadata=22 sets=634 visuals=71963 "
        "team_kit_sets=634 team_kit_assets_per_set=39 "
        "text_banks=716 text_strings=23346 text_editable=20074 "
        "text_read_only=3272 roster_numbers=6522 "
        "audio=850 audio_editable=850 audio_export_only=0 "
        "audio_streaming_banks=17 audio_streaming_ranges=53571 "
        "audio_streaming_wav_ranges=53571 "
        "audio_default_scope=playable_54421_standalone_then_ranges "
        "audio_replacement_pack_v2=selected_mixed "
        "audio_replacement_pack_v3=all_standalone_850 "
        "audio_replacement_pack_v4=all_standalone_850_mapped "
        "audio_pack_preflight=fully_validated_read_only_preview_then_explicit_apply "
        "audio_pack_import=validated_preview_token_apply "
        "audio_pack_path_lookup=canonical_850 "
        "audio_meaning_confidence=1_152_697 "
        "audio_annotations=project_metadata_only_searchable_54421 "
        "audio_add_all_matching=bounded_256 "
        "audio_detail_layout=scrollable_pinned_actions "
        "audio_toolbar_layout=two_row_930 "
        "audio_preview_lifecycle=selection_source_epoch_owned_process "
        "audio_query_lifecycle=applied_token_debounce_guarded "
        "audio_shortlist_clear=one_level_ordered_restore "
        "audio_source_failure=transactional_old_catalog_restore "
        "audio_waveform=explicit_read_only_session_wav "
        "audio_media_invalidation=selection_source_content_owned "
        "embedded_audio_task=global_action_guarded_until_drain "
        "embedded_operation_task=audio_crib_mutually_exclusive_until_drain "
        "audio_bundle_modified_range=user_wav "
        "crib=498 crib_editable=498 crib_standalone_editable=182 "
        "crib_scene_editable=188 crib_geometry=10_meshes_7_scenes_position_only "
        "stadium_scenes=477 stadium_textures_editable=23838 "
        "stadium_geometry=same_topology_position_only_private "
        "playbooks=37 formations=1533 plays=9251 chains=32502 "
        "play_nodes=91833 play_slot_refs=101761 "
        "play_assignment_route=same_book_stock_copy_only startup=connected "
        "texture_master=direct_source_with_native_edit_layer "
        "private_inventory=false retail=false generated_stadium=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(
            f"2K5_MOD_STUDIO_RUNTIME_CLOSURE_REFUSED: {exc}"
        ) from exc
