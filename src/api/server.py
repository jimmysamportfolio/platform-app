"""
FastAPI Server for Legal Lease RAG Frontend

Exposes REST endpoints for:
- Chat/Q&A with the RAG system
- Portfolio analytics
- Document listing and viewing
"""

import os
import sys
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from retrieval.orchestrator import LeaseRAGOrchestrator
from analysis.portfolio import PortfolioAnalyzer
from utils.db import get_all_leases, get_lease_by_tenant, DEFAULT_DB_PATH, get_leases_grouped_by_property, get_clauses_for_comparison

# File Watcher Imports
from watchdog.observers import Observer
from ingestion.file_watcher import IngestionHandler
from config.settings import WATCHDOG_INPUT_FOLDER, WATCHDOG_PROCESSED_FOLDER

app = FastAPI(
    title="Legal Lease RAG API",
    description="API for the Legal Lease RAG Dashboard",
    version="1.0.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components lazily
_orchestrator: Optional[LeaseRAGOrchestrator] = None
_analyzer: Optional[PortfolioAnalyzer] = None
_observer: Optional[Observer] = None  # File watcher observer
_ingestion_handler: Optional[IngestionHandler] = None  # Reference to handler

@app.on_event("startup")
async def startup_event():
    """Start the file watcher on server startup."""
    global _observer, _ingestion_handler
    print("\n🐕 Starting Background File Watcher...")
    try:
        _ingestion_handler = IngestionHandler(
            input_folder=WATCHDOG_INPUT_FOLDER,
            processed_folder=WATCHDOG_PROCESSED_FOLDER,
            db_path=DEFAULT_DB_PATH
        )
        _observer = Observer()
        _observer.schedule(_ingestion_handler, str(_ingestion_handler.input_folder), recursive=False)
        _observer.start()
        print("✅ File Watcher running in background thread")
    except Exception as e:
        print(f"❌ Failed to start File Watcher: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Stop the file watcher on server shutdown."""
    global _observer
    if _observer:
        print("\n🛑 Stopping File Watcher...")
        _observer.stop()
        _observer.join()
        print("✅ File Watcher stopped")


def get_orchestrator() -> LeaseRAGOrchestrator:
    """Get or initialize the RAG orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = LeaseRAGOrchestrator(lazy_init=True)
    return _orchestrator


def get_analyzer() -> PortfolioAnalyzer:
    """Get or initialize the portfolio analyzer."""
    global _analyzer
    if _analyzer is None:
        _analyzer = PortfolioAnalyzer()
    return _analyzer


# --- Request/Response Models ---

class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    answer: str
    route: str
    sources: list = []


# --- Chat Endpoint ---

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message to the RAG system and get a response."""
    try:
        orchestrator = get_orchestrator()
        response = orchestrator.query(request.message)
        return ChatResponse(
            answer=response.answer,
            route=response.route,
            sources=[s.get("document_name", "Unknown") for s in response.sources[:3]]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Analytics Endpoints ---

@app.get("/api/analytics/portfolio")
async def get_portfolio_analytics():
    """Get portfolio summary analytics."""
    try:
        analyzer = get_analyzer()
        summary = analyzer.get_portfolio_summary()
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Document Endpoints ---

@app.get("/api/documents")
async def list_documents():
    """Get list of all lease documents."""
    try:
        leases = get_all_leases()
        return {"documents": leases}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/documents/{document_name}/content")
async def get_document_content(document_name: str):
    """Get the raw markdown content of a parsed document."""
    try:
        # Find the parsed markdown file
        parsed_dir = Path("data/parsed")
        
        # Look for a matching file
        matching_files = list(parsed_dir.glob(f"*{document_name}*"))
        if not matching_files:
            # Try direct match
            for md_file in parsed_dir.glob("*.md"):
                if document_name.lower() in md_file.stem.lower():
                    matching_files.append(md_file)
        
        if not matching_files:
            raise HTTPException(status_code=404, detail="Document not found")
        
        content = matching_files[0].read_text(encoding="utf-8")
        return {
            "filename": matching_files[0].name,
            "content": content
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/documents/{document_name}")
async def delete_document(document_name: str):
    """
    Delete a document from the system.
    
    This removes:
    1. The lease record from database
    2. The ingestion logs
    3. Vectors from Pinecone
    """
    global _ingestion_handler
    try:
        from utils.db import delete_lease, delete_ingestion_log
        from retrieval.vector_store import LeaseVectorStore
        
        # 1. Delete from database
        lease_deleted = delete_lease(document_name)
        log_deleted = delete_ingestion_log(document_name)
        
        if not lease_deleted and not log_deleted:
            raise HTTPException(status_code=404, detail="Document not found in database")

        # 2. Tell the file watcher to forget this file (so it can be re-added)
        if _ingestion_handler:
            _ingestion_handler.forget_file(document_name)
        
        # 3. Delete vectors from Pinecone
        vectors_deleted = 0
        try:
            vector_store = LeaseVectorStore()
            vectors_deleted = vector_store.delete_by_document(document_name)
        except Exception as e:
            print(f"⚠️ Failed to delete vectors from Pinecone: {e}")

        return {
            "status": "success", 
            "message": f"Deleted document: {document_name}",
            "details": {
                "lease_deleted": lease_deleted,
                "logs_deleted": log_deleted,
                "vectors_deleted": vectors_deleted
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Health Check ---

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


# --- Clause Comparison Endpoints ---

class CompareRequest(BaseModel):
    lease_ids: list[int]


@app.get("/api/leases/list")
async def list_leases_grouped():
    """
    Get all leases grouped by property for the lease picker.
    
    Returns:
        List of properties, each with their leases.
    """
    try:
        properties = get_leases_grouped_by_property()
        return {"properties": properties}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/clauses/compare")
async def compare_clauses(request: CompareRequest):
    """
    Compare clauses across multiple leases.
    
    Args:
        request: CompareRequest with list of lease IDs.
        
    Returns:
        Dictionary with clause types as keys and comparison data.
    """
    if not request.lease_ids:
        raise HTTPException(status_code=400, detail="No lease IDs provided")
    
    if len(request.lease_ids) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 leases can be compared at once")
    
    try:
        comparisons = get_clauses_for_comparison(request.lease_ids)
        return {
            "comparisons": comparisons,
            "lease_count": len(request.lease_ids),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
