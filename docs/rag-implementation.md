# RAG implementation

Code: `app/rag/` (chunker, embeddings, vector_store, pgvector_store, pipeline) · knowledge base: `app/rag/knowledge/*.md`.

## Pipeline
1. **Load** — seed copies the Markdown files into `knowledge_documents` (title, category from `<!-- category: x -->`, checksum).
2. **Split** — `split_text()` removes comments, glues headings to their paragraph, packs paragraphs across sections into
   ~`RAG_CHUNK_SIZE` (600) character chunks, splits oversized paragraphs on sentence boundaries, carries `RAG_CHUNK_OVERLAP` (80) characters.
3. **Embed** — `HashingEmbedder` (demo; deterministic signed feature hashing of stemmed unigrams+bigrams, L2-normalised, 384 dims)
   or `OpenAIEmbedder` (`text-embedding-3-small` with `dimensions=384`, so the column type never changes).
4. **Store** — `knowledge_chunks.embedding vector(384)` with an HNSW `vector_cosine_ops` index (PostgreSQL); JSON on SQLite.
   Product descriptions/specs are indexed too, with `category="product"` metadata, powering semantic product search.
5. **Query embedding** + **retrieve** — `cosine_distance` ordering in SQL (Python cosine on SQLite), top `k×3` candidates, a light
   lexical re-rank that rewards query terms in the document title, then top `RAG_TOP_K` (4).
6. **Metadata filtering** — support answers filter to KB categories (never product blurbs); product search filters to `product`.
7. **Generate** — OpenAI: documents are wrapped as quoted data (`wrap_untrusted`) and the model must answer only from them or
   say `NO_ANSWER`. Mock: an **extractive** answer — the sentences with the most query overlap, in document order, each cited `[n]`.
8. **Sources** — every answer returns `{id, title, source, score, excerpt}` and the UI shows them.

## Never inventing policy
If the best chunk scores below `RAG_MIN_SCORE` (0.10 for the hashing embedder; ~0.30 recommended for OpenAI embeddings),
the answer is the fixed fallback *"I couldn't find a reliable answer … I don't want to guess"* with an offer to escalate, and
`grounded=false`. Tested: `test_unknown_question_returns_fallback_not_invention`.

## Tested retrieval (build environment, hashing embedder)
| Question | Top source | Fact in answer |
|---|---|---|
| What is your return policy? | return-policy | "10 days" |
| My payment failed but money was deducted | payment-faq | "5 to 7 working days" |
| What warranty do laptops have? | warranty | "one-year" |
| Is shipping free? | shipping-policy | "₹999" |
| Can I cancel my order after it is packed? | order-cancellation | "packed" |
| What is the melting point of tungsten carbide? | — | fallback, no sources |

## Limits (honest)
The hashing embedder is lexical, so paraphrases with no shared words ("How long until it arrives in Delhi?") can fall below the
threshold and get the fallback. That is the safe failure. Switching to OpenAI embeddings fixes recall without code changes.
