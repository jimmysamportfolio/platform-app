"""
Vector Store Wrapper Module

Wrapper for Pinecone vector database operations.
This module is responsible for:
- Connecting to Pinecone index
- Performing semantic search with metadata filtering
- Converting results to LangChain Document objects
- Handling API errors gracefully
"""

import os
import sys
from typing import List, Optional, Dict, Any

# Add project root to path for config imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv
from pinecone import Pinecone
from pinecone.exceptions import PineconeException
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.documents import Document

from config.settings import DEFAULT_EMBEDDING_MODEL, VECTOR_NAMESPACE as DEFAULT_NAMESPACE

load_dotenv()


class LeaseVectorStore:
    """
    Vector store wrapper for lease document retrieval.
    
    Uses Pinecone for vector storage and Google Gemini for embeddings.
    Supports metadata filtering for tenant/property-specific searches.
    """
    
    def __init__(
        self,
        namespace: str = DEFAULT_NAMESPACE,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    ):
        """
        Initialize the vector store.
        
        Args:
            namespace: Pinecone namespace to search within.
            embedding_model: Google embedding model to use.
            
        Raises:
            ValueError: If required environment variables are missing.
        """
        self.namespace = namespace
        
        # Validate environment variables
        api_key = os.getenv("GOOGLE_API_KEY")
        pinecone_key = os.getenv("PINECONE_API_KEY")
        index_name = os.getenv("PINECONE_INDEX_NAME")
        
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")
        if not pinecone_key:
            raise ValueError("PINECONE_API_KEY environment variable not set")
        if not index_name:
            raise ValueError("PINECONE_INDEX_NAME environment variable not set")
        
        # Initialize embeddings
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model=embedding_model,
            google_api_key=api_key,
        )
        
        # Initialize Pinecone
        self.pc = Pinecone(api_key=pinecone_key)
        self.index = self.pc.Index(index_name)
        
        print(f"✅ LeaseVectorStore initialized (namespace: {self.namespace})")
    
    def _build_filter(self, filter_dict: Optional[Dict[str, Any]]) -> Optional[Dict]:
        """
        Build Pinecone filter from a simple dictionary.
        
        Args:
            filter_dict: Simple key-value pairs for exact matching.
                         Example: {'tenant_name': 'Starbucks', 'clause_type': 'rent'}
        
        Returns:
            Pinecone-compatible filter dictionary or None.
        """
        if not filter_dict:
            return None
        
        # Build $and filter for multiple conditions
        conditions = []
        for key, value in filter_dict.items():
            if isinstance(value, list):
                # Handle list values with $in operator
                conditions.append({key: {"$in": value}})
            else:
                # Exact match
                conditions.append({key: {"$eq": value}})
        
        if len(conditions) == 1:
            return conditions[0]
        
        return {"$and": conditions}
    
    def search(
        self,
        query: str,
        k: int = 25,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        """
        Perform semantic search with optional metadata filtering.
        
        Args:
            query: The search query string.
            k: Number of results to return (default: 25).
            filter_dict: Optional metadata filters.
                         Example: {'tenant_name': 'Starbucks'}
        
        Returns:
            List of LangChain Document objects with content and metadata.
            
        Raises:
            PineconeException: If the Pinecone API call fails.
        """
        try:
            # Generate query embedding
            query_embedding = self.embeddings.embed_query(query)
            
            # Build Pinecone filter
            pinecone_filter = self._build_filter(filter_dict)
            
            # Query Pinecone
            results = self.index.query(
                vector=query_embedding,
                top_k=k,
                namespace=self.namespace,
                filter=pinecone_filter,
                include_metadata=True,
            )
            
            # Convert to LangChain Documents
            documents = []
            for match in results.matches:
                metadata = match.metadata or {}
                
                # Extract text content (stored in metadata during ingestion)
                content = metadata.pop("text", "")
                
                # Add score to metadata for transparency
                metadata["score"] = match.score
                metadata["vector_id"] = match.id
                
                documents.append(Document(
                    page_content=content,
                    metadata=metadata,
                ))
            
            return documents
            
        except PineconeException as e:
            print(f"❌ Pinecone error: {e}")
            raise
        except Exception as e:
            print(f"❌ Search error: {e}")
            raise
    
    def search_by_tenant(
        self,
        query: str,
        tenant_name: str,
        k: int = 25,
    ) -> List[Document]:
        """
        Convenience method to search within a specific tenant's documents.
        
        Args:
            query: The search query string.
            tenant_name: Name of the tenant to filter by.
            k: Number of results to return.
            
        Returns:
            List of LangChain Document objects.
        """
        return self.search(query, k=k, filter_dict={"tenant_name": tenant_name})
    
    def search_by_clause_type(
        self,
        query: str,
        clause_type: str,
        k: int = 25,
    ) -> List[Document]:
        """
        Convenience method to search for specific clause types.
        
        Args:
            query: The search query string.
            clause_type: Type of clause to filter by (e.g., 'rent', 'termination').
            k: Number of results to return.
            
        Returns:
            List of LangChain Document objects.
        """
        return self.search(query, k=k, filter_dict={"clause_type": clause_type})
    
    def delete_by_document(self, document_name: str) -> int:
        """
        Delete all vectors associated with a specific document.
        
        Args:
            document_name: Name of the source document to delete.
            
        Returns:
            Number of vectors deleted.
        """
        try:
            # Query for vector IDs with this document name
            # Pinecone doesn't support direct delete by metadata filter,
            # so we need to find the IDs first using a dummy query
            
            # Get a sample embedding for the query
            dummy_embedding = self.embeddings.embed_query("document")
            
            # Query with filter to get matching vector IDs
            results = self.index.query(
                vector=dummy_embedding,
                top_k=10000,  # Get as many as possible
                namespace=self.namespace,
                filter={"source_document": {"$eq": document_name}},
                include_metadata=False,
            )
            
            if not results.matches:
                print(f"⚠️ No vectors found for document: {document_name}")
                return 0
            
            # Extract vector IDs
            vector_ids = [match.id for match in results.matches]
            
            # Delete the vectors
            self.index.delete(
                ids=vector_ids,
                namespace=self.namespace,
            )
            
            print(f"✅ Deleted {len(vector_ids)} vectors for: {document_name}")
            return len(vector_ids)
            
        except Exception as e:
            print(f"❌ Error deleting vectors: {e}")
            raise


# --- Test Block ---
if __name__ == "__main__":
    # Test the vector store
    store = LeaseVectorStore(namespace="leases-test")
    
    print("\n--- Testing Search ---")
    
    # Basic search
    results = store.search("What is the security deposit amount?", k=5)
    print(f"\nFound {len(results)} results for 'security deposit':")
    for i, doc in enumerate(results, 1):
        print(f"\n{i}. Score: {doc.metadata.get('score', 'N/A'):.4f}")
        print(f"   Tenant: {doc.metadata.get('tenant_name', 'N/A')}")
        print(f"   Section: {doc.metadata.get('source_section', 'N/A')}")
        print(f"   Content: {doc.page_content[:150]}...")
    
    # Filtered search
    print("\n--- Testing Filtered Search ---")
    filtered = store.search(
        "What is the rent?",
        k=5,
        filter_dict={"tenant_name": "1256325 B.C. LTD."}
    )
    print(f"\nFound {len(filtered)} results for 'rent' (filtered by tenant):")
    for i, doc in enumerate(filtered, 1):
        print(f"\n{i}. {doc.metadata.get('source_section', 'N/A')}")
