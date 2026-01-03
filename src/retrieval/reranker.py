"""
Reranker Module

Local reranking using FlashRank (CPU-based, no API costs).
This module is responsible for:
- Reranking retrieved documents for improved relevance
- Using FlashRank's lightweight TinyBERT model
- Preserving original metadata through reranking
- Handling edge cases (empty inputs, single documents)
"""

import os
import sys
from typing import List, Optional

# Add project root to path for config imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from flashrank import Ranker, RerankRequest
from langchain_core.documents import Document

from config.settings import DEFAULT_RERANKER_MODEL, RERANKER_CACHE_DIR


class LeaseReranker:
    """
    Local reranker for lease document retrieval.
    
    Uses FlashRank's TinyBERT model for fast, CPU-based reranking.
    No external API calls required - runs entirely locally.
    """
    
    # FlashRank model options (from fastest to most accurate):
    # - "ms-marco-TinyBERT-L-2-v2" (Default, fastest, ~4MB)
    # - "ms-marco-MiniLM-L-12-v2" (Balanced, ~34MB)
    # - "rank-T5-flan" (Most accurate, ~110MB)

    def __init__(self, model_name: str = DEFAULT_RERANKER_MODEL, cache_dir: str = RERANKER_CACHE_DIR):
        """
        Initialize the reranker.
        
        Args:
            model_name: FlashRank model to use.
            cache_dir: Directory to cache downloaded model.
        """
        self.model_name = model_name
        
        # Initialize FlashRank Ranker
        self.ranker = Ranker(model_name=model_name, cache_dir=cache_dir)
        
        print(f"✅ LeaseReranker initialized (model: {self.model_name})")
    
    def rerank(
        self,
        query: str,
        documents: List[Document],
        top_n: int = 5,
    ) -> List[Document]:
        """
        Rerank documents based on relevance to the query.
        
        Args:
            query: The search query to rank against.
            documents: List of LangChain Document objects from vector search.
            top_n: Number of top documents to return.
            
        Returns:
            List of reranked Document objects (best first), limited to top_n.
        """
        # Handle edge cases
        if not documents:
            return []
        
        if len(documents) <= 1:
            return documents[:top_n]
        
        # Prepare passages for FlashRank
        # FlashRank expects list of dicts with 'id', 'text', and optional 'meta'
        passages = []
        for i, doc in enumerate(documents):
            passages.append({
                "id": i,
                "text": doc.page_content,
                "meta": doc.metadata,  # Preserve original metadata
            })
        
        # Create rerank request
        rerank_request = RerankRequest(query=query, passages=passages)
        
        # Perform reranking
        try:
            rerank_results = self.ranker.rerank(rerank_request)
        except Exception as e:
            print(f"⚠️ Reranking failed: {e}. Returning original order.")
            return documents[:top_n]
        
        # Convert back to LangChain Documents, preserving metadata
        reranked_documents = []
        for result in rerank_results[:top_n]:
            original_idx = result["id"]
            original_doc = documents[original_idx]
            
            # Create new document with rerank score added to metadata
            metadata = original_doc.metadata.copy()
            metadata["rerank_score"] = result["score"]
            metadata["original_rank"] = original_idx + 1
            
            reranked_documents.append(Document(
                page_content=original_doc.page_content,
                metadata=metadata,
            ))
        
        return reranked_documents
    
    def rerank_with_scores(
        self,
        query: str,
        documents: List[Document],
        top_n: int = 5,
    ) -> List[tuple[Document, float]]:
        """
        Rerank documents and return with explicit scores.
        
        Args:
            query: The search query to rank against.
            documents: List of LangChain Document objects.
            top_n: Number of top documents to return.
            
        Returns:
            List of (Document, score) tuples.
        """
        reranked = self.rerank(query, documents, top_n)
        return [(doc, doc.metadata.get("rerank_score", 0.0)) for doc in reranked]


# --- Test Block ---
if __name__ == "__main__":
    import sys
    sys.path.insert(0, "src")
    
    from retrieval.vector_store import LeaseVectorStore
    
    # Initialize components
    store = LeaseVectorStore(namespace="leases-test")
    reranker = LeaseReranker()
    
    # Perform initial search
    query = "What is the security deposit amount?"
    print(f"\n🔍 Query: '{query}'")
    
    # Get 25 candidates from vector search
    candidates = store.search(query, k=25)
    print(f"\n📦 Vector search returned {len(candidates)} candidates")
    
    # Rerank to top 5
    reranked = reranker.rerank(query, candidates, top_n=5)
    
    print(f"\n🏆 Top {len(reranked)} reranked results:")
    for i, doc in enumerate(reranked, 1):
        print(f"\n{i}. Rerank Score: {doc.metadata.get('rerank_score', 0):.4f}")
        print(f"   Original Rank: {doc.metadata.get('original_rank', 'N/A')}")
        print(f"   Vector Score: {doc.metadata.get('score', 'N/A'):.4f}")
        print(f"   Tenant: {doc.metadata.get('tenant_name', 'N/A')}")
        print(f"   Section: {doc.metadata.get('source_section', 'N/A')}")
        print(f"   Content: {doc.page_content[:150]}...")
