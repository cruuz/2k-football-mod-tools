"""APF 2K8 Mod Studio product package.

The package contains no game assets.  Every catalog and preview is generated
from a user-owned All-Pro Football 2K8 game image or extracted game directory.
"""

from .models import (
    ApfAsset,
    ApfCategory,
    ApfSource,
    ApfStatus,
    UniformAsset,
)

__version__ = "0.1.0-alpha.68"

__all__ = [
    "ApfAsset",
    "ApfCategory",
    "ApfSource",
    "ApfStatus",
    "UniformAsset",
    "__version__",
]
