"""The console memory a build is made for (b780-m64b): 128 MB for xemu, or an experimental 64 MB build.

Noah, 2026-11-03: "We need an option in the editor to limit a few things to allow the 64 MB option for Xbox and
Android ... maybe let people pick and choose what must be removed to get 64 to work."

* ``BuildPlan.console_memory`` is 128 (the default, the full SOFTDRINK build for xemu at 128 MB with every feature) or
  64 (an original Xbox console, or the Android emulator hakuX, which reimplements the Xbox kernel instead of running the
  real one). A 128 plan is exactly what it was before this option existed: its recipe carries no ``console_memory`` key
  (``mod_build.BuildPlan.to_recipe``) and nothing here changes one of its fields.
* At 64 every option that needs 128 MB or the real Xbox kernel (``requires_128``) must be off. The Build tab turns them
  off and greys them out with the reason; :func:`problems` (called by ``mod_build.validate_plan``, so every build path
  and Check my project use it) refuses a 64 MB plan that still has one, roster edits that grow the roster file, or a
  selection the memory model says will not fit, and names what to turn off.
* The memory model is ``nfl2k5_memory_budget`` (job b780-m64a): ``REQUIRES_128``, ``option_costs``, ``predict`` and
  ``recommended_64_profile``. Its numbers are modelled, not measured on a console, so the Studio calls them an
  estimate. Without that module the 64 MB target keeps the rules below and makes no fit prediction.

The 64 MB build is experimental, estimated, not yet tested on a real Xbox or hakuX (``STATUS_64``, the label the
coordinator set). A selection the model says fits only with the default uniforms builds with a warning
(``ALLOW_ALTERNATE_KIT_SHORTFALL``, coordinator 11/03: option b). The full experience is xemu at 128 MB.
"""

from __future__ import annotations

import importlib
import json
import math
import threading
from dataclasses import MISSING, fields, replace
from pathlib import Path
from typing import Any, Callable, Mapping

FIELD = "console_memory"
DEFAULT = 128
CHOICES = (128, 64)
CAPTION = "Console memory"
#: How the whole 64 MB target is labelled everywhere (coordinator, 11/03).
STATUS_64 = "experimental, estimated, not yet tested on a real Xbox or hakuX"
LABELS = {128: "128 MB, xemu (full SOFTDRINK)",
          64: f"64 MB, original Xbox and Android hakuX ({STATUS_64})"}
SHORT = {128: "128 MB (xemu)", 64: "64 MB (experimental)"}
EVIDENCE_WORD = "estimate"
#: The fit rule (coordinator's call, b780-m64b). The model's hardest game includes uniforms a player picks (an alternate
#: kit at the heaviest stadium). True: a selection that fits with the default uniforms (the CPU's own, style 0) builds,
#: with a warning that a player-picked alternate kit at that stadium may not fit; False: any shortfall refuses.
ALLOW_ALTERNATE_KIT_SHORTFALL = True
HELP_TEXT = (
    "Which machine the disc is made for. 128 MB, xemu (full SOFTDRINK) is the default and the main build: every option, "
    "for xemu with System Memory set to 128 MiB and the Complex 4627 BIOS. 64 MB is for an original Xbox console and the "
    f"Android emulator hakuX: {STATUS_64}. It leaves out every option that needs 128 MB or the real Xbox kernel, "
    "shows what each remaining option costs in memory (an estimate from the memory model), and refuses a selection the "
    "model says will not fit. For the full experience use xemu at 128 MB.")
NOTE_128 = ("128 MB is the full SOFTDRINK build for xemu (System Memory 128 MiB, Complex 4627 BIOS) with every option. "
            "It is the default.")
NOTE_64 = (f"The 64 MB build is {STATUS_64}. Options that need 128 MB or the real Xbox kernel are off and greyed out "
           "below, with the reason; the start-up checks for 128 MB and the 4627 BIOS are left out too. The remaining "
           "options show what they cost in memory (estimates); pick what to drop until the line below says it fits. For "
           "the full experience use xemu at 128 MB.")
RECOMMENDED_BUTTON = "Use the recommended 64 MB set"
CHECKING = "Checking the 64 MB memory budget for this selection (the estimate takes a few seconds)."
NO_ESTIMATE = ("The memory model could not estimate this selection, so the Studio cannot predict whether it fits in 64 MB. "
               "For the full experience use xemu at 128 MB.")
#: The warning of a selection that fits with the default uniforms only (coordinator's wording, 11/03).
ALTERNATE_KIT_WARNING = ("A player-picked alternate kit at {stadium} may not fit ({short} KB short); if a game loops on the "
                         "stadium shots, use the default uniforms.")
RECOMMENDED_HELP = ("Applies the recommended 64 MB selection from the memory model: it turns off the options that cost the "
                    "most memory and keeps the rest of your choices. Review the list before Make my disc.")
#: The badge of an option the 64 MB target turns off ("Off at 64 MB: <reason>").
LOCK_PREFIX = "Off at 64 MB: "
NEXT_STEPS_64 = (f"This is the 64 MB build for an original Xbox or the Android emulator hakuX: {STATUS_64}. To try it in "
                 "xemu the way a console runs it, set System Memory to 64 MiB; for the full SOFTDRINK experience build the "
                 "128 MB target and play it in xemu at 128 MiB.")
SHARE_NOTE = ("The ready-made SOFTDRINK 2K28 pack is the full 128 MB build for xemu (System Memory 128 MiB). For the "
              f"64 MB build (original Xbox, Android hakuX; {STATUS_64}): choose Customize SOFTDRINK 2K28 "
              "with Build for: 64 MB, then make the disc on the Build tab, which starts from the recommended 64 MB set. That "
              "route keeps the pack's art, the options that fit and the 2026 rosters, fitted to the original game's roster "
              "size (free agents beyond the original game's count are left out).")
SHARE_CHOICE_CAPTION = "Build for"
SHARE_CHOICE_HELP = ("Customize SOFTDRINK 2K28 loads the pack's sources into the Build tab. 64 MB sets the Build tab's "
                     "Console memory to the experimental 64 MB target and turns off what needs 128 MB.")

# Options that need 128 MB or the real 4627 Xbox kernel. ``nfl2k5_memory_budget.REQUIRES_128`` (the memory model)
# adds to these and its wording wins; these stay so the target is safe without the model. Reasons are plain, short
# and finish the sentence "Off at 64 MB: ...".
_KERNEL_REASON = ("it needs xemu at 128 MB and the real Xbox kernel: it teaches the 4627 kernel the upper 64 MB, "
                  "which a console does not have and hakuX does not run")
_PREGAME_REASON = ("it needs 128 MB: at 64 MB a disc with it fails at the pregame intro (lab bisect); on a 128 MB "
                   "build the start-up check stops it with a message instead")
OWN_REQUIRES_128 = {
    "k128_memory": _KERNEL_REASON,
    "k128_roster_heap": "it needs the 128 MB memory option (the extra memory above 64 MB)",
    "k128_early": "it needs the 128 MB memory option (the extra memory above 64 MB)",
    "guardian_overlay": _PREGAME_REASON,
    "reserves_16": _PREGAME_REASON,
    "created_teams_extra": _PREGAME_REASON,
}
#: The badge's few words for the options this module knows (the model's fuller reason goes in the tooltip).
BADGE_REASONS = {
    "k128_memory": "needs xemu at 128 MB and the real Xbox kernel",
    "k128_roster_heap": "needs the memory above 64 MB",
    "k128_early": "needs xemu at 128 MB",
    "guardian_overlay": "needs 128 MB",
    "reserves_16": "needs 128 MB",
    "created_teams_extra": "needs 128 MB",
    "hires_pack": "needs 128 MB (2x textures)",
}
#: Requirement keys that are not one switch: the roster edits' free-agent capacity growth (the bigger roster file).
CAPACITY_KEYS = ("roster_capacity", "free_agent_capacity")
CAPACITY_REASON = ("they grow the roster file (the bigger free-agent pool), which needs the 128 MB build: at 64 MB a disc "
                   "with the bigger roster fails at the pregame intro")
#: Coordinator, 11/03 ("ship a version that at least has the updated rosters"): a 64 MB build fits roster edits that grow
#: the roster file to the original game's roster size instead of refusing them.
ROSTER_FIT_NOTE = ("At 64 MB the roster edits are fitted to the original game's roster size, so the 2026 rosters stay. "
                   "Dropped: the free agents beyond the original game's count; franchise draft-pick ownership and the "
                   "backfield labels fall back to the 2004 game's, and the Player Card champions page starts empty.")
_CAPTIONS = {
    "k128_memory": "128 MB memory (K128, xemu set to 128 MB)",
    "k128_roster_heap": "Roster block in the extra memory",
    "k128_early": "Bigger graphics memory (K128 early form)",
    "guardian_overlay": "Guardian caps (experimental)",
    "reserves_16": "16 reserves (experimental)",
    "created_teams_extra": "Two extra created teams (experimental)",
    "roster_edits": "Include exported ★ Rosters edits",
}

Labeller = Callable[[str], str]


# ------------------------------------------------------------------------------------------------ the memory model
def model():
    """The memory model module (``nfl2k5_memory_budget``), or None while it is not in this build."""

    try:
        return importlib.import_module("mod_editor.core.nfl2k5_memory_budget")
    except Exception:  # noqa: BLE001 - an absent or broken model never breaks the Build tab
        return None


def _plan_fields() -> dict[str, Any]:
    from .mod_build import BuildPlan
    return {item.name: item for item in fields(BuildPlan)}


def normalize(value: object) -> int:
    """128 or 64, or ValueError (``True``/``False`` are not memory sizes)."""

    if type(value) is not int or value not in CHOICES:
        raise ValueError(f"Console memory must be 128 or 64 (MB), not {value!r}")
    return value


def of(plan: object) -> int:
    """The plan's console memory (128 for an older plan, recipe or project that has none)."""

    if isinstance(plan, Mapping):
        overrides = plan.get("overrides")
        value = (overrides.get(FIELD) if isinstance(overrides, Mapping) and FIELD in overrides
                 else plan.get(FIELD, DEFAULT))
    else:
        value = getattr(plan, FIELD, DEFAULT)
    return value if type(value) is int and value in CHOICES else DEFAULT


def is_on(plan: object, key: str) -> bool:
    """True when the plan asks for this option (a ticked box, a non-zero count, a path, a non-retail level)."""

    value = getattr(plan, key, None)
    return bool(value) and value != "retail"


def off_value(key: str):
    """The value that turns an option off: its default when that is already off, otherwise its type's off value."""

    item = _plan_fields().get(key)
    if item is None:
        return False
    if item.default is not MISSING:
        default = item.default
    elif item.default_factory is not MISSING:
        default = item.default_factory()
    else:
        default = None
    if not (bool(default) and default != "retail"):
        return default
    if isinstance(default, bool):
        return False
    if isinstance(default, int):
        return 0
    if isinstance(default, str):
        return ""
    return None


def requires_128() -> dict[str, str]:
    """Option -> reason for every BuildPlan option the 64 MB target turns off (the model's list and wording win)."""

    rules = dict(OWN_REQUIRES_128)
    found = getattr(model(), "REQUIRES_128", None)
    if callable(found):
        try:
            found = found()
        except Exception:  # noqa: BLE001
            found = None
    if isinstance(found, Mapping):
        known = _plan_fields()
        for key, reason in found.items():
            if key in known and key != "roster_edits" and str(reason).strip():
                rules[str(key)] = _reason_text(reason)
    return rules


def capacity_reason() -> str:
    """Why roster edits that grow the roster file cannot go on a 64 MB build (the model's words when it has them)."""

    found = getattr(model(), "REQUIRES_128", None)
    if isinstance(found, Mapping):
        for key in (*CAPACITY_KEYS, "roster_edits"):
            if str(found.get(key, "")).strip():
                return _reason_text(found[key])
    return CAPACITY_REASON


def _reason_text(reason: object) -> str:
    text = " ".join(str(reason).split()).rstrip(".")
    return text[:1].lower() + text[1:] if text[:2] != text[:2].upper() else text


def lock_badge(reason: str, key: str | None = None) -> str:
    """'Off at 64 MB: needs 128 MB': the badge of an option the 64 MB target turned off."""

    return LOCK_PREFIX + badge_reason(reason, key)


def badge_reason(reason: str, key: str | None = None) -> str:
    """The badge's few words (this module's for the options it knows, else the reason's first clause)."""

    return BADGE_REASONS.get(key or "") or _short_reason(reason)


def _short_reason(reason: str) -> str:
    """The reason's first clause; the whole reason goes in the tooltip."""

    text = _reason_text(reason).split(". ", 1)[0].removeprefix("it ")
    for stop in (":", ";", " ("):
        if stop in text:
            text = text.split(stop, 1)[0]
    return text.strip().rstrip(".")


def label(key: str, labels: Mapping[str, str] | Labeller | None = None) -> str:
    if callable(labels):
        try:
            found = labels(key)
        except Exception:  # noqa: BLE001
            found = ""
        if found:
            return str(found)
    elif isinstance(labels, Mapping) and labels.get(key):
        return str(labels[key])
    return _CAPTIONS.get(key) or key.replace("_", " ").capitalize()


def forced_off(plan: object) -> list[tuple[str, str]]:
    """(option, reason) for every option the plan has on that a 64 MB build cannot carry."""

    return [(key, reason) for key, reason in requires_128().items() if is_on(plan, key)]


def without_forced(plan):
    """The plan with every 64 MB forced-off option off (a 128 plan comes back unchanged). Roster edits stay: a 64 MB
    build fits ones that grow the roster file to the original size (``model_plan``, ``fit_roster_edits``)."""

    if of(plan) != 64:
        return plan
    changes = {key: off_value(key) for key, _ in forced_off(plan)}
    return replace(plan, **changes) if changes else plan


# ------------------------------------------------------------------------------------------------ costs and the fit
def identity(plan: object) -> str:
    """One string per selection the model could answer differently (the recipe, and the roster edits file's stamp)."""

    recipe = plan.to_recipe() if hasattr(plan, "to_recipe") else plan
    path = str(getattr(plan, "roster_edits", "") or (recipe.get("roster_edits", "") if isinstance(recipe, Mapping) else ""))
    try:
        stat = Path(path).stat() if path else None
        stamp = (stat.st_mtime_ns, stat.st_size) if stat else None
    except OSError:
        stamp = None
    return json.dumps([recipe, stamp], sort_keys=True, default=str)


_ANSWERS: dict[tuple, Any] = {}      # (model module, call, identity) -> answer; a few recent selections
_ANSWERS_LOCK = threading.Lock()     # the Build tab asks from a worker thread


def _remember(kind: str, plan: object, compute):
    module = model()
    if plan is None:
        return compute()
    key = (module, kind, identity(plan))
    with _ANSWERS_LOCK:
        if key in _ANSWERS:
            _ANSWERS[key] = _ANSWERS.pop(key)       # most recent last
            return _ANSWERS[key]
    answer = compute()
    with _ANSWERS_LOCK:
        _ANSWERS[key] = answer
        while len(_ANSWERS) > 16:
            _ANSWERS.pop(next(iter(_ANSWERS)))
    return answer


def option_costs(plan: object = None) -> dict[str, int]:
    """Option -> bytes at 64 MB from the model: what turning each option that is on would free (with no plan: the
    model's own reference plan, the SOFTDRINK pack)."""

    found = getattr(model(), "option_costs", None)
    if not callable(found):
        return {}
    return dict(_remember("costs", plan, lambda: _option_costs(found, plan)))


def _option_costs(found, plan) -> dict[str, int]:
    try:
        try:
            costs = found(plan, target_mb=64)
        except TypeError:
            costs = found(plan)
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(costs, Mapping):
        return {}
    out = {}
    for key, value in costs.items():
        try:
            out[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return out


def predict(plan: object) -> dict[str, Any] | None:
    """The model's 64 MB prediction for this plan, normalised, or None when there is no model.

    ``{"fits", "spare_bytes", "over_bytes", "hardest", "suggestions": [(option, bytes)], "evidence"}``."""

    found = getattr(model(), "predict", None)
    if not callable(found):
        return None
    answer = _remember("predict", plan, lambda: _predict(found, plan))
    return dict(answer) if answer is not None else None


def _predict(found, plan) -> dict[str, Any] | None:
    try:
        try:
            raw = found(plan, target_mb=64)
        except TypeError:
            raw = found(plan)
    except Exception:  # noqa: BLE001 - a model that cannot read this plan gives no prediction, never a crash
        return None
    if raw is None:
        return None
    get = raw.get if isinstance(raw, Mapping) else (lambda key, default=None: getattr(raw, key, default))
    spare = int(get("spare_bytes", 0) or 0)
    over = int(get("over_bytes", 0) or 0)
    fits = get("fits", None)
    fits = bool(fits) if fits is not None else over <= 0
    suggestions = []
    for row in get("suggestions", ()) or ():
        try:
            key, size = (row["field"], row["bytes"]) if isinstance(row, Mapping) else row
            suggestions.append((str(key), int(size)))
        except (KeyError, TypeError, ValueError):
            continue
    primary = get("primary_uniforms", None)
    safety = get("safety_bytes", None)
    primary_fits, primary_spare, primary_where = None, 0, ""
    if isinstance(primary, Mapping) and type(primary.get("margin")) is int and type(safety) is int:
        primary_fits = primary["margin"] >= safety
        primary_spare = max(primary["margin"] - safety, 0)
        primary_where = str(primary.get("hardest", "") or "")
    return {"fits": fits, "spare_bytes": max(spare, 0), "over_bytes": max(over, 0),
            "hardest": str(get("hardest", "") or ""), "suggestions": suggestions,
            "evidence": str(get("evidence", "MODELLED") or "MODELLED"),
            "primary_fits": primary_fits, "primary_spare_bytes": primary_spare, "primary_hardest": primary_where}


def alternate_kit_shortfall(prediction: Mapping[str, Any] | None) -> bool:
    """True when the selection fits with the default uniforms and only a player-picked alternate kit falls short."""

    return bool(prediction) and not prediction.get("fits") and prediction.get("primary_fits") is True


def alternate_kit_warning(prediction: Mapping[str, Any]) -> str:
    """'A player-picked alternate kit at NRG Stadium (s37) may not fit (55 KB short); if a game loops ...'."""

    return ALTERNATE_KIT_WARNING.format(stadium=prediction.get("hardest") or "the heaviest stadium",
                                        short=f"{kb_up(int(prediction.get('over_bytes', 0))):,}")


def refuses(prediction: Mapping[str, Any] | None) -> bool:
    """Whether Make my disc refuses this prediction (see ALLOW_ALTERNATE_KIT_SHORTFALL)."""

    if not prediction or prediction.get("fits"):
        return False
    return not (ALLOW_ALTERNATE_KIT_SHORTFALL and alternate_kit_shortfall(prediction))


def kb_up(size: int) -> int:
    return int(math.ceil(max(size, 0) / 1024))


def kb_down(size: int) -> int:
    return int(max(size, 0) // 1024)


def cost_text(size: int) -> str:
    """'Memory at 64 MB: 12 KB (estimate)'; under 1 KB reads 'under 1 KB', nothing reads 'none'."""

    amount = "none" if size <= 0 else "under 1 KB" if size < 1024 else f"{kb_up(size):,} KB"
    return f"Memory at 64 MB: {amount} ({EVIDENCE_WORD})"


def _examples(prediction: Mapping[str, Any], labels=None, *, limit: int = 5) -> list[str]:
    """The model's suggestions, enough of them to cover the shortfall (at most ``limit``). A suggestion of 0 bytes is
    a sub-option that goes with the one before it ("Scorebug (391 KB, with Scorebug effects)")."""

    over = int(prediction.get("over_bytes", 0))
    rows: list[list] = []
    covered, more = 0, 0
    for key, size in prediction.get("suggestions", ()):
        if size <= 0:
            if rows and not more:
                rows[-1][2].append(label(key, labels))
            continue
        if covered >= over:
            break
        if len(rows) >= limit:
            more += 1
            continue
        rows.append([label(key, labels), size, []])
        covered += size
    named = [f"{name} ({kb_up(size):,} KB" + (", with " + ", ".join(extra) if extra else "") + ")"
             for name, size, extra in rows]
    if more:
        named.append(f"and {more} more")
    return named


def _covered(prediction: Mapping[str, Any]) -> bool:
    """Whether the model's suggestions, taken together, free the whole shortfall."""

    return sum(max(size, 0) for _key, size in prediction.get("suggestions", ())) >= int(prediction.get("over_bytes", 0))


def budget_line(prediction: Mapping[str, Any] | None, labels=None) -> str:
    """The Build tab's one line about the 64 MB fit (see the brief's wording)."""

    if prediction is None:
        return ("No memory model is in this build, so the Studio cannot predict whether this selection fits in 64 MB. "
                f"The 64 MB build is {STATUS_64}; for the full experience use xemu at 128 MB.")
    where = prediction.get("hardest") or ""
    where = f", {where}" if where else ""
    tail = (" This is an estimate from the memory model, not a measurement on a console."
            if str(prediction.get("evidence", "MODELLED")).upper() != "MEASURED" else "")
    if prediction.get("fits"):
        return (f"Predicted to fit with {kb_down(int(prediction.get('spare_bytes', 0))):,} KB to spare at the hardest "
                f"stadium{where}.{tail}")
    if alternate_kit_shortfall(prediction):
        primary_where = prediction.get("primary_hardest") or ""
        primary_where = f", {primary_where}" if primary_where else ""
        line = (f"Predicted to fit with the default uniforms ({kb_down(int(prediction.get('primary_spare_bytes', 0))):,} "
                f"KB to spare at the hardest stadium{primary_where}). " + alternate_kit_warning(prediction))
        if not ALLOW_ALTERNATE_KIT_SHORTFALL:
            line = "Will not fit with every uniform. " + line
        return line + tail
    examples = _examples(prediction, labels)
    line = f"Will not fit: remove {kb_up(int(prediction.get('over_bytes', 0))):,} KB (hardest stadium{where})"
    line += ("; for example turn off " + ", ".join(examples) + ".") if examples else "."
    if not _covered(prediction):
        line += (" No single option frees the rest: several have to go together, which Use the recommended 64 MB set "
                 "does.")
    return line + tail


# ------------------------------------------------------------------------------------------------ refusals
def capacity_records(plan: object) -> int:
    """Records the plan's roster edits add to the roster file (free-agent capacity growth), or 0."""

    return _roster_facts(str(getattr(plan, "roster_edits", "") or ""))["records"]


def roster_fit_applies(plan: object) -> bool:
    """A 64 MB plan whose roster edits grow the roster file: the build fits them to the original roster size."""

    return of(plan) == 64 and capacity_records(plan) > 0


def roster_fit_problem(plan: object) -> str:
    """Why these roster edits cannot be fitted to the original roster size (the document's own checks), or ""."""

    return _roster_facts(str(getattr(plan, "roster_edits", "") or ""))["fit_problem"]


_ROSTER_FACTS: dict[tuple[str, int, int], dict[str, Any]] = {}


def _roster_facts(path: str) -> dict[str, Any]:
    """{"records": capacity growth, "fit_problem": "" or why the retail fit refuses the document}, cached per file."""

    empty = {"records": 0, "fit_problem": ""}
    if not path:
        return empty
    try:
        stat = Path(path).stat()
    except OSError:
        return empty
    key = (path, stat.st_mtime_ns, stat.st_size)
    if key not in _ROSTER_FACTS:
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8-sig"))   # b780-uxfix: a Notepad BOM is fine
        except (OSError, ValueError):
            document = None
        request = document.get("free_agent_capacity") if isinstance(document, dict) else None
        value = request.get("records", 0) if isinstance(request, dict) else 0
        records = value if type(value) is int and value > 0 else 0
        _ROSTER_FACTS.clear()
        _ROSTER_FACTS[key] = {"records": records, "fit_problem": _fit_problem(document) if records else ""}
    return _ROSTER_FACTS[key]


def retail_fit():
    """M64A's roster fit (tools/nfl2k5_roster_retail_fit.py), imported as a library, or None if this build lacks it."""

    try:
        return importlib.import_module("tools.nfl2k5_roster_retail_fit")
    except Exception:  # noqa: BLE001 - a tree run with tools/ on the path instead of the repository root
        try:
            return importlib.import_module("nfl2k5_roster_retail_fit")
        except Exception:  # noqa: BLE001
            return None


def _fit_problem(document) -> str:
    """The retail fit's document checks (no roster needed): a dated refresh whose only rows in appended records are the
    dated free agents (signed ones included). "" when the build can fit it."""

    module = retail_fit()
    if module is None:
        return "this Studio has no roster fit (tools/nfl2k5_roster_retail_fit.py)"
    try:
        module.require(isinstance(document, dict) and isinstance(document.get("roster_refresh"), dict),
                       "the document has no dated roster refresh to fit")
        module.pinned_depth(document)
        module.depth_rows(document["roster_refresh"])
    except Exception as exc:  # noqa: BLE001 - every refusal is shown to the user as the reason
        return str(exc) or exc.__class__.__name__
    return ""


def fit_roster_edits(document: Mapping[str, Any], base: bytes, *, source_sha256: str = "") -> tuple[dict, dict]:
    """The roster edits at the original (retail) roster size for a 64 MB build: M64A's retail_variant, the way the
    release 64 MB file was made (signed depth free agents kept, the capacity block, the free agents beyond the original
    game's count and the draft_pick_ownership and hback_roles sections dropped). ``base`` is the main roster this build
    has made from the user's own disc, right before the dated refresh; it replaces the authoring base the document
    pins, so the fit is decided on the roster the refresh will really be written into. Raises when the fit refuses."""

    module = retail_fit()
    if module is None:
        raise ValueError("this Studio has no roster fit (tools/nfl2k5_roster_retail_fit.py)")
    unpinned = dict(document)
    for key in ("fa3_free_agent_depth", "free_agent_capacity"):
        block = unpinned.get(key)
        if isinstance(block, dict) and "base_sha256" in block:
            unpinned[key] = {k: v for k, v in block.items() if k != "base_sha256"}
    return module.retail_variant(unpinned, bytes(base), source_sha256=source_sha256, drop_xbe_sections=True)


def roster_fit_note(receipt: Mapping[str, Any] | None = None) -> str:
    """What the 64 MB build drops from roster edits that grow the roster file (with the counts once fitted)."""

    if not receipt:
        return ROSTER_FIT_NOTE
    kept, candidates = int(receipt.get("depth_kept", 0)), int(receipt.get("depth_candidates", 0))
    signed = len(receipt.get("signed_depth_kept") or [])
    return (ROSTER_FIT_NOTE + f" This build keeps {kept} of the {candidates} dated free agents"
            + (f" ({signed} of them signed to clubs)" if signed else "") + ".")


def model_plan(plan):
    """The plan as the memory model should see a 64 MB build of it: the forced-off options off and, when the build fits
    the roster edits to the original roster size, no capacity growth and no draft-pick or backfield sections."""

    plan = without_forced(plan)
    if of(plan) != 64 or not roster_fit_applies(plan):
        return plan
    flat = {item.name: getattr(plan, item.name) for item in fields(plan)}
    flat.update(roster_capacity=False, roster_draft_pick_ownership=False, roster_hback_roles=False)
    return flat


def problems(plan: object, labels=None, *, records: int | None = None, fit: bool = True) -> list[str]:
    """Why this 64 MB plan cannot be built, each sentence naming what to turn off; [] for a 128 plan or a plan that fits.

    ``records`` is the roster edits' capacity growth when the caller already read it; ``fit`` asks the memory model
    (after the forced-off options are counted as off, so its shortfall is about what the user can still choose)."""

    if of(plan) != 64:
        return []
    out = []
    blocked = forced_off(plan)
    if blocked:
        out.append("The 64 MB build cannot include "
                   + "; ".join(f"{label(key, labels)} ({badge_reason(reason, key)})" for key, reason in blocked)
                   + ". Turn " + ("it" if len(blocked) == 1 else "them") + " off, or choose Console memory 128 MB "
                   "(xemu, full SOFTDRINK).")
    grown = capacity_records(plan) if records is None else records
    problem = roster_fit_problem(plan) if grown else ""
    if problem:
        name = Path(str(getattr(plan, "roster_edits", "") or "")).name or "the roster edits"
        out.append(f"The 64 MB build cannot fit the roster edits {name} to the original game's roster size "
                   f"({grown:,} more records asked for): {_reason_text(problem)}. Untick Include exported \u2605 Rosters "
                   "edits, or choose Console memory 128 MB.")
    if fit:
        prediction = predict(model_plan(plan))
        if prediction is not None and refuses(prediction):
            out.append(refusal(prediction, labels))
    return out


def refusal(prediction: Mapping[str, Any], labels=None) -> str:
    """The refusal of a selection the model says will not fit, naming what to turn off."""

    return "The 64 MB build will not fit: " + budget_line(prediction, labels).removeprefix("Will not fit: ")


# ------------------------------------------------------------------------------------------------ the recommended set
def recommended_profile(plan: object = None) -> dict[str, Any]:
    """The model's recommended 64 MB selection for this plan (option -> value), with the forced-off options off and the
    64 MB target; only those two without a model."""

    found = getattr(model(), "recommended_64_profile", None)
    profile: dict[str, Any] = {}
    if callable(found):
        try:
            try:
                raw = found(plan) if plan is not None else found()
            except TypeError:
                raw = found()
        except Exception:  # noqa: BLE001
            raw = None
        if isinstance(raw, Mapping):
            raw = raw.get("overrides", raw) if isinstance(raw.get("overrides"), Mapping) else raw
            known = _plan_fields()
            profile = {str(key): value for key, value in raw.items() if key in known and key not in ("source", "target")}
    for key in requires_128():
        profile[key] = off_value(key)
    profile[FIELD] = 64
    return profile
