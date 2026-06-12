"""Binary SHA-256 Merkle tree with O(log n) inclusion proofs."""

import hashlib
import json
from typing import List, Optional, Tuple


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _combine(left: str, right: str) -> str:
    return _sha256((left + right).encode())


class VoteMerkleTree:
    """
    Binary SHA-256 Merkle tree.

    Uses Bitcoin duplicate-last-leaf convention for odd layers.
    Leaf hashes are SHA-256 of raw leaf data; internal nodes hash concatenated child hashes.
    """

    def __init__(self) -> None:
        self._leaves: List[str] = []

    def add_leaf(self, data: bytes) -> str:
        leaf_hash = _sha256(data)
        self._leaves.append(leaf_hash)
        return leaf_hash

    def get_root(self) -> Optional[str]:
        if not self._leaves:
            return None
        layer = list(self._leaves)
        while len(layer) > 1:
            if len(layer) % 2 == 1:
                layer.append(layer[-1])
            layer = [_combine(layer[i], layer[i + 1]) for i in range(0, len(layer), 2)]
        return layer[0]

    def get_proof(self, leaf_index: int) -> List[Tuple[str, str]]:
        """Return O(log n) Merkle proof path as list of (sibling_hash, 'left'|'right')."""
        if leaf_index < 0 or leaf_index >= len(self._leaves):
            return []

        proof: List[Tuple[str, str]] = []
        layer = list(self._leaves)
        idx = leaf_index

        while len(layer) > 1:
            if len(layer) % 2 == 1:
                layer.append(layer[-1])

            if idx % 2 == 0:
                sibling_idx = idx + 1
                proof.append((layer[sibling_idx], "right"))
            else:
                sibling_idx = idx - 1
                proof.append((layer[sibling_idx], "left"))

            layer = [_combine(layer[i], layer[i + 1]) for i in range(0, len(layer), 2)]
            idx //= 2

        return proof

    @staticmethod
    def verify_proof(leaf_hash: str, proof: List[Tuple[str, str]], root: str) -> bool:
        """Verify an inclusion proof in O(log n)."""
        current = leaf_hash
        for sibling_hash, side in proof:
            if side == "right":
                current = _combine(current, sibling_hash)
            else:
                current = _combine(sibling_hash, current)
        return current == root

    def serialize(self) -> bytes:
        return json.dumps({"leaves": self._leaves}).encode()

    @classmethod
    def deserialize(cls, data: bytes) -> "VoteMerkleTree":
        obj = cls()
        obj._leaves = json.loads(data.decode())["leaves"]
        return obj

    def __len__(self) -> int:
        return len(self._leaves)
