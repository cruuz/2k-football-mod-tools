"""Give every built-in team its own uniform assets instead of shared ones.

APF's built-in teams do not each own their kit. Forty teams draw helmets from
only **six** helmet textures, socks from six, numbers from seven, jerseys from
nine. Editing "the Eagles helmet" therefore edits every other team pointing at
the same texture, which is exactly the wall modders keep hitting: a wing painted
for one team turns up on several, so the only safe edits are ones every sharer
can live with.

The game already ships more slots than it uses. There are twenty-four helmet
packages and only six are referenced; the other eighteen sit complete and
unused. The same is true across most families. So this is not about adding
assets, it is about pointing each team at one of its own.

The assignment plan is not computed here and is not free-form. It is the frozen
deterministic plan that ``tools/apf_uniform_selector_patch.py`` already derives
from the pinned allocation report and re-derives through the retail ROST pointer
graph, and that writer refuses any recipe that is not byte-identical to it. This
module is the seam that lets the app offer it, describe it honestly, and run it;
it adds no write authority of its own.

What it does not claim: the writer's own boundary is that runtime visibility and
Xbox 360 hardware acceptance are unproved. Nothing here upgrades that.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import tempfile


def _writer():
    """The selector writer, imported the way apf_studio imports tools/."""

    tools = str(Path(__file__).resolve().parents[2] / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    try:
        import apf_uniform_selector_patch as module
    except ImportError:  # pragma: no cover - lean checkouts without tools/
        return None
    return module


class UniformIndependenceError(ValueError):
    """The plan could not be described or applied."""


#: Families in the order a modder cares about them: the ones that actually
#: change first, and helmets first of all, because that is the reported wall.
_FAMILY_ORDER = (
    "helmet", "jersey", "number", "sock", "pants", "shoulder",
    "font", "logo", "textlogo", "glove", "shoe",
)


@dataclass(frozen=True)
class FamilyPlan:
    """One family's before and after, in terms a modder can act on."""

    family: str
    catalog_count: int
    selector_slot: int
    distinct_before: int
    distinct_after: int
    teams_changed: int

    @property
    def already_independent(self) -> bool:
        return self.teams_changed == 0

    @property
    def summary(self) -> str:
        if self.already_independent:
            return (
                f"{self.family}: already one per team "
                f"({self.distinct_before} of {self.catalog_count} used)"
            )
        return (
            f"{self.family}: {self.distinct_before} shared textures become "
            f"{self.distinct_after}, so {self.teams_changed} teams stop sharing"
        )


@dataclass(frozen=True)
class IndependencePlan:
    """The whole frozen plan, described without touching a game volume."""

    families: tuple[FamilyPlan, ...]

    @property
    def total_teams_changed(self) -> int:
        return sum(row.teams_changed for row in self.families)

    @property
    def helmet(self) -> FamilyPlan | None:
        return next((row for row in self.families if row.family == "helmet"), None)

    def headline(self) -> str:
        helmet = self.helmet
        if helmet is None or helmet.already_independent:
            return "Every team already has its own uniform assets."
        return (
            f"Right now {helmet.distinct_before} helmet textures are shared by "
            f"all teams, so editing one team's helmet changes the others. "
            f"This gives every team its own."
        )


def plan_available() -> bool:
    """Whether the plan can be described at all, for a GUI to check first."""

    module = _writer()
    if module is None:
        return False
    try:
        module.load_authorities()
    except Exception:  # noqa: BLE001 - a missing report is not an error here
        return False
    return True


def describe_plan() -> IndependencePlan:
    """Read the frozen plan and report what it changes. No game data needed."""

    module = _writer()
    if module is None:  # pragma: no cover - lean checkouts without tools/
        raise UniformIndependenceError("The selector planner is unavailable")
    try:
        allocation, _raw, _capacity, _capacity_raw = module.load_authorities()
        recipe = module.expected_recipe(allocation)
    except Exception as exc:  # noqa: BLE001 - surfaced as one clear message
        raise UniformIndependenceError(
            f"The uniform assignment plan could not be read: {exc}"
        ) from exc

    rows: list[FamilyPlan] = []
    for family in recipe.get("families", []):
        assignments = family.get("assignments") or []
        before = {row["expected_retail_asset_index"] for row in assignments}
        after = {row["replacement_asset_index"] for row in assignments}
        changed = sum(
            1 for row in assignments
            if row["expected_retail_asset_index"] != row["replacement_asset_index"]
        )
        rows.append(FamilyPlan(
            family=str(family.get("family", "")),
            catalog_count=int(family.get("catalog_count", 0)),
            selector_slot=int(family.get("selector_slot", -1)),
            distinct_before=len(before),
            distinct_after=len(after),
            teams_changed=changed,
        ))

    order = {name: index for index, name in enumerate(_FAMILY_ORDER)}
    rows.sort(key=lambda row: (order.get(row.family, len(order)), row.family))
    return IndependencePlan(families=tuple(rows))


@dataclass(frozen=True)
class SharedAsset:
    """Which teams a single texture currently belongs to."""

    family: str
    asset_index: int
    teams: tuple[str, ...]

    @property
    def is_shared(self) -> bool:
        return len(self.teams) > 1

    def warning(self) -> str:
        """What to tell someone before they paint on this texture."""

        if not self.teams:
            return (
                "No built-in team uses this texture, so editing it is safe: "
                "nothing on the field changes until a team is pointed at it."
            )
        if not self.is_shared:
            return f"Used only by {self.teams[0]}. Editing it affects that team alone."
        listed = ", ".join(self.teams)
        return (
            f"Shared by {len(self.teams)} teams: {listed}. Editing this texture "
            f"changes all of them. Use Team Independence to give each team its own."
        )


def teams_using(family: str, asset_index: int) -> SharedAsset:
    """Which built-in teams currently point at one texture.

    This is the question that was never asked in the app and cost people hours:
    a wing painted for one team quietly appears on every other team sharing the
    texture. The answer comes from the same pinned allocation the plan uses, so
    it agrees with what Team Independence reports.
    """

    module = _writer()
    if module is None:  # pragma: no cover - lean checkouts without tools/
        raise UniformIndependenceError("The selector planner is unavailable")
    try:
        allocation, _raw, _capacity, _capacity_raw = module.load_authorities()
    except Exception as exc:  # noqa: BLE001 - one clear message
        raise UniformIndependenceError(
            f"The uniform assignment plan could not be read: {exc}"
        ) from exc

    names = {
        int(row["team_index"]): str(row.get("display_name") or row["team_index"])
        for row in allocation.get("teams", [])
        if isinstance(row, dict) and "team_index" in row
    }

    for entry in allocation.get("families", []):
        if entry.get("family") != family:
            continue
        assignments = (entry.get("built_in_plan") or {}).get("assignments") or []
        teams = tuple(
            names.get(int(row["team_index"]), str(row["team_index"]))
            for row in assignments
            if int(row.get("expected_retail_asset_index", -1)) == asset_index
        )
        return SharedAsset(family=family, asset_index=asset_index, teams=teams)

    raise UniformIndependenceError(f"Unknown uniform family: {family}")


def apply_plan(index_0a: Path, output_volume: Path, manifest: Path) -> dict:
    """Write a new ``0A`` in which every team owns its own uniform assets.

    The user's own volume is opened read-only and a new one is created; nothing
    is modified in place. The recipe is generated into a private temporary file
    rather than being asked of the user, because the writer accepts exactly one
    plan and a hand-edited recipe would only ever be refused.
    """

    module = _writer()
    if module is None:  # pragma: no cover - lean checkouts without tools/
        raise UniformIndependenceError("The selector writer is unavailable")

    source = Path(index_0a)
    if not source.is_file():
        raise UniformIndependenceError(f"Game volume not found: {source}")
    for target in (Path(output_volume), Path(manifest)):
        if target.exists():
            raise UniformIndependenceError(f"A file already exists there: {target}")

    with tempfile.TemporaryDirectory(prefix="apf-uniform-independence-") as work:
        recipe_path = Path(work) / "recipe.json"
        try:
            allocation, _raw, _capacity, _capacity_raw = module.load_authorities()
            payload = module.transport.canonical_json_bytes(
                module.expected_recipe(allocation)
            )
            recipe_path.write_bytes(payload)
            return module.write_output(
                source, recipe_path, Path(output_volume), Path(manifest)
            )
        except UniformIndependenceError:
            raise
        except Exception as exc:  # noqa: BLE001 - one clear message for the UI
            raise UniformIndependenceError(str(exc)) from exc
