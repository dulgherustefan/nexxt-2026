"""Text embeddings on Amazon Bedrock, with a content-addressed cache.

- Cache key: sha256 of model id + input type + normalized text (NFC, ș/ț with comma below, single spaces).
- Two cache layers per namespace:
  * static: ``versoml/data/kb/emb_<namespace>__<model>.npz`` (committed, float16), written by
    ``versoml kb build --live`` for the static corpus and the eval queries;
  * runtime: ``<var>/kb/emb_<namespace>.sqlite`` (float16), for texts seen at run time (queries, new precedents).
- Live calls happen only when the LLM mode allows them (``live``, or ``auto`` with a Bedrock key) or when the
  caller passes ``allow_live=True``. Replay and offline modes read the caches only, and ``embed_texts``
  returns None when a vector is missing.
- Runtime texts pass the PII guard (``assert_llm_safe``) before they leave the process. Callers pass
  pseudonymized text; raw personal data raises ``RawPIIError`` and nothing is sent.
- Rows are L2-normalized float32. Texts are never logged.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import sqlite3
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np

from versoml.config import PACKAGE_DIR, Settings, get_settings
from versoml.shared.privacy.text import normalize_ro

log = logging.getLogger("versoml.knowledge.embeddings")

InputType = Literal["search_document", "search_query", "classification", "clustering"]
INPUT_TYPES: tuple[str, ...] = ("search_document", "search_query", "classification", "clustering")
STATIC_DIR = PACKAGE_DIR / "data" / "kb"
_NAMESPACE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")
_WS = re.compile(r"\s+")
_LIVE_BACKOFF_S = 60.0


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    family: Literal["cohere_v3", "cohere_v4", "titan_v2"]
    dim: int
    max_batch: int     # texts per request
    max_chars: int     # texts are cut at the end beyond this length (the model truncates too)


MODELS: dict[str, ModelSpec] = {
    "cohere.embed-multilingual-v3": ModelSpec("cohere.embed-multilingual-v3", "cohere_v3", 1024, 96, 2048),
    "cohere.embed-v4:0": ModelSpec("cohere.embed-v4:0", "cohere_v4", 1536, 96, 16000),
    "amazon.titan-embed-text-v2:0": ModelSpec("amazon.titan-embed-text-v2:0", "titan_v2", 512, 1, 16000),
}

# backend(spec, texts, input_type) -> one vector per text (lists of floats)
Backend = Callable[[ModelSpec, list[str], str], list[list[float]]]


class EmbeddingError(RuntimeError):
    """A live embedding call failed after the retries. The message never contains the texts."""


def model_spec(model_id: str | None = None) -> ModelSpec:
    from versoml.knowledge.settings import get_kb_settings

    model_id = model_id or get_kb_settings().embed_model
    if model_id not in MODELS:
        raise ValueError(f"Unknown embedding model: {model_id}. Known: {', '.join(MODELS)}")
    return MODELS[model_id]


def normalize_text(text: str) -> str:
    """The form that is hashed and sent: NFC, ș/ț with comma below, whitespace collapsed."""
    return _WS.sub(" ", normalize_ro(text or "")).strip()


def cache_key(model_id: str, input_type: str, text: str) -> str:
    blob = f"{model_id}\x1f{input_type}\x1f{normalize_text(text)}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _model_slug(model_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", model_id.lower()).strip("-")


def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float32)
    if matrix.ndim == 1:
        matrix = matrix[None, :]
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)


# ---------------------------------------------------------------- caches


class StaticCache:
    """Committed vectors for one (namespace, model): keys (raw sha256) and float16 rows in one .npz file."""

    def __init__(self, path: Path, dim: int):
        self.path = path
        self.dim = dim
        self._index: dict[str, int] = {}
        self._vecs = np.zeros((0, dim), dtype=np.float16)
        self._pending: dict[str, np.ndarray] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with np.load(self.path, allow_pickle=False) as data:
                keys = data["keys"]
                vecs = data["vecs"]
        except (OSError, KeyError, ValueError) as exc:
            log.warning("Embedding cache %s is unreadable (%s); it is ignored.", self.path.name, type(exc).__name__)
            return
        if vecs.ndim != 2 or vecs.shape[1] != self.dim or len(keys) != len(vecs):
            log.warning("Embedding cache %s has the wrong shape; it is ignored.", self.path.name)
            return
        self._vecs = vecs.astype(np.float16)
        self._index = {bytes(row).hex(): i for i, row in enumerate(keys)}

    def __len__(self) -> int:
        return len(self._index) + len(self._pending)

    def get(self, key: str) -> np.ndarray | None:
        row = self._pending.get(key)
        if row is not None:
            return row
        i = self._index.get(key)
        return None if i is None else self._vecs[i]

    def put(self, key: str, vec: np.ndarray) -> None:
        with self._lock:
            if key not in self._index:
                self._pending[key] = np.asarray(vec, dtype=np.float16)

    def flush(self, keep: set[str] | None = None) -> int:
        """Write the file (atomically). `keep` prunes rows whose key is not in it. Returns the row count."""
        with self._lock:
            entries = {k: self._vecs[i] for k, i in self._index.items()}
            entries.update(self._pending)
            if keep is not None:
                entries = {k: v for k, v in entries.items() if k in keep}
            keys = sorted(entries)
            key_arr = np.array([np.frombuffer(bytes.fromhex(k), dtype=np.uint8) for k in keys],
                               dtype=np.uint8).reshape(len(keys), 32)
            vec_arr = (np.stack([entries[k] for k in keys]).astype(np.float16) if keys
                       else np.zeros((0, self.dim), dtype=np.float16))
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.stem + ".tmp.npz")
            np.savez_compressed(tmp, keys=key_arr, vecs=vec_arr)
            tmp.replace(self.path)
            self._index = {k: i for i, k in enumerate(keys)}
            self._vecs = vec_arr
            self._pending.clear()
            return len(keys)


class RuntimeCache:
    """Vectors for texts seen at run time, in SQLite (safe for the two zone processes)."""

    _SCHEMA = ("CREATE TABLE IF NOT EXISTS vectors (key TEXT PRIMARY KEY, model TEXT NOT NULL, "
               "input_type TEXT NOT NULL, dim INTEGER NOT NULL, vec BLOB NOT NULL, created_at REAL NOT NULL)")

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._ready = False

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=30)
        if not self._ready:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(self._SCHEMA)
            conn.commit()
            self._ready = True
        return conn

    def get_many(self, keys: Sequence[str], dim: int) -> dict[str, np.ndarray]:
        if not keys or not self.path.exists():
            return {}
        out: dict[str, np.ndarray] = {}
        with self._lock, closing(self._connect()) as conn:
            for i in range(0, len(keys), 500):
                part = list(keys[i:i + 500])
                rows = conn.execute(
                    f"SELECT key, dim, vec FROM vectors WHERE key IN ({','.join('?' * len(part))})", part
                ).fetchall()
                for key, row_dim, blob in rows:
                    if row_dim == dim:
                        out[key] = np.frombuffer(blob, dtype=np.float16)
        return out

    def put_many(self, rows: Sequence[tuple[str, str, str, np.ndarray]]) -> None:
        if not rows:
            return
        now = time.time()
        with self._lock, closing(self._connect()) as conn, conn:
            conn.executemany(
                "INSERT OR IGNORE INTO vectors (key, model, input_type, dim, vec, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                [(k, m, t, int(v.shape[0]), np.asarray(v, dtype=np.float16).tobytes(), now) for k, m, t, v in rows],
            )

    def count(self) -> int:
        if not self.path.exists():
            return 0
        with self._lock, closing(self._connect()) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM vectors").fetchone()[0])


# ---------------------------------------------------------------- Bedrock backend


_RETRY_CODES = {"ThrottlingException", "ServiceUnavailableException", "ModelNotReadyException",
                "InternalServerException", "ModelTimeoutException", "TooManyRequestsException"}
_FATAL_CODES = {"AccessDeniedException", "UnrecognizedClientException", "ExpiredTokenException",
                "ResourceNotFoundException"}


class BedrockBackend:
    """Calls bedrock-runtime InvokeModel with the bearer token loaded at run time."""

    def __init__(self, region: str):
        self.region = region
        self._client = None
        self._lock = threading.Lock()

    def available(self) -> bool:
        from versoml.secrets import load_bedrock_key

        return load_bedrock_key()

    def client(self):
        with self._lock:
            if self._client is None:
                import boto3
                from botocore.config import Config

                from versoml.secrets import install_log_redaction, load_bedrock_key

                install_log_redaction()
                load_bedrock_key()
                self._client = boto3.client(
                    "bedrock-runtime", region_name=self.region,
                    config=Config(retries={"max_attempts": 1, "mode": "standard"}, connect_timeout=5,
                                  read_timeout=60),
                )
            return self._client

    def __call__(self, spec: ModelSpec, texts: list[str], input_type: str) -> list[list[float]]:
        if spec.family == "titan_v2":
            if len(texts) == 1:
                return [self._titan(spec, texts[0])]
            with ThreadPoolExecutor(max_workers=8) as pool:
                return list(pool.map(lambda t: self._titan(spec, t), texts))
        body: dict = {"texts": texts, "input_type": input_type}
        if spec.family == "cohere_v3":
            body["truncate"] = "END"
        else:
            body.update({"truncate": "RIGHT", "embedding_types": ["float"], "output_dimension": spec.dim})
        data = self._invoke(spec.model_id, body)
        vectors = data.get("embeddings")
        if isinstance(vectors, dict):
            vectors = vectors.get("float")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise EmbeddingError(f"{spec.model_id} returned {len(vectors or [])} vectors for {len(texts)} texts")
        return vectors

    def _titan(self, spec: ModelSpec, text: str) -> list[float]:
        data = self._invoke(spec.model_id, {"inputText": text, "dimensions": spec.dim, "normalize": True})
        vector = data.get("embedding")
        if not isinstance(vector, list):
            raise EmbeddingError(f"{spec.model_id} returned no vector")
        return vector

    def _invoke(self, model_id: str, body: dict) -> dict:
        response = self.client().invoke_model(modelId=model_id, body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                              contentType="application/json", accept="application/json")
        return json.loads(response["body"].read())


def _error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return str(response.get("Error", {}).get("Code", "")) or type(exc).__name__
    return type(exc).__name__


# ---------------------------------------------------------------- the embedder


@dataclass
class EmbedStats:
    requests: int = 0
    texts: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    live_calls: int = 0
    live_texts: int = 0
    errors: int = 0
    last_error: str | None = None
    by_namespace: dict[str, int] = field(default_factory=dict)


class Embedder:
    def __init__(self, settings: Settings | None = None, *, static_dir: Path | None = None,
                 var_dir: Path | None = None, backend: Backend | None = None,
                 retries: int = 4, backoff_s: float = 0.5):
        self.settings = settings or get_settings()
        self.static_dir = Path(static_dir) if static_dir else STATIC_DIR
        self._var_dir = Path(var_dir) if var_dir else None
        self.backend: Backend = backend or BedrockBackend(self.settings.aws_region)
        self.retries = retries
        self.backoff_s = backoff_s
        self.stats = EmbedStats()
        self._static: dict[tuple[str, str], StaticCache] = {}
        self._runtime: dict[str, RuntimeCache] = {}
        self._lock = threading.Lock()
        self._live_failed_at: float | None = None

    # ---------------------------------------------------------- configuration

    @property
    def var_kb_dir(self) -> Path:
        base = self._var_dir if self._var_dir else self.settings.var_dir
        return base / "kb"

    def live_allowed(self, allow_live: bool | None = None) -> bool:
        """True when a cache miss may be sent to Bedrock now."""
        if allow_live is False:
            return False
        if self._live_failed_at and time.time() - self._live_failed_at < _LIVE_BACKOFF_S and allow_live is not True:
            return False
        if allow_live is None:
            from versoml.knowledge.settings import get_kb_settings

            forced = get_kb_settings().embed_live
            if forced is not None:
                allow_live = forced
            else:
                mode = self.settings.versoml_llm_mode
                if mode in ("offline", "replay"):
                    return False
                allow_live = True  # live, or auto (live when a key is present)
        if not allow_live:
            return False
        available = getattr(self.backend, "available", None)
        return bool(available()) if callable(available) else True

    def static_cache(self, namespace: str, model_id: str) -> StaticCache:
        spec = model_spec(model_id)
        key = (namespace, spec.model_id)
        with self._lock:
            if key not in self._static:
                path = self.static_dir / f"emb_{namespace}__{_model_slug(spec.model_id)}.npz"
                self._static[key] = StaticCache(path, spec.dim)
            return self._static[key]

    def runtime_cache(self, namespace: str) -> RuntimeCache:
        with self._lock:
            if namespace not in self._runtime:
                self._runtime[namespace] = RuntimeCache(self.var_kb_dir / f"emb_{namespace}.sqlite")
            return self._runtime[namespace]

    # ---------------------------------------------------------- lookups

    def lookup(self, texts: Sequence[str], input_type: str = "search_document", *, namespace: str = "kb",
               model: str | None = None) -> tuple[np.ndarray, np.ndarray]:
        """Cached vectors only: (matrix n×dim float32, found mask). Missing rows are zeros."""
        _check(namespace, input_type)
        spec = model_spec(model)
        keys = [cache_key(spec.model_id, input_type, t) for t in texts]
        out = np.zeros((len(keys), spec.dim), dtype=np.float32)
        found = np.zeros(len(keys), dtype=bool)
        static = self.static_cache(namespace, spec.model_id)
        missing: list[int] = []
        for i, key in enumerate(keys):
            vec = static.get(key)
            if vec is not None:
                out[i] = vec
                found[i] = True
            else:
                missing.append(i)
        if missing:
            runtime = self.runtime_cache(namespace).get_many([keys[i] for i in missing], spec.dim)
            for i in missing:
                vec = runtime.get(keys[i])
                if vec is not None:
                    out[i] = vec
                    found[i] = True
        if found.any():
            out[found] = _normalize_rows(out[found])
        return out, found

    # ---------------------------------------------------------- the main call

    def embed(self, texts: Sequence[str], input_type: str = "search_document", *, namespace: str = "kb",
              allow_live: bool | None = None, static: bool = False, model: str | None = None) -> np.ndarray | None:
        _check(namespace, input_type)
        texts = [normalize_text(t) for t in texts]
        spec = model_spec(model)
        self.stats.requests += 1
        self.stats.texts += len(texts)
        self.stats.by_namespace[namespace] = self.stats.by_namespace.get(namespace, 0) + len(texts)
        if not texts:
            return np.zeros((0, spec.dim), dtype=np.float32)

        matrix, found = self.lookup(texts, input_type, namespace=namespace, model=spec.model_id)
        self.stats.cache_hits += int(found.sum())
        missing = [i for i in range(len(texts)) if not found[i]]
        self.stats.cache_misses += len(missing)
        if not missing:
            return matrix
        if not self.live_allowed(allow_live):
            return None

        # unique texts only, in a stable order
        todo: dict[str, list[int]] = {}
        for i in missing:
            todo.setdefault(texts[i], []).append(i)
        unique = list(todo)
        if not (static and namespace == "kb"):
            # runtime (or case-derived) text: nothing raw leaves the process
            from versoml.shared.privacy import assert_llm_safe

            assert_llm_safe(unique)

        try:
            vectors = self._call_batched(spec, unique, input_type)
        except EmbeddingError as exc:
            self.stats.errors += 1
            self.stats.last_error = str(exc)[:200]
            log.warning("Embedding call failed (%s, %d texts): %s", spec.model_id, len(unique), str(exc)[:200])
            return None

        rows = _normalize_rows(np.asarray(vectors, dtype=np.float32))
        if rows.shape[1] != spec.dim:
            self.stats.errors += 1
            self.stats.last_error = f"dimension {rows.shape[1]} instead of {spec.dim}"
            log.warning("Embedding dimension mismatch for %s: %d", spec.model_id, rows.shape[1])
            return None
        to_runtime: list[tuple[str, str, str, np.ndarray]] = []
        static_cache = self.static_cache(namespace, spec.model_id) if static else None
        for text, row in zip(unique, rows):
            key = cache_key(spec.model_id, input_type, text)
            if static_cache is not None:
                static_cache.put(key, row)
            else:
                to_runtime.append((key, spec.model_id, input_type, row))
            for i in todo[text]:
                matrix[i] = row
        if static_cache is not None:
            static_cache.flush()
        else:
            self.runtime_cache(namespace).put_many(to_runtime)
        return _normalize_rows(matrix)

    def _call_batched(self, spec: ModelSpec, texts: list[str], input_type: str) -> list[list[float]]:
        out: list[list[float]] = []
        batch = max(1, spec.max_batch) if spec.family != "titan_v2" else 32
        for start in range(0, len(texts), batch):
            part = [t[:spec.max_chars] for t in texts[start:start + batch]]
            out.extend(self._call_with_retries(spec, part, input_type))
        return out

    def _call_with_retries(self, spec: ModelSpec, texts: list[str], input_type: str) -> list[list[float]]:
        last = "unknown error"
        for attempt in range(self.retries + 1):
            try:
                self.stats.live_calls += 1
                vectors = self.backend(spec, texts, input_type)
                self.stats.live_texts += len(texts)
                self._live_failed_at = None
                return vectors
            except Exception as exc:  # noqa: BLE001 - classified below; texts are never part of the message
                if type(exc).__name__ == "RawPIIError":
                    raise
                code = _error_code(exc)
                from versoml.secrets import redact

                last = redact(f"{code}: {exc}")[:200]
                fatal = code in _FATAL_CODES or code == "ValidationException" or isinstance(exc, (ValueError, TypeError))
                if fatal or attempt == self.retries:
                    if code in _FATAL_CODES or "Connect" in code or "Endpoint" in code or "NoCredentials" in code:
                        self._live_failed_at = time.time()
                    break
                retryable = code in _RETRY_CODES or "Timeout" in code or "Connection" in code or "Endpoint" in code
                if not retryable:
                    break
                time.sleep(self.backoff_s * (2 ** attempt) * (0.75 + random.random() * 0.5))
        raise EmbeddingError(last)

    def describe(self) -> dict:
        from versoml.knowledge.settings import get_kb_settings

        spec = model_spec(None)
        return {
            "model": spec.model_id, "dim": spec.dim, "live_allowed": self.live_allowed(None),
            "configured_model": get_kb_settings().embed_model,
            "stats": {k: v for k, v in self.stats.__dict__.items()},
        }


def _check(namespace: str, input_type: str) -> None:
    if not _NAMESPACE_RE.match(namespace):
        raise ValueError(f"Invalid embedding namespace: {namespace!r}")
    if input_type not in INPUT_TYPES:
        raise ValueError(f"Invalid input_type: {input_type!r}")


_default: Embedder | None = None
_default_lock = threading.Lock()


def get_embedder() -> Embedder:
    global _default
    with _default_lock:
        if _default is None:
            _default = Embedder()
        return _default


def set_embedder(embedder: Embedder | None) -> None:
    """Replace the process embedder (tests). None resets it to the default on next use."""
    global _default
    with _default_lock:
        _default = embedder


def embed_texts(
    texts: list[str],
    input_type: InputType = "search_document",
    *,
    namespace: str = "kb",
    allow_live: bool | None = None,
    static: bool = False,
    model: str | None = None,
) -> np.ndarray | None:
    """Embed texts: rows are L2-normalized float32, one per text. None when a vector is not available.

    Cached vectors are used first (committed static cache, then the runtime cache under var/kb). Cache misses
    go to Bedrock only when live calls are allowed (LLM mode live or auto with a key, or ``allow_live=True``).
    Runtime texts pass the PII guard first: raw personal data raises ``RawPIIError`` and nothing is sent.
    ``static=True`` is for ``versoml kb build``: new vectors go to the committed cache under versoml/data/kb.
    """
    return get_embedder().embed(texts, input_type, namespace=namespace, allow_live=allow_live, static=static,
                                model=model)
