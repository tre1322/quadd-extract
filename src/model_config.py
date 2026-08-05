"""
model_config.py

Single source of truth for which Anthropic model this app calls.

Anthropic retires dated model IDs over time. When that happens, every hardcoded
call site starts failing with:

    404 not_found_error: model: <id>

which surfaces in the UI as "Transformation failed: Error code: 404 ...".

Keeping the ID in one place means a retirement is a one-line env change on the
deployment rather than a code edit across every call site.

Verify which IDs are currently live with:

    curl https://api.anthropic.com/v1/models \
      -H "x-api-key: $ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01"
"""

from __future__ import annotations

import os
from typing import Optional

# Default used when no environment override is set.
DEFAULT_CLAUDE_MODEL = "claude-sonnet-5"


def resolve_model(model: Optional[str] = None) -> str:
    """
    Resolve the Anthropic model ID: explicit argument > environment > default.

    Both ANTHROPIC_MODEL (documented in README.md) and CLAUDE_MODEL (documented
    in .env.example) are honored, because this repo documents both names --
    reading only one would leave the other silently ineffective.

    Blank or whitespace-only values are treated as unset, so an empty Railway
    variable cannot quietly resurrect a stale default.
    """
    for candidate in (model, os.getenv("ANTHROPIC_MODEL"), os.getenv("CLAUDE_MODEL")):
        if candidate and candidate.strip():
            return candidate.strip()
    return DEFAULT_CLAUDE_MODEL
