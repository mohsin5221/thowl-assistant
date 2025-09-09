# app/streamlit_app.py
# TH OWL Assistant — ChatGPT-style UI with editable latest answer

import os
import streamlit as st
from langdetect import detect

# Local modules you already have
from llm import ask_llm, translate
import retrieval

# ----------------------------
# Helpers
# ----------------------------
def secret_or_env(key: str, default=None):
    """Read from Streamlit secrets, else env var, without crashing when secrets.toml is missing."""
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)

def get_query_param(name: str):
    """Support both new and old Streamlit query param APIs."""
    try:
        return st.query_params.get(name)
    except Exception:
        return st.experimental_get_query_params().get(name)

def safe_rerun():
    try:
        st.rerun()
    except Exception:
        st.experimental_rerun()

def render_sources(hits):
    if not hits:
        return
    with st.expander("📚 Sources for this answer"):
        for h in hits:
            url = h.get("url", "")
            score = h.get("score", 0.0)
            lang = h.get("lang", "?")
            st.markdown(f"- [{url}]({url}) · score **{score:.3f}** · lang **{lang}**")

def mark_all_uneditable():
    """Clear 'editable' on all assistant messages."""
    for m in st.session_state.messages:
        if m.get("role") == "assistant":
            m["editable"] = False

# ----------------------------
# Page config + minimal styling
# ----------------------------
st.set_page_config(page_title="TH OWL Assistant — Chat", page_icon="🎓", layout="wide")
st.markdown(
    """
    <style>
      header, footer {visibility: hidden;}
      .block-container {max-width: 900px; padding-top: 1rem;}
      [data-testid="stChatMessage"] { margin-bottom: 0.75rem; }
      [data-testid="stChatMessage"] div[data-testid="stMarkdownContainer"] p { line-height: 1.55; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------
# Admin detection (for index tools)
# ----------------------------
ADMIN_TOKEN = secret_or_env("ADMIN_TOKEN")
admin_param = get_query_param("admin")
admin_mode = bool(ADMIN_TOKEN and admin_param and admin_param == ADMIN_TOKEN)

# Hide the sidebar entirely for non-admin users
if not admin_mode:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"], [data-testid="stSidebarNav"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

# ----------------------------
# Top bar (title + controls)
# ----------------------------
c1, c2 = st.columns([1, 1])
with c1:
    st.markdown("### 🎓 TH OWL Assistant")
    st.caption("Skip the Website, Ask the Chatbot.")

with c2:
    LANG_OPTIONS = {
        "Auto (match question)": None,
        "English": "en",
        "Deutsch": "de",
        "Français": "fr",
        "Español": "es",
    }
    sel_lang = st.selectbox("Answer language", list(LANG_OPTIONS.keys()), index=0)

# Admin-only sidebar to (re)build index
if admin_mode:
    with st.sidebar:
        st.header("Index (Admin)")
        st.write("1) Add seed URLs to `seeds.txt`\n2) Click rebuild\n3) Chat in main panel")

        follow = st.checkbox("Follow links under same path (depth 1)", value=True)
        prefix = st.text_input(
            "Allowed prefix",
            value="https://www.th-owl.de/skim/dokumentation/",
            help="Only crawl links that start with this prefix."
        )
        max_links = st.number_input("Max links per seed", min_value=5, max_value=100, value=12, step=1)

        if st.button("🔁 Rebuild index from seeds.txt"):
            with st.spinner("Building index (fetching pages, PDFs)…"):
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

# ----------------------------
# Session state (chat + edit state)
# ----------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Hi! Ask me anything about TH-OWL. I’ll cite official sources.",
            "sources": [],
            "from_llm": False,
            "editable": False,  # greeting is not editable
        }
    ]
st.session_state.setdefault("edit_msg_idx", None)
st.session_state.setdefault("edit_buffer", "")

# Toolbar: new chat / show sources by default
tcol1, tcol2, _ = st.columns([0.3, 0.35, 0.35])
with tcol1:
    if st.button("🧹 New chat"):
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "New chat started. How can I help?",
                "sources": [],
                "from_llm": False,
                "editable": False,
            }
        ]
        st.session_state.edit_msg_idx = None
        st.session_state.edit_buffer = ""
        safe_rerun()
with tcol2:
    auto_sources = st.checkbox("Show sources by default", value=True)

# ----------------------------
# Render chat history with edit only on latest LLM answer
# ----------------------------
for i, msg in enumerate(st.session_state.messages):
    avatar = "🎓" if msg["role"] == "assistant" else "🧑‍💻"
    with st.chat_message(msg["role"], avatar=avatar):
        is_editable = (msg["role"] == "assistant" and msg.get("editable", False))
        is_editing_this = (is_editable and st.session_state.edit_msg_idx == i)

        if is_editable and is_editing_this:
            st.info("✏️ You’re editing this answer. Make changes and click **Save**.")
            if st.session_state.edit_buffer == "":
                st.session_state.edit_buffer = msg["content"]

            st.text_area(
                "Edit answer",
                key="edit_area",
                value=st.session_state.edit_buffer,
                height=240,
                label_visibility="collapsed",
            )

            b1, b2, _ = st.columns([0.2, 0.2, 0.6])
            with b1:
                if st.button("💾 Save", key=f"save_{i}"):
                    st.session_state.messages[i]["content"] = st.session_state.edit_area
                    st.session_state.edit_msg_idx = None
                    st.session_state.edit_buffer = ""
                    st.success("Saved.")
                    safe_rerun()
            with b2:
                if st.button("✖ Cancel", key=f"cancel_{i}"):
                    st.session_state.edit_msg_idx = None
                    st.session_state.edit_buffer = ""
                    safe_rerun()

            # Optional: download the edited answer
            st.download_button(
                "⬇️ Download as .txt",
                data=st.session_state.edit_area,
                file_name=f"answer_{i}.txt",
                mime="text/plain",
                key=f"dl_edit_{i}",
            )

            if msg.get("sources") and auto_sources:
                render_sources(msg["sources"])

        else:
            # Normal (non-edit) render
            st.markdown(msg["content"])

            # Only the latest LLM answer shows Edit/Download buttons
            if is_editable:
                ac1, ac2, _ = st.columns([0.15, 0.25, 0.6])
                with ac1:
                    if st.button("✏️ Edit", key=f"edit_{i}"):
                        st.session_state.edit_msg_idx = i
                        st.session_state.edit_buffer = msg["content"]
                        safe_rerun()
                with ac2:
                    st.download_button(
                        "⬇️ Download",
                        data=msg["content"],
                        file_name=f"answer_{i}.txt",
                        mime="text/plain",
                        key=f"dl_{i}",
                    )

            if msg.get("sources") and auto_sources:
                render_sources(msg["sources"])

# ----------------------------
# Chat input
# ----------------------------
user_q = st.chat_input("Type your question…")
if user_q:
    # 1) Show user message immediately
    st.session_state.messages.append({"role": "user", "content": user_q})
    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(user_q)

    # 2) Prepare retrieval (language detect + optional translate)
    try:
        q_lang = detect(user_q).split("-")[0]
    except Exception:
        q_lang = "en"

    query_for_search = user_q if q_lang == "en" else translate(user_q, target_code="en")

    # 3) Retrieve top chunks
    try:
        hits = retrieval.search(query_for_search, top_k=4)
        context = "\n---\n".join(h["chunk_text"] for h in hits)
    except Exception:
        hits, context = [], ""

    # 4) Ask LLM with original question + English context
    forced_lang = LANG_OPTIONS[sel_lang]
    with st.chat_message("assistant", avatar="🎓"):
        with st.spinner("Thinking…"):
            try:
                answer = ask_llm(user_q, context=context, force_lang_code=forced_lang)
            except Exception as e:
                answer = f"Sorry, something went wrong: `{e}`"

        # Render answer immediately
        st.markdown(answer)
        if hits:
            render_sources(hits)

    # 5) Append assistant message as the ONLY editable one
    mark_all_uneditable()
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "sources": hits,
        "from_llm": True,
        "editable": True,   # only the newest LLM answer is editable
    })
    safe_rerun()
    st.session_state.edit_msg_idx = None
    st.session_state.edit_buffer = ""

# ----------------------------
# API key hint (non-blocking)
# ----------------------------
if not secret_or_env("OPENAI_API_KEY"):
    st.warning("OPENAI_API_KEY not found. Set it in `.streamlit/secrets.toml` or as an env var.")
