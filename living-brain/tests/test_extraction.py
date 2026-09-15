"""Offline tests for extraction parsing/validation (no LLM)."""
import pytest

from living_brain.extraction import build_prompt, parse_extraction


def test_parse_valid_extraction():
    raw = (
        '{"entities":[{"type":"Person","label":"Sarah Chen","aliases":["Sarah"],'
        '"props":{"role":"eng lead"}}],'
        '"relationships":[{"source":"Sarah Chen","target":"Atlas",'
        '"rel_type":"works-on","evidence":"Sarah leads Atlas"}]}'
    )
    ex = parse_extraction(raw)
    assert len(ex.entities) == 1
    e = ex.entities[0]
    assert e.type == "person"          # normalised to lowercase
    assert e.label == "Sarah Chen"
    assert e.aliases == ["Sarah"]
    assert ex.relationships[0].rel_type == "works-on"


def test_parse_strips_code_fences():
    raw = '```json\n{"entities":[],"relationships":[]}\n```'
    ex = parse_extraction(raw)
    assert ex.entities == []
    assert ex.relationships == []


def test_parse_empty_object():
    assert parse_extraction("{}").entities == []


def test_parse_rejects_non_json():
    with pytest.raises(ValueError):
        parse_extraction("this is not json")


def test_parse_rejects_non_object():
    with pytest.raises(ValueError):
        parse_extraction("[1, 2, 3]")


def test_parse_rejects_empty_label():
    with pytest.raises(ValueError):
        parse_extraction('{"entities":[{"type":"person","label":"  "}]}')


def test_build_prompt_contains_text_and_schema():
    p = build_prompt("Sarah leads Atlas.")
    assert "Sarah leads Atlas." in p
    assert "entities" in p and "relationships" in p
    assert "ONLY valid JSON" in p
