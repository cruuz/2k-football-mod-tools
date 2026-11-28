"""Typed errors suitable for either a GUI or command-line front end."""

#: The public community Discord invite (Noah's, 2026-11-18: it opens #2k5-help and does not expire). It is defined once,
#: here, because both Studios and every writer that names Discord in a message already import this module.
#: update_check re-exports it for the Help menus. Change the link here and nowhere else.
COMMUNITY_DISCORD = "https://discord.gg/FkNSKRAKch"


class ModEditorError(Exception):
    """Base class for expected, user-facing editor errors."""


class ValidationError(ModEditorError):
    """Input or project data failed a safety or schema check."""


class RegistryError(ValidationError):
    """The capability registry is absent or malformed."""


class OutputRefusedError(ModEditorError):
    """An output operation was refused before changing a destination."""


class ActionNotImplementedError(ModEditorError):
    """The requested action is intentionally visible but not implemented."""
