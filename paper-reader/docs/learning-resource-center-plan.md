# Learning Resource Center Plan

## 1. Product decision

The current `视频资源` module should evolve into a source-grounded `学习资源` center. It should keep curated Bilibili links/search entries, but recommendations must no longer be limited to locally maintained metadata. For a selected paper or a user question, the center should be able to find and explain:

- related papers and surveys;
- high-quality videos and courses;
- official documentation, tutorials, and other text resources;
- curated links that the user has already collected.

The navigation label should change only after the generalized resource API and UI are available. Until then, keeping `视频资源` avoids presenting planned scope as a shipped capability.

## 2. Current constraints

- Paper and derived data are stored in JSON files.
- Video records live in `data/videos/catalog.json`.
- Video recommendation uses substring matching over maintained metadata only; it does not search external sources, subtitles, transcripts, or semantic vectors.
- The PaperPilot Compose file currently runs the frontend and backend but no project-owned database.
- A PostgreSQL container owned by another Compose project must not be reused. PaperPilot needs its own database, volume, credentials, migrations, and lifecycle.

JSON remains useful as a migration source and local-file fallback, but it is not suitable for concurrent writes, relationships between papers and resources, hybrid search, or durable recommendation history.

## 3. Target architecture

```text
Reader / chat / resource-center query
                |
                v
        Resource Query Service
        - intent and concept extraction
        - paper-context assembly
                |
       +--------+---------+----------------+
       |                  |                |
       v                  v                v
 Curated resource    Paper providers   Media/text providers
 repository          OpenAlex          Bilibili search
                     Crossref          curated web adapters
                     Semantic Scholar
       |                  |                |
       +--------+---------+----------------+
                v
       Normalize and deduplicate
       DOI / canonical URL / content hash
                v
       PostgreSQL + pgvector
       full-text + vector hybrid retrieval
                v
       rerank + AI explanation
       with source URLs and reasons
                v
       resource cards / chat citations
```

The LLM must not invent resources. It plans queries, reranks normalized candidates, and explains relevance, while every result retains provider metadata and a resolvable source URL.

## 4. Docker and storage design

Add a project-owned `db` service based on `pgvector/pgvector:pg16`:

- container name: `paperpilot-postgres`;
- private Compose network shared only by PaperPilot services;
- named volume: `paperpilot_pgdata`;
- health check with `pg_isready`;
- database credentials supplied through `.env`, not committed;
- backend waits for the database health check;
- Alembic performs schema migrations.

Large PDFs, thumbnails, and generated assets should remain in the mounted data directory or future object storage. PostgreSQL stores metadata, extracted text, hashes, links, job state, and embeddings; it should not become a binary-file bucket.

Introduce a repository interface so the application can migrate from JSON without rewriting agents and routes:

```text
PaperRepository
ResourceRepository
RecommendationRepository
```

During migration, an idempotent command imports `papers.json`, derived records, and `videos/catalog.json`, preserving existing IDs and file paths. A migration report records imported, skipped, and conflicting rows.

## 5. Core data model

### `learning_resources`

- `id` UUID primary key
- `resource_type`: `paper`, `video`, `course`, `web`, `documentation`, `local_file`
- `title`, `abstract_or_summary`, `language`
- `provider`: `curated`, `openalex`, `crossref`, `semantic_scholar`, `bilibili`, etc.
- `provider_id`, `canonical_url`, `doi`
- `authors` JSONB, `published_at`
- `thumbnail_url`, `source_url`, `mime_type`
- `content_text` or searchable transcript/abstract
- `metadata` JSONB for provider-specific fields
- `content_hash`, `status`, `created_at`, `updated_at`
- `embedding` vector, nullable until embedding generation completes

### Relationship and operational tables

- `resource_topics`: normalized concepts, tags, and knowledge points.
- `paper_resource_links`: links a paper to a resource with relevance score, explanation, and supporting page/chunk IDs.
- `resource_queries`: original query, selected paper, normalized intent, provider status, latency, and cache key.
- `resource_query_results`: ranked candidates, component scores, and final position.
- `resource_feedback`: save, dismiss, useful/not-useful, and click signals.
- `ingestion_jobs`: provider fetch, text extraction, embedding, retry count, and error state.

Unique constraints should cover provider/provider ID, normalized DOI, canonical URL, and content hash where present.

## 6. Retrieval and recommendation flow

1. Build context from the user query, paper title/abstract, guide, and the most relevant indexed chunks.
2. Use the LLM to produce a small structured query plan: concepts, resource types, language, difficulty, and freshness needs.
3. Search local PostgreSQL full-text indexes immediately.
4. Call enabled providers in parallel through adapters with timeouts, quotas, and per-provider circuit breakers.
5. Normalize and deduplicate results before the LLM sees them.
6. Store/cache normalized candidates and generate missing embeddings asynchronously.
7. Use hybrid ranking:
   - lexical relevance;
   - vector similarity;
   - paper-context overlap;
   - source quality and metadata completeness;
   - recency only when the query requires it;
   - user feedback.
8. Ask the LLM to explain the top results using only stored candidate fields and paper evidence.
9. Return source URL, provider, resource type, relevance reason, and the paper chunks/pages that triggered the recommendation.

The initial release can run PostgreSQL full-text search before embeddings are ready. This keeps the system usable while the embedding provider remains configurable.

## 7. Provider strategy

- OpenAlex: primary discovery source for papers, authors, concepts, and related works.
- Crossref: DOI and publication metadata verification/supplement.
- Semantic Scholar: optional citation/relevance enrichment when an API key is configured.
- Bilibili search: no API key required; provide traceable search URLs and curated links.
- Curated resources: always available and ranked alongside external results.
- Web text: start with explicitly configured and attributable provider adapters. Avoid unrestricted scraping as the first implementation.

All provider credentials remain backend-only. The frontend receives provider availability and rate-limit status, never secrets.

## 8. API surface

- `GET /api/resources`: filter and paginate the local resource library.
- `POST /api/resources`: register or upload a generalized resource.
- `PATCH /api/resources/{id}` and `DELETE /api/resources/{id}`.
- `POST /api/resources/search`: deterministic local/provider search without an AI narrative.
- `POST /api/resources/recommend`: paper-aware AI query planning, ranking, and explanations.
- `GET /api/resources/queries/{id}`: query progress and partial provider results.
- `POST /api/resources/{id}/feedback`: save/useful/dismiss feedback.
- `GET /api/resources/providers/status`: configured providers, health, and quota state.

Long provider searches should return a query ID and stream or poll partial results rather than holding one HTTP request open indefinitely.

## 9. UI direction

When the generalized API is ready, rename the navigation entry and component to `学习资源` / `LearningResourceCenter`.

The page should prioritize discovery over manual metadata entry:

- one paper-aware search box with example queries;
- tabs or filters for `全部`, `论文`, `文字/文档`, `视频/课程`, and `收藏链接`;
- result cards with title, type, source, date, language, and `为什么推荐`;
- visible source link and paper evidence/page chips;
- save, dismiss, and feedback actions;
- a secondary `添加收藏链接` dialog instead of a full-page upload form;
- provider status and an explicit fallback message when external search is unavailable.

Chat recommendations should consume the same resource service so the chat panel and resource center never use different ranking rules.

## 10. Delivery phases

### P0 - Persistence foundation

- Add project-owned PostgreSQL/pgvector Compose service.
- Add SQLAlchemy repository layer and Alembic.
- Create generalized resource tables.
- Import existing JSON papers and video catalogue.
- Preserve current APIs through compatibility adapters.

Acceptance: existing upload, reading, chat, translation, mind map, and Bilibili video flows pass against PostgreSQL; migration is repeatable and reports conflicts.

### P1 - Generalized local resource center

- Replace video-only schemas and routes with resource equivalents.
- Add PostgreSQL full-text search, filters, pagination, deduplication, and job tracking.
- Move local resource creation into a dialog and ship the generalized result-card UI.

Acceptance: users can add and retrieve papers, documents, links, and Bilibili video entries from one interface; no external provider credential is required.

### P2 - Paper discovery and AI explanation

- Add OpenAlex and Crossref adapters, with optional Semantic Scholar enrichment.
- Add structured AI query planning and source-grounded relevance explanations.
- Link recommendations to paper pages/chunks and expose them in chat.

Acceptance: a paper-aware query returns deduplicated related papers with working source links and inspectable recommendation reasons; provider failure degrades to local search.

### P3 - Video, course, and text discovery

- Add Bilibili search shortcuts and configured text/documentation providers.
- Add transcripts/snippets where licensing and provider terms permit.
- Enable vector embeddings and hybrid reranking.
- Add cache expiry, quotas, retries, and provider observability.

Acceptance: mixed resource types appear in one ranked result set, can be filtered, and retain provider provenance.

### P4 - Quality and personalization

- Use saves, dismissals, and useful/not-useful feedback in ranking.
- Add evaluation sets for relevance, duplicate rate, broken links, latency, and hallucinated-resource rate.
- Add collections, export, alerts, and multi-paper project spaces after retrieval quality is stable.

## 11. Recommended next implementation slice

Start with P0 only. It creates the stable storage boundary required by every later feature and avoids coupling external API work to the current JSON catalogue. The first pull request should contain Compose/database migrations, repositories, and JSON import tests, but no UI rename and no external provider integration.
