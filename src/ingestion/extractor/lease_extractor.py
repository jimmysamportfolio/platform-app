"""
Lease Extractor Module

Extracts structured lease data from parsed documents using LLM.
Contains the Lease Pydantic model and LeaseExtractor class.
"""

from typing import List, Optional
from datetime import date
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
from config.prompts import LEASE_EXTRACTION_PROMPT

load_dotenv()


class RentStep(BaseModel):
    """Represents a period in the rent schedule."""
    start_year: float = Field(..., description="Start year of this rent step (e.g. 1)")
    end_year: float = Field(..., description="End year of this rent step (e.g. 5)")
    rate_psf: float = Field(..., description="Annual rent per square foot")
    monthly_rent: Optional[float] = Field(None, description="Monthly basic rent amount")
    annual_rent: Optional[float] = Field(None, description="Annual basic rent amount")


class Lease(BaseModel):
    """Represents the structured data extracted from a lease abstract."""
    
    # Key Lease Terms
    lease_date: Optional[date] = Field(None, description="Date of the lease agreement")
    tenant_name: str = Field(..., description="Name of the tenant entity")
    trade_name: Optional[str] = Field(None, description="Trading name of the business (e.g. Church's Chicken)")
    landlord_name: str = Field(..., description="Name of the landlord entity")
    
    # Property Details
    premises_description: str = Field(..., description="Unit number or description of the premises")
    property_address: Optional[str] = Field(None, description="Formatted address of the property")
    rentable_area_sqft: float = Field(..., description="Rentable area in square feet")
    
    # Critical Dates & Term
    commencement_date: Optional[date] = Field(None, description="Lease commencement date")
    expiration_date: Optional[date] = Field(None, description="Lease expiration date")
    term_years: float = Field(..., description="Length of the term in years")
    possession_date: Optional[str] = Field(None, description="Date of possession")
    
    # Financials
    deposit_amount: Optional[float] = Field(None, description="Security deposit amount")
    basic_rent_schedule: List[RentStep] = Field(default_factory=list, description="Schedule of basic rent steps")
    
    # Rights & Restrictions
    renewal_options: Optional[str] = Field(None, description="Summary of renewal options (e.g. '2 x 5 years')")
    permitted_use: Optional[str] = Field(None, description="Description of allowed business activities")
    exclusive_use: Optional[str] = Field(None, description="Details of exclusivity rights")
    radius_restriction: Optional[str] = Field(None, description="Details of radius restrictions")
    
    # Other Parties
    indemnifier_name: Optional[str] = Field(None, description="Name(s) of indemnifier(s)")
    
    # Additional Due Diligence Fields
    tenant_address: Optional[str] = Field(None, description="Tenant's address for notices")
    indemnifier_address: Optional[str] = Field(None, description="Indemnifier's address")
    fixturing_period: Optional[str] = Field(None, description="Fixturing period details (e.g., '90 days free possession')")
    free_rent_period: Optional[str] = Field(None, description="Any free rent period granted to tenant")
    tenant_improvement_allowance: Optional[str] = Field(None, description="TI allowance amount or details")
    offer_to_lease_date: Optional[date] = Field(None, description="Date of the original Offer to Lease")
    indemnity_agreement_date: Optional[date] = Field(None, description="Date of the Indemnity Agreement")

    def calculate_average_rent_psf(self) -> float:
        """
        Calculates the weighted average annual rent PSF over the term.
        Returns 0.0 if no rent schedule is present.
        """
        if not self.basic_rent_schedule:
            return 0.0
            
        total_value = 0.0
        total_duration = 0.0
        
        for step in self.basic_rent_schedule:
            duration = step.end_year - step.start_year + 1  # Inclusive range
            
            if duration <= 0:
                continue
                
            total_value += step.rate_psf * duration
            total_duration += duration
            
        if total_duration == 0:
            return 0.0
            
        return round(total_value / total_duration, 2)


class LeaseExtractor:
    """Extracts structured lease data using Gemini LLM."""
    
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
        self.structured_llm = self.llm.with_structured_output(Lease)

    def extract(self, text_content: str) -> Lease:
        """
        Extracts structured Lease data from the provided text using Gemini.
        
        Args:
            text_content: The raw text of the lease.
            
        Returns:
            Lease object with extracted data.
        """
        prompt = ChatPromptTemplate.from_messages([
            ("system", LEASE_EXTRACTION_PROMPT),
            ("human", "Lease Text:\n{text}")
        ])
        
        chain = prompt | self.structured_llm
        
        try:
            return chain.invoke({"text": text_content})
        except Exception as e:
            print(f"Error during extraction: {e}")
            raise e
