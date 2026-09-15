"""Offline tests for the wikilink / markdown-link parsers."""
from living_brain.wikilinks import parse_markdown_link_targets, parse_wikilinks


def test_parse_wikilinks_basic_and_aliased():
    text = "See [[Project Atlas]] and [[Sarah Chen|Sarah]] for details."
    assert parse_wikilinks(text) == ["Project Atlas", "Sarah Chen"]


def test_parse_wikilinks_dedup_first_seen_order():
    assert parse_wikilinks("[[B]] [[A]] [[B]]") == ["B", "A"]


def test_parse_wikilinks_none():
    assert parse_wikilinks("no links here") == []


def test_markdown_link_targets_skip_urls_and_anchors():
    text = "[note](./other.md) [web](https://x.com) [sec](#heading) ![img](a.png)"
    targets = parse_markdown_link_targets(text)
    assert "./other.md" in targets
    assert "https://x.com" not in targets
    assert "#heading" not in targets
    assert "a.png" not in targets  # image, not a link
