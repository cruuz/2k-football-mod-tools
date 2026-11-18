"""Beta 81's installer, portable project, source recovery and disc publication."""
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt5.QtWidgets import QApplication, QFileDialog

from mod_editor.core import image_use, mod_build, modpack, modpack_files, modpack_sources
from mod_editor.core import nfl2k5_project_check as doctor, xdvdfs_compact as discs
from mod_editor.gui.build_panel_qt import BuildPanel
from mod_editor.gui.share_panel_qt import SharePanel
from tests.mod_editor.test_modpack_files import image, contents


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(app):
    panel = SharePanel()
    panel._notify = lambda *_: None
    panel._start = lambda operation, done, failed: done(operation(lambda *_: None))
    yield panel
    panel.deleteLater()


def test_new_build_quick_export_then_novice_installs_on_different_layout(panel, tmp_path):
    original = {"default.xbe": b"XBEH" + bytes(5000), "stadium": b"old turf"}
    edited = dict(original, stadium=b"new turf")
    base = image(tmp_path / "base.iso", original)
    padded = image(tmp_path / "padded.iso", edited, order=list(reversed(edited)))
    built = tmp_path / "Beta.xiso.iso"
    discs.compact_copy(padded, built)
    panel.prefill_from_build(dict(source=base, target=built, plan={"name": "My league", "author": "R", "console_memory": 64}))
    art = tmp_path / "league.png"
    art.write_bytes(b"original art")
    panel.set_assets([art])
    panel.version_field.setText("2.0")
    panel.start_export()
    info = panel.last_export
    assert (info["format"], info["author"], info["version"], info["runs"]) == (3, "R", "2.0", 1)
    assert info["assets"][0]["path"].endswith("/league.png")
    pack = Path(info["pack"])
    alternate = image(tmp_path / "reader.iso", original, order=list(reversed(original)))
    target = tmp_path / "game.iso"
    with patch.object(QFileDialog, "getOpenFileName", side_effect=[(str(alternate), ""), (str(pack), "")]), \
         patch.object(QFileDialog, "getSaveFileName", return_value=(str(target), "")):
        panel.install_softdrink()
    assert contents(target) == contents(built)
    assert panel.last_apply["console_memory"] == 64
    assert "64 MB" in panel.apply_status.text() and "128 MiB" not in panel.apply_status.text()
    assert contents(base)["stadium"] == b"old turf"


def test_manual_install_paths_invalidate_checks_and_old_worker(panel, tmp_path):
    base = tmp_path / "base.iso"
    base.write_bytes(b"a" * 4096)
    edited = tmp_path / "changed.iso"
    edited.write_bytes(b"b" + b"a" * 4095)
    first, second = [tmp_path / (name + ".2k5patch") for name in ("one", "two")]
    for path in (first, second):
        modpack.export(base, edited, path, {"name": path.stem}, recipe=False)
    panel.load_pack(first)
    panel.source_field.setText(str(base))
    panel.target_field.setText(str(tmp_path / "out.iso"))
    panel.start_check()
    assert panel.apply_button.isEnabled()
    panel.source_field.setText(str(edited))
    assert panel.last_check is None and not panel.apply_button.isEnabled()
    callbacks = []
    panel._start = lambda operation, done, failed: callbacks.append(done)
    panel.start_check()
    panel.pack_field.setText(str(second))
    assert panel._pack is None
    panel.pack_field.editingFinished.emit()
    assert panel._pack.path == second
    callbacks[0]({"state": "ready", "explanation": "previous source"})
    assert panel.last_check is None and not panel.apply_button.isEnabled()


def test_export_next_generation_at_same_path_releases_old_attachments(panel, tmp_path):
    receipt = dict(source=tmp_path / "base.iso", target=tmp_path / "copy.iso", plan={"name":"One", "author":"A"})
    panel.prefill_from_build(receipt)
    panel.project_field.setText("private.2k5mod")
    panel.retail_field.setText("reference.iso")
    panel.set_assets([tmp_path / "notes.txt"])
    panel.prefill_from_build(receipt)
    assert panel.project_field.text()
    panel.prefill_from_build({**receipt, "plan": {"name": "Two", "author": "B"}})
    assert not panel.project_field.text() and not panel.retail_field.text() and not panel._asset_paths
    assert (panel.name_field.text(), panel.author_field.text()) == ("Two", "B")


def test_reopen_custom_league_stars_tiers_kit_and_honors(app, tmp_path):
    panel = BuildPanel()
    try:
        project, honors = (str(tmp_path / name) for name in ("league.json", "honors.csv"))
        overrides = dict(abilities=True, abilities_right_stick_stars_only=True, abilities_button_moves_stars_only=False,
                         abilities_charge_stars_only=True, abilities_star_access=["full", "full", "stick_charge", "full"],
                         honors_history=honors, team_number_scale={"13H0": 1.15}, stock_age_policy="keep_birthdates")
        panel.load_softdrink_sources(dict(preset="softdrink_advanced", project=project, overrides=overrides))
        state = panel.project_build_settings()
        for key, expected in overrides.items():
            assert state[key] == expected
        panel.softdrink_project_check.setChecked(False)
        state = panel.project_build_settings()
        panel.restore_project_build_settings({})
        assert not panel.softdrink_project_field.text() and not panel.honors_history_field.text()
        panel.restore_project_build_settings(state)
        assert panel.project_build_settings() == state
        assert panel.softdrink_project_field.text() == project and not panel.softdrink_project_check.isChecked()
    finally:
        panel.deleteLater()


def test_cancel_then_resume_verified_assets_and_protect_user_changes(tmp_path):
    first, second = tmp_path / "a.txt", tmp_path / "b.txt"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    bundle, folder = tmp_path / "sources.zip", tmp_path / "work"
    identity = modpack_sources.write_bundle(bundle, {}, {"assets/a.txt": first, "assets/b.txt": second})
    def cancel(stage, *_):
        if "assets/b.txt" in stage:
            raise InterruptedError("Cancelled")
    with pytest.raises(InterruptedError):
        modpack_sources.extract_bundle(bundle, folder, identity, resume=True, progress=cancel)
    good = folder / "assets/a.txt"
    saved = good.stat().st_mtime_ns
    assert good.read_bytes() == b"first" and not (folder / "assets/b.txt").exists()
    modpack_sources.extract_bundle(bundle, folder, identity, resume=True)
    assert good.stat().st_mtime_ns == saved
    assert (folder / "assets/b.txt").read_bytes() == b"second"
    good.write_bytes(b"mine")
    with pytest.raises(modpack.ModpackError, match="different contents"):
        modpack_sources.extract_bundle(bundle, folder, identity, resume=True)
    assert good.read_bytes() == b"mine"


@pytest.mark.parametrize("target", [64, 128])
def test_chosen_memory_survives_in_working_recipe_and_resume(tmp_path, target):
    member = "assets/project.json"
    doc = tmp_path / member
    doc.parent.mkdir()
    doc.write_text(json.dumps({"edits": []}))
    recipe = dict(schema="softdrink_sources/v1", project="@pack/" + member, preset="softdrink_experimental",
                  overrides={"console_memory": 128 if target == 64 else 64})
    local = modpack_sources.materialize(recipe, tmp_path, resume=True, console_target=target)
    assert local["overrides"]["console_memory"] == target
    assert modpack_sources.build_plan(json.loads((tmp_path / "SOFTDRINK-build-recipe.json").read_bytes())).console_memory == target
    assert modpack_sources.materialize(recipe, tmp_path, resume=True, console_target=target) == local


def test_loose_league_artwork_goes_through_build_preflight_not_zip(tmp_path):
    project = tmp_path / "SOFTDRINK-league-project.json"
    project.write_text(json.dumps(dict(schema="nfl2k5_visual_mod_project/v1", purpose="uniforms", edits=[])))
    data = doctor.project_inputs(project)
    assert data.document["purpose"] == "uniforms" and data.name == project.name
    report = doctor.doctor(project, "", mod_build.BuildPlan("", ""), checks=("inventory",))
    assert report.project["manifest_sha256"] == data.manifest_sha256
    assert not any(row.code == "project.unreadable" for row in report.findings)


def test_index_progress_can_cancel_before_disc_build(tmp_path):
    from mod_editor.core.nfl2k5_source_cache import Nfl2k5SourceCache
    from mod_editor.core.nfl2k5_build_service import Nfl2k5BuildService
    def index(self, source, progress=None):
        progress("Checking your game file", 7, 10)
    def stop(stage, *_):
        if stage == "Checking your game file":
            raise InterruptedError("Cancelled")
    with patch.object(Nfl2k5BuildService, "preflight_project", return_value={"edits":[{"kind":"texture"}]}), \
         patch.object(Nfl2k5SourceCache, "index", index), patch.object(mod_build, "build") as run:
        with pytest.raises(InterruptedError):
            modpack_sources.build_project(mod_build.BuildPlan("base.iso","new.iso"), tmp_path / "artwork.json", stop)
        run.assert_not_called()


def test_failed_publish_restores_both_disc_and_receipts(tmp_path):
    target = tmp_path / "out.iso"
    private = tmp_path / "private"
    private.mkdir()
    staged = private / target.name
    staged.write_bytes(b"new disc")
    target.write_bytes(b"old disc")
    suffixes = (".surfaces.json", ".greens.json")
    for suffix in suffixes:
        Path(str(target) + suffix).write_bytes(b"previous " + suffix.encode())
    Path(str(staged) + suffixes[0]).write_bytes(b"new")
    previous = image_use.receipt_states(target, suffixes)
    with patch.object(image_use, "publish_image", side_effect=PermissionError("output in use")):
        with pytest.raises(PermissionError):
            image_use.publish_image_with_receipts(staged, target, target.stat(), previous)
    assert target.read_bytes() == b"old disc"
    assert [Path(str(target) + s).read_bytes() for s in suffixes] == [b"previous " + s.encode() for s in suffixes]


def test_receipt_path_collision_and_changed_during_build_preserve_outputs(tmp_path):
    target = tmp_path / "out.iso"
    staged = tmp_path / "staged.iso"
    staged.write_bytes(b"verified")
    suffixes = (".surfaces.json",)
    snapshots = image_use.receipt_states(target, suffixes)
    path = Path(str(target) + suffixes[0])
    path.mkdir()
    with pytest.raises(image_use.ValidationError, match="regular file"):
        image_use.receipt_states(target, suffixes)
    path.rmdir()
    path.write_text("appeared during build")
    with pytest.raises(image_use.ValidationError, match="changed"):
        image_use.publish_image_with_receipts(staged, target, None, snapshots)
    assert not target.exists() and path.read_text() == "appeared during build"


def test_compaction_alone_is_not_a_game_change(tmp_path):
    retail = {"default.xbe": b"XBEH" + bytes(2048), "team": b"roster"}
    before = image(tmp_path / "source.iso", retail)
    compact = tmp_path / "compact.iso"
    receipt = discs.compact_copy(before, compact)
    assert before.stat().st_size != compact.stat().st_size
    assert not discs.game_files_changed(before, receipt["files"], lambda *_: None)
    changed = image(tmp_path / "changed.iso", {**retail, "team": b"edited"})
    assert discs.game_files_changed(changed, receipt["files"], lambda *_: None)


def test_invalid_loose_artwork_is_reported_as_an_artwork_error(tmp_path):
    project = tmp_path / "league.json"
    project.write_text('{"schema": "unknown"}')
    report = doctor.doctor(project, "", mod_build.BuildPlan("", ""), checks=("inventory",))
    assert [f for f in report.findings if f.code == "project.unreadable"]
    assert "zip" not in report.findings[0].detail.lower()


def test_real_stock_preflight_and_coach_edits_use_the_same_roster(tmp_path):
    from mod_editor.core import nfl2k5_roster_records as records
    source = Path(os.environ.get("NFL2K5_RETAIL_ISO", ""))
    if not source.is_file():
        pytest.skip("requires a user-provided NFL 2K5 retail game")
    plan = mod_build.BuildPlan(str(source), str(tmp_path / "unused.iso"), coach_ai=True)
    with pytest.raises(ValueError, match="only selected change was left out"):
        mod_build.build(plan, require_change=True)
    assert not Path(plan.target).exists()
    with pytest.raises(ValueError, match="hiring pool"):
        mod_build._coach_carousel_preflight(source, lambda *_: None)
    clubs = ["ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB",
             "HOU", "IND", "JAX", "KC", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "OAK", "PHI",
             "PIT", "SD", "SEA", "SF", "STL", "TB", "TEN", "WAS"]
    edits = tmp_path / "roster-edits.json"
    edits.write_text(json.dumps({"schema": records.EDITS_SCHEMA, "edits": [],
                                "coaches": [{"team": team, "first": "A", "last": "B"} for team in clubs]}))
    mod_build._coach_carousel_preflight(source, lambda *_: None, edits)
    assert not Path(plan.target).exists()


@pytest.mark.parametrize("disc_renamed", [False, True])
def test_process_death_in_multi_file_publication_recovers_one_generation(tmp_path, disc_renamed):
    previous = tmp_path / "out.iso"
    stage = tmp_path / "private"
    stage.mkdir()
    staged = stage / "out.iso"
    suffix = ".greens.json"
    for path, token in ((previous, "old"), (staged, "new")):
        path.write_text(token)
        Path(str(path) + suffix).write_text(token + " receipt")
    code = """
import os, sys
from pathlib import Path
from mod_editor.core import image_use
target, stage = map(Path, sys.argv[1:3])
original = image_use.publish_image
def power_cut(*args):
    if sys.argv[3] == "True":
        original(*args)
    os._exit(23)
image_use.publish_image = power_cut
image_use.publish_image_with_receipts(stage, target, target.stat(), image_use.receipt_states(target, (".greens.json",)))
"""
    result = subprocess.run([sys.executable, "-c", code, str(previous), str(staged), str(disc_renamed)], check=False)
    assert result.returncode == 23
    image_use.recover_image_publication(previous, (suffix,))
    token = "new" if disc_renamed else "old"
    assert previous.read_text() == token
    assert Path(str(previous) + suffix).read_text() == token + " receipt"
    assert not list(tmp_path.glob(".2k5-publish-*"))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
