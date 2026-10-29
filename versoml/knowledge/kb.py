"""The knowledge base: hybrid retrieval over rules, docs/context, case studies, typologies and precedents.

Signals: BM25 + dense cosine (Bedrock embeddings) fused by reciprocal rank fusion (k=60). Without a query
vector (offline and not cached, or the PII guard refused the query) the dense signal is replaced by a local
character n-gram TF-IDF cosine; `Hit.why` names the signals used. An exact rule ID in the query lifts that
rule's chunk. The AML zone never loads precedents: client case data reaches the AML zone only through the diode.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Literal

import numpy as np

from versoml.config import Settings, get_settings
from versoml.knowledge import corpus
from versoml.knowledge.chunker import Chunk
from versoml.knowledge.embeddings import Embedder, get_embedder, model_spec
from versoml.knowledge.glossary import expand
from versoml.knowledge.index import BM25, CharNgramTfidf, mmr as mmr_select, ranking, rrf, tokenize_all
from versoml.knowledge.models import KINDS, Answer, Hit
from versoml.knowledge.settings import get_kb_settings
from versoml.knowledge.text import normalize_ro, query_rule_ids, query_tokens, rule_ids_in

log = logging.getLogger("versoml.knowledge")

Zone = Literal["client", "aml"]
TOP_PER_SIGNAL = 100
RULE_BOOST = 2.0          # in units of 1/(k+1): an exact rule ID outweighs being first in one signal
# search() without `kinds`: the knowledge kinds; past cases come from precedents() or kinds=[..., "precedent"]
DEFAULT_KINDS = ("rule", "law", "guidance", "typology", "case_study")
PRECEDENTS_RUNTIME = "precedents.jsonl"
GLOSSARY_WEIGHT = 0.5     # BM25 weight of the translated query terms


class KnowledgeBase:
    def __init__(self, zone: Zone = "client", *, settings: Settings | None = None, embedder: Embedder | None = None,
                 kb_dir: Path | None = None, model: str | None = None, llm=None):
        if zone not in ("client", "aml"):
            raise ValueError(f"Unknown zone: {zone}")
        self.zone: Zone = zone
        self.settings = settings or get_settings()
        if zone == "client" and self.settings.versoml_zone == "aml":
            raise PermissionError("The wall: the AML zone process cannot load the client zone knowledge base.")
        self.embedder = embedder or get_embedder()
        self._llm = llm
        self.kb_dir = Path(kb_dir) if kb_dir else corpus.KB_DIR
        self.model = model_spec(model).model_id
        kb_settings = get_kb_settings()
        self.rrf_k = kb_settings.rrf_k
        self.rrf_weights = {"bm25": kb_settings.rrf_weight_bm25, "dense": kb_settings.rrf_weight_dense,
                            "char_ngram": kb_settings.rrf_weight_char}
        self.rerank_enabled = kb_settings.rerank
        self._lock = threading.RLock()
        self._dirty = False
        self._char: CharNgramTfidf | None = None
        self.stale = False
        self.load_ms = 0
        started = time.perf_counter()
        self._load()
        self.load_ms = round((time.perf_counter() - started) * 1000)

    # ------------------------------------------------------------ loading

    @property
    def runtime_precedents_path(self) -> Path:
        return self.settings.var_dir / "kb" / PRECEDENTS_RUNTIME

    def _load(self) -> None:
        manifest = corpus.read_manifest(self.kb_dir)
        self.manifest = manifest
        rules = corpus.rule_chunks()
        static_fp = corpus.static_fingerprint(rules)
        static = corpus.read_jsonl(self.kb_dir / corpus.CHUNKS_FILE)
        if not static or manifest.get("static_fingerprint") != static_fp:
            if static:
                log.warning("The knowledge base snapshot is stale; rebuilt in memory. Run `versoml kb build`.")
            static = corpus.build_static_corpus()
            self.stale = True
        precedents: list[Chunk] = []
        if self.zone == "client":
            precedents = corpus.read_jsonl(self.kb_dir / corpus.PRECEDENTS_FILE)
            if not precedents or manifest.get("precedents_fingerprint") != corpus.precedents_fingerprint():
                precedents = corpus.golden_precedents()
                self.stale = self.stale or bool(manifest)
            runtime = {c.id: c for c in corpus.read_jsonl(self.runtime_precedents_path)}
            if runtime:
                precedents = [c for c in precedents if c.id not in runtime] + list(runtime.values())
        self._static_count = len(static)
        self._chunks: list[Chunk] = [*static, *precedents]
        self._vectors_for(range(len(self._chunks)), fresh=True)
        self._build_lexical()

    @property
    def llm(self):
        """The LLM client used by ask() (the process client unless one was injected)."""
        if self._llm is None:
            from versoml.shared.llm import get_llm

            self._llm = get_llm()
        return self._llm

    def _namespace(self, chunk: Chunk) -> str:
        return "precedents" if chunk.kind == "precedent" else "kb"

    def _vectors_for(self, rows, fresh: bool = False) -> None:
        """Cached document vectors for `rows` (no network)."""
        spec = model_spec(self.model)
        if fresh:
            self._dense = np.zeros((len(self._chunks), spec.dim), dtype=np.float32)
            self._has_vec = np.zeros(len(self._chunks), dtype=bool)
        rows = list(rows)
        for namespace in ("kb", "precedents"):
            sel = [i for i in rows if self._namespace(self._chunks[i]) == namespace]
            if not sel:
                continue
            matrix, found = self.embedder.lookup([self._chunks[i].embed_text() for i in sel], "search_document",
                                                 namespace=namespace, model=self.model)
            self._dense[sel] = matrix
            self._has_vec[sel] = found

    def _build_lexical(self) -> None:
        with self._lock:
            texts = [c.embed_text() for c in self._chunks]
            self._bm25 = BM25(tokenize_all(texts))
            self._kinds = np.array([c.kind for c in self._chunks])
            self._ids = {c.id: i for i, c in enumerate(self._chunks)}
            self._rule_sets = [set(c.rule_ids) for c in self._chunks]
            self._char = None
            self._dirty = False

    def _ensure_index(self) -> None:
        if self._dirty:
            self._build_lexical()

    def _char_index(self) -> CharNgramTfidf:
        with self._lock:
            if self._char is None:
                self._char = CharNgramTfidf([c.embed_text() for c in self._chunks])
            return self._char

    # ------------------------------------------------------------ helpers

    def chunk(self, chunk_id: str) -> Chunk | None:
        self._ensure_index()
        i = self._ids.get(chunk_id)
        return None if i is None else self._chunks[i]

    def chunks(self, kinds: list[str] | None = None) -> list[Chunk]:
        self._ensure_index()
        return [c for c in self._chunks if not kinds or c.kind in kinds]

    def _candidates(self, kinds, rule_ids, exclude: set[int] | None = None) -> np.ndarray:
        mask = np.ones(len(self._chunks), dtype=bool)
        if kinds:
            unknown = set(kinds) - set(KINDS)
            if unknown:
                raise ValueError(f"Unknown kinds: {sorted(unknown)}")
            mask &= np.isin(self._kinds, list(kinds))
        if rule_ids:
            wanted = _expand_rule_ids(rule_ids)
            mask &= np.array([bool(s & wanted) for s in self._rule_sets], dtype=bool)
        for i in exclude or ():
            mask[i] = False
        return mask

    def _query_vector(self, text: str, namespace: str) -> tuple[np.ndarray | None, str | None]:
        """(vector, reason when missing). Committed eval vectors are found first; then the runtime caches/live."""
        matrix, found = self.embedder.lookup([text], "search_query", namespace="kb", model=self.model)
        if found[0]:
            return matrix[0], None
        try:
            out = self.embedder.embed([text], "search_query", namespace=namespace, model=self.model)
        except Exception as exc:  # noqa: BLE001 - only the PII guard is expected here
            if type(exc).__name__ == "RawPIIError":
                return None, "pii_guard"
            raise
        if out is None:
            return None, "no_query_vector"
        return out[0], None

    def _rank(self, query: str, cand: np.ndarray, *, namespace: str, boost_rules: bool = True,
              use_dense: bool = True) -> tuple[list[int], dict[int, dict], dict]:
        """Fused order over the candidates, the per-document `why`, and query-level info."""
        query = normalize_ro(query).strip()
        signals: dict[str, list[int]] = {}
        raw: dict[str, np.ndarray] = {}
        bm = self.bm25_scores(query)
        signals["bm25"] = ranking(bm, cand, TOP_PER_SIGNAL)
        raw["bm25"] = bm
        info: dict = {"dense": False}
        qvec, reason = (self._query_vector(query, namespace) if use_dense and self._has_vec.any()
                        else (None, "no_document_vectors" if use_dense else "disabled"))
        if qvec is not None:
            ds = self._dense @ qvec
            ds[~self._has_vec] = -1.0
            signals["dense"] = ranking(ds, cand, TOP_PER_SIGNAL)
            raw["dense"] = ds
            info["dense"] = True
        else:
            cs = self._char_index().scores(query)
            signals["char_ngram"] = ranking(cs, cand, TOP_PER_SIGNAL)
            raw["char_ngram"] = cs
            info["fallback"] = reason
        fused = rrf(signals, self.rrf_k, self.rrf_weights)
        boosted: dict[int, str] = {}
        if boost_rules:
            for rid in query_rule_ids(query):
                for canonical in _expand_rule_ids([rid]):
                    i = self._ids.get(f"rule:{canonical}")
                    if i is not None and cand[i]:
                        fused[i] = fused.get(i, 0.0) + RULE_BOOST / (self.rrf_k + 1)
                        boosted[i] = rid
        order = sorted(fused, key=lambda i: (-fused[i], i))
        ranks = {name: {doc: r for r, doc in enumerate(lst, start=1)} for name, lst in signals.items()}
        why: dict[int, dict] = {}
        for i in order:
            w: dict = {"signals": list(signals), "dense": info["dense"], "rrf": round(fused[i], 5)}
            for name in signals:
                rank = ranks[name].get(i)
                w[f"{name}_rank"] = rank
                if rank is not None:
                    w[f"{name}_score"] = round(float(raw[name][i]), 4)
            if i in boosted:
                w["rule_id_boost"] = boosted[i]
            if info.get("fallback"):
                w["fallback"] = info["fallback"]
            why[i] = w
        info["fused"] = fused
        return order, why, info

    def bm25_scores(self, query: str) -> np.ndarray:
        """BM25 over all chunks; glossary translations of the query terms count at half weight."""
        base = query_tokens(normalize_ro(query))
        extra = [t for t in expand(base) if t not in set(base)]
        scores = self._bm25.scores(base)
        if extra:
            scores = scores + GLOSSARY_WEIGHT * self._bm25.scores(extra)
        return scores

    def _hit(self, i: int, score: float, why: dict) -> Hit:
        c = self._chunks[i]
        return Hit(id=c.id, kind=c.kind, title=c.title, text=c.text, source=c.source, confidence=c.confidence,
                   rule_ids=list(c.rule_ids), score=round(float(score), 6), why=why, meta=dict(c.meta))

    def _similarity(self, use_dense: bool):
        if use_dense:
            return lambda a, b: float(max(0.0, self._dense[a] @ self._dense[b]))
        char = self._char_index()
        return lambda a, b: float(char.matrix[a].multiply(char.matrix[b]).sum())

    # ------------------------------------------------------------ public API

    def search(self, query: str, k: int = 6, *, kinds: list[str] | None = None, rule_ids: list[str] | None = None,
               mmr: float | None = None, rerank: bool | None = None) -> list[Hit]:
        """Hybrid search. `kinds` and `rule_ids` filter; `mmr` (0..1, e.g. 0.7) diversifies the top k;
        `rerank` (default: the VERSOML_KB_RERANK setting, off) reorders the fused top with Cohere Rerank.

        Without `kinds`, every kind except precedents is searched (past cases are not legal sources); pass
        kinds=[..., "precedent"] or use precedents() for them.
        """
        if not query or not query.strip() or k <= 0:
            return []
        with self._lock:
            self._ensure_index()
            cand = self._candidates(kinds or list(DEFAULT_KINDS), rule_ids)
            namespace = "queries_client" if self.zone == "client" else "queries_aml"
            order, why, info = self._rank(query, cand, namespace=namespace)
            if (self.rerank_enabled if rerank is None else rerank) and order:
                from versoml.knowledge.rerank import rerank_order

                order = rerank_order(self, query, order, why)
            if mmr is not None and order:
                use_dense = info["dense"] and all(self._has_vec[i] for i in order[: 3 * k])
                order = mmr_select(order[: 3 * k], info["fused"], self._similarity(use_dense), k, lam=mmr)
            return [self._hit(i, info["fused"][i], why[i]) for i in order[:k]]

    def for_rules(self, rule_ids: list[str], k_per: int = 1) -> list[Hit]:
        """Legal grounding for fired rules: the rule's own chunk first, then docs that cite it."""
        out: list[Hit] = []
        seen: set[str] = set()
        with self._lock:
            self._ensure_index()
            for rid in rule_ids:
                canon = _canonical(rid)
                wanted = _expand_rule_ids([rid])
                picked = 0
                i = self._ids.get(f"rule:{canon}")
                if i is not None and self._chunks[i].id not in seen:
                    out.append(self._hit(i, 1.0, {"exact_rule": rid, "signals": ["rule_id"]}))
                    seen.add(self._chunks[i].id)
                    picked += 1
                if picked >= k_per:
                    continue
                cand = self._candidates(["law", "guidance", "typology", "case_study"], list(wanted))
                for j in [j for j in np.flatnonzero(cand) if self._chunks[j].id in seen]:
                    cand[j] = False
                if not cand.any():
                    continue
                rule_chunk = self._chunks[i] if i is not None else None
                query = rule_chunk.title if rule_chunk else rid
                order, why, info = self._rank(query, cand, namespace="kb", boost_rules=False, use_dense=False)
                # docs that name the rule but share no words with its title still count
                rest = [j for j in np.flatnonzero(cand) if j not in info["fused"]]
                for j in [*order, *rest]:
                    if picked >= k_per:
                        break
                    w = why.get(j, {"signals": ["rule_id"]})
                    out.append(self._hit(j, info["fused"].get(j, 0.0), {**w, "for_rule": rid}))
                    seen.add(self._chunks[j].id)
                    picked += 1
        return out

    def precedents(self, text: str, k: int = 3, *, exclude_case_id: str | None = None) -> list[Hit]:
        """Similar past cases (client zone only; the AML zone gets an empty list)."""
        if self.zone != "client" or not text or not text.strip():
            return []
        with self._lock:
            self._ensure_index()
            exclude = set()
            if exclude_case_id:
                i = self._ids.get(f"prec:{exclude_case_id}")
                if i is not None:
                    exclude.add(i)
            cand = self._candidates(["precedent"], None, exclude)
            if not cand.any():
                return []
            order, why, info = self._rank(text, cand, namespace="precedents", boost_rules=False)
            return [self._hit(i, info["fused"][i], why[i]) for i in order[:k]]

    def add_precedent(self, case_id: str, text: str, outcome: dict, meta: dict | None = None) -> None:
        """Store a decided case as a precedent (client zone only). Text is pseudonymized before it is stored."""
        if self.zone != "client":
            raise PermissionError("The wall: the AML zone does not keep client precedents.")
        if not case_id or not str(case_id).strip():
            raise ValueError("case_id is required")
        meta = dict(meta or {})
        outcome = dict(outcome or {})
        scenario = str(meta.get("scenario") or outcome.get("scenario") or "")
        safe = corpus.safe_case_text(text, case_id)
        rule_ids = list(dict.fromkeys([*(outcome.get("rule_ids") or []), *rule_ids_in(safe)]))
        outcome.setdefault("rule_ids", rule_ids)
        body = corpus.precedent_text(case_id, scenario, safe, outcome, channel=meta.get("channel"),
                                     amount=meta.get("amount") if isinstance(meta.get("amount"), dict) else None,
                                     label="Summary")
        chunk = Chunk(id=f"prec:{case_id}", kind="precedent", title=f"Past case {case_id}" + (f" · {scenario}" if scenario else ""),
                      text=body, source=f"var/kb/{PRECEDENTS_RUNTIME}", confidence=None, rule_ids=rule_ids,
                      meta={**{k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool, type(None), list, dict))},
                            "outcome": outcome, "scenario": scenario, "case_id": case_id, "origin": "runtime"})
        path = self.runtime_precedents_path
        path.parent.mkdir(parents=True, exist_ok=True)
        # the network call happens before the lock: a slow embedding must not hold up searches on other cases
        vec = None
        try:
            vec = self.embedder.embed([chunk.embed_text()], "search_document", namespace="precedents",
                                      model=self.model)
        except Exception as exc:  # noqa: BLE001 - a precedent without a vector is still found by BM25
            log.warning("No vector for precedent %s: %s", case_id, type(exc).__name__)
        with self._lock:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(chunk.to_json(), ensure_ascii=False, sort_keys=True) + "\n")
            i = self._ids.get(chunk.id)
            if i is None:
                self._chunks.append(chunk)
                self._dense = np.vstack([self._dense, np.zeros((1, self._dense.shape[1]), dtype=np.float32)])
                self._has_vec = np.append(self._has_vec, False)
                i = len(self._chunks) - 1
            else:
                self._chunks[i] = chunk
                self._has_vec[i] = False
            self._dirty = True
            if vec is not None:
                self._dense[i] = vec[0]
                self._has_vec[i] = True
            self._ids[chunk.id] = i

    def embed(self, texts: list[str], input_type: str = "search_query") -> np.ndarray | None:
        namespace = "queries_client" if self.zone == "client" else "queries_aml"
        return self.embedder.embed(texts, input_type, namespace=namespace, model=self.model)

    async def ask(self, question: str, k: int = 6) -> Answer:
        from versoml.knowledge.answer import ask

        return await ask(self, question, k=k)

    def stats(self) -> dict:
        self._ensure_index()
        by_kind: dict[str, int] = {}
        for c in self._chunks:
            by_kind[c.kind] = by_kind.get(c.kind, 0) + 1
        runtime = sum(1 for c in self._chunks if c.meta.get("origin") == "runtime")
        spec = model_spec(self.model)
        return {
            "zone": self.zone,
            "chunks": len(self._chunks),
            "by_kind": dict(sorted(by_kind.items())),
            "embedding_model": spec.model_id,
            "embedding_dim": spec.dim,
            "dense_available": bool(self._has_vec.any()),
            "dense_coverage": round(float(self._has_vec.mean()), 4) if len(self._chunks) else 0.0,
            "live_embeddings": self.embedder.live_allowed(None),
            "built_at": self.manifest.get("built_at"),
            "stale": self.stale,
            "precedents": {"static": by_kind.get("precedent", 0) - runtime, "runtime": runtime} if self.zone == "client" else None,
            "load_ms": self.load_ms,
            "signals": ["bm25", "dense", "rrf"] if self._has_vec.any() else ["bm25", "char_ngram", "rrf"],
        }


def _canonical(rule_id: str) -> str:
    try:
        from versoml.shared.rules.registry import resolve_id

        return resolve_id(rule_id.upper())
    except Exception:  # noqa: BLE001
        return rule_id.upper()


def _expand_rule_ids(rule_ids) -> set[str]:
    """The IDs, their canonical IDs and the aliases of those (DSP-04 ↔ PAY-15)."""
    out: set[str] = set()
    try:
        from versoml.shared.rules.registry import aliases

        alias_map = aliases()
    except Exception:  # noqa: BLE001
        alias_map = {}
    for rid in rule_ids:
        rid = str(rid).upper()
        canon = alias_map.get(rid, rid)
        out.update({rid, canon})
        out.update(a for a, c in alias_map.items() if c == canon)
    return out


_kbs: dict[str, KnowledgeBase] = {}
_kbs_lock = threading.Lock()


def get_kb(zone: Zone = "client") -> KnowledgeBase:
    """The process knowledge base for a zone (cached). The AML zone never loads precedents."""
    with _kbs_lock:
        if zone not in _kbs:
            kb = KnowledgeBase(zone)
            # build the character n-gram index in the background: the fallback is then ready on first use
            threading.Thread(target=kb._char_index, name=f"kb-warmup-{zone}", daemon=True).start()
            _kbs[zone] = kb
        return _kbs[zone]


def reset_kb() -> None:
    """Drop the cached knowledge bases (tests, or after `versoml kb build`)."""
    with _kbs_lock:
        _kbs.clear()
