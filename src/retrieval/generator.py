"""
RAG Answer Generator Module

Generates final answers using retrieved context and Gemini LLM.
This module is responsible for:
- Formatting retrieved documents into context
- Constructing prompts with legal assistant persona
- Generating grounded, cited answers
- Preventing hallucination with strict instructions
"""

import os
import re
import sys
from typing import List, Optional, Tuple

# Add project root to path for config imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from config.settings import DEFAULT_LLM_MODEL, LLM_TEMPERATURE
from config.prompts import RAG_SYSTEM_PROMPT, RAG_HUMAN_TEMPLATE

load_dotenv()


class RAGGenerator:
    """
    RAG Answer Generator for Legal Lease queries.
    
    Uses Gemini to generate grounded answers from retrieved documents.
    Enforces citation and prevents hallucination.
    """

    def __init__(self, model_name: str = DEFAULT_LLM_MODEL):
        """
        Initialize the RAG generator.
        
        Args:
            model_name: Gemini model to use for generation.
            
        Raises:
            ValueError: If GOOGLE_API_KEY is not set.
        """
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")
        
        self.llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=LLM_TEMPERATURE,
            google_api_key=api_key,
        )
        
        # Build the prompt template
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", RAG_SYSTEM_PROMPT),
            ("human", RAG_HUMAN_TEMPLATE),
        ])
        
        # Build the chain
        self.chain = self.prompt | self.llm | StrOutputParser()
        
        print(f"✅ RAGGenerator initialized (model: {model_name})")
    
    def _format_context(self, documents: List[Document]) -> str:
        """
        Format retrieved documents into a context string.
        
        Args:
            documents: List of LangChain Document objects.
            
        Returns:
            Formatted context string with document content and metadata.
        """
        if not documents:
            return "No documents were retrieved."
        
        context_parts = []
        for i, doc in enumerate(documents, 1):
            # Extract metadata for citation
            tenant = doc.metadata.get("tenant_name", "Unknown Tenant")
            section = doc.metadata.get("source_section", "")
            source_ref = doc.metadata.get("source_reference", "")
            
            # Build document header
            header = f"--- Document {i} ---"
            if tenant:
                header += f"\nTenant: {tenant}"
            if section:
                header += f"\nSection: {section}"
            if source_ref:
                header += f"\nSource: {source_ref}"
            
            # Combine header and content
            context_parts.append(f"{header}\n\n{doc.page_content}")
        
        return "\n\n".join(context_parts)
    
    def _parse_confidence(self, answer: str) -> Tuple[str, int]:
        """
        Parse the confidence score from the LLM response.
        
        Args:
            answer: Raw LLM response that may contain [CONFIDENCE: X%]
            
        Returns:
            Tuple of (cleaned_answer, confidence_percentage)
        """
        # Look for [CONFIDENCE: X%] pattern
        pattern = r'\[CONFIDENCE:\s*(\d+)%?\]'
        match = re.search(pattern, answer, re.IGNORECASE)
        
        if match:
            confidence = int(match.group(1))
            # Remove the confidence tag from the answer
            cleaned = re.sub(pattern, '', answer, flags=re.IGNORECASE).strip()
            return cleaned, min(100, max(0, confidence))  # Clamp to 0-100
        
        # No confidence found - default to 75% (reasonable answer)
        return answer, 75
    
    def generate_answer(
        self,
        query: str,
        context_documents: List[Document],
    ) -> str:
        """
        Generate an answer based on the query and retrieved documents.
        
        Args:
            query: The user's question.
            context_documents: List of retrieved Document objects.
            
        Returns:
            Generated answer string.
        """
        # Format context from documents
        context = self._format_context(context_documents)
        
        try:
            # Generate answer
            answer = self.chain.invoke({
                "context": context,
                "question": query,
            })
            
            return answer
            
        except Exception as e:
            print(f"❌ Generation error: {e}")
            return f"An error occurred while generating the answer: {str(e)}"
    
    def generate_with_sources(
        self,
        query: str,
        context_documents: List[Document],
    ) -> dict:
        """
        Generate answer with source tracking and confidence score.
        
        Args:
            query: The user's question.
            context_documents: List of retrieved Document objects.
            
        Returns:
            Dictionary with 'answer', 'confidence', and 'sources' keys.
        """
        raw_answer = self.generate_answer(query, context_documents)
        
        # Parse out the confidence score
        answer, confidence = self._parse_confidence(raw_answer)
        
        # Extract source references
        sources = []
        for doc in context_documents:
            source = {
                "tenant": doc.metadata.get("tenant_name", "Unknown"),
                "section": doc.metadata.get("source_section", ""),
                "reference": doc.metadata.get("source_reference", ""),
                "score": doc.metadata.get("rerank_score", doc.metadata.get("score", 0)),
            }
            sources.append(source)
        
        return {
            "answer": answer,
            "confidence": confidence,
            "sources": sources,
            "query": query,
        }


# --- Test Block ---
if __name__ == "__main__":
    import sys
    sys.path.insert(0, "src")
    
    from retrieval.vector_store import LeaseVectorStore
    from retrieval.reranker import LeaseReranker
    
    # Initialize components
    store = LeaseVectorStore(namespace="leases-test")
    reranker = LeaseReranker()
    generator = RAGGenerator()
    
    # Test query
    query = "What is the security deposit amount for Church's Chicken?"
    print(f"\n🔍 Query: '{query}'")
    
    # Retrieve and rerank
    candidates = store.search(query, k=25)
    print(f"📦 Retrieved {len(candidates)} candidates")
    
    top_docs = reranker.rerank(query, candidates, top_n=5)
    print(f"🏆 Reranked to top {len(top_docs)} documents")
    
    # Generate answer
    print("\n📝 Generating answer...\n")
    result = generator.generate_with_sources(query, top_docs)
    
    print("=" * 60)
    print("ANSWER:")
    print("=" * 60)
    print(result["answer"])
    
    print("\n" + "=" * 60)
    print("SOURCES:")
    print("=" * 60)
    for i, src in enumerate(result["sources"], 1):
        print(f"{i}. {src['tenant']} - {src['section']} (score: {src['score']:.3f})")
