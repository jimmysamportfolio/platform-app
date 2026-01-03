"""
RAG Orchestrator Module

Main orchestrator that ties together the dual-path retrieval system.
This module is responsible for:
- Routing queries to analytics or retrieval paths
- Coordinating vector search, reranking, and generation
- Providing a unified interface for the RAG system
"""

import os
import sys
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Add project root to path for config imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv
from langchain_core.documents import Document

from config.settings import RETRIEVAL_K, RERANK_TOP_N, VECTOR_NAMESPACE

from retrieval.router import QueryRouter
from retrieval.vector_store import LeaseVectorStore
from retrieval.reranker import LeaseReranker
from retrieval.generator import RAGGenerator
from retrieval.analytics_handler import AnalyticsHandler

load_dotenv()


@dataclass
class RAGResponse:
    """Structured response from the RAG system."""
    query: str
    answer: str
    route: str  # 'analytics' or 'retrieval'
    sources: List[Dict[str, Any]]
    metadata: Dict[str, Any]


class LeaseRAGOrchestrator:
    """
    Main orchestrator for the Legal Lease RAG system.
    
    Implements dual-path retrieval:
    - Analytics Path: Structured data queries (metadata_store.json) - NO LLM
    - Retrieval Path: Semantic search + reranking + generation - Uses LLM
    """
    
    def __init__(
        self,
        vector_namespace: str = VECTOR_NAMESPACE,
        retrieval_k: int = RETRIEVAL_K,
        rerank_top_n: int = RERANK_TOP_N,
        lazy_init: bool = False,
    ):
        """
        Initialize the RAG orchestrator.
        
        Args:
            vector_namespace: Pinecone namespace to search.
            retrieval_k: Number of candidates to retrieve from vector search.
            rerank_top_n: Number of documents to keep after reranking.
            lazy_init: If True, defer initialization of heavy components.
        """
        self.retrieval_k = retrieval_k
        self.rerank_top_n = rerank_top_n
        self.vector_namespace = vector_namespace
        
        # Initialize analytics handler (no LLM, instant)
        self.analytics = AnalyticsHandler()
        
        # Lazy initialization for LLM-dependent components
        self._router = None
        self._vector_store = None
        self._reranker = None
        self._generator = None
        
        if not lazy_init:
            self._init_retrieval_components()
        
        print("✅ LeaseRAGOrchestrator ready!")
    
    def _init_retrieval_components(self):
        """Initialize retrieval path components (LLM-dependent)."""
        print("🚀 Initializing retrieval components...")
        self._router = QueryRouter()
        self._vector_store = LeaseVectorStore(namespace=self.vector_namespace)
        self._reranker = LeaseReranker()
        self._generator = RAGGenerator()
    
    @property
    def router(self):
        if self._router is None:
            self._router = QueryRouter()
        return self._router
    
    @property
    def vector_store(self):
        if self._vector_store is None:
            self._vector_store = LeaseVectorStore(namespace=self.vector_namespace)
        return self._vector_store
    
    @property
    def reranker(self):
        if self._reranker is None:
            self._reranker = LeaseReranker()
        return self._reranker
    
    @property
    def generator(self):
        if self._generator is None:
            self._generator = RAGGenerator()
        return self._generator
    
    def _extract_tenant_from_query(self, query: str) -> Optional[str]:
        """Extract tenant/trade name from query using simple pattern matching."""
        # Common patterns
        patterns = [
            r"for\s+([A-Za-z\'\.\s]+?)(?:\s*\?|$)",  # "for Church's Chicken?"
            r"(?:Church'?s?\s*Chicken|H\.?\s*Sran|Starbucks)",  # Known trade names
        ]
        
        # Check for known tenants
        query_lower = query.lower()
        if "church" in query_lower:
            return "Church's Chicken"
        if "sran" in query_lower:
            return "H. Sran"
        
        return None
    
    def _handle_analytics(self, query: str) -> RAGResponse:
        """
        Handle analytics path queries using structured data (NO LLM).
        
        This is instant - no API calls!
        """
        query_lower = query.lower()
        tenant = self._extract_tenant_from_query(query)
        
        # Route to specific analytics method based on query content
        if "deposit" in query_lower and tenant:
            result = self.analytics.get_deposit_amount(tenant)
        elif "term" in query_lower and tenant:
            result = self.analytics.get_term(tenant)
        elif "expir" in query_lower and tenant:
            result = self.analytics.get_expiration(tenant)
        elif "rent" in query_lower and tenant:
            result = self.analytics.get_rent_schedule(tenant)
        elif "total" in query_lower and "deposit" in query_lower:
            result = self.analytics.get_total_deposit()
        elif "average" in query_lower and "rent" in query_lower:
            result = self.analytics.get_average_rent_psf()
        elif "summary" in query_lower or "portfolio" in query_lower:
            result = self.analytics.get_portfolio_summary()
        else:
            # Generic lookup - try deposit if tenant found
            if tenant:
                result = self.analytics.get_deposit_amount(tenant)
            else:
                result = self.analytics.get_portfolio_summary()
        
        return RAGResponse(
            query=query,
            answer=result.answer,
            route="analytics",
            sources=[{"type": "metadata_store", "path": "data/metadata_store.json"}],
            metadata={"data": result.data, "query_type": result.query_type},
        )
    
    def _handle_retrieval(
        self,
        query: str,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> RAGResponse:
        """Handle retrieval path queries (uses LLM)."""
        # Step 1: Vector search
        candidates = self.vector_store.search(
            query,
            k=self.retrieval_k,
            filter_dict=filter_dict,
        )
        
        if not candidates:
            return RAGResponse(
                query=query,
                answer="No relevant documents were found for your query.",
                route="retrieval",
                sources=[],
                metadata={"candidates": 0, "reranked": 0},
            )
        
        # Step 2: Rerank (local, no API)
        top_docs = self.reranker.rerank(query, candidates, top_n=self.rerank_top_n)
        
        # Step 3: Generate answer (LLM call)
        result = self.generator.generate_with_sources(query, top_docs)
        
        return RAGResponse(
            query=query,
            answer=result["answer"],
            route="retrieval",
            sources=result["sources"],
            metadata={
                "candidates": len(candidates),
                "reranked": len(top_docs),
            },
        )
    
    def query(
        self,
        query: str,
        filter_dict: Optional[Dict[str, Any]] = None,
        force_route: Optional[str] = None,
    ) -> RAGResponse:
        """
        Process a user query through the appropriate path.
        
        Args:
            query: The user's natural language question.
            filter_dict: Optional metadata filters for vector search.
            force_route: Force a specific route ('analytics' or 'retrieval').
            
        Returns:
            RAGResponse with answer, sources, and metadata.
        """
        # Determine route
        if force_route:
            route = force_route
        else:
            route = self.router.route_query(query)
        
        print(f"🔀 Route: {route.upper()}")
        
        # Execute appropriate path
        if route == "analytics":
            return self._handle_analytics(query)
        else:
            return self._handle_retrieval(query, filter_dict)
    
    def query_analytics(self, query: str) -> RAGResponse:
        """Force query through analytics path (no LLM calls)."""
        return self._handle_analytics(query)
    
    def query_retrieval(self, query: str, filter_dict: Optional[Dict] = None) -> RAGResponse:
        """Force query through retrieval path."""
        return self._handle_retrieval(query, filter_dict)
    
    def chat(self, query: str) -> str:
        """Simple chat interface that returns just the answer."""
        response = self.query(query)
        return response.answer


# --- Test Block ---
if __name__ == "__main__":
    # Initialize with lazy_init to avoid hitting APIs during import
    rag = LeaseRAGOrchestrator(lazy_init=True)
    
    print("\n" + "=" * 60)
    print("🧪 TESTING ANALYTICS PATH (No LLM - Instant!)")
    print("=" * 60)
    
    # These queries use analytics path - NO LLM calls!
    analytics_queries = [
        "What is the security deposit amount for Church's Chicken?",
        "What is the total security deposit across all leases?",
        "When does the H. Sran lease expire?",
        "What is the rent schedule for Church's Chicken?",
    ]
    
    for q in analytics_queries:
        print(f"\n🔍 Query: {q}")
        response = rag.query_analytics(q)  # Force analytics path
        print(f"📝 Answer: {response.answer}")
    
    print("\n" + "=" * 60)
    print("🧪 TESTING RETRIEVAL PATH (Uses LLM)")
    print("=" * 60)
    
    # Retrieval queries - these search the vector store
    retrieval_queries = [
        "What are the landlord's maintenance obligations?",
        "What is the exclusive use clause for Church's Chicken?",
        "What happens if the tenant defaults on rent in the H. Sran lease?",
        "What are the insurance requirements for Church's Chicken?",
        "Does the H. Sran lease have a radius restriction clause?",
    ]
    
    for q in retrieval_queries:
        print(f"\n🔍 Query: {q}")
        response = rag.query_retrieval(q)
        print(f"📝 Answer: {response.answer}")
    
    print("\n" + "=" * 60)
    print("✅ All tests complete!")
    print("=" * 60)
