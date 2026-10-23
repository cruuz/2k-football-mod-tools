"""Signed franchise migration service shared by Studio and the command line."""
from __future__ import annotations

from dataclasses import dataclass
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import os
import tempfile
import zipfile
import zlib

from . import nfl2k5_franchise_upgrade as upgrade
from . import nfl2k5_roster_records as rr
from . import nfl2k5_save_rost as sr

#: The migrations a franchise can take. Hair styles and honors come from the disc;
#: played-clubs uses the same verified club repair as Upgrade; undated candidates stay in the receipt.
COMMANDS = ("upgrade", "coach-sync", "team-history", "hair-styles", "honors", "played-clubs")
DEFAULT_COHORT = Path(__file__).resolve().parents[2] / "mod_editor/data/f12_cohort.json"


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def upgrade_source(path: Path) -> Path:
    """The signed folder for a loose SAVEGAME.DAT (what Studio's Open dialog hands over); anything else unchanged.

    fx1 (review r2-franchise MAJOR 2): a loose container holds only SAVEGAME.DAT and EXTRA, so preview refused it
    ("requires exactly one TYPE") and the default output landed inside the save folder.
    """
    path = Path(path)
    if path.is_file() and path.name.upper() == rr.SAVEGAME_NAME.upper() and not zipfile.is_zipfile(path):
        return path.parent
    return path


def load_container(path: Path) -> rr.SaveContainer:
    container = rr.SaveContainer.load(path, require_signature=True)
    for name in container.members:
        relative = PurePosixPath(name.replace("\\", "/"))
        upgrade.require(not relative.is_absolute() and ".." not in relative.parts
                        and ":" not in name, "unsafe save member path")
    for leaf in ("SAVEGAME.DAT", "EXTRA", "TYPE"):
        names = [name for name in container.members if PurePosixPath(name).name.upper() == leaf]
        upgrade.require(len(names) == 1, f"requires exactly one {leaf} in a signed franchise folder")
        if leaf == "TYPE":
            upgrade.require(container.members[names[0]].decode("utf-16-le").rstrip("\0") == "FXG",
                            "TYPE must be FXG (franchise)")
    upgrade.franchise(container.savegame)
    return container


def load_disc(path: Path, *, books: bool = True) -> tuple[bytes, dict[int, bytes]]:
    upgrade.require(path.is_file(), "--disc must be a disc image file")
    with rr._outer_image()(path) as archive:
        body = archive.read_entry(5)[32:]
        roster = sr.decode(body, preamble=0, reference_year=upgrade.BASE_YEAR)
        resources = {}
        if books:
            for team in roster.teams[:32]:
                label = roster.rel(team.offset + 0x110, size=8)
                upgrade.require(label is not None, "disc team has no book label")
                key = roster.string(label + 4)
                name_id = zlib.crc32(f"{key}-pb.iff".upper().encode("utf-16-le")) & 0xFFFFFFFF
                matches = [i for i, entry in enumerate(archive.entries) if entry.name_id == name_id]
                upgrade.require(len(matches) == 1, f"disc has {len(matches)} resources for {key}-pb.iff")
                resources[name_id] = archive.read_entry(matches[0])
        return body, resources


def write_copy(container: rr.SaveContainer, payload: bytes, output: Path, before_publish=None) -> dict:
    upgrade.require(not output.exists(), "output exists; choose a fresh save directory")
    source = container.path.resolve()
    destination = output.resolve()
    upgrade.require(destination != source and source not in destination.parents,
                    "output must be outside the input save")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".franchise-upgrade-", dir=output.parent))
    try:
        # A zip source normally makes SaveContainer.write choose zip output.
        # This command always exports a directory, preserving every member.
        folder = rr.SaveContainer("folder", container.path, container.members,
                                  container.savegame_name, container.extra_name, container.verified)
        receipt = folder.write(stage, payload)
        receipt["target"] = str(output)
        if before_publish is not None:
            before_publish(receipt)   # fx1: the caller's evidence is on disk before the copy appears
        stage.rename(output)
        return receipt
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def check_paths(source: Path, disc: Path, output: Path | None, receipt: Path) -> None:
    """Keep both the save container and its evidence outside read-only inputs."""
    source, disc, receipt = source.resolve(), disc.resolve(), receipt.resolve()
    upgrade.require(not receipt.exists(), "receipt exists; choose a fresh path")
    upgrade.require(receipt != source and source not in receipt.parents and receipt != disc,
                    "receipt must be outside the input save and disc")
    if output is not None:
        output = output.resolve()
        upgrade.require(not output.exists(), "output exists; choose a fresh path")
        upgrade.require(output != source and source not in output.parents and output != disc,
                        "output must be outside the input save and disc")
        upgrade.require(receipt != output and output not in receipt.parents,
                        "receipt must be outside the output save container")


@dataclass(frozen=True)
class UpgradePlan:
    container: rr.SaveContainer
    disc: Path
    payload: bytes
    receipt: dict


def plan_upgrade(source: Path, disc: Path, *, command: str = "upgrade",
                 cohort_path: Path = DEFAULT_COHORT, team_history_path: Path | None = None) -> UpgradePlan:
    """Read, validate and preview every change, without creating any files."""
    upgrade.require(command in COMMANDS, "unknown upgrade command")
    upgrade.require(team_history_path is None or command not in ("coach-sync", "hair-styles", "honors"),
                    "TEAM evidence requires upgrade, team-history or played-clubs")
    container = load_container(source)
    before_validation = upgrade.validate_save(container.savegame)
    body, resources = load_disc(disc, books=command == "upgrade")
    payload = container.savegame
    steps = []
    if command == "upgrade":
        cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
        payload, step = upgrade.upgrade_years(payload, cohort)
        steps.append(step)
        payload, step = upgrade.sync_playbooks(payload, body, resources)
        steps.append(step)
    if command in ("upgrade", "team-history"):
        evidence = json.loads(team_history_path.read_text(encoding="utf-8")) if team_history_path else None
        payload, step = upgrade.upgrade_team_history(payload, body, evidence)
        steps.append(step)
    if command in ("upgrade", "coach-sync"):
        payload, step = upgrade.sync_coaches(payload, body)
        steps.append(step)
    if command in ("upgrade", "hair-styles"):
        # b778-hr3: a franchise started before the disc had hair styles keeps style 0 for everyone
        payload, step = upgrade.sync_hair_styles(payload, body)
        steps.append(step)
    if command == "played-clubs":
        evidence = json.loads(team_history_path.read_text(encoding="utf-8")) if team_history_path else None
        payload, step = upgrade.infer_played_clubs(payload, body, evidence)
        steps.append(step)
    if command in ("upgrade", "honors"):
        # b778-pc2: a franchise started before the disc had the honors page shows "HONORS: NONE YET" for everyone
        payload, step = upgrade.sync_honors(payload, body)
        steps.append(step)
    after_validation = upgrade.validate_save(payload)
    receipt = {"schema": upgrade.SCHEMA, "command": command, "dry_run": True,
               "input": str(source.resolve()), "disc": str(disc.resolve()),
               "disc_sha256": hash_file(disc),
               "input_savegame_sha256": upgrade.sha(container.savegame),
               "output_savegame_sha256": upgrade.sha(payload),
               "input_extra_sha256": upgrade.sha(container.members[container.extra_name]),
               "output_extra_sha256": upgrade.sha(rr.sign_save(payload)),
               "changed_fields": sum(len(s["changes"]) for s in steps), "steps": steps,
               "validation": {"before": before_validation, "after": after_validation}}
    if command == "upgrade":
        receipt["cohort_sha256"] = hash_file(cohort_path)
    if team_history_path:
        receipt["team_history_evidence_sha256"] = hash_file(team_history_path)
    return UpgradePlan(container, disc.resolve(), payload, receipt)


def write_plan(plan: UpgradePlan, output: Path | None, receipt_path: Path) -> dict:
    """Export a preview to fresh paths, refusing changes to either input since preview."""
    check_paths(plan.container.path, plan.disc, output, receipt_path)
    current = load_container(plan.container.path)
    upgrade.require(current.members == plan.container.members, "input save changed since preview; preview again")
    upgrade.require(hash_file(plan.disc) == plan.receipt["disc_sha256"],
                    "disc changed since preview; preview again")
    receipt = copy.deepcopy(plan.receipt)
    receipt["dry_run"] = output is None
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    # Reserve evidence first: a permission/path error must not leave a save
    # copy with no receipt. The output writer itself stages and verifies it.
    # fx1 (review pr67 nit, r2-franchise MINOR 3): the receipt is written, flushed and synced while the verified
    # copy is still staged, then the copy is renamed into place. A failed receipt write (disk full) leaves no
    # published copy; a failed rename removes the receipt.
    handle = receipt_path.open("x", encoding="utf-8", newline="\n")
    try:
        def publish(write_receipt=None):
            if write_receipt is not None:
                receipt["write"] = write_receipt
            handle.write(json.dumps(receipt, indent=1) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            handle.close()
        if output is not None:
            write_copy(plan.container, plan.payload, output, before_publish=publish)
        else:
            publish()
    except BaseException:
        try:
            handle.close()
        except OSError:
            pass
        receipt_path.unlink(missing_ok=True)
        raise
    return receipt
