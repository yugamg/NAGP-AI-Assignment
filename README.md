# AI Travel Planning Assistant — Singapore

A travel assistant for Singapore that combines a document-based knowledge
base (RAG) with live data from a self-built MCP server (weather + currency
conversion), orchestrated with LangChain and served through a Streamlit chat
UI.

See `CLAUDE.md` for the full build spec and `RULES.md` for the engineering
rules this codebase follows.

## Architecture

```
Streamlit chat UI (app/ui/streamlit_app.py)
        |
        v
LangChain agent (app/agent.py, create_agent + LangGraph, model: gpt-4o-mini)
system prompt: app/prompts.py
        |
        +-- search_knowledge_base (app/rag/retriever.py)
        |       reads the Chroma vector store built by app/rag/ingest.py
        |
        +-- MCP client (app/mcp_client/client.py, stdio)
                spawns app/mcp_server/server.py as a subprocess
                get_weather -> Open-Meteo
                convert_currency -> Frankfurter
```

The agent decides per turn which tool(s) to call:
- destination questions (attractions, transport, culture, food, itineraries) go to `search_knowledge_base`
- time-sensitive questions (forecast, exchange rate) go to `get_weather` or `convert_currency`
- combined questions (e.g. "plan a 3-day trip and adjust for weather") use both, in sequence, before the final answer

The full message history is replayed to the agent on every call, so
follow-up questions ("what about day 2?", "convert that to USD instead")
keep context without a separate memory component.

## Knowledge Base

Five public Singapore travel resources, captured and cleaned into markdown
files under `data/knowledge_base/`. Each file has `title` and `source_url`
in its YAML frontmatter so every retrieved chunk can be cited back to a
source.

- `wikivoyage_singapore.md` — Wikivoyage, Singapore Travel Guide (https://en.wikivoyage.org/wiki/Singapore)
- `visitsingapore_essential_info.md` — Visit Singapore, Essential Travel Information (https://www.visitsingapore.com/travel-tips/essential-travel-information/)
- `visitsingapore_sample_itinerary.md` — Visit Singapore, Enjoy Singapore in 7 Days (https://www.visitsingapore.com/travel-tips/travelling-to-singapore/itineraries/7-days-in-singapore/)
- `visitsingapore_things_to_do.md` — Visit Singapore, Top Things To Do, all 7 sub-categories (https://www.visitsingapore.com/things-to-do/top-things-to-do/)
- `visitsingapore_food_drinks.md` — Visit Singapore, Local Food & Drinks (https://www.visitsingapore.com/things-to-do/dining/local-food-and-drinks/)

These files are the deliverable — the app ingests them from disk and does
not need internet access at run time to answer destination questions.
`scripts/fetch_sources.py` documents a reproducible re-fetch of the same
URLs for reference; it writes to `data/knowledge_base_raw/` and never
overwrites the curated files, since a raw scrape is noisier (site nav,
cookie banners) than the hand-cleaned versions checked in here.

### RAG workflow

1. Load — `app/rag/ingest.py` reads every `.md` file in `data/knowledge_base/`, parsing the frontmatter for `title` and `source_url`.
2. Chunk — `RecursiveCharacterTextSplitter`, 800 chars / 120 overlap, splitting on markdown headers first.
3. Embed — local `sentence-transformers/all-MiniLM-L6-v2`, no API key, runs on-device.
4. Store — persisted to a local Chroma collection at `data/vectorstore/`, cosine distance.
5. Retrieve — `app/rag/retriever.py` exposes `search_knowledge_base` as a LangChain tool; similarity search with k=4, filtered by a distance threshold.
6. Generate — the system prompt requires every destination-fact claim to be grounded in what this tool returned.
7. Cite — each returned chunk carries its source title and URL, and the prompt tells the model to name the source next to the claim.

If nothing relevant comes back, the tool returns the sentinel
`NO_RELEVANT_KNOWLEDGE_FOUND` and the prompt tells the model to say so
plainly instead of inventing destination facts.

## MCP Tools

A real MCP server (`app/mcp_server/server.py`, built with the official `mcp`
SDK's `FastMCP`) exposes two tools over stdio. It is not imported directly —
it's called over the actual MCP protocol via `langchain-mcp-adapters`
(`app/mcp_client/client.py` spawns the server as a subprocess).

- `get_weather(forecast_days)` — Open-Meteo, free, no key. Always checks Singapore (the only destination this assistant covers) — it takes no location, so it can't be pointed at the wrong city.
- `convert_currency(amount, from_currency, to_currency)` — Frankfurter (ECB reference rates), free, no key

Both tools return `{"error": "..."}` on failure (bad location, unknown
currency code, network or timeout error) instead of a fabricated value, and
the system prompt tells the agent to relay that plainly.

## Prompt & Context Strategy

The full system prompt is in `app/prompts.py`. In short:

- Two sources, never blurred: `search_knowledge_base` is the only source for destination facts, the two MCP tools are the only source for anything time-sensitive. The model is told not to answer either kind of question from general knowledge.
- Explicit missing-info handling: both the retriever's sentinel and the MCP tools' error payloads have matching instructions — say so plainly, don't guess.
- Fact vs. suggestion: when the model combines sources into a recommendation (sequencing a day, swapping in an indoor activity for rain), it flags that as its own suggestion, not a retrieved fact.
- Source attribution: destination claims are cited by KB document title, live claims are labeled by tool name. The UI also renders a per-turn "Sources & tools used" trace so this is visible in the app, not just requested in the prompt.
- Context continuity: the full running message history is passed back to the agent every turn, so it naturally carries forward stated preferences (budget, dates, travelling with kids, interests) without a separate memory layer.
- Scope guardrails: the prompt tells the model to decline booking/payment requests (out of scope for this assignment) and offer what it can actually help with instead.

## Setup and Run

Requires Python 3.12 (sentence-transformers / torch / chromadb wheels target
3.12; a newer interpreter such as 3.14 may not have compatible wheels yet).

```bash
# 1. create and activate a venv
python3.12 -m venv .venv
source .venv/bin/activate

# 2. install dependencies
pip install -r requirements.txt

# 3. add your OpenAI key
cp .env.example .env
# edit .env and set OPENAI_API_KEY (OPENAI_MODEL defaults to gpt-4o-mini)

# 4. build the knowledge base (one-time, or after editing data/knowledge_base/*.md)
python -m app.rag.ingest

# 5. run the app
streamlit run app/ui/streamlit_app.py --server.fileWatcherType none
```

Open http://localhost:8501.

`--server.fileWatcherType none` is needed because Streamlit's dev-mode file
watcher tries to introspect every module under `transformers` (pulled in by
`sentence-transformers`) to know what to hot-reload, which is slow enough on
that library's size to stall the first request for a long time. Nothing in
this app changes while it runs, so the watcher isn't needed.

## What's Verified

Every item below was exercised live in a running instance of the app, not
just unit-tested in isolation:

- RAG retrieval and citations: a plain destination question returned a grounded, cited answer with no MCP calls made.
- MCP weather tool: real calls to Open-Meteo's live geocoding and forecast APIs.
- MCP currency tool: real calls to Frankfurter's live ECB rates.
- Combined RAG + MCP: the required "3-day itinerary adjusted for the weather forecast" scenario called both the weather tool and the knowledge base, and produced a day-by-day plan that swapped in indoor attractions where rain was likely.
- Multi-turn context: a follow-up turn correctly recalled attractions named in the previous turn and correctly identified which were indoor, without them being restated.
- Missing-knowledge handling: an out-of-scope query (e.g. a Tokyo restaurant question) returns the "not covered" response instead of a fabricated answer.
- Per-turn source/tool trace: the "Sources & tools used" section shows KB citations for RAG turns and the tool name plus raw result for MCP turns.

Two real bugs were found and fixed during this live verification:

1. Chroma's default distance metric is squared L2, not cosine. A threshold written assuming cosine distance was silently too strict and rejected valid knowledge-base matches. Fixed by setting cosine distance explicitly in `ingest.py` and recalibrating the threshold in `config.py`.
2. The UI opened and closed a fresh asyncio event loop on every turn, but the cached OpenAI client's async HTTP client stays bound to whichever loop existed when it was built, causing `RuntimeError: Event loop is closed` on the second turn. Fixed by keeping one event loop alive for the process's lifetime.

## Sample Questions

See `questions.md` for example questions and what each one should do:
knowledge base, MCP tools, combined, and failure handling.

## Out of Scope

No flight or hotel booking, no payment processing, no route navigation, no
travel reservations — per the assignment brief.
