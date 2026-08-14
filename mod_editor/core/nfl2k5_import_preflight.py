"""Predict what a fixed VC-LZ slot will do to a replacement, before a build.

Every P8 uniform target in NFL 2K5 is a *fixed compressed span*: the decoded
payload is a constant size, and its VC-LZ stream has to fit an allocation the
game reserved.  When it does not, the importers step the palette down from 256
until it does (see ``nfl_tset_png_import.quantize_levels_to_vc_lz_bound``).

That step is lossy, and until this module existed it happened silently and only
at build time -- so a user learned that their artwork had lost 240 palette
entries by looking at the result, if at all.  This runs the same ladder against
a staged PNG up front and says which slots come through untouched, which lose
colours and how many, and which cannot fit at all.

**It is a prediction, not a claim about the build.**  It runs the real
quantizer and the real encoder against the real slot contract, so for the
families modelled here it agrees with the importer by construction.  A family
with no contract below is reported as unmodelled rather than guessed at.

Cost is roughly 1 s for a slot that fits at full palette and up to ~6 s for one
that walks the whole ladder -- against tens of seconds per target for a build
that then refuses.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Callable, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl_tset_png_import as palette_tools  # noqa: E402
from nfl_txtr import TxtrError, swizzle_2d  # noqa: E402


#: Outcome vocabulary. Deliberately three words, because a user's next action
#: differs for each: nothing, decide whether the loss is acceptable, or fix the
#: image.
FULL = "full"
REDUCED = "reduced"
REFUSED = "refused"
UNMODELLED = "unmodelled"


@dataclass(frozen=True, slots=True)
class SlotContract:
    """The fixed shape one P8 family writes into.

    ``palette_count`` is 2 for the jersey/pants TSETs, which carry a clean and a
    mud palette over one shared index chain, and 1 for the single-palette
    families.
    """

    kind: str
    width: int
    height: int
    mip_levels: int
    system_bytes: int
    palette_count: int

    @property
    def mip_dimensions(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (self.width >> level, self.height >> level)
            for level in range(self.mip_levels)
        )

    @property
    def index_chain_bytes(self) -> int:
        return sum(width * height for width, height in self.mip_dimensions)

    @property
    def decoded_bytes(self) -> int:
        return (
            self.system_bytes
            + self.index_chain_bytes
            + 1024 * self.palette_count
        )


#: The families whose decoded layout is proved and stable enough to predict.
#: Anything absent is reported as UNMODELLED rather than approximated -- a
#: confident wrong number would be worse than no number.
CONTRACTS: dict[str, SlotContract] = {
    "torso": SlotContract("torso", 512, 256, 6, 256, 2),
    "sleeve": SlotContract("sleeve", 512, 256, 6, 256, 2),
    "pants": SlotContract("pants", 512, 256, 6, 256, 2),
    "live_helmet": SlotContract("live_helmet", 256, 256, 6, 128, 1),
}


@dataclass(frozen=True, slots=True)
class SlotPrediction:
    """What one staged PNG will become in one fixed slot."""

    asset_id: str
    label: str
    kind: str
    outcome: str
    palette_entries: int | None = None
    source_colours: int | None = None
    encoded_bytes: int | None = None
    allocation_bytes: int | None = None
    refused_tiers: tuple[int, ...] = ()
    detail: str = ""

    @property
    def headroom_bytes(self) -> int | None:
        if self.encoded_bytes is None or self.allocation_bytes is None:
            return None
        return self.allocation_bytes - self.encoded_bytes

    @property
    def needs_attention(self) -> bool:
        return self.outcome in {REDUCED, REFUSED}

    def summary(self) -> str:
        """One line a user can act on."""

        if self.outcome == FULL:
            return f"{self.label}: fits as authored ({self.palette_entries} colours)."
        if self.outcome == REDUCED:
            return (
                f"{self.label}: will be reduced to {self.palette_entries} colours "
                f"to fit its {self.allocation_bytes:,}-byte slot "
                f"(from {self.source_colours:,} in your image)."
            )
        if self.outcome == REFUSED:
            return f"{self.label}: will not fit at all. {self.detail}"
        return f"{self.label}: {self.detail}"


def _load_rgba(png_path: Path, width: int, height: int) -> bytes:
    """Resize the user's PNG to the slot exactly as the importers do."""

    from PIL import Image

    with Image.open(png_path) as image:
        resized = image.convert("RGBA").resize((width, height), Image.LANCZOS)
        return resized.tobytes()


def _mip_chain(rgba: bytes, contract: SlotContract) -> list:
    """Box-filter the chain the importers build, at their exact dimensions."""

    levels = [palette_tools.MipLevel(0, contract.width, contract.height, rgba)]
    current, width, height = rgba, contract.width, contract.height
    for level in range(1, contract.mip_levels):
        next_width, next_height = width // 2, height // 2
        reduced = bytearray(next_width * next_height * 4)
        for y in range(next_height):
            row = y * 2
            for x in range(next_width):
                column = x * 2
                sources = (
                    (row * width + column) * 4,
                    (row * width + column + 1) * 4,
                    ((row + 1) * width + column) * 4,
                    ((row + 1) * width + column + 1) * 4,
                )
                target = (y * next_width + x) * 4
                for channel in range(4):
                    total = sum(current[source + channel] for source in sources)
                    reduced[target + channel] = (total + 2) // 4
        current, width, height = bytes(reduced), next_width, next_height
        levels.append(palette_tools.MipLevel(level, width, height, current))
    return levels


def predict_slot(
    png_path: Path,
    contract: SlotContract,
    allocation_bytes: int,
    *,
    stream_tag: int = 1,
    offset_bits: int = 12,
    asset_id: str = "",
    label: str = "",
) -> SlotPrediction:
    """Run the real ladder against one staged PNG and report the outcome.

    The decoded payload is assembled with a zero system block. Only its *size*
    reaches the encoder's ratio, and every real system block is small and
    constant per family, so the predicted tier matches what the importer picks.
    """

    name = label or asset_id or contract.kind
    try:
        rgba = _load_rgba(Path(png_path), contract.width, contract.height)
    except Exception as exc:
        return SlotPrediction(
            asset_id, name, contract.kind, UNMODELLED,
            detail=f"the image could not be read ({exc}).",
        )
    source_colours = len(
        set(zip(rgba[0::4], rgba[1::4], rgba[2::4], rgba[3::4]))
    )
    levels = _mip_chain(rgba, contract)
    system = bytes(contract.system_bytes)

    def candidate(palette, index_levels) -> bytes:
        chain = b"".join(
            swizzle_2d(indices, level.width, level.height, 1)
            for indices, level in zip(index_levels, levels)
        )
        return (
            system
            + chain
            + palette_tools.palette_bytes(palette) * contract.palette_count
        )

    try:
        fit = palette_tools.quantize_levels_to_vc_lz_bound(
            levels,
            candidate,
            stream_tag=stream_tag,
            offset_bits=offset_bits,
            max_encoded_size=allocation_bytes,
        )
    except TxtrError as exc:
        return SlotPrediction(
            asset_id, name, contract.kind, REFUSED,
            source_colours=source_colours,
            allocation_bytes=allocation_bytes,
            detail=(
                f"{exc} Remove fine noise, dithering, and long smooth "
                "gradients, which cost the most compressed space."
            ),
        )
    refused = tuple(
        int(attempt["maximum_palette_entries"])
        for attempt in fit.attempts
        if attempt["result"] == "vc_lz_overflow"
    )
    return SlotPrediction(
        asset_id=asset_id,
        label=name,
        kind=contract.kind,
        outcome=REDUCED if refused else FULL,
        palette_entries=len(fit.palette),
        source_colours=source_colours,
        encoded_bytes=len(fit.compressed),
        allocation_bytes=allocation_bytes,
        refused_tiers=refused,
        detail=(
            "Distinct shade count is what costs compressed space here, not "
            "image resolution — the editor resizes to the slot either way."
            if refused else ""
        ),
    )


def predict_edits(
    edits: Iterable[tuple[str, str, str, Path, int]],
    *,
    progress: Callable[[str, int, int], None] | None = None,
) -> tuple[SlotPrediction, ...]:
    """Predict a whole staged set.

    Each edit is ``(asset_id, label, kind, png_path, allocation_bytes)``. A kind
    with no modelled contract is reported as unmodelled and costs nothing.
    """

    rows: list[SlotPrediction] = []
    staged: Sequence = list(edits)
    for index, (asset_id, label, kind, png_path, allocation) in enumerate(staged):
        if progress is not None:
            progress(f"Checking {label or asset_id}", index, len(staged))
        contract = CONTRACTS.get(kind)
        if contract is None:
            rows.append(SlotPrediction(
                asset_id, label or asset_id, kind, UNMODELLED,
                detail="this family has no fixed-span prediction yet.",
            ))
            continue
        rows.append(predict_slot(
            Path(png_path), contract, int(allocation),
            asset_id=asset_id, label=label or asset_id,
        ))
    if progress is not None:
        progress("Check complete", len(staged), len(staged))
    return tuple(rows)


def report(predictions: Sequence[SlotPrediction]) -> str:
    """A short human summary of a whole check."""

    if not predictions:
        return "Nothing is staged, so there is nothing to check."
    full = [row for row in predictions if row.outcome == FULL]
    reduced = [row for row in predictions if row.outcome == REDUCED]
    refused = [row for row in predictions if row.outcome == REFUSED]
    unmodelled = [row for row in predictions if row.outcome == UNMODELLED]
    lines: list[str] = []
    if refused:
        lines.append(
            f"{len(refused)} will not fit and will stop the build:"
        )
        lines.extend(f"  • {row.summary()}" for row in refused)
    if reduced:
        lines.append(
            f"{len(reduced)} will build, but lose colours to fit a fixed slot:"
        )
        lines.extend(f"  • {row.summary()}" for row in reduced)
    if full:
        lines.append(f"{len(full)} fit as authored, untouched.")
    if unmodelled:
        lines.append(
            f"{len(unmodelled)} could not be predicted and will be decided at "
            "build time."
        )
    return "\n".join(lines)


__all__ = [
    "CONTRACTS",
    "FULL",
    "REDUCED",
    "REFUSED",
    "UNMODELLED",
    "SlotContract",
    "SlotPrediction",
    "predict_edits",
    "predict_slot",
    "report",
]
