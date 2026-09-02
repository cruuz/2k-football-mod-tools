"""Everything one NFL 2K5 player owns, gathered in one place.

A modder who wants to work on a player has to know things the app never told
them: that the face texture is found by a ``face_id`` stored in the player's
own roster record, that a portrait is a separate numbered image, and that
neither is filed under the player's name anywhere in the interface. So the
usual answer to "which face is Aeneas Williams?" was to scroll a list of 1,872
textures hoping the label matched.

This joins them. Given the roster, it reports for each player the face
textures, the portrait, and the identity fields that belong to them, with the
link stated rather than guessed: ``face_id`` is read out of the player record
at offset ``0x06`` by the existing text catalog, and the live-face catalog is
keyed by exactly that number.

Two things it deliberately does not do:

* **It does not invent an equipment link.** Gloves, cleats, wristbands and
  elbow pads exist in NFL 2K5 as five shared textures, one copy for the whole
  game, so there is nothing per-player to report. Saying "this player's gloves"
  would be a lie about how the disc stores them; the report says they are
  shared and names them once.
* **It does not claim a portrait link that is not in the bytes.** Portraits are
  numbered separately from faces, and nothing found so far ties a portrait
  number to a player record. Where a portrait's own label carries the player's
  name the match is reported as ``by_name`` and flagged as such, rather than
  being presented as though it came from the roster.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence


# The five equipment textures NFL 2K5 actually stores, and what they cover.
# One copy each for the whole game -- see docs/research/nfl2k5_all_texture_replacement.md.
SHARED_EQUIPMENT: tuple[tuple[str, str], ...] = (
    ("shoes_taped", "Shoes — taped"),
    ("wristband_qb", "Wristband — quarterback"),
    ("elbowpad_taped", "Elbow pad — taped"),
    ("elbowpad_rubber", "Elbow pad — rubber"),
    ("elbowpad_elastic", "Elbow pad — elastic"),
)

EQUIPMENT_NOTE = (
    "NFL 2K5 stores equipment as shared textures, one copy for the whole game, "
    "so these are not per-player. Editing one changes it for everybody."
)


@dataclass(frozen=True)
class PlayerAsset:
    """One editable thing that belongs to a player."""

    asset_id: str
    label: str
    kind: str          # "live_face" | "player_portrait"
    link: str          # "face_id" (from the roster record) | "by_name"
    width: int = 0
    height: int = 0


@dataclass(frozen=True)
class PlayerAssetSummary:
    """A player, and everything the disc lets you edit about them."""

    player_index: int
    outer_index: int
    name: str
    face_id: str
    assets: tuple[PlayerAsset, ...] = ()
    identity_asset_ids: tuple[str, ...] = ()
    jersey_asset_id: str | None = None
    notes: tuple[str, ...] = ()

    @property
    def face_assets(self) -> tuple[PlayerAsset, ...]:
        return tuple(a for a in self.assets if a.kind == "live_face")

    @property
    def portrait_assets(self) -> tuple[PlayerAsset, ...]:
        return tuple(a for a in self.assets if a.kind == "player_portrait")


def _normalise_name(value: str) -> str:
    return " ".join(str(value).split()).casefold()


def _faces_by_id(assets: Iterable[Any]) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = {}
    for asset in assets:
        if getattr(asset, "kind", None) != "live_face":
            continue
        face_id = getattr(asset, "face_id", None)
        if face_id is None:
            continue
        grouped.setdefault(str(face_id), []).append(asset)
    return grouped


def _portraits_by_name(assets: Iterable[Any]) -> dict[str, list[Any]]:
    """Portraits carry a name in their label but no roster link in the bytes."""
    grouped: dict[str, list[Any]] = {}
    for asset in assets:
        if getattr(asset, "kind", None) != "player_portrait":
            continue
        label = str(getattr(asset, "label", ""))
        if "—" not in label:
            continue
        name = _normalise_name(label.split("—", 1)[1])
        if not name or name.startswith("*") or "unassigned" in name:
            continue
        grouped.setdefault(name, []).append(asset)
    return grouped


def build_player_assets(
    players: Sequence[Mapping[str, Any]],
    visual_assets: Iterable[Any],
) -> tuple[PlayerAssetSummary, ...]:
    """Join roster players to the textures that belong to them.

    ``players`` are rows carrying at least ``player_index``, ``outer_index``,
    ``name`` and ``face_id`` -- the shape the text catalog already produces.
    ``visual_assets`` is the extended visual catalog.
    """
    assets = list(visual_assets)
    faces = _faces_by_id(assets)
    portraits = _portraits_by_name(assets)

    summaries: list[PlayerAssetSummary] = []
    for row in players:
        face_id = str(row.get("face_id", ""))
        name = str(row.get("name", "")).strip()
        found: list[PlayerAsset] = []

        for asset in faces.get(face_id, ()):
            found.append(PlayerAsset(
                asset_id=str(asset.asset_id),
                label=str(asset.label),
                kind="live_face",
                # Stated, not guessed: the roster record names this texture.
                link="face_id",
                width=int(getattr(asset, "width", 0)),
                height=int(getattr(asset, "height", 0)),
            ))

        for asset in portraits.get(_normalise_name(name), ()):
            found.append(PlayerAsset(
                asset_id=str(asset.asset_id),
                label=str(asset.label),
                kind="player_portrait",
                # Honest about its weakness: matched on the label, not the disc.
                link="by_name",
                width=int(getattr(asset, "width", 0)),
                height=int(getattr(asset, "height", 0)),
            ))

        notes: list[str] = []
        if not faces.get(face_id):
            notes.append(
                f"No live-face texture carries face_id {face_id}; this player "
                "shares a generic head."
            )
        if not portraits.get(_normalise_name(name)):
            notes.append(
                "No portrait matches this player by name. Portraits are "
                "numbered separately and the roster does not point at one."
            )

        summaries.append(PlayerAssetSummary(
            player_index=int(row.get("player_index", -1)),
            outer_index=int(row.get("outer_index", -1)),
            name=name,
            face_id=face_id,
            assets=tuple(found),
            identity_asset_ids=tuple(row.get("identity_asset_ids", ()) or ()),
            jersey_asset_id=row.get("jersey_asset_id"),
            notes=tuple(notes),
        ))
    return tuple(summaries)


def equipment_rows() -> tuple[tuple[str, str], ...]:
    """The shared equipment textures, for a panel that must not imply ownership."""
    return SHARED_EQUIPMENT


__all__ = [
    "EQUIPMENT_NOTE",
    "SHARED_EQUIPMENT",
    "PlayerAsset",
    "PlayerAssetSummary",
    "build_player_assets",
    "equipment_rows",
]
