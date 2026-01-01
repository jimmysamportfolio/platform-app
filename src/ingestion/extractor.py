"""
Extractor Module

Extracts structured data from parsed lease documents.
This module is responsible for:
- Defining the schema for lease data (Pydantic models)
- Extracting key terms, dates, and financial data from text
- Calculating derived metrics (e.g., average rent)
- Building structured metadata for portfolio analysis
"""

from typing import List, Optional
from datetime import date
from pydantic import BaseModel, Field

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
    permitted_use: Optional[str] = Field(None, description="Description of permitted use")
    exclusive_use: Optional[str] = Field(None, description="Details of exclusivity rights")
    radius_restriction: Optional[str] = Field(None, description="Details of radius restrictions")
    
    # Other Parties
    indemnifier_name: Optional[str] = Field(None, description="Name(s) of indemnifier(s)")

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
            duration = step.end_year - step.start_year + 1  # Inclusive range, e.g., 1-3 is 3 years
            # Handle fractional years if needed, but assuming integer years for now based on typical lease abstracts
            
            # If duration is 0 or negative (invalid data), skip
            if duration <= 0:
                continue
                
            total_value += step.rate_psf * duration
            total_duration += duration
            
        if total_duration == 0:
            return 0.0
            
        return round(total_value / total_duration, 2)