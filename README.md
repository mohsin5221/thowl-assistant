Installation

# Clone the repository
git clone https://github.com/mohsin5221/thowl-assistant.git
cd thowl-assistant

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

**Configuration**

OpenAI API Key
Set your OpenAI key in either of these places:
.env file:
OPENAI_API_KEY=sk-...
or Streamlit secrets:
# .streamlit/secrets.toml
OPENAI_API_KEY = "sk-..."
ADMIN_TOKEN = "your-admin-token"

Seeds File
Add initial URLs to crawl for content:
# seeds.txt
https://www.th-owl.de/skim/dokumentation/

**Usage**

Run the assistant locally using Streamlit:
streamlit run app/streamlit_app.py
Admin Mode
http://localhost:8501/?admin=your-admin-token

**Project structure**
.
├─ app/
│  ├─ streamlit_app.py     # main entry (UI + admin)
│  ├─ retrieval.py         # crawl, chunk, TF-IDF, search
│  └─ llm.py               # ask_llm, translate, API client
├─ seeds.txt               # URLs to index
├─ data/
│  ├─ cache/               # chunks.csv, vectorizer, matrix
│  ├─ raw_html/            # saved HTML
│  └─ raw_pdf/             # saved PDFs
└─ .streamlit/
   └─ secrets.toml        


