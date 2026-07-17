from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import httpx

from app.models.schemas import PaperChunk

logger = logging.getLogger(__name__)


class VectorIndex:
    """论文切片向量索引（US-04：系统为文本切片建立向量索引，并提供检索接口）。

    两种后端：
    - 本地TF-IDF字符向量（英文按词、中文按二元组）：无外部依赖，词面检索，
      无法跨语言（中文问题问英文论文会零召回）。
    - 远程embedding（配置EMBEDDING_API_URL后启用）：OpenAI兼容/embeddings接口，
      用多语种模型（如BAAI/bge-m3）可打通中英跨语言语义检索；调用失败自动回退
      本地TF-IDF，保证检索接口始终可用。

    持久化与复用（US-04：不重复索引 / 删除同步清理；进阶包②）：
    昂贵的稠密embedding向量按"内容签名"持久化到 data/indexes/<id>.vectors.json，
    重新索引或进程重启时，只要切片内容与embedding模型未变即直接复用，不再重复
    调用embedding接口（省时省钱）；内容或模型变化则签名失配、自动重新嵌入。
    稀疏TF-IDF廉价，每次内存重建，不进持久化。
    """

    # 每个切片送入embedding接口的最大字符数，防止超出模型输入限制
    EMBEDDING_INPUT_CHARS = 1500
    # 单次/embeddings请求的批大小，避免超出服务端条数/长度限制
    EMBEDDING_BATCH_SIZE = 32

    def __init__(
        self,
        embedding_api_url: str = "",
        embedding_api_key: str = "",
        embedding_model: str = "",
        persist_dir: Path | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.embedding_api_url = embedding_api_url.rstrip("/")
        self.embedding_api_key = embedding_api_key
        self.embedding_model = embedding_model
        self.persist_dir = persist_dir
        self._transport = transport  # 供测试注入MockTransport
        # 稀疏TF-IDF向量：paper_id -> {chunk_id: {term: weight}}
        self._sparse: dict[str, dict[str, dict[str, float]]] = {}
        # 每篇论文的IDF表：paper_id -> {term: idf}
        self._idf: dict[str, dict[str, float]] = {}
        # 远程embedding稠密向量：paper_id -> {chunk_id: [float]}
        self._dense: dict[str, dict[str, list[float]]] = {}

    @property
    def remote_enabled(self) -> bool:
        return bool(self.embedding_api_url and self.embedding_model)

    def backend_name(self, paper_id: str) -> str:
        """返回该论文实际生效的向量后端，用于检索调试接口展示。"""
        if paper_id in self._dense:
            return "remote-embedding"
        if paper_id in self._sparse:
            return "local-tfidf"
        return "none"

    def index(self, paper_id: str, chunks: list[PaperChunk]) -> None:
        if not chunks:
            # 空论文：清空内存与磁盘，避免残留（US-04删除同步清理）
            self.remove(paper_id)
            return

        signature = self._signature(chunks)

        # 稀疏TF-IDF：整体重算并覆盖（替换而非追加，重解析不产生重复索引）
        token_lists = {
            chunk.chunk_id: self._tokenize(chunk.content) for chunk in chunks
        }
        document_frequency: dict[str, int] = defaultdict(int)
        for tokens in token_lists.values():
            for term in set(tokens):
                document_frequency[term] += 1
        total = len(chunks)
        idf = {
            term: math.log((total + 1) / (frequency + 1)) + 1.0
            for term, frequency in document_frequency.items()
        }
        vectors: dict[str, dict[str, float]] = {}
        for chunk_id, tokens in token_lists.items():
            counts = Counter(tokens)
            weights = {
                term: (1 + math.log(count)) * idf[term]
                for term, count in counts.items()
            }
            vectors[chunk_id] = self._normalize(weights)
        self._sparse[paper_id] = vectors
        self._idf[paper_id] = idf

        # 稠密embedding：优先复用签名匹配的持久化结果，否则调用接口重新嵌入
        self._dense.pop(paper_id, None)
        if self.remote_enabled:
            cached = self._load_persisted_dense(paper_id, signature)
            if cached is not None:
                self._dense[paper_id] = cached
                logger.info("复用持久化embedding向量：paper_id=%s", paper_id)
            else:
                dense = self._embed_remote(
                    [chunk.content[: self.EMBEDDING_INPUT_CHARS] for chunk in chunks]
                )
                if dense is not None and len(dense) == len(chunks):
                    self._dense[paper_id] = {
                        chunk.chunk_id: vector
                        for chunk, vector in zip(chunks, dense)
                    }
                    logger.info("已生成embedding向量：paper_id=%s，%d个切片", paper_id, total)

        # 配置了远程embedding但本次没拿到稠密向量（接口失败/回退）时，不要用空向量
        # 覆盖已持久化的有效embedding——否则一次网络抖动就会摧毁缓存、逼迫全量重嵌。
        embedding_expected_but_missing = self.remote_enabled and paper_id not in self._dense
        if not embedding_expected_but_missing:
            self._persist(paper_id, chunks, signature)

    def search(self, paper_id: str, query: str) -> dict[str, float]:
        """返回 {chunk_id: 余弦相似度}，供知识库做融合重排序。"""
        query = query.strip()
        if not query:
            return {}
        if paper_id in self._dense:
            scores = self._search_dense(paper_id, query)
            if scores is not None:
                return scores
            # 远程查询向量失败时回退本地TF-IDF，保证检索接口不因外部服务中断
        return self._search_sparse(paper_id, query)

    def remove(self, paper_id: str) -> None:
        self._sparse.pop(paper_id, None)
        self._idf.pop(paper_id, None)
        self._dense.pop(paper_id, None)
        path = self._persist_path(paper_id)
        if path is not None:
            path.unlink(missing_ok=True)

    # ---- 本地TF-IDF ----

    def _search_sparse(self, paper_id: str, query: str) -> dict[str, float]:
        vectors = self._sparse.get(paper_id)
        idf = self._idf.get(paper_id)
        if not vectors or not idf:
            return {}
        counts = Counter(self._tokenize(query))
        weights = {
            term: (1 + math.log(count)) * idf[term]
            for term, count in counts.items()
            if term in idf
        }
        if not weights:
            return {}
        query_vector = self._normalize(weights)
        scores: dict[str, float] = {}
        for chunk_id, vector in vectors.items():
            score = self._cosine_sparse(query_vector, vector)
            if score > 0:
                scores[chunk_id] = score
        return scores

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        lowered = text.lower()
        tokens = re.findall(r"[a-z0-9_]{2,}", lowered)
        chinese = re.findall(r"[一-鿿]", lowered)
        # 中文使用二元组，兼顾术语区分度与召回率
        tokens.extend(
            chinese[index] + chinese[index + 1]
            for index in range(len(chinese) - 1)
        )
        if len(chinese) == 1:
            tokens.append(chinese[0])
        return tokens

    @staticmethod
    def _normalize(weights: dict[str, float]) -> dict[str, float]:
        norm = math.sqrt(sum(value * value for value in weights.values()))
        if norm == 0:
            return {}
        return {term: value / norm for term, value in weights.items()}

    @staticmethod
    def _cosine_sparse(left: dict[str, float], right: dict[str, float]) -> float:
        if len(left) > len(right):
            left, right = right, left
        return sum(value * right.get(term, 0.0) for term, value in left.items())

    # ---- 远程embedding（可选） ----

    def _embed_remote(self, texts: list[str]) -> list[list[float]] | None:
        if not texts:
            return []
        try:
            headers = {"Content-Type": "application/json"}
            if self.embedding_api_key:
                headers["Authorization"] = f"Bearer {self.embedding_api_key}"
            results: list[list[float]] = []
            with httpx.Client(
                timeout=httpx.Timeout(60, connect=15),
                transport=self._transport,
            ) as client:
                # 分批请求，避免一次性提交过多切片超出服务端限制
                for start in range(0, len(texts), self.EMBEDDING_BATCH_SIZE):
                    batch = texts[start : start + self.EMBEDDING_BATCH_SIZE]
                    response = client.post(
                        f"{self.embedding_api_url}/embeddings",
                        headers=headers,
                        json={"model": self.embedding_model, "input": batch},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    items = sorted(payload["data"], key=lambda item: item.get("index", 0))
                    results.extend(item["embedding"] for item in items)
            return results
        except Exception as exc:  # noqa: BLE001 - 任意失败都必须回退本地向量
            logger.warning("Embedding接口调用失败，回退本地TF-IDF向量：%s", exc)
            return None

    def _search_dense(self, paper_id: str, query: str) -> dict[str, float] | None:
        embedded = self._embed_remote([query[: self.EMBEDDING_INPUT_CHARS]])
        if not embedded:
            return None
        query_vector = embedded[0]
        norm = math.sqrt(sum(value * value for value in query_vector))
        if norm == 0:
            return None
        scores: dict[str, float] = {}
        for chunk_id, vector in self._dense[paper_id].items():
            chunk_norm = math.sqrt(sum(value * value for value in vector))
            if chunk_norm == 0:
                continue
            dot = sum(a * b for a, b in zip(query_vector, vector))
            score = dot / (norm * chunk_norm)
            if score > 0:
                scores[chunk_id] = score
        return scores

    # ---- 持久化与复用 ----

    @staticmethod
    def _signature(chunks: list[PaperChunk]) -> str:
        """按切片ID与内容生成内容签名，用于判断持久化向量是否仍然有效。"""
        digest = hashlib.sha256()
        for chunk in chunks:
            digest.update(chunk.chunk_id.encode("utf-8"))
            digest.update(b"\x00")
            digest.update(chunk.content.encode("utf-8"))
            digest.update(b"\x00")
        return digest.hexdigest()[:16]

    def _persist_path(self, paper_id: str) -> Path | None:
        if self.persist_dir is None:
            return None
        return self.persist_dir / f"{paper_id}.vectors.json"

    def _load_persisted_dense(
        self,
        paper_id: str,
        signature: str,
    ) -> dict[str, list[float]] | None:
        """读取持久化的稠密向量；签名或embedding模型不一致时视为失效。"""
        path = self._persist_path(paper_id)
        if path is None or not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if payload.get("signature") != signature:
            return None
        if payload.get("embedding_model") != self.embedding_model:
            return None
        dense = payload.get("dense")
        if not isinstance(dense, dict) or not dense:
            return None
        try:
            return {
                chunk_id: [float(value) for value in vector]
                for chunk_id, vector in dense.items()
            }
        except (TypeError, ValueError):
            return None

    def _persist(self, paper_id: str, chunks: list[PaperChunk], signature: str) -> None:
        path = self._persist_path(paper_id)
        if path is None:
            return
        dense = self._dense.get(paper_id, {})
        payload = {
            "paper_id": paper_id,
            "backend": self.backend_name(paper_id),
            # 只有稠密向量存在时才记录模型，供复用时校验模型一致性
            "embedding_model": self.embedding_model if dense else "",
            "signature": signature,
            "chunk_count": len(chunks),
            "vocabulary_size": len(self._idf.get(paper_id, {})),
            # 只持久化昂贵的稠密向量；稀疏TF-IDF廉价、每次内存重建
            "dense": {
                chunk_id: [round(value, 6) for value in vector]
                for chunk_id, vector in dense.items()
            },
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(path)
