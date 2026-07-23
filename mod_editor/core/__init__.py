"""UI-independent model and safety boundary for the mod editor."""

from .capabilities import Capability, CapabilityRegistry, CapabilityRegistryLoader
from .apf_digital_font import create_apf_digital_font_recipe
from .controller import ModEditorController
from .gameplay_inspection import (
    inspect_draft_priority,
    inspect_gameplay_sliders,
    inspect_nfl_franchise_limit,
    inspect_nfl_save_inventory,
)
from .menu_modes import inspect_main_menu
from .presentation_inspection import inspect_apf_scorebug_presentation
from .model import GameId, ModProject, ReplacementItem
from .providers import ProviderOrchestrator, ProviderRequest, ProviderRunResult
from .recipes import (
    RecipeError,
    ScorebugRecipeEdit,
    create_apf_helmet_recipe,
    create_apf_jersey_recipe,
    create_apf_pants_recipe,
    create_apf_shoulder_recipe,
    create_nfl_scorebug_recipe,
)
from .uniform_sharing import (
    inspect_apf_helmet_sharing,
    inspect_apf_jersey_sharing,
    inspect_apf_pants_sharing,
    inspect_apf_shoulder_sharing,
    inspect_nfl_uniform_sharing,
)

__all__ = [
    "Capability",
    "CapabilityRegistry",
    "CapabilityRegistryLoader",
    "GameId",
    "ModEditorController",
    "ModProject",
    "ProviderOrchestrator",
    "ProviderRequest",
    "ProviderRunResult",
    "RecipeError",
    "ReplacementItem",
    "ScorebugRecipeEdit",
    "create_apf_digital_font_recipe",
    "create_apf_helmet_recipe",
    "create_apf_jersey_recipe",
    "create_apf_pants_recipe",
    "create_apf_shoulder_recipe",
    "create_nfl_scorebug_recipe",
    "inspect_draft_priority",
    "inspect_gameplay_sliders",
    "inspect_apf_helmet_sharing",
    "inspect_apf_jersey_sharing",
    "inspect_apf_pants_sharing",
    "inspect_apf_shoulder_sharing",
    "inspect_apf_scorebug_presentation",
    "inspect_main_menu",
    "inspect_nfl_franchise_limit",
    "inspect_nfl_save_inventory",
    "inspect_nfl_uniform_sharing",
]
