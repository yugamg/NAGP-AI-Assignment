"""
The entire UI: a single-page Streamlit chat interface. Run with:
  streamlit run app/ui/streamlit_app.py
"""

import asyncio

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage

from app.agent import AgentTurn, build_agent, run_turn

KB_SOURCES = [
    ("Singapore Travel Guide - Wikivoyage", "https://en.wikivoyage.org/wiki/Singapore"),
    ("Essential Singapore Travel Information", "https://www.visitsingapore.com/travel-tips/essential-travel-information/"),
    ("Enjoy Singapore in 7 Days (Sample Itinerary)", "https://www.visitsingapore.com/travel-tips/travelling-to-singapore/itineraries/7-days-in-singapore/"),
    ("Top Things To Do", "https://www.visitsingapore.com/things-to-do/top-things-to-do/"),
    ("Local Food & Drinks", "https://www.visitsingapore.com/things-to-do/dining/local-food-and-drinks/"),
]

TOOL_LABELS = {
    "search_knowledge_base": "Knowledge base (RAG)",
    "get_weather": "Live weather (MCP)",
    "convert_currency": "Live currency rate (MCP)",
}


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@st.cache_resource(show_spinner="Starting the MCP server and loading tools...")
def get_agent():
    return run_async(build_agent())


def render_tool_trace(turn: AgentTurn) -> None:
    if not turn.tool_calls:
        return
    with st.expander("Sources & tools used", expanded=False):
        for call in turn.tool_calls:
            label = TOOL_LABELS.get(call.name, call.name)
            if call.name == "search_knowledge_base":
                if "NO_RELEVANT_KNOWLEDGE_FOUND" in call.result:
                    st.markdown(f"**{label}** — no relevant content found for: `{call.args.get('query', '')}`")
                else:
                    st.markdown(f"**{label}** — query: `{call.args.get('query', '')}`")
                    st.text(call.result[:2000])
            else:
                st.markdown(f"**{label}** — input: `{call.args}`")
                st.code(call.result, language="json")


def main() -> None:
    st.set_page_config(page_title="Singapore Travel Assistant", page_icon="🧭")

    with st.sidebar:
        st.header("Singapore Travel Planning Assistant")
        st.write(
            "Ask about attractions, transport, food, and itineraries "
            "(from a curated knowledge base), or live weather and currency "
            "conversion (via MCP tools). Combine both for a weather-aware "
            "itinerary or a budget-aware trip plan."
        )
        st.subheader("Knowledge base sources")
        for title, url in KB_SOURCES:
            st.markdown(f"- [{title}]({url})")
        if st.button("Clear conversation"):
            st.session_state.messages = []
            st.rerun()

    st.title("🧭 Singapore Travel Planning Assistant")

    if "messages" not in st.session_state:
        st.session_state.messages = []  # list of (role, content, AgentTurn|None)

    for role, content, turn in st.session_state.messages:
        with st.chat_message(role):
            st.markdown(content)
            if turn is not None:
                render_tool_trace(turn)

    user_input = st.chat_input("Ask about Singapore — e.g. 'Plan a 3-day trip and adjust for the weather'")
    if not user_input:
        return

    st.session_state.messages.append(("user", user_input, None))
    with st.chat_message("user"):
        st.markdown(user_input)

    try:
        agent = get_agent()
    except RuntimeError as exc:
        with st.chat_message("assistant"):
            st.error(str(exc))
        return

    chat_history = []
    for role, content, _ in st.session_state.messages[:-1]:
        chat_history.append(HumanMessage(content=content) if role == "user" else AIMessage(content=content))

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            turn = run_async(run_turn(agent, chat_history, user_input))
        st.markdown(turn.answer)
        render_tool_trace(turn)

    st.session_state.messages.append(("assistant", turn.answer, turn))


if __name__ == "__main__":
    main()
