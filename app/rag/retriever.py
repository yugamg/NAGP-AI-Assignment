from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.tools import tool

from app.config import (
    CHROMA_COLLECTION,
    EMBEDDING_MODEL,
    MAX_RELEVANT_DISTANCE,
    NO_RELEVANT_KNOWLEDGE,
    RETRIEVAL_K,
    VECTORSTORE_DIR,
)

_store = None


def _get_store() -> Chroma:
    global _store
    if _store is None:
        if not VECTORSTORE_DIR.exists():
            raise RuntimeError(
                "Knowledge base not built yet. Run `python -m app.rag.ingest` first."
            )
        embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
        _store = Chroma(
            collection_name=CHROMA_COLLECTION,
            embedding_function=embeddings,
            persist_directory=str(VECTORSTORE_DIR),
        )
    return _store


def format_chunks(results: list[tuple]) -> str:
    """Render (Document, distance) pairs as citation-carrying text for the LLM."""
    relevant = [(doc, dist) for doc, dist in results if dist <= MAX_RELEVANT_DISTANCE]
    if not relevant:
        return NO_RELEVANT_KNOWLEDGE

    blocks = []
    for doc, _ in relevant:
        title = doc.metadata.get("title", "Unknown source")
        url = doc.metadata.get("source_url", "")
        blocks.append(f"[Source: {title} ({url})]\n{doc.page_content}")
    return "\n\n---\n\n".join(blocks)


@tool
def search_knowledge_base(query: str) -> str:
    """Search the Singapore travel knowledge base for destination facts:
    attractions, neighbourhoods, transportation, culture, food, and
    itineraries. Always use this for destination questions, never for
    weather or currency. Returns cited chunks, or a sentinel string if
    nothing relevant is found.

    Use a specific, descriptive query (e.g. "three day itinerary with
    outdoor and indoor activities"), not a single generic word like
    "itinerary" — this is a semantic search, and vague queries retrieve
    weaker matches.
    """
    store = _get_store()
    results = store.similarity_search_with_score(query, k=RETRIEVAL_K)
    return format_chunks(results)
