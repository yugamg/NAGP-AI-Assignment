import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
KB_DIR = ROOT_DIR / "data" / "knowledge_base"
VECTORSTORE_DIR = ROOT_DIR / "data" / "vectorstore"
MCP_SERVER_SCRIPT = ROOT_DIR / "app" / "mcp_server" / "server.py"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CHROMA_COLLECTION = "singapore_travel_kb"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
RETRIEVAL_K = 4
# Cosine distance (0 = identical, 2 = opposite; see ingest.py's hnsw:space
# setting). Calibrated empirically: relevant travel-topic queries against this
# corpus land at ~0.2-0.55, off-topic queries (e.g. "sushi in Tokyo") land at
# ~0.55+. Anything above this is treated as "not actually relevant" rather
# than forced into the answer.
MAX_RELEVANT_DISTANCE = 0.55

NO_RELEVANT_KNOWLEDGE = "NO_RELEVANT_KNOWLEDGE_FOUND"
