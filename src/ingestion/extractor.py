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
import os
import json
import sys
import site
# Ensure user site-packages are in path (fixes ModuleNotFoundError for locally installed packages)
user_site_packages = site.getusersitepackages()
if user_site_packages not in sys.path:
    sys.path.append(user_site_packages)

from dotenv import load_dotenv

# Using LangChain + Google GenAI for extraction
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

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
            
            # If duration is 0 or negative (invalid data), skip
            if duration <= 0:
                continue
                
            total_value += step.rate_psf * duration
            total_duration += duration
            
        if total_duration == 0:
            return 0.0
            
        return round(total_value / total_duration, 2)

class LeaseExtractor:
    def __init__(self, model_name: str = "gemini-2.5-flash"):
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
            ("system", """You are an expert commercial real estate lease abstractor. Your goal is to accurately extract key terms from the provided lease document text.

CRITICAL EXTRACTION GUIDELINES:

1. DATES - Look carefully for:
   - "Possession Date": Often in Schedule B, may say "estimated to be [DATE]"
   - "Commencement Date": Often defined as "expiry of the Fixturing Period" - if so, CALCULATE it by adding the Fixturing Period days to the Possession Date
   - "Expiration Date": Calculate from Commencement Date + Term Years if not explicit
   - "Fixturing Period": Look for phrases like "X days' free possession"

2. EXCLUSIVE USE - Search for:
   - Section titled "Exclusive Use" (often in Schedules)
   - Clauses about competitors the landlord cannot lease to (e.g., "will not lease to any tenant whose principal business is...")
   - Extract the SPECIFIC restriction details

3. RADIUS RESTRICTION - Look for:
   - Clauses restricting tenant from operating similar business within X miles/km
   - Often in Schedule B or restrictive covenants section

4. RENEWAL OPTIONS - Format as: "X option(s) to renew for Y year term(s)"

5. DATES FORMAT: Always use YYYY-MM-DD format

6. If a field can be CALCULATED from other data (e.g., expiration = commencement + term), DO the calculation.

7. Read the ENTIRE document including all Schedules (A, B, C, D) - key information is often there.

8. RENT SCHEDULE - Extract ALL rent steps from the Basic Rent table:
   - Look for tables with columns like "Lease Year", "Per Square Foot", "Per Annum", "Per Month"
   - For EACH rent step, extract: start_year, end_year, rate_psf, monthly_rent, annual_rent
   - ALWAYS extract the monthly_rent value (often labeled "Per Month" in the table)
   - If monthly_rent is not explicit, CALCULATE it: annual_rent / 12

BE THOROUGH - missing data often exists in Schedules at the end of the document."""),
            ("human", "Lease Text:\n{text}")
        ])
        
        chain = prompt | self.structured_llm
        
        try:
            return chain.invoke({"text": text_content})
        except Exception as e:
            print(f"Error during extraction: {e}")
            raise e


# --- Clause Extraction for Comparison Tool ---

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
    
    def __init__(self, model_name: str = "gemini-2.5-flash"):
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
            ("system", """You are extracting lease clause summaries for side-by-side comparison. Extract EXACTLY these 9 clause types if present:

CLAUSE TYPES (use these exact values):
- rent_payment: Base rent, escalations, additional rent, CAM, NNN
- security_deposit: Amount, conditions for return
- term_renewal: Lease term length, renewal options, notice periods  
- use_restrictions: Permitted use, exclusive use, prohibited activities
- maintenance_repairs: Tenant vs landlord responsibilities
- insurance: Required coverage types and amounts
- termination: Early termination rights, conditions
- assignment_subletting: Consent requirements, conditions
- default_remedies: Cure periods, remedies available

OUTPUT FORMAT - BE CONSISTENT:
- summary: 1-2 short phrases. Max 40 words. Use **bold** for key numbers and values (e.g., **$22.50/sqft**, **10 years**, **3%**).
- key_terms: Exactly 3-5 values, comma-separated. Include dollar amounts and time periods.
- article_reference: Use format "Article X" or "Section X.XX" or "Schedule X"

EXAMPLES:
| clause_type | summary | key_terms |
|-------------|---------|-----------|
| rent_payment | Base rent **$22.50/sqft** Year 1, increasing **3%** annually. **Triple net** lease. | $22.50/sqft, 3% annual, NNN |
| security_deposit | **$45,000** deposit (2 months rent). Returned within **30 days**. | $45,000, 2 months, 30 days |
| term_renewal | **10-year** initial term. **Two 5-year** renewal options at market rent. | 10 years, 2 options, 5 years each |
| use_restrictions | **Restaurant** use only. **Exclusive for sushi** within center. No alcohol. | Restaurant, exclusive sushi, no alcohol |
| termination | **No early termination**. Must provide **6-month** notice for non-renewal. | No early out, 6-month notice |

IMPORTANT: 
- Use **bold** markdown for all key numbers, amounts, and important terms
- Only extract clauses that are EXPLICITLY stated in the lease
- Use consistent formatting across all clauses
- If a clause isn't clearly defined, skip it"""),
            ("human", "Lease Text:\n{text}")
        ])
        
        chain = prompt | self.structured_llm
        
        try:
            result = chain.invoke({"text": text_content[:100000]})  # Limit to avoid token overflow
            return [clause.model_dump() for clause in result.clauses]
        except Exception as e:
            print(f"Error during clause extraction: {e}")
            return []


# --- Test Block ---
if __name__ == "__main__":
    # A dummy lease snippet to test the logic
    dummy_lease_text = """
        
    LEASE

    BETWEEN:

    PLATFORM PROPERTIES (MAPLE RIDGE) LTD.

    (Landlord)

    AND:

    1256325 B.C. LTD.

    (Tenant)

    AND:

    Harpreet Bahia &#x26; Jatinder Badyal

    (collectively, the Indemnifier)

    INITIAL

    Landlord  Tenant

    MR – July 2020






    # TABLE OF CONTENTS

    # ARTICLE 1 INTERPRETATION

    1.01     Basic Terms.                                                            1

    1.02     Definitions.                                                            2

    1.03     Schedules.                                                              8

    # ARTICLE 2 DEMISE AND TERM

    2.01     Demise.                                                                 8

    2.02     Survey of Rentable Area.                                                8

    2.03     Term.                                                                   9

    2.04     Acceptance of Premises.                                                 9

    2.05     Use of Common Areas.                                                    9

    2.06     Relocation.                                                             9

    # ARTICLE 3 RENT, ADDITIONAL RENT AND DEPOSIT

    3.01     Rent.                                                                  11

    3.02     Payment.                                                               12

    3.03     Adjustments.                                                           12

    3.04     Deposit.                                                               12

    3.05     Additional Rent.                                                       13

    3.06     Payment of Rent.                                                       13

    3.07     Gross Revenues Statements                                              14

    # ARTICLE 4 OPERATING COSTS

    4.01     Proportionate Share.                                                   15

    4.02     Allocation.                                                            15

    4.03     Re-Allocation of Operating Costs and Taxes.                            16

    4.04     Net Lease.                                                             16

    # ARTICLE 5 TAXES

    5.01     Payment of Taxes.                                                      16

    5.02     Tenant’s Taxes.                                                        17

    5.03     Right of Appeal.                                                       17

    5.04     Business Tax, etc.                                                     18

    5.05     Evidence of Payments.                                                  18

    # ARTICLE 6 CONTROL OF SHOPPING CENTRE AND COMMON AREAS

    6.01     Landlord’s Additions.                                                  18

    6.02     Supply of Services.                                                    18

    6.03     Required Alterations.                                                  18

    6.04     Landlord's Right to Exhibit Premises and Place Signs.                  18

    6.05     Landlord May Perform Tenant's Covenants, etc.                          19

    6.06     Tenant's Use of Parking Areas.                                         19

    6.07     Landlord's Right to Remove Vehicles.                                   19

    6.08     Control of Common Areas.                                               19

    6.09     Merchandise on Common Areas.                                           20

    6.10     Alterations and Additions to the Shopping Centre.                      20

    6.11     Display Windows.                                                       21

    6.12     Common Areas.                                                          21

    6.13     Management of Shopping Centre.                                         21

    6.14     Access.                                                                21

    6.15     Maintenance.                                                           22

    # ARTICLE 7 UTILITIES AND HEATING, VENTILATING AND AIR CONDITIONING

    7.01     Utilities.                                                             22

    INITIAL

    Landlord  Tenant

    MR – July 2020






    # 7.02 Light Fixtures and Ceilings.

    22

    # 7.03 Damaging Equipment.

    23

    # 7.04 Heating, Ventilating and Air Conditioning.

    23

    # ARTICLE 8 USE OF PREMISES

    # 8.01 Use of Premises.

    23

    # 8.02 No Nuisance, etc.

    23

    # 8.03 Injurious Activity.

    24

    # 8.04 Comply with Laws, etc.

    24

    # 8.05 Comply with Rules.

    24

    # 8.06 Environmental Laws.

    24

    # 8.07 Environmental Indemnity.

    25

    # 8.08 Environmental Enquiries.

    25

    # 8.09 Notice of Damage, Defects, etc.

    25

    # 8.10 Prohibited Uses.

    26

    # 8.11 Obligation to Operate.

    26

    # 8.12 Quiet Possession.

    27

    # 8.13 Energy Conservation.

    27

    # ARTICLE 9 ASSIGNMENT AND SUBLETTING

    # 9.01 Assigning or Subletting.

    27

    # 9.02 No Release.

    28

    # 9.03 Change of Control.

    28

    # 9.04 Renewals.

    28

    # 9.05 Costs.

    28

    # 9.06 Licenses, Concessions.

    28

    # ARTICLE 10 INSURANCE AND INDEMNITY

    # 10.01 Tenant’s Insurance.

    28

    # 10.02 Waiver of Subrogation.

    29

    # 10.03 Insurers.

    29

    # 10.04 Certificates.

    30

    # 10.05 Insurance Defaults.

    30

    # 10.06 Settlement.

    30

    # 10.07 Indemnity to the Landlord.

    30

    # 10.08 Amendments.

    30

    # 10.09 Acts Conflicting with Insurance.

    31

    # 10.10 Landlord not Responsible for Injuries, Loss, Damage, etc.

    31

    # 10.11 No Liability for Indirect Damages.

    31

    # 10.12 Landlord’s Insurance.

    31

    # 10.13 Tenant’s Contractor’s Insurance

    31

    # ARTICLE 11 TENANT ALTERATIONS, REPAIRS, INSTALLATIONS, FIXTURES

    # 11.01 Repairs.

    32

    # 11.02 Refurbish.

    32

    # 11.03 Care of the Premises.

    32

    # 11.04 Damage to Premises.

    32

    # 11.05 Right to Examine.

    32

    # 11.06 Landlord's Consent Required.

    32

    # 11.07 Carrying out Improvements.

    33

    # 11.08 Tenant's Removal of Fixtures, etc.

    33

    # 11.09 Goods, Chattels, etc. Not to be Disposed of.

    33

    # 11.10 Mandatory Removal of Fixtures, etc.

    33

    # 11.11 Liens and Encumbrances.

    34

    INITIAL

    Landlord  Tenant

    MR – July 2020






    # 11.12 Signs.

    # 11.13 Peaceful Surrender.

    # ARTICLE 12 DAMAGE OR DESTRUCTION AND EXPROPRIATION

    # 12.01 Damage or Destruction of Premises.

    # 12.02 Expropriation.

    # ARTICLE 13 STATUS STATEMENT, REGISTRATION AND SUBORDINATION

    # 13.01 Certificates.

    # 13.02 Registration.

    # 13.03 Subordination.

    # 13.04 Tenant Information

    # ARTICLE 14 DEFAULT

    # 14.01 Default.

    # 14.02 Bankruptcy, etc.

    # 14.03 Consequences of Re-Entry.

    # 14.04 Distress.

    # 14.05 Landlord's Costs in Enforcing Lease.

    # 14.06 Payments After Termination

    # 14.07 Personal Property Security.

    # ARTICLE 15 GENERAL

    # 15.01 Force Majeure.

    # 15.02 No Representations by Landlord.

    # 15.03 Holding Over.

    # 15.04 Landlord - Tenant Relationship.

    # 15.05 Time of Essence.

    # 15.06 Waiver.

    # 15.07 Interest.

    # 15.08 Entire Agreement.

    # 15.09 No Changes or Waivers.

    # 15.10 Notices.

    # 15.11 Headings and Marginal Notes.

    # 15.12 Rights Cumulative.

    # 15.13 Sale By Landlord.

    # 15.14 British Columbia Law.

    # 15.15 Provisions Severable.

    # 15.16 Joint and Several.

    # 15.17 Interpretation.

    # 15.18 Enurement.

    # 15.19 Indemnity

    # SCHEDULE A (Plan of Premises)

    # SCHEDULE B (Miscellaneous Provisions)

    # SCHEDULE C (Percentage Rent)

    # SCHEDULE D (Indemnity Agreement)

    INITIAL

    Landlord  Tenant

    MR – July 2020






    1

    This Lease dated for reference this 13ᵗʰ day of July, 2020.

    BETWEEN:

    PLATFORM PROPERTIES (MAPLE RIDGE) LTD. (Inc. No. BC1104846), a company incorporated under the laws of the Province of British Columbia and having a place of business at #900 - 1200 West 73rd Avenue, Vancouver, B.C., V6P 6G5 (the "Landlord")

    AND:

    1256325 B.C. LTD. (Inc. No. 1256325), a company incorporated under the laws of the Province of British Columbia, having its registered and records office at #202 – 32625 South Fraser Way, Abbotsford, B.C., V2T 1X8 (the "Tenant")

    AND:

    Harpreet Bahia having an address at 3477 Blueberry Court, Abbotsford, B.C., V3G 3C9

    AND:

    Jatinder Badyal having an address at 3816 Clinton Street, Burnaby, B.C., V5J 2K1 (collectively, the "Indemnifier")

    # ARTICLE 1

    # INTERPRETATION

    # 1.01 Basic Terms.

    The following is a summary of certain basic Lease provisions which are referred to in subsequent provisions of this Lease. If there is any conflict between the contents of this summary and the remaining provisions of this Lease, the remaining provisions shall govern:

    - (a) Premises: Unit #170, located upon lands municipally described as 11939 240 Street, Maple Ridge, B.C. or such other unit number or municipal address as may be created by subdivision or other modification from time to time, being those premises shown in dark outline on Schedule A hereto (section 2.01);
    - (b) Rentable Area

    INITIAL

    Landlord  Tenant

    MR – July 2020




    # 2

    of the Premises: Estimated to be 1,761 square feet (subject to confirmation by measurement by the Landlord's architect or surveyor) (section 2.02);

    (c) Commencement Date: Expiry of the Fixturing Period (section 1.02);

    (d) Expiration Date: The date which is the last day of the Initial Term or if the Initial Term is renewed, the last day of the last renewal to the Term;

    (e) Initial Term: The Initial Term is ten (10) years plus, if the Commencement Date is not the first day of a calendar month, the number of days from the Commencement Date to the last day of the month in which the Commencement Date occurs, beginning on the Commencement Date and ending at midnight on the Expiration Date of the Initial Term;

    (f) Renewal Options: Two (2) options to renew for further five (5) year terms (Schedule B);

    (g) Basic Rent:

    | Lease Year | Per Square Foot | Per Annum  | Per Month |
    | ---------- | --------------- | ---------- | --------- |
    | 1-3        | $40.00          | $70,440.00 | $5,870.00 |
    | 4-7        | $43.00          | $75,723.00 | $6,310.25 |
    | 8-10       | $46.00          | $81,006.00 | $6,750.50 |

    (section 3.01);

    (h) Tenant’s Proportionate Share: as set out in section 1.02;

    (i) Deposit: $20,000.00 (inclusive of GST) (section 3.04);

    (j) Permitted Use: The Premises will be used solely for the purpose of operating a sit down, delivery and take out style fried chicken restaurant for the sale of a variety of chicken products as primary menu items, and as ancillary items, fries, biscuits, carbonated beverages, milk, juice, and other related products (section 8.01);

    (k) Tenant’s Trade Name: Church’s Chicken (section 8.01);

    # 1.02 Definitions.

    In this Lease, unless otherwise stated, the following terms shall have the following meanings:

    "Additional Rent" has the meaning set out in section 3.01(a)(ii);

    INITIAL

    Landlord Tenant

    MR – July 2020






    # Definitions

    "Basic Rent" has the meaning set out in section 1.01(g);

    "Buildings" means all buildings located on the Property from time to time;

    "Commencement Date" means the day after the expiry date of the Fixturing Period;

    # Common Areas

    "Common Areas" means:

    1. all parts of the Shopping Centre which, from time to time, are not designated or intended by the Landlord to be leased to tenants of the Shopping Centre; and
    2. those areas which serve or are for the benefit of the Shopping Centre and which are designated from time to time by the Landlord as part of the Common Areas.

    Common Areas include, without limitation, all areas which are provided or designated (and which may be changed from time to time) by the Landlord for the use or benefit of the tenants, their employees, customers and other invitees in common with others entitled to the use or benefit thereof in the manner and for the purposes permitted by this Lease.

    Without limiting the generality of the foregoing, Common Areas include Common Facilities, hallways, common washrooms, roof, walls, parking areas, stairwells, sidewalks, common loading areas, arcades, administration offices, telephone, meter, valve, mechanical, mail and janitor rooms and storage areas not occupied by tenants of the Shopping Centre and landscaped areas;

    # Common Facilities

    "Common Facilities" means those facilities, utilities, improvements, equipment and installations which serve or are for the benefit of the Shopping Centre and which are provided or designated (and which may be changed from time to time) by the Landlord for the use or benefit of the tenants of the Shopping Centre, their employees, customers and other invitees in common with others entitled to the use or benefit thereof in the manner and for the purposes permitted by this Lease. Without limiting the generality of the foregoing, Common Facilities include music and public address systems, electrical, plumbing, drainage, mechanical and all other installations, equipment or services located in the Shopping Centre or on lands adjacent thereto or related thereto as well as the structures housing the same, the cost of which is borne or shared by the Landlord; HVAC facilities and systems; escalators, ramps, moving sidewalks and elevators (passenger, freight and service) and other transportation equipment and systems; telephone, meter, valve, mechanical, fire prevention, security and communications systems;

    "Corporation Capital Tax" shall mean the applicable amount (as described below) of any tax or taxes levied against the Landlord and owners of the Shopping Centre by any governmental authority having jurisdiction based upon or computed by reference to the paid-up capital or place of business of the Landlord and the owners of the Shopping Centre as determined for the purposes of such tax or taxes; and for the purpose of this provision the phrase "applicable amount" of such tax or taxes means the amount of tax that would be payable from time to time under any statute of Canada and any statute of British Columbia which imposes tax in respect of the capital of corporations.

    "Deposit" has the meaning set out in section 3.04(a);

    INITIAL Landlord Tenant

    MR – July 2020






    # Definitions

    "Easement Area" means the area, if any, shown cross hatched on the plan attached hereto as Schedule A, and labelled as "Easement Area" provided the Easement Area may not be expanded or enclosed by the Tenant without the prior written consent of the Landlord;

    "Environmental Laws" means any and all statutes, laws, regulations, orders, bylaws, standards, guidelines, permits and other lawful requirements of any federal, provincial, municipal or other governmental authority having jurisdiction over the Premises and the Shopping Centre now or hereafter in force with respect in any way to the environment, environmental assessment, health, occupational health and safety, or transportation of dangerous goods, including the principles of common law and equity;

    "Fixturing Period" has the meaning set out in Schedule B hereof;

    "Gross Revenues" if applicable, means all charges made by the Tenant and its agents, concessionaires, sub-lessees, franchisees and licensees and any other person or firm to customers for all sales or leasing of merchandise and services at or from the Premises, including sales from telephone and mail order, whether for cash, cheque, credit, gift certificate or otherwise, and all other receipts and receivables whatsoever from all business conducted at or from the Premises (including all interest, instalment and finance charges). No deductions will be made for uncollectible credit amounts. Without limiting the foregoing, Gross Revenues will include orders received on the Premises, wherever filled, charges for merchandise and services on the earlier of the date the services are rendered or the merchandise is billed or charged to the customer, all deposits given on merchandise purchased from the Premises and not refunded to purchasers, receipts from vending or amusement machines located on the Premises and the cash proceeds of any business interruption insurance paid to the Tenant with respect to the Premises. Excluded from Gross Revenues are provincial sales taxes, goods and services taxes and any other taxes imposed by any government authority and required to be collected as a direct and separate tax by the Tenant from its customers and not included in the retail sales price of the merchandise and refunds and adjustments made on merchandise claimed to be defective or unsatisfactory, returned by a customer and accepted by the Tenant;

    "GST" means any and all goods and services or other value added tax imposed on the Tenant or Landlord or both for which the Landlord is liable or is obligated to collect from the Tenant;

    "Hazardous Substances" means (a) any substance which, when released into the Shopping Centre or any part thereof, or into the natural environment, is likely to cause, at any time, material harm or degradation to the Shopping Centre or any part thereof, or to the natural environment or material risk to human health, and includes, without limitation, any flammables, explosives, radioactive materials, asbestos, polychlorinated biphenyls (PCB's), chlorofluorocarbons (CFCV's), hydrochlorofluorocarbons (HFC's), hydrocarbon contaminants, urea formaldehyde foam insulation, radon gas, underground or above ground tanks, chemicals known to cause cancer or reproductive toxicity, pollutants, contaminants, hazardous wastes, toxic or deleterious substances or related materials, petroleum and petroleum products, special waste or waste of any kind or (b) any substance declared to be hazardous, corrosive or toxic under any laws now or hereafter enacted or promulgated by any authorities, or (c) both (a) and (b);

    INITIAL

    Landlord  Tenant

    MR – July 2020






    # Definitions

    "HVAC" means the heating, ventilating and air-conditioning plants and systems necessary to heat, ventilate and air-condition the Common Areas and all leasable premises excepting those leased premises with separate plants and systems and includes, without limitation, the chilled and heated water systems, freon systems or air generating facilities and any storage and distribution systems leading therefrom;

    "Initial Term" means the initial term of this Lease described in section 1.01(e);

    "Landlord’s Work" means that work described on the Schedule forming part of the Offer to Lease, titled Landlord’s Work and referred to in Schedule B hereto as Landlord's Work. Unless there are additional terms added to Schedule B hereto, the Landlord's Work set out in the Offer to Lease shall govern;

    "Lease" means this lease and all schedules;

    "Offer to Lease" means that offer to lease dated June 10, 2020, the amendment dated June 30, 2020 and any other amendments or modifications regarding the lease of the Premises entered into between the Landlord and the Tenant before the date of this Lease;

    "Operating Costs" means, without duplication, all of the costs and expenses of every kind associated with the operation, maintenance, repair, replacement, management and administration of the Shopping Centre, including without limitation:

    | (a) | costs of all insurance which the Landlord is obligated or permitted to obtain pursuant to this Lease, or which the Landlord deems reasonable to obtain, and the deductible on any insurance policy which policy has a claim for payment arising during the Term;                                                                                                                                                                                                                             |
    | --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
    | (b) | maintenance, repair and replacements of HVAC;                                                                                                                                                                                                                                                                                                                                                                                                                                                |
    | (c) | costs of providing telephone, electric, oil, gas, water, sewage and other utilities, excluding those utilities consumed on the Premises which will be paid by the Tenant pursuant to section 7.01, and costs of replacing building standard electric light fixtures, ballasts, tubes, starters, lamps, lightbulbs and controls;                                                                                                                                                              |
    | (d) | 1. providing security, supervision, traffic control, parking area maintenance, janitorial, landscaping, window cleaning, sign maintenance, and snow removal services,
    2. machinery, supplies, tools, equipment and materials used in connection with the Shopping Centre or any rentals thereof, and
    3. waste collection, disposal and recycling, excluding the cost of waste collection, disposal and recycling generated from the Premises if paid by the Tenant pursuant to section 7.01; |
    | (e) | license fees payable by the Landlord in relation to the Shopping Centre;                                                                                                                                                                                                                                                                                                                                                                                                                     |
    | (f) | roof repairs and replacements;                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
    | (g) | all fees, salaries, wages, benefits and other remuneration of employees and consultants providing services in relation to the operation, management, administration, repair and maintenance of the Shopping Centre;                                                                                                                                                                                                                                                                          |

    INITIAL

    Landlord Tenant

    MR – July 2020






    # 6

    (h) property management and administration fees equal to five percent (5%) percent of Basic Rent;

    (i) costs of all repairs and replacements to and maintenance and operation of the Shopping Centre and the systems, facilities, machinery, fixtures and equipment servicing the Shopping Centre provided the Landlord may elect to amortise the cost of any repairs or replacements over the useful life thereof, as determined by the Landlord acting reasonably, and bring such amounts into Operating Costs on an annual basis, together with interest on the unamortised portion calculated annually at two percent above the commercial prime lending rate from time to time of the Landlord's bank;

    (j) costs of any installations, additions or other work to the Shopping Centre made as a result of: i) any government requirement or ii) the installation or addition for the purpose of reducing other Operating Costs such as electricity, heating, fuel, janitorial or maintenance costs or to improve security provided the Landlord may elect to amortise these costs over the useful life thereof, as determined by the Landlord acting reasonably, and bring such amounts into Operating Costs on an annual basis, together with interest on the unamortised portion calculated annually at two percent above the commercial prime lending rate from time to time of the Landlord's bank;

    and all other expenses, costs, charges and outlays whatsoever in connection with or related to the Shopping Centre and the operation, maintenance, repair, management and administration of the Shopping Centre but excluding the costs of (i) the Landlord's income taxes in respect of income earned from the Shopping Centre and (ii) the capital cost of replacements or repairs which are attributable to structural defects as a result of defective design or construction but not excluding normal maintenance of structures;

    "Percentage Rent" means the amount by which NIL% of the Gross Revenues for the relevant period exceeds the Basic Rent payable for the same period and if no number is written in this definition this Lease shall not be subject to Percentage Rent;

    "Possession Date" has the meaning set out in Schedule B;

    "Premises" means the area being all or a portion of a Building located on the Property and forming part of the Shopping Centre as more particularly set out in section 1.01(a);

    "Property" means those lands municipally located at 11939 240 Street, Maple Ridge, B.C. or such other municipal address as may be created by subdivision or other modification from time to time, legally described as:

    PID 012-292-966, South Half Lot 1 Section 16 Township 12 New Westminster District Plan 1676 Except: Plan EPP85537 or such other legal address as may be created by subdivision or other modification from time to time;

    "Proportionate Share" means the percentage equal to the fraction which has as its numerator the Rentable Area of the Premises, and has as its denominator, the Rentable Area of all premises in the Shopping Centre, provided that in the calculation of the Rentable Area of the Shopping Centre there shall be excluded therefrom the square footage of all storage areas, mezzanine areas and any premises occupied by a tenant

    INITIAL

    Landlord Tenant

    MR – July 2020






    # 7

    who does not pay for Operating Costs and/or Taxes on a proportionate share basis, subject to any adjustments made pursuant to the terms of section 2.02;

    "Rent" means Additional Rent, Percentage Rent, if any, and Basic Rent;

    "Rentable Area" means an area of any premises (not including mezzanines) which may be leased to tenants, and shall be calculated by measuring from the exterior surfaces of exterior walls, from the exterior surfaces of interior walls separating a premises from Common Area and from the centre line of party or demising walls separating two or more areas which may be leased to tenants and will include all interior space whether or not occupied by interior projections, stairways, shafts, ventilation spaces, columns, pipes, conduits or the like and other physical features plus a portion of the area of common corridors, elevators, washrooms, mechanical, telephone, electrical and other utility rooms, enclosed loading areas and other areas serving any such premises in any Building, such portion to be determined by the Landlord in a reasonable and consistent manner based on the degree to which those areas service such premises;

    "Rules and Regulations" means any and all rules and regulations created by the Landlord for the better governance of the operations of the Shopping Centre;

    "Shopping Centre" means the Property, the Premises, all Buildings, and all other improvements and facilities from time to time located thereon;

    "Taxes" means all taxes, school taxes, local improvement taxes, sewer, water and utilities taxes, and all other rates, charges, duties, levies and assessments whatsoever whether municipal, governmental, provincial, federal, school or otherwise, imposed, assessed or charged on or in respect of the Shopping Centre, or on the Landlord on account of same, capital taxes relating to the Shopping Centre, including capital taxes imposed on the Landlord in respect of the Shopping Centre or the capital of the Landlord relating to the Shopping Centre, including Corporation Capital Tax and all taxes in the future levied in lieu of or in replacement of the foregoing, but excluding any tax attracted by the Tenant's leasehold improvements and equipment and otherwise payable by the Tenant under this Lease and any taxes assessed on the income or profits of the Landlord;

    "Tenant's Taxes" means all GST, sales taxes, business transfer taxes and other taxes (except "Taxes" as defined above), rates and assessments levied against the Landlord, the Tenant, the Property, the Shopping Centre or the Premises in respect of or as a result of this Lease, the Basic Rent or Additional Rent, the provision of any goods, services, or utilities by the Landlord to the Tenant and/or in respect of any chattels, machinery, equipment, improvements or Tenant's fixtures erected or affixed to the Premises, by or on behalf of the Tenant, including all such taxes in the future levied in lieu of or in replacement of the foregoing;

    "Tenant’s Work" means that work described on the Schedule forming part of the Offer to Lease, titled Tenant’s Work and referred to in Schedule B hereto as Tenant's Work. Unless there are additional terms added to Schedule B hereto, the Tenant's Work set out in the Offer to Lease shall govern;

    "Term" means the Initial Term and any extensions or renewals exercised by the Tenant pursuant to section 1.01(f).

    INITIAL

    Landlord Tenant

    MR – July 2020






    # 1.03 Schedules.

    The following Schedules form part of this Lease:

    - Schedule A - Plan of Premises
    - Schedule B – Miscellaneous Provisions
    - 1.00 Renewal Option(s)
    - 2.00 Tenant's Work
    - 2.01 Fixturing Period
    - 2.02 Tenant Improvement Allowance
    - 3.00 Landlord’s Work
    - 4.00 Exclusivity Claims
    - 4.01 Prohibited Uses
    - 5.00 Radius Restriction
    - 6.00 Exclusive Use
    - 7.00 Grand Opening and Promotion Fund
    - 8.00 Pylon Signage
    - Schedule C – Percentage Rent
    - Schedule D – Indemnity Agreement

    # ARTICLE 2

    # DEMISE AND TERM

    # 2.01 Demise.

    In consideration of the rents, covenants, conditions and agreements on the part of the Tenant to be paid, observed and performed, the Landlord demises and leases to the Tenant and the Tenant takes and rents on the terms of this Lease, the Premises. The Premises include all areas and improvements within the building shell which shall extend vertically from floor level to the underside of the main roof deck. In addition, the Tenant shall be entitled for the benefit of the Premises to enjoy, upon the terms and conditions set out in this Lease, the non-exclusive use in common with all others entitled thereto, of the Common Areas. The Landlord may make minor variations in the form or siting of the Premises and such minor variations shall not render this Lease void or voidable, anything herein contained and any rule of law or equity to the contrary notwithstanding.

    The Landlord grants to the Tenant an easement over the Easement Area, if any.

    The Landlord is the registered owner of the Shopping Centre and holds the Shopping Centre as bare trustee and agent for the beneficial owner thereof, being Maple Ridge Developments Limited Partnership, who has authorised the Landlord to enter into this Lease. The Tenant acknowledges and recognises that the Landlord has full authority and power to enter into this Lease and enjoy the benefit of and create the obligations of the Landlord hereunder as agent and trustee for the beneficial owner. The Landlord together with the beneficial owner will be considered the Landlord for the purposes of this Lease.

    # 2.02 Survey of Rentable Area.

    The Landlord shall have the right to conduct a legal survey of the Premises and the Buildings from time to time to determine and adjust the Rentable Area of the Premises.

    INITIAL

    Landlord   Tenant

    MR – July 2020







    # 2.03 Term.

    To have and to hold the Premises unto the Tenant for the Term commencing on the Commencement Date, subject to the payment of Basic Rent and Additional Rent as herein defined and the fulfilment by the Tenant of its obligations under this Lease, unless earlier terminated as set out in this Lease.

    # 2.04 Acceptance of Premises.

    The opening by the Tenant of its business in the Premises shall constitute an acknowledgement by the Tenant that the Premises are in the condition called for by this Lease, that the Landlord has performed all of the Landlord’s Work with respect thereto and that the Tenant does not reserve or assert any rights for claims, offsets or back charges. The Tenant acknowledges that the Premises are leased to the Tenant on an "as is" basis, and there are no representations or warranties by the Landlord as to the Premises except as otherwise set out herein.

    # 2.05 Use of Common Areas.

    The use and occupation by the Tenant of the Premises includes the non-exclusive and non-transferrable right or license to use the Common Areas in common with others entitled thereto, and for the purposes for which they are intended and during such hours as the Shopping Centre may be open for business, as determined by the Landlord from time to time, subject in each case to this Lease and to any Rules and Regulations. Any rights of the Tenant to use the Common Areas shall contractually terminate on the expiration of the Term or earlier termination of this Lease.

    # 2.06 Relocation.

    The Landlord shall have the right, at any time during the Term of this Lease, after giving notice to the Tenant (“Relocation Notice”), to relocate the Tenant to other premises in the Shopping Centre (the "Relocated Premises") provided the Landlord will ensure the Tenant will have at least sixty (60) days before having to relocate, as is set out in subsection (c), and if the Landlord gives Relocation Notice the following terms and conditions shall apply:

    - (a) the Relocated Premises shall contain approximately the same Rentable Area as the Premises and similar exposure so as not to unreasonably detrimentally affect the Tenant's business;
    - (b) the Landlord shall provide at its expense leasehold improvements in the Relocated Premises at least equal to those contained in the Premises at the time of relocation.

    INITIAL

    Landlord Tenant

    MR – July 2020






    # 10

    In addition, the Landlord shall be responsible for the reasonable costs of moving the Tenant’s trade fixtures, goods, chattels, furniture and furnishings from the Premises to the Relocated Premises, but such cost shall include only the cost of the physical movement of such things and the Landlord shall not be responsible for any other costs incurred by the Tenant in respect of the Relocated Premises, nor shall the Landlord be liable for any direct or indirect costs, business interruption, consequential losses or damages, or any other costs, losses or damages occasioned by the interruption of the Tenant’s business;

    (c) after the Landlord has determined when leasehold improvements to the Relocated Premises will be completed, the Landlord shall give a second notice of at least fifteen (15) days to the Tenant (“Date of Relocation Notice”) setting out the date upon which the Tenant must relocate to the Relocated Premises (the “Relocation Date”). The Relocation Date must be at least sixty (60) days after the date the Landlord gave to the Tenant the original Relocation Notice. The Tenant shall vacate the Premises and relocate to the Relocated Premises effective as of the Relocation Date and the Relocated Premises shall be deemed to be the Premises and all other terms and conditions of this Lease shall apply to the Relocated Premises as of and effective the Relocation Date, except for terms and conditions that are inconsistent with the terms and conditions of this Lease and provided that Basic Rent and the Tenant’s Proportionate Share shall be adjusted accordingly, and the Tenant shall execute such documents as the Landlord may require to confirm the foregoing;

    (d) the Landlord warrants that any relocation will not result in any downtime of the Tenant’s business for greater than seven (7) days. In the event that any relocation results in downtime of the Tenant’s business for greater than seven (7) days through no fault of the Tenant (a “Relocation Delay”), the Landlord hereby agrees to indemnify the Tenant for any reasonable loss of income during such Relocation Delay and, further, Rent will be abated during the Relocation Delay provided that, in all instances and to the extent reasonably possible, the Tenant will act to assist the Landlord to mitigate any such Relocation Delay;

    (e) if the Tenant refuses to allow the Landlord to relocate the Tenant as set out above or refuses to relocate to the Relocated Premises on or before the Relocation Date, or if the Tenant attempts to obstruct such relocation in any manner, the Landlord may, at its option, terminate this Lease upon fifteen (15) days’ notice to the Tenant, without prejudice to any other rights or remedies the Landlord may have, and in such event Rent and any other payments for which the Tenant is liable shall be apportioned and paid to the date of such termination of this Lease, and the Tenant shall deliver possession of the Premises to the Landlord upon the date of termination as set out in the Landlord’s notice; and

    (f) notwithstanding the foregoing or anything to the contrary, the Landlord shall not be allowed to exercise its rights under this paragraph 2.06 at any time during the first ten (10) years of the Initial Term.

    INITIAL
    Landlord  Tenant

    MR – July 2020






    # ARTICLE 3

    # RENT, ADDITIONAL RENT AND DEPOSIT

    # 3.01 Rent.

    (a) The Tenant shall pay to the Landlord, or as the Landlord may direct, Rent for the Premises, including Tenant’s Taxes payable in respect thereof, during the Term in lawful Canadian money, without any set off, compensation, abatement or deduction whatsoever paid in advance on the first day of each and every calendar month commencing on the Commencement Date as follows:

    - (i) Basic Rent in the amount set out in section 1.01(g);
    - (ii) Additional Rent payable in the manner set out below; and, if applicable
    - (iii) Percentage Rent.

    (b) In addition to the Basic Rent and the Percentage Rent, if applicable, payable hereunder, the Tenant shall pay as Additional Rent to the Landlord or such other person as the same may be payable to, in the manner set out above, or in the manner and at the times more particularly set out hereinafter in this Lease, all other amounts payable hereunder, and, without limitation, the Tenant shall pay to the Landlord the following:

    - (i) the Tenant’s Proportionate Share of Operating Costs;
    - (ii) the Tenant’s Proportionate Share of Taxes;
    - (iii) the cost of utilities set out herein;
    - (iv) an amount equal to any increase in the business taxes, insurance costs or Taxes payable by reason of any installation, fixturing, improvement or alteration made in, upon or to the Premises or by reason of any act, omission or default of the Tenant;
    - (v) an amount equal to any increase in any Operating Costs directly attributable to any installation in or upon the Premises or to the business operations conducted by the Tenant;
    - (vi) the charges established by the Landlord from time to time for all supplementary services and utilities provided by the Landlord to the Tenant which may include, without limitation, security, maintenance, repair, janitorial, cleaning and other services provided outside normal business hours and/or in manner not considered by the Landlord as standard;
    - (vii) an amount equal to all professional fees incurred by the Landlord in the enforcement of the Tenant’s covenants under this Lease and in respect of the recovery of any insurance claims on behalf of the Tenant and all costs incurred or sums paid by the Landlord or any other tenant by reason of any breach of the Tenant’s covenants to be performed and observed by the Tenant under this Lease; and

    INITIAL

    Landlord Tenant

    MR – July 2020






    # 3.02 Payment.

    The Tenant shall make all payments required to be made by it under this Lease to the Landlord at its address set out on page one, or at any other address the Landlord from time to time designates by notice to the Tenant.

    # 3.03 Adjustments.

    (a) All Rent reserved herein shall be deemed to accrue from day to day, and if for any reason it shall become necessary to calculate Rent for irregular periods of less than one (1) month an appropriate pro-rata adjustment shall be made on a daily basis, or such other reasonable basis as determined by the Landlord, in order to compute Rent for such irregular period.

    (b) The Basic Rent is based on an estimate of the Rentable Area of the Premises set out in section 1.01(b) subject to any adjustments pursuant to the terms of section 2.02.

    # 3.04 Deposit.

    (a) The Landlord acknowledges receipt of the Deposit from the Tenant as a deposit to be held by the Landlord, without liability for the payment of interest thereon, to be applied as follows:

    - (i) firstly, as a security deposit equal to one month's Basic Rent and Additional Rent, to be held by the Landlord until the expiry or any earlier termination of this Lease; and
    - (ii) secondly, the balance, to be applied to the first month's Basic Rent and Additional Rent due and payable under the terms of this Lease.

    (b) If at any time Rent or any sum payable by the Tenant is overdue and unpaid or the Tenant fails to observe and perform any of the terms or conditions in this Lease to be observed and performed by the Tenant, the Landlord may, either before or after terminating this Lease, appropriate and apply the whole or any part of the Deposit to the payment of such Rent or other sum of money or to compensate the Landlord for any loss, cost, damage, or expense sustained or suffered by the Landlord by reason of the failure of the Tenant to observe and perform any of the terms or conditions in this Lease to be observed or performed by the Tenant, and such appropriation and application will be without prejudice to the Landlord's right to pursue any other remedy set forth in this Lease.

    INITIAL Landlord Tenant

    MR – July 2020






    (c) If the whole or any part of the Deposit is appropriated and applied by the Landlord under section 3.04(b), the Tenant will, upon demand from the Landlord, immediately pay to the Landlord a sufficient amount to restore the Deposit to the amount specified in section 3.04(a) and the Tenant's failure to do so within ten (10) days after receipt of such demand will constitute a breach of this Lease.

    (d) The Landlord may deliver and assign the Deposit to any purchaser of the Landlord's interest in the Premises and thereupon the Landlord will be discharged from any further liability with respect to such Deposit.

    # 3.05 Additional Rent.

    All money payable by the Tenant under this Lease and money paid or expenses incurred hereunder by the Landlord, which ought to have been paid or incurred by the Tenant to any party including without limitation Tenant’s Taxes, or for which the Landlord is entitled to reimbursement from the Tenant, excluding Basic Rent and Percentage Rent:

    (a) will unless otherwise stipulated herein, be payable by the Tenant to the Landlord as Additional Rent in accordance with applicable legislation or otherwise within seven (7) days after the Landlord has given the Tenant notice of same; and

    (b) may be recovered by the Landlord as Additional Rent and by any and all remedies available to the Landlord for the recovery of Rent in arrears.

    # 3.06 Payment of Rent.

    All payments by the Tenant to the Landlord required or contemplated by this Lease shall be:

    (a) to the Landlord by the Tenant in lawful currency of Canada;

    (b) made when due hereunder, without prior demand therefore and without any set-off, compensation or deduction whatsoever, at the office of the Landlord or such other place as the Landlord may designate from time to time to the Tenant;

    (c) applied towards amounts then outstanding hereunder, in such manner as the Landlord may see fit;

    (d) deemed to be Rent, in partial consideration for which this Lease has been entered into, and shall be payable and recoverable as Rent, such that the Landlord shall have all rights and remedies against the Tenant for default in any such payment which may not be expressly said to be Basic Rent or Additional Rent or Percentage Rent, if applicable;

    (e) subject to a $100.00 overdue charge if any such payment of Rent is not made when due, which charge shall be Additional Rent payable with the next monthly instalment of Basic Rent, all without prejudice to any other right or remedy of the Landlord; and

    (f) made by way of automatic debit of the Tenant's bank account or a series of cheques, post-dated to the respective due dates of such payments, which the Tenant shall supply to the Landlord at the commencement of each lease year or

    INITIAL Landlord Tenant

    MR – July 2020






    # Lease Agreement

    earlier should the Landlord so request, without prejudice to any other right or remedy of the Landlord.

    The Tenant’s obligation to pay all monies pursuant to this Lease shall survive the expiry or earlier termination of this Lease where amounts owing have not been calculated prior to the expiry or termination of this Lease.

    # 3.07 Gross Revenues Statements

    (a) If the Tenant is required to pay Percentage Rent under this Lease, the provisions of the Schedule setting out the payment of Percentage Rent and reporting of Gross Revenues shall supersede this section.

    (b) If the Tenant is not required to pay Percentage Rent under this Lease, the Tenant shall:

    - (i) By the fifteenth (15) day of every calendar month and until the month after the end of the Term, submit to the Landlord a written statement certified correct by an officer of the Tenant, showing in reasonable detail the Gross Revenues during the immediately preceding month.
    - (ii) Within sixty (60) days after the end of each year or other period designated by the Landlord and after the end of the Term, submit to the Landlord a written statement certified by its certified professional accountant, or similarly qualified accountant reasonably satisfactory to the Landlord, setting out in reasonable detail the amount of the Tenant’s Gross Revenues for each month during the immediately preceding year or other period.

    (c) The Tenant shall keep detailed and accurate accounts, records, books, reporting records and dates with respect to its Gross Revenues, the daily business done and the orders received in or from the Premises in accordance with this section and shall cause any sub-lessee, licensee, franchisee or concessionaire to do so. The Tenant must keep those records for at least three years from the end of each calendar year. The Tenant will comply with all reasonable directions issued to it by the Landlord respecting accounting records and procedures to be adopted for proper recording and control of transactions affecting Gross Revenues, including, without limitation, the mandatory use of a cash register which tabulates the daily sales constituting Gross Revenues. By accepting any statement of Gross Revenues, the Landlord will not have waived any of its rights under this Lease.

    (d) The Landlord and its accountants and agents shall have the right at all reasonable times to examine all accounts, records, books, cash register tapes, computer records, sales tickets, sales reports, contracts and other data concerning the Gross Revenues, including all credits and other things relating to Gross Revenues.

    INITIAL Landlord Tenant

    MR – July 2020






    # ARTICLE 4

    # OPERATING COSTS

    # 4.01 Proportionate Share.

    The Tenant shall pay to the Landlord its Proportionate Share of Operating Costs as follows:

    1. The Landlord shall estimate the Operating Costs for each year of the Term or its fiscal period, as the Landlord elects, and provide notice to the Tenant of the Tenant’s Proportionate Share of such Operating Costs. The Tenant shall pay 1/12th of the Landlord's estimate of the Tenant's Proportionate Share of the Operating Costs with each monthly instalment of Basic Rent payable throughout that period, which will be adjusted if the Landlord subsequently re-estimates the Operating Costs for such period or the remaining portion;
    2. The Landlord shall advise the Tenant of the actual amount of Operating Costs for such period and the Tenant's Proportionate Share after the expiry of such period in reasonable detail, which will be binding on the parties. Within thirty (30) days after receipt of that advice from the Landlord, the Tenant shall pay to the Landlord any underpayment by the Tenant of its Proportionate Share of Operating Costs for the period or the Landlord shall credit the Tenant in respect of any overpayment;
    3. If the Landlord is required to prepay any Operating Costs or pay any Operating Costs more frequently than required at the beginning of each year of the Term or its fiscal period, the Tenant shall pay to the Landlord its Proportionate Share of those Operating Costs, forthwith upon the request of the Landlord, to allow the Landlord to pay those Operating Costs in a timely manner.

    # 4.02 Allocation.

    1. Notwithstanding the foregoing, whenever in the Landlord’s reasonable opinion, an Operating Cost properly relates to the Tenant or a group of tenants in the Shopping Centre, the Landlord may allocate such Operating Cost to such Tenant or group of tenants. Any amount so allocated to the Tenant shall be paid by the Tenant as Additional Rent.
    2. If any facilities, services, systems or utilities:

    for the operation, maintenance, administration, management, repair, or replacement of the Shopping Centre are provided from another building or buildings owned or operated by the Landlord or its agent; or
    3. for the operation, maintenance, administration, management, repair or replacement of another building or buildings owned or operated by the Landlord or its agent are provided from the Shopping Centre,

    the costs, charges and expenses therefore shall for the purpose of calculation of Operating Costs be allocated by the Landlord between the Shopping Centre and the other building or buildings on a reasonable basis.

    INITIAL

    Landlord  Tenant

    MR – July 2020







    (c) In computing Operating Costs for any fiscal period, if less than 100% of the Rentable Area of the Shopping Centre is occupied by tenants during that period, the amount of Operating Costs will be deemed to be increased to an amount equal to the like Operating Costs which normally would be expected by the Landlord to have been incurred had such occupancy been 100% of the Rentable Area of the Shopping Centre during that period.

    # 4.03 Re-Allocation of Operating Costs and Taxes.

    Notwithstanding anything to the contrary herein contained, the Landlord shall have the right to re-allocate expenses and taxes relating to the various tenants and components of the Shopping Centre on a reasonable basis, having regard to the business operations of such tenant and the Shopping Centre as a whole, and in such case the amount of Operating Costs and the amount of Taxes shall be deemed to be the amounts so allocated by the Landlord.

    # 4.04 Net Lease.

    It is the intention of both the Landlord and the Tenant that this Lease is a completely carefree net lease to the Landlord, except as expressly herein set out; that all costs, fees, interest, charges and expenses, reimbursements and obligations of every nature and kind whatsoever relating to the Premises (including the payment of a Proportionate Share of Operating Costs) which may arise or become due during or out of the Term, whether or not specifically referred to herein and whether or not of a kind now existing or within the contemplation of the parties, and whether or not originally paid or payable by the Landlord (except such as are expressly excluded herein) shall be paid or discharged by the Tenant or reimbursed by the Tenant to the Landlord and recoverable by the Landlord from the Tenant as Additional Rent and the Tenant hereby agrees to indemnify and save the Landlord harmless from and against all costs and fees and interest thereon. Except as expressly and directly set forth herein, the Landlord shall have no obligations or liabilities in respect to the Shopping Centre or the Tenant whatsoever. The Tenant shall pay the Landlord its Proportionate Share of all other expenses as aforesaid, utilities and levies within seven (7) days after the Landlord has given the Tenant notice as to the amount of such costs, as Additional Rent. The certificate of an accountant appointed by the Landlord shall in the event of a dispute, be conclusive and binding upon the Landlord and the Tenant as to any amount payable by the Tenant to the Landlord pursuant to this clause.

    # ARTICLE 5

    # TAXES

    # 5.01 Payment of Taxes.

    (a) The Tenant shall pay to the Landlord within ten (10) days after demand by the Landlord the Tenant's Proportionate Share of all Taxes, proportioned for any partial calendar year in which the Tenant is in possession of the Premises, and such demand will be accompanied by a copy of the tax bill or notice from the applicable government or notice of the actual Taxes.

    (b) At the election of the Landlord by notice to the Tenant, the Landlord will be entitled to estimate the Tenant's Proportionate Share of Taxes for the current and/or






    # 5.01 Taxes.

    Following years and collect advance payments on account of Taxes from the Tenant. In such case, the Tenant shall pay to the Landlord in equal monthly instalments with the Basic Rent, an amount designated by the Landlord so that the Tenant's Proportionate Share of Taxes will have been paid to the Landlord at least twenty-one (21) days before the Taxes fall due.

    (c) After the actual Taxes for each calendar year are determined, the Landlord may at its election change any of such monthly payments to collect sufficient money from the Tenant to allow the Landlord to pay the Tenant's Proportionate Share of the Taxes at least twenty-one (21) days before Taxes are due and payable.

    (d) If the Landlord does not require the Tenant to make monthly payments on account of Taxes and the Term ends when the actual Taxes for that calendar year are unknown the Tenant shall pay to the Landlord within ten (10) days after request from the Landlord the Proportionate Share of the Taxes for the portion of the calendar year before the end of the Term, based on the Landlord's estimate of the Taxes. At the election of either party, an adjustment will be made between the Landlord and the Tenant, when the actual Taxes are known.

    (e) The Landlord, acting reasonably, may elect to allocate to the Tenant, based on a reasonable and equitable allocation made by the Landlord in its sole discretion, any amount of Taxes or increase in Taxes. The Landlord may allocate and attribute Taxes to and amongst the various components of the Shopping Centre on an equitable basis (having regard to, among other things, the various uses of the components, the costs of construction of same, the relationship of the location and area of each of the components and their relative values and any other factors utilized in current assessment practices) and the Tenant shall pay its Proportionate Share of all Taxes so allocated by the Landlord to that portion of the Shopping Centre. For greater certainty, there will be a credit against Taxes equal to the amount of any payments on account of Taxes made by tenants who do not pay for Taxes on a Proportionate Share basis.

    # 5.02 Tenant’s Taxes.

    The Tenant shall pay all Tenant’s Taxes when due if applicable, provided the Tenant shall pay to the Landlord all Tenant’s Taxes if required by the Landlord given the nature of any form of Tenant’s Taxes, within seven (7) days after demand by the Landlord. If the Term of this Lease ends when the actual amount of the Tenant’s Taxes for that year is unknown, the Tenant shall, on or before the end of the Term, pay to the Landlord the Landlord's estimate of Tenant’s Taxes for that year. A further adjustment, if necessary, will be made between the Landlord and the Tenant when the actual amount of the Tenant’s Taxes is known.

    # 5.03 Right of Appeal.

    The Tenant shall have the right at its own expense in the name of the Landlord to appeal any assessment, Taxes or Tenant’s Taxes imposed in respect of the Premises provided the interest of the Landlord is not prejudiced and provided the Tenant posts such security as is required by the Landlord, but the Tenant shall indemnify the Landlord against all costs and charges arising from such appeals including all resulting increases in assessments, Taxes or Tenant’s Taxes.

    INITIAL Landlord Tenant

    MR – July 2020







    # 5.04 Business Tax, etc.

    The Tenant shall pay when due all business taxes and other taxes, charges, levies, licenses and expenses levied on the Tenant or Landlord in respect of the Tenant's business, use or occupancy of the Premises including interest and penalties for late payment.

    # 5.05 Evidence of Payments.

    The Tenant shall deliver to the Landlord from time to time satisfactory evidence of the due payment by the Tenant of all payments required by the Tenant under this Lease within seven (7) days after request by the Landlord.

    # ARTICLE 6 CONTROL OF SHOPPING CENTRE AND COMMON AREAS

    # 6.01 Landlord’s Additions.

    The Landlord may, but shall not be obligated to make additions, improvements, installations and repairs to the Shopping Centre other than the Premises. In that regard the Landlord may cause obstructions of and interference with the use or enjoyment of the Premises, as are reasonably necessary and may interrupt or suspend the supply of electricity, water or other services when necessary and there will be no abatement in Rent, nor shall the Landlord be liable as a result.

    # 6.02 Supply of Services.

    The Landlord and all persons authorized by the Landlord may, but shall not be obligated to use, install, maintain or repair pipes, wires, ducts or other installations in, under or through the Premises for or in connection with the supply of any services deemed advisable by the Landlord or for any other purposes reasonably required by the Landlord in relation to the Premises or any other premises or Common Areas in the Shopping Centre provided this right of the Landlord shall not be deemed to limit the Landlord’s Work. Those services may include, without limitation gas, electricity, water, sanitation, HVAC, and fire protection.

    # 6.03 Required Alterations.

    The Landlord and all persons authorized by the Landlord may, but shall not be obligated to, enter the Premises and make all decorations, repairs, alterations, improvements or additions the Landlord considers advisable or as required to comply with governmental requirements and regulations provided this right of the Landlord shall not be deemed to limit the Landlord’s Work. The Landlord and all persons authorized by the Landlord are allowed to take all necessary material into the Premises and the Rent hereunder will not abate during any such work.

    # 6.04 Landlord's Right to Exhibit Premises and Place Signs.

    The Landlord shall have the right throughout the Term, to show the Premises to prospective purchasers during normal business hours and to prospective tenants during normal business hours of the last six (6) months of the Term and the Landlord shall have

    INITIAL Landlord Tenant

    MR – July 2020







    # 6.05 Landlord May Perform Tenant's Covenants, etc.

    If the Tenant fails to perform any of its obligations under this Lease, the Landlord may perform or cause the same to be performed and do all things necessary or incidental thereto, and without limitation the Landlord may make repairs, installations, erections and spend monies. All payments, expenses, charges, fees and disbursements incurred or paid by or on behalf of the Landlord in respect thereof will be immediately payable by the Tenant to the Landlord.

    # 6.06 Tenant's Use of Parking Areas.

    The Tenant, its employees, suppliers and other persons who are not customers having business with the Tenant will be prohibited from using for vehicle parking, loading or unloading any part of the customer parking area designated and altered from time to time by the Landlord. Tenant and employee parking shall be limited to times and places specified by the Landlord so as to cause minimal interference with businesses within the Shopping Centre. Parking will be regulated by the Landlord in a reasonable manner, and the Tenant and its employees, suppliers and other persons who are not customers shall obey such regulations from time to time established by the Landlord. If requested by the Landlord, the Tenant shall supply its employees' license numbers.

    The Landlord shall not be liable to the Tenant, its employees, suppliers and other persons having business with the Tenant for loss or damage to any motor vehicle or its contents or for the unauthorized use by other tenants or parties of parking spaces allotted to the Tenant, but the rights of the Tenant, its employees, suppliers and others having business with the Tenant shall be against the person or persons causing such damage or occupying such parking space(s).

    Any rights of the Tenant and its employees, suppliers and others having business with the Tenant to parking shall contractually terminate on the expiration of the Term or earlier termination of this Lease.

    # 6.07 Landlord's Right to Remove Vehicles.

    If the Tenant, its employees, suppliers and other persons who are not customers having business with the Tenant park vehicles in areas not allocated for that purpose, the Landlord shall have the right to remove such vehicles and the Tenant will save harmless the Landlord from all resulting damages and pay the costs of such removal.

    # 6.08 Control of Common Areas.

    (a) The Landlord shall have the right to control the Common Areas.

    (b) The Landlord shall operate and maintain the Shopping Centre in such manner as the Landlord determines from time to time, as would a prudent landlord of a similar.






    # 6.08 Control and Management of the Shopping Centre

    Commercial development having regard to size, age and location, subject, however, to normal wear and tear and to damage other than damage as insured pursuant to this Lease.

    (c) The Shopping Centre is at all times subject to the exclusive control and management of the Landlord. Without limiting the generality of the foregoing, the Landlord has the right, in its control, management and operation of the Shopping Centre and by the establishment of Rules and Regulations and general policies with respect to the operation of the Shopping Centre or any part thereof at all times during the Fixturing Period and throughout the Term, to:

    - (i) provide electric power to the Premises in accordance with the Landlord’s criteria for the Shopping Centre;
    - (ii) construct other buildings, structures or improvements in the Shopping Centre and make alterations and additions thereof, subtractions therefrom, or rearrangements thereof, build additional storeys on any improvements and construct additional buildings or facilities adjoining or proximate to the Shopping Centre;
    - (iii) relocate or rearrange the various components of the Shopping Centre from those existing at the Commencement Date. The Tenant hereby acknowledges that the purpose of Schedule A is solely to show the approximate location of the Premises and any other relevant areas; and
    - (iv) do and perform such other acts in and to the Shopping Centre as, in the use of good business judgment, the Landlord determines to be advisable for the more efficient and proper operation of the Shopping Centre.

    (d) Notwithstanding anything contained in this Lease, it is understood and agreed that if as a result of the exercise by the Landlord of its rights set out in this section 6.08, the Common Areas are varied or diminished in any manner whatsoever, the Landlord is not subject to any liability nor is the Tenant entitled to any compensation of diminution or abatement of Rent, nor is any alteration or diminution of the Common Areas deemed constructive or actual eviction, or a breach of any covenant for quiet enjoyment contained in this Lease and the Tenant will, at the request and cost of the Landlord, execute such documents as are reasonably required by the Landlord to release any interest the Tenant may have in those parts of the Common Areas designated by the Landlord.

    # 6.09 Merchandise on Common Areas

    Without limiting section 6.08, the Tenant shall not keep, display or sell any merchandise on or otherwise obstruct or use any part of the Common Areas, except as permitted by the Landlord and for displays included in Shopping Centre promotions permitted by the Landlord.

    # 6.10 Alterations and Additions to the Shopping Centre

    (a) The Tenant covenants that nothing contained in this Lease shall be construed so as to prevent the Landlord from varying, altering, relocating or rearranging the

    INITIAL

    Landlord Tenant

    MR – July 2020






    # 6.10 Common Areas.

    The Landlord shall have the unrestricted right to make alterations to the location or size of parking areas, driveways, sidewalks and Buildings or adding areas to or removing areas from the Shopping Centre from time to time or from erecting additional Buildings or extending Buildings and without limiting the foregoing, the Landlord shall have the unrestricted right to construct additional Buildings from time to time on the Common Areas, add or change any Building, or may alter the ingress or egress to the Common Areas, change the loading or unloading facilities and service entrances from time to time without in any way being responsible to the Tenant, provided only that the Landlord shall at all times provide reasonable access to the Premises across the Common Areas for the Tenant, its employees, licensees, invitees, customers and agents.

    (b) Subject to the foregoing and to the obligation of the Landlord to maintain parking facilities at all times on the Common Areas, the Landlord may transfer or dispose of portions of the Common Areas to the owners of abutting property, or dedicate or transfer to municipal authorities, lands for road widening and other purposes, and when and so often as the Landlord shall dispose or transfer or dedicate any portion of the Common Areas, then the reference herein to "Common Areas" shall mean and refer to the portion of the Common Areas remaining after any such transfer, disposition or dedication and shall include any adjacent land which may be acquired by the Landlord.

    (c) If the Landlord should elect to make alterations or additions to the Shopping Centre and in the Landlord's opinion in making such alterations or additions, it is necessary to relocate the Premises then the provisions of section 2.06 shall apply.

    # 6.11 Display Windows.

    The Tenant shall keep the display windows of the Premises suitably illuminated during the business hours of the Shopping Centre. The windows must maintain clear visibility into the Premises. The Tenant must maintain the professional image of the Shopping Centre.

    # 6.12 Common Areas.

    The Tenant shall not do anything which may injure the Common Areas or be a nuisance to any other tenants or premises in the Shopping Centre.

    # 6.13 Management of Shopping Centre.

    The Landlord may appoint a manager of the Shopping Centre and give notice to the Tenant of such appointment, and after giving such notice that manager will be authorized to deal with the Tenant and all administrative matters relating to the Shopping Centre and this Lease shall be referred by the Tenant to such manager.

    # 6.14 Access.

    No admittance is permitted to the roof or maintenance, electrical, mechanical or similar rooms containing property of the Landlord or Common Facilities by anyone other than personnel authorized by the Landlord. The Landlord, without limiting any other rights hereunder of the Landlord may on reasonable notice, and without notice in the case of emergency, enter upon and through the Premises for access to the roof or other parts of the Building.

    INITIAL Landlord Tenant

    MR – July 2020






    # 6.15 Maintenance.

    The Landlord shall maintain the Shopping Centre as would a prudent landlord of a development similar in class and nature to the Shopping Centre.

    # ARTICLE 7 UTILITIES AND HEATING, VENTILATING AND AIR CONDITIONING

    # 7.01 Utilities.

    (a) The Tenant shall promptly pay all telephone, electric, oil, gas, water, sewage, and other utility charges consumed on the Premises. If there is not a separate meter for measuring any utility consumed on the Premises, the Tenant shall pay to the Landlord in advance by monthly instalments the amount estimated by the Landlord from time to time as the Tenant's share of such utilities.

    (b) If required by the Landlord, a separate check meter for utility services will be installed for the Premises at the Tenant’s expense in a location designated by the Landlord, and the Tenant’s share of that utility will be measured using the check meter.

    (c) The Tenant shall immediately advise the Landlord of any appliances or machines installed by the Tenant likely to consume large amounts of electricity or other utilities.

    (d) The Tenant shall at the request of the Landlord from time to time deliver to the Landlord a list of all appliances, equipment and machines used in the Premises.

    (e) If the Landlord pays any of the Tenant's utilities or any other services rendered to or for the benefit of the Tenant, the Tenant shall forthwith reimburse the Landlord.

    (f) The Tenant will not install any equipment which will exceed or overload the capacity of utility facilities and agrees that if the equipment installed by the Tenant requires additional facilities they will be installed at the Tenant's expense in accordance with plans and specifications approved by the Landlord prior to installation.

    (g) The Tenant shall be responsible for arranging and paying for the collection, storage, disposal, and/or recycling of all food products, cooking oils, fats and/or grease generated from the Tenant’s business in the Premises and in such a manner as to minimize associated odor and nuisance.

    # 7.02 Light Fixtures and Ceilings.

    The Tenant shall maintain and replace from time to time at its cost as is reasonably necessary all light fixtures, tubes, ballasts, starters, ceiling tiles and t-bar or any other type of ceiling material that might exist from time to time in the Premises.

    INITIAL Landlord Tenant

    MR – July 2020






    # 7.03 Damaging Equipment.

    The Tenant shall not use the Premises in any way that would impair the efficient and proper operation of any electrical, life safety, plumbing, HVAC or sprinkler system or other equipment located within and serving the Premises.

    # 7.04 Heating, Ventilating and Air Conditioning.

    The Tenant shall, throughout the Term, operate and regulate those portions of the HVAC equipment within and serving the Premises in such a manner as to maintain such reasonable conditions of temperature and humidity within the Premises as are determined by the Landlord and its architect or engineer so that no direct or indirect appropriation of the HVAC from the Common Areas and Common Facilities occurs. The Tenant shall comply with such stipulations and with any Rules and Regulations of the Landlord pertaining to the operation and regulation of such equipment. If the Tenant fails to comply with such stipulations and Rules and Regulations, the Landlord shall be entitled to take such steps as it deems advisable to correct such defaults (including, without limitation, entering upon the Premises and assuming control of such equipment) without liability to the Tenant, and the Tenant will pay to the Landlord forthwith upon demand as Additional Rent all costs and expenses incurred by the Landlord in so doing. For greater certainty the Tenant shall install and maintain at its sole cost an air filtration and ecologizer system reasonably satisfactory to the Landlord so as to minimize odor and emissions from the Premises.

    # ARTICLE 8 USE OF PREMISES

    # 8.01 Use of Premises.

    The Tenant shall not use the Premises nor allow them to be used for any purpose other than for the purposes set out in ARTICLE 1 unless the written consent of the Landlord is previously obtained. It is the Tenant's sole responsibility to ensure that the Premises can be used for those purposes and to obtain any necessary permits, licences and government approvals at the Tenant's cost. In connection with the business to be conducted by the Tenant on the Premises, the Tenant shall only use the trade name specified in ARTICLE 1 and will not change the trade name of the business to be operated in the Premises without the prior written consent of the Landlord.

    # 8.02 No Nuisance, etc.

    The Tenant shall not permit to be carried on in the Premises any noisy, illegal, noxious, immoral or offensive trade, business, or activity nor commit waste upon the Premises. The Tenant shall not permit anything to be done in or about the Premises which may cause or permit annoying noises or vibrations or offensive odours to issue from the Premises or which may cause nuisance, annoyance, damage or disturbance to the Landlord or the occupants or owners of the Shopping Centre or other premises in the vicinity of the Shopping Centre. The Tenant shall not place in the Premises any heavy machinery or equipment without obtaining the prior written consent of the Landlord.

    INITIAL Landlord Tenant

    MR – July 2020






    # 8.03 Injurious Activity.

    The Tenant shall not carry on or permit to be carried on the Premises, any activity deemed by the Landlord acting reasonably to be injurious to the Shopping Centre.

    # 8.04 Comply with Laws, etc.

    The Tenant shall at its expense promptly comply with all laws, ordinances, bylaws, codes, regulations, requirements and recommendations of all government and other authorities or associations of insurance underwriters or agents applicable to the Tenant, its business or use of the Premises, and all related notices served on the Landlord or the Tenant.

    # 8.05 Comply with Rules.

    The Landlord is hereby permitted to make and revise Rules and Regulations from time to time relating to the Shopping Centre, notice of which shall be given to the Tenant. All such Rules and Regulations will be part of this Lease as if contained herein.

    # 8.06 Environmental Laws.

    The Tenant covenants and agrees with the Landlord to:

    - (a) use the Premises only in compliance with all Environmental Laws;
    - (b) permit the Landlord to investigate the Premises, any goods on the Premises and the Tenant's records at any time and from time to time to verify such compliance with Environmental Laws and this Lease;
    - (c) at the reasonable request of the Landlord, obtain from time to time a report from an independent consultant designated or approved by the Landlord verifying compliance with Environmental Laws and this Lease or the extent of any non-compliance therewith;
    - (d) not store nor permit, manufacture, dispose, discharge, treat, generate, use, transport or release Hazardous Substances on or from the Premises or the Property without the Landlord’s prior written consent;
    - (e) promptly remove any Hazardous Substances from the Premises in a manner which complies with all Environmental Laws governing their removal;
    - (f) promptly remove any Hazardous Substances from the Property, if such Hazardous Substances were caused or created in any way by the Tenant or those for whom the Tenant is at law responsible for, in a manner which complies with all Environmental Laws governing their removal; and
    - (g) notify the Landlord in writing of:

    INITIAL Landlord Tenant

    MR – July 2020






    (ii) all claims, actions, orders or investigations threatened by any third party against the Tenant or the Premises or Shopping Centre relating to damage, contribution, cost recovery, compensation, loss or injuries resulting from or in any way related to any Hazardous Substances or any Environmental Laws; and

    (iii) the discovery of any Hazardous Substances, or any occurrence or condition on the Premises or in the vicinity of the Premises which could potentially subject the Tenant or Landlord or any other occupant of the Shopping Centre, or the Premises or Shopping Centre, to any fines, penalties, orders or proceedings under any Environmental Laws.

    If any Hazardous Substances are brought onto or created upon the Premises or the Property by the Tenant, or those for whom the Tenant is at law responsible, during the Term, such Hazardous Substances shall be the sole and exclusive property of the Tenant and not of the Landlord, notwithstanding the degree of affixation of the Hazardous Substances or the goods containing the Hazardous Substances to the Premises or the Property and notwithstanding the expiry or sooner termination of this Lease.

    The Landlord confirms and the Tenant acknowledges that the Landlord purchased the Property from previous owners who operated businesses which contributed to Hazardous Materials being placed on or under the Property. The Landlord undertook a risk assessment of the Property through qualified consultants and a Certificate of Compliance was subsequently issued for the Property by the Ministry of Environment and Climate Change Strategy permitting commercial land use on the Property.

    # 8.07 Environmental Indemnity.

    The Tenant shall indemnify and save harmless the Landlord and those for whom the Landlord is responsible from and against any and all claims, causes of action, liability, damages, costs and/or expenses (including Landlord's actual legal costs and disbursements on a solicitor and own client, full indemnity basis) for loss incurred by the Landlord relating to or arising from a breach by the Tenant of the covenant in section 8.06. The Tenant hereby expressly agrees that this indemnification will survive the expiration or the earlier termination of this Lease.

    # 8.08 Environmental Enquiries.

    The Tenant hereby authorizes the Landlord to make enquiries from time to time of any governmental authority and any supplier or other party dealing with the Tenant with respect to the compliance by the Tenant with Environmental Laws and the Tenant agrees that the Tenant will from time to time provide to the Landlord such written authorization as the Landlord may reasonably require in order to facilitate the obtaining of such information.

    # 8.09 Notice of Damage, Defects, etc.

    The Tenant shall promptly inform the Landlord by the most effective and immediate method and provide notice to the Landlord of any damage to or defect in the HVAC system, water pipes, plumbing system, gas pipes, telephone lines, electric light, life safety system, building envelope, storefront windows and doors, garbage and recycling area or other casualty in the Premises or the Shopping Centre.

    INITIAL

    Landlord Tenant

    MR – July 2020






    # 8.10 Prohibited Uses.

    The Tenant shall not conduct on the Premises an "auction sale", "distress sale", "bankruptcy sale", "going out of business sale" or any other sale which may convey to the public that business operations are to be discontinued, and shall only sell merchandise in the regular course of trade as a retail merchant for the purpose for which the Premises are leased. The Tenant shall not conduct or carry on any of the following businesses on the Premises:

    - (a) any manufacturing operation or any type of automotive centre or used car lot;
    - (b) a mail order business if it might materially reduce the pedestrian traffic in the Shopping Centre or detract from the successful operation of the Shopping Centre;
    - (c) an order office business;
    - (d) a store selling second hand goods, war surplus articles, insurance salvage stock, fire sale stock, or merchandise damaged by fire except if a fire occurs on the Premises and then only merchandise damaged by the fire;
    - (e) a store conducted, promoted or represented in whole or substantially as a discount operation or in part as a discount operation so as to give the impression that it is being conducted principally as a discount operation;
    - (f) an operation wherein the Tenant uses any fraudulent or deceptive advertising or selling procedures;
    - (g) outdoor selling;
    - (h) a pawn shop; or
    - (i) any other business which because of the merchandise likely to be sold or the merchandising or pricing methods likely to be used would, in the Landlord’s opinion, tend to lower the character of the Shopping Centre.

    The Landlord shall have the right to cause the Tenant to discontinue and the Tenant shall thereupon forthwith discontinue the sale of any item, merchandise, commodity, or the supply of any service, or the carrying on of any business, any of which is either prohibited by this section 8.10 or which the Landlord determines is not directly related to the permitted use set out in section 8.01 hereof.

    # 8.11 Obligation to Operate.

    The Tenant shall not vacate, abandon or cease to operate its business in the Premises either in whole or in part and shall:

    - (a) conduct its business in the entire Premises commencing no later than the Commencement Date;
    - (b) remain open for business for no less than customary business days and hours for such business in the metropolitan area where the Shopping Centre is located, unless prevented by any governmental authority;

    INITIAL
    Landlord  Tenant

    MR – July 2020







    # 8.12 Quiet Possession.

    Upon the Tenant paying the Rent and performing all its obligations under this Lease, the
    Tenant will be entitled to peaceably possess and enjoy the Premises for the Term without
    interruption or disturbance from the Landlord or any other persons lawfully claiming by,
    from or under the Landlord, except as specifically set out in this Lease.

    # 8.13 Energy Conservation.

    The Tenant shall:

    - (a) co-operate with the Landlord in the conservation of all forms of energy, recycling
    and similar environmental initiatives in the Shopping Centre including, without
    limitation, in the Premises;
    - (b) comply with all laws, by-laws, regulations and orders relating to the conservation
    of energy, recycling and any environmental initiatives affecting the Premises and
    the Shopping Centre or any part thereof; and
    - (c) at its own cost and expense comply with all reasonable requests and demands of
    the Landlord made with a view to such energy conservation, recycling and
    environmental initiatives.

    # ARTICLE 9 ASSIGNMENT AND SUBLETTING

    # 9.01 Assigning or Subletting.

    The Tenant shall not assign, sublet, transfer, mortgage or enter into or grant a license,
    concession, or right of occupancy nor permit any occupancy (a "Disposition") with respect
    to the Premises or any part without the prior written consent of the Landlord, which consent
    will not be unreasonably withheld. Without limiting the foregoing, the Landlord must be
    satisfied, in its sole discretion, as to the respectability, reputation and financial
    responsibility of the person or other entity (an "Assignee") to whom the Tenant wishes to
    make a Disposition and the Landlord must be satisfied, in its sole discretion, as to the
    Assignee’s proposed use of the Premises. The Landlord may, at the Landlord’s sole
    discretion, as a condition of consenting, require an Assignee to agree in writing with the
    Landlord to fulfil all the obligations of the Tenant under this Lease and require all directors,
    officers and shareholders of the Assignee to guarantee those obligations of the Assignee,
    on the terms prepared by the solicitors for the Landlord. The Tenant shall promptly deliver
    to the Landlord all information the Landlord reasonably requires in respect of the proposed
    Assignee including its name, address, the nature of its business, proof of its financial
    responsibility and reputation and a copy of the form of assignment or other Disposition
    document proposed to be used. If the Disposition is a sublease of the Premises, or a
    portion thereof, then the Landlord shall be entitled to receive any rent payable under the
    sublease which is in excess of the Basic Rent payable under this Lease.

    INITIAL Landlord Tenant

    MR – July 2020






    # 9.02 No Release.

    Any Disposition to which the Landlord has consented will not release the Tenant from any of its obligations under this Lease. The Landlord's acceptance of Rent from an Assignee who the Landlord has not consented to will not constitute a waiver of the requirement for consent, nor will the Landlord’s consent to any one Disposition be deemed to be consent to any further Disposition. No Disposition will be made to any Assignee proposing to carry on a business the Landlord is obligated to restrict because of any other lease or agreement.

    # 9.03 Change of Control.

    If the Tenant is a non-reporting body corporate, any direct or indirect change in the control or beneficial ownership of the Tenant to any person not presently a shareholder of the Tenant, by transfer or issuance of shares or otherwise, will be deemed an assignment of this Lease and subject to sections 9.01 and 9.02.

    # 9.04 Renewals.

    The Tenant shall not be released from any of its obligations under this Lease if an Assignee renews this Lease or any part of the Term as provided for in this Lease.

    # 9.05 Costs.

    The Tenant shall, together with its initial request to the Landlord for consent to any Disposition, pay to the Landlord its reasonable administration fee and the Tenant shall reimburse to the Landlord its actual legal costs and disbursements on a solicitor and own client, full indemnity basis and any other costs, charges and expenses which may be incurred by the Landlord in connection with the Tenant’s request for consent to any Disposition and subsequent assignment documents.

    # 9.06 Licenses, Concessions.

    The Tenant shall not grant any concessions, licenses or permits to sell or take orders for merchandise or services in the Premises without the prior written approval of the Landlord.

    # ARTICLE 10 INSURANCE AND INDEMNITY

    # 10.01 Tenant’s Insurance.

    The Tenant shall, at its sole cost and expense during the Term and during such other period of time that the Tenant occupies the Premises, take out and maintain in full force and effect, the following:

    - (a) glass insurance, with the Landlord as a loss payee, covering all glass and plate glass in or forming part of the Premises, including glass windows and doors, in an amount equal to its full insurable value;
    - (b) commercial general liability insurance, with the Landlord as an additional insured, in amounts (not less than $5,000,000.00 per occurrence) designated by the Landlord in respect of claims for injury, death or property damage, and which shall

    INITIAL

    Landlord  Tenant

    MR – July 2020






    # 10.01 Insurance Requirements

    The Tenant shall obtain and maintain, at its own expense, the following insurance:

    - (a) Commercial general liability insurance, including personal injury, products and completed operations, blanket contractual, non-owned automobile, and broad form property damage liability;
    - (b) "all risks" insurance, including earthquake and flood insurance, covering the leasehold improvements, fixtures, furniture, inventory, equipment and personal property of the Tenant to their full replacement cost value. Such insurance will include the Landlord as a loss payee as its interest may appear with respect to insured leasehold improvements. The Tenant shall make such proceeds available toward the repair or replacement of the insured property if this Lease is not terminated pursuant to any other provisions hereof;
    - (c) comprehensive boiler and machinery coverage, as required, on the equipment installed by the Tenant;
    - (d) tenant's "all risks" legal liability insurance in an amount not less than the replacement cost of the Premises;
    - (e) automobile liability insurance to a limit of liability of not less than $5,000,000 in any one accident, covering all licensed motor vehicles owned by the Tenant and used in connection with its business carried on from the Premises;
    - (f) business interruption insurance in an amount that will reimburse the Tenant for direct or indirect loss of gross profits attributable to all perils insured against under subsection 10.01(c) and (d), and other perils commonly insured against by prudent tenants, or attributable to prevention of access to the Premises as a result of those perils for a period of not less than six (6) months;
    - (g) such other insurance as the Landlord designates as a prudent landlord; and
    - (h) Tenant insurance shall, as required by the Landlord, name the Landlord, the Landlord’s mortgagee, property management company and any other persons, firms or corporations designated by the Landlord as additional insureds.

    # 10.02 Waiver of Subrogation

    All policies covering property damage written on behalf of the Tenant shall contain a waiver of any subrogation rights that the Tenant's insurer(s) may have against the Landlord and against those for whom the Landlord is, in law, responsible.

    # 10.03 Insurers

    The Tenant shall effect all insurance with insurers and brokers licensed to carry on business in British Columbia who are acceptable to the Landlord and on terms satisfactory to the Landlord acting reasonably. The Tenant's commercial general liability insurance will contain a cross liability and severability of interest clause in favour of the Landlord as if the Landlord and Tenant were separately insured. All insurance policies, except automobile liability, will contain a clause requiring the insurer not to cancel or alter without first giving the Landlord at least thirty (30) days’ written notice.






    # 10.04 Certificates.

    The Tenant shall supply the Landlord with a certificate of insurance signed by an authorized insurance agent or insurance company setting out in detail the particulars of its insurance coverage at the commencement of the Term and with respect to any new policies at least ten (10) days before the expiry of the existing policies. In the event of any loss or damage to the Shopping Centre, or if same is requested by the Landlord, the Tenant shall provide a certified copy of the policies in force with respect to such insurance coverage.

    # 10.05 Insurance Defaults.

    If the Tenant does not maintain in force any required insurance or provide proof of insurance, the Landlord may take out insurance it deems appropriate, pay the premiums, and the Tenant shall pay to the Landlord the amount of the premiums on the next Basic Rent payment date.

    # 10.06 Settlement.

    If both the Landlord and the Tenant have claims to be indemnified under any insurance, the insurance proceeds will be applied first to the settlement of the claim of the Landlord and the balance to the settlement of the claim of the Tenant.

    # 10.07 Indemnity to the Landlord.

    The Tenant shall indemnify and save harmless the Landlord from all liabilities, damages, costs, claims, suits and other actions in connection with all:

    - (a) breaches and defaults in respect of any covenant, term or agreement of this Lease by the Tenant,
    - (b) negligence or wilful acts or omissions of the Tenant,
    - (c) damage to any property on or about the Premises, unless occurring as a result of the Landlord's negligence, and
    - (d) injuries to the Tenant or any employee, licensee, invitee, customer or agent of the Tenant, and death resulting therefrom, occurring on or about the Premises as a result of the negligence, wilful act, breach or default under this Lease of the Tenant, its employees, licensees, invitees, customers or agents,

    including all costs and the Landlord’s actual legal costs and disbursements on a solicitor and own client, full indemnity basis and this indemnity will survive the expiry or sooner termination of this Lease.

    # 10.08 Amendments.

    Any changes to the above noted insurance requirements must be first approved by the Landlord in writing.

    INITIAL
    Landlord  Tenant

    MR – July 2020






    # 10.09  Acts Conflicting with Insurance.

    The Tenant shall not do or permit anything to be done by its employees, licensees, invitees, customers or agents which may render void or voidable or conflict with the requirements of any insurance policy relating to the Shopping Centre or regulations of fire insurance underwriters applicable to such policy, or which may increase the premiums payable in respect of any such policy. If any policy is cancelled because of any act or omission of the Tenant, the Landlord shall have the right at its option to terminate this Lease immediately by giving notice of termination to the Tenant. If the premiums payable in respect of any such policy are increased by an act or omission of the Tenant, the Tenant shall at the Landlord's request pay to the Landlord the amount by which those premiums are increased or the Landlord shall collect such amount as Additional Rent.

    # 10.10  Landlord not Responsible for Injuries, Loss, Damage, etc.

    The Landlord is not responsible for any injury to any person or for any loss of or damage to any property belonging to the Tenant or other occupants of the Premises or their respective employees, licensees, invitees, customers or agents or other persons from time to time in the Premises or while such person or property is in or about the Premises, the Shopping Centre or any related areaways, parking areas, lawns, sidewalks, steps, truckways, platforms, corridors or stairways, including without limiting the foregoing that caused by theft or breakage, or by steam, water, rain or snow which may leak into, flow from the Premises, any nearby lands or premises or from any other place, or for any injury to any person or loss or damage attributable to wiring, smoke, anything done or omitted by any other tenant or for any other loss whatsoever with respect to the Premises and any business carried on therein unless caused by the negligence or wilful misconduct of the Landlord.

    # 10.11  No Liability for Indirect Damages.

    The Landlord is not liable for indirect or consequential damages for personal discomfort or illness caused by or in respect of the heating of the Premises, or the operation of any air conditioning equipment, plumbing or other equipment or HVAC systems in or about the Shopping Centre.

    # 10.12  Landlord’s Insurance.

    The Landlord shall during the Term, take out and maintain in full force and effect insurance against all risks of physical loss or damage to the Shopping Centre, and such fixtures and improvements as the Landlord shall determine, and subject to such deductibles as the Landlord may reasonably determine. Provided however, the insurance shall not cover any property of the Tenant, whether owned by the Tenant or held by it in any capacity, nor leasehold improvements whether made by or on behalf of the Tenant. Notwithstanding any contribution by the Tenant to any insurance costs as provided for herein, no insurable interest shall be conferred upon the Tenant under policies carried by the Landlord.

    # 10.13  Tenant’s Contractor’s Insurance

    The Tenant will require any contractor performing work on the Premises to carry and maintain, at no expense to the Landlord, commercial general liability insurance and other






    # ARTICLE 11

    # TENANT ALTERATIONS, REPAIRS, INSTALLATIONS, FIXTURES

    # 11.01 Repairs.

    The Tenant shall maintain, repair and keep the Premises, including all appurtenances,
    equipment and fixtures including locks, all doors, including glass doors and windows,
    window frames, store fronts including vestibules, hot water tanks, plumbing fixtures,
    metal bar grid, ceiling tiles, lighting fixtures, electrical, plumbing, life safety and
    HVAC systems within the Premises in good order and repair as a careful owner would do,
    reasonable wear and tear excepted. The Tenant is responsible for damage to the Premises
    caused by its employees, licensees, invitees, customers or agents.

    # 11.02 Refurbish.

    The Tenant shall refurbish and redecorate the interior of the Premises and replace fixtures
    from time to time to maintain the appearance of the Premises as would a prudent tenant
    of a development similar in class and nature to the Shopping Centre.

    # 11.03 Care of the Premises.

    The Tenant shall take good care of the Premises in the manner of a prudent owner, and
    will keep the Premises and, without limitation, any loading area and garbage and recycling
    area in a clean, tidy and healthy condition and not allow them to become unsightly or
    hazardous.

    # 11.04 Damage to Premises.

    The Tenant shall reimburse the Landlord for all costs incurred by the Landlord in repairing
    all damage caused to the Premises, its furnishings and amenities and the Shopping Centre
    as a result of the negligence, wilful act or omission of the Tenant, its employees,
    licensees, invitees, customers or agents or other persons in or about the Premises.

    # 11.05 Right to Examine.

    The Landlord and its agents shall have the right at all times on at least twelve (12) hours’
    notice to enter the Premises, to examine its condition, and the Tenant shall within fourteen
    (14) days after the Landlord gives notice requiring same, make the repairs and replacements
    the Landlord requires to comply with this ARTICLE 11. If the Tenant fails to make such
    repairs and replacements within that fourteen (14) day period, the Landlord or its agents
    may without giving further notice enter the Premises and at the Tenant's expense, perform
    and carry out those repairs and replacements. The Landlord is entitled to enter the Premises
    without notice in the event of an emergency.

    # 11.06 Landlord's Consent Required.

    The Tenant shall not make any repairs, alterations, removals, or improvements in or about
    the Premises or do anything which might affect the operation of the lighting, plumbing,
    water, life safety systems, HVAC systems or the Shopping Centre without having

    INITIAL

    Landlord Tenant

    MR – July 2020






    # 11.06  Tenant's Work

    submitted to the Landlord adequate plans and specifications satisfactory to the Landlord and having obtained the Landlord's prior written consent.

    The Tenant shall not make any penetrations or openings in the floor slab, walls, roof, fire separations or building envelope of the Premises or the Shopping Centre without the prior written consent of the Landlord.

    All work consented to by the Landlord will be done by contractors or tradesmen previously approved in writing by the Landlord and whom the Tenant will cause to carry liability insurance as specified in section 10.13.

    # 11.07  Carrying out Improvements

    The Tenant shall promptly pay for all authorized improvements, obtain necessary approvals from all governmental authorities and carry out all authorized improvements in a good and workmanlike manner in accordance with high quality standards and all statutes, regulations, by-laws and directions of applicable governmental authorities. Upon completion of any improvements, the Tenant will provide the Landlord with a complete set of "As Built" drawings for such improvements. The Tenant shall also pay to the Landlord the amount of all increases of insurance premiums or Taxes resulting from any such improvements. All improvements made by the Landlord or the Tenant on the Premises including, but without restricting the foregoing, wall and floor coverings, t-bar ceiling, light fixtures, electrical, plumbing and HVAC fixtures and supplies, partitions and built-in furniture, will be the property of the Landlord and considered as part of the Premises.

    # 11.08  Tenant's Removal of Fixtures, etc.

    Notwithstanding section 11.07, the Tenant may at the expiry of the Term, remove from the Premises all movable and unattached furniture, machinery, fittings, shelving, supplies, counters, chattels and equipment brought onto the Premises by the Tenant in the nature of trade fixtures, but in removing them the Tenant shall not damage the Premises, and shall promptly repair any damage caused. For greater certainty, the Tenant may not, unless required to do so by the Landlord under section 11.10, remove any heating, ventilating or air-conditioning systems, facilities and equipment in or serving the Premises; plumbing fixtures and equipment; sprinklers; floor covering affixed to the floor of the Premises; light fixtures; storefront and doors; or suspended ceiling.

    # 11.09  Goods, Chattels, etc. Not to be Disposed of

    The Tenant shall not, except in the ordinary course of business, remove from the Premises or sell in bulk any goods, chattels, or fixtures until all Basic Rent and Additional Rent payable during the Term has been fully paid. The Tenant shall not remove from the Premises any plumbing, electrical, life safety or HVAC fixtures or equipment or other building services.

    # 11.10  Mandatory Removal of Fixtures, etc.

    The Landlord may, by notice given to the Tenant not later than thirty (30) days after expiry or other termination of this Lease, require the Tenant to remove all or any part of the Tenant's property and any fixtures, improvements or fittings to the Premises made by the Tenant or by the Landlord on behalf of the Tenant and to restore the Premises to their

    INITIAL

    Landlord  Tenant

    MR – July 2020







    # 11.11 Liens and Encumbrances.

    The Tenant shall keep the Shopping Centre free from and immediately discharge all liens, claims of lien and other encumbrances filed against the Premises, Property or Shopping Centre by or as a result of the actions or default of the Tenant or any contractor, subcontractor, supplier, consultant, worker or other person engaged by the Tenant or any contractor of the Tenant or for whom the Tenant is legally responsible or who has done work or provided labour, materials or service in respect of the Premises. If the Tenant fails to do so, the Landlord may (but is not obligated to do so) pay into Court or into a lawyer's trust account the amount required to obtain a discharge of such lien or encumbrance. The Tenant shall pay to the Landlord all amounts paid or incurred and all actual legal costs and disbursements on a solicitor and own client, full indemnity basis and other fees, costs and disbursements in respect of those proceedings. The Tenant shall also indemnify and save harmless the Landlord from and against all damages suffered by the Landlord as a result of such liens and encumbrances.

    # 11.12 Signs.

    The Tenant shall not place or allow any sign, notice, awning or advertisement on the outside of the Premises, the Shopping Centre or any Common Area or on any part of the interior of the Premises which is visible from the exterior thereof, without the prior written approval of the Landlord. The Landlord may by notice given to the Tenant not later than thirty (30) days after expiry of the Term or earlier termination of this Lease, require the Tenant, at its own expense, to remove any or all of its signs, awnings and advertisements located on or about the Shopping Centre as designated by the Landlord in such notice and restore all portions of the Shopping Centre affected thereby to their former condition. The Tenant acknowledges that all signage is subject to all municipal bylaws and regulations and must comply with the Landlord's signage guidelines. The Tenant is responsible for all costs associated with the Tenant's signage and shall secure all the required permits and approvals from all applicable authorities. If the Landlord, acting reasonably, objects to any sign, notice, awning, advertisement, picture, lettering or decoration which may be painted, affixed or displayed in any part of the interior of the Premises, the Tenant shall forthwith remove same at the Tenant’s sole cost and expense.

    # 11.13 Peaceful Surrender.

    At the end of the Term, the Tenant shall immediately and peaceably surrender and yield up to the Landlord the Premises, its appurtenances, and all fixtures, improvements, and erections, in a state of cleanliness and good repair, order and condition, without notice from the Landlord and deliver to the Landlord all keys to the Premises in the possession of the Tenant.

    INITIAL Landlord Tenant

    MR – July 2020







    # ARTICLE 12

    # DAMAGE OR DESTRUCTION AND EXPROPRIATION

    # 12.01  Damage or Destruction of Premises.

    (a) If the Premises are damaged or destroyed by perils covered by the Landlord's insurance policy with respect to the Premises, and unless that damage is caused by the negligence or fault of the Tenant, its employees or agents, the Basic Rent and Additional Rent will abate in the proportion that the area of the Premises rendered unfit for occupancy bears to the area of all of the Premises from the date the damage occurred until the Premises are rebuilt. The Landlord shall to the extent that insurance proceeds are available repair the Premises, unless this Lease is terminated as herein provided. In no event shall the Landlord be required to repair or replace the Tenant's leasehold improvements, stock in trade, fixtures, furnishings, floor coverings or equipment. The Landlord shall not be liable to the Tenant for any loss or damage suffered by the Tenant as a result of delay arising because of adjustment of insurance by the Landlord, labour troubles or any other cause beyond the Landlord's control.

    (b) From and after the date upon which the Landlord gives notice to the Tenant that the Landlord's work of reconstruction or repair is completed, the Tenant shall immediately commence all work required to fully restore the Premises and the Tenant's leasehold improvements, stock in trade, fixtures, furnishings, floor coverings or equipment and any other improvements previously made by or on behalf of the Tenant and the Tenant shall complete such work and reopen for business within a reasonable period of time after the giving of the Landlord's notice aforesaid with the Premises fully fixtured, stocked and staffed. The certificate of the Landlord's architect shall bind the parties hereto as to the state of tenantability of the Premises and as to the date upon which the Landlord's work of reconstruction or repair is completed.

    (c) If the Premises are damaged or destroyed by any cause and in the opinion of the Landlord the Premises cannot be rebuilt or made fit for the purposes of the Tenant within one hundred eighty (180) days after the date of such damage or destruction, instead of rebuilding or making the Premises fit for the Tenant, the Landlord may, at its option, terminate this Lease by giving the Tenant notice of termination within thirty (30) days of such damage or destruction.

    (d) Whether or not the Premises are damaged, if at least 50% of the Rentable Area of the Shopping Centre is damaged or destroyed and in the opinion of the Landlord acting reasonably that area cannot be rebuilt or made fit for tenants within one hundred eighty (180) days after such damage or destruction, the Landlord may, at its option, terminate this Lease by giving the Tenant notice of termination within thirty (30) days of such damage or destruction.

    (e) If the Landlord gives notice under section 12.01(c) or 12.01(d) the Rent and any other payments for which the Tenant is liable under this Lease will be apportioned as of the date of the occurrence of the damage or the date the Tenant properly ceases to conduct its business from the Premises, whichever is later. In such event, this Lease shall terminate on the effective date set out in the notice, not less than sixty (60) days after the Landlord gives the Tenant such notice. As of that

    INITIAL Landlord Tenant

    MR – July 2020






    # 36

    effective date, the parties will not be liable to fulfil their obligations under this Lease and the Tenant shall surrender to the Landlord vacant possession of the Premises.

    # 12.02 Expropriation.

    If during the Term, all of the Premises or more than 50% of the Shopping Centre are expropriated or otherwise taken by an authority having such power, the Landlord may at its option give notice to the Tenant terminating this Lease on the date that the Landlord is required to yield up possession and the Term shall cease from the date of entry of that authority. The Landlord and the Tenant shall be entitled to recover damages from that authority for the value of their respective interests and for all other damages and expenses allowed by law.

    # ARTICLE 13 STATUS STATEMENT, REGISTRATION AND SUBORDINATION

    # 13.01 Certificates.

    On the request of the Landlord, the Tenant shall from time to time promptly provide to the Landlord or to any other third party designated by the Landlord, certificates in writing (in form and substance as reasonably required by the Landlord) as to the then current status of this Lease, including whether it is in full force and effect, modified or unmodified, the rental payable hereunder, the state of the accounts between the Landlord and the Tenant, the existence or non-existence of defaults, and any other matters pertaining to this Lease as to which the Landlord shall request a certificate. The failure by the Tenant to deliver such a certificate within ten (10) days shall be considered to be a default under this Lease.

    # 13.02 Registration.

    The Tenant will not register this Lease nor any right granted hereunder at the land title office nor will the Landlord deliver this Lease or any right granted hereunder in registrable form.

    # 13.03 Subordination.

    (a) This Lease is subject and subordinate to all debentures, mortgages or other financial encumbrances at any time registered in the applicable land title office or the Personal Property Registry against the Shopping Centre or personal property of the Landlord regardless of the dates of registration including all renewals, modifications, consolidations, replacements and extensions. The Tenant shall promptly from time to time execute and deliver to the Landlord all instruments or assurances the Landlord requires to evidence this subordination and the Tenant hereby agrees to attorn to such mortgagee or encumbrancer provided that such mortgagee or encumbrancer has acknowledged the tenancy created by this Lease.

    (b) Any documents signed by the Tenant to evidence the foregoing subordination will provide that if the Tenant fulfils its obligations under this Lease the Tenant shall be entitled to peaceful possession of the Premises pursuant to the terms of this Lease, notwithstanding any action taken by an encumbrance holder in respect of the Premises to enforce its encumbrance.

    INITIAL

    Landlord Tenant

    MR – July 2020






    # 13.04  Tenant Information

    The Tenant shall, upon request, provide the Landlord with such information as to the
    financial standing and corporate organization of the Tenant and, if applicable, the
    Indemnifier, as the Landlord or the Landlord’s mortgagee requires. Failure of the Tenant
    to comply with the Landlord's request herein shall constitute a default under the terms of
    this Lease and the Landlord shall be entitled to exercise all of its rights and remedies
    provided in this Lease.

    # ARTICLE 14

    # DEFAULT

    # 14.01  Default.

    If at any time:

    1. the Tenant does not make any payment of Rent on the day it is due and payable;
    2. the Tenant or any other occupant of the Premises violates or fails to observe,
    perform, or keep any other covenant, agreement, obligation or stipulation herein
    contained, which has not been cured within seven (7) days after notice of same
    has been given by the Landlord to the Tenant;
    3. the Premises are unoccupied for fifteen (15) days or are vacated or the Tenant
    abandons or attempts to abandon the Premises, or sells or disposes of the goods
    and chattels of the Tenant or removes them from the Premises so that there would
    not in the event of such sale or disposal be sufficient goods of the Tenant on the
    Premises subject to distress to satisfy all Rent due or accruing hereunder for a
    period of at least twelve months;
    4. the Tenant makes a sale of all or a substantially all of its assets or any other sale
    of its assets out of the ordinary course of the Tenant’s business wherever such
    assets are situated (other than a sale made to an assignee or sublessee pursuant
    to a permitted assignment or subletting hereunder); or
    5. the Tenant assigns, transfers, encumbers, sublets or permits the occupation or
    use of the parting with or sharing possession of all or any part of the Premises by
    anyone except in a manner permitted by this Lease;

    then and in every such case the Landlord, in addition to any other rights or remedies it has
    pursuant to this Lease or by law or in equity, has the immediate right of re-entry upon the
    Premises and it may repossess the Premises by force if necessary without previous
    notice, remove all persons and property therefrom and use such force and assistance as
    the Landlord deems advisable to recover possession of the Premises and, in addition to
    any other remedies available to the Landlord hereunder or by law, may immediately cancel
    and terminate this Lease, without limitation to the Landlord’s right to claim damages arising
    from the Tenant’s default. In such case, the estate vested in the Tenant and all other
    rights of the Tenant under this Lease will immediately cease and expire and the Tenant
    shall pay to the Landlord all monies payable under this Lease and the Landlord's expenses
    of retaking possession, including the Landlord’s actual legal costs and disbursements on
    a solicitor and own client, full indemnity basis. Any property so removed may be removed.

    INITIAL

    Landlord  Tenant

    MR – July 2020






    # 14.02  Bankruptcy, etc.

    If this Lease or any of the goods or chattels of the Tenant are seized or taken in execution or in attachment by any creditor of the Tenant, if the Tenant makes any assignment for the benefit of creditors, if a receiver, receiver and manager or receiver-manager is appointed in respect of any of the assets of the Tenant, or if the Tenant is wound up or takes the benefit of any legislation for bankrupt or insolvent debtors, then at the election of the Landlord this Lease shall immediately be forfeited and void and the Basic Rent and Additional Rent for the current month and the next three (3) months will immediately become due and payable. In such case the Landlord shall at any time thereafter be entitled to re-enter the Premises, or any part thereof, in the name of the whole to re-enter and to have again, repossess and enjoy same as of its former estate.

    # 14.03  Consequences of Re-Entry.

    If the Landlord re-enters the Premises, without limiting any other remedies available to the Landlord:

    1. the Tenant shall pay on the first day of every month the Basic Rent and Additional Rent for the balance of the intended Term of this Lease as if re-entry had not been made, less the actual amount received by the Landlord after re-entry from any subsequent leasing for the balance of the intended Term; and
    2. the Landlord will be entitled to re-let the Premises and the Tenant will be responsible to the Landlord for all damages suffered by the Landlord as a result of the Tenant's breach or default.

    Re-entry will not operate as a waiver or satisfaction in whole or in part of any right, claim or demand of the Landlord in connection with any breach or failure by the Tenant in respect of any of its obligations under this Lease.

    # 14.04  Distress.

    1. All the goods and personal property of the Tenant in the Premises or wherever located will be liable to distress and sale for arrears of Rent without exemption, including the Basic Rent, Additional Rent and accelerated Rent and none of the goods or personal property in the Premises will be exempt from distress, seizure and sale for arrears of Rent and the Tenant waives the benefit of all present or future statutes limiting or eliminating the Landlord's right of distress.
    2. The Landlord may use all force it deems necessary to gain admission to the Premises without being liable to any action or for any resulting loss or damage and the Tenant hereby releases the Landlord from all actions, proceedings, claims and demands in respect of such distress. If the Tenant removes any goods or personal property from the Premises, the Landlord may follow them for ninety (90) days after removal.

    INITIAL

    Landlord            Tenant

    MR – July 2020







    # 14.05  Landlord's Costs in Enforcing Lease.

    In the event of a breach or default by the Tenant, the Landlord shall be entitled to collect from the Tenant immediately on demand, the Landlord’s actual costs and expenditures, including without limitation its actual legal costs and disbursements on a solicitor and own client, full indemnity basis.

    # 14.06  Payments After Termination

    No payment of money by the Tenant to the Landlord after the expiration of the Term or other termination of this Lease or after the giving of any notice by the Landlord to the Tenant, will reinstate, continue, renew or extend the Term or make ineffective any notice given to the Tenant prior to the payment of such money. After the service of notice or the commencement of a suit, or after final judgment granting the Landlord possession of the Premises, the Landlord may receive and collect any sums of Rent due under this Lease, and the payment thereof will not make ineffective any notice, or in any manner affect any pending suit or any judgment theretofore obtained.

    # 14.07  Personal Property Security.

    As security for all indebtedness at any time owing by the Tenant to the Landlord under this Lease and as security for the payment of cash allowances, inducement payments, or the value of any other benefit paid to or conferred on the Tenant by the Landlord and for all other obligations of the Tenant under this Lease, the Tenant mortgages, charges and grants to the Landlord a continuing fixed security interest in all of the Tenant's present and after acquired personal property including all inventory, equipment, fixtures, chattels, and leasehold improvements and the proceeds thereof, but excluding consumer goods, (collectively "Collateral"). The security interest shall attach on execution of this Lease or, in the case of after acquired property, on the date of acquisition by the Tenant. Notwithstanding the foregoing, the Tenant will be entitled to sell its inventory to its customers in the ordinary course of its business. The Tenant's principal place of business is as shown on page one and the Tenant will give the Landlord at least ten (10) days’ written notice of any change. The Tenant waives all rights to receive from the Landlord a copy of any financing statement or verification statement under the Personal Property Security Act. Upon any default under this Lease, the Landlord may take any lawful action it deems expedient under this Lease and may also appoint a receiver or receiver-manager in respect of the Collateral (who will have all the powers of the Landlord), enter onto the Premises and take possession of the Collateral, preserve, protect, maintain, retain and administer the Collateral, sell, lease or otherwise dispose of the Collateral and exercise all rights of a secured party under the Personal Property Security Act of the jurisdiction in which the Premises are located, all in the discretion of the Landlord. All proceeds of disposition of the Collateral will be applied towards money owing to the Landlord by the Tenant as the Landlord directs and the Tenant will be liable for any deficiency thereafter. The Tenant covenants not to permit a security interest to be created in any of the Collateral without the consent of the Landlord.

    INITIAL

    Landlord          Tenant

    MR – July 2020






    # ARTICLE 15

    # GENERAL

    # 15.01 Force Majeure.

    In the event that any party hereto shall be delayed or hindered in or prevented from the performance of any act required hereunder by reason of acts of God, strikes, lock-outs, labour troubles, riots, insurrection, war or other reason of a nature beyond such party’s control in performing work or doing acts required under the terms of this Lease, then performance of such act shall be excused for the period of the delay and the party delayed shall do what was delayed or prevented as soon as reasonably possible after the delay and shall use all reasonable efforts to minimize the effects of the event of Force Majeure. Financial inability of the Landlord or Tenant or any other party shall not be considered to be an event of Force Majeure. Any party so delayed shall give prompt written notice to the other parties if it becomes subject to an event of Force Majeure and shall advise as to the anticipated duration of such event. Without limiting the foregoing, if the federal, provincial or municipal government enacts a binding order regarding the current COVID-19 pandemic which prohibits the Tenant from occupying the Premises (an “Order”), the Landlord and Tenant, acting reasonably, shall determine the duration and effect of the Order (the “Interruption”) and all obligations of the Tenant to pay Basic Rent to the Landlord shall be waived until the end of the Interruption subject to the terms of the Order and all applicable law, but the Term shall be extended by that same number of the days of the Interruption. In such an event, to the extent possible, the parties agree to use commercially reasonable efforts to minimize the period and effect of the Interruption.

    # 15.02 No Representations by Landlord.

    There are no promises, representations or undertakings by or binding on the Landlord with respect to any alteration, remodelling or decorating, or installation of equipment or fixtures in the Premises or with respect to any other matter, except as expressly set out in this Lease and Offer to Lease. The Tenant acknowledges that the Premises are leased subject to all zoning and other land use restrictions, and it is the Tenant's obligation to ensure that its intended uses are permitted. There are no representations or warranties by the Landlord as to the Premises except as set out in the Offer to Lease or this Lease.

    # 15.03 Holding Over.

    If the Tenant holds over after the end of the Term, and the Landlord accepts Rent, the new tenancy will be a month to month tenancy, subject to the terms and covenants herein applicable to a month to month tenancy, except that:

    - (a) it will be subject to termination by the Landlord on one week's notice to the Tenant;
    - (b) there will be no right of renewal; and
    - (c) the monthly Basic Rent payable will be double the monthly Basic Rent last payable hereunder.

    INITIAL
    Landlord  Tenant

    MR – July 2020





    # 15.04  Landlord - Tenant Relationship.

    Any intention to create a joint venture or partnership between the parties, or any relationship other than that of Landlord and Tenant is disclaimed.

    # 15.05  Time of Essence.

    Time is of the essence of this Lease.

    # 15.06  Waiver.

    The failure of the Landlord to insist on strict performance of any covenant or obligation of the Tenant in this Lease or to exercise any right or option hereunder will not be a waiver or relinquishment of that covenant or obligation or any other default hereunder. The acceptance of any Rent from or the performance of any obligation hereunder by anyone other than the Tenant will not be an admission by the Landlord of any right, title or interest of such person as a sub-tenant, assignee, transferee or otherwise in the place of the Tenant, nor shall it constitute a waiver of any breach of this Lease. If the Landlord makes an error in calculating or billing any monies payable by the Tenant under this Lease, such will not be a waiver of the Landlord's right to collect the proper amount of monies payable by the Tenant.

    # 15.07  Interest.

    The Tenant shall pay to the Landlord interest at a rate equal to the commercial prime lending rate of the Landlord's bank plus five per cent per annum calculated, compounded and payable monthly on all money payable by the Tenant pursuant to this Lease, which has become overdue, as long as such payments remain unpaid by the Tenant, which interest will be recoverable as Additional Rent.

    # 15.08  Entire Agreement.

    This Lease constitutes the entire agreement between the parties with respect to the Premises except as contained in the Offer to Lease and where there is any inconsistency between this Lease and the Offer to Lease, the terms of this Lease shall govern.

    # 15.09  No Changes or Waivers.

    No changes to or waiver of any part of this Lease will be binding or enforceable unless reduced to writing and executed by the Landlord and the Tenant and if so executed shall be binding upon the Indemnifier, if any. The Landlord's agents have no authority to amend this Lease unless duly authorized in writing by the Landlord to do so.

    # 15.10  Notices.

    Any notice, request, demand, direction, designation or statement required or permitted under this Lease to the Tenant or the Landlord will be sufficiently given if delivered, sent by facsimile transmission or emailed or mailed in British Columbia by double registered mail postage prepaid, to the addresses as set out below, or if given to the Tenant by delivery to the Premises. Any notice will be deemed to have been given on the date delivered or sent by facsimile transmission or emailed, and if mailed, on the sixth day after it was mailed. The Landlord or the Tenant may at any time give notice to the other of a

    INITIAL

    Landlord  Tenant

    MR – July 2020





    change of address for notices, after which the altered address will be the address of such party for notices. During any interruption of postal service, notice shall be given by delivery or sent by facsimile or emailed. Notices are to be given as follows:

    # To the Landlord:

    PLATFORM PROPERTIES (MAPLE RIDGE) LTD.

    #900-1200 West 73rd Avenue

    Vancouver, BC

    V6P 6G5

    Attention: Kyle Shury

    Fax: (604) 563-5001

    Email: kyle@platformproperties.ca

    # To the Tenant:

    1256325 B.C. Ltd.

    #202- 32625 South Fraser Way

    Abbotsford, BC

    V2T 1X8

    Attention: Harpreet Bahia &#x26; Jatinder Badyal

    Email: sub4916@gmail.com

    # To the Indemnifier:

    Harpreet Bahia

    3477 Blueberry Court

    Abbotsford, BC

    V3G 3C9

    Attention: Harpreet Bahia

    Email: sub4916@gmail.com

    Jatinder Badyal

    3816 Clinton Street

    Burnaby, BC

    V5J 2K1

    Attention: Jatinder Badyal

    Email: jerrybadyal@gmail.com

    # 15.11  Headings and Marginal Notes.

    The headings and marginal notes in this Lease form no part of this Lease and are inserted for convenience of reference only.

    # 15.12  Rights Cumulative.

    All rights and remedies of the Landlord under this Lease are cumulative and not alternative.

    INITIAL

    Landlord  Tenant

    MR – July 2020







    # 15.13 Sale By Landlord.

    In the event of a sale, transfer or lease by the Landlord of the Premises or the Shopping Centre or the assignment by the Landlord of this Lease or any interest under this Lease, the Landlord shall without further agreement, to the extent that such purchaser, transferee or lessee has become bound by the covenants and obligations of the Landlord hereunder, be released and relieved of all liability and obligations under this Lease.

    # 15.14 British Columbia Law.

    This Lease will be construed in accordance with the laws of the Province of British Columbia and the courts of British Columbia will have exclusive jurisdiction with respect to all matters arising in relation to this Lease.

    # 15.15 Provisions Severable.

    If any provisions of this Lease are illegal or unenforceable, they will be considered separate and severable from this Lease and the remaining provisions will remain in force and be binding on the parties as if the severed provisions had not been included.

    # 15.16 Joint and Several.

    If there are two or more Tenants, Indemnifiers (if any) or persons bound by the Tenant's obligations under this Lease, their obligations are joint and several.

    # 15.17 Interpretation.

    All the obligations of the Tenant under this Lease are to be construed as covenants and agreements as though the words importing such covenants and agreements were used in each separate provision. All obligations of the Tenant are in force during the full Term, unless otherwise specified. The words "Tenant" or "Indemnifier" (if applicable) and the personal pronoun "it" relating thereto and used therewith shall be read and construed as Tenants or Indemnifiers (if applicable) and "his", "her", or "its" or "their" respectively, as the number and gender of the party or parties referred to each require, and the number of the verb agreeing therewith will be construed and agreed with the said word or pronoun so substituted.

    # 15.18 Enurement.

    This Lease shall enure to the benefit of and be binding on the parties hereto and their respective executors, administrators, successors and permitted assigns.

    # 15.19 Indemnity

    Concurrently with the delivery of this Lease executed by the Tenant, there shall be delivered to the Landlord the Indemnity Agreement attached hereto as Schedule D executed by the Indemnifier.

    INITIAL
    Landlord  Tenant

    MR – July 2020






    The parties hereto have executed this Lease as of the day and year first above written.

    # PLATFORM PROPERTIES (MAPLE RIDGE) LTD.

    By:
    Authorized Signatory

    By:
    Authorized Signatory

    # 1256325 B.C. LTD.

    By:
    Authorized Signatory

    By:
    Authorized Signatory

    # Witnesses

    Harpreet Bahia
    Name:
    Address:

    Jatinder Badyal
    Name:
    Address:

    # INITIAL

    Landlord  Tenant

    MR – July 2020






    SCHEDULE A

    # Plan of Premises

    Showing the area and location of the Premises. The purpose of this plan is to identify the approximate location of the Premises in the Shopping Centre. The Landlord reserves the right, in its sole discretion, at any time to relocate, rearrange or alter the buildings and structures, other premises and Common Areas.

    | BLDG 2000  | 20,994 SF |
    | ---------- | --------- |
    | 100-2      |           |
    | BLDG 20    | 10        |
    | Y0oD       | 9188 SF   |
    | 8          | 88        |
    | 240 STREET |           |

    INITIAL

    Landlord  Tenant

    MR – July 2020





    # SCHEDULE B

    # (Miscellaneous Provisions)

    # 1.00 Renewal Option(s)

    (a) If the Tenant punctually, duly and regularly pays the Rent and observes and performs all its obligations in this Lease, the Landlord shall grant the Tenant two (2) renewal options of this Lease for terms of five (5) years each on the same terms as this Lease, except for the Basic Rent which will be determined as set out in this section, and except for any free rent, tenant inducements or tenant's improvements provided by the Landlord to the Tenant, which will be deleted.

    (b) Each option can only be exercised by the Tenant giving written notice of exercise to the Landlord, not more than three hundred sixty-five (365) days nor less than one hundred eighty (180) days before the end of the Initial Term or last renewal which formed part of the Term, as the case may be.

    (c) After an option has been exercised, the Landlord and Tenant shall promptly attempt to agree on the Basic Rent for the renewal term, which will be the Fair Market Basic Rent as defined in this section, but in any event not less than the equivalent Basic Rent and Percentage Rent, if applicable, paid during the last year of the Initial Term or last renewal which formed part of the Term, as the case may be. If the parties are not able to agree on the Basic Rent by sixty (60) days before the beginning of the renewal term, such Basic Rent will be determined by a sole arbitrator in accordance with the Arbitration Act of British Columbia. The domestic rules of the British Columbia International Commercial Arbitration Centre (the "Centre") or any successor institution, if any, if the Centre ceases to carry on business will be applicable to such arbitration (with the exception of rules requiring the Centre to administer the arbitration and with respect to the payment of fees to the Centre for such administration). The arbitrator will be a member of the Appraisal Institute of Canada or its successor, and the cost of the arbitration will be borne as ordered by the arbitrator.

    (d) "Fair Market Basic Rent" means the Basic Rent generally prevailing sixty (60) days prior to the end of the Initial Term or last renewal which formed part of the Term, as the case may be, for leases of similar size premises of the same class of space in the area in which the Premises are located or comparable areas, which leases have been recently negotiated. In determining such Basic Rent, the value of all leasehold improvements installed on the Premises by the Tenant and the Landlord will be included.

    (e) If such Basic Rent has not been determined by the beginning of the renewal term, the Tenant shall until such determination pay the Basic Rent payable during the last year of the Initial Term or last renewal which formed part of the Term, as the case may be. Any additional Basic Rent owing for the renewal term before such determination will be payable by the Tenant within ten (10) days after such determination. Interest as set out in section 15.07 will be payable by the Tenant to the Landlord on such additional Basic Rent, calculated from the date of commencement of the renewal term to the date such additional amounts are paid.

    INITIAL

    Landlord Tenant

    MR – July 2020







    # 2.00 Tenant's Work

    The Tenant will be responsible for the Tenant’s Work in accordance with the provisions as set out in the Offer to Lease unless otherwise provided below.

    # 2.01 Fixturing Period

    The Landlord shall give to the Tenant at least five (5) business days’ advance notice of the date upon which the Premises will be ready for the commencement of the Tenant’s Work (the "Possession Date"). The Possession Date is currently estimated to be November 1, 2020. The Tenant shall have a maximum of one hundred twenty (120) days’ free possession of the Premises from the Possession Date for the purposes of performing the Tenant’s Work (the "Fixturing Period"). During the Fixturing Period, the Landlord may also have access to the Premises for the purposes of completing the Landlord's Work provided that the Tenant's Work may be undertaken without undue interference from the carrying out of the Landlord's Work.

    Any occupation of the Premises by the Tenant prior to the Commencement Date will be subject to all of the terms of this Lease, except for payment of Basic Rent and Additional Rent. The Tenant shall be responsible for the cost of all utilities, garbage removal and the costs of any insurance during the Fixturing Period.

    If the Tenant is to take possession of the Premises on a specific date and if the Premises are not ready for possession on that specific date, then the Tenant shall take possession of the Premises as soon as the same are ready for possession and this Lease shall not be void or voidable nor shall the Landlord be liable for any loss or damage resulting from the delay in the Tenant obtaining possession.

    # 2.02 Tenant Improvement Allowance

    The Landlord will pay to the Tenant, as a contribution toward the Tenant’s leasehold improvements, the maximum sum of $20.00 per square foot of Rentable Area of the Premises, plus GST within thirty (30) days of satisfaction of all of the following conditions and provided that there has been no default by the Tenant of its obligations under this Lease:

    - (a) the Tenant supplying the Landlord with proof satisfactory to the Landlord of having expended such amount towards construction of leasehold improvements within the Premises, such proof to be in the form of either a quantity surveyors or bank appraisers report;
    - (b) the Tenant supplying the Landlord with a complete set of "As Built" drawings for the Tenant’s Work;
    - (c) the Tenant supplying the Landlord with a Certificate of Occupancy Permit for the Premises and a Signage Permit for all Tenant signs requiring permits;
    - (d) the Tenant providing a statutory declaration stating that all accounts for work, services and materials for the Premises have been paid by the Tenant and that the Tenant is not aware of any unpaid parties who have or could file claims of builder’s.

    INITIAL

    Landlord    Tenant

    MR – July 2020






    # 4.00 Exclusivity Claims

    The Tenant covenants and agrees that during the Term, the Tenant will not use or permit any part of the Premises to be used for any operation which would cause the Landlord to be in violation of those restrictive covenants imposed upon the Landlord pursuant to leases to other tenants including those below:

    | INITIAL        | Landlord | Tenant |
    | -------------- | -------- | ------ |
    | MR – July 2020 |          |        |

    # 3.00 Landlord’s Work

    The Landlord will be responsible for the Landlord’s Work in accordance with the provisions set out in the Offer to Lease unless otherwise provided below.

    # 2.00 Tenant’s Work

    The Tenant shall not commence any work on the Premises until:

    1. The Landlord has received satisfactory title information confirming that the Shopping Centre is free and clear of all liens and encumbrances in connection with the Tenant’s Work;
    2. Delivery of proof of insurance as required pursuant to this Lease;
    3. This Lease being executed by the Landlord and Tenant;
    4. The Tenant having opened for business in the Premises;
    5. The Tenant providing to the Landlord an invoice indicating the amount of the tenant improvement allowance payable, including GST, and the Tenant’s GST registration number.

    Any tenant improvement allowance, leasehold improvement allowance or inducement contribution toward the Tenant’s leasehold improvements or similar amount paid or credited to the Tenant shall be amortised by the Landlord over the Initial Term at an interest rate of 8% per annum, calculated semi-annually. If this Lease is terminated by the Landlord due to any default by the Tenant under this Lease, then the outstanding and unamortised portion of the tenant improvement allowance, leasehold improvement allowance or inducement or similar amount paid or credited to the Tenant shall be paid by the Tenant to the Landlord forthwith upon demand by the Landlord. If the Tenant fails to forthwith pay the amount so demanded by the Landlord, the Landlord will have the same rights and remedies as are available to it for unpaid Rent. The obligation of the Tenant to repay the tenant improvement allowance, leasehold improvement allowance or inducement or similar amount paid or credited to the Tenant in the event of the Tenant's default under this Lease will survive the expiration or earlier termination of this Lease.





    # PHARMACY

    Landlord covenants and agrees that it shall not lease, licence, suffer or permit the use of any other space in the Shopping Centre for the operation of a retail pharmacy or pharmaceutical dispensary.

    # DENTAL

    The Landlord will not lease premises in the Shopping Centre to a business whose principal business is that of a dental or orthodontic practice.

    # SUSHI

    The Landlord will not lease premises in the Shopping Centre to a business whose principal business is that of a Japanese style Sushi restaurant.

    # PIZZA

    The Landlord will not lease premises in the Shopping Centre to a business whose principal business is the sale of pizza.

    # CANNABIS

    The Landlord will not lease premises in the Shopping Centre to a business whose principal business is that of the retail sale of cannabis for recreational use.

    # FITNESS

    The Landlord will not lease premises in the Shopping Centre to a business whose principal business is that of a health club facility.

    # VET

    The Landlord will not lease premises in the Shopping Centre to a business whose principal business is that of a veterinary clinic/veterinary hospital.

    The Tenant acknowledges that the Landlord may modify or delete the exclusivity claims and/or restrictive covenants set out above and may grant exclusivity claims and/or restrictive covenants to other tenants of the Shopping Centre, other than as described above, but in no event will such further exclusivity claims and/or restrictive covenants conflict with any exclusive use granted herein to the Tenant. Provided that such further exclusivity claims and/or restrictive covenants do not conflict with the exclusive use granted herein to the Tenant, then the Tenant will not use or permit the Premises to be used for any operation which would cause the Landlord to be in violation of such further restrictive covenants.

    INITIAL
    Landlord  Tenant

    MR – July 2020




    # 4.01 Prohibited Uses

    The Tenant covenants and agrees that during the Term, the Tenant will not use or permit any part of the Premises to be used for any operation which would cause the Landlord to be in violation of those prohibited uses imposed upon the Landlord pursuant to leases to other tenants including those below:

    1. for the sale, dispensing or distribution of any items of merchandise requiring the approval or supervision of a registered or licensed pharmacist;
    2. for the operation of any store which sells general merchandise at one or more price points commonly known as dollar stores;
    3. for the operation of a convenience store, variety store or jug milk store;
    4. for the sale of photofinishing services, including self-serve kiosks for the developing of photographs from digital images;
    5. for the operation of a retail postal outlet;
    6. for the operation of a store whose principal business is the sale of health and beauty aids;
    7. for the operation of a store whose principal business is the sale of greeting cards and/or stationery;
    8. for the operation of a store whose principal business is the sale of cosmetics and beauty products;
    9. for the operation of a store whose principal business is the sale of fragrances (such as perfumes and colognes) and/or perfumed bath and/or body products;
    10. for the operation of a store whose principal business is the sale of home health care and convalescent products;
    11. for the operation of a health supplements food store or a store whose principal business is the sale of vitamins, neutraceuticals and/or health food supplements;
    12. for the operation of a telecommunications, telephone, automated or electronic system (including without limitation, internet communication systems), whether located in a kiosk, booth, store, or any other facility, whereby a customer can communicate with a third party (no matter where such third party is located) to have prescriptions filled, to order medical supplies and/or non-prescription drugs or to ask questions or receive information respecting medications, prescriptions or non-prescription drugs;
    13. for the operation of a store which exclusively sells bulk merchandise (notwithstanding the foregoing, Landlord may lease space in the Development to one bulk food retailer of not greater than 7,000 square feet);

    INITIAL

    Landlord Tenant

    MR – July 2020







    # vii

    (14) for the operation of a store whose business is comprised of any two (2) or more of the types of businesses or the stores or outlets described in subparagraphs (1) to (13) of this paragraph.

    The Tenant acknowledges that the Landlord may modify or delete the prohibited uses set out above and may agree to additional prohibited uses for other tenants of the Shopping Centre, other than as described above, but in no event will such further prohibited uses conflict with any permitted use granted herein to the Tenant. Provided that such further prohibited uses do not conflict with the permitted use granted herein to the Tenant, then the Tenant will not use or permit the Premises to be used for any operation which would cause the Landlord to be in violation of such further prohibited uses.

    # 5.00 Radius Restriction

    Neither the Tenant nor any affiliated party will directly or indirectly engage in any business that is similar to or in competition with the Tenant’s business in the Premises within three (3) kilometres of the Shopping Centre.

    # 6.00 Exclusive Use

    The Landlord covenants that so long as the Tenant is in actual possession of the whole of the Premises and is carrying on its business in the Premises in accordance with the terms of this Lease including using the Premises for the permitted use as set out in section 8.01 and is not then in default, or been in repeated default, of this Lease the Landlord will not, at any time during the Term, lease premises in the Shopping Centre, other than the Premises, to any tenant whose principal business is the sale of chicken products, such as by way of example, but not limited to KFC, Popeyes Chicken, Mary Brown’s Chicken &#x26; Taters, Swiss Chalet or Barcelo’s.

    It is understood and agreed that the Landlord is not obliged to observe the foregoing covenant if by so doing it will be in breach of any laws, rules, regulations or enactments from time to time in force, and the foregoing covenant is not intended to apply or to be enforceable to the extent that it would give rise to any offence under the Competition Act, or any federal or provincial statute that may be substituted therefor or may be enacted with similar intent, as from time to time amended.

    Notwithstanding the foregoing, the Tenant acknowledges that the foregoing covenant shall not apply to any premises or business of any tenant, or the successors or assigns of any tenant, operating within the Shopping Centre under any lease or agreement in existence prior to the Commencement Date, and shall further not apply to any tenant occupying in excess of 8,000 square feet of Rentable Area.

    INITIAL

    Landlord  Tenant

    MR – July 2020







    # 7.00 Grand Opening and Promotion Fund

    This section has been intentionally deleted.

    # 8.00 Pylon Signage

    The Tenant shall be entitled to the use of one (1) double sided panel on one of the pylon signs for the Shopping Centre. The size of the panel shall be approximately five (5) feet by two (2) feet in a location on the pylon sign determined by the Landlord and the Tenant shall pay a monthly fee in the amount of $175.00, exclusive of GST payable at the same time as Basic Rent for the use of the panel. The Tenant shall be entitled to the use of the panel during the Initial Term and each renewal of the Term, as applicable, but the monthly fee will be subject to reasonable renegotiation at the end of the Initial Term and each renewal of the Term, as applicable. The use by the Tenant of the panel shall be subject to the Tenant complying with the terms of this Lease, and if the Tenant is in default under any term of this Lease, the right of the Tenant to use of the panel may be terminated by the Landlord upon three (3) days’ notice to the Tenant. The Tenant shall be required to pay for all costs of creation and installation of their signage on the panel as well a pro-rata share of operating costs for such pylon sign as determined by the Landlord in addition to any other Rent payable hereunder.

    INITIAL

    Landlord  Tenant

    MR – July 2020






    # SCHEDULE C

    # (Percentage Rent)

    # 1.01 Percentage Rent.

    In addition to Basic Rent, the Tenant shall pay to the Landlord Percentage Rent on a monthly basis.

    # 1.02 Certification of Percentage Rent.

    By the fifteenth (15) day of every calendar month, beginning on the month after Percentage Rent is first payable, and until the month after the end of the Term, the Tenant shall submit to the Landlord a written statement certified correct by an officer of the Tenant, showing in reasonable detail the Gross Revenues during the immediately preceding month. If Percentage Rent is payable in and for that month, the Tenant will concurrently pay to the Landlord such Percentage Rent.

    # 1.03 Annual Calculation and Payment.

    (a) Within sixty (60) days after the end of each year or other period designated by the Landlord and after the end of the Term, the Tenant shall submit to the Landlord a written statement certified by its certified professional accountant or similarly qualified accountant reasonably satisfactory to the Landlord, setting out in reasonable detail the amount of the Tenant’s Gross Revenues for each month during the immediately preceding year or other period and the amount of Percentage Rent payable. An adjustment will be made between the parties so that the Tenant shall pay to the Landlord the Basic Rent and Percentage Rent for that year or the other period.

    (b) If the monthly payments actually made by the Tenant on account of Percentage Rent are less than the Percentage Rent calculated in accordance with this section set out above, the Tenant shall immediately pay to the Landlord the additional Percentage Rent payable.

    (c) If the monthly payments actually made by the Tenant on account of Percentage Rent are greater than Percentage Rent calculated in accordance with this section set out above, then the Landlord may at its election within thirty (30) days after receipt of such statement either refund to the Tenant the excess or credit the Tenant for the excess against the Basic Rent and Additional Rent payable during the next month’s rental.

    # 1.04 Tenant’s Accounts.

    To establish the Percentage Rent, the Tenant shall keep detailed and accurate accounts, records, books, reporting records and date with respect to its Gross Revenues, the daily business done and the orders received in or from the Premises in accordance with this section and shall cause any sub-lessee, licensee, franchisee or concessionaire to do so. The Tenant must keep those records for at least three years from the end of each calendar year. The Tenant will comply with all reasonable directions issued to it by the Landlord respecting accounting records and procedures to be adopted for proper recording and control of transactions affecting Gross Revenues, including, without limitation, the mandatory use of a cash register which tabulates the daily sales constituting Gross Revenues. By accepting any statement of Gross Revenues, the Landlord will not have waived any of its rights under this Lease.

    INITIAL

    Landlord       Tenant

    MR – July 2020







    # 1.05 Right to Examine

    The Landlord and its accountants and agents shall have the right at all reasonable times to examine all accounts, records, books, cash register tapes, computer records, sales tickets, sales reports, contracts and other data concerning the Gross Revenues, including all credits and other things relating to Gross Revenues. If an examination discloses that there is a variation of more than three percent (3%) in any statement of Gross Revenues rendered by the Tenant from the actual Gross Revenues, the cost of the Landlord's examination will be paid by the Tenant, and if the variation is more than five percent (5%), the Landlord shall also be entitled to terminate this Lease on thirty (30) days’ notice to the Tenant. In addition, the Tenant shall on demand immediately pay any deficiency in Percentage Rent disclosed by that examination together with interest payable under this Lease. All information obtained by the Landlord as a result of such examination will be treated as confidential unless the Tenant is obliged to pay the cost of the examination and fails to do so or unless required in connection with sale, financing or other business transaction by the Landlord.

    # 1.06 Additional Gross Revenues

    If the Tenant directly or indirectly engages in or furnishes any financial aid or other support or assistance to any business, enterprise or undertaking competitive with the use of the Premises set out in section 8.01, in whole or part conducted from premises located within a three (3) kilometre radius from any part of the Shopping Centre, then for the purpose of calculating Percentage Rent, all Gross Revenues from that competitive business, enterprise or undertaking will be added to the Gross Revenues from the business operations of the Tenant in the Premises except to the extent that the Landlord gives prior written consent to the Tenant, which may be withheld in the Landlord's absolute discretion, and except that this provision does not apply to any business enterprise of the Tenant in operation as of the date of this Lease.

    INITIAL
    Landlord  Tenant

    MR – July 2020






    # SCHEDULE D

    # (Indemnity Agreement)

    THIS AGREEMENT is dated the 13ᵗʰ day of July, 2020.

    BETWEEN:

    PLATFORM PROPERTIES (MAPLE RIDGE) LTD.

    (the "Landlord")

    AND:

    Harpreet Bahia &#x26; Jatinder Badyal

    (the "Indemnifier")

    In order to induce the Landlord to enter into the lease (the "Lease") dated the 13ᵗʰ day of July, 2020 and made between the Landlord and 1256325 B.C. Ltd. as Tenant, and for other good and valuable consideration, the receipt and sufficiency whereof is hereby acknowledged, the Indemnifier hereby makes the following indemnity and agreement (the "Indemnity") with and in favour of the Landlord.

    1. The Indemnifier hereby agrees with the Landlord that at all times during the Term of the Lease and for greater certainty all extensions or renewals of the Lease it will:
    1. make the due and punctual payment of all Rent, monies, charges and other amounts of any kind whatsoever payable under the Lease by the Tenant whether to the Landlord or otherwise and whether the Lease has been disaffirmed or disclaimed;
    2. effect prompt and complete performance of all and singular the terms, covenants and conditions contained in the Lease on the part of the Tenant to be kept, observed and performed; and
    3. indemnify and save harmless the Landlord from any loss, costs or damages arising out of any failure by the Tenant to pay the aforesaid Rent, monies, charges or other amounts due under the Lease or resulting from any failure by the Tenant to observe or perform any of the terms, covenants and conditions contained in the Lease.
    2. This Indemnity is absolute and unconditional and the obligations of the Indemnifier shall not be released, discharged, mitigated, impaired or affected by:
    1. any extension of time, indulgences or modifications which the Landlord extends to or makes with the Tenant in respect of the performance of any of the obligations of the Tenant under the Lease;
    2. any waiver by or failure of the Landlord to enforce any of the terms, covenants and conditions contained in the Lease;

    INITIAL

    Landlord        Tenant

    MR – July 2020






    # xii

    (c) any assignment of the Lease by the Tenant or by any trustee, receiver or liquidator;

    (d) any consent which the Landlord gives to any such assignment or subletting;

    (e) any amendment to the Lease or any waiver by the Tenant of any of its rights under the Lease; or

    (f) the expiration of the Term.

    # 3.

    The Indemnifier hereby expressly waives notice of the acceptance of this Agreement and all notice of non-performance, non-payment or non-observance on the part of the Tenant of the terms, covenants and conditions contained in the Lease. Without limiting the generality of the foregoing, and subject to the terms of section 8 of this Agreement, any notice which the Landlord desires to give to the Indemnifier shall be sufficiently given if delivered to the Indemnifier in accordance with the provisions for the giving of notice set out in the Lease and every such notice is deemed to have been given if given in accordance with the provisions of the Lease. The Indemnifier may designate by written notice a substitute address for that set forth above or in the Lease and thereafter notices if applicable shall be directed to such substitute address. If two or more Persons are named as Indemnifier, any notice given hereunder or under the Lease shall be sufficiently given if delivered or mailed in the foregoing manner to any one of such Persons.

    # 4.

    In the event of a default under the Lease or under this Agreement, the Indemnifier waives any right to require the Landlord to:

    (a) proceed against the Tenant or pursue any rights or remedies against the Tenant with respect to the Lease;

    (b) proceed against or exhaust any security of the Tenant held by the Landlord; or

    (c) pursue any other remedy whatsoever in the Landlord’s power.

    The Landlord has the right to enforce this Indemnity regardless of the acceptance of additional security from the Tenant and regardless of any release or discharge of the Tenant by the Landlord or by others or by operation of any law.

    # 5.

    Without limiting the generality of the foregoing, the liability of the Indemnifier under this Indemnity is not and is not deemed to have been waived, released, discharged, impaired or affected by reason of the release or discharge of the Tenant in any receivership, bankruptcy, winding-up or other creditors proceedings or the rejection, disaffirmance or disclaimer of the Lease in any proceeding and shall continue with respect to the periods prior thereto and thereafter, for and with respect to the Term as if the Lease had not been disaffirmed or disclaimed, and in furtherance hereof, the Indemnifier agrees, upon any such disaffirmance or disclaimer, that the Indemnifier shall, at the option of the Landlord, become the Tenant of the Landlord upon the same terms and conditions as are contained in the Lease, applied mutatis mutandis. The liability of the Indemnifier shall not be affected by any repossession of the Premises by the Landlord, provided, however, that the net payments received by the Landlord after deducting all costs and expenses of repossessing and reletting the Premises shall be credited from time to time by the Landlord.

    INITIAL

    Landlord Tenant

    MR – July 2020






    # Indemnity Agreement

    against the indebtedness of the Indemnifier hereunder and the Indemnifier shall pay any balance owing to the Landlord from time to time immediately upon demand.

    # 6.

    No action or proceedings brought or instituted under this Indemnity and no recovery in pursuance thereof shall be a bar or defence to any further action or proceeding which may be brought under this Indemnity by reason of any further default hereunder or in the performance and observance of the terms, covenants and conditions contained in the Lease.

    # 7.

    No modification of this Indemnity shall be effective unless the same is in writing and is executed by both the Indemnifier and the Landlord.

    # 8.

    The Indemnifier shall, without limiting the generality of the foregoing, be bound by this Indemnity in the same manner as though the Indemnifier were the Tenant named in the Lease and for greater certainty, any matter approved or agreed upon from time to time by the Tenant will be considered to have been approved and agreed upon by the Indemnifier, and for this purpose the Landlord may treat the Tenant as the representative of the Indemnifier. The Landlord will be free to deal with the Tenant without seeking the approval or consent of or notifying or advising the Indemnifier and, in connection with this Lease and all related matters, any notice or communication made or given by the Landlord to the Tenant will be deemed to be effectively made or given to the Indemnifier. As between the Landlord and the Indemnifier, the Indemnifier accepts the entire responsibility for ensuring that it will be kept apprised (by the Tenant) of all matters concerning this Lease and for ensuring that the Tenant seeks and obtains approval or concurrence of the Indemnifier (to the extent that the Indemnifier may be affected, or would like to be consulted) for matters concerning this Lease including any such renewal, modification, amendment, or extension thereof.

    # 9.

    If two or more individuals, corporations, partnerships or other business associations (or any combination of two or more thereof) execute this Indemnity as Indemnifier, the liability of each such individual, corporation, partnership or other business association hereunder is joint and several. In like manner, if the Indemnifier named in the Indemnity is a partnership or other business association, the members of which are by virtue of statutory or general law subject to personal liability, the liability of each such member is joint and several.

    # 10.

    All of the terms, covenants and conditions of this Indemnity extend to and are binding upon the Indemnifier, his or its heirs, executors, administrators, successors and assigns, as the case may be, and enure to the benefit of and may be enforced by the Landlord, its successors and assigns, as the case may be, and any mortgagee, chargee, trustee under a deed of trust or other encumbrancer of all or any part of the Shopping Centre referred to in the Lease.

    # 11.

    The expressions "Landlord", "Tenant", "Rent", "Term" and "Premises" and other terms or expressions where used in this Indemnity, respectively, have the same meaning as in the Lease.

    # 12.

    This Agreement is being executed and delivered, and shall be performed in the Province of Canada in which the Shopping Centre is located, and the laws of such Province shall

    INITIAL

    Landlord

    Tenant

    MR – July 2020






    # Indemnity

    govern the validity, construction, enforcement and interpretation of this Lease. The exclusive venue for any application or court action brought in respect of this Lease shall lie with the courts of the Province in which the Shopping Centre is located, and the parties hereto exclusively attorn to the jurisdiction of such courts.

    # 13.

    Wherever in this Indemnity reference is made to either the Landlord or the Tenant, the reference is deemed to apply also to the respective heirs, executors, administrators, successors and assigns and permitted assigns, respectively, of the Landlord and the Tenant, as the case may be, named in the Lease. Any assignment by the Landlord or any of its interests in the Lease operates automatically as an assignment to such assignee of the benefit of this Indemnity.

    The parties hereto have executed this Indemnity as of the day and year first above written.

    PLATFORM PROPERTIES (MAPLE RIDGE) LTD.

    By:
    Authorized Signatory

    IN WITNESS WHEREOF, the Indemnifier has signed and sealed this Indemnity.

    Harpreet Bahia   Witness

    Name:

    Address:

    Jatinder Badyal   Witness

    Name:

    INITIAL
    Landlord   Tenant

    MR – July 2020




    """

    print("Extracting metadata from dummy text...")
    try:
        extractor = LeaseExtractor()
        data = extractor.extract(dummy_lease_text)
        
        # Print the result
        print(json.dumps(data.model_dump(mode='json'), indent=2))
        print("\nCalculation Test:")
        print(f"Average Rent PSF: {data.calculate_average_rent_psf()}") # Expected 0.0 for this dummy text as no PSF schedule
        
    except Exception as e:
        print(f"\nExtraction failed: {e}")