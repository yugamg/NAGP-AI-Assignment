# AI Travel Planning Assistant — Singapore

A context-aware travel assistant for Singapore that combines a document-based
knowledge base (RAG) with live data from a self-built MCP server (weather +
currency conversion), orchestrated with LangChain and served through a
Streamlit chat UI.

Built for the "AI Travel Planning Assistant" developer assignment. See
`CLAUDE.md` for the full build spec and `RULES.md` for the engineering
discipline this codebase follows.

---

## Architecture

```
┌─────────────────────┐
│  Streamlit chat UI   │  app/ui/streamlit_app.py
└──────────┬───────────┘
           │ user message + running chat history
           ▼
┌─────────────────────────────────────────────┐
│  LangChain agent (create_agent, LangGraph)   │  app/agent.py
│  model: gpt-4o-mini   system prompt: app/prompts.py
└───────┬───────────────────────┬──────────────┘
        │ tool call                     tool call
        ▼                               ▼
┌───────────────────────┐   ┌─────────────────────────────┐
│ search_knowledge_base  │   │  MCP client (stdio)          │  app/mcp_client/client.py
│ app/rag/retriever.py   │   │  spawns app/mcp_server/server.py as a subprocess
└──────────┬──────────────┘   └──────────┬───────────────────┘
           │                              │ MCP protocol (JSON-RPC over stdio)
           ▼                              ▼
┌───────────────────────┐   ┌─────────────────────────────┐
│  Chroma vector store    │   │  get_weather → Open-Meteo    │
│  (local, persisted)     │   │  convert_currency → Frankfurter│
│  built by app/rag/ingest.py│ └─────────────────────────────┘
└───────────────────────┘
```

The agent decides, per user turn, which tool(s) to call:
- Destination questions (attractions, transport, culture, food, itineraries) → `search_knowledge_base`
- Time-sensitive questions (forecast, exchange rate) → `get_weather` / `convert_currency`
- Combined questions (e.g. "plan a 3-day trip and adjust for weather") → both, in sequence, before composing one answer

The full message history (not just the current turn) is replayed to the agent
on every call, so follow-up questions ("what about day 2?", "convert that to
USD instead") retain context without any separate memory framework.

---

## Knowledge Base

Five public Singapore travel resources, captured and cleaned into markdown
files under `data/knowledge_base/` (each carries `title` + `source_url` in
YAML frontmatter so every retrieved chunk can be cited):

| File | Source |
|---|---|
| `wikivoyage_singapore.md` | [Wikivoyage — Singapore Travel Guide](https://en.wikivoyage.org/wiki/Singapore) |
| `visitsingapore_essential_info.md` | [Visit Singapore — Essential Travel Information](https://www.visitsingapore.com/travel-tips/essential-travel-information/) |
| `visitsingapore_sample_itinerary.md` | [Visit Singapore — Enjoy Singapore in 7 Days](https://www.visitsingapore.com/travel-tips/travelling-to-singapore/itineraries/7-days-in-singapore/) |
| `visitsingapore_things_to_do.md` | [Visit Singapore — Top Things To Do](https://www.visitsingapore.com/things-to-do/top-things-to-do/) (all 7 sub-categories: Unique Experiences, City in Nature, Culture & Heritage, Iconic Architecture, Family Fun, After Dark, Museums & Galleries) |
| `visitsingapore_food_drinks.md` | [Visit Singapore — Local Food & Drinks](https://www.visitsingapore.com/things-to-do/dining/local-food-and-drinks/) |

These files **are** the deliverable (assignment requirement: "knowledge-base
documents, or clear instructions for obtaining them") — the app ingests them
from disk and does not depend on the internet being reachable at grading
time. `scripts/fetch_sources.py` documents a reproducible (best-effort)
re-fetch of the same URLs for reference; it writes to `data/knowledge_base_raw/`
and never overwrites the curated files, since a raw scrape is noisier
(site navigation, cookie banners) than the hand-cleaned versions checked in here.

### RAG workflow
1. **Load** — `app/rag/ingest.py` reads every `.md` file in `data/knowledge_base/`, parsing the YAML frontmatter for `title`/`source_url`.
2. **Chunk** — `RecursiveCharacterTextSplitter`, 800 chars / 120 overlap, splitting on markdown headers first.
3. **Embed** — local `sentence-transformers/all-MiniLM-L6-v2` (no API key, runs on-device).
4. **Store** — persisted to a local Chroma collection at `data/vectorstore/`.
5. **Retrieve** — `app/rag/retriever.py` exposes `search_knowledge_base` as a LangChain tool; it runs similarity search (k=4) and filters out chunks past a distance threshold.
6. **Generate** — the agent's system prompt requires it to ground every destination-fact claim in what this tool returned.
7. **Cite** — every returned chunk carries `[Source: <title> (<url>)]`, and the prompt instructs the model to name the source next to the claim.

If nothing relevant is found, the tool returns the sentinel
`NO_RELEVANT_KNOWLEDGE_FOUND` and the system prompt instructs the model to
say so plainly rather than invent destination facts.

---

## MCP Tools

A real MCP server (`app/mcp_server/server.py`, built with the official `mcp`
SDK's `FastMCP`) exposes two tools over **stdio** — not imported directly,
called over the actual MCP protocol via `langchain-mcp-adapters`
(`app/mcp_client/client.py` spawns the server as a subprocess per session).

| Tool | Backing API | Notes |
|---|---|---|
| `get_weather(location, forecast_days)` | [Open-Meteo](https://open-meteo.com/) (geocoding + forecast) | Free, no API key |
| `convert_currency(amount, from_currency, to_currency)` | [Frankfurter](https://www.frankfurter.dev/) (ECB reference rates) | Free, no API key |

Both tools return a structured `{"error": "..."}` on failure (bad location,
unknown currency code, network/timeout error) instead of a fabricated value —
the system prompt instructs the agent to relay that plainly.

MCP requirements checklist (assignment §4.2):
- [x] Connect to ≥2 MCP tools
- [x] Tools available to the application (loaded as LangChain tools)
- [x] Appropriate tool selected per user intent (agent's own tool-calling, guided by the system prompt)
- [x] Required input passed to the tool (LLM extracts location / amount / currencies from the message)
- [x] Tool output used in the final response
- [x] Live info clearly labeled as MCP-sourced (system prompt + UI trace)
- [x] Tool/API failure handled without fabricating an answer

---

## Prompt & Context Strategy

The full system prompt is in `app/prompts.py`. Summary of the strategy (see
assignment §5):

- **Two sources, never blurred.** The prompt names `search_knowledge_base` as
  the *only* source for destination facts and the two MCP tools as the
  *only* source for anything time-sensitive. The model is told not to answer
  either kind of question from its own general knowledge.
- **Explicit missing-info handling.** Both the retriever's sentinel value and
  the MCP tools' error payloads have matching instructions in the prompt:
  say so plainly, don't guess.
- **Fact vs. suggestion.** When the model combines sources into a
  recommendation (sequencing a day, swapping in an indoor activity for rain),
  it's instructed to flag that clearly as its own suggestion rather than a
  retrieved fact.
- **Source attribution.** Destination claims are cited by KB document title;
  live claims are labeled by tool name. The UI additionally renders a
  per-turn "Sources & tools used" trace so this isn't just a prompt request —
  it's independently visible in the app.
- **Context continuity.** Rather than a separate memory/summarization layer,
  the full running message history is passed back to the agent every turn,
  so it can naturally carry forward stated preferences (budget, dates,
  travelling with kids, interests).
- **Scope guardrails.** The prompt tells the model to decline booking/payment
  requests (out of scope per the assignment) and redirect to what it can do.

---

## Setup

Requires Python **3.12** (sentence-transformers/torch/chromadb wheels target
3.12 — a newer interpreter like 3.14 may not have compatible wheels yet).

```bash
# 1. Create and activate a venv
python3.12 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Add your OpenAI key
cp .env.example .env
# edit .env and set OPENAI_API_KEY (OPENAI_MODEL defaults to gpt-4o-mini)

# 4. Build the knowledge base (one-time, or after editing data/knowledge_base/*.md)
python -m app.rag.ingest

# 5. Run the app
streamlit run app/ui/streamlit_app.py
```

Open http://localhost:8501.

### Running tests
```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

---

## What's verified vs. what needs your OpenAI key

Everything in this repo has been run and checked in this environment
**except the live OpenAI-backed chat turns**, since that requires an API key
this environment doesn't have:

- ✅ MCP server + client verified end-to-end against the real, live Open-Meteo and Frankfurter APIs (real HTTP calls, real subprocess over the real MCP stdio protocol — see `tests/test_mcp_tools.py` for the mocked-failure-path tests, and the smoke test in git history for the live call).
- ✅ RAG ingestion verified end-to-end: 5 documents → 388 chunks → embedded → persisted → retrieved with correct citations, and the no-match sentinel confirmed on an out-of-scope query.
- ✅ The LangChain 1.x `create_agent` message-shape (tool call → `ToolMessage` → final answer) verified against a stub tool-calling model, since `app/agent.py`'s trace-extraction logic depends on that exact shape.
- ⏳ A full chat turn through `gpt-4o-mini` — needs `OPENAI_API_KEY` in `.env`, then `streamlit run app/ui/streamlit_app.py`.

---

## Sample Questions

See `SAMPLE_QA.md` for example questions per category (destination-only,
live-data-only, combined, missing-info handling) with what to expect.

---

## Out of Scope (per assignment)

No flight/hotel booking, no payment processing, no route navigation, no
travel reservations.
