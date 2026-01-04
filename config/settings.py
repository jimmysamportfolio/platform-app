"""
Global constants and configuration settings for the Legal RAG application.

This module contains:
- Chunk sizes for document processing
- Model names (LLM, embedding models)
- API endpoint configurations
- Other application-wide constants
"""

# --- LLM Configuration ---
DEFAULT_LLM_MODEL = "gemini-2.5-flash"
DEFAULT_EMBEDDING_MODEL = "models/text-embedding-004"
LLM_TEMPERATURE = 0  # Strict factual answers

# --- Reranker Configuration ---
DEFAULT_RERANKER_MODEL = "ms-marco-TinyBERT-L-2-v2"
RERANKER_CACHE_DIR = ".flashrank_cache"

# --- Chunking Configuration ---
MAX_CHUNK_TOKENS = 1000
SECONDARY_CHUNK_SIZE = 800
SECONDARY_CHUNK_OVERLAP = 100
ORPHAN_CHUNK_MIN_TOKENS = 25

# --- Retrieval Configuration ---
RETRIEVAL_K = 40  # Number of candidates to retrieve from vector store
RERANK_TOP_N = 10  # More docs to handle definition-style queries
VECTOR_NAMESPACE = "leases-test"  # Namespace where documents are indexed in Pinecone

# --- Ingestion Configuration ---
ENRICHMENT_BATCH_SIZE = 5
ENRICHMENT_DELAY_SECONDS = 12.0  # ~5 batches/min to stay under 15 RPM
EMBEDDING_BATCH_SIZE = 50
EMBEDDING_DELAY_SECONDS = 0.5

# --- Enrichment Mode ---
# Options: 'llm' (uses Gemini API - expensive), 'rule-based' (free), 'none' (skip enrichment)
ENRICHMENT_MODE = "rule-based"  # Recommended: 'rule-based' for cost savings

# --- Database Configuration ---
DEFAULT_DB_PATH = "data/leases.db"
METADATA_STORE_PATH = "data/metadata_store.json"

# --- Clause Types for Classification ---
CLAUSE_TYPES = [
    "definitions",
    "rent_payment",
    "security_deposit",
    "maintenance_repairs",
    "insurance",
    "default_remedies",
    "termination",
    "assignment_subletting",
    "use_restrictions",
    "environmental",
    "indemnification",
    "general_provisions",
    "schedules_exhibits",
    "parties_recitals",
    "other"
]

# --- Watchdog Configuration ---
WATCHDOG_INPUT_FOLDER = "input"
WATCHDOG_PROCESSED_FOLDER = "processed"
WATCHDOG_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".md"}
