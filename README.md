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
streamlit run app/ui/streamlit_app.py --server.fileWatcherType none
```

Open http://localhost:8501.

`--server.fileWatcherType none` avoids a real Streamlit dev-mode issue: its
file watcher tries to introspect every module under `transformers` (pulled in
by `sentence-transformers`) to know what to hot-reload, which is slow enough
on that library's size to stall the first request for a long time. It's not
needed for this app (no source files change while it runs), so it's disabled.

### Running tests
```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

---

## What's Verified

Every capability below was exercised live in a running instance of this app
(not just unit-tested in isolation):

- ✅ **RAG retrieval + citations** — "What are the must-visit attractions for a family with young kids?" returned grounded, per-claim-cited answers from `Top Things To Do`, with no MCP calls made (correct tool selection).
- ✅ **MCP weather tool** — real calls to Open-Meteo's live geocoding + forecast APIs.
- ✅ **MCP currency tool** — real calls to Frankfurter's live ECB rates (e.g. 200 SGD → 14,999 INR at the day's rate).
- ✅ **Combined RAG + MCP (the primary required scenario)** — "Create a three-day Singapore itinerary for next week and adjust it according to the weather forecast" correctly called both the weather tool (got a 3-day forecast showing 76-96% rain chance) and the knowledge base, then produced a day-by-day itinerary that swapped in indoor attractions (ArtScience Museum, National Gallery, S.E.A. Aquarium) because of the forecast.
- ✅ **Multi-turn context** — a follow-up turn ("convert 200 SGD to INR for that trip, and remind me which of those attractions were indoor") correctly recalled the specific attractions named in the previous turn and correctly identified which were indoor, without restating them.
- ✅ **Missing-knowledge handling** — an out-of-scope query ("best sushi restaurant in Tokyo") returns the `NO_RELEVANT_KNOWLEDGE_FOUND` sentinel rather than a fabricated answer.
- ✅ **Per-turn source/tool trace** — the "Sources & tools used" expander correctly shows the KB chunk(s) with citations for RAG turns, and the tool name + raw JSON result for MCP turns.
- ✅ Unit tests (`tests/test_mcp_tools.py`, 7 tests) pass — happy-path and failure-path coverage for both MCP tools with the HTTP layer mocked.

Two real bugs were found and fixed during this live verification (not just
theoretical — both would have broken the app for any real user):
1. **Chroma's default distance metric is squared L2, not cosine** — a 0.8
   "relevance" threshold written assuming cosine distance was silently too
   strict, causing correct itinerary content to be treated as irrelevant.
   Fixed by setting `collection_metadata={"hnsw:space": "cosine"}` in
   `ingest.py` and recalibrating the threshold in `config.py` against actual
   measured distances for on-topic vs. off-topic queries.
2. **`RuntimeError: Event loop is closed` on the second chat turn** — the UI
   was opening and closing a fresh asyncio event loop per turn, but the
   cached `ChatOpenAI` client's async HTTP client stays bound to whichever
   loop existed when it was built. Fixed in `streamlit_app.py` by keeping one
   event loop alive for the process's lifetime instead of closing it each turn.

---

## Sample Questions

See `SAMPLE_QA.md` for example questions per category (destination-only,
live-data-only, combined, missing-info handling) with what to expect.

---

## Out of Scope (per assignment)

No flight/hotel booking, no payment processing, no route navigation, no
travel reservations.
