"""A staged PNG edit must resolve through the catalog that minted its ID.

Reported against Beta 39: after swapping textures in the Team Kit panel, Build
Modded XISO refused with::

    Unknown uniform asset ID: tset:3660:4:0:socks00
    Nothing was changed in your source XISO.

``tset:3660:4:0:socks00`` is "Socks 00 -- Cincinnati Bengals Home", a 64x64
``uniform_equipment_texture`` owned by the **extended** visual catalog. The
session resolved every staged edit through the **uniform** catalog, which has
never heard of that ID.

Staging worked because ``replace()`` is handed an already-resolved asset
*object* by the panel. Every later step re-resolved the ID *string*, so a user
could fill a session with equipment edits and then find that Build, Save
Project, Load Project, batch import, Undo's restore and Revert All all refused
them. ``Nfl2k5ProductVisualCatalog`` had existed for this the whole time -- its
docstring says a reversible session can use it "for either catalog without
knowing where the asset originated" -- and nothing ever handed it to a session.

The routing predates the Team Kit equipment surface, so it only became
reachable once a user touched socks rather than jerseys.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_extended_visual_catalog import (
    Nfl2k5ProductVisualCatalog,
    load_nfl2k5_extended_visual_catalog,
)
from mod_editor.core.nfl2k5_uniform_catalog import (
    UniformCatalogError,
    load_nfl2k5_uniform_catalog,
)
from mod_editor.studio.session import StudioSession


#: The exact asset from the report.
REPORTED = "tset:3660:4:0:socks00"

#: Every namespace a visual browser can mint. Each one used to be a build
#: failure waiting for someone to edit that kind of texture.
NAMESPACES = (
    "tset:",
    "p8:",
    "nfl2k5.portrait.",
    "nfl2k5.live-face.",
    "nfl2k5.create-field.",
    "nfl2k5.scorebug.",
    "nfl2k5.uniform.",
)


class _StandInCatalog:
    """A session given a stand-in catalog must keep using the stand-in."""

    def __init__(self) -> None:
        self.asset = SimpleNamespace(asset_id="stand-in:1", label="Stand-in")
        self.asked: list[str] = []

    def get_asset(self, asset_id: str):
        self.asked.append(asset_id)
        if asset_id != self.asset.asset_id:
            raise ValidationError(f"Unknown stand-in asset: {asset_id}")
        return self.asset


class _AssetIO:
    """Stands in for the private source-cache IO; never opens a game."""

    def __init__(self, _cache: object) -> None:
        pass

    @staticmethod
    def ensure_original(_asset: object) -> Path:
        return _AssetIO.original  # type: ignore[attr-defined]

    @staticmethod
    def validate_replacement(_asset: object, path: Path) -> tuple[bytes, bytes]:
        payload = path.read_bytes()
        if payload == b"ORIGINAL-CONTAINER":
            return payload, b"ORIGINAL-PIXELS"
        if payload == b"USER-CONTAINER":
            return payload, b"USER-PIXELS"
        raise ValidationError("bad synthetic PNG")


class _SessionHarness(unittest.TestCase):
    """One session over the real catalogs, with the game IO stubbed out."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="visual-routing-")
        self.root = Path(self.temporary.name)
        cache_root = self.root / "private-source-cache"
        cache_root.mkdir()
        self.original = cache_root / "original.png"
        self.original.write_bytes(b"ORIGINAL-CONTAINER")
        _AssetIO.original = self.original  # type: ignore[attr-defined]
        self.cache = SimpleNamespace(
            source=SimpleNamespace(sha256="a" * 64),
            root=cache_root,
            pack0=cache_root / "pack0.bin",
            inventory=cache_root / "inventory.json",
        )
        self.patcher = mock.patch(
            "mod_editor.studio.session.Nfl2k5ProductVisualIO", _AssetIO
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.addCleanup(self.temporary.cleanup)
        self.uniform = load_nfl2k5_uniform_catalog()

    def _session(self, catalog=None) -> StudioSession:
        return StudioSession(
            self.cache,
            self.uniform if catalog is None else catalog,
            root=self.root / "sessions",
            session_id=f"s{len(list((self.root / 'sessions').glob('*')))if (self.root / 'sessions').exists() else 0}",
        )

    def _user_png(self, name: str) -> Path:
        path = self.root / name
        path.write_bytes(b"USER-CONTAINER")
        return path


class ReportedFailureTests(_SessionHarness):
    def test_the_uniform_catalog_really_does_not_own_that_id(self) -> None:
        """The premise of the bug, so the fix cannot be tested against nothing."""

        with self.assertRaises(UniformCatalogError) as caught:
            self.uniform.get_asset(REPORTED)
        self.assertIn("Unknown uniform asset ID", str(caught.exception))

    def test_the_session_resolves_the_reported_socks_asset(self) -> None:
        asset = self._session()._visual_asset(REPORTED)
        self.assertEqual(asset.asset_id, REPORTED)
        self.assertEqual(asset.kind, "uniform_equipment_texture")
        self.assertEqual((asset.width, asset.height), (64, 64))
        self.assertIn("Socks", asset.label)

    def test_every_visual_namespace_resolves(self) -> None:
        session = self._session()
        aggregate = session._derive_visual_catalog()
        for prefix in NAMESPACES:
            with self.subTest(namespace=prefix):
                sample = next(
                    (a.asset_id for a in aggregate.assets if a.asset_id.startswith(prefix)),
                    None,
                )
                self.assertIsNotNone(sample, f"no asset in namespace {prefix}")
                self.assertEqual(session._visual_asset(sample).asset_id, sample)


class UniformEditsAreUnchangedTests(_SessionHarness):
    """Widening the lookup must not change what a jersey edit resolves to."""

    def test_a_uniform_id_resolves_to_the_identical_object(self) -> None:
        session = self._session()
        for asset in self.uniform.assets[:25]:
            with self.subTest(asset_id=asset.asset_id):
                self.assertIs(
                    session._visual_asset(asset.asset_id),
                    self.uniform.get_asset(asset.asset_id),
                )

    def test_the_aggregate_is_built_from_this_session_s_uniform_catalog(self) -> None:
        """Not from a module-level default, which could be a different report."""

        session = self._session()
        aggregate = session._derive_visual_catalog()
        self.assertIsInstance(aggregate, Nfl2k5ProductVisualCatalog)
        self.assertIs(aggregate.uniforms, self.uniform)

    def test_the_set_hierarchy_still_comes_from_the_uniform_catalog(self) -> None:
        self.assertIs(self._session().catalog, self.uniform)


class StandInCatalogTests(_SessionHarness):
    """Sessions built with a test double must not be dragged onto real data."""

    def test_a_stand_in_catalog_is_used_as_is(self) -> None:
        stand_in = _StandInCatalog()
        session = self._session(stand_in)
        self.assertIs(session._visual_asset("stand-in:1"), stand_in.asset)
        self.assertEqual(stand_in.asked, ["stand-in:1"])
        self.assertIsNone(session.visual_catalog)

    def test_an_attached_catalog_wins_over_deriving_one(self) -> None:
        session = self._session()
        attached = Nfl2k5ProductVisualCatalog(
            self.uniform, load_nfl2k5_extended_visual_catalog()
        )
        session.attach_visual_catalog(attached)
        self.assertIs(session.visual_catalog, attached)
        self.assertEqual(session._visual_asset(REPORTED).asset_id, REPORTED)


class BuildPathTests(_SessionHarness):
    """The regression test that was missing: stage equipment, then compile."""

    def test_an_equipment_edit_reaches_the_canonical_project(self) -> None:
        session = self._session()
        asset = session._visual_asset(REPORTED)
        session.replace(asset, self._user_png("socks.png"))
        self.assertEqual(session.modified_count, 1)

        document = session.canonical_document()
        edits = [
            edit for edit in document["edits"]
            if edit.get("asset_id") == REPORTED
        ]
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]["kind"], "uniform_equipment_texture")

    def test_the_project_router_accepts_an_equipment_edit(self) -> None:
        """Save Project and Load Project both resolve through this."""

        session = self._session()
        self.assertEqual(
            session._project_png_asset(REPORTED).asset_id, REPORTED
        )

    def test_reverting_an_equipment_edit_works(self) -> None:
        session = self._session()
        asset = session._visual_asset(REPORTED)
        session.replace(asset, self._user_png("socks.png"))
        self.assertTrue(session.revert(asset))
        self.assertEqual(session.modified_count, 0)

    def test_a_batch_import_resolves_equipment_ids(self) -> None:
        """Import Team Kit re-resolves each ID, so it hit the same wall."""

        session = self._session()
        asset = session._visual_asset(REPORTED)
        session.replace_batch(
            ((asset, self._user_png("socks.png")),),
            label="Import Team Kit",
        )
        self.assertEqual(session.modified_count, 1)
        self.assertIn(REPORTED, session.modified_asset_ids)


class FacadeWiringTests(unittest.TestCase):
    def test_the_facade_hands_its_aggregate_to_a_new_session(self) -> None:
        from mod_editor.studio.facade import Nfl2k5StudioFacade

        attached: list[object] = []
        session = SimpleNamespace(
            attach_visual_catalog=lambda catalog: attached.append(catalog)
        )
        facade = SimpleNamespace(visual_catalog=object())
        Nfl2k5StudioFacade._attach_visual_catalog(facade, session)  # type: ignore[arg-type]
        self.assertEqual(attached, [facade.visual_catalog])

    def test_a_session_without_the_hook_is_left_alone(self) -> None:
        from mod_editor.studio.facade import Nfl2k5StudioFacade

        facade = SimpleNamespace(visual_catalog=object())
        Nfl2k5StudioFacade._attach_visual_catalog(facade, object())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
