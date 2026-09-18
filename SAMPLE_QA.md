# Sample Questions & Expected Behaviour

These illustrate each required capability. Exact wording of answers will vary
run to run (LLM-generated), but the sourcing behaviour described should hold.

## 1. Destination knowledge only (RAG)

**Q: What are the must-visit attractions in Singapore?**
Expected: pulls from `visitsingapore_things_to_do.md` and
`wikivoyage_singapore.md`, cites both by title, no tool calls made.

**Q: Which neighbourhoods are suitable for cultural experiences?**
Expected: cites Chinatown, Little India, Kampong Gelam, Katong-Joo Chiat from
the Culture & Heritage section, sourced to Visit Singapore.

**Q: What indoor attractions can I visit?**
Expected: surfaces the museums/galleries (all indoor) plus other
explicitly-indoor entries (Jewel Changi, ArtScience Museum, Gardens by the
Bay's conservatories), no live tool call.

**Q: Suggest activities for a family with children.**
Expected: pulls the Family Fun category content, may label sequencing advice
as "Suggestion:" per the prompt's fact/suggestion distinction.

## 2. Live data only (MCP)

**Q: What is the weather in Singapore?**
Expected: calls `get_weather`, states current temperature/condition, labels
it as live data from Open-Meteo. No knowledge-base call needed.

**Q: What is the forecast for the next three days?**
Expected: calls `get_weather` with `forecast_days=3`, returns a per-day
breakdown.

**Q: Convert INR 50,000 to SGD.**
Expected: calls `convert_currency(50000, "INR", "SGD")`, states the
converted amount and cites Frankfurter/ECB rates.

**Q: What is the weather like on the moon?** *(failure-path check)*
Expected: `get_weather` geocoding returns no result → tool returns a
structured error → the assistant says it couldn't find that location, rather
than fabricating a forecast.

## 3. Combined RAG + MCP (the primary required scenario)

**Q: Create a three-day Singapore itinerary for next week and adjust it according to the weather forecast.**
Expected: calls `search_knowledge_base` for attractions/itinerary structure
*and* `get_weather` for the forecast, then produces a day-by-day plan that
swaps outdoor activities (Gardens by the Bay outdoor areas, Sentosa beaches)
for indoor alternatives (Jewel Changi, museums, Oceanarium) on days with a
high rain-chance forecast. Both sources cited distinctly.

**Q: I have a budget of INR 60,000. Convert it to SGD and suggest a three-day itinerary.**
Expected: calls `convert_currency` first, then `search_knowledge_base` for
itinerary content, and produces a plan that references the converted budget.

## 4. Missing-information handling

**Q: What's the best sushi restaurant in Tokyo?**
Expected: `search_knowledge_base` returns `NO_RELEVANT_KNOWLEDGE_FOUND` (this
KB is Singapore-only); the assistant states plainly that this isn't covered,
rather than answering from general knowledge.

**Q: Book me a flight to Singapore.**
Expected: assistant declines — booking is explicitly out of scope per the
system prompt — and offers to help with trip planning instead.

## 5. Multi-turn context

**Turn 1 — Q: Plan a 2-day trip focused on nature and wildlife.**
**Turn 2 — Q: What about the weather for those two days — should I bring an umbrella?**
Expected: turn 2 is answered in the context of the itinerary from turn 1
(same date range implied) without the user having to restate it — the full
message history is replayed to the agent each turn.
