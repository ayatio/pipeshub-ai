"""Offline tests for identity helpers."""
from living_brain.ids import content_hash, entity_id, slugify


def test_slugify_basic():
    assert slugify("Sarah Chen") == "sarah-chen"
    assert slugify("  Project ATLAS! ") == "project-atlas"


def test_slugify_unicode_and_empty():
    assert slugify("Café Déjà") == "cafe-deja"
    assert slugify("!!!") == "unnamed"


def test_entity_id_shape():
    assert entity_id("person", "Sarah Chen") == "person/sarah-chen"
    assert entity_id("Project", "Atlas") == "project/atlas"


def test_content_hash_stable_and_normalising():
    a = content_hash("hello world")
    b = content_hash("hello world")
    assert a == b
    # trailing whitespace per line is normalised away
    assert content_hash("hello world  \n") == content_hash("hello world")


def test_content_hash_distinguishes_content():
    assert content_hash("a") != content_hash("b")
