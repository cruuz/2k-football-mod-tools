"""The console memory a build is made for (b780-m64b): 128 MB for xemu, or an EXPERIMENTAL 64 MB build.

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

The 64 MB build is EXPERIMENTAL and UNTESTED on a real Xbox and in hakuX. The full experience is xemu at 128 MB.
"""

from __future__ import annotations

import importlib
import json
import math
from dataclasses import MISSING, fields, replace
from pathlib import Path
from typing import Any, Callable, Mapping

FIELD = "console_memory"
DEFAULT = 128
CHOICES = (128, 64)
CAPTION = "Console memory"
LABELS = {128: "128 MB, xemu (full SOFTDRINK)",
          64: "64 MB, original Xbox and Android hakuX (experimental)"}
SHORT = {128: "128 MB (xemu)", 64: "64 MB (experimental)"}
EVIDENCE_WORD = "estimate"
HELP_TEXT = (
    "Which machine the disc is made for. 128 MB, xemu (full SOFTDRINK) is the default and the main build: every option, "
    "for xemu with System Memory set to 128 MiB and the Complex 4627 BIOS. 64 MB is for an original Xbox console and the "
    "Android emulator hakuX. It is EXPERIMENTAL and untested on a real Xbox and in hakuX: it leaves out every option "
    "that needs 128 MB or the real Xbox kernel, shows what each remaining option costs in memory, and refuses a "
    "selection the memory model says will not fit. For the full experience use xemu at 128 MB.")
NOTE_128 = ("128 MB is the full SOFTDRINK build for xemu (System Memory 128 MiB, Complex 4627 BIOS) with every option. "
            "It is the default.")
NOTE_64 = ("EXPERIMENTAL: the 64 MB build is untested on a real Xbox and in hakuX. Options that need 128 MB or the real "
           "Xbox kernel are off and greyed out below, with the reason; the start-up checks for 128 MB and the 4627 BIOS "
           "are left out too. The remaining options show what they cost in memory; pick what to drop until the line "
           "below says it fits. For the full experience use xemu at 128 MB.")
RECOMMENDED_BUTTON = "Use the recommended 64 MB set"
RECOMMENDED_HELP = ("Applies the recommended 64 MB selection from the memory model: it turns off the options that cost the "
                    "most memory and keeps the rest of your choices. Review the list before Make my disc.")
#: The badge of an option the 64 MB target turns off ("Off at 64 MB: <reason>").
LOCK_PREFIX = "Off at 64 MB: "
NEXT_STEPS_64 = ("This is the EXPERIMENTAL 64 MB build, for an original Xbox or the Android emulator hakuX. It is untested "
                 "on both. To try it in xemu the way a console runs it, set System Memory to 64 MiB; for the full "
                 "SOFTDRINK experience build the 128 MB target and play it in xemu at 128 MiB.")
SHARE_NOTE = ("The ready-made SOFTDRINK 2K28 pack is the full 128 MB build for xemu (System Memory 128 MiB). For the "
              "EXPERIMENTAL 64 MB build (original Xbox, Android hakuX; untested on both): choose Customize SOFTDRINK 2K28 "
              "with Build for: 64 MB, then make the disc on the Build tab. That route keeps the pack's art and the options "
              "that fit; the pack's 2026 rosters need 128 MB for now.")
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
#: Requirement keys that are not one switch: the roster edits' free-agent capacity growth (the bigger roster file).
CAPACITY_KEYS = ("roster_capacity", "free_agent_capacity")
CAPACITY_REASON = ("they grow the roster file (the bigger free-agent pool), which needs the 128 MB build: at 64 MB a disc "
                   "with the bigger roster fails at the pregame intro")
_CAPTIONS = {
    "k128_memory": "128 MB memory (K128, xemu set to 128 MB)",
    "k128_roster_heap": "Roster block in the extra memory",
    "k128_early": "Bigger graphics memory (K128 early form)",
    "guardian_overlay": "Guardian caps (experimental)",
    "reserves_16": "16 reserves (experimental)",
    "created_teams_extra": "Two extra created teams (experimental)",
    "roster_edits": "Include exported Rosters edits",
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


def lock_badge(reason: str) -> str:
    return LOCK_PREFIX + _short_reason(reason)


def _short_reason(reason: str) -> str:
    """The badge's few words; the whole reason goes in the tooltip."""

    text = reason.removeprefix("it ")
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
    """A copy of the plan with every 64 MB forced-off option turned off (a 128 plan comes back unchanged)."""

    if of(plan) != 64:
        return plan
    changes = {key: off_value(key) for key, _ in forced_off(plan)}
    return replace(plan, **changes) if changes else plan


# ------------------------------------------------------------------------------------------------ costs and the fit
def option_costs(plan: object = None) -> dict[str, int]:
    """Option -> bytes at 64 MB from the model (every costed option with no plan; the options that are on with one)."""

    found = getattr(model(), "option_costs", None)
    if not callable(found):
        return {}
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
    return {"fits": fits, "spare_bytes": max(spare, 0), "over_bytes": max(over, 0),
            "hardest": str(get("hardest", "") or ""), "suggestions": suggestions,
            "evidence": str(get("evidence", "MODELLED") or "MODELLED")}


def kb_up(size: int) -> int:
    return int(math.ceil(max(size, 0) / 1024))


def kb_down(size: int) -> int:
    return int(max(size, 0) // 1024)


def cost_text(size: int) -> str:
    """'Memory at 64 MB: 12 KB (estimate)'; under 1 KB reads 'under 1 KB', nothing reads 'none'."""

    amount = "none" if size <= 0 else "under 1 KB" if size < 1024 else f"{kb_up(size):,} KB"
    return f"Memory at 64 MB: {amount} ({EVIDENCE_WORD})"


def _examples(prediction: Mapping[str, Any], labels=None, *, limit: int = 4) -> list[str]:
    """The model's suggestions, enough of them to cover the shortfall (at most ``limit``)."""

    over = int(prediction.get("over_bytes", 0))
    named, covered = [], 0
    for key, size in prediction.get("suggestions", ()):
        named.append(f"{label(key, labels)} ({kb_up(size):,} KB)")
        covered += size
        if covered >= over or len(named) >= limit:
            break
    return named


def budget_line(prediction: Mapping[str, Any] | None, labels=None) -> str:
    """The Build tab's one line about the 64 MB fit (see the brief's wording)."""

    if prediction is None:
        return ("No memory model is in this build, so the Studio cannot predict whether this selection fits in 64 MB. "
                "The 64 MB build is untested; for the full experience use xemu at 128 MB.")
    where = prediction.get("hardest") or ""
    where = f", {where}" if where else ""
    tail = (" This is an estimate from the memory model, not a measurement on a console."
            if str(prediction.get("evidence", "MODELLED")).upper() != "MEASURED" else "")
    if prediction.get("fits"):
        return (f"Predicted to fit with {kb_down(int(prediction.get('spare_bytes', 0))):,} KB to spare at the hardest "
                f"stadium{where}.{tail}")
    examples = _examples(prediction, labels)
    line = f"Will not fit: remove {kb_up(int(prediction.get('over_bytes', 0))):,} KB (hardest stadium{where})"
    line += ("; for example turn off " + ", ".join(examples) + ".") if examples else "."
    return line + tail


# ------------------------------------------------------------------------------------------------ refusals
def capacity_records(plan: object) -> int:
    """Records the plan's roster edits add to the roster file (free-agent capacity growth), or 0."""

    path = str(getattr(plan, "roster_edits", "") or "")
    if not path:
        return 0
    return _capacity_of(path)


_CAPACITY_CACHE: dict[tuple[str, int, int], int] = {}


def _capacity_of(path: str) -> int:
    try:
        stat = Path(path).stat()
    except OSError:
        return 0
    key = (path, stat.st_mtime_ns, stat.st_size)
    if key not in _CAPACITY_CACHE:
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            document = None
        request = document.get("free_agent_capacity") if isinstance(document, dict) else None
        value = request.get("records", 0) if isinstance(request, dict) else 0
        _CAPACITY_CACHE.clear()
        _CAPACITY_CACHE[key] = value if type(value) is int and value > 0 else 0
    return _CAPACITY_CACHE[key]


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
                   + "; ".join(f"{label(key, labels)} ({_short_reason(reason)})" for key, reason in blocked)
                   + ". Turn " + ("it" if len(blocked) == 1 else "them") + " off, or choose Console memory 128 MB "
                   "(xemu, full SOFTDRINK).")
    grown = capacity_records(plan) if records is None else records
    if grown:
        name = Path(str(getattr(plan, "roster_edits", "") or "")).name or "the roster edits"
        out.append(f"The 64 MB build cannot use the roster edits {name}: {capacity_reason()} ({grown:,} more "
                   "records). Untick Include exported Rosters edits, or choose roster edits that do not grow the roster "
                   "file (the SOFTDRINK 2K28 2026 rosters need 128 MB for now).")
    if fit:
        prediction = predict(without_forced(plan))
        if prediction is not None and not prediction["fits"]:
            out.append("The 64 MB build will not fit: " + budget_line(prediction, labels).removeprefix("Will not fit: "))
    return out


# ------------------------------------------------------------------------------------------------ the recommended set
def recommended_profile() -> dict[str, Any]:
    """The model's recommended 64 MB selection (option -> value) with the forced-off options off; {} without a model."""

    found = getattr(model(), "recommended_64_profile", None)
    profile: dict[str, Any] = {}
    if callable(found):
        try:
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
