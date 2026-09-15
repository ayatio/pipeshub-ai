"""Offline tests for pure ontology shape inference."""
from living_brain.ontology import infer_shape


def test_infer_shape_empty():
    assert infer_shape([]) == {"common_keys": [], "seen_keys": [], "instances": 0}


def test_infer_shape_common_and_seen():
    shape = infer_shape([{"role", "team"}, {"role", "email"}, {"role"}])
    assert shape["common_keys"] == ["role"]        # in every instance
    assert shape["seen_keys"] == ["email", "role", "team"]  # union, sorted
    assert shape["instances"] == 3


def test_infer_shape_no_common_keys():
    shape = infer_shape([{"a"}, {"b"}])
    assert shape["common_keys"] == []
    assert shape["seen_keys"] == ["a", "b"]
