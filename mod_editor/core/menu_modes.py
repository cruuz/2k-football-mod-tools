"""Hash-pinned, named Main Menu ownership inspection.

The public result deliberately translates executable research into state,
row, layout, and blocker names.  It never returns virtual addresses, archive
offsets, or a mutation contract.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any

from .errors import ValidationError


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_DIR = ROOT / "reports/assets"
LOOKUP_SCHEMA = "mod_editor_named_main_menu_inspector/v1"


@dataclass(frozen=True)
class _ReportPin:
    filename: str
    schema: str
    size: int
    sha256: str


_REPORT_PINS = {
    "state": _ReportPin(
        "menu_state_trace.json",
        "vc_menu_state_trace/v1",
        39_938,
        "ecd93117a3a808a16697c23ae10e3225953bcb4dabda30afabdc5c02911974f1",
    ),
    "nfl_live": _ReportPin(
        "nfl_main_menu_live_state.json",
        "nfl2k5_main_menu_live_state/v1",
        18_483,
        "a5d4b64962fefb2e5dbee4768d120172c0642405df2a0137759e2bce3737b89a",
    ),
    "closure": _ReportPin(
        "menu_state_trace_closure_v2.json",
        "vc_menu_state_trace_closure/v2",
        22_417,
        "1145accb0a91cc0137cbf3757a0bff9d6a85a00a55ed41efa891e2a267c7788a",
    ),
    "apf_frontend": _ReportPin(
        "apf_frontend_main_ownership_v6.json",
        "vc_apf_frontend_main_ownership/v6",
        15_621,
        "8b5d6862486bb03909550402d51814ec24cec20694151886de9e4a0b6290ef19",
    ),
    "apf_labels": _ReportPin(
        "menu_label_renderer_v3.json",
        "vc_apf_menu_label_renderer/v3",
        33_170,
        "59f81323ba3edc5bbb0331c47998a1bfe15fc4246358863941fc54287e6f860b",
    ),
    "apf_text": _ReportPin(
        "quicknav_text_render_v4.json",
        "vc_apf_quicknav_text_render/v4",
        34_919,
        "b5b2bc068b918459dd96686665edeed5ca1edb033f1ef835c285b67bab34f591",
    ),
}


def _read_regular_file(path: Path, expected_size: int) -> bytes:
    try:
        supplied = path.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(f"Pinned menu evidence is missing: {path.name}") from exc
    if not stat.S_ISREG(supplied.st_mode) or stat.S_ISLNK(supplied.st_mode):
        raise ValidationError("Pinned menu evidence must be a non-symlink regular file")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (supplied.st_dev, supplied.st_ino):
            raise ValidationError("Pinned menu evidence identity changed while opening")
        if opened.st_size != expected_size:
            raise ValidationError("Pinned menu evidence size does not match")
        chunks: list[bytes] = []
        remaining = expected_size
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            if not block:
                raise ValidationError("Pinned menu evidence ended early")
            chunks.append(block)
            remaining -= len(block)
        if os.read(descriptor, 1):
            raise ValidationError("Pinned menu evidence grew while reading")
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
        ):
            raise ValidationError("Pinned menu evidence changed while reading")
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def _read_report(report_dir: Path, key: str) -> dict[str, Any]:
    pin = _REPORT_PINS[key]
    payload = _read_regular_file(report_dir / pin.filename, pin.size)
    if hashlib.sha256(payload).hexdigest() != pin.sha256:
        raise ValidationError(f"Pinned menu evidence hash mismatch: {pin.filename}")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Pinned menu evidence is not valid JSON: {pin.filename}") from exc
    if not isinstance(value, dict) or value.get("schema") != pin.schema:
        raise ValidationError(f"Pinned menu evidence schema mismatch: {pin.filename}")
    return value


def _evidence(keys: tuple[str, ...]) -> list[dict[str, str]]:
    return [
        {
            "report": _REPORT_PINS[key].filename,
            "sha256": _REPORT_PINS[key].sha256,
        }
        for key in keys
    ]


def _assert_equal(actual: Any, expected: Any, description: str) -> None:
    if actual != expected:
        raise ValidationError(f"Pinned menu evidence disagrees about {description}")


def _named_nfl_rows(
    rows: list[dict[str, Any]], transitions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    _assert_equal(len(rows), len(transitions), "NFL initialized row count")
    result = []
    for expected_index, (row, transition) in enumerate(zip(rows, transitions)):
        _assert_equal(row["index"], expected_index, "NFL row order")
        _assert_equal(transition["raw_index"], expected_index, "NFL transition row order")
        _assert_equal(transition["label"], row["label"], "NFL initialized row label")
        if row["target_title"] is not None:
            activation = {
                "kind": "push_target_state",
                "target": row["target_title"],
                "status": "proved",
            }
        else:
            _assert_equal(row["label"], "The Crib|TM|", "NFL callback-only row")
            activation = {
                "kind": "native_callback",
                "target": "The Crib",
                "status": "callback_owner_proved",
            }
        result.append(
            {
                "position": expected_index,
                "label": row["label"],
                "initially_drawable": transition["initial_drawable"],
                "activation": activation,
            }
        )
    return result


def _inspect_nfl(report_dir: Path) -> dict[str, Any]:
    keys = ("state", "nfl_live")
    state = _read_report(report_dir, "state")
    live = _read_report(report_dir, "nfl_live")
    menu = state["nfl2k5"]
    result = live["result"]
    source = live["source_pins"]

    _assert_equal(source["menu_state_report"]["sha256"], _REPORT_PINS["state"].sha256,
                  "NFL state-report pin")
    _assert_equal(menu["state_descriptor"]["title"], "Main Menu", "NFL state name")
    _assert_equal(result["construction_mode"], 0, "NFL constructed menu mode")
    _assert_equal(result["initial_selectable_rows"], 7, "NFL initial row count")
    _assert_equal(result["initial_selected_label"], "Quick Game",
                  "NFL initial selection")
    _assert_equal(result["default_layout_draw_call_if_loaded"], True,
                  "NFL default serialized-layout path")
    _assert_equal(result["default_direct_font_row_draw"], False,
                  "NFL default direct-font path")

    rows = _named_nfl_rows(
        menu["navigation_rows"],
        live["initialization_and_selection"]["initial_transitions"],
    )
    _assert_equal(all(row["initially_drawable"] for row in rows), True,
                  "NFL initially drawable rows")
    _assert_equal([row["label"] for row in rows],
                  live["upstream_joins"]["menu_state"]["labels"],
                  "NFL joined row labels")
    return {
        "schema": LOOKUP_SCHEMA,
        "game": "NFL 2K5",
        "platform": "original_xbox",
        "query": "main_menu",
        "read_only": True,
        "mutation_supported": False,
        "source_pin": {
            "file": "default.xbe",
            "sha256": source["xbe"]["sha256"],
        },
        "evidence": _evidence(keys),
        "state": {
            "name": "Main Menu",
            "descriptor_owned": True,
            "initial_selection": "Quick Game",
            "initial_selection_status": "proved_static_initialization",
            "cold_boot_reachability": "unproved",
            "rows": rows,
        },
        "layout_reachability": [
            {
                "layout": menu["state_loaded_layout_entry"]["layout_name"],
                "relation": "descriptor_selected",
                "status": "proved_if_resource_loaded",
            },
            {
                "layout": menu["navigation_child_entry"]["layout_name"],
                "relation": "serialized_child_of_main_menu_sub",
                "status": "proved",
            },
        ],
        "rendering": {
            "default_path": "serialized_layout",
            "alternate_direct_font_path_is_default": False,
            "logical_canvas": result["cpu_logical_canvas"],
            "physical_framebuffer_mapping": "unproved",
        },
        "known_blockers": [
            {
                "id": "cold_boot_predecessor",
                "status": "unproved",
                "needed": "retail runtime trace of the state installation and lifecycle survival",
            },
            {
                "id": "selected_row_visual",
                "status": "unproved",
                "needed": "loaded-layout frame trace linking selection to a timeline or primitive",
            },
            {
                "id": "physical_pixel_mapping",
                "status": "unproved",
                "needed": "Xbox GPU viewport, projection, and overscan recovery",
            },
        ],
    }


def _named_apf_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    action_names = {
        10: "preflight_then_native_callback",
        11: "state_stack_transition",
        12: "replace_like_transition",
    }
    result = []
    for expected_index, row in enumerate(rows):
        _assert_equal(row["index"], expected_index, "APF row order")
        row_type = row["type"]
        if row_type not in action_names:
            raise ValidationError("Pinned menu evidence contains an unknown APF row action")
        target = row["target_title"]
        if row_type == 10:
            _assert_equal(row["label"], "Xbox Live", "APF callback-only row")
            target = "Xbox Live service flow"
        result.append(
            {
                "position": expected_index,
                "label": row["label"],
                "activation": {
                    "kind": action_names[row_type],
                    "target": target,
                    "status": "proved",
                },
            }
        )
    return result


def _inspect_apf(report_dir: Path) -> dict[str, Any]:
    keys = ("state", "closure", "apf_frontend", "apf_labels", "apf_text")
    state = _read_report(report_dir, "state")
    closure = _read_report(report_dir, "closure")
    frontend = _read_report(report_dir, "apf_frontend")
    labels = _read_report(report_dir, "apf_labels")
    text = _read_report(report_dir, "apf_text")
    menu = state["apf2k8"]
    scope = frontend["scope"]

    _assert_equal(frontend["source"]["inputs"]["base_menu"]["sha256"],
                  _REPORT_PINS["state"].sha256, "APF state-report pin")
    _assert_equal(frontend["source"]["inputs"]["base_closure"]["sha256"],
                  _REPORT_PINS["closure"].sha256, "APF closure-report pin")
    _assert_equal(labels["provenance"]["v1_state_trace"]["sha256"],
                  _REPORT_PINS["state"].sha256, "APF label state-report pin")
    _assert_equal(labels["provenance"]["v2_report"]["sha256"],
                  _REPORT_PINS["closure"].sha256, "APF label closure-report pin")
    _assert_equal(text["provenance"]["base_menu_label_v3"]["sha256"],
                  _REPORT_PINS["apf_labels"].sha256, "APF text label-report pin")
    _assert_equal(menu["state_descriptor"]["title"], "Main Menu", "APF state name")
    _assert_equal(scope["main_direct_layout_is_quicknav_proved"], True,
                  "APF descriptor-selected layout")
    _assert_equal(scope["main_direct_layout_is_layout_mainmenu"], False,
                  "APF layout_mainmenu direct ownership")
    _assert_equal(scope["layout_mainmenu_runtime_instantiation_proved"], False,
                  "APF layout_mainmenu runtime instantiation")
    _assert_equal(scope["cold_boot_to_main_menu_proved"], False,
                  "APF cold-boot reachability")
    _assert_equal(scope["boot_frontend_sync_request_proved"], True,
                  "APF frontend bundle boot request")
    _assert_equal(labels["scope"]["main_label_content_provider_proved"], True,
                  "APF Main label content provider")
    _assert_equal(labels["scope"]["main_provider_localization_bypass_proved"], True,
                  "APF Main provider localization boundary")
    _assert_equal(labels["scope"]["main_visible_label_renderer_proved"], False,
                  "APF visible Main label renderer")
    _assert_equal(text["scope"]["provider_output_semantic_consumer_proved"], False,
                  "APF provider text semantic consumer")
    _assert_equal(text["scope"]["named_font_resource_proved"], False,
                  "APF named font resource")
    _assert_equal(text["scope"]["atlas_binding_proved"], False,
                  "APF font atlas binding")

    rows = _named_apf_rows(menu["navigation_rows"])
    routes = closure["apf2k8"]["main_routes"]
    route_count = len(routes["queue_or_route_sites"]) + 1
    _assert_equal(route_count, 8, "APF executable Main Menu route count")
    return {
        "schema": LOOKUP_SCHEMA,
        "game": "APF 2K8",
        "platform": "xbox_360",
        "query": "main_menu",
        "read_only": True,
        "mutation_supported": False,
        "source_pin": {
            "file": "default.xex",
            "sha256": frontend["source"]["xex_sha256"],
        },
        "evidence": _evidence(keys),
        "state": {
            "name": "Main Menu",
            "descriptor_owned": True,
            "proved_executable_route_count": route_count,
            "cold_boot_reachability": "unproved",
            "rows": rows,
        },
        "layout_reachability": [
            {
                "layout": frontend["main_direct_layout"]["descriptor_layout_name"],
                "archive": frontend["main_direct_layout"]["physical_resource"]["archive"],
                "relation": "descriptor_selected",
                "status": "proved",
            },
            {
                "layout": menu["state_loaded_layout_entry"]["records"][0]["primary_name"],
                "relation": "serialized_child_of_quicknav",
                "status": "proved",
            },
            {
                "layout": frontend["frontend_bundle"]["inner_name"],
                "archive": frontend["frontend_bundle"]["archive"],
                "relation": "boot_requested_bundle_member",
                "status": "runtime_instantiation_unproved",
                "direct_main_owner": False,
            },
        ],
        "labels": {
            "content_provider": "proved",
            "localization_bypass_on_proved_provider_path": True,
            "visible_label_renderer": "unproved",
            "provider_text_semantic_consumer": "unproved",
        },
        "known_blockers": [
            {
                "id": "cold_boot_to_main",
                "status": "unproved",
                "needed": "retail runtime trace proving which route constructs Main Menu",
            },
            {
                "id": "layout_mainmenu_instantiation",
                "status": "unproved",
                "needed": "runtime owner for the frontend_sync layout_mainmenu member",
            },
            {
                "id": "transition_policy_names",
                "status": "partially_proved",
                "needed": "runtime semantics for every state-stack policy and queue mode",
            },
            {
                "id": "visible_label_text_handoff",
                "status": "unproved",
                "needed": "provider-buffer-to-rendered-run edge or a runtime baked-text proof",
            },
            {
                "id": "font_and_atlas_identity",
                "status": "unproved",
                "needed": "named font resource and atlas binding",
            },
        ],
    }


def inspect_main_menu(game: str, report_dir: Path = DEFAULT_REPORT_DIR) -> dict[str, Any]:
    """Return a named Main Menu proof boundary for one supported title."""

    if not isinstance(game, str):
        raise ValidationError("Main Menu game must be nfl2k5 or apf2k8")
    normalized = game.strip().lower()
    if normalized == "nfl2k5":
        return _inspect_nfl(report_dir)
    if normalized == "apf2k8":
        return _inspect_apf(report_dir)
    raise ValidationError("Main Menu game must be nfl2k5 or apf2k8")


__all__ = ["DEFAULT_REPORT_DIR", "LOOKUP_SCHEMA", "inspect_main_menu"]
