import os
import streamlit as st
from langdetect import detect

# local imports from same folder
from llm import ask_llm, translate          # translate already imported ✅
import retrieval

st.set_page_config(page_title="TH OWL Assistant (MVP)", page_icon="🎓", layout="centered")

st.title("🎓 TH OWL Assistant — MVP")
st.caption("Multilingual answers grounded in official TH-OWL pages. Answers are editable.")

# --- Sidebar: index controls ---
with st.sidebar:
    st.header("Index")
    st.write("1) Put URLs in seeds.txt\n2) Click rebuild\n3) Ask questions")

    follow = st.checkbox("Follow links under same path (depth 1)", value=True)
    # If your seeds are English, consider setting the default to the EN docs prefix:
    # e.g. "https://www.th-owl.de/en/skim/documentation/"
    prefix = st.text_input("Allowed prefix", value="https://www.th-owl.de/skim/dokumentation/")
    max_links = st.number_input("Max links per seed", min_value=5, max_value=50, value=12, step=1)

    if st.button("🔁 Rebuild index from seeds.txt"):
        with st.spinner("Building index (fetching pages, PDFs)..."):
            try:
                vec, X, df = retrieval.build_index_from_seeds(
                    "seeds.txt",
                    follow_links=follow,
                    allowed_prefixes=[prefix] if prefix else [],
                    max_links_per_seed=int(max_links),
                )
                st.success(f"Indexed {len(df)} content chunks from official pages.")
                st.toast("Index built")
            except Exception as e:
                st.error(f"Index build failed: {e}")

# --- Main Q&A section ---
# Language override (optional)
LANG_OPTIONS = {
    "Auto (match question)": None,
    "English": "en",
    "Deutsch": "de",
    "Français": "fr",
    "Español": "es",
}
sel = st.selectbox("Answer language", list(LANG_OPTIONS.keys()), index=0)

user_q = st.text_input(
    "Your question",
    placeholder="e.g. “How Do I connect to wifi on windows?“",
)

c1, c2 = st.columns([1,1])
with c1:
    ask = st.button("Ask")


if ask:
    if not user_q.strip():
        st.warning("Please enter a question.")
    else:
        # NEW: detect user question language
        try:
            q_lang = detect(user_q).split("-")[0]
        except Exception:
            q_lang = "en"

        # NEW: pre-translate the query to English for TF-IDF retrieval if your index is English
        query_for_search = user_q
        if q_lang != "en":
            query_for_search = translate(user_q, target_code="en")

        # 1) Retrieve top chunks (if index exists) using the (possibly translated) query
        try:
            hits = retrieval.search(query_for_search, top_k=3)   # NEW: use query_for_search
            context = "\n---\n".join(h["chunk_text"] for h in hits)
        except Exception:
            hits, context = [], ""

        # 2) Ask LLM with ORIGINAL user_q (any language) + English context
        with st.spinner("Thinking..."):
            try:
                forced = LANG_OPTIONS[sel]
                # ask_llm will translate context into the output language as needed
                st.session_state.answer = ask_llm(user_q, context=context, force_lang_code=forced)
            except Exception as e:
                st.session_state.answer = f"Error: {e}"

        # 3) Show sources (nice for trust)
        if hits:
            st.markdown("**Sources (top):**")
            for h in hits:
                st.write(f"- {h['url']}  (score: {h['score']:.3f}, lang: {h['lang']})")
        else:
            st.caption("No matching official context found. The assistant may say it doesn't know.")

# Editable answer area
st.subheader("Editable answer")
st.session_state.answer = st.text_area(
    "You can refine the text below before copying:",
    value=st.session_state.get("answer", ""),
    height=240,
)

# key presence hint
if not (os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY", None)):
    st.warning("OPENAI_API_KEY not found. Create a .env file or add it in Streamlit Secrets.")
