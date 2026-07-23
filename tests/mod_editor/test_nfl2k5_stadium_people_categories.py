"""Tests for the stadium people/sideline texture classifier.

These exercise the pure, source-cache-free classification helpers that power
the "Stadium People & Sideline" grouping (fans, cheerleaders, coaches,
officials, chain crew, camera/media, ushers, sideline props).  The vocabulary
mirrors the decoded SCNE name census.
"""

import unittest

from mod_editor.core.nfl2k5_stadium_studio import (
    STADIUM_PEOPLE_CATEGORIES,
    ValidationError,
    stadium_people_categories_for_names,
    stadium_people_category,
    stadium_people_category_label,
)


class StadiumPeopleCategoryTests(unittest.TestCase):
    def test_known_people_names_map_to_their_category(self) -> None:
        cases = {
            "cheerleader1": "cheerleaders",
            "cheerleaderhaira": "cheerleaders",
            "cheerleadera_shadow": "cheerleaders",
            "crowda": "crowd",
            "crowdb": "crowd",
            "crowds29": "crowd",
            "crowdbald": "crowd",
            "crowdsleep": "crowd",
            "crowdticket": "crowd",
            "coach": "coaches",
            "coach_desk": "coaches",
            "cameraman01": "camera_crew",
            "cameraman01_shadow": "camera_crew",
            "chaingang01": "chain_crew",
            "chain_gang_0": "chain_crew",
            "sideline_player": "sideline",
            "sideline_gatorcooler": "sideline",
            "referee01": "officials",
            "officials_stripes": "officials",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(stadium_people_category(name), expected)

    def test_case_insensitive(self) -> None:
        self.assertEqual(stadium_people_category("CHEERLEADER1"), "cheerleaders")
        self.assertEqual(stadium_people_category("CrowdA"), "crowd")

    def test_specific_role_wins_over_broad_crowd_bucket(self) -> None:
        # ``crowdusher`` contains both ``crowd`` and ``usher``; ushers is ordered
        # before crowd so the more specific role wins.
        self.assertEqual(stadium_people_category("crowdusher"), "ushers")

    def test_unrelated_stadium_names_do_not_match(self) -> None:
        for name in (
            "field_grass", "scoreboard", "goalpost", "sky_dome",
            "jersey00", "helmet00", "endzone_logo", "yard_line",
        ):
            with self.subTest(name=name):
                self.assertIsNone(stadium_people_category(name))

    def test_bare_ref_substring_does_not_match_officials(self) -> None:
        # Guard against ``ref`` matching words like ``reference``.
        for name in ("reference_manual", "preferred_angle", "refresh_rate"):
            with self.subTest(name=name):
                self.assertIsNone(stadium_people_category(name))

    def test_non_string_returns_none(self) -> None:
        self.assertIsNone(stadium_people_category(None))  # type: ignore[arg-type]
        self.assertIsNone(stadium_people_category(123))  # type: ignore[arg-type]

    def test_categories_for_names_collects_and_sorts(self) -> None:
        self.assertEqual(
            stadium_people_categories_for_names(
                "crowda", "cheerleader1", "field_grass", "coach"
            ),
            ("cheerleaders", "coaches", "crowd"),
        )
        self.assertEqual(stadium_people_categories_for_names("field_grass"), ())

    def test_every_category_has_a_label(self) -> None:
        for category_id, _label, _tokens in STADIUM_PEOPLE_CATEGORIES:
            self.assertTrue(stadium_people_category_label(category_id))

    def test_unknown_label_raises(self) -> None:
        with self.assertRaises(ValidationError):
            stadium_people_category_label("not_a_category")

    def test_category_table_has_no_duplicate_ids(self) -> None:
        ids = [category_id for category_id, _label, _tokens in STADIUM_PEOPLE_CATEGORIES]
        self.assertEqual(len(ids), len(set(ids)))




from pathlib import Path as _Path

from mod_editor.core.nfl2k5_stadium_studio import (
    StadiumMaterial,
    StadiumSurfaceOwner,
    StadiumTexture,
    classify_stadium_people_textures,
)


def _tex(tid, mapped=(), scene="stadium"):
    return StadiumTexture(
        texture_id=tid, scene_id=scene, texture_index=0, width=64, height=64,
        format_name="P8", rgba_sha256="a" * 64, png_sha256="b" * 64,
        png_path=_Path("/tmp/x.png"), mapped_material_names=mapped,
        mapped_material_count=len(mapped), access_status="base_level_supported",
    )


def _mat(name, tid, node_names=()):
    owners = tuple(
        StadiumSurfaceOwner(i, n, 0, 0, None, None)
        for i, n in enumerate(node_names)
    )
    return StadiumMaterial(0, name, "mapped", tid, owners)


class ClassifyStadiumPeopleTexturesTests(unittest.TestCase):
    def test_matches_by_mapped_material_name(self) -> None:
        textures = (
            _tex("t1", mapped=("cheerleader1",)),
            _tex("t2", mapped=("field_grass",)),
        )
        self.assertEqual(
            classify_stadium_people_textures("stadium", textures, ()),
            {"t1": ("cheerleaders",)},
        )

    def test_matches_by_scene_name(self) -> None:
        self.assertEqual(
            classify_stadium_people_textures(
                "chain_gang_0", (_tex("t1", mapped=("generic",)),), ()
            ),
            {"t1": ("chain_crew",)},
        )

    def test_matches_by_owning_material_and_node_names(self) -> None:
        textures = (_tex("t1", mapped=("UNIFORM_DOUBLESIDED",)),)
        materials = (_mat("crowda", "t1", node_names=("crowdn",)),)
        self.assertEqual(
            classify_stadium_people_textures("stadium", textures, materials),
            {"t1": ("crowd",)},
        )

    def test_unrelated_texture_excluded(self) -> None:
        self.assertEqual(
            classify_stadium_people_textures(
                "stadium", (_tex("t1", mapped=("field_grass",)),), ()
            ),
            {},
        )

    def test_specific_role_wins_in_mapped_name(self) -> None:
        self.assertEqual(
            classify_stadium_people_textures(
                "stadium", (_tex("t1", mapped=("crowdusher_sign",)),), ()
            ),
            {"t1": ("ushers",)},
        )


if __name__ == "__main__":
    unittest.main()
