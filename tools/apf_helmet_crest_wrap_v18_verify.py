#!/usr/bin/env python3
"""Compatibility alias for the promoted public helmet crest verifier."""

from __future__ import annotations

import apf_helmet_crest_wrap_verify as _public
from apf_helmet_crest_wrap_verify import *  # noqa: F401,F403


def __getattr__(name: str):
    return getattr(_public, name)


if __name__ == "__main__":
    raise SystemExit(_public.main())
