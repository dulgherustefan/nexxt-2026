"""Arborele Merkle în stilul RFC 6962 / RFC 9162 (Certificate Transparency).

frunză = SHA-256(0x00 || date), nod = SHA-256(0x01 || stânga || dreapta).
Pentru n frunze, împărțirea se face la cea mai mare putere a lui 2 mai mică decât n.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"


def leaf_hash(data: bytes) -> bytes:
    """Hash-ul unei frunze (cu prefixul 0x00, care separă frunzele de noduri)."""
    return hashlib.sha256(LEAF_PREFIX + data).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(NODE_PREFIX + left + right).digest()


def _split(n: int) -> int:
    """Cea mai mare putere a lui 2 strict mai mică decât n (n ≥ 2)."""
    k = 1
    while k << 1 < n:
        k <<= 1
    return k


def root_from_leaves(leaves: Sequence[bytes]) -> bytes:
    """Rădăcina (MTH) peste frunze deja hash-uite cu `leaf_hash`."""
    n = len(leaves)
    if n == 0:
        return hashlib.sha256(b"").digest()
    if n == 1:
        return leaves[0]
    k = _split(n)
    return node_hash(root_from_leaves(leaves[:k]), root_from_leaves(leaves[k:]))


def merkle_root(items: Sequence[bytes]) -> bytes:
    """Rădăcina peste datele brute ale frunzelor."""
    return root_from_leaves([leaf_hash(item) for item in items])


def inclusion_path(leaves: Sequence[bytes], index: int) -> list[bytes]:
    """Dovada de includere PATH(m, D[n]) din RFC 6962 §2.1.1."""
    n = len(leaves)
    if not 0 <= index < n:
        raise IndexError("the leaf index is outside the tree")
    if n == 1:
        return []
    k = _split(n)
    if index < k:
        return inclusion_path(leaves[:k], index) + [root_from_leaves(leaves[k:])]
    return inclusion_path(leaves[k:], index - k) + [root_from_leaves(leaves[:k])]


def verify_inclusion(leaf: bytes, index: int, tree_size: int, path: Sequence[bytes], root: bytes) -> bool:
    """Verificarea din RFC 9162 §2.1.3.2. `leaf` e hash-ul frunzei (cu prefixul 0x00)."""
    if index < 0 or index >= tree_size:
        return False
    fn, sn, r = index, tree_size - 1, leaf
    for p in path:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            r = node_hash(p, r)
            if not fn & 1:
                while not fn & 1 and fn != 0:
                    fn >>= 1
                    sn >>= 1
        else:
            r = node_hash(r, p)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r == root
