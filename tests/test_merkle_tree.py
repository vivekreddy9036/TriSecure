"""Tests for VoteMerkleTree — binary SHA-256 Merkle tree with inclusion proofs."""
import pytest
from security.merkle_tree import VoteMerkleTree


def _tree_with(n):
    t = VoteMerkleTree()
    leaves = [t.add_leaf(f"vote_{i}".encode()) for i in range(n)]
    return t, leaves


def test_empty_tree_has_no_root():
    assert VoteMerkleTree().get_root() is None


def test_single_leaf():
    t = VoteMerkleTree()
    h = t.add_leaf(b"only vote")
    assert t.get_root() == h


def test_two_leaves_root_deterministic():
    t1, _ = _tree_with(2)
    t2, _ = _tree_with(2)
    assert t1.get_root() == t2.get_root()


def test_proof_verify_roundtrip_even(n=8):
    t, leaves = _tree_with(n)
    root = t.get_root()
    for i, lh in enumerate(leaves):
        proof = t.get_proof(i)
        assert VoteMerkleTree.verify_proof(lh, proof, root), f"leaf {i} failed"


def test_proof_verify_roundtrip_odd(n=5):
    t, leaves = _tree_with(n)
    root = t.get_root()
    for i, lh in enumerate(leaves):
        proof = t.get_proof(i)
        assert VoteMerkleTree.verify_proof(lh, proof, root), f"leaf {i} odd tree"


def test_proof_length_is_log2():
    import math
    for n in [4, 8, 16]:
        t, leaves = _tree_with(n)
        proof = t.get_proof(0)
        assert len(proof) == int(math.log2(n))


def test_tampered_proof_rejected():
    t, leaves = _tree_with(4)
    root = t.get_root()
    proof = t.get_proof(1)
    bad_proof = [("a" * 64, proof[0][1])] + proof[1:]
    assert not VoteMerkleTree.verify_proof(leaves[1], bad_proof, root)


def test_wrong_leaf_rejected():
    t, leaves = _tree_with(4)
    proof = t.get_proof(0)
    root = t.get_root()
    assert not VoteMerkleTree.verify_proof(leaves[1], proof, root)


def test_serialize_deserialize():
    t1, _ = _tree_with(6)
    data = t1.serialize()
    t2 = VoteMerkleTree.deserialize(data)
    assert t1.get_root() == t2.get_root()
    assert len(t1) == len(t2)
