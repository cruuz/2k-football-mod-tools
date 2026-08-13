"""Pin the current APF public claims to the implemented proof boundary."""

from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "mod_editor/capabilities/registry.v1.json"
LOGO_OWNERSHIP_DOC = ROOT / "docs/mod_editor/apf2k8_logo_surface_ownership.md"
PUBLIC_DOCS = (
    ROOT / "README.md",
    ROOT / "APF2K8-README.md",
    ROOT / "docs/mod_editor/APF2K8_STATUS.md",
    ROOT / "docs/mod_editor/apf2k8_mod_studio_getting_started.md",
    ROOT / "docs/mod_editor/apf2k8_mod_studio_changelog.md",
)


class ApfPublicClaimsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        document = json.loads(REGISTRY.read_text(encoding="utf-8"))
        cls.capabilities = {
            row["id"]: row for row in document["capabilities"]
        }
        cls.docs = " ".join(
            " ".join(path.read_text(encoding="utf-8").split())
            for path in PUBLIC_DOCS
        )

    def test_team_crest_registry_replaces_the_stale_scale_patch_contract(self) -> None:
        package = self.capabilities["apf2k8.logos_cards.team_logo"]
        cache = self.capabilities["apf2k8.logos_cards.team_logo_cache"]
        package_claims = " ".join(
            [package["summary"], package["gui"]["reason"]]
            + package["input_constraints"]
        )
        cache_claims = " ".join(
            [cache["summary"], cache["gui"]["reason"]]
            + cache["input_constraints"]
        )
        self.assertIn("all 118", package_claims)
        self.assertIn("logo_l0", package_claims)
        self.assertIn("logo_l1", package_claims)
        self.assertIn("regenerated", package_claims)
        self.assertIn("independently", cache_claims)
        self.assertNotIn("mip tail is byte-preserved", package_claims)
        self.assertNotIn("mip tail is byte-preserved", cache_claims)
        self.assertEqual(package["runtime"]["status"], "partial")
        for marker in (
            "selector-slot-5",
            "selector-slot-6",
            "frontend/Team Select",
            "uniform_textlogo",
            "changed-logo runtime consumption",
        ):
            self.assertIn(marker.casefold(), package_claims.casefold())
        self.assertIn("statically mapped", cache_claims.casefold())
        self.assertIn("runtime consumption", cache["runtime"]["scope"].casefold())
        for marker in (
            "front_crown_to_rear_v1",
            "stock high/low helmet-shell UV atlas",
            "fixed-coordinate bilateral shell atlas",
            "all 118",
            "physical side-logo placement",
            "zero-triangle degenerates",
            "Place on helmet",
            "direct X/Y drag",
            "independent Width/Height",
            "Rotation",
            "Reset",
            "off-canvas",
            "creates no Xenia patch",
            "does not edit default.xex",
        ):
            self.assertIn(marker, package_claims)
        for marker in (
            "v24",
            "10-view high/low static asset-space Eagles visual gate",
            "no xenia, wine, emulator, controller, or fifo",
            "runtime consumption",
            "gameplay visibility",
            "Xbox 360 hardware",
        ):
            self.assertIn(marker.casefold(), package["runtime"]["scope"].casefold())
            self.assertIn(marker.casefold(), cache["runtime"]["scope"].casefold())
        stale = " ".join(
            [package_claims, cache_claims, package["runtime"]["scope"],
             cache["runtime"]["scope"]]
        )
        for marker in ("1.01x", "2.00x", "Xenia Canary-only", "unproved and blocked"):
            self.assertNotIn(marker, stale)

        appearance = self.capabilities[
            "apf2k8.colors.uniform_selector_appearance_custom_team"
        ]
        self.assertEqual(appearance["runtime"]["status"], "partial")
        for marker in (
            "all 118",
            "171/213",
            "1310",
            "1126",
            "source",
            "10-view high/low static asset-space Eagles visual gate",
        ):
            self.assertIn(marker, appearance["runtime"]["scope"])
        self.assertIn("runtime consumption", appearance["runtime"]["scope"])

    def test_logo_ownership_doc_discloses_ui_linkage_and_runtime_boundary(self) -> None:
        text = " ".join(
            LOGO_OWNERSHIP_DOC.read_text(encoding="utf-8").split()
        ).casefold()
        for marker in (
            "selector slot 5",
            "uniform_logo_nn.iff",
            "n_logo_l0",
            "frontend/team select cache pair",
            "selector slot 6",
            "uniform_textlogo_00..205.iff",
            "never squeezes",
            "changed-logo runtime consumption",
            "remain unproved",
        ):
            self.assertIn(marker, text)
        self.assertNotIn("team select runtime-proved", text)

    def test_playbook_registry_exposes_only_exact_stock_route_reuse(self) -> None:
        capability = self.capabilities["apf2k8.scripts.director_playbook"]
        claims = " ".join(
            [capability["summary"], capability["gui"]["reason"]]
            + capability["input_constraints"]
        )
        self.assertEqual(capability["classification"], "offline-writer-proved")
        self.assertEqual(
            capability["backend"]["module"],
            "mod_editor/core/apf2k8_playbook_route_writer.py",
        )
        for marker in (
            "586 plays",
            "11 slots",
            "descriptor",
            "existing",
            "logical selectors",
            "formation/play membership",
            "Freehand",
        ):
            self.assertIn(marker, claims)
        self.assertIn("STFS", claims)
        self.assertIn("raw handoff", claims)

    def test_roster_audit_and_model_export_claims_are_exact(self) -> None:
        roster = self.capabilities["apf2k8.players.roster"]
        roster_claims = roster["selectors"]["notes"]
        for marker in (
            "1,344",
            "1,312 equivalent",
            "Mike Haynes versus Mark Smith",
            "31 randomized Atoms",
            "zero unexplained",
        ):
            self.assertIn(marker, roster_claims)

        model = self.capabilities["apf2k8.models.scne_gltf"]
        model_claims = " ".join(
            [model["summary"], model["gui"]["reason"]]
            + model["input_constraints"]
        )
        for marker in (
            "outer 1310 / inner 128",
            "33 meshes",
            "outer 1310 / inner 273",
            "1 mesh",
            "helmet/head attachment",
            "POSITION-only",
            "expanded triangle",
            "SpeedFlex/F7",
        ):
            self.assertIn(marker, model_claims)
        self.assertEqual(model["classification"], "offline-writer-proved")
        self.assertEqual(model["backend"]["operation"], "write")
        self.assertEqual(model["runtime"]["status"], "not-tested")

    def test_every_public_document_names_the_new_boundaries(self) -> None:
        for marker in (
            "all 118",
            "Mike Haynes",
            "Mark Smith",
            "31 randomized Atoms",
            "36 offense",
            "33 defense",
            "signed CON",
            "Model Export",
            "front_crown_to_rear_v1",
            "shell atlas",
            "121 outer entries",
            "all 117",
            "fixed semantic canvas",
            "zero-triangle",
            "weighted 4-bit",
            "six-view",
            "10-view",
            "no Xenia, Wine, emulator, controller, or FIFO",
            "Place on helmet",
            "FRONT / CROWN → REAR",
            "nearest-neighbour",
            "off-canvas",
            "normalized original import",
            "last transform",
        ):
            self.assertIn(marker.casefold(), self.docs.casefold())
        for path in PUBLIC_DOCS:
            text = " ".join(path.read_text(encoding="utf-8").split())
            for marker in (
                "front_crown_to_rear_v1",
                "no Xenia patch",
                "gameplay visibility",
                "Xbox 360 hardware",
            ):
                self.assertIn(marker.casefold(), text.casefold(), path.name)
        for path in PUBLIC_DOCS[1:]:
            self.assertIn("0.1.0-alpha.71", path.read_text(encoding="utf-8"))
        self.assertIn("not Mike Smith", self.docs)
        self.assertNotIn("Xenia Mike Smith", self.docs)
        self.assertNotIn("1.01×", self.docs)
        self.assertNotIn("2.00×", self.docs)
        self.assertNotIn("Xenia-only", self.docs)
        self.assertNotIn("65–75%", self.docs)
        for stale in (
            "v18",
            "v19 tuning",
            "35–40%",
            "20–25%",
            "stopped mid-shell",
            "512×226",
        ):
            self.assertNotIn(stale.casefold(), self.docs.casefold())


if __name__ == "__main__":
    unittest.main()
