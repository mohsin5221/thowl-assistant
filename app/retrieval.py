from __future__ import annotations
import os, re, time
from pathlib import Path
from typing import List, Dict, Tuple

import requests
from bs4 import BeautifulSoup
import pdfplumber
import pandas as pd

from langdetect import detect, DetectorFactory
DetectorFactory.seed = 0

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import joblib
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_HTML = DATA_DIR / "raw_html"
RAW_PDF  = DATA_DIR / "raw_pdf"
CACHE    = DATA_DIR / "cache"
for d in (RAW_HTML, RAW_PDF, CACHE):
    d.mkdir(parents=True, exist_ok=True)

VEC_PATH   = CACHE / "tfidf_vectorizer.joblib"
MTRX_PATH  = CACHE / "tfidf_matrix.joblib"
CHUNKS_CSV = CACHE / "chunks.csv"

HEADERS = {"User-Agent": "TH-OWL-Assistant"}

# ----------------- helpers -----------------
def _sanitize_filename(url: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_.-]", "_", url)
    return base[:150]

def _clean_text(txt: str) -> str:
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt

def _detect_lang(txt: str) -> str:
    try:
        code = detect(txt)
        return code.split("-")[0]
    except Exception:
        return "en"

def _chunk_text(txt: str, max_chars=1200, overlap=200) -> List[str]:
    chunks = []
    i = 0
    n = len(txt)
    step = max_chars - overlap
    if step <= 0:
        step = max_chars
    while i < n:
        chunk = txt[i:i+max_chars]
        if len(chunk.strip()) > 50:
            chunks.append(chunk.strip())
        i += step
    return chunks

def is_pdf_url(url: str) -> bool:
    return url.lower().endswith(".pdf")

# ----------------- fetchers -----------------
def fetch_html(url: str, timeout=20) -> str:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    RAW_HTML.joinpath(_sanitize_filename(url) + ".html").write_bytes(r.content)

    soup = BeautifulSoup(r.content, "lxml")
    # remove non-content elements
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    main = soup.find(["main", "article"])
    text = main.get_text(separator="\n") if main else soup.get_text(separator="\n")
    return _clean_text(text)

def fetch_pdf(url: str, timeout=30) -> str:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    pdf_path = RAW_PDF / (_sanitize_filename(url) + ".pdf")
    pdf_path.write_bytes(r.content)

    text_parts = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
    return _clean_text("\n".join(text_parts))

# ----------------- shallow link discovery -----------------
def discover_links(base_url: str, allowed_prefixes: list[str], limit: int = 12) -> list[str]:
    """Return up to `limit` links under the allowed prefixes found on base_url."""
    try:
        r = requests.get(base_url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(r.content, "lxml")

    def normalize(u: str) -> str:
        u = u.split("#")[0].strip()
        return u

    out = []
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        abs_url = normalize(urljoin(base_url, href))
        # skip non-http(s) and obvious assets
        if not abs_url.startswith(("http://", "https://")):
            continue
        if abs_url.endswith((".jpg",".jpeg",".png",".svg",".gif",".css",".js",".ico",".webp",".woff",".woff2",".ttf")):
            continue
        # keep only links under allowed prefixes
        if any(abs_url.startswith(p) for p in allowed_prefixes):
            if abs_url not in out:
                out.append(abs_url)
        if len(out) >= limit:
            break
    return out

def expand_seeds(seeds_file: Path | str,
                 follow_links: bool = False,
                 allowed_prefixes: list[str] | None = None,
                 max_links_per_seed: int = 12) -> list[str]:
    allowed_prefixes = allowed_prefixes or []
    seeds_path = Path(seeds_file)
    urls = []
    for line in seeds_path.read_text().splitlines():
        url = line.strip()
        if not url or url.startswith("#"):
            continue
        urls.append(url)
        if follow_links and allowed_prefixes:
            urls.extend(discover_links(url, allowed_prefixes, limit=max_links_per_seed))
    # de-dup while preserving order
    seen = set()
    deduped = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped

# ----------------- indexing -----------------
def build_index_from_seeds(seeds_file: Path | str,
                           follow_links: bool = False,
                           allowed_prefixes: list[str] | None = None,
                           max_links_per_seed: int = 12) -> Tuple[TfidfVectorizer, any, pd.DataFrame]:
    url_list = expand_seeds(seeds_file,
                            follow_links=follow_links,
                            allowed_prefixes=allowed_prefixes,
                            max_links_per_seed=max_links_per_seed)

    rows = []
    for url in url_list:
        try:
            if is_pdf_url(url):
                text = fetch_pdf(url)
                src_type = "pdf"
            else:
                text = fetch_html(url)
                src_type = "html"
        except Exception as e:
            print(f"[WARN] skipping {url}: {e}")
            continue

        if not text or len(text) < 80:
            continue

        lang = _detect_lang(text)
        chunks = _chunk_text(text, max_chars=1200, overlap=200)
        for idx, ch in enumerate(chunks):
            rows.append({
                "url": url,
                "source_type": src_type,
                "lang": lang,
                "chunk_index": idx,
                "chunk_text": ch
            })
        time.sleep(0.7)  # politeness

    if not rows:
        raise RuntimeError("No content extracted. Check your seeds and allowed prefixes.")

    df = pd.DataFrame(rows)
    df.to_csv(CHUNKS_CSV, index=False)

    vectorizer = TfidfVectorizer(
        ngram_range=(1,2),
        max_df=0.9,
        min_df=1,
        sublinear_tf=True
    )
    X = vectorizer.fit_transform(df["chunk_text"].tolist())

    joblib.dump(vectorizer, VEC_PATH)
    joblib.dump(X, MTRX_PATH)
    return vectorizer, X, df

def load_index() -> Tuple[TfidfVectorizer, any, pd.DataFrame]:
    if not (VEC_PATH.exists() and MTRX_PATH.exists() and CHUNKS_CSV.exists()):
        raise RuntimeError("Index not built yet. Click 'Rebuild index' or run build_index_from_seeds.")
    vectorizer = joblib.load(VEC_PATH)
    X = joblib.load(MTRX_PATH)
    df = pd.read_csv(CHUNKS_CSV)
    return vectorizer, X, df

# ----------------- search -----------------
def search(query: str, top_k=3) -> List[Dict]:
    vectorizer, X, df = load_index()

    try:
        q_lang = detect(query).split("-")[0]
    except Exception:
        q_lang = "en"

    q_vec = vectorizer.transform([query])
    sims = cosine_similarity(q_vec, X).ravel()

    df = df.copy()
    df["score"] = sims

    # Prefer same-language chunks; fallback if none
    same_lang = df[df["lang"] == q_lang]
    pool = same_lang if len(same_lang) >= max(1, top_k//2) else df

    top = pool.sort_values("score", ascending=False).head(top_k)
    results = []
    for _, row in top.iterrows():
        results.append({
            "url": row["url"],
            "lang": row["lang"],
            "score": float(row["score"]),
            "chunk_text": row["chunk_text"]
        })
    return results
