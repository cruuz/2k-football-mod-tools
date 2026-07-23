"""Typed errors suitable for either a GUI or command-line front end."""


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
