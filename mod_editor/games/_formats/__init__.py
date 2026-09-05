"""Shared container and format packages that game modules compose.

Nothing under ``_formats`` is a game: discovery skips underscore-prefixed
directories.  A format package wraps one container or one on-disc format --
the PS2 ISO9660 volume and boot identity, the Visual Concepts outer-pack
stack, EA's TDB tables, PS2 memory-card saves -- behind the vocabulary of
:mod:`mod_editor.games.contract`, so that two games that share a stack share
one implementation.  A game imports ``mod_editor.games._formats.<format>``;
it never imports another game.  See ``contract.SHARED_FORMATS_PACKAGE``.
"""
