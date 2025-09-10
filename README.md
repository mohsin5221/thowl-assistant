# TH-OWL Assistant — Architecture (C4)

This document describes the TH-OWL Assistant using the **C4 model** (C1→C4), plus key sequence diagrams.  
Codebase (today):
- `app/streamlit_app.py` — Chat UI (Streamlit), admin-only indexing, “edit latest answer”, sources.
- `retrieval.py` — Crawl -> chunk -> **TF-IDF** index build; search; shallow link discovery.
- `llm.py` — OpenAI wrapper (`ask_llm`, `translate`), language detection & retries.

Artifacts (persisted):
- `data/cache/chunks.csv`
- `data/cache/tfidf_vectorizer.joblib`
- `data/cache/tfidf_matrix.joblib`
- `data/raw_html/*`, `data/raw_pdf/*`

---

## C1 — System Context

![C1 System Context](./C1_SystemContext.png)

**Summary**
- Users chat via browser.
- App answers via OpenAI (grounded by retrieved chunks from official TH-OWL docs).
- Admin can rebuild the index from `seeds.txt`.
- Secrets (`OPENAI_API_KEY`, `ADMIN_TOKEN`) come from env or Streamlit Secrets.

---

## C2 — Containers

![C2 Containers](./C2_containers.png)

**Containers & responsibilities**
- **Streamlit App (Python)**: chat UI, session state, admin sidebar, orchestration.
- **Retrieval (Python)**: crawl, clean, chunk, TF-IDF (scikit-learn), search.
- **LLM Client (Python)**: prompt construction, language policy, translation.
- **Index store (files)**: persisted chunks + TF-IDF artifacts.
- **External systems**: TH-OWL Docs (content), OpenAI API (LLM), Secrets/Env (config).

**Tech choices**
- Streamlit (UI), scikit-learn (TF-IDF), BeautifulSoup/pdfplumber (extraction), OpenAI Python SDK.

---

## C3 — Components

![C3 Components](./C3_Components.png)

**App components**
- **Chat Layer**: `st.chat_message/input`; renders sources; only the *latest* assistant answer is editable.
- **Session Orchestrator**: manages `messages[]`, edit state, reruns.
- **Admin Sidebar**: reads `seeds.txt`, controls `follow`, `allowed_prefix`, `max_links`, triggers rebuild.

**Retrieval components**
- **Fetchers**: `fetch_html`, `fetch_pdf` (store raw copies).
- **Link Discovery**: `discover_links`, `expand_seeds` (depth-1; prefix-constrained).
- **Indexer**: `_chunk_text`, language detection, TF-IDF fit; writes artifacts.
- **Searcher**: `load_index`, `search` (cosine similarity, same-language preference).

**LLM components**
- **ask_llm**: grounded answering; strict output-language policy.
- **translate**: quick language conversion for retrieval or answer enforcement.
- **Client**: `_get_client`, `_get_api_key`, retry helper.

---

## C4 — Code/Functions (selected)

### `retrieval.py`
| Function | Purpose |
|---|---|
| `expand_seeds(seeds, follow, allowed_prefixes, max_links)` | Build URL list; depth-1 discovery with prefix constraints. |
| `fetch_html(url) / fetch_pdf(url)` | Fetch + clean text; cache raw HTML/PDF. |
| `_chunk_text(text, 1200, 200)` | Overlapping chunks for retrieval. |
| `build_index_from_seeds(...) -> (vectorizer, X, df)` | Crawl, chunk, detect lang, **TF-IDF fit**, persist. |
| `load_index() -> (vectorizer, X, df)` | Load artifacts from cache. |
| `search(query, top_k)` | TF-IDF cosine; bias to user’s language; return top chunks with url+score. |

### `llm.py`
| Function | Purpose |
|---|---|
| `ask_llm(user_text, context, force_lang_code)` | Build messages, call OpenAI, enforce output language, handle no-context & errors. |
| `translate(text, target_code)` | Translate via OpenAI (no-op if already in target). |
| `_detect_lang_code`, `_shrink_context`, `_retry` | Utilities for robustness & policy. |

### `app/streamlit_app.py` (key flows)
- Admin gating: `?admin=ADMIN_TOKEN` (hide sidebar for non-admin).
- Rebuild index: calls `retrieval.build_index_from_seeds(...)`.
- Q&A: `retrieval.search(...)` → join chunks as context → `llm.ask_llm(...)`.
- Edit latest answer only: `editable=True` on newest assistant message; save/cancel.

---

## Sequences

### User question
![Sequence — User Question](.<img width="846" height="368" alt="SEQ_Admin" src="https://github.com/user-attachments/assets/2b7471a5-f911-4114-aac6-3bf4b3d13637" />
)

### Admin rebuild
![Sequence — Admin Rebuild](.<img width="716" height="355" alt="SEQ_UserQuestions" src="https://github.com/user-attachments/assets/551429da-1d48-4e1c-bffb-0d2650048909" />
)

---

## Quality Attributes

- **Accuracy**: Answers are grounded in retrieved chunks; same-language bias; sources shown.
- **Usability**: Simple chat; “edit latest answer”; admin tools hidden from end users.
- **Performance**: TF-IDF is fast for small/medium corpora; persisted artifacts avoid refits on start.
- **Maintainability**: Retrieval and LLM concerns split into separate modules; diagrams + doc here.
- **Reliability**: Retry wrapper for LLM; skips bad URLs; caches raw sources for debugging.

---


---


---

## Operational Notes

- **Secrets**: set `OPENAI_API_KEY`, `ADMIN_TOKEN` (env or `.streamlit/secrets.toml`).  
- **Indexing**: put URLs in `seeds.txt`, set **Allowed prefix**, toggle **Follow links**, click **Rebuild**.  
- **Running locally**: `streamlit run app/streamlit_app.py`.

---


---

## Glossary

- **Chunk**: A fixed-size slice of page text used for retrieval.  
- **Context**: Concatenation of top-K chunks passed to the LLM.  
- **TF-IDF**: Term Frequency–Inverse Document Frequency vectorizer for lexical search.

