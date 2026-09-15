"""Offline tests for link canonical form and scoring."""
import pytest

from living_brain.linking import (
    canonical_pair,
    cosine_to_score,
    make_link,
    semantic_link,
    shared_attr_link,
    temporal_link,
)


def test_canonical_pair_orders_ids():
    assert canonical_pair("b", "a") == ("a", "b")
    assert canonical_pair("a", "b") == ("a", "b")


def test_make_link_canonicalises():
    link = make_link("z", "a", "similar-to", "semantic", 0.9, {"cosine": 0.8})
    assert (link.a_id, link.b_id) == ("a", "z")


def test_make_link_rejects_self_link():
    with pytest.raises(ValueError):
        make_link("a", "a", "similar-to", "semantic", 0.9, {"x": 1})


def test_make_link_rejects_unknown_method():
    with pytest.raises(ValueError):
        make_link("a", "b", "rel", "telepathy", 0.9, {"x": 1})


def test_make_link_rejects_out_of_range_score():
    with pytest.raises(ValueError):
        make_link("a", "b", "rel", "semantic", 1.5, {"x": 1})


def test_no_link_without_evidence():
    with pytest.raises(ValueError):
        make_link("a", "b", "rel", "semantic", 0.9, {})


def test_cosine_to_score_bounds():
    assert cosine_to_score(-1.0) == 0.0
    assert cosine_to_score(1.0) == 1.0
    assert cosine_to_score(0.0) == 0.5


def test_semantic_link_threshold():
    assert semantic_link("a", "b", 0.5, threshold=0.75) is None
    link = semantic_link("a", "b", 0.9, threshold=0.75)
    assert link is not None
    assert link.method == "semantic"
    assert link.evidence["cosine"] == 0.9


def test_shared_attr_and_temporal_links_carry_evidence():
    sa = shared_attr_link("a", "b", "employer", "acme")
    assert sa.method == "shared_attr"
    assert sa.evidence == {"attr": "employer", "value": "acme"}
    tl = temporal_link("a", "b", 42)
    assert tl.method == "temporal"
    assert tl.evidence == {"episode_id": 42}
