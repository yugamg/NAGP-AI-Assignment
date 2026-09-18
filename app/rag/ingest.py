"""
Build the knowledge-base vector store.

Reads every markdown file in data/knowledge_base/ (each starting with a small
YAML frontmatter block for `title` and `source_url`), splits the body into
chunks, embeds them locally, and persists to Chroma.

Run with: python -m app.rag.ingest
"""

import shutil

import yaml
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import (
    CHROMA_COLLECTION,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    EMBEDDING_MODEL,
    KB_DIR,
    VECTORSTORE_DIR,
)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a '---\\nyaml\\n---\\nbody' file into (metadata, body)."""
    if not text.startswith("---"):
        return {}, text
    _, frontmatter, body = text.split("---", 2)
    return yaml.safe_load(frontmatter) or {}, body.strip()


def load_documents() -> list[Document]:
    docs = []
    for path in sorted(KB_DIR.glob("*.md")):
        metadata, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
        if not body:
            continue
        docs.append(
            Document(
                page_content=body,
                metadata={
                    "title": metadata.get("title", path.stem),
                    "source_url": metadata.get("source_url", ""),
                },
            )
        )
    return docs


def build_vectorstore() -> None:
    documents = load_documents()
    if not documents:
        raise SystemExit(
            f"No knowledge-base documents found in {KB_DIR}. "
            "Add markdown files with 'title'/'source_url' frontmatter first."
        )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n## ", "\n### ", "\n\n", "\n", " ", ""],
    )
    chunks = splitter.split_documents(documents)

    if VECTORSTORE_DIR.exists():
        shutil.rmtree(VECTORSTORE_DIR)
    VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)

    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=CHROMA_COLLECTION,
        persist_directory=str(VECTORSTORE_DIR),
    )

    print(f"Ingested {len(documents)} source document(s) -> {len(chunks)} chunks.")
    print(f"Vector store persisted to {VECTORSTORE_DIR}")


if __name__ == "__main__":
    build_vectorstore()
