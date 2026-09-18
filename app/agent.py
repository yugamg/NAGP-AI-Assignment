"""
Builds the single LangChain agent that ties together the RAG tool and the two
MCP tools, and runs it against a running message history.

LangChain 1.x's `create_agent` (LangGraph under the hood) replaces the older
`create_tool_calling_agent` + `AgentExecutor` pair. It compiles a small graph
that alternates between calling the model and calling tools until the model
stops requesting tools, and returns the full message list — including every
`ToolMessage` — which is exactly what we need to show a "sources & tools
used" trace per turn without any extra bookkeeping.
"""

from dataclasses import dataclass, field

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI

from app.config import OPENAI_API_KEY, OPENAI_MODEL
from app.mcp_client.client import load_mcp_tools
from app.prompts import SYSTEM_PROMPT
from app.rag.retriever import search_knowledge_base


@dataclass
class ToolCallRecord:
    name: str
    args: dict
    result: str


@dataclass
class AgentTurn:
    answer: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)


async def build_agent():
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key."
        )

    mcp_tools = await load_mcp_tools()
    tools = [search_knowledge_base, *mcp_tools]

    model = ChatOpenAI(model=OPENAI_MODEL, api_key=OPENAI_API_KEY, temperature=0.2)
    return create_agent(model, tools=tools, system_prompt=SYSTEM_PROMPT)


async def run_turn(agent, chat_history: list[BaseMessage], user_input: str) -> AgentTurn:
    messages = [*chat_history, HumanMessage(content=user_input)]
    result = await agent.ainvoke({"messages": messages})
    new_messages = result["messages"][len(messages):]

    tool_calls: list[ToolCallRecord] = []
    pending_calls: dict[str, dict] = {}

    for msg in new_messages:
        if isinstance(msg, AIMessage):
            for call in msg.tool_calls or []:
                pending_calls[call["id"]] = {"name": call["name"], "args": call["args"]}
        elif isinstance(msg, ToolMessage):
            call_info = pending_calls.pop(msg.tool_call_id, {"name": msg.name, "args": {}})
            tool_calls.append(
                ToolCallRecord(name=call_info["name"], args=call_info["args"], result=str(msg.content))
            )

    final_answer = new_messages[-1].content if new_messages else ""
    return AgentTurn(answer=final_answer, tool_calls=tool_calls)
