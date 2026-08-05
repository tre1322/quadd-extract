"""
model_config.py

Shared plumbing for talking to the Anthropic API: which model to call
(resolve_model) and how to read a reply safely (extract_text).

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
from typing import Any, Optional

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


def extract_text(response: Any) -> str:
    """
    Pull the assistant's text out of a Messages API response.

    Do NOT use response.content[0].text. A reply is a LIST of content blocks and
    the first one is not guaranteed to be text -- newer models may lead with a
    'thinking' block, which raises:

        AttributeError: 'ThinkingBlock' object has no attribute 'text'

    Whether a thinking block appears varies with the model and the request, so
    this is a latent 500 rather than a consistent one: the same code can pass a
    short smoke test and fail on a real, longer prompt.

    Concatenates every text block (a reply can legitimately contain more than
    one) and ignores thinking/tool_use/other block types.

    Raises:
        ValueError: if the reply contains no text block at all.
    """
    blocks = getattr(response, "content", None) or []
    parts = [
        block.text
        for block in blocks
        if getattr(block, "type", None) == "text" and getattr(block, "text", None)
    ]

    if not parts:
        seen = [getattr(b, "type", type(b).__name__) for b in blocks]
        raise ValueError(
            f"Anthropic reply contained no text block (got: {seen or 'empty response'}). "
            f"stop_reason={getattr(response, 'stop_reason', 'unknown')}"
        )

    return "".join(parts)
