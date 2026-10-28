"""The evidence ledger: SHA-256 chain, RFC 6962 Merkle tree, Ed25519 seal, QR code, verification."""

from versoml.shared.ledger.canonical import canonical_bytes, canonical_json, hash_obj, prefixed_hash, sha256_hex
from versoml.shared.ledger.ledger import (
    DOSSIER_FORMAT,
    LabelError,
    Ledger,
    LedgerError,
    case_genesis,
    entry_hash,
    qr_text,
    root_hex,
    seal_payload,
    verify_dossier,
    verify_facts,
    verify_proof,
)
from versoml.shared.ledger.merkle import inclusion_path, leaf_hash, merkle_root, root_from_leaves, verify_inclusion

__all__ = [
    "DOSSIER_FORMAT",
    "LabelError",
    "Ledger",
    "LedgerError",
    "canonical_bytes",
    "canonical_json",
    "case_genesis",
    "entry_hash",
    "hash_obj",
    "inclusion_path",
    "leaf_hash",
    "merkle_root",
    "prefixed_hash",
    "qr_text",
    "root_from_leaves",
    "root_hex",
    "seal_payload",
    "sha256_hex",
    "verify_dossier",
    "verify_facts",
    "verify_inclusion",
    "verify_proof",
]
