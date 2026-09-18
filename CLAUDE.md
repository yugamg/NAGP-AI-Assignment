# CLAUDE.md — AI Travel Planning Assistant (Singapore)

> Build exactly what is written here. Nothing more.
> This is a graded assignment, not a demo — it must actually work end to end.

---

## The One Thing This App Shows

Two kinds of knowledge, combined:

1. **Stable destination knowledge** — attractions, neighbourhoods, transport, culture,
   itineraries. Lives in documents. Retrieved with RAG.
2. **Live, time-sensitive knowledge** — weather, currency rates. Cannot live in
   documents because it changes daily. Retrieved with MCP tools, on demand.

The assistant's job is to know which kind of question it's answering, pull from
the right source (sometimes both), and say plainly where each fact came from.

Never blend these silently. A user should always be able to tell: "that came
from the knowledge base," "that came from a live tool call," or "that's the
model's own suggestion."

---

## Reference

The full brief is at `AI_Travel_Planning_Assistant_Assignment.pdf` in this folder.
Read it before changing scope. Destination is **Singapore** (per the brief's
recommendation — public resources are good and it keeps the KB scope bounded).

---

## Tech Stack (fixed — do not substitute)

- **Python 3.12** (not 3.14 — sentence-transformers/torch/chromadb wheels target
  3.12; use a venv pinned to 3.12)
- **LangChain** for orchestration, prompts, retrieval chain, and tool binding
- **Chroma** as the vector store (persisted to disk under `data/vectorstore/`)
- **sentence-transformers** (`all-MiniLM-L6-v2`) for embeddings — local, free, no
  API key, runs offline after first download
- **OpenAI** (`gpt-4o-mini` default, override via `OPENAI_MODEL`) as the chat LLM
  via `langchain-openai` — this is the one required API key
- **MCP** — a real MCP server we write ourselves (`mcp` Python SDK, stdio
  transport), consumed through `langchain-mcp-adapters`. No off-the-shelf MCP
  servers. The point of the assignment is understanding the client/server
  handshake, not wiring up someone else's package.
- **Streamlit** for the UI — one page, a chat interface. No React, no FastAPI
  frontend, no extra framework.

No other frameworks. No Redis, no Postgres, no Celery, no Docker requirement.
This is a single-process app you run with `streamlit run`.

---

## Folder Structure

```
NAGP AI Assignment/
├── CLAUDE.md
├── RULES.md
├── README.md
├── SAMPLE_QA.md
├── requirements.txt
├── .env.example
├── .gitignore
├── AI_Travel_Planning_Assistant_Assignment.pdf
├── app/
│   ├── config.py                  ← env vars, paths, model names — one place
│   ├── prompts.py                 ← system prompt + prompt-strategy notes
│   ├── agent.py                   ← builds the LangChain tool-calling agent
│   ├── rag/
│   │   ├── ingest.py               ← load KB docs → chunk → embed → persist
│   │   └── retriever.py            ← load persisted store, expose retriever tool
│   ├── mcp_server/
│   │   └── server.py               ← MCP server: weather + currency tools
│   ├── mcp_client/
│   │   └── client.py               ← spawns the MCP server, exposes LC tools
│   └── ui/
│       └── streamlit_app.py        ← the entire UI
├── data/
│   ├── knowledge_base/             ← source markdown files (title + url in frontmatter)
│   └── vectorstore/                ← Chroma persistence (gitignored, rebuildable)
├── scripts/
│   └── fetch_sources.py            ← reproducible fetch of the 4 public sources
└── tests/
    └── test_mcp_tools.py           ← unit tests for the two MCP tools (mocked HTTP)
```

That's it. No extra files beyond this list.

---

## Knowledge Base — Sources

At least three public resources, per the brief. We use four:

1. Wikivoyage — Singapore Travel Guide
2. Visit Singapore — Essential Travel Information
3. Visit Singapore — Sample Itineraries
4. Visit Singapore — Things To Do

Each is fetched once and saved as a markdown file in `data/knowledge_base/` with
YAML frontmatter:

```markdown
---
title: "Singapore Travel Guide"
source_url: "https://en.wikivoyage.org/wiki/Singapore"
---

<cleaned article content>
```

`ingest.py` reads this frontmatter and carries `title` + `source_url` as chunk
metadata, so every retrieved chunk can be cited by title and link — not just
"source 1, source 2."

If a source can't be fetched at build time, that's fine — the saved `.md` files
in `data/knowledge_base/` **are** the deliverable per the brief ("knowledge-base
documents, or clear instructions for obtaining them"). `scripts/fetch_sources.py`
documents how they were obtained, for reproducibility, but the graded app must
not depend on the internet being reachable during grading — it reads from the
already-ingested Chroma store.

---

## RAG Pipeline (`app/rag/`)

1. `ingest.py` — walks `data/knowledge_base/*.md`, splits with
   `RecursiveCharacterTextSplitter` (~800 chars, 120 overlap — travel guides have
   short, list-heavy sections; don't over-chunk), embeds with
   `HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")`,
   persists to `data/vectorstore/` via Chroma. Idempotent: re-running rebuilds
   cleanly (delete-then-recreate the collection, don't append duplicates).
2. `retriever.py` — loads the persisted Chroma collection and exposes a
   `@tool`-decorated `search_knowledge_base(query: str)` function returning the
   top-k chunks **with their `title` / `source_url` metadata attached** — the
   agent must be able to cite these verbatim, not paraphrase away the source.
3. If the retriever returns nothing relevant (empty results, or all scores below
   a similarity threshold), the tool returns an explicit
   `"NO_RELEVANT_KNOWLEDGE_FOUND"` sentinel. The system prompt instructs the
   model: on seeing that sentinel, say plainly that the knowledge base doesn't
   cover the question — never invent destination facts to fill the gap.

---

## MCP Server (`app/mcp_server/server.py`)

A real MCP server over stdio, built with the official `mcp` Python SDK
(`mcp.server.fastmcp.FastMCP`). Two tools:

### `get_weather(location: str, forecast_days: int = 3)`
- Geocode `location` via Open-Meteo's free geocoding endpoint, then call
  Open-Meteo's forecast endpoint for current conditions + a daily forecast.
- No API key required (Open-Meteo is free/open for non-commercial use).
- On any HTTP error, timeout, or empty geocoding result: return a structured
  error payload (`{"error": "..."}`), never a fabricated forecast.

### `convert_currency(amount: float, from_currency: str, to_currency: str)`
- Call the Frankfurter API (`https://api.frankfurter.app`) — free, no key,
  ECB reference rates.
- Validate currency codes are 3-letter ISO 4217 before calling out.
- On failure: structured error payload, same discipline as above.

Both tools return plain JSON-serializable dicts — the MCP protocol handles
serialization. Keep the tool functions boring: fetch, validate, shape the
response, return. No caching layer, no retry framework — a single timeout and
a clear error is enough for this scope.

---

## MCP Client (`app/mcp_client/client.py`)

Uses `langchain-mcp-adapters`' `MultiServerMCPClient` to launch
`app/mcp_server/server.py` as a stdio subprocess and load its tools as native
LangChain `BaseTool` objects. This is the actual "client consumes server"
mechanic the assignment wants demonstrated — don't shortcut it by importing the
server's Python functions directly into the agent. They must talk over the MCP
protocol.

---

## Agent (`app/agent.py`)

One LangChain tool-calling agent (`create_tool_calling_agent` +
`AgentExecutor`) with three tools bound:
- `search_knowledge_base` (RAG)
- `get_weather` (MCP)
- `convert_currency` (MCP)

Conversation memory: pass the full running message history back in on every
turn (Streamlit `session_state` holds it; the agent is stateless per call).
This satisfies "multi-turn conversation with retained context" without a
memory framework — a list of messages is enough.

The system prompt (`app/prompts.py`) is the enforcement point for every rule in
brief section 5 (grounding, citing sources, not fabricating, distinguishing
fact from suggestion, stating when info is missing). See `RULES.md` for the
non-negotiables baked into it.

---

## UI (`app/ui/streamlit_app.py`)

One page. A chat interface (`st.chat_message`, `st.chat_input`). Nothing else:

- Message history rendered top to bottom, user and assistant turns.
- Each assistant turn, below the answer, an expandable **"Sources & tools
  used"** section listing:
  - KB chunks cited (title + link)
  - MCP tool calls made (tool name, inputs, and a one-line result summary)
- A sidebar with: a short static description of the app, the 4 KB source links,
  and a "clear conversation" button. That's the entire sidebar.

No dashboards, no tabs, no settings panel, no file upload, no auth. The brief
says explicitly: focus is the AI workflow, not interface sophistication.

---

## Environment Variables (`.env`, see `.env.example`)

```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

Nothing else needs a key — embeddings are local, weather/currency APIs are free
and keyless.

---

## How to Run

```bash
# 1. Create and activate a Python 3.12 venv
python3.12 -m venv .venv
source .venv/bin/activate

# 2. Install
pip install -r requirements.txt

# 3. Set your OpenAI key
cp .env.example .env
# edit .env and paste OPENAI_API_KEY

# 4. Build the knowledge base (one-time, or after editing data/knowledge_base/*.md)
python -m app.rag.ingest

# 5. Run the app
streamlit run app/ui/streamlit_app.py
```

---

## Definition of Done

- [ ] 4 KB source documents in `data/knowledge_base/` with title + URL frontmatter
- [ ] `ingest.py` builds a persisted Chroma store from them
- [ ] RAG retrieval returns cited, grounded answers; says so clearly when KB has nothing relevant
- [ ] MCP server runs standalone and exposes weather + currency tools
- [ ] MCP client loads those tools via the MCP protocol (not direct import) and the agent calls them correctly
- [ ] Combined RAG+MCP scenario works: 3-day Singapore itinerary adjusted for forecast
- [ ] Multi-turn context retained (a follow-up question referencing a prior answer works)
- [ ] Tool/API failures produce a clear "couldn't retrieve X" message, never fabricated data
- [ ] Streamlit chat UI shows sources and tool calls per turn, distinct from the prose answer
- [ ] README, SAMPLE_QA.md, requirements.txt, .env.example all present and accurate
- [ ] No console errors on a fresh `pip install` + run

---

## Hard Rules

1. **No off-the-shelf MCP servers.** We write the MCP server. That's the point.
2. **No fabricated destination facts.** If the KB doesn't cover it, say so.
3. **No fabricated live data.** If a tool call fails, say so — never guess a
   plausible-looking weather forecast or exchange rate.
4. **Every destination-fact claim is traceable** to a KB chunk's title/URL.
5. **Every live-data claim is labeled** as coming from a tool, with the tool name.
6. **LangChain only** for orchestration — no bypassing it with raw OpenAI SDK
   calls in application code.
7. **Local embeddings only** — no embedding API key dependency.
8. **One Streamlit page.** Resist the urge to add tabs, dashboards, or settings.
9. See `RULES.md` for how the code itself should read and be structured.
