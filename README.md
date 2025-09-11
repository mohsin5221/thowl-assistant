# TH-OWL Assistant

Codebase :
- `app/streamlit_app.py` — Chat UI (Streamlit), admin-only indexing, “edit latest answer”, sources.
- `retrieval.py` — Crawl -> chunk -> **TF-IDF** index build; search; shallow link discovery.
- `llm.py` — OpenAI wrapper (`ask_llm`, `translate`), language detection & retries.

Artifacts:
- `data/cache/chunks.csv`
- `data/cache/tfidf_vectorizer.joblib`
- `data/cache/tfidf_matrix.joblib`
- `data/raw_html/*`, `data/raw_pdf/*`

---

## C1 — System Context

**Summary**
- Users chat via browser.
- App answers via OpenAI (grounded by retrieved chunks from official TH-OWL docs).
- Admin can rebuild the index from `seeds.txt`.
- Secrets (`OPENAI_API_KEY`, `ADMIN_TOKEN`) come from env or Streamlit Secrets.

---

## C2 — Containers

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
![Sequence — User Question](.<img width="716" height="355" alt="SEQ_UserQuestions" src="https://github.com/user-attachments/assets/551429da-1d48-4e1c-bffb-0d2650048909" />
)

### Admin rebuild
![Sequence — Admin Rebuild](.<img width="846" height="368" alt="SEQ_Admin" src="https://github.com/user-attachments/assets/2b7471a5-f911-4114-aac6-3bf4b3d13637"/>
)

---

## Quality Attributes

- **Accuracy**: Answers are grounded in retrieved chunks; same-language bias; sources shown.
- **Usability**: Simple chat; “edit latest answer”; admin tools hidden from end users.
- **Performance**: TF-IDF is fast for small/medium corpora; persisted artifacts avoid refits on start.
- **Maintainability**: Retrieval and LLM concerns split into separate modules; diagrams + doc here.
- **Reliability**: Retry wrapper for LLM; skips bad URLs; caches raw sources for debugging.

---

## Operational Notes

- **Secrets**: set `OPENAI_API_KEY`, `ADMIN_TOKEN` (env or `.streamlit/secrets.toml`).  
- **Indexing**: put URLs in `seeds.txt`, set **Allowed prefix**, toggle **Follow links**, click **Rebuild**.  
- **Running locally**: `streamlit run app/streamlit_app.py`.


---

## Glossary

- **Chunk**: A fixed-size slice of page text used for retrieval.  
- **Context**: Concatenation of top-K chunks passed to the LLM.  
- **TF-IDF**: Term Frequency–Inverse Document Frequency vectorizer for lexical search.

## 🚀 Run the project locally

### 0) Prerequisites
- Python **3.10+** (3.11 recommended)  
- Dependencies installed: `pip install -r requirements.txt`  
- Secrets configured (see **Configuration** above): `OPENAI_API_KEY` (required), `ADMIN_TOKEN` (optional)

> On Windows (PowerShell), activate the venv with:
> ```
> .venv\Scripts\Activate.ps1
> ```

### 1) Start the app
From the **repo root**:
```bash
streamlit run app/streamlit_app.py
```
Open the URL Streamlit prints (usually `http://localhost:8501`).

### 2) (Optional) Admin mode — build / rebuild the index
Open with your admin token to reveal the indexing sidebar:
```
http://localhost:8501/?admin=YOUR_ADMIN_TOKEN
```
In the sidebar:
- **Allowed prefix** (recommended):  
  - `https://www.th-owl.de/skim/dokumentation/`  
  - *(If you also crawl English pages add: `https://www.th-owl.de/en/skim/documentation/`)*
- **Follow links under same path**: ✓ (depth-1 discovery)  
- **Max links per seed**: 12–20  
- Click **🔁 Rebuild index from seeds.txt**

Artifacts are written to `data/cache/` (`chunks.csv`, `tfidf_vectorizer.joblib`, `tfidf_matrix.joblib`), with raw sources in `data/raw_html/` and `data/raw_pdf/`.

### 3) Seeds (what gets crawled)
Edit `seeds.txt` (one URL per line, `#` for comments). Prefer canonical SKiM doc pages; avoid fragment anchors like `#tab-…` (often JS-rendered).

Example:
```txt
https://www.th-owl.de/skim/dokumentation/
https://www.th-owl.de/en/skim/documentation/
# Add specific topics (CampusCard, eduroam, etc.) as needed
```

### 4) Stop the server
Press **Ctrl+C** in the terminal.

## 🧪 Troubleshooting

- **“No secrets found” / missing API key**  
  Create a `.env` or `./.streamlit/secrets.toml` with `OPENAI_API_KEY` (and `ADMIN_TOKEN` if you use admin mode).

- **“Index not built yet”**  
  Open admin mode and click **Rebuild index**. Confirm your **Allowed prefix** matches the site you seeded.

- **`ModuleNotFoundError: retrieval / llm`**  
  Run from the **repo root**:
  ```bash
  streamlit run app/streamlit_app.py
  ```

- **App starts but answers look wrong / sparse**  
  Seed the canonical EN/DE documentation pages; keep **Follow links** enabled; raise **Max links per seed** and rebuild.
