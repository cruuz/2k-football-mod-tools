"""All Textures must be a workspace, and its edits must reach the disc.

The capability shipped registered and marked Editable with **no page behind
it** -- a sidebar entry that did nothing. Fixing that is two separate things,
and only one of them is visible:

1. A browser to pick a texture in. That is the obvious half.
2. A route into ``Build Modded XISO``. That is the half that matters. A
   browser whose edits are silently dropped at build time would be worse than
   the bare card it replaced, because the user would believe the edit landed.

So these assertions are about the second half. The composed build has to know
the ``p8_texture`` kind, validate it, refuse duplicates, and dispatch it to the
adapter; the catalog has to publish assets the browser can list; and the
category has to mount the real visual page rather than the capability-card
fallback.

Everything here is metadata and source structure. The end-to-end proof -- two
texture edits composed into a real modded XISO, 31,652 bytes changed -- is a
retail-data run recorded in the release notes, not something CI can perform.
"""

from __future__ import annotations

from pathlib import Path
from collections import Counter
import sys
import tempfile
from types import SimpleNamespace
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core.capabilities import CapabilityRegistryLoader  # noqa: E402
from mod_editor.core.nfl2k5_extended_visual_catalog import (  # noqa: E402
    PRODUCTION_EXPECTATIONS, load_nfl2k5_extended_visual_catalog,
)
from mod_editor.core.nfl2k5_p8_texture_writer import (  # noqa: E402
    EXPECTED_TARGETS, build_unified_p8_texture_imports, load_inventory,
)
from mod_editor.core.product_catalog import (  # noqa: E402
    ProductCategory, build_nfl2k5_product_catalog,
)

_PROJECT = _REPO_ROOT / "tools" / "nfl2k5_visual_mod_project.py"
_STUDIO = _REPO_ROOT / "mod_editor" / "gui" / "studio_qt.py"
_INDEX = _REPO_ROOT / "extracted" / "ESPN NFL 2K5 (USA)" / "vc_53450030" / "0"


class InventoryTests(unittest.TestCase):
    def test_every_target_loads(self) -> None:
        targets = load_inventory()
        self.assertEqual(len(targets), EXPECTED_TARGETS)

    def test_targets_carry_the_identity_the_build_binds_against(self) -> None:
        target = load_inventory()["p8:3136:pad_north"]
        self.assertEqual(target.pack_path, "vc_53450030/8")
        self.assertTrue(target.pack_sha256)
        self.assertGreater(target.span_size, 0)
        self.assertEqual((target.width, target.height), (128, 128))

    def test_every_reviewed_texture_group_is_present(self) -> None:
        groups = {target.group for target in load_inventory().values()}
        self.assertEqual(
            groups,
            {
                "End Zone",
                "Goalpost Pads",
                "Field Surface",
                "Equipment",
                "Player Presentation Strips",
                "Team Presentation — Menu / UI",
                "Team Logos — Menus / Presentation",
                "Team Mini Cards — Menus / Presentation",
                "Franchise & Draft Presentation",
            },
        )

    def test_menu_presentation_closure_has_exact_bounded_counts(self) -> None:
        catalog = load_nfl2k5_extended_visual_catalog()
        families = Counter(
            asset.presentation_family
            for asset in catalog.assets_for_kind("p8_texture")
            if asset.presentation_family is not None
        )
        self.assertEqual(
            families,
            {
                "menu_logo_large": 317,
                "menu_logo_small": 317,
                "menu_flipchip": 317,
                "menu_mini_card": 634,
                "franchise_team_logo": 85,
                "draft_pda_logo": 85,
            },
        )
        ids = load_inventory()
        self.assertNotIn("p8:3103:unknown_a", ids)
        self.assertNotIn("p8:3103:unknown_h", ids)

    def test_all_player_strips_are_editable_including_the_cross_pack_one(self) -> None:
        targets = load_inventory()
        strips = [
            target for target in targets.values()
            if target.group == "Player Presentation Strips"
        ]
        self.assertEqual(len(strips), 4_080)
        self.assertTrue(all(target.replacement_supported for target in strips))
        cross_pack = targets["p8:581:p005"]
        self.assertEqual(len(cross_pack.physical_spans), 2)
        self.assertEqual(
            [piece.pack_name for piece in cross_pack.physical_spans], ["0", "1"]
        )
        self.assertEqual(
            [piece.size for piece in cross_pack.physical_spans], [53_888, 21_008]
        )

    def test_every_uniform_has_four_distinct_presentation_textures(self) -> None:
        targets = load_inventory().values()
        presentation = [
            target for target in targets
            if target.group == "Team Presentation — Menu / UI"
        ]
        self.assertEqual(len(presentation), 634 * 4)
        self.assertEqual(
            {target.texture for target in presentation},
            {"logo", "chiclet", "splayer", "flipchip"},
        )
        self.assertEqual(
            (load_inventory()["p8:3783:logo"].width,
             load_inventory()["p8:3783:logo"].height),
            (128, 128),
        )


class CatalogTests(unittest.TestCase):
    def test_the_browser_has_assets_to_list(self) -> None:
        catalog = load_nfl2k5_extended_visual_catalog()
        assets = catalog.assets_for_kind("p8_texture")
        self.assertEqual(len(assets), PRODUCTION_EXPECTATIONS.p8_texture_count)
        self.assertEqual(len(assets), EXPECTED_TARGETS)

    def test_an_asset_produces_the_edit_the_build_accepts(self) -> None:
        catalog = load_nfl2k5_extended_visual_catalog()
        asset = catalog.assets_for_kind("p8_texture")[0]
        edit = asset.provider_edit("/tmp/example.png")
        self.assertEqual(set(edit), {"kind", "asset_id", "png"})
        self.assertEqual(edit["kind"], "p8_texture")
        self.assertTrue(str(edit["asset_id"]).startswith("p8:"))

    def test_p011_and_the_cross_pack_strip_are_editable(self) -> None:
        catalog = load_nfl2k5_extended_visual_catalog()
        p011 = catalog.get_asset("p8:684:p011")
        self.assertTrue(p011.editable)
        self.assertEqual(p011.dimensions, (1056, 64))
        self.assertEqual(p011.provider_edit("/tmp/p011.png")["kind"], "p8_texture")
        cross_pack = catalog.get_asset("p8:581:p005")
        self.assertTrue(cross_pack.editable)
        self.assertEqual(
            cross_pack.provider_edit("/tmp/p005.png")["kind"], "p8_texture"
        )

    def test_every_asset_declares_the_capability_it_belongs_to(self) -> None:
        catalog = load_nfl2k5_extended_visual_catalog()
        owners = {
            asset.capability_id for asset in catalog.assets_for_kind("p8_texture")
        }
        self.assertEqual(owners, {"nfl2k5.textures.all_p8"})

    def test_eagles_presentation_logo_is_named_and_searchable(self) -> None:
        catalog = load_nfl2k5_extended_visual_catalog()
        asset = catalog.get_asset("p8:3783:logo")
        self.assertIn("Philadelphia Eagles", asset.label)
        self.assertIn("21H0", asset.label)
        self.assertIn("menu logo", asset.search_terms)
        self.assertIn("PHI", asset.search_terms)
        self.assertNotEqual(asset.asset_id, "nfl2k5.uniform.21h0.helmet.helmet00")

    def test_separate_eagles_menu_and_franchise_logos_are_typed(self) -> None:
        catalog = load_nfl2k5_extended_visual_catalog()
        menu = catalog.get_asset("p8:3102:logo_21_0")
        self.assertEqual(menu.presentation_family, "menu_logo_large")
        self.assertEqual(menu.asset_code, "21")
        self.assertEqual(menu.style, 0)
        self.assertEqual(menu.set_selectors, ("21H0", "21A0"))
        self.assertEqual(menu.outer_name, "logos.cdf")
        self.assertEqual(menu.dimensions, (256, 256))
        self.assertIn("SportsCenter", menu.consumer_scope)
        self.assertIn("Philadelphia Eagles", menu.label)
        self.assertIn("frontend logo", menu.search_terms)

        franchise = catalog.get_asset("p8:45:21_teamlogo_00_h0")
        self.assertEqual(franchise.presentation_family, "franchise_team_logo")
        self.assertEqual(franchise.outer_name, "fr21.iff")
        self.assertEqual(
            franchise.consumer_scope, "FRANCHISE2 coach_desk teamlogo"
        )
        self.assertIn("coach desk", franchise.search_terms)
        self.assertNotIn("midfield", franchise.label.casefold())
        self.assertIn("not midfield", franchise.authoring_note.casefold())

        draft = catalog.get_asset("p8:45:pdalogo")
        self.assertEqual(draft.presentation_family, "draft_pda_logo")
        self.assertEqual(draft.dimensions, (64, 64))
        self.assertIn("pda logo", draft.search_terms)


@unittest.skipUnless(_INDEX.is_file(), "retail extracted index is not present")
class CrossPackProviderTests(unittest.TestCase):
    def test_raw_eagles_menu_logo_previews_and_exports(self) -> None:
        from mod_editor.core.nfl2k5_extended_visual_io import (
            Nfl2k5ExtendedVisualIO,
        )
        from nfl_tset_png_import import decode_rgba_png

        asset = load_nfl2k5_extended_visual_catalog().get_asset(
            "p8:3102:logo_21_0"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = SimpleNamespace(
                originals=root / "originals",
                pack0=_INDEX,
                source=SimpleNamespace(sha256="retail-fixture"),
            )
            cache.originals.mkdir()
            io = Nfl2k5ExtendedVisualIO(cache)
            original = io.ensure_original(asset)
            width, height, rgba = decode_rgba_png(
                original.read_bytes(), asset.dimensions
            )
            exported = io.export_original(asset, root / "eagles-menu-logo.png")
            self.assertEqual(exported.read_bytes(), original.read_bytes())
        self.assertEqual((width, height), (256, 256))
        self.assertEqual(len(rgba), 256 * 256 * 4)

    def test_raw_menu_logo_uses_fixed_span_without_vc_lz(self) -> None:
        from nfl_all_texture_xiso_workflow import resolve_target
        from nfl_outer import parse_archive
        from nfl_txtr import HEADER, write_png

        width = height = 64
        rgba = bytes(
            component
            for y in range(height)
            for x in range(width)
            for component in (
                224 if (x // 8 + y // 8) % 2 else 16,
                48 if x < width // 2 else 192,
                120,
                255,
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "eagles_flipchip.png"
            write_png(png, width, height, rgba)
            edits = build_unified_p8_texture_imports(
                _INDEX, "p8:3096:21_flipchip_00_h0", png
            )
        self.assertEqual(len(edits), 1)
        replacement, _exports, record, _selector, _proof = edits[0]
        source = resolve_target(
            parse_archive(_INDEX), 3_096, "21_flipchip_00_h0"
        )
        self.assertEqual(len(replacement), 5_280)
        self.assertEqual(
            replacement[:HEADER.size + source.system_bytes],
            source.template_span[:HEADER.size + source.system_bytes],
        )
        self.assertTrue(record["raw_uncompressed_fixed_span"])
        self.assertTrue(record["vc_lz_not_applicable"])
        self.assertTrue(record["wrapper_identical"])
        self.assertTrue(record["system_bytes_identical"])

    def test_p005_stages_two_complete_composed_build_edits(self) -> None:
        from nfl_txtr import write_png

        width, height = 1_344, 64
        rgba = bytes(
            component
            for y in range(height)
            for x in range(width)
            for component in (
                48 if (x // 64 + y // 8) % 2 else 208,
                112,
                72,
                255,
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "p005.png"
            write_png(png, width, height, rgba)
            edits = build_unified_p8_texture_imports(
                _INDEX, "p8:581:p005", png
            )
        self.assertEqual([len(edit[0]) for edit in edits], [53_888, 21_008])
        self.assertEqual(
            [edit[4]["xiso_pack_path"] for edit in edits],
            ["vc_53450030/0", "vc_53450030/1"],
        )
        self.assertEqual(
            {edit[4]["logical_replacement_sha256"] for edit in edits},
            {edits[0][4]["logical_replacement_sha256"]},
        )
        self.assertEqual(len(b"".join(edit[0] for edit in edits)), 74_896)


class ComposedBuildTests(unittest.TestCase):
    """The half that matters: the edit must survive Build Modded XISO."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = _PROJECT.read_text(encoding="utf-8")

    def test_the_build_declares_the_kind(self) -> None:
        self.assertIn('P8_TEXTURE_KIND = "p8_texture"', self.source)
        self.assertIn(
            'P8_TEXTURE_FIELDS = {"kind", "asset_id", "png"}', self.source
        )

    def test_the_build_validates_the_edit_shape(self) -> None:
        self.assertIn("elif kind == P8_TEXTURE_KIND:", self.source)
        self.assertIn("has invalid p8_texture fields/types", self.source)

    def test_the_build_refuses_a_repeated_target(self) -> None:
        self.assertIn('"project repeats one p8_texture target"', self.source)

    def test_the_build_dispatches_to_the_adapter(self) -> None:
        self.assertIn("build_unified_p8_texture_import", self.source)
        self.assertIn("p8_texture_adapter", self.source)

    def test_the_adapter_is_registered_before_execution(self) -> None:
        """@dataclass resolves through sys.modules; an unregistered module
        raises AttributeError on import."""
        loader = self.source[self.source.index("def _load_p8_texture_adapter"):]
        loader = loader[:loader.index("def _load_stadium_texture_adapter")]
        self.assertLess(
            loader.index("sys.modules[spec.name] = module"),
            loader.index("spec.loader.exec_module(module)"),
        )


class WorkspaceMountTests(unittest.TestCase):
    def test_the_category_mounts_the_real_browser(self) -> None:
        source = _STUDIO.read_text(encoding="utf-8")
        self.assertIn("ProductCategory.TEXTURES: frozenset({", source)
        self.assertIn('"p8_texture",', source)
        mount = source.index("elif category == ProductCategory.TEXTURES:")
        window = source[mount:mount + 700]
        self.assertIn("_build_visual_page(section, visual_kinds)", window)

    def test_the_capability_is_exposed_and_enabled(self) -> None:
        catalog = build_nfl2k5_product_catalog(CapabilityRegistryLoader().load())
        binding = catalog.binding("nfl2k5.textures.all_p8")
        gui = binding.capability.raw["gui"]
        self.assertTrue(gui["expose"])
        self.assertTrue(gui["default_enabled"])

    def test_the_category_holds_the_capability(self) -> None:
        catalog = build_nfl2k5_product_catalog(CapabilityRegistryLoader().load())
        section = catalog.section(ProductCategory.TEXTURES)
        self.assertIn(
            "nfl2k5.textures.all_p8",
            {binding.capability_id for binding in section.capabilities},
        )


if __name__ == "__main__":
    unittest.main()
