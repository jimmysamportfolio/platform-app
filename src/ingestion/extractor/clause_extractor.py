"""
Clause Extractor Module

Extracts clause summaries for lease comparison.
Contains ExtractedClause, ExtractedClauses models and ClauseExtractor class.
"""

from typing import List, Optional
from pydantic import BaseModel, Field
import os
import sys
import site

# Ensure user site-packages are in path
user_site_packages = site.getusersitepackages()
if user_site_packages not in sys.path:
    sys.path.append(user_site_packages)

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

# Add project root to path for config imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from config.settings import DEFAULT_LLM_MODEL
from config.prompts import CLAUSE_EXTRACTION_PROMPT

load_dotenv()


# Standard clause types for extraction
STANDARD_CLAUSE_TYPES = [
    "rent_payment",
    "security_deposit", 
    "term_renewal",
    "use_restrictions",
    "maintenance_repairs",
    "insurance",
    "termination",
    "assignment_subletting",
    "default_remedies",
]


class ExtractedClause(BaseModel):
    """Represents a single extracted clause with summary and key terms."""
    clause_type: str = Field(..., description="One of: rent_payment, security_deposit, term_renewal, use_restrictions, maintenance_repairs, insurance, termination, assignment_subletting, default_remedies")
    article_reference: Optional[str] = Field(None, description="Article/section number (e.g., 'Article 3', 'Section 5.01')")
    summary: str = Field(..., description="Concise summary with key facts and numbers. Max 40 words.")
    key_terms: str = Field(..., description="3-5 key values, comma-separated (e.g., '$25/sqft, 5 years, 2 options')")


class ExtractedClauses(BaseModel):
    """Collection of extracted clauses from a lease."""
    clauses: List[ExtractedClause] = Field(default_factory=list, description="List of extracted clause summaries")


class ClauseExtractor:
    """
    Extracts clause summaries and key terms from lease documents.
    
    Produces scannable comparison data instead of full clause text.
    """
    
    def __init__(self, model_name: str = DEFAULT_LLM_MODEL):
        self.api_key = os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment variables.")
        
        # Initialize Gemini
        self.llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0,
            max_retries=2,
            google_api_key=self.api_key
        )
        
        # Bind the schema to the model
        self.structured_llm = self.llm.with_structured_output(ExtractedClauses)
    
    def extract_clauses(self, text_content: str) -> List[dict]:
        """
        Extract clause summaries and key terms from lease text.
        
        Args:
            text_content: The raw text of the lease document.
            
        Returns:
            List of clause dictionaries with clause_type, summary, key_terms, article_reference.
        """
        prompt = ChatPromptTemplate.from_messages([
            ("system", CLAUSE_EXTRACTION_PROMPT),
            ("human", "Lease Text:\n{text}")
        ])
        
        chain = prompt | self.structured_llm
        
        try:
            result = chain.invoke({"text": text_content[:100000]})  # Limit to avoid token overflow
            return [clause.model_dump() for clause in result.clauses]
        except Exception as e:
            print(f"Error during clause extraction: {e}")
            return []
