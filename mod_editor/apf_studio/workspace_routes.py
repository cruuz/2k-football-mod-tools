"""Where the universal browser sends a row a dedicated writer already owns.

The All-Assets browser lists every indexed record, and its own Replace action
only covers the two exact-size PNG slots bound in
:data:`mod_editor.apf_studio.models.ASSET_ACTION_BINDINGS`.  Everything else got
one message: *"<name> is not an editable PNG slot in this browser."*

That sentence was true about the browser and false about the product.  The
browser's own search hints point at ``logo_l0`` and ``shoulder_color``, and both
are written every day -- by ``Logos -> Team Logo`` and by ``Uniforms``,
respectively.  A modder who followed the hint hit a wall in front of a door that
was already open, and reported it against Beta 29 and Beta 30.

This module is the door.  Given one catalog row it answers which workspace owns
a proved writer for that exact record, so the browser can hand the row over
instead of refusing it.  It is deliberately free of Qt and of archive reads: the
caller supplies the tables it already holds, every rule keys on an exact
identity the catalog reports, and an unrecognized row still returns ``None`` so
an unproved record keeps its honest boundary.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .models import ApfAsset, ApfCategory, UniformAsset


#: Inner-file names of the two crest layers inside every ``uniform_logo_NN``
#: package.  ``tools/apf_logo_patch.py`` writes both from one staged mask, which
#: is why either row routes to the same crest slot.
CREST_LAYER_NAMES = ("logo_l0", "logo_l1")

#: The tab titles :class:`~mod_editor.apf_studio.gui.LogosStudioPage` gives its
#: two crest/wordmark editors.  Kept here so a route names its destination
#: exactly rather than by tab position.
TEAM_LOGO_TAB = "Team Logo"
WORDMARK_TAB = "Wordmarks"
UNIFORM_MATERIALS_TAB = "Editable Materials"

#: The tab :class:`~mod_editor.apf_studio.gui.ScorebugStudioPage` gives the one
#: presentation slot that has a proved writer.
DIGITAL_FONT_TAB = "Digital Font"

#: Exact identity of the shared score-digit atlas.
DIGITAL_FONT_NAME = "digital_font"

#: The field scorebug's own team-logo component.  It embeds no texture; it
#: samples one at runtime, which is why it routes to the crest writer rather
#: than claiming an editor of its own.
SCOREBUG_TEAM_LOGO_SCENE = "scorebug_team_logos"


@dataclass(frozen=True, slots=True)
class WorkspaceRoute:
    """One catalog row's proved authoring home.

    ``key`` is opaque to the browser and meaningful only to the destination
    page, which is what keeps this table free of every panel's internals.
    """

    category: ApfCategory
    tab: str
    key: str
    action_label: str
    workspace_label: str
    summary: str

    @property
    def destination(self) -> str:
        """``Logos & Team Art -> Team Logo``, for status lines and tooltips."""

        if not self.tab:
            return self.category.title
        return f"{self.category.title} → {self.tab}"


def _scorebug_route(asset: ApfAsset) -> WorkspaceRoute | None:
    """The two presentation rows a proved writer can actually reach.

    Everything else on the field scorebug -- the SCNE geometry and the eleven
    TXTR descriptors embedded inside those scenes -- has no writer, so it gets
    no route.  Returning ``None`` is how this table says *nothing here can edit
    that*, and the browser then keeps its honest export-only boundary.
    """

    if asset.type_name == "TXTR" and asset.name == DIGITAL_FONT_NAME:
        return WorkspaceRoute(
            category=ApfCategory.SCOREBUG,
            tab=DIGITAL_FONT_TAB,
            key=DIGITAL_FONT_NAME,
            action_label="Edit the score digits…",
            workspace_label="Scorebug & Presentation → Digital Font",
            summary=(
                "This is the shared 128×128 alpha-only score-digit atlas. The "
                "Digital Font editor owns it and accepts any image size or "
                "format, refitting it for you. It is a global atlas: edits may "
                "affect UI outside the field scorebug, and runtime visibility "
                "is not proved."
            ),
        )
    if asset.type_name == "SCNE" and asset.name == SCOREBUG_TEAM_LOGO_SCENE:
        return WorkspaceRoute(
            category=ApfCategory.LOGOS,
            tab=TEAM_LOGO_TAB,
            key="",
            action_label="Open Team Logo…",
            workspace_label="Logos & Team Art → Team Logo",
            summary=(
                "This scorebug component embeds no texture. It samples the team "
                "logo at runtime through two dynamic samplers. Team Logo writes "
                "both candidate reservoirs (the uniform_logo crest package and "
                "the logo cache); which one the scorebug actually reads is not "
                "proved. The component's own geometry stays read-only."
            ),
        )
    return None


def _crest_route(asset: ApfAsset) -> WorkspaceRoute | None:
    if asset.type_name != "TXTR" or asset.name not in CREST_LAYER_NAMES:
        return None
    return WorkspaceRoute(
        category=ApfCategory.LOGOS,
        tab=TEAM_LOGO_TAB,
        key=str(asset.outer_index),
        action_label="Edit in Team Logo…",
        workspace_label="Logos & Team Art → Team Logo",
        summary=(
            "This is a helmet-crest layer inside a uniform_logo package. The "
            "Team Logo editor owns it: one 512×512 RGBA image writes both "
            "logo_l0 and logo_l1 plus the matching frontend/Team Select cache "
            "index. Any image size or format is accepted and fitted for you."
        ),
    )


def _uniform_route(asset: ApfAsset, uniform: UniformAsset) -> WorkspaceRoute:
    if uniform.family == "textlogo":
        return WorkspaceRoute(
            category=ApfCategory.LOGOS,
            tab=WORDMARK_TAB,
            key=str(uniform.asset_index),
            action_label="Edit in Wordmarks…",
            workspace_label="Logos & Team Art → Wordmarks",
            summary=(
                "This is a rectangular selector-slot-6 wordmark. The Wordmarks "
                f"editor owns slot #{uniform.asset_index:03d} and writes it as "
                f"a {uniform.width}×{uniform.height} image with contain, cover, "
                "or stretch fitting."
            ),
        )
    return WorkspaceRoute(
        category=ApfCategory.UNIFORMS,
        tab=UNIFORM_MATERIALS_TAB,
        key=uniform.asset_id,
        action_label="Edit in Uniforms…",
        workspace_label="Uniforms & Equipment → Editable Materials",
        summary=(
            f"This is {uniform.title}, one of the 96 proved uniform material "
            f"slots. The Uniforms workspace writes it as {uniform.width}×"
            f"{uniform.height}; any image size or format is fitted for you."
        ),
    )


def _field_art_route(name: str) -> WorkspaceRoute:
    return WorkspaceRoute(
        category=ApfCategory.FIELD_ART,
        tab="",
        key=name,
        action_label="Edit in Field Art…",
        workspace_label="Field Art → base texture editor",
        summary=(
            f"{name} is one of the offline-proved writable field-art base "
            "textures. The Field Art editor owns it and keeps every sibling "
            "layer, descriptor pad, and packed mip tail byte-identical."
        ),
    )


def _stadium_texture_route(outer_index: int, inner_index: int) -> WorkspaceRoute:
    return WorkspaceRoute(
        category=ApfCategory.STADIUMS,
        tab="",
        key=f"{outer_index}:{inner_index}",
        action_label="Edit in Stadium Studio…",
        workspace_label="Stadium Studio → embedded textures",
        summary=(
            "This package carries the stadium's embedded textures. Stadium "
            "Studio lists them individually and replaces them in place inside "
            "a copied volume."
        ),
    )


def route_for_asset(
    asset: ApfAsset,
    *,
    uniform_assets: Iterable[UniformAsset] = (),
    field_art_targets: Mapping[tuple[int, int], str] | None = None,
    stadium_texture_location: tuple[int, int] | None = None,
) -> WorkspaceRoute | None:
    """The workspace that can actually edit ``asset``, or ``None``.

    ``uniform_assets`` is the catalog's own uniform/wordmark table,
    ``field_art_targets`` maps ``(outer, inner)`` to the writable field-art slot
    name, and ``stadium_texture_location`` is the one package whose embedded
    textures Stadium Studio edits.  Callers pass what they already hold; each
    omitted table simply disables its own rules.
    """

    presentation = _scorebug_route(asset)
    if presentation is not None:
        return presentation

    crest = _crest_route(asset)
    if crest is not None:
        return crest

    location = (asset.outer_index, asset.inner_index)
    for uniform in uniform_assets:
        if (uniform.outer_index, uniform.inner_index) == location:
            return _uniform_route(asset, uniform)

    if field_art_targets:
        name = field_art_targets.get(location)  # type: ignore[arg-type]
        if name is not None:
            return _field_art_route(name)

    if stadium_texture_location is not None and location == stadium_texture_location:
        return _stadium_texture_route(*stadium_texture_location)

    return None


@dataclass(frozen=True, slots=True)
class WorkspaceHandoff:
    """One browser row asking the shell to open its real editor.

    ``image`` carries a file the user already chose or dropped in the browser,
    so a hand-off finishes the action the user started instead of only moving
    them to another page.
    """

    route: WorkspaceRoute
    asset_name: str
    asset_id: str
    image: str = ""
