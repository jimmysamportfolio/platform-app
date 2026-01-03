"""
Query Router Module

LLM-based semantic router for query classification.
This module is responsible for:
- Classifying queries as 'analytics' or 'retrieval'
- Using Gemini for semantic understanding (not regex)
- Safe fallback to retrieval on errors
"""

import os
from typing import Literal

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv()


# Type alias for route labels
RouteLabel = Literal["analytics", "retrieval"]


class QueryRouter:
    """
    LLM-based semantic router for Legal RAG queries.
    
    Routes queries to either:
    - 'analytics': Aggregate/calculation questions across multiple leases
    - 'retrieval': Specific clause/term lookup questions
    """
    
    SYSTEM_PROMPT = """You are a query router for a Legal RAG system that manages commercial real estate leases.

Your task is to classify the user's question into exactly ONE of two categories:

1. **analytics** - Questions about SPECIFIC VALUES, calculations, aggregations, or comparisons of structured data. Examples:
   - "What is the security deposit amount for Church's Chicken?" (asking for a specific value)
   - "What is the average rent across all properties?"
   - "How many leases expire in 2026?"
   - "What is the total security deposit amount?"
   - "Which tenant pays the highest rent?"
   - "When does the H. Sran lease expire?"
   - "What is the lease term for Starbucks?"
   - "Compare rent amounts between Lease A and B."

2. **retrieval** - Questions about CLAUSES, TERMS, DEFINITIONS, or LEGAL TEXT in the lease documents. Examples:
   - "Who handles HVAC maintenance?"
   - "Does the Starbucks lease have a break clause?"
   - "What does the assignment clause say?"
   - "What is the permitted use for Church's Chicken?"
   - "What happens if the tenant defaults?"
   - "Explain the insurance requirements."
   - "What are the landlord's obligations?"

KEY DISTINCTION:
- If asking for a NUMBER, DATE, AMOUNT, or SPECIFIC FACT → **analytics**
- If asking about WHAT A CLAUSE SAYS or HOW SOMETHING WORKS → **retrieval**

IMPORTANT: Return ONLY the single word "analytics" or "retrieval". No explanation, no punctuation."""

    def __init__(self, model_name: str = "gemini-2.5-flash"):
        """
        Initialize the query router.
        
        Args:
            model_name: Gemini model to use for classification.
            
        Raises:
            ValueError: If GOOGLE_API_KEY is not set.
        """
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")
        
        self.llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0,  # Strict classification
            google_api_key=api_key,
        )
        
        print(f"✅ QueryRouter initialized (model: {model_name})")
    
    def route_query(self, query: str) -> RouteLabel:
        """
        Route a user query to the appropriate handler.
        
        Args:
            query: The user's natural language question.
            
        Returns:
            'analytics' for aggregate/calculation queries,
            'retrieval' for clause/term lookup queries.
        """
        try:
            # Send to LLM for classification
            messages = [
                SystemMessage(content=self.SYSTEM_PROMPT),
                HumanMessage(content=query),
            ]
            
            response = self.llm.invoke(messages)
            
            # Clean the response
            label = response.content.strip().lower()
            
            # Remove any punctuation or extra characters
            label = label.replace(".", "").replace(",", "").replace(":", "").strip()
            
            # Validate response
            if label in ("analytics", "retrieval"):
                return label
            else:
                # Unexpected response, default to retrieval
                print(f"⚠️ Unexpected router response: '{label}'. Defaulting to 'retrieval'.")
                return "retrieval"
                
        except Exception as e:
            # On any error, fallback to retrieval (safer default)
            print(f"⚠️ Router error: {e}. Defaulting to 'retrieval'.")
            return "retrieval"


# --- Test Block ---
if __name__ == "__main__":
    router = QueryRouter()
    
    # Test queries
    test_queries = [
        # Analytics queries
        ("What is the average rent across all properties?", "analytics"),
        ("How many leases expire in 2026?", "analytics"),
        ("What is the total security deposit amount?", "analytics"),
        ("Which tenant pays the highest rent per square foot?", "analytics"),
        
        # Retrieval queries
        ("Who handles HVAC maintenance?", "retrieval"),
        ("Does the Starbucks lease have a break clause?", "retrieval"),
        ("What is the permitted use for Church's Chicken?", "retrieval"),
        ("Compare assignment rules between Lease A and Lease B.", "retrieval"),
        ("What happens if the tenant defaults on rent?", "retrieval"),
    ]
    
    print("\n--- Testing Query Router ---\n")
    correct = 0
    for query, expected in test_queries:
        result = router.route_query(query)
        status = "✅" if result == expected else "❌"
        if result == expected:
            correct += 1
        print(f"{status} Query: '{query[:50]}...'")
        print(f"   Expected: {expected}, Got: {result}\n")
    
    print(f"Accuracy: {correct}/{len(test_queries)} ({100*correct/len(test_queries):.0f}%)")
