import os
import streamlit as st
from langdetect import detect

# local imports
from llm import ask_llm, translate
import retrieval

# --------- Admin detection & sidebar control ----------
def get_query_param(name: str):
    # Works on both newer & older Streamlit versions
    try:
        return st.query_params.get(name)
    except Exception:
        return st.experimental_get_query_params().get(name)

ADMIN_TOKEN = st.secrets.get("ADMIN_TOKEN") or os.getenv("ADMIN_TOKEN")
admin_param = get_query_param("admin")
admin_mode = bool(ADMIN_TOKEN and admin_param and admin_param == ADMIN_TOKEN)

# Collapsed by default; we’ll fully hide the sidebar for non-admin.
st.set_page_config(
    page_title="TH OWL Assistant (MVP)",
    page_icon="🎓",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Hide the sidebar & its toggle for non-admin users
if not admin_mode:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="stSidebarNav"] { display: none !important; }
        button[kind="header"] { display: none !important; } /* hide top-right hamburger if present */
        </style>
        """,
        unsafe_allow_html=True,
    )

# --------- App UI ----------
st.title("🎓 TH OWL Assistant — MVP")
st.caption("Skip the Website, Ask the Chatbot.")

# --- Admin-only sidebar: index controls ---
if admin_mode:
    with st.sidebar:
        st.header("Index (Admin)")
        st.write("1) Put URLs in seeds.txt\n2) Click rebuild\n3) Ask questions")

        follow = st.checkbox("Follow links under same path (depth 1)", value=True)
        prefix = st.text_input(
            "Allowed prefix",
            value="https://www.th-owl.de/skim/dokumentation/",
            help="Only crawl links that start with this prefix."
        )
        max_links = st.number_input("Max links per seed", min_value=5, max_value=50, value=12, step=1)

        if st.button("🔁 Rebuild index from seeds.txt"):
            with st.spinner("Building index (fetching pages, PDFs)..."):
                try:
                    # Cache-friendly: keep references to reduce rebuilds in the same session
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
    placeholder="e.g. “How do I connect to Wi-Fi on Windows?“",
)

c1, c2 = st.columns([1,1])
with c1:
    ask = st.button("Ask")

if ask:
    if not user_q.strip():
        st.warning("Please enter a question.")
    else:
        # Detect question language
        try:
            q_lang = detect(user_q).split("-")[0]
        except Exception:
            q_lang = "en"

        # Translate to English for retrieval if needed
        query_for_search = user_q if q_lang == "en" else translate(user_q, target_code="en")

        # Retrieve top chunks (gracefully handle missing index)
        try:
            hits = retrieval.search(query_for_search, top_k=3)
            context = "\n---\n".join(h["chunk_text"] for h in hits)
        except Exception:
            hits, context = [], ""

        # Ask LLM with original user_q + English context
        with st.spinner("Thinking..."):
            try:
                forced = LANG_OPTIONS[sel]
                st.session_state.answer = ask_llm(user_q, context=context, force_lang_code=forced)
            except Exception as e:
                st.session_state.answer = f"Error: {e}"

        # Sources (if any)
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

# Key presence hint
if not (os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY", None)):
    st.warning("OPENAI_API_KEY not found. Create a .env file or add it in Streamlit Secrets.")
