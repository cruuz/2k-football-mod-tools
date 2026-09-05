"""Product catalog and export services for NFL 2K5 audio.

The game contains 850 indexed ``AUDO`` resources.  This module joins the
metadata-only ownership audit shipped with Mod Studio to the resource index in
the user's private source cache.  PCM is decoded only when the user previews or
exports a sound, and decoded retail audio never enters a shareable project or
the public application package.

All 849 non-Menu-Back rows use stable outer/chunk identity and the composed
fixed-allocation writer. The legacy exact physical ``menu-back_01`` slot keeps
its separate provider route. Duplicate names or decoded content never collapse
distinct physical spans, but each generic row warns that semantic cue identity
and runtime selector ownership may still be unknown.

The same private index owns 17 ``AUSB`` descriptors, 16 external streaming
banks, and 53,571 indexed ranges used by soundtrack, commentary, stadium, and
presentation audio. Every bank and exact range is searchable and raw ``.bin``
exportable. All ranges are proved Xbox IMA ADPCM and can be played or exported
privately as PCM16 WAV. All 53,571 logical ranges now expose fixed-allocation
replacement through 53,570 reviewed physical slots, including one two-owner
alias whose logical cues change together. Whole-bank replacement/repacking is
still unavailable, and runtime cue identity/consumption remains unproved.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
from typing import Any, Callable, Iterable
import warnings
import wave
import zlib

from . import platform_compat
from .errors import ValidationError
from .json_stream import (
    file_contains_bytes,
    iter_top_level_array,
    read_bounded_regular_file,
    require_regular_file,
)
from .nfl2k5_audo_family_labels import (
    AudoFamilyLabelPromotion,
    FAMILY_LABEL_REPORT,
    FAMILY_LABEL_REPORT_SHA256,
    load_family_label_promotions,
)
from .nfl2k5_audo_fixed_slots import (
    EDITABLE_CLASSIFICATION,
    generic_fixed_slot_warning,
)
from .nfl2k5_source_cache import SOURCE_SHA256, SourceCache
from .nfl_audio import (
    NFL_MENU_BACK_AUDIO_CHANNELS,
    NFL_MENU_BACK_AUDIO_FRAME_COUNT,
    NFL_MENU_BACK_AUDIO_SAMPLE_RATE,
    NFL_MENU_BACK_AUDIO_TARGET,
    create_nfl_menu_back_audio_recipe,
)
from .nfl2k5_ausb_fixed_slots import (
    CanonicalStreamingSlot,
    Nfl2k5AusbFixedSlotError,
    StreamingSlotCatalog,
    build_streaming_slot_catalog,
)


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from nfl_outer import FormatError, parse_archive, read_entry_range  # noqa: E402
from nfl_scene_probe import (  # noqa: E402
    ProbeError,
    ResourceRecord,
    decode_resource,
    decode_xbox_ima,
    named_inner,
    probe_audo,
    utf16z,
)


CAPACITY_REPORT = ROOT / "reports/assets/nfl2k5_audo_import_capacity.json"
CAPACITY_REPORT_SCHEMA = "nfl2k5_audo_import_capacity/v1"
CAPACITY_REPORT_SHA256 = (
    "1d9ebb31a8822d113ae0fc8ec028e4ff652ccb7cbcf9d6d1d870aa58ef65f556"
)
EXPECTED_AUDIO_COUNT = 850
EXPECTED_STREAMING_BANK_COUNT = 17
EXPECTED_STREAMING_RANGE_COUNT = 53_571
EXPECTED_PLAYABLE_AUDIO_COUNT = EXPECTED_AUDIO_COUNT + EXPECTED_STREAMING_RANGE_COUNT
PLAYABLE_AUDIO_SCOPE_ID = "playable"
EXPORT_CAPABILITY_ID = "nfl2k5.audio.audo_wav"
FIXED_AUDO_CAPABILITY_ID = "nfl2k5.audio.fixed_audo_wav"
FIXED_AUDO_PROVIDER_ID = "nfl2k5-unified-visual-v1"
MENU_BACK_CAPABILITY_ID = "nfl2k5.audio.menu_back_wav"
# Keep this stable literal here so importing the product catalog does not pull
# in the provider registry (and its complete self-hash closure).  The actual
# provider class is imported only by ``replacement_provider`` below.
MENU_BACK_PROVIDER_ID = "nfl2k5-menu-back-audio-v1"
STREAMING_AUSB_CAPABILITY_ID = "nfl2k5.audio.ausb_fixed_range_wav"
STREAMING_AUSB_PROVIDER_ID = "nfl2k5-unified-visual-v1"
MENU_BACK_SELECTOR = (3, 101)
ORIGINAL_SCHEMA = "2k5_mod_studio_audio_original_wav/v1"
STREAMING_RANGE_ORIGINAL_SCHEMA = (
    "2k5_mod_studio_streaming_range_original_wav/v1"
)
MAX_REPORT_BYTES = 16 * 1024 * 1024
MAX_WAV_BYTES = 256 * 1024 * 1024
# The largest reviewed AUSB range needs roughly 32 MiB of PCM.  Keep one
# explicit product boundary shared by path reads, in-memory authorization, and
# portable project members.  The origin gate applies the tighter exact-shape
# requirement after this coarse input cap.
MAX_AUDIO_REPLACEMENT_WAV_BYTES = 64 * 1024 * 1024 + 44
MAX_ORIGINAL_SIDECAR_BYTES = 64 * 1024
COPY_BLOCK = 1024 * 1024
DEFAULT_PAGE_SIZE = 250
MAX_PAGE_SIZE = 2000

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_KEY_RE = re.compile(r"^outer_(\d{4})_chunk_(\d{4})$")


STANDALONE_AUDIO_FAMILIES: tuple[tuple[str, str], ...] = (
    ("frontend_ui", "Frontend & franchise UI"),
    ("field_crowd_player", "On-field, crowd & player state"),
    ("team_crowd", "Team crowd variations"),
    ("crib_minigames", "Crib, minigames & trivia"),
    ("unknown", "Unknown standalone family"),
)

STREAMING_AUDIO_FAMILIES: tuple[tuple[str, str], ...] = (
    ("music", "Soundtrack & music"),
    ("commentary", "Commentary & speech"),
    ("stadium", "Stadium, PA & coach"),
    ("presentation", "Broadcast & presentation"),
    ("ambient", "Ambient & diagnostics"),
    ("unknown", "Unknown streaming bank"),
)

# The combined browser keeps the existing family IDs so selecting a family does
# not rewrite or wrap either catalog row type. ``unknown`` is the only ID shared
# by the two source scopes; its mixed label is intentionally container-neutral.
PLAYABLE_AUDIO_FAMILIES: tuple[tuple[str, str], ...] = (
    *STANDALONE_AUDIO_FAMILIES[:-1],
    *STREAMING_AUDIO_FAMILIES[:-1],
    ("unknown", "Unknown playable audio"),
)

_STANDALONE_FAMILY_LABELS = dict(STANDALONE_AUDIO_FAMILIES)
_STREAMING_FAMILY_LABELS = dict(STREAMING_AUDIO_FAMILIES)

_BANK_ROLE_CLASSES = {
    "animationaudio": "overlay_and_presentation",
    "coacha": "stadium_pa_or_coach",
    "crib22": "music_or_crib_audio",
    "cribmusic": "music",
    "cutsceneaudio": "cutscene_or_presentation",
    "cwdloop": "diagnostic_or_ambient",
    "cwdsurr": "diagnostic_or_ambient",
    "drafta": "draft_presentation",
    "femusic": "music",
    "halftimeaudio": "overlay_and_presentation",
    "lines": "commentary_or_speech",
    "loadm": "music",
    "overlayaudio": "overlay_and_presentation",
    "players": "commentary_or_speech",
    "teams": "commentary_or_speech",
    "wrapupm": "music_or_show_presentation",
}


def _standalone_family(outer_index: int) -> tuple[str, str]:
    if outer_index in {3, 9, 23}:
        family_id = "frontend_ui"
    elif outer_index in {346, 347}:
        family_id = "field_crowd_player"
    elif 513 <= outer_index <= 1192:
        family_id = "team_crowd"
    elif outer_index in {4248, 4249, 4250, 4264, 4266, 4271}:
        family_id = "crib_minigames"
    else:
        family_id = "unknown"
    return family_id, _STANDALONE_FAMILY_LABELS[family_id]


def _streaming_family(role_class: str) -> tuple[str, str]:
    if role_class in {"music", "music_or_crib_audio", "music_or_show_presentation"}:
        family_id = "music"
    elif role_class == "commentary_or_speech":
        family_id = "commentary"
    elif role_class in {"stadium_pa", "stadium_pa_or_coach", "stadium_pa_sfx"}:
        family_id = "stadium"
    elif role_class in {
        "overlay_and_presentation", "cutscene_or_presentation", "draft_presentation",
    }:
        family_id = "presentation"
    elif role_class == "diagnostic_or_ambient":
        family_id = "ambient"
    else:
        family_id = "unknown"
    return family_id, _STREAMING_FAMILY_LABELS[family_id]


class Nfl2k5AudioCatalogError(ValidationError):
    """The private AUDO index or product metadata failed closed."""


@dataclass(frozen=True, slots=True)
class AudioAliasGroup:
    group_id: str
    member_count: int


@dataclass(frozen=True, slots=True)
class AudioReplacementContract:
    """Metadata-only contract for one supported fixed-allocation route."""

    capability_id: str
    provider_id: str
    target: str
    channels: int
    sample_rate: int
    frame_count: int
    sample_format: str
    metadata_chunks_allowed: bool

    @property
    def duration_seconds(self) -> float:
        return self.frame_count / self.sample_rate


MENU_BACK_CONTRACT = AudioReplacementContract(
    capability_id=MENU_BACK_CAPABILITY_ID,
    provider_id=MENU_BACK_PROVIDER_ID,
    target=NFL_MENU_BACK_AUDIO_TARGET,
    channels=NFL_MENU_BACK_AUDIO_CHANNELS,
    sample_rate=NFL_MENU_BACK_AUDIO_SAMPLE_RATE,
    frame_count=NFL_MENU_BACK_AUDIO_FRAME_COUNT,
    sample_format="PCM16LE",
    metadata_chunks_allowed=False,
)


@dataclass(frozen=True, slots=True)
class Nfl2k5AudioAsset:
    """One physical standalone audio resource, never a filename guess."""

    asset_id: str
    name: str
    outer_index: int
    outer_id: str
    outer_head: str
    outer_size: int
    chunk_index: int
    chunk_offset: int
    stored_size: int
    system_bytes: int
    payload_bytes: int
    tail_bytes: int
    channels: int
    sample_rate: int
    frame_count: int
    codec_word: str
    classification: str
    classification_reasons: tuple[str, ...]
    fixed_slot_authorization: str
    runtime_selector_owner: str
    runtime_visibility: str
    duplicate_name: AudioAliasGroup | None
    equal_payload: AudioAliasGroup | None
    equal_decoded_content: AudioAliasGroup | None
    equal_resource_span: AudioAliasGroup | None
    physical_span_shared: bool
    resource_body_sha256: str
    payload_sha256: str
    decoded_pcm_sha256: str
    replacement_contract: AudioReplacementContract | None
    # Never set for a reviewed label or the Menu Back proof; ``None`` keeps
    # the row provisional.  Defaulted so every existing constructor and
    # ``dataclasses.replace`` call site stays valid.
    family_label_promotion: AudoFamilyLabelPromotion | None = None

    @property
    def selector(self) -> tuple[int, int]:
        return self.outer_index, self.chunk_index

    @property
    def scope_id(self) -> str:
        return "standalone"

    @property
    def container_label(self) -> str:
        return "Standalone AUDO"

    @property
    def family_id(self) -> str:
        return _standalone_family(self.outer_index)[0]

    @property
    def family_label(self) -> str:
        return _standalone_family(self.outer_index)[1]

    @property
    def family_reviewed_label(self) -> str | None:
        """The disclosed family-inference label, or ``None`` when not promoted."""

        promotion = self.family_label_promotion
        return promotion.label if promotion is not None else None

    @property
    def label_text(self) -> str:
        """The human-facing cue label.

        A promoted provisional cue shows its disclosed ``family: `` inference;
        every reviewed label, the Menu Back proof, and every unpromoted cue
        keep the unchanged game name.
        """

        return self.family_reviewed_label or self.name

    @property
    def format_label(self) -> str:
        channel_text = "mono" if self.channels == 1 else "stereo"
        return f"Playable PCM16 WAV export • {channel_text} • {self.sample_rate:,} Hz"

    @property
    def export_format_label(self) -> str:
        return "Playable WAV (.wav)"

    @property
    def editable(self) -> bool:
        return self.replacement_contract is not None

    @property
    def edit_status(self) -> str:
        return "Editable" if self.editable else "Export-only"

    @property
    def legacy_complete_pack_editable(self) -> bool:
        """Preserve the v1 152-plus-Menu-Back complete-pack membership."""

        return (
            self.selector == MENU_BACK_SELECTOR
            or self.classification == EDITABLE_CLASSIFICATION
        )

    @property
    def duration_seconds(self) -> float:
        return self.frame_count / self.sample_rate

    @property
    def alias_groups(self) -> tuple[AudioAliasGroup, ...]:
        return tuple(
            group for group in (
                self.duplicate_name,
                self.equal_payload,
                self.equal_decoded_content,
                self.equal_resource_span,
            )
            if group is not None
        )

    @property
    def alias_status(self) -> str:
        if self.physical_span_shared:
            return "Shared physical span"
        if self.alias_groups:
            largest = max(group.member_count for group in self.alias_groups)
            return f"Alias-related ({largest} members)"
        return "Unique physical resource"

    @property
    def ownership_status(self) -> str:
        if self.selector == MENU_BACK_SELECTOR:
            return "Separate Menu Back fixed writer proved; runtime audibility not yet tested"
        if self.editable:
            return (
                "Exact outer/chunk physical fixed slot; semantic cue identity and "
                "runtime selector ownership may be unknown"
            )
        return "Physical resource owned; runtime cue selector unproved"

    @property
    def replacement_warning(self) -> str:
        if self.selector == MENU_BACK_SELECTOR:
            return (
                "Menu Back keeps its separately reviewed fixed-target route. "
                "Runtime audibility for this physical cue is not yet captured."
            )
        return generic_fixed_slot_warning(self.outer_index, self.chunk_index)

    @property
    def action_note(self) -> str:
        if self.editable:
            contract = self.replacement_contract
            assert contract is not None
            channel_text = "mono" if contract.channels == 1 else "stereo"
            if self.selector == MENU_BACK_SELECTOR:
                return (
                    "Menu Back is the original bounded audio-replacement route. "
                    f"Replace accepts a {channel_text} PCM16 WAV at exactly "
                    f"{contract.sample_rate:,} Hz and exactly "
                    f"{contract.frame_count:,} frames, with no metadata chunks. "
                    "The build writes a separate XISO; the source is never modified. "
                    "Runtime audibility for this physical cue is not yet captured."
                )
            return (
                f"Replace accepts a {channel_text} PCM16 WAV at exactly "
                f"{contract.sample_rate:,} Hz and exactly "
                f"{contract.frame_count:,} frames. The composed standalone-audio "
                "writer builds a new XISO. "
                f"{self.replacement_warning} Runtime audibility for this physical "
                "cue is not yet proven."
            )
        return (
            "You can preview and export this sound. Replace stays disabled until "
            "its exact in-game cue owner distinguishes its alias-related physical "
            "siblings; a duplicate name or equal-content match is not a safe selector."
        )

    @property
    def suggested_filename(self) -> str:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", self.name).strip("._") or "audio"
        return (
            f"outer_{self.outer_index:04d}_chunk_{self.chunk_index:04d}_{safe}.wav"
        )


@dataclass(frozen=True, slots=True)
class Nfl2k5StreamingAudioBank:
    """One AUSB descriptor and its exact external streaming-bank owner.

    The external bank is exportable as the raw ``.bin`` stored in the user's
    own archive. Its Xbox IMA framing and exact substream boundaries are owned,
    so each range can be decoded separately. The whole bank is not presented as
    one playable cue, and replacement stays locked until cue identity, loops,
    and a reversible repack contract are understood.
    """

    asset_id: str
    name: str
    role_class: str
    outer_index: int
    outer_id: str
    outer_head: str
    outer_size: int
    chunk_index: int
    chunk_offset: int
    stored_size: int
    external_filename: str
    external_outer_index: int
    external_outer_id: str
    external_size: int
    entry_count: int
    sample_rate: int
    channel_word: int
    unknown_word: int
    unit_word: int
    boundaries: tuple[int, ...]
    descriptor_sha256: str
    shared_external_descriptor_count: int

    @property
    def selector(self) -> tuple[int, int]:
        return self.outer_index, self.chunk_index

    @property
    def scope_id(self) -> str:
        return "streaming"

    @property
    def container_label(self) -> str:
        return "AUSB streaming bank"

    @property
    def family_id(self) -> str:
        return _streaming_family(self.role_class)[0]

    @property
    def family_label(self) -> str:
        return _streaming_family(self.role_class)[1]

    @property
    def editable(self) -> bool:
        return False

    @property
    def edit_status(self) -> str:
        return "Export-only"

    @property
    def replacement_status(self) -> str:
        return "Edit individual indexed ranges"

    @property
    def export_format_label(self) -> str:
        return "Raw streaming bank (.bin)"

    @property
    def format_label(self) -> str:
        channel_text = "channel" if self.channel_word == 1 else "channels"
        return (
            f"Indexed Xbox IMA bank • {self.sample_rate:,} Hz • "
            f"{self.channel_word} {channel_text}"
        )

    @property
    def alias_status(self) -> str:
        if self.shared_external_descriptor_count > 1:
            return (
                "Shared external bank "
                f"({self.shared_external_descriptor_count} descriptors)"
            )
        return "Unique external bank"

    @property
    def ownership_status(self) -> str:
        return (
            "Descriptor, Xbox IMA framing, boundary table, and external archive "
            "entry owned; per-cue identity and runtime routing unresolved"
        )

    @property
    def action_note(self) -> str:
        return (
            f"This {self.family_label.lower()} bank exposes {self.entry_count:,} "
            "indexed ranges. Export Raw Bank copies the exact .bin from your own "
            "game for preservation or outside analysis. It contains retail bytes, "
            "never enters a shareable Mod Studio project, and must not be distributed. "
            "The whole bank is not one playable cue; open Indexed Streaming Ranges "
            "to play or export individual cues as WAV. Bank Replace stays disabled "
            "until cue identities, loop/duration rules, and a safe repack contract "
            "are decoded."
        )

    @property
    def suggested_filename(self) -> str:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", self.external_filename)
        return f"outer_{self.outer_index:04d}_chunk_{self.chunk_index:04d}_{safe}"


@dataclass(frozen=True, slots=True)
class Nfl2k5StreamingAudioRange:
    """One exact Xbox IMA range inside an owned NFL 2K5 streaming bank."""

    bank: Nfl2k5StreamingAudioBank
    range_index: int
    start: int
    end: int

    @property
    def asset_id(self) -> str:
        return f"{self.bank.asset_id}.r{self.range_index:05d}"

    @property
    def name(self) -> str:
        return f"{self.bank.name} / range {self.range_index:,}"

    @property
    def scope_id(self) -> str:
        return "streaming_ranges"

    @property
    def container_label(self) -> str:
        return "AUSB streaming range"

    @property
    def family_id(self) -> str:
        return self.bank.family_id

    @property
    def family_label(self) -> str:
        return self.bank.family_label

    @property
    def role_class(self) -> str:
        return self.bank.role_class

    @property
    def outer_index(self) -> int:
        return self.bank.outer_index

    @property
    def outer_id(self) -> str:
        return self.bank.outer_id

    @property
    def chunk_index(self) -> int:
        return self.bank.chunk_index

    @property
    def external_filename(self) -> str:
        return self.bank.external_filename

    @property
    def external_outer_index(self) -> int:
        return self.bank.external_outer_index

    @property
    def sample_rate(self) -> int:
        return self.bank.sample_rate

    @property
    def channels(self) -> int:
        return self.bank.channel_word

    @property
    def stored_size(self) -> int:
        return self.end - self.start

    @property
    def frame_count(self) -> int:
        block_align = 36 * self.channels
        return self.stored_size // block_align * 64

    @property
    def duration_seconds(self) -> float:
        return self.frame_count / self.sample_rate

    @property
    def playable(self) -> bool:
        return True

    @property
    def editable(self) -> bool:
        return True

    @property
    def edit_status(self) -> str:
        return "Editable"

    @property
    def replacement_status(self) -> str:
        return "Editable"

    @property
    def replacement_contract(self) -> AudioReplacementContract:
        """Strict logical authoring contract for this fixed physical slot.

        Physical offsets and canonical slot IDs deliberately stay outside this
        catalog-visible contract.  ``Nfl2k5AudioService`` resolves them lazily
        through the reviewed fixed-slot catalog only when an edit is prepared.
        """

        return AudioReplacementContract(
            capability_id=STREAMING_AUSB_CAPABILITY_ID,
            provider_id=STREAMING_AUSB_PROVIDER_ID,
            target=self.asset_id,
            channels=self.channels,
            sample_rate=self.sample_rate,
            frame_count=self.frame_count,
            sample_format="PCM16LE",
            metadata_chunks_allowed=False,
        )

    @property
    def export_format_label(self) -> str:
        return "Playable PCM16 WAV (.wav) or raw indexed range (.bin)"

    @property
    def format_label(self) -> str:
        return (
            f"Xbox IMA ADPCM • {self.channels}ch • {self.sample_rate:,} Hz"
        )

    @property
    def alias_status(self) -> str:
        return self.bank.alias_status

    @property
    def ownership_status(self) -> str:
        return (
            "Exact descriptor boundary, canonical physical slot, Xbox IMA "
            "framing, channel count, sample rate, and pack span are owned; a "
            "shared physical alias changes every listed logical owner together"
        )

    @property
    def action_note(self) -> str:
        return (
            f"Range {self.range_index:,} is the exact byte span "
            f"0x{self.start:x}..0x{self.end:x} inside {self.external_filename}. "
            "Play and Export WAV decode that exact Xbox IMA span privately to PCM16. "
            "Export Raw Range still copies the encoded retail bytes and must not be "
            "distributed. Replace accepts a canonical PCM16 WAV with this range's "
            "exact channel/rate/frame shape and writes only its reviewed fixed slot "
            "in a new XISO. Shareable projects contain only the user's WAV and this "
            "logical range ID; raw banks, offsets, and source fingerprints are never "
            "included."
        )

    @property
    def suggested_filename(self) -> str:
        stem = re.sub(
            r"[^A-Za-z0-9._-]+", "_", Path(self.external_filename).stem
        )
        return f"{stem}_range_{self.range_index:05d}_{self.start:010x}_{self.end:010x}.bin"

    @property
    def suggested_wav_filename(self) -> str:
        return Path(self.suggested_filename).with_suffix(".wav").name


@dataclass(frozen=True, slots=True)
class AudioReplacementMetadata:
    """User-authored WAV metadata suitable for a project manifest."""

    asset_id: str
    capability_id: str
    provider_id: str
    target: str
    wav_path: Path
    wav_size: int
    wav_sha256: str
    channels: int
    sample_rate: int
    frame_count: int


@dataclass(frozen=True, slots=True)
class AudioReplacementSnapshot:
    """One immutable caller-file read paired with its strict logical contract.

    Session code must pass ``wav_bytes`` directly to the origin gate and then
    write the authorized token's bytes.  Reopening ``metadata.wav_path`` after
    a successful verdict would reintroduce a path-swap race.
    """

    metadata: AudioReplacementMetadata
    wav_bytes: bytes


@dataclass(frozen=True, slots=True)
class AudioReplacementPlan:
    """The provider hook produced after strict validation and recipe creation."""

    asset: Nfl2k5AudioAsset
    replacement: AudioReplacementMetadata
    recipe_path: Path

    @property
    def capability_id(self) -> str:
        return self.replacement.capability_id

    @property
    def provider_id(self) -> str:
        return self.replacement.provider_id


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Nfl2k5AudioCatalogError(message)


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(COPY_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    _require(type(value) is int and value >= minimum, f"Audio metadata has invalid {label}")
    return value


def _text(value: Any, label: str) -> str:
    _require(isinstance(value, str) and bool(value), f"Audio metadata has invalid {label}")
    return value


def _mapping(value: Any, label: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"Audio metadata has invalid {label}")
    return value


def _alias(value: Any, label: str) -> AudioAliasGroup | None:
    if value is None:
        return None
    row = _mapping(value, label)
    group_id = _text(row.get("group_id"), f"{label} group ID")
    count = _integer(row.get("member_count"), f"{label} member count", minimum=2)
    return AudioAliasGroup(group_id, count)


def _asset_id(outer_index: int, chunk_index: int) -> str:
    return f"nfl2k5.audio.audo.o{outer_index:04d}.c{chunk_index:04d}"


def _inventory_kind_rows(
    cache: SourceCache, kind: str
) -> dict[tuple[int, int], dict[str, Any]]:
    rows: dict[tuple[int, int], dict[str, Any]] = {}
    for raw in iter_top_level_array(cache.inventory, "chunks", label="private game index"):
        _require(isinstance(raw, dict), "Private game index contains a non-object row")
        if raw.get("kind") != kind:
            continue
        outer = _integer(raw.get("outer_index"), "inventory outer index")
        chunk = _integer(raw.get("chunk_index"), "inventory chunk index")
        key = (outer, chunk)
        _require(
            key not in rows,
            f"Private game index duplicates {kind} selector {outer}:{chunk}",
        )
        rows[key] = raw
    return rows


def _inventory_rows(cache: SourceCache) -> dict[tuple[int, int], dict[str, Any]]:
    return _inventory_kind_rows(cache, "AUDO")


def _streaming_bank_id(outer_index: int, chunk_index: int) -> str:
    return f"nfl2k5.audio.ausb.o{outer_index:04d}.c{chunk_index:04d}"


def _parse_streaming_banks(cache: SourceCache) -> tuple[Nfl2k5StreamingAudioBank, ...]:
    inventory = _inventory_kind_rows(cache, "AUSB")
    if not inventory:
        return ()
    try:
        archive = parse_archive(cache.pack0)
    except (OSError, FormatError) as exc:
        raise Nfl2k5AudioCatalogError(
            f"Could not open streaming-audio bank index: {exc}"
        ) from exc

    pending: list[dict[str, Any]] = []
    for (outer_index, chunk_index), raw in sorted(inventory.items()):
        try:
            entry = archive.entries[outer_index]
        except IndexError as exc:
            raise Nfl2k5AudioCatalogError(
                f"Streaming-audio descriptor {outer_index}:{chunk_index} names "
                "an unavailable outer entry"
            ) from exc
        outer_id = _text(raw.get("outer_id"), "streaming descriptor outer ID")
        outer_head = _text(raw.get("outer_head"), "streaming descriptor outer head")
        outer_size = _integer(raw.get("outer_size"), "streaming descriptor outer size")
        chunk_offset = _integer(raw.get("chunk_offset"), "streaming descriptor offset")
        stored_size = _integer(
            raw.get("stored_size"), "streaming descriptor stored size", minimum=1
        )
        if (
            entry.size != outer_size
            or f"0x{entry.name_id:08x}" != outer_id
            or entry.head_ascii != outer_head
        ):
            raise Nfl2k5AudioCatalogError(
                f"Streaming-audio descriptor owner changed at {outer_index}:{chunk_index}"
            )
        word_10_text = _text(raw.get("word_10"), "streaming descriptor word_10")
        try:
            word_10 = int(word_10_text, 0)
        except ValueError as exc:
            raise Nfl2k5AudioCatalogError(
                "Private game index has an invalid streaming descriptor word_10"
            ) from exc
        record = ResourceRecord(
            outer_index=outer_index,
            outer_id=outer_id,
            outer_size=outer_size,
            chunk_index=chunk_index,
            chunk_offset=chunk_offset,
            kind="AUSB",
            stored_size=stored_size,
            word_08=_integer(raw.get("word_08"), "streaming descriptor word_08"),
            word_0c=_integer(raw.get("word_0c"), "streaming descriptor word_0c"),
            word_10=word_10,
            word_14=_integer(raw.get("word_14"), "streaming descriptor word_14"),
        )
        try:
            span = read_entry_range(
                archive, entry, chunk_offset, 0x20 + stored_size
            )
            body, detail = decode_resource(span, record)
            name = named_inner(body, "AUSB")[0]
            external_filename = utf16z(body, 0x40, 0x80)[0]
            if external_filename.casefold() != f"{name}.bin".casefold():
                raise Nfl2k5AudioCatalogError(
                    f"Streaming bank {name} has a mismatched external filename"
                )
            if len(body) < 0x9C:
                raise Nfl2k5AudioCatalogError(
                    f"Streaming bank {name} has a truncated descriptor"
                )
            count, unknown, channel_word, rate, unit_word = struct.unpack_from(
                "<5I", body, 0x80
            )
            if count <= 0 or rate != 22_050 or channel_word not in {1, 2} \
                    or unit_word != 0x12000:
                raise Nfl2k5AudioCatalogError(
                    f"Streaming bank {name} has an unsupported descriptor layout"
                )
            table_end = 0x98 + (count + 1) * 4
            if table_end > len(body):
                raise Nfl2k5AudioCatalogError(
                    f"Streaming bank {name} has a truncated boundary table"
                )
            boundaries = tuple(struct.unpack_from(f"<{count + 1}I", body, 0x98))
            if boundaries[0] != 0 or any(
                right < left for left, right in zip(boundaries, boundaries[1:])
            ):
                raise Nfl2k5AudioCatalogError(
                    f"Streaming bank {name} has invalid range boundaries"
                )
            external_id = zlib.crc32(
                external_filename.upper().encode("utf-16le")
            ) & 0xFFFFFFFF
            matches = [
                candidate for candidate in archive.entries
                if candidate.name_id == external_id
            ]
            if len(matches) != 1 or boundaries[-1] != matches[0].size:
                raise Nfl2k5AudioCatalogError(
                    f"Streaming bank {name} does not own one exact external entry"
                )
        except (FormatError, ProbeError, struct.error, ValueError) as exc:
            if isinstance(exc, Nfl2k5AudioCatalogError):
                raise
            raise Nfl2k5AudioCatalogError(
                f"Could not read streaming-audio descriptor "
                f"{outer_index}:{chunk_index}: {exc}"
            ) from exc
        external = matches[0]
        pending.append({
            "asset_id": _streaming_bank_id(outer_index, chunk_index),
            "name": name,
            "role_class": _BANK_ROLE_CLASSES.get(name, "unknown"),
            "outer_index": outer_index,
            "outer_id": outer_id,
            "outer_head": outer_head,
            "outer_size": outer_size,
            "chunk_index": chunk_index,
            "chunk_offset": chunk_offset,
            "stored_size": stored_size,
            "external_filename": external_filename,
            "external_outer_index": external.table_index,
            "external_outer_id": f"0x{external.name_id:08x}",
            "external_size": external.size,
            "entry_count": count,
            "sample_rate": rate,
            "channel_word": channel_word,
            "unknown_word": unknown,
            "unit_word": unit_word,
            "boundaries": boundaries,
            "descriptor_sha256": str(detail["decoded_sha256"]),
        })

    sharing: dict[int, int] = {}
    for row in pending:
        external_index = int(row["external_outer_index"])
        sharing[external_index] = sharing.get(external_index, 0) + 1
    return tuple(
        Nfl2k5StreamingAudioBank(
            **row,
            shared_external_descriptor_count=sharing[int(row["external_outer_index"])],
        )
        for row in pending
    )


def _normalize_asset(raw: object, inventory: dict[str, Any]) -> Nfl2k5AudioAsset:
    row = _mapping(raw, "AUDO record")
    key_text = _text(row.get("key"), "AUDO key")
    matched = _KEY_RE.fullmatch(key_text)
    _require(matched is not None, "Audio metadata has an invalid stable key")
    outer_index, chunk_index = (int(matched.group(1)), int(matched.group(2)))
    outer = _mapping(row.get("outer"), "outer record")
    chunk = _mapping(row.get("chunk"), "chunk record")
    audio_format = _mapping(row.get("format"), "audio format")
    groups = _mapping(row.get("groups"), "alias groups")
    ownership = _mapping(row.get("ownership"), "ownership")
    hashes = _mapping(row.get("hashes"), "audio hashes")

    _require(_integer(outer.get("index"), "outer index") == outer_index,
             "Audio key and outer index disagree")
    _require(_integer(chunk.get("index"), "chunk index") == chunk_index,
             "Audio key and chunk index disagree")
    _require(chunk.get("kind") == "AUDO", "Audio metadata row is not AUDO")
    stored_size = _integer(chunk.get("stored_body_bytes"), "stored body bytes", minimum=1)
    wrapper_size = _integer(chunk.get("wrapper_span_bytes"), "wrapper bytes", minimum=33)
    _require(wrapper_size == stored_size + 0x20, "Audio wrapper extent is inconsistent")

    system_bytes = _integer(audio_format.get("system_bytes"), "system bytes", minimum=1)
    payload_bytes = _integer(
        audio_format.get("payload_allocation_bytes"), "payload allocation", minimum=1
    )
    tail_bytes = _integer(audio_format.get("tail_bytes"), "tail bytes")
    _require(system_bytes + payload_bytes + tail_bytes == stored_size,
             "Audio body allocation is inconsistent")
    channels = _integer(audio_format.get("channels"), "channel count", minimum=1)
    sample_rate = _integer(audio_format.get("sample_rate"), "sample rate", minimum=1)
    frame_count = _integer(audio_format.get("frame_count"), "frame count", minimum=1)
    block_count = _integer(audio_format.get("block_count"), "block count", minimum=1)
    block_align = _integer(audio_format.get("total_block_align"), "block alignment", minimum=1)
    _require(block_align == 36 * channels and payload_bytes == block_align * block_count,
             "Audio block allocation is inconsistent")
    _require(frame_count == 64 * block_count, "Audio frame allocation is inconsistent")

    expected_inventory = {
        "outer_index": outer_index,
        "outer_id": _text(outer.get("id"), "outer ID"),
        "outer_head": _text(outer.get("head_ascii"), "outer head"),
        "outer_size": _integer(outer.get("size"), "outer size", minimum=1),
        "chunk_index": chunk_index,
        "chunk_offset": _integer(chunk.get("offset_in_outer"), "chunk offset"),
        "stored_size": stored_size,
        "word_08": system_bytes,
        "word_0c": payload_bytes,
        "word_10": "0x00000000",
        "word_14": 0,
    }
    for field, expected in expected_inventory.items():
        actual = inventory.get(field)
        if field == "word_10" and type(actual) is int:
            actual = f"0x{actual:08x}"
        _require(actual == expected,
                 f"Private cache and audio metadata disagree for {key_text} ({field})")

    classification = _text(row.get("classification"), "classification")
    reasons = row.get("classification_reasons")
    _require(
        isinstance(reasons, list)
        and reasons
        and all(isinstance(value, str) and value for value in reasons),
        "Audio classification reasons are invalid",
    )
    for field in ("resource_body_sha256", "payload_sha256", "decoded_pcm_sha256"):
        _require(
            isinstance(hashes.get(field), str)
            and _SHA256_RE.fullmatch(str(hashes[field])) is not None,
            f"Audio metadata has invalid {field}",
        )

    selector = (outer_index, chunk_index)
    fixed_authorization = _text(
        ownership.get("fixed_slot_authorization"), "fixed-slot authorization"
    )
    structural = _mapping(row.get("structural_import"), "structural import")
    authoring = _mapping(structural.get("authoring_contract"), "authoring contract")
    expected_authoring = {
        "channels": channels,
        "exact_frame_count": frame_count,
        "format": "strict RIFF PCM16LE",
        "metadata_chunks_allowed": False,
        "sample_rate": sample_rate,
    }
    _require(authoring == expected_authoring,
             "The standalone-audio authoring contract changed")
    physical_span_shared = groups.get("physical_span_shared")
    _require(type(physical_span_shared) is bool,
             "Audio metadata has invalid physical-span sharing status")
    contract = None
    if selector == MENU_BACK_SELECTOR:
        _require(row.get("name") == NFL_MENU_BACK_AUDIO_TARGET,
                 "The fixed menu-back selector changed names")
        _require(fixed_authorization == "public-offline-writer-proved",
                 "The fixed menu-back writer authorization is missing")
        _require(
            authoring == expected_authoring == {
                "channels": MENU_BACK_CONTRACT.channels,
                "exact_frame_count": MENU_BACK_CONTRACT.frame_count,
                "format": "strict RIFF PCM16LE",
                "metadata_chunks_allowed": MENU_BACK_CONTRACT.metadata_chunks_allowed,
                "sample_rate": MENU_BACK_CONTRACT.sample_rate,
            },
            "The fixed menu-back authoring contract changed",
        )
        contract = MENU_BACK_CONTRACT
    else:
        _require(fixed_authorization == "none",
                 "A non-menu-back AUDO row unexpectedly claims a fixed writer")
        _require(
            classification in {"export-only", EDITABLE_CLASSIFICATION}
            and physical_span_shared is False
            and structural.get("same_allocation") is True
            and structural.get("metadata_change_required") is False
            and ownership.get("physical_resource_owner") == "exact outer/chunk/span",
            "A generic standalone-audio row lost its exact physical-slot proof",
        )
        contract = AudioReplacementContract(
            capability_id=FIXED_AUDO_CAPABILITY_ID,
            provider_id=FIXED_AUDO_PROVIDER_ID,
            target=_asset_id(outer_index, chunk_index),
            channels=channels,
            sample_rate=sample_rate,
            frame_count=frame_count,
            sample_format="PCM16LE",
            metadata_chunks_allowed=False,
        )
    codec_word = _text(audio_format.get("codec_word"), "codec word")
    _require(codec_word == "0x00000011", "Audio codec is not Xbox IMA ADPCM")

    return Nfl2k5AudioAsset(
        asset_id=_asset_id(outer_index, chunk_index),
        name=_text(row.get("name"), "audio name"),
        outer_index=outer_index,
        outer_id=expected_inventory["outer_id"],
        outer_head=expected_inventory["outer_head"],
        outer_size=expected_inventory["outer_size"],
        chunk_index=chunk_index,
        chunk_offset=expected_inventory["chunk_offset"],
        stored_size=stored_size,
        system_bytes=system_bytes,
        payload_bytes=payload_bytes,
        tail_bytes=tail_bytes,
        channels=channels,
        sample_rate=sample_rate,
        frame_count=frame_count,
        codec_word=codec_word,
        classification=classification,
        classification_reasons=tuple(reasons),
        fixed_slot_authorization=fixed_authorization,
        runtime_selector_owner=_text(
            ownership.get("runtime_selector_owner"), "runtime selector owner"
        ),
        runtime_visibility=_text(
            ownership.get("runtime_visibility"), "runtime visibility"
        ),
        duplicate_name=_alias(groups.get("duplicate_name"), "duplicate-name group"),
        equal_payload=_alias(groups.get("equal_payload"), "equal-payload group"),
        equal_decoded_content=_alias(
            groups.get("equal_decoded_content"), "equal-content group"
        ),
        equal_resource_span=_alias(
            groups.get("equal_resource_span"), "equal-span group"
        ),
        physical_span_shared=physical_span_shared,
        resource_body_sha256=str(hashes["resource_body_sha256"]),
        payload_sha256=str(hashes["payload_sha256"]),
        decoded_pcm_sha256=str(hashes["decoded_pcm_sha256"]),
        replacement_contract=contract,
    )


def apply_family_label_promotions(
    assets: Iterable[Nfl2k5AudioAsset],
    promotions: dict[str, AudoFamilyLabelPromotion] | None,
) -> tuple[Nfl2k5AudioAsset, ...]:
    """Attach fail-closed family-label promotions to provisional cues only.

    Reviewed labels and the Menu Back proof are immutable: their rows pass
    through untouched even if a promotion somehow names them.  An absent or
    empty promotion map leaves every label provisional.
    """

    if not promotions:
        return tuple(assets)
    result: list[Nfl2k5AudioAsset] = []
    for asset in assets:
        if asset.selector == MENU_BACK_SELECTOR or asset.legacy_complete_pack_editable:
            result.append(asset)
            continue
        key = f"outer_{asset.outer_index:04d}_chunk_{asset.chunk_index:04d}"
        promotion = promotions.get(key)
        if promotion is None or promotion.selector != asset.selector:
            result.append(asset)
            continue
        result.append(replace(asset, family_label_promotion=promotion))
    return tuple(result)


class Nfl2k5AudioCatalog:
    """Immutable metadata catalog for standalone, streaming, and playable audio."""

    def __init__(
        self,
        cache: SourceCache,
        *,
        capacity_report: Path = CAPACITY_REPORT,
        expected_count: int = EXPECTED_AUDIO_COUNT,
        expected_report_sha256: str | None = CAPACITY_REPORT_SHA256,
        family_label_report: Path | None = None,
        expected_family_label_sha256: str | None = FAMILY_LABEL_REPORT_SHA256,
        require_menu_back: bool = True,
    ) -> None:
        self.cache = cache
        requested_report = capacity_report.expanduser()
        try:
            report_info = require_regular_file(
                requested_report, "audio ownership metadata"
            )
        except ValidationError as exc:
            raise Nfl2k5AudioCatalogError(str(exc)) from exc
        self.capacity_report = requested_report.resolve(strict=True)
        _require(0 < report_info.st_size <= MAX_REPORT_BYTES,
                 "Audio ownership metadata is outside the product size limit")
        if expected_report_sha256 is not None:
            _require(
                _SHA256_RE.fullmatch(expected_report_sha256) is not None
                and _sha256_path(self.capacity_report) == expected_report_sha256,
                "Audio ownership metadata changed from the shipped product version",
            )
        try:
            schema_marker = f'"schema": "{CAPACITY_REPORT_SCHEMA}"'.encode("utf-8")
            _require(
                file_contains_bytes(
                    self.capacity_report,
                    schema_marker,
                    label="audio ownership metadata",
                ),
                "Audio ownership metadata schema is unsupported",
            )
        except OSError as exc:
            raise Nfl2k5AudioCatalogError(
                f"Could not read audio ownership metadata: {exc}"
            ) from exc

        inventory = _inventory_rows(cache)
        _require(
            len(inventory) == expected_count,
            f"Private game index exposes {len(inventory)} AUDO rows; {expected_count} expected",
        )
        assets: list[Nfl2k5AudioAsset] = []
        seen_selectors: set[tuple[int, int]] = set()
        for raw in iter_top_level_array(
            self.capacity_report, "records", label="audio ownership metadata"
        ):
            row = _mapping(raw, "AUDO record")
            key_text = _text(row.get("key"), "AUDO key")
            matched = _KEY_RE.fullmatch(key_text)
            _require(matched is not None, "Audio metadata has an invalid key")
            selector = (int(matched.group(1)), int(matched.group(2)))
            _require(selector not in seen_selectors,
                     f"Audio metadata duplicates selector {selector[0]}:{selector[1]}")
            _require(selector in inventory,
                     f"Audio metadata selector {selector[0]}:{selector[1]} is not in the cache")
            assets.append(_normalize_asset(row, inventory[selector]))
            seen_selectors.add(selector)
        _require(len(assets) == expected_count,
                 f"Audio metadata exposes {len(assets)} rows; {expected_count} expected")
        _require(seen_selectors == set(inventory),
                 "The private AUDO index and ownership metadata do not cover the same rows")
        assets.sort(key=lambda asset: (asset.outer_index, asset.chunk_index))
        family_promotions = load_family_label_promotions(
            self.capacity_report,
            report=(
                family_label_report
                if family_label_report is not None
                else FAMILY_LABEL_REPORT
            ),
            expected_sha256=expected_family_label_sha256,
        )
        self.assets = apply_family_label_promotions(assets, family_promotions)
        self._by_id = {asset.asset_id: asset for asset in self.assets}
        self._by_selector = {asset.selector: asset for asset in self.assets}
        _require(len(self._by_id) == len(self.assets), "Stable audio asset IDs are duplicated")
        editable = tuple(asset for asset in self.assets if asset.editable)
        if require_menu_back:
            _require(
                sum(asset.selector == MENU_BACK_SELECTOR for asset in editable) == 1,
                "The catalog must expose the proved menu-back writer",
            )
        self.streaming_banks = _parse_streaming_banks(cache)
        self._streaming_by_id = {
            bank.asset_id: bank for bank in self.streaming_banks
        }
        _require(
            len(self._streaming_by_id) == len(self.streaming_banks),
            "Stable streaming-audio bank IDs are duplicated",
        )
        self.streaming_ranges = tuple(
            Nfl2k5StreamingAudioRange(bank, index, start, end)
            for bank in self.streaming_banks
            for index, (start, end) in enumerate(
                zip(bank.boundaries, bank.boundaries[1:])
            )
        )
        _require(
            all(
                item.stored_size > 0
                and item.stored_size % (36 * item.channels) == 0
                and item.frame_count > 0
                for item in self.streaming_ranges
            ),
            "A streaming-audio range is not whole Xbox IMA channel blocks",
        )
        self._streaming_range_by_id = {
            item.asset_id: item for item in self.streaming_ranges
        }
        _require(
            len(self._streaming_range_by_id) == len(self.streaming_ranges),
            "Stable streaming-audio range IDs are duplicated",
        )
        # This is the one canonical playable inventory. Keep the original row
        # objects and their public scope/action contracts intact: standalone
        # AUDO first, then exact streaming ranges. Complete banks are raw
        # containers, not playable cues, and therefore never enter this tuple.
        self.playable_assets: tuple[
            Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange, ...
        ] = self.assets + self.streaming_ranges
        _require(
            len({item.asset_id for item in self.playable_assets})
            == len(self.playable_assets),
            "Stable playable-audio asset IDs are duplicated",
        )
        if expected_count == EXPECTED_AUDIO_COUNT:
            _require(
                len(self.streaming_banks) == EXPECTED_STREAMING_BANK_COUNT,
                f"Private game index exposes {len(self.streaming_banks)} AUSB banks; "
                f"{EXPECTED_STREAMING_BANK_COUNT} expected",
            )
            _require(
                self.streaming_external_bank_count == 16,
                "Streaming-audio external ownership count changed",
            )
            _require(
                self.streaming_range_count == EXPECTED_STREAMING_RANGE_COUNT,
                f"Private streaming banks expose {self.streaming_range_count:,} ranges; "
                f"{EXPECTED_STREAMING_RANGE_COUNT:,} expected",
            )
            _require(
                self.playable_count == EXPECTED_PLAYABLE_AUDIO_COUNT,
                f"Private audio inventory exposes {self.playable_count:,} playable "
                f"sounds; {EXPECTED_PLAYABLE_AUDIO_COUNT:,} expected",
            )
            _require(
                self.streaming_family_counts == {
                    "ambient": 3,
                    "commentary": 3,
                    "music": 5,
                    "presentation": 5,
                    "stadium": 1,
                },
                "Streaming-audio family ownership changed",
            )
            _require(
                self.streaming_range_family_counts == {
                    "ambient": 4,
                    "commentary": 52_940,
                    "music": 136,
                    "presentation": 482,
                    "stadium": 9,
                },
                "Streaming-audio range-family ownership changed",
            )
            _require(
                self.family_counts == {
                    "frontend_ui": 36,
                    "field_crowd_player": 13,
                    "team_crowd": 680,
                    "crib_minigames": 121,
                },
                "Standalone-audio family ownership changed",
            )

    @property
    def asset_count(self) -> int:
        return len(self.assets)

    @property
    def editable_count(self) -> int:
        return sum(asset.editable for asset in self.assets)

    @property
    def export_only_count(self) -> int:
        return self.asset_count - self.editable_count

    @property
    def family_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for asset in self.assets:
            counts[asset.family_id] = counts.get(asset.family_id, 0) + 1
        return counts

    @property
    def streaming_bank_count(self) -> int:
        return len(self.streaming_banks)

    @property
    def streaming_external_bank_count(self) -> int:
        return len({bank.external_outer_index for bank in self.streaming_banks})

    @property
    def streaming_range_count(self) -> int:
        return len(self.streaming_ranges)

    @property
    def playable_count(self) -> int:
        """Number of playable WAV rows, excluding raw streaming banks."""

        return len(self.playable_assets)

    @property
    def streaming_family_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for bank in self.streaming_banks:
            counts[bank.family_id] = counts.get(bank.family_id, 0) + 1
        return counts

    @property
    def streaming_range_family_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.streaming_ranges:
            counts[item.family_id] = counts.get(item.family_id, 0) + 1
        return counts

    def get_asset(self, value: str | Nfl2k5AudioAsset) -> Nfl2k5AudioAsset:
        asset_id = value.asset_id if isinstance(value, Nfl2k5AudioAsset) else value
        asset = self._by_id.get(asset_id)
        if asset is None:
            raise Nfl2k5AudioCatalogError(f"Unknown audio asset: {asset_id}")
        if isinstance(value, Nfl2k5AudioAsset) and value != asset:
            raise Nfl2k5AudioCatalogError("Audio asset metadata does not match the catalog")
        return asset

    def get_selector(self, outer_index: int, chunk_index: int) -> Nfl2k5AudioAsset:
        try:
            return self._by_selector[(outer_index, chunk_index)]
        except KeyError as exc:
            raise Nfl2k5AudioCatalogError(
                f"Unknown audio selector: {outer_index}:{chunk_index}"
            ) from exc

    def get_streaming_bank(
        self, value: str | Nfl2k5StreamingAudioBank
    ) -> Nfl2k5StreamingAudioBank:
        asset_id = value.asset_id if isinstance(value, Nfl2k5StreamingAudioBank) else value
        bank = self._streaming_by_id.get(asset_id)
        if bank is None:
            raise Nfl2k5AudioCatalogError(f"Unknown streaming-audio bank: {asset_id}")
        if isinstance(value, Nfl2k5StreamingAudioBank) and value != bank:
            raise Nfl2k5AudioCatalogError(
                "Streaming-audio bank metadata does not match the catalog"
            )
        return bank

    def get_streaming_range(
        self, value: str | Nfl2k5StreamingAudioRange
    ) -> Nfl2k5StreamingAudioRange:
        asset_id = (
            value.asset_id if isinstance(value, Nfl2k5StreamingAudioRange) else value
        )
        item = self._streaming_range_by_id.get(asset_id)
        if item is None:
            raise Nfl2k5AudioCatalogError(
                f"Unknown streaming-audio range: {asset_id}"
            )
        if isinstance(value, Nfl2k5StreamingAudioRange) and value != item:
            raise Nfl2k5AudioCatalogError(
                "Streaming-audio range metadata does not match the catalog"
            )
        return item

    def query(
        self,
        *,
        search: str = "",
        status: str | None = None,
        offset: int = 0,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[Nfl2k5AudioAsset, ...]:
        if type(offset) is not int or offset < 0:
            raise Nfl2k5AudioCatalogError("Audio result offset cannot be negative")
        if type(limit) is not int or not 1 <= limit <= MAX_PAGE_SIZE:
            raise Nfl2k5AudioCatalogError(
                f"Audio page size must be between 1 and {MAX_PAGE_SIZE}"
            )
        if status not in (None, "Editable", "Export-only"):
            raise Nfl2k5AudioCatalogError("Audio status filter is invalid")
        needle = search.strip().casefold()
        rows: Iterable[Nfl2k5AudioAsset] = self.assets
        if status is not None:
            rows = (asset for asset in rows if asset.edit_status == status)
        if needle:
            rows = (
                asset for asset in rows
                if needle in " ".join((
                    asset.name,
                    asset.asset_id,
                    asset.outer_id,
                    asset.alias_status,
                    asset.ownership_status,
                    str(asset.outer_index),
                    str(asset.chunk_index),
                )).casefold()
            )
        materialized = tuple(rows)
        return materialized[offset:offset + limit]


def _asset_key(asset_id: str) -> str:
    return hashlib.sha256(asset_id.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, payload: bytes, *, replace: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(path) and not replace:
        raise Nfl2k5AudioCatalogError(f"A file already exists there: {path}")
    if path.is_symlink():
        raise Nfl2k5AudioCatalogError(f"Refusing to replace a symbolic link: {path}")
    temporary = platform_compat.temporary_sibling(path)
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if not replace and os.path.lexists(path):
            raise Nfl2k5AudioCatalogError(f"A file appeared at the destination: {path}")
        os.replace(temporary, path)
        return path.resolve(strict=True)
    finally:
        temporary.unlink(missing_ok=True)


def _stream_entry_to_new_file(
    archive: Any,
    entry: Any,
    destination: Path,
    progress: Callable[[int, int], None] | None = None,
    *,
    relative_offset: int = 0,
    length: int | None = None,
) -> Path:
    """Copy one exact private archive span without materializing it in RAM."""

    selected_size = entry.size - relative_offset if length is None else length
    if (
        type(relative_offset) is not int
        or type(selected_size) is not int
        or relative_offset < 0
        or selected_size < 0
        or relative_offset + selected_size > entry.size
    ):
        raise Nfl2k5AudioCatalogError(
            "Streaming-bank export range is outside its owned external entry"
        )

    requested = destination.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    if requested.suffix.lower() != ".bin":
        raise Nfl2k5AudioCatalogError(
            "Streaming-bank export needs a .bin filename because this action "
            "copies the exact encoded source bytes"
        )
    requested.parent.mkdir(parents=True, exist_ok=True)
    try:
        parent_info = requested.parent.lstat()
    except FileNotFoundError as exc:
        raise Nfl2k5AudioCatalogError(
            "Streaming-bank export folder does not exist"
        ) from exc
    if not stat.S_ISDIR(parent_info.st_mode) or stat.S_ISLNK(parent_info.st_mode):
        raise Nfl2k5AudioCatalogError(
            "Streaming-bank export folder must be a regular, non-link folder"
        )
    parent = requested.parent.resolve(strict=True)
    target = parent / requested.name
    if os.path.lexists(target):
        raise Nfl2k5AudioCatalogError(f"A file already exists there: {target}")
    temporary = platform_compat.temporary_sibling(target)
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
            0o600,
        )
        written = 0
        if progress is not None:
            progress(0, selected_size)
        selected_end = relative_offset + selected_size
        entry_segment_start = 0
        for segment in entry.segments:
            entry_segment_end = entry_segment_start + segment.size
            part_start = max(relative_offset, entry_segment_start)
            part_end = min(selected_end, entry_segment_end)
            if part_start >= part_end:
                entry_segment_start = entry_segment_end
                continue
            pack = archive.packs[segment.pack_ordinal]
            try:
                source_info = pack.path.lstat()
                if not stat.S_ISREG(source_info.st_mode) or stat.S_ISLNK(source_info.st_mode):
                    raise Nfl2k5AudioCatalogError(
                        "A private archive pack is no longer a regular file"
                    )
                with pack.path.open("rb") as source:
                    source.seek(
                        segment.pack_offset + part_start - entry_segment_start
                    )
                    remaining = part_end - part_start
                    while remaining:
                        block = source.read(min(COPY_BLOCK, remaining))
                        if not block:
                            raise Nfl2k5AudioCatalogError(
                                "The private streaming bank shortened during export"
                            )
                        view = memoryview(block)
                        while view:
                            count = os.write(descriptor, view)
                            if count <= 0:
                                raise OSError("short streaming-bank export write")
                            view = view[count:]
                        written += len(block)
                        remaining -= len(block)
                        if progress is not None:
                            progress(written, selected_size)
            except OSError as exc:
                raise Nfl2k5AudioCatalogError(
                    f"Could not read the private streaming bank: {exc}"
                ) from exc
            entry_segment_start = entry_segment_end
        if written != selected_size:
            raise Nfl2k5AudioCatalogError(
                "The private streaming-bank export size is inconsistent"
            )
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        if os.path.lexists(target):
            raise Nfl2k5AudioCatalogError(
                f"A file appeared at the export destination: {target}"
            )
        try:
            os.link(temporary, target, follow_symlinks=False)
        except FileExistsError as exc:
            raise Nfl2k5AudioCatalogError(
                f"A file appeared at the export destination: {target}"
            ) from exc
        return target.resolve(strict=True)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


_STRICT_PCM16_WAV_HEADER = struct.Struct("<4sI4s4sIHHIIHH4sI")


def _validate_strict_pcm16_wav_shape(
    payload: bytes,
    *,
    channels: int,
    sample_rate: int,
    frame_count: int,
) -> bytes:
    """Return PCM only for one canonical 44-byte-header PCM16 WAV.

    This lightweight structural pass is used before comparing a supplied file
    with its selected private original (an exact match means Revert).  Every
    non-original shareable replacement then crosses the two private origin
    gates using this same immutable ``payload`` object.
    """

    if type(payload) is not bytes:
        raise Nfl2k5AudioCatalogError(
            "Replacement WAV must be supplied as immutable bytes"
        )
    expected_pcm = channels * frame_count * 2
    if not 44 <= len(payload) <= MAX_AUDIO_REPLACEMENT_WAV_BYTES:
        raise Nfl2k5AudioCatalogError(
            "Replacement WAV is empty or exceeds the 64 MiB PCM input limit"
        )
    try:
        (
            riff_id,
            riff_size,
            wave_id,
            fmt_id,
            fmt_size,
            format_tag,
            wav_channels,
            wav_rate,
            byte_rate,
            block_align,
            bits_per_sample,
            data_id,
            data_size,
        ) = _STRICT_PCM16_WAV_HEADER.unpack_from(payload)
    except struct.error as exc:
        raise Nfl2k5AudioCatalogError("Replacement WAV header is truncated") from exc
    expected_align = channels * 2
    if riff_id != b"RIFF" or wave_id != b"WAVE":
        raise Nfl2k5AudioCatalogError("Replacement is not a RIFF/WAVE file")
    if (
        riff_size + 8 != len(payload)
        or fmt_id != b"fmt "
        or fmt_size != 16
        or data_id != b"data"
        or len(payload) != 44 + data_size
    ):
        raise Nfl2k5AudioCatalogError(
            "WAV must contain exactly a 16-byte fmt chunk followed by data; "
            "remove metadata and trailing bytes"
        )
    if (
        format_tag != 1
        or wav_channels != channels
        or wav_rate != sample_rate
        or bits_per_sample != 16
        or block_align != expected_align
        or byte_rate != sample_rate * expected_align
    ):
        channel_text = "mono" if channels == 1 else "stereo"
        raise Nfl2k5AudioCatalogError(
            f"WAV must be canonical {channel_text} PCM16 at exactly "
            f"{sample_rate:,} Hz"
        )
    if data_size != expected_pcm:
        raise Nfl2k5AudioCatalogError(
            f"WAV must contain exactly {frame_count:,} PCM frames"
        )
    return payload[44:]


def _wav_info(payload: bytes) -> tuple[int, int, int, bytes]:
    try:
        with wave.open(io.BytesIO(payload), "rb") as stream:
            channels = stream.getnchannels()
            rate = stream.getframerate()
            frames = stream.getnframes()
            if stream.getsampwidth() != 2 or stream.getcomptype() != "NONE":
                raise Nfl2k5AudioCatalogError("Cached audio is not uncompressed PCM16")
            pcm = stream.readframes(frames)
            if len(pcm) != frames * channels * 2 or stream.readframes(1):
                raise Nfl2k5AudioCatalogError("Cached WAV has an inconsistent frame count")
    except (EOFError, wave.Error, struct.error) as exc:
        raise Nfl2k5AudioCatalogError(f"Cached WAV is invalid: {exc}") from exc
    return channels, rate, frames, pcm


_NIBBLE_SWAP_TABLE = bytes.maketrans(
    bytes(range(256)),
    bytes((value >> 4) | ((value & 0x0F) << 4) for value in range(256)),
)


def _decode_streaming_xbox_ima_pcm(
    payload: bytes,
    channels: int,
    progress: Callable[[int, int], None] | None = None,
) -> bytes:
    """Decode strict 36-byte Xbox IMA channel blocks with a safe fallback.

    Python 3.12's C-backed ``audioop`` gives a materially faster local preview.
    It consumes the opposite nibble order, so bytes are translated first; the
    predictor plus its first 63 decoded samples exactly match the established
    NFL decoder. Python 3.13+ transparently uses the pure-Python reference path.
    """

    if channels not in {1, 2} or len(payload) % (36 * channels):
        raise Nfl2k5AudioCatalogError(
            "Streaming Xbox IMA payload is outside its channel-block contract"
        )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            import audioop as fast_audio  # type: ignore[import-not-found]
    except ImportError:
        fast_audio = None
    if fast_audio is None:
        block_align = 36 * channels
        chunk_bytes = block_align * 1024
        parts: list[bytes] = []
        for offset in range(0, len(payload), chunk_bytes):
            encoded = payload[offset:offset + chunk_bytes]
            try:
                samples = decode_xbox_ima(encoded, channels)
            except ProbeError as exc:
                raise Nfl2k5AudioCatalogError(
                    f"Could not decode streaming Xbox IMA: {exc}"
                ) from exc
            parts.append(struct.pack(f"<{len(samples)}h", *samples))
            if progress is not None:
                progress(min(len(payload), offset + len(encoded)), len(payload))
        return b"".join(parts)

    output = bytearray()
    block_align = 36 * channels
    for block_number, block_offset in enumerate(
        range(0, len(payload), block_align)
    ):
        decoded_channels: list[bytes] = []
        for channel in range(channels):
            channel_offset = block_offset + channel * 36
            predictor, step_index = struct.unpack_from(
                "<hH", payload, channel_offset
            )
            if step_index > 88:
                raise Nfl2k5AudioCatalogError(
                    f"Xbox IMA block 0x{block_offset:x} channel {channel}: "
                    f"step index {step_index}"
                )
            coded = payload[
                channel_offset + 4:channel_offset + 36
            ].translate(_NIBBLE_SWAP_TABLE)
            expanded, _state = fast_audio.adpcm2lin(
                coded, 2, (predictor, step_index)
            )
            if len(expanded) != 128:
                raise Nfl2k5AudioCatalogError(
                    "The accelerated Xbox IMA decoder returned the wrong frame count"
                )
            decoded_channels.append(struct.pack("<h", predictor) + expanded[:126])
        if channels == 1:
            output.extend(decoded_channels[0])
        else:
            output.extend(fast_audio.add(
                fast_audio.tostereo(decoded_channels[0], 2, 1, 0),
                fast_audio.tostereo(decoded_channels[1], 2, 0, 1),
                2,
            ))
        if progress is not None and (
            block_number % 1024 == 1023
            or block_offset + block_align == len(payload)
        ):
            progress(block_offset + block_align, len(payload))
    return bytes(output)


class Nfl2k5AudioService:
    """Lazy decoder/exporter and fixed-allocation replacement adapter."""

    def __init__(self, cache: SourceCache, catalog: Nfl2k5AudioCatalog) -> None:
        _require(cache.root == catalog.cache.root, "Audio service and catalog caches differ")
        self.cache = cache
        self.catalog = catalog
        self._archive: Any | None = None
        self._streaming_slots: StreamingSlotCatalog | None = None
        self._source_fingerprints: Any | None = None
        self._containment_fingerprints: Any | None = None
        self._streaming_pcm_cache_stamp: tuple[int, int] | None = None
        self._streaming_pcm_cache_owners: dict[str, tuple[str, ...]] = {}

    @property
    def archive(self) -> Any:
        if self._archive is None:
            try:
                self._archive = parse_archive(self.cache.pack0)
            except (OSError, FormatError) as exc:
                raise Nfl2k5AudioCatalogError(
                    f"Could not open the private game archive: {exc}"
                ) from exc
        return self._archive

    @property
    def streaming_slot_catalog(self) -> StreamingSlotCatalog:
        """Lazily build the reviewed logical-to-physical AUSB slot map."""

        if self._streaming_slots is None:
            try:
                self._streaming_slots = build_streaming_slot_catalog(
                    self.catalog.streaming_ranges, self.archive
                )
            except (Nfl2k5AusbFixedSlotError, ValueError) as exc:
                raise Nfl2k5AudioCatalogError(
                    f"Could not prepare fixed streaming-audio slots: {exc}"
                ) from exc
        return self._streaming_slots

    def resolve_streaming_slot(
        self, item: str | Nfl2k5StreamingAudioRange
    ) -> CanonicalStreamingSlot:
        """Resolve a logical range (or its internal canonical ID) to one slot."""

        asset_id = item.asset_id if isinstance(item, Nfl2k5StreamingAudioRange) else item
        if isinstance(item, Nfl2k5StreamingAudioRange):
            self.catalog.get_streaming_range(item)
        if not isinstance(asset_id, str):
            raise Nfl2k5AudioCatalogError("Streaming-audio range ID must be text")
        try:
            return self.streaming_slot_catalog.resolve(asset_id)
        except Nfl2k5AusbFixedSlotError as exc:
            raise Nfl2k5AudioCatalogError(str(exc)) from exc

    def affected_streaming_asset_ids(
        self, item: str | Nfl2k5StreamingAudioRange
    ) -> tuple[str, ...]:
        """Return every logical owner changed by one physical AUSB edit."""

        return tuple(
            owner.asset_id for owner in self.resolve_streaming_slot(item).owners
        )

    def resolve_editable_audio(
        self,
        value: str | Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange,
    ) -> Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange:
        """Resolve only catalog-visible editable cues; raw banks stay locked."""

        selected = self.resolve_playable_audio(value)
        if not selected.editable:
            raise Nfl2k5AudioCatalogError(selected.action_note)
        return selected

    def resolve_playable_audio(
        self,
        value: str | Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange,
    ) -> Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange:
        """Resolve standalone/range content without imposing an editability gate."""

        if isinstance(value, Nfl2k5AudioAsset):
            selected: Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange = (
                self.catalog.get_asset(value)
            )
        elif isinstance(value, Nfl2k5StreamingAudioRange):
            selected = self.catalog.get_streaming_range(value)
        elif isinstance(value, str):
            try:
                selected = self.catalog.get_asset(value)
            except Nfl2k5AudioCatalogError:
                selected = self.catalog.get_streaming_range(value)
        else:
            raise Nfl2k5AudioCatalogError("Unknown playable audio target")
        return selected

    def audio_physical_id(
        self,
        value: str | Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange,
    ) -> str:
        selected = self.resolve_editable_audio(value)
        if isinstance(selected, Nfl2k5StreamingAudioRange):
            return self.resolve_streaming_slot(selected).canonical_id
        return selected.asset_id

    def audio_affected_asset_ids(
        self,
        value: str | Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange,
    ) -> tuple[str, ...]:
        selected = self.resolve_editable_audio(value)
        if isinstance(selected, Nfl2k5StreamingAudioRange):
            return self.affected_streaming_asset_ids(selected)
        return (selected.asset_id,)

    @property
    def audio_origin_ready(self) -> bool:
        """Whether both strictly loaded private inventories are memory-resident."""

        return (
            self._source_fingerprints is not None
            and self._containment_fingerprints is not None
        )

    @staticmethod
    def _containment_policy(
        assets: Iterable[Nfl2k5AudioAsset],
        slots: Iterable[CanonicalStreamingSlot],
    ) -> Any:
        # Local imports avoid the source-containment scanner -> audio-catalog
        # cycle while reproducing its reviewed deterministic policy derivation.
        from .nfl2k5_audio_containment_fingerprints import (
            PcmContainmentPolicy,
            ShortCueAnchorShape,
        )

        minimum_short: dict[tuple[int, int], int] = {}
        shapes = [
            (asset.channels, asset.sample_rate, asset.frame_count)
            for asset in assets
        ] + [
            (slot.channels, slot.sample_rate, slot.frame_count) for slot in slots
        ]
        for channels, sample_rate, frame_count in shapes:
            long_frames = sample_rate // 4
            if channels not in (1, 2) or sample_rate <= 0 or not 0 < frame_count:
                raise Nfl2k5AudioCatalogError(
                    "Audio catalog has an invalid source-containment PCM shape"
                )
            if frame_count < long_frames:
                key = (channels, sample_rate)
                minimum_short[key] = min(
                    minimum_short.get(key, frame_count), frame_count
                )
        return PcmContainmentPolicy(tuple(
            ShortCueAnchorShape(channels, rate, frames)
            for (channels, rate), frames in sorted(minimum_short.items())
        ))

    def load_private_origin_inventories(self) -> tuple[Any, Any]:
        """Strictly load both source-bound private inventories, once.

        This method never starts the expensive source scanners.  A headless
        coordinator owns generation and progress/cancellation; editing calls
        this loader and receive a direct, actionable error while preparation is
        incomplete.
        """

        if self.audio_origin_ready:
            return self._source_fingerprints, self._containment_fingerprints

        from .nfl2k5_audio_source_containment import (
            Nfl2k5AudioSourceContainmentStore,
        )
        from .nfl2k5_audio_source_fingerprints import (
            Nfl2k5AudioSourceFingerprintStore,
        )

        slots = self.streaming_slot_catalog.slots
        owner_ids = tuple(sorted(
            [asset.asset_id for asset in self.catalog.assets]
            + [owner.asset_id for slot in slots for owner in slot.owners]
        ))
        exact_store = Nfl2k5AudioSourceFingerprintStore(
            expected_source_sha256=SOURCE_SHA256,
            expected_standalone_count=len(self.catalog.assets),
            expected_streaming_slot_count=len(slots),
            expected_streaming_owner_count=sum(len(slot.owners) for slot in slots),
        )
        containment_store = Nfl2k5AudioSourceContainmentStore(
            expected_source_sha256=SOURCE_SHA256,
            expected_cue_count=len(self.catalog.assets) + len(slots),
            expected_owner_count=len(owner_ids),
        )
        policy = self._containment_policy(self.catalog.assets, slots)
        try:
            exact = exact_store.load_existing(
                self.cache, self.catalog.assets, slots
            )
            containment = containment_store.load_existing(
                self.cache, policy, owner_ids
            )
        except ValidationError as exc:
            raise Nfl2k5AudioCatalogError(
                "Private audio safety data is unsafe or no longer matches this "
                f"game copy. Run headless audio preparation again. {exc}"
            ) from exc
        if exact is None or containment is None:
            missing = []
            if exact is None:
                missing.append("exact source-audio inventory")
            if containment is None:
                missing.append("source-audio containment inventory")
            raise Nfl2k5AudioCatalogError(
                "Audio editing needs private safety preparation for this game "
                f"copy ({' and '.join(missing)} missing). Run the headless audio "
                "preparation job, then retry; browsing, playback, and export remain available."
            )
        if not (
            exact.source_sha256
            == containment.source_binding_sha256
            == SOURCE_SHA256
        ):
            raise Nfl2k5AudioCatalogError(
                "Private audio safety inventories belong to a different game copy"
            )
        # Publish to the live service only after both complete loads and their
        # shared source binding pass. A partial failure never creates readiness.
        self._source_fingerprints = exact
        self._containment_fingerprints = containment
        return exact, containment

    def original_path(self, asset: str | Nfl2k5AudioAsset) -> Path:
        selected = self.catalog.get_asset(asset)
        return self.cache.originals / "audio" / f"{_asset_key(selected.asset_id)}.wav"

    def streaming_range_original_path(
        self, item: str | Nfl2k5StreamingAudioRange
    ) -> Path:
        selected = self.catalog.get_streaming_range(item)
        return (
            self.cache.originals / "audio" / "streaming-ranges"
            / f"{_asset_key(selected.asset_id)}.wav"
        )

    def audio_original_path(
        self,
        item: str | Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange,
    ) -> Path:
        selected = self.resolve_editable_audio(item)
        if isinstance(selected, Nfl2k5StreamingAudioRange):
            return self.ensure_streaming_range_wav(selected)
        return self.ensure_original(selected)

    def audio_playback_path(
        self,
        item: str | Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange,
    ) -> Path:
        selected = self.resolve_playable_audio(item)
        if isinstance(selected, Nfl2k5StreamingAudioRange):
            return self.streaming_range_playback_path(selected)
        return self.playback_path(selected)

    def ensure_original(self, asset: str | Nfl2k5AudioAsset) -> Path:
        """Decode and verify a private original only when it is first requested."""

        selected = self.catalog.get_asset(asset)
        output = self.original_path(selected)
        metadata = output.with_suffix(".json")
        if output.is_file() and metadata.is_file() and not output.is_symlink() \
                and not metadata.is_symlink():
            try:
                payload = output.read_bytes()
                record = json.loads(metadata.read_text(encoding="utf-8"))
                channels, rate, frames, pcm = _wav_info(payload)
                if record == {
                    "asset_id": selected.asset_id,
                    "channels": selected.channels,
                    "decoded_pcm_sha256": selected.decoded_pcm_sha256,
                    "frame_count": selected.frame_count,
                    "sample_rate": selected.sample_rate,
                    "schema": ORIGINAL_SCHEMA,
                    "source_sha256": SOURCE_SHA256,
                    "wav_sha256": hashlib.sha256(payload).hexdigest(),
                    "wav_size": len(payload),
                } and (
                    channels,
                    rate,
                    frames,
                    hashlib.sha256(pcm).hexdigest(),
                ) == (
                    selected.channels,
                    selected.sample_rate,
                    selected.frame_count,
                    selected.decoded_pcm_sha256,
                ):
                    return output
            except (OSError, json.JSONDecodeError, Nfl2k5AudioCatalogError):
                pass
            raise Nfl2k5AudioCatalogError(
                "A private original-audio backup changed outside Mod Studio. "
                "Remove the source cache and load the XISO again."
            )
        if os.path.lexists(output) or os.path.lexists(metadata):
            raise Nfl2k5AudioCatalogError(
                "A private original-audio backup is incomplete or unsafe. "
                "Remove the source cache and load the XISO again."
            )

        wav_payload, pcm = self._decode_wav(selected)
        _atomic_write(output, wav_payload)
        sidecar = {
            "asset_id": selected.asset_id,
            "channels": selected.channels,
            "decoded_pcm_sha256": hashlib.sha256(pcm).hexdigest(),
            "frame_count": selected.frame_count,
            "sample_rate": selected.sample_rate,
            "schema": ORIGINAL_SCHEMA,
            "source_sha256": SOURCE_SHA256,
            "wav_sha256": hashlib.sha256(wav_payload).hexdigest(),
            "wav_size": len(wav_payload),
        }
        try:
            _atomic_write(
                metadata,
                (json.dumps(sidecar, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            )
        except BaseException:
            output.unlink(missing_ok=True)
            raise
        return output

    def playback_path(self, asset: str | Nfl2k5AudioAsset) -> Path:
        """Return a local WAV path suitable for a GUI media player."""

        return self.ensure_original(asset)

    def ensure_streaming_range_wav(
        self,
        item: str | Nfl2k5StreamingAudioRange,
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        """Decode and verify one private AUSB range as Xbox IMA PCM16 WAV."""

        selected = self.catalog.get_streaming_range(item)
        output = self.streaming_range_original_path(selected)
        metadata = output.with_suffix(".json")
        wav_payload, pcm, raw_sha256 = self._decode_streaming_range_wav(
            selected, progress
        )
        sidecar = {
            "asset_id": selected.asset_id,
            "channels": selected.channels,
            "decoded_pcm_sha256": hashlib.sha256(pcm).hexdigest(),
            "encoded_range_sha256": raw_sha256,
            "encoded_range_size": selected.stored_size,
            "frame_count": selected.frame_count,
            "sample_rate": selected.sample_rate,
            "schema": STREAMING_RANGE_ORIGINAL_SCHEMA,
            "source_sha256": SOURCE_SHA256,
            "wav_sha256": hashlib.sha256(wav_payload).hexdigest(),
            "wav_size": len(wav_payload),
        }
        if output.is_file() and metadata.is_file() and not output.is_symlink() \
                and not metadata.is_symlink():
            try:
                cached_payload = output.read_bytes()
                cached_record = json.loads(metadata.read_text(encoding="utf-8"))
                channels, rate, frames, cached_pcm = _wav_info(cached_payload)
                if cached_record == sidecar and cached_payload == wav_payload and (
                    channels, rate, frames, cached_pcm
                ) == (
                    selected.channels,
                    selected.sample_rate,
                    selected.frame_count,
                    pcm,
                ):
                    return output
            except (OSError, json.JSONDecodeError, Nfl2k5AudioCatalogError):
                pass
            raise Nfl2k5AudioCatalogError(
                "A private decoded streaming-range cache changed outside Mod Studio. "
                "Remove the source cache and load the XISO again."
            )
        if os.path.lexists(output) or os.path.lexists(metadata):
            raise Nfl2k5AudioCatalogError(
                "A private decoded streaming-range cache is incomplete or unsafe. "
                "Remove the source cache and load the XISO again."
            )
        _atomic_write(output, wav_payload)
        try:
            _atomic_write(
                metadata,
                (json.dumps(sidecar, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            )
        except BaseException:
            output.unlink(missing_ok=True)
            raise
        return output

    def streaming_range_playback_path(
        self,
        item: str | Nfl2k5StreamingAudioRange,
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        """Return a verified private WAV for one indexed streaming range."""

        return self.ensure_streaming_range_wav(item, progress)

    def export_wav(
        self,
        asset: str | Nfl2k5AudioAsset,
        destination: Path,
        *,
        replace: bool = False,
    ) -> Path:
        selected = self.catalog.get_asset(asset)
        output = destination.expanduser()
        if not output.is_absolute():
            output = Path.cwd() / output
        if output.suffix.lower() != ".wav":
            raise Nfl2k5AudioCatalogError("Audio export needs a .wav filename")
        original = self.ensure_original(selected)
        return _atomic_write(output, original.read_bytes(), replace=replace)

    def export_streaming_bank(
        self,
        bank: str | Nfl2k5StreamingAudioBank,
        destination: Path,
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        """Export one complete multi-cue bank from the user's private archive.

        This intentionally does not pretend the complete bank is one WAV or
        expose a replacement route. The descriptor's final indexed boundary
        must own the complete external archive entry before any bytes are
        copied.
        """

        selected = self.catalog.get_streaming_bank(bank)
        try:
            entry = self.archive.entries[selected.external_outer_index]
        except IndexError as exc:
            raise Nfl2k5AudioCatalogError(
                "The streaming bank's external archive entry is unavailable"
            ) from exc
        if (
            f"0x{entry.name_id:08x}" != selected.external_outer_id
            or entry.size != selected.external_size
            or selected.boundaries[0] != 0
            or selected.boundaries[-1] != entry.size
            or len(selected.boundaries) != selected.entry_count + 1
        ):
            raise Nfl2k5AudioCatalogError(
                "The streaming bank no longer matches its indexed ownership boundary"
            )
        return _stream_entry_to_new_file(
            self.archive, entry, destination, progress=progress
        )

    def export_streaming_range(
        self,
        item: str | Nfl2k5StreamingAudioRange,
        destination: Path,
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        """Export one exact indexed bank range as opaque raw bytes."""

        selected = self.catalog.get_streaming_range(item)
        bank = self.catalog.get_streaming_bank(selected.bank)
        try:
            entry = self.archive.entries[bank.external_outer_index]
        except IndexError as exc:
            raise Nfl2k5AudioCatalogError(
                "The streaming range's external archive entry is unavailable"
            ) from exc
        if (
            f"0x{entry.name_id:08x}" != bank.external_outer_id
            or entry.size != bank.external_size
            or selected.end < selected.start
            or selected.start != bank.boundaries[selected.range_index]
            or selected.end != bank.boundaries[selected.range_index + 1]
            or selected.end > entry.size
        ):
            raise Nfl2k5AudioCatalogError(
                "The streaming range no longer matches its indexed ownership boundary"
            )
        return _stream_entry_to_new_file(
            self.archive,
            entry,
            destination,
            progress=progress,
            relative_offset=selected.start,
            length=selected.stored_size,
        )

    def export_streaming_range_wav(
        self,
        item: str | Nfl2k5StreamingAudioRange,
        destination: Path,
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        """Export one proved Xbox IMA range as a standard PCM16 WAV."""

        selected = self.catalog.get_streaming_range(item)
        output = destination.expanduser()
        if not output.is_absolute():
            output = Path.cwd() / output
        if output.suffix.lower() != ".wav":
            raise Nfl2k5AudioCatalogError(
                "Decoded streaming-range export needs a .wav filename"
            )
        original = self.ensure_streaming_range_wav(selected, progress)
        return _atomic_write(output, original.read_bytes())

    def read_replacement_snapshot(
        self,
        asset: str | Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange,
        wav_path: Path,
    ) -> AudioReplacementSnapshot:
        """Read a caller WAV exactly once and validate its canonical shape."""

        selected = self.resolve_editable_audio(asset)
        requested = wav_path.expanduser()
        if requested.suffix.lower() != ".wav":
            raise Nfl2k5AudioCatalogError("The audio replacement needs a .wav file")
        try:
            resolved, payload = read_bounded_regular_file(
                requested,
                "Replacement WAV",
                maximum=MAX_AUDIO_REPLACEMENT_WAV_BYTES,
                error_type=Nfl2k5AudioCatalogError,
            )
        except Nfl2k5AudioCatalogError as exc:
            message = str(exc)
            if " is missing:" in message:
                raise Nfl2k5AudioCatalogError("Choose an existing WAV file") from exc
            if "regular file" in message or "hard-linked" in message:
                raise Nfl2k5AudioCatalogError(
                    "Choose a regular WAV file, not a folder or link"
                ) from exc
            if "empty or too large" in message:
                raise Nfl2k5AudioCatalogError(
                    "That WAV is empty or exceeds the input limit"
                ) from exc
            raise
        contract = selected.replacement_contract
        assert contract is not None
        try:
            _validate_strict_pcm16_wav_shape(
                payload,
                channels=contract.channels,
                sample_rate=contract.sample_rate,
                frame_count=contract.frame_count,
            )
        except Nfl2k5AudioCatalogError as exc:
            channel_text = "mono" if contract.channels == 1 else "stereo"
            target_name = (
                "Menu Back"
                if isinstance(selected, Nfl2k5AudioAsset)
                and selected.selector == MENU_BACK_SELECTOR
                else selected.name
            )
            raise Nfl2k5AudioCatalogError(
                f"{target_name} needs a canonical {channel_text} PCM16 WAV at "
                f"exactly {contract.sample_rate:,} Hz with exactly "
                f"{contract.frame_count:,} frames and no metadata chunks. {exc}"
            ) from exc
        metadata = AudioReplacementMetadata(
            asset_id=selected.asset_id,
            capability_id=contract.capability_id,
            provider_id=contract.provider_id,
            target=contract.target,
            wav_path=resolved,
            wav_size=len(payload),
            wav_sha256=hashlib.sha256(payload).hexdigest(),
            channels=contract.channels,
            sample_rate=contract.sample_rate,
            frame_count=contract.frame_count,
        )
        return AudioReplacementSnapshot(metadata, payload)

    def validate_replacement(
        self,
        asset: str | Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange,
        wav_path: Path,
    ) -> AudioReplacementMetadata:
        """Compatibility view of one strict immutable path snapshot."""

        return self.read_replacement_snapshot(asset, wav_path).metadata

    def authorize_user_replacement_bytes(
        self,
        asset: str | Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange,
        wav_bytes: bytes,
    ) -> Any:
        """Authorize exact immutable bytes against both private source gates."""

        selected = self.resolve_editable_audio(asset)
        contract = selected.replacement_contract
        assert contract is not None
        # Keep structural diagnostics close to the selected logical cue before
        # loading the much larger private containment inventory.
        _validate_strict_pcm16_wav_shape(
            wav_bytes,
            channels=contract.channels,
            sample_rate=contract.sample_rate,
            frame_count=contract.frame_count,
        )
        exact, containment = self.load_private_origin_inventories()
        from .nfl2k5_audio_origin_authorization import (
            authorize_strict_pcm16_wav,
            require_authorized_pcm16_wav,
        )

        try:
            issued = authorize_strict_pcm16_wav(
                wav_bytes,
                target_channels=contract.channels,
                target_sample_rate=contract.sample_rate,
                target_frame_count=contract.frame_count,
                source_fingerprints=exact,
                containment_fingerprints=containment,
            )
            issued = require_authorized_pcm16_wav(issued)
        except ValidationError as exc:
            raise Nfl2k5AudioCatalogError(str(exc)) from exc
        if issued.wav_bytes is not wav_bytes:
            raise Nfl2k5AudioCatalogError(
                "Audio origin authorization did not preserve the exact immutable WAV snapshot"
            )
        return issued

    def authorize_replacement_snapshot(
        self,
        asset: str | Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange,
        snapshot: AudioReplacementSnapshot,
    ) -> Any:
        """Authorize a snapshot without ever reopening its caller path."""

        selected = self.resolve_editable_audio(asset)
        if (
            type(snapshot) is not AudioReplacementSnapshot
            or snapshot.metadata.asset_id != selected.asset_id
            or snapshot.metadata.wav_size != len(snapshot.wav_bytes)
            or snapshot.metadata.wav_sha256
            != hashlib.sha256(snapshot.wav_bytes).hexdigest()
        ):
            raise Nfl2k5AudioCatalogError(
                "Replacement WAV snapshot no longer matches its validated metadata"
            )
        return self.authorize_user_replacement_bytes(selected, snapshot.wav_bytes)

    def validate_user_replacement(
        self,
        asset: str | Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange,
        wav_path: Path,
    ) -> AudioReplacementMetadata:
        """Compatibility path API backed by the complete two-inventory gate."""

        snapshot = self.read_replacement_snapshot(asset, wav_path)
        self.authorize_replacement_snapshot(asset, snapshot)
        return snapshot.metadata

    @staticmethod
    def _raise_source_derived_audio(owner_name: str) -> None:
        raise Nfl2k5AudioCatalogError(
            f"That WAV contains decoded source audio from {owner_name}. "
            "Retail-derived audio cannot be stored in a shareable Mod Studio "
            "project. Choose audio you created or have permission to distribute."
        )

    def _cached_streaming_pcm_owner(
        self, pcm_sha256: str
    ) -> Nfl2k5StreamingAudioRange | None:
        """Return a fully verified cached streaming owner for one PCM hash.

        Streaming-range PCM hashes are deliberately not shipped as retail
        fingerprints.  The private cache sidecars created by Play/Export WAV
        let the project boundary still reject any exact streaming source audio
        the current installation has decoded.
        """

        root = self.cache.originals / "audio" / "streaming-ranges"
        try:
            root_info = root.lstat()
        except FileNotFoundError:
            self._streaming_pcm_cache_stamp = None
            self._streaming_pcm_cache_owners = {}
            return None
        if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode):
            raise Nfl2k5AudioCatalogError(
                "The private streaming-audio cache is unsafe. Remove the source "
                "cache and load the XISO again."
            )
        try:
            entries = tuple(root.iterdir())
            stamp = (root_info.st_mtime_ns, len(entries))
        except OSError as exc:
            raise Nfl2k5AudioCatalogError(
                f"Could not inspect the private streaming-audio cache: {exc}"
            ) from exc
        if stamp != self._streaming_pcm_cache_stamp:
            owners: dict[str, list[str]] = {}
            for sidecar in entries:
                if sidecar.suffix.casefold() != ".json":
                    continue
                try:
                    info = sidecar.lstat()
                    if (
                        not stat.S_ISREG(info.st_mode)
                        or stat.S_ISLNK(info.st_mode)
                        or not 0 < info.st_size <= MAX_ORIGINAL_SIDECAR_BYTES
                    ):
                        continue
                    record = json.loads(sidecar.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError):
                    continue
                if not isinstance(record, dict) or (
                    record.get("schema") != STREAMING_RANGE_ORIGINAL_SCHEMA
                    or record.get("source_sha256") != SOURCE_SHA256
                    or _SHA256_RE.fullmatch(
                        str(record.get("decoded_pcm_sha256", ""))
                    ) is None
                ):
                    continue
                asset_id = record.get("asset_id")
                if not isinstance(asset_id, str):
                    continue
                try:
                    item = self.catalog.get_streaming_range(asset_id)
                except Nfl2k5AudioCatalogError:
                    continue
                if (
                    sidecar != self.streaming_range_original_path(item).with_suffix(
                        ".json"
                    )
                    or record.get("channels") != item.channels
                    or record.get("sample_rate") != item.sample_rate
                    or record.get("frame_count") != item.frame_count
                ):
                    continue
                owners.setdefault(record["decoded_pcm_sha256"], []).append(
                    item.asset_id
                )
            self._streaming_pcm_cache_owners = {
                digest: tuple(sorted(asset_ids))
                for digest, asset_ids in owners.items()
            }
            self._streaming_pcm_cache_stamp = stamp

        for asset_id in self._streaming_pcm_cache_owners.get(pcm_sha256, ()):
            item = self.catalog.get_streaming_range(asset_id)
            verified = self.ensure_streaming_range_wav(item)
            try:
                payload = verified.read_bytes()
            except OSError as exc:
                raise Nfl2k5AudioCatalogError(
                    f"Could not verify cached streaming source audio: {exc}"
                ) from exc
            channels, rate, frames, pcm = _wav_info(payload)
            if (
                (channels, rate, frames)
                != (item.channels, item.sample_rate, item.frame_count)
            ):
                raise Nfl2k5AudioCatalogError(
                    "Cached streaming source audio changed during validation"
                )
            if hashlib.sha256(pcm).hexdigest() == pcm_sha256:
                return item
        return None

    def create_replacement_plan(
        self,
        asset: str | Nfl2k5AudioAsset,
        wav_path: Path,
        recipe_output: Path,
        *,
        purpose: str,
    ) -> AudioReplacementPlan:
        """Validate user audio and route it to the existing typed provider recipe."""

        selected = self.catalog.get_asset(asset)
        if selected.selector != MENU_BACK_SELECTOR:
            raise Nfl2k5AudioCatalogError(
                "Additional standalone sounds build through a normal Mod Studio project; "
                "the legacy one-file recipe is available only for Menu Back."
            )
        replacement = self.validate_replacement(selected, wav_path)
        recipe = create_nfl_menu_back_audio_recipe(
            output=recipe_output,
            purpose=purpose,
            wav=replacement.wav_path,
        )
        return AudioReplacementPlan(selected, replacement, recipe)

    @staticmethod
    def replacement_provider(**kwargs: Any) -> Any:
        """Factory used by the build coordinator for an audio replacement plan."""

        from .nfl_audio_provider import Nfl2k5MenuBackAudioProvider

        return Nfl2k5MenuBackAudioProvider(**kwargs)

    def _decode_streaming_range_wav(
        self,
        item: Nfl2k5StreamingAudioRange,
        progress: Callable[[int, int], None] | None = None,
    ) -> tuple[bytes, bytes, str]:
        bank = self.catalog.get_streaming_bank(item.bank)
        try:
            entry = self.archive.entries[bank.external_outer_index]
        except IndexError as exc:
            raise Nfl2k5AudioCatalogError(
                "The streaming range's external archive entry is unavailable"
            ) from exc
        if (
            f"0x{entry.name_id:08x}" != bank.external_outer_id
            or entry.size != bank.external_size
            or item.start != bank.boundaries[item.range_index]
            or item.end != bank.boundaries[item.range_index + 1]
            or item.stored_size <= 0
            or item.stored_size % (36 * item.channels) != 0
            or item.frame_count * item.channels * 2 + 44 > MAX_WAV_BYTES
        ):
            raise Nfl2k5AudioCatalogError(
                "The streaming range no longer matches its Xbox IMA ownership contract"
            )
        try:
            payload = read_entry_range(
                self.archive, entry, item.start, item.stored_size
            )
        except (OSError, FormatError) as exc:
            raise Nfl2k5AudioCatalogError(
                f"Could not read the private streaming range: {exc}"
            ) from exc
        if len(payload) != item.stored_size:
            raise Nfl2k5AudioCatalogError(
                "The private streaming range shortened during decode"
            )
        if progress is not None:
            progress(0, len(payload))
        pcm = _decode_streaming_xbox_ima_pcm(
            payload, item.channels, progress
        )
        if len(pcm) != item.frame_count * item.channels * 2:
            raise Nfl2k5AudioCatalogError(
                "The Xbox IMA range decoded to an inconsistent frame count"
            )
        stream = io.BytesIO()
        with wave.open(stream, "wb") as wav:
            wav.setnchannels(item.channels)
            wav.setsampwidth(2)
            wav.setframerate(item.sample_rate)
            wav.writeframes(pcm)
        output = stream.getvalue()
        channels, rate, frames, checked_pcm = _wav_info(output)
        if (channels, rate, frames, checked_pcm) != (
            item.channels,
            item.sample_rate,
            item.frame_count,
            pcm,
        ):
            raise Nfl2k5AudioCatalogError(
                "Decoded streaming-range WAV failed its in-memory round trip"
            )
        return output, pcm, hashlib.sha256(payload).hexdigest()

    def _decode_wav(self, asset: Nfl2k5AudioAsset) -> tuple[bytes, bytes]:
        try:
            entry = self.archive.entries[asset.outer_index]
        except IndexError as exc:
            raise Nfl2k5AudioCatalogError("Audio outer-entry selector is unavailable") from exc
        if (
            entry.size != asset.outer_size
            or f"0x{entry.name_id:08x}" != asset.outer_id
            or entry.head_ascii != asset.outer_head
        ):
            raise Nfl2k5AudioCatalogError("Audio outer-entry ownership changed")
        span = read_entry_range(
            self.archive, entry, asset.chunk_offset, 0x20 + asset.stored_size
        )
        record = ResourceRecord(
            outer_index=asset.outer_index,
            outer_id=asset.outer_id,
            outer_size=asset.outer_size,
            chunk_index=asset.chunk_index,
            chunk_offset=asset.chunk_offset,
            kind="AUDO",
            stored_size=asset.stored_size,
            word_08=asset.system_bytes,
            word_0c=asset.payload_bytes,
            word_10=0,
            word_14=0,
        )
        try:
            body, _detail = decode_resource(span, record)
            semantic = probe_audo(body, record, True)
        except (ProbeError, FormatError, struct.error, ValueError) as exc:
            raise Nfl2k5AudioCatalogError(f"Could not decode {asset.name}: {exc}") from exc
        if hashlib.sha256(body).hexdigest() != asset.resource_body_sha256:
            raise Nfl2k5AudioCatalogError("Audio resource body differs from its private index")
        expected_semantic = (
            asset.name,
            asset.channels,
            asset.sample_rate,
            asset.payload_bytes,
        )
        actual_semantic = (
            semantic.get("name"),
            semantic.get("channels"),
            semantic.get("sample_rate"),
            semantic.get("data_size"),
        )
        if actual_semantic != expected_semantic:
            raise Nfl2k5AudioCatalogError("Decoded audio metadata differs from its catalog row")
        data_start = asset.system_bytes + int(semantic["data_offset"])
        payload = body[data_start:data_start + asset.payload_bytes]
        if len(payload) != asset.payload_bytes \
                or hashlib.sha256(payload).hexdigest() != asset.payload_sha256:
            raise Nfl2k5AudioCatalogError("Audio payload differs from its catalog hash")
        try:
            samples = decode_xbox_ima(payload, asset.channels)
        except ProbeError as exc:
            raise Nfl2k5AudioCatalogError(f"Could not decode {asset.name}: {exc}") from exc
        pcm = struct.pack(f"<{len(samples)}h", *samples)
        if len(samples) != asset.frame_count * asset.channels \
                or hashlib.sha256(pcm).hexdigest() != asset.decoded_pcm_sha256:
            raise Nfl2k5AudioCatalogError("Decoded PCM differs from its catalog hash")
        stream = io.BytesIO()
        with wave.open(stream, "wb") as wav:
            wav.setnchannels(asset.channels)
            wav.setsampwidth(2)
            wav.setframerate(asset.sample_rate)
            wav.writeframes(pcm)
        output = stream.getvalue()
        if not 44 <= len(output) <= MAX_WAV_BYTES:
            raise Nfl2k5AudioCatalogError("Decoded WAV is outside the product size limit")
        channels, rate, frames, checked_pcm = _wav_info(output)
        if (channels, rate, frames, checked_pcm) != (
            asset.channels,
            asset.sample_rate,
            asset.frame_count,
            pcm,
        ):
            raise Nfl2k5AudioCatalogError("Decoded WAV failed its in-memory round trip")
        return output, pcm


__all__ = [
    "apply_family_label_promotions",
    "AudioAliasGroup",
    "AudioReplacementContract",
    "AudioReplacementMetadata",
    "AudioReplacementPlan",
    "AudioReplacementSnapshot",
    "CAPACITY_REPORT",
    "EXPECTED_AUDIO_COUNT",
    "EXPECTED_PLAYABLE_AUDIO_COUNT",
    "EXPECTED_STREAMING_BANK_COUNT",
    "EXPECTED_STREAMING_RANGE_COUNT",
    "EXPORT_CAPABILITY_ID",
    "FIXED_AUDO_CAPABILITY_ID",
    "FIXED_AUDO_PROVIDER_ID",
    "MENU_BACK_CAPABILITY_ID",
    "MENU_BACK_PROVIDER_ID",
    "MENU_BACK_SELECTOR",
    "MAX_AUDIO_REPLACEMENT_WAV_BYTES",
    "Nfl2k5AudioAsset",
    "Nfl2k5AudioCatalog",
    "Nfl2k5AudioCatalogError",
    "Nfl2k5AudioService",
    "Nfl2k5StreamingAudioBank",
    "Nfl2k5StreamingAudioRange",
    "PLAYABLE_AUDIO_FAMILIES",
    "PLAYABLE_AUDIO_SCOPE_ID",
    "STANDALONE_AUDIO_FAMILIES",
    "STREAMING_AUDIO_FAMILIES",
    "STREAMING_AUSB_CAPABILITY_ID",
    "STREAMING_AUSB_PROVIDER_ID",
]
