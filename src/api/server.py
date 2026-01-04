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
from utils.db import get_all_leases, get_lease_by_tenant, DEFAULT_DB_PATH

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


# --- Health Check ---

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
