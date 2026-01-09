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
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import asyncio

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

# WebSocket connection manager for real-time notifications
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

ws_manager = ConnectionManager()

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
        
        # Register callback for WebSocket notifications
        def notify_new_file(file_name: str, file_path: str):
            asyncio.run(ws_manager.broadcast({
                "type": "new_file",
                "file_name": file_name,
                "file_path": file_path,
            }))
        IngestionHandler.register_callback(notify_new_file)
        
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
    confidence: int = 75  # 0-100 confidence percentage
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
            confidence=getattr(response, 'confidence', 75),
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
    4. Pending files from queue
    """
    global _ingestion_handler
    try:
        from utils.db import delete_lease, delete_ingestion_log
        from retrieval.vector_store import LeaseVectorStore
        
        # 1. Delete from database
        lease_deleted = delete_lease(document_name)
        log_deleted = delete_ingestion_log(document_name)
        
        # 2. Remove from pending queue (if present)
        pending_removed = False
        if document_name in IngestionHandler._pending_files:
            IngestionHandler.remove_pending(document_name)
            pending_removed = True
        
        # 3. Tell the file watcher to forget this file (so it can be re-added)
        if _ingestion_handler:
            _ingestion_handler.forget_file(document_name)
        
        # If nothing was found anywhere, raise 404
        if not lease_deleted and not log_deleted and not pending_removed:
            raise HTTPException(status_code=404, detail="Document not found in database or pending queue")
        
        # 4. Delete vectors from Pinecone (only if it was in database)
        vectors_deleted = 0
        if lease_deleted:
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
                "pending_removed": pending_removed,
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


# --- Document Generation Endpoints ---

class RentRowInput(BaseModel):
    lease_year_start: int
    lease_year_end: int
    per_sqft: float
    per_annum: float
    per_month: float


class GenerateDocumentRequest(BaseModel):
    tenant_name: str
    tenant_address: str
    indemnifier_name: str
    indemnifier_address: str
    premises_unit: str
    rentable_area: str
    lease_date: str
    initial_term: str
    renewal_option_count: int
    renewal_option_years: int
    possession_date: str
    fixturing_period: str
    offer_to_lease_date: str
    indemnity_date: str
    rent_schedule: list[RentRowInput]
    deposit: str
    tenant_improvement_allowance: str = ""
    permitted_use: str
    trade_name: str
    exclusive_use: str = ""
    radius_restriction: str = ""


@app.post("/api/documents/generate")
async def generate_document(request: GenerateDocumentRequest):
    """
    Generate a populated lease document from user inputs.
    
    Returns the generated document as a file download.
    """
    from fastapi.responses import FileResponse
    from generation.document_generator import generate_lease_document
    import tempfile
    import uuid
    
    try:
        # Convert request to dict for the generator
        input_data = {
            "tenant_name": request.tenant_name,
            "tenant_address": request.tenant_address,
            "indemnifier_name": request.indemnifier_name,
            "indemnifier_address": request.indemnifier_address,
            "premises_unit": request.premises_unit,
            "rentable_area": request.rentable_area,
            "lease_date": request.lease_date,
            "initial_term": request.initial_term,
            "renewal_option_count": request.renewal_option_count,
            "renewal_option_years": request.renewal_option_years,
            "possession_date": request.possession_date,
            "fixturing_period": request.fixturing_period,
            "offer_to_lease_date": request.offer_to_lease_date,
            "indemnity_date": request.indemnity_date,
            "rent_schedule": [row.model_dump() for row in request.rent_schedule],
            "deposit": request.deposit,
            "tenant_improvement_allowance": request.tenant_improvement_allowance,
            "permitted_use": request.permitted_use,
            "trade_name": request.trade_name,
            "exclusive_use": request.exclusive_use,
            "radius_restriction": request.radius_restriction,
        }
        
        # Generate unique filename
        filename = f"Lease_{request.trade_name or request.tenant_name}_{uuid.uuid4().hex[:8]}.docx"
        filename = filename.replace(" ", "_").replace("/", "-")
        
        # Generate the document
        output_path = generate_lease_document(
            input_data,
            output_filename=filename,
            output_dir="output"
        )
        
        return FileResponse(
            path=str(output_path),
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Template not found: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/extraction/key-terms")
async def get_key_terms_for_leases(lease_ids: str):
    """
    Get key terms/due diligence fields for specified leases.
    
    Args:
        lease_ids: Comma-separated list of lease IDs.
        
    Returns:
        Dictionary with lease data including all extraction fields.
    """
    try:
        ids = [int(id.strip()) for id in lease_ids.split(",") if id.strip()]
        
        if not ids:
            raise HTTPException(status_code=400, detail="No lease IDs provided")
        
        # Get leases with all fields
        leases_data = []
        all_leases = get_all_leases()
        
        for lease in all_leases:
            if lease["id"] in ids:
                leases_data.append({
                    "id": lease["id"],
                    "tenant_name": lease.get("tenant_name"),
                    "trade_name": lease.get("trade_name"),
                    "tenant_address": lease.get("tenant_address"),
                    "indemnifier_name": lease.get("indemnifier_name"),
                    "indemnifier_address": lease.get("indemnifier_address"),
                    "lease_date": lease.get("lease_start"),
                    "premises": lease.get("premises_description"),
                    "rentable_area_sqft": lease.get("rentable_area_sqft"),
                    "term_years": lease.get("term_years"),
                    "renewal_option": lease.get("renewal_option"),
                    "deposit_amount": lease.get("deposit_amount"),
                    "permitted_use": lease.get("permitted_use"),
                    "fixturing_period": lease.get("fixturing_period"),
                    "free_rent_period": lease.get("free_rent_period"),
                    "possession_date": lease.get("possession_date"),
                    "tenant_improvement_allowance": lease.get("tenant_improvement_allowance"),
                    "exclusive_use": lease.get("exclusive_use"),
                })
        
        return {"leases": leases_data, "count": len(leases_data)}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid lease ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Ingestion Endpoints ---

class ProcessIngestionRequest(BaseModel):
    file_path: str
    mode: str  # "full" or "clause_only"


@app.websocket("/ws/ingestion")
async def websocket_ingestion(websocket: WebSocket):
    """
    WebSocket endpoint for real-time ingestion notifications.
    Clients receive messages when new files are detected.
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, waiting for messages
            data = await websocket.receive_text()
            # Echo back for ping/pong
            await websocket.send_json({"type": "pong", "data": data})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.get("/api/ingestion/pending")
async def get_pending_files():
    """
    Get list of files waiting for user to select extraction mode.
    """
    return {
        "pending_files": IngestionHandler.get_pending_files(),
        "count": len(IngestionHandler.get_pending_files()),
    }


@app.post("/api/ingestion/process")
async def process_ingestion(request: ProcessIngestionRequest):
    """
    Process a pending file with the selected mode.
    
    Args:
        file_path: Path to the file to process.
        mode: "full" for complete pipeline, "clause_only" for quick extraction.
    """
    global _ingestion_handler
    
    if not _ingestion_handler:
        raise HTTPException(status_code=500, detail="Ingestion handler not initialized")
    
    if request.mode not in ["full", "clause_only"]:
        raise HTTPException(status_code=400, detail="Mode must be 'full' or 'clause_only'")
    
    # Process in background thread to avoid blocking
    import threading
    result_holder = {"result": None, "error": None}
    
    def run_processing():
        try:
            result_holder["result"] = _ingestion_handler.process_file(
                request.file_path, 
                request.mode
            )
        except Exception as e:
            result_holder["error"] = str(e)
    
    thread = threading.Thread(target=run_processing)
    thread.start()
    thread.join(timeout=300)  # 5 minute timeout
    
    if result_holder["error"]:
        raise HTTPException(status_code=500, detail=result_holder["error"])
    
    return result_holder["result"]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
