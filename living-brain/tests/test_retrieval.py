"""Offline tests for RRF fusion (the pure core of hybrid retrieval)."""
from living_brain.retrieval import fuse_and_order, reciprocal_rank_fusion


def test_rrf_rewards_agreement_across_signals():
    # 'b' is top-ranked in both signals; it should win overall.
    fts = ["a", "b", "c"]
    vec = ["b", "d", "a"]
    order = fuse_and_order([fts, vec])
    assert order[0] == "b"


def test_rrf_single_ranking_preserves_order():
    assert fuse_and_order([["x", "y", "z"]]) == ["x", "y", "z"]


def test_rrf_scores_decrease_with_rank():
    scores = reciprocal_rank_fusion([["a", "b", "c"]])
    assert scores["a"] > scores["b"] > scores["c"]


def test_rrf_tie_break_is_stable_by_first_appearance():
    # two disjoint singletons at rank 1 tie on score; first-seen breaks the tie.
    order = fuse_and_order([["a"], ["b"]])
    assert order == ["a", "b"]


def test_rrf_empty():
    assert fuse_and_order([]) == []
    assert reciprocal_rank_fusion([[]]) == {}
