"""Retail-free APF 32-team / 53-player *planning* workspace.

APF's stock team record exposes exactly 42 runtime membership pointers.  This
module intentionally does not patch those pointers and never claims that the
game sees 53 players.  It combines a private, source-derived 42-player view
with eleven user-authored project-side reserve assignments for each of the
first 32 populated team records.

Only the reserve plan is serializable.  The canonical plan contains player
indices selected by the modder plus fixed target metadata; it never contains
the source's 42 active memberships, player records, names, preimages, ROST
bytes, or executable bytes.  Binding the plan to a loaded source is a separate
validation step and fails if a reserve duplicates any source-active player.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Iterable, Mapping, Sequence


SCHEMA = "apf2k8_roster_reserve_plan/v1"
GAME = "apf2k8_xbox360"
SCOPE = "32_teams_42_stock_active_plus_11_project_reserves"
FILE_EXTENSION = ".apf2k8roster"
TEAM_COUNT = 32
STOCK_ACTIVE_SLOTS = 42
PROJECT_RESERVE_SLOTS = 11
MASTER_ROSTER_SLOTS = STOCK_ACTIVE_SLOTS + PROJECT_RESERVE_SLOTS
PLAYER_COUNT = 2_254
MAX_PLAN_BYTES = 256 * 1024


class RosterWorkspaceError(ValueError):
    """A reserve plan or source membership view left the bounded contract."""


def _integer(value: object, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise RosterWorkspaceError(
            f"{label} must be a whole number from {minimum} to {maximum}"
        )
    return value


def _reserve_slots(
    values: Sequence[int | None], *, team_index: int
) -> tuple[int | None, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(
        values, Sequence
    ):
        raise RosterWorkspaceError(
            f"Team {team_index} reserve slots must be one ordered list"
        )
    if len(values) != PROJECT_RESERVE_SLOTS:
        raise RosterWorkspaceError(
            f"Team {team_index} must expose exactly {PROJECT_RESERVE_SLOTS} "
            "project-side reserve slots"
        )
    result: list[int | None] = []
    for slot, value in enumerate(values):
        if value is None:
            result.append(None)
        else:
            result.append(
                _integer(
                    value,
                    f"Team {team_index} reserve slot {slot} player index",
                    0,
                    PLAYER_COUNT - 1,
                )
            )
    assigned = [value for value in result if value is not None]
    if len(set(assigned)) != len(assigned):
        raise RosterWorkspaceError(
            f"Team {team_index} assigns the same reserve player more than once"
        )
    return tuple(result)


@dataclass(frozen=True)
class TeamReservePlan:
    """Eleven authored reserve positions for one stable on-disc team index."""

    team_index: int
    reserve_player_indices: tuple[int | None, ...]

    def __post_init__(self) -> None:
        _integer(self.team_index, "Team index", 0, TEAM_COUNT - 1)
        normalized = _reserve_slots(
            self.reserve_player_indices, team_index=self.team_index
        )
        object.__setattr__(self, "reserve_player_indices", normalized)

    @property
    def assigned_count(self) -> int:
        return sum(value is not None for value in self.reserve_player_indices)

    @property
    def complete(self) -> bool:
        return self.assigned_count == PROJECT_RESERVE_SLOTS


@dataclass(frozen=True)
class ReserveRosterPlan:
    """All 32 project-side reserve lists, independent of private source data."""

    teams: tuple[TeamReservePlan, ...]

    def __post_init__(self) -> None:
        if any(not isinstance(team, TeamReservePlan) for team in self.teams):
            raise RosterWorkspaceError(
                "Every reserve-plan team row must use the bounded team contract"
            )
        if len(self.teams) != TEAM_COUNT:
            raise RosterWorkspaceError(
                f"A reserve plan must contain exactly {TEAM_COUNT} team rows"
            )
        observed = tuple(team.team_index for team in self.teams)
        if observed != tuple(range(TEAM_COUNT)):
            raise RosterWorkspaceError(
                "Reserve-plan teams must be in exact team-index order 0..31"
            )
        assigned = [
            player
            for team in self.teams
            for player in team.reserve_player_indices
            if player is not None
        ]
        if len(set(assigned)) != len(assigned):
            raise RosterWorkspaceError(
                "A player cannot occupy reserve slots for two different teams"
            )

    @classmethod
    def empty(cls) -> "ReserveRosterPlan":
        return cls(
            tuple(
                TeamReservePlan(team_index, (None,) * PROJECT_RESERVE_SLOTS)
                for team_index in range(TEAM_COUNT)
            )
        )

    @property
    def assigned_count(self) -> int:
        return sum(team.assigned_count for team in self.teams)

    @property
    def open_slot_count(self) -> int:
        return TEAM_COUNT * PROJECT_RESERVE_SLOTS - self.assigned_count

    @property
    def completed_team_count(self) -> int:
        return sum(team.complete for team in self.teams)

    def team(self, team_index: int) -> TeamReservePlan:
        index = _integer(team_index, "Team index", 0, TEAM_COUNT - 1)
        return self.teams[index]

    def assign(
        self, team_index: int, reserve_slot: int, player_index: int | None
    ) -> "ReserveRosterPlan":
        team = self.team(team_index)
        slot = _integer(
            reserve_slot,
            "Project reserve slot",
            0,
            PROJECT_RESERVE_SLOTS - 1,
        )
        if player_index is not None:
            _integer(
                player_index,
                "Reserve player index",
                0,
                PLAYER_COUNT - 1,
            )
        values = list(team.reserve_player_indices)
        values[slot] = player_index
        updated = list(self.teams)
        updated[team.team_index] = TeamReservePlan(team.team_index, tuple(values))
        return ReserveRosterPlan(tuple(updated))


@dataclass(frozen=True)
class RosterSlot:
    """One display row in the combined 53-position planning view."""

    team_index: int
    master_slot: int
    role: str
    player_index: int | None
    runtime_visible: bool
    status: str


@dataclass(frozen=True)
class TeamRosterWorkspace:
    team_index: int
    selection_status: str
    slots: tuple[RosterSlot, ...]

    @property
    def active_player_indices(self) -> tuple[int, ...]:
        return tuple(
            slot.player_index
            for slot in self.slots[:STOCK_ACTIVE_SLOTS]
            if slot.player_index is not None
        )

    @property
    def reserve_player_indices(self) -> tuple[int | None, ...]:
        return tuple(
            slot.player_index for slot in self.slots[STOCK_ACTIVE_SLOTS:]
        )

    @property
    def master_complete(self) -> bool:
        return all(value is not None for value in self.reserve_player_indices)


@dataclass(frozen=True)
class RosterWorkspaceSummary:
    team_count: int
    source_active_player_count: int
    assigned_project_reserve_count: int
    open_project_reserve_count: int
    complete_master_team_count: int
    runtime_visible_player_count: int
    runtime_visible_reserve_count: int


@dataclass(frozen=True)
class RosterWorkspace:
    """Private source-active view bound to a retail-free authored reserve plan."""

    plan: ReserveRosterPlan
    teams: tuple[TeamRosterWorkspace, ...]
    summary: RosterWorkspaceSummary


def _selection_status(team_index: int) -> str:
    return (
        "stock_offline_team"
        if team_index < 24
        else "populated_online_placeholder_offline_selector_unproved"
    )


def stock_active_from_memberships(
    memberships: Iterable[Mapping[str, object]],
) -> dict[int, tuple[int, ...]]:
    """Normalize the parser's 1,344 source-derived membership rows.

    The result is private runtime context. It is intentionally not accepted by
    :func:`encode_reserve_plan` and can never enter the shareable plan payload.
    """

    slots: dict[tuple[int, int], int] = {}
    for ordinal, row in enumerate(memberships):
        if not isinstance(row, Mapping):
            raise RosterWorkspaceError(
                f"Source membership row {ordinal} is not a mapping"
            )
        team_index = _integer(
            row.get("team_index"),
            f"Source membership row {ordinal} team index",
            0,
            TEAM_COUNT - 1,
        )
        roster_slot = _integer(
            row.get("roster_slot"),
            f"Source membership row {ordinal} roster slot",
            0,
            STOCK_ACTIVE_SLOTS - 1,
        )
        player_index = _integer(
            row.get("player_index"),
            f"Source membership row {ordinal} player index",
            0,
            PLAYER_COUNT - 1,
        )
        key = (team_index, roster_slot)
        if key in slots:
            raise RosterWorkspaceError(
                f"Source membership team {team_index} slot {roster_slot} is duplicated"
            )
        slots[key] = player_index
    expected_count = TEAM_COUNT * STOCK_ACTIVE_SLOTS
    if len(slots) != expected_count:
        raise RosterWorkspaceError(
            f"Source membership view has {len(slots)} rows; expected exactly "
            f"{expected_count} (32 teams x 42 active slots)"
        )
    players = list(slots.values())
    if len(set(players)) != len(players):
        raise RosterWorkspaceError(
            "A source-active player occurs in more than one counted team slot"
        )
    return {
        team_index: tuple(
            slots[(team_index, roster_slot)]
            for roster_slot in range(STOCK_ACTIVE_SLOTS)
        )
        for team_index in range(TEAM_COUNT)
    }


def bind_reserve_plan(
    plan: ReserveRosterPlan,
    source_active: Mapping[int, Sequence[int]],
) -> RosterWorkspace:
    """Bind authored reserves to an exact private 32x42 source membership view."""

    if not isinstance(source_active, Mapping):
        raise RosterWorkspaceError("Source-active memberships must be a team mapping")
    if set(source_active) != set(range(TEAM_COUNT)):
        raise RosterWorkspaceError(
            "Source-active membership mapping must contain exact team indices 0..31"
        )
    normalized_active: dict[int, tuple[int, ...]] = {}
    all_active: list[int] = []
    for team_index in range(TEAM_COUNT):
        values = source_active[team_index]
        if isinstance(values, (str, bytes, bytearray)) or not isinstance(
            values, Sequence
        ):
            raise RosterWorkspaceError(
                f"Team {team_index} source-active membership is not an ordered list"
            )
        if len(values) != STOCK_ACTIVE_SLOTS:
            raise RosterWorkspaceError(
                f"Team {team_index} must have exactly {STOCK_ACTIVE_SLOTS} "
                "source-active players"
            )
        active = tuple(
            _integer(
                value,
                f"Team {team_index} active slot {slot} player index",
                0,
                PLAYER_COUNT - 1,
            )
            for slot, value in enumerate(values)
        )
        if len(set(active)) != len(active):
            raise RosterWorkspaceError(
                f"Team {team_index} has a duplicate source-active player"
            )
        normalized_active[team_index] = active
        all_active.extend(active)
    if len(set(all_active)) != len(all_active):
        raise RosterWorkspaceError(
            "A source-active player occurs on more than one team"
        )
    active_set = set(all_active)
    reserve_set = {
        player
        for team in plan.teams
        for player in team.reserve_player_indices
        if player is not None
    }
    overlap = active_set.intersection(reserve_set)
    if overlap:
        player = min(overlap)
        raise RosterWorkspaceError(
            f"Reserve player {player} is already one of the 1,344 source-active players"
        )

    teams: list[TeamRosterWorkspace] = []
    for team_plan in plan.teams:
        rows: list[RosterSlot] = []
        for slot, player in enumerate(normalized_active[team_plan.team_index]):
            rows.append(
                RosterSlot(
                    team_plan.team_index,
                    slot,
                    "stock_active",
                    player,
                    True,
                    "runtime_active_stock_membership",
                )
            )
        for reserve_slot, player in enumerate(team_plan.reserve_player_indices):
            rows.append(
                RosterSlot(
                    team_plan.team_index,
                    STOCK_ACTIVE_SLOTS + reserve_slot,
                    "project_reserve",
                    player,
                    False,
                    (
                        "project_only_not_written_to_game"
                        if player is not None
                        else "project_only_unassigned"
                    ),
                )
            )
        teams.append(
            TeamRosterWorkspace(
                team_plan.team_index,
                _selection_status(team_plan.team_index),
                tuple(rows),
            )
        )
    assigned = plan.assigned_count
    return RosterWorkspace(
        plan,
        tuple(teams),
        RosterWorkspaceSummary(
            TEAM_COUNT,
            TEAM_COUNT * STOCK_ACTIVE_SLOTS,
            assigned,
            TEAM_COUNT * PROJECT_RESERVE_SLOTS - assigned,
            plan.completed_team_count,
            TEAM_COUNT * STOCK_ACTIVE_SLOTS,
            0,
        ),
    )


def bind_membership_rows(
    plan: ReserveRosterPlan,
    memberships: Iterable[Mapping[str, object]],
) -> RosterWorkspace:
    return bind_reserve_plan(plan, stock_active_from_memberships(memberships))


def _document(plan: ReserveRosterPlan) -> dict[str, object]:
    return {
        "distribution": {
            "contains_executable_patch": False,
            "contains_retail_bytes": False,
            "contains_source_active_memberships": False,
            "payload": "user-authored reserve player indices only",
        },
        "game": GAME,
        "schema": SCHEMA,
        "scope": SCOPE,
        "team_count": TEAM_COUNT,
        "teams": [
            {
                "reserve_player_indices": list(team.reserve_player_indices),
                "team_index": team.team_index,
            }
            for team in plan.teams
        ],
    }


def encode_reserve_plan(plan: ReserveRosterPlan) -> bytes:
    """Return one deterministic, replacement-only JSON plan."""

    return (
        json.dumps(_document(plan), sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def decode_reserve_plan(data: bytes) -> ReserveRosterPlan:
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_PLAN_BYTES:
        raise RosterWorkspaceError(
            f"Reserve plan size must be from 1 to {MAX_PLAN_BYTES} bytes"
        )
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RosterWorkspaceError("Reserve plan is not valid UTF-8 JSON") from exc
    if not isinstance(document, dict) or set(document) != {
        "distribution",
        "game",
        "schema",
        "scope",
        "team_count",
        "teams",
    }:
        raise RosterWorkspaceError("Reserve plan root fields are invalid")
    if (
        document.get("schema") != SCHEMA
        or document.get("game") != GAME
        or document.get("scope") != SCOPE
        or document.get("team_count") != TEAM_COUNT
    ):
        raise RosterWorkspaceError("Reserve plan targets a different contract")
    if document.get("distribution") != _document(ReserveRosterPlan.empty())[
        "distribution"
    ]:
        raise RosterWorkspaceError("Reserve plan does not declare the retail-free boundary")
    raw_teams = document.get("teams")
    if not isinstance(raw_teams, list) or len(raw_teams) != TEAM_COUNT:
        raise RosterWorkspaceError("Reserve plan must contain exactly 32 team rows")
    teams: list[TeamReservePlan] = []
    for ordinal, raw in enumerate(raw_teams):
        if not isinstance(raw, dict) or set(raw) != {
            "reserve_player_indices",
            "team_index",
        }:
            raise RosterWorkspaceError(f"Reserve-plan team row {ordinal} is invalid")
        team_index = _integer(
            raw.get("team_index"), f"Reserve-plan team row {ordinal} index", 0, 31
        )
        slots = raw.get("reserve_player_indices")
        if not isinstance(slots, list):
            raise RosterWorkspaceError(
                f"Reserve-plan team {team_index} reserve slots must be a list"
            )
        teams.append(TeamReservePlan(team_index, tuple(slots)))
    plan = ReserveRosterPlan(tuple(teams))
    if encode_reserve_plan(plan) != data:
        raise RosterWorkspaceError("Reserve plan JSON is not canonical")
    return plan


def _plan_path(path: Path, *, must_exist: bool) -> Path:
    supplied = Path(path).expanduser()
    if supplied.suffix.casefold() != FILE_EXTENSION:
        raise RosterWorkspaceError(
            f"Reserve-plan files must use the {FILE_EXTENSION} extension"
        )
    if not supplied.is_absolute():
        supplied = Path.cwd() / supplied
    supplied = Path(os.path.abspath(os.fspath(supplied)))
    if must_exist:
        try:
            supplied_info = supplied.lstat()
        except OSError as exc:
            raise RosterWorkspaceError("Reserve plan could not be opened") from exc
        if stat.S_ISLNK(supplied_info.st_mode):
            raise RosterWorkspaceError("Reserve plan must be a bounded regular file")
        return supplied.resolve(strict=True)
    parent = supplied.parent.resolve(strict=True)
    info = parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise RosterWorkspaceError("Reserve-plan destination folder is unsafe")
    return parent / supplied.name


def save_reserve_plan(plan: ReserveRosterPlan, destination: Path) -> Path:
    """Atomically publish a new plan without overwriting any existing path."""

    destination = _plan_path(destination, must_exist=False)
    if os.path.lexists(destination):
        raise FileExistsError(destination)
    data = encode_reserve_plan(plan)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    published = False
    try:
        os.fchmod(descriptor, 0o600)
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("Short write while saving the reserve plan")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.link(temporary, destination)
        published = True
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        if destination.read_bytes() != data:
            raise RosterWorkspaceError("Published reserve plan failed verification")
    except BaseException:
        if published:
            destination.unlink(missing_ok=True)
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
    return destination


def load_reserve_plan(source: Path) -> ReserveRosterPlan:
    source = _plan_path(source, must_exist=True)
    info = source.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_nlink != 1
        or not 0 < info.st_size <= MAX_PLAN_BYTES
    ):
        raise RosterWorkspaceError("Reserve plan must be a bounded regular file")
    descriptor = os.open(
        source,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or (opened.st_dev, opened.st_ino, opened.st_size)
            != (info.st_dev, info.st_ino, info.st_size)
        ):
            raise RosterWorkspaceError("Reserve plan changed while it was opened")
        chunks: list[bytes] = []
        remaining = MAX_PLAN_BYTES + 1
        while remaining > 0:
            block = os.read(descriptor, min(64 * 1024, remaining))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
        data = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(data) != opened.st_size
            or len(data) > MAX_PLAN_BYTES
            or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        ):
            raise RosterWorkspaceError("Reserve plan changed while it was read")
    finally:
        os.close(descriptor)
    return decode_reserve_plan(data)


__all__ = [
    "FILE_EXTENSION",
    "GAME",
    "MASTER_ROSTER_SLOTS",
    "MAX_PLAN_BYTES",
    "PLAYER_COUNT",
    "PROJECT_RESERVE_SLOTS",
    "ReserveRosterPlan",
    "RosterSlot",
    "RosterWorkspace",
    "RosterWorkspaceError",
    "RosterWorkspaceSummary",
    "SCHEMA",
    "SCOPE",
    "STOCK_ACTIVE_SLOTS",
    "TEAM_COUNT",
    "TeamReservePlan",
    "TeamRosterWorkspace",
    "bind_membership_rows",
    "bind_reserve_plan",
    "decode_reserve_plan",
    "encode_reserve_plan",
    "load_reserve_plan",
    "save_reserve_plan",
    "stock_active_from_memberships",
]
