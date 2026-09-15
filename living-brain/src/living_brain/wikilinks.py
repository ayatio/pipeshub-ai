"""Parse [[wikilinks]] and markdown links from note text (BUILD-BRIEF §5).

Pure and deterministic — unit-tested offline. Used to build 'structural' links:
a note's explicit references to other concepts/notes.
"""
from __future__ import annotations

import re

# [[Target]] or [[Target|Alias]]
_WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
# [text](target) — capture the target, ignore images ![alt](src) and URLs.
_MDLINK = re.compile(r"(?<!\!)\[[^\]]+\]\(([^)]+)\)")


def parse_wikilinks(text: str) -> list[str]:
    """Return unique [[wikilink]] targets in first-seen order."""
    seen: dict[str, None] = {}
    for m in _WIKILINK.finditer(text):
        target = m.group(1).strip()
        if target:
            seen.setdefault(target, None)
    return list(seen)


def parse_markdown_link_targets(text: str) -> list[str]:
    """Return unique non-URL markdown link targets (e.g. other note paths)."""
    seen: dict[str, None] = {}
    for m in _MDLINK.finditer(text):
        target = m.group(1).strip()
        if target and not re.match(r"^[a-z]+://", target) and not target.startswith("#"):
            seen.setdefault(target, None)
    return list(seen)
