"""
Analytics Handler Module

Handles structured data queries against SQLite database.
This module is responsible for:
- Querying the leases database
- Returning structured data directly (NO LLM calls)
- Answering aggregate/calculation questions
- Looking up specific values (deposit amounts, rent, dates)
"""

import os
import sys
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from utils.db import get_connection, get_all_leases, get_lease_by_tenant, get_rent_schedule, DEFAULT_DB_PATH

load_dotenv()


@dataclass
class AnalyticsResult:
    """Structured result from analytics queries."""
    success: bool
    answer: str
    data: Optional[Dict[str, Any]] = None
    query_type: str = "general"


class AnalyticsHandler:
    """
    Handles analytics queries using structured data from SQLite database.
    
    **NO LLM CALLS** - Returns structured data directly for fast, rate-limit-free responses.
    """
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        """
        Initialize the analytics handler.
        
        Args:
            db_path: Path to SQLite database.
        """
        self.db_path = db_path
        leases = get_all_leases(db_path)
        print(f"✅ AnalyticsHandler initialized ({len(leases)} leases loaded)")
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for matching (handle different apostrophe types, etc.)."""
        if not text:
            return ""
        # 1. Lowercase first
        text = text.lower()
        # 2. Normalize apostrophes (handle all unicode variants)
        text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u0060", "'").replace("’", "'").replace("‘", "'")
        # 3. Replace newlines and tabs with space
        text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
        # 4. Collapse multiple spaces -> single space
        text = " ".join(text.split())
        return text.strip()
    
    def get_all_leases(self) -> List[Dict[str, Any]]:
        """Get all lease documents."""
        return get_all_leases(self.db_path)
    
    def get_lease_by_tenant(self, tenant_name: str) -> Optional[Dict[str, Any]]:
        """
        Find a lease by tenant name (partial match).
        
        Args:
            tenant_name: Full or partial tenant name or trade name.
            
        Returns:
            Lease data dict or None if not found.
        """
        # Delegate to db specific word-set implementation
        # Note: We duplicate logic here if we want memory-only filtering, 
        # but db.py handles the actual logic now.
        return get_lease_by_tenant(tenant_name, self.db_path)
    
    # --- Direct Value Lookups (No LLM) ---
    
    def get_deposit_amount(self, tenant_name: str) -> AnalyticsResult:
        """Get security deposit for a specific tenant."""
        lease = self.get_lease_by_tenant(tenant_name)
        if lease:
            deposit = lease.get("deposit_amount")
            if deposit:
                return AnalyticsResult(
                    success=True,
                    answer=f"The security deposit for {lease.get('tenant_name')} ({lease.get('trade_name', 'N/A')}) is **${deposit:,.2f}**.",
                    data={"tenant": lease.get("tenant_name"), "deposit_amount": deposit},
                    query_type="deposit"
                )
        return AnalyticsResult(success=False, answer=f"Could not find deposit amount for '{tenant_name}'.")
    
    def get_term(self, tenant_name: str) -> AnalyticsResult:
        """Get lease term for a specific tenant."""
        lease = self.get_lease_by_tenant(tenant_name)
        if lease:
            term = lease.get("term_years")
            if term:
                return AnalyticsResult(
                    success=True,
                    answer=f"The lease term for {lease.get('tenant_name')} is **{term} years**.",
                    data={"tenant": lease.get("tenant_name"), "term_years": term},
                    query_type="term"
                )
        return AnalyticsResult(success=False, answer=f"Could not find lease term for '{tenant_name}'.")
    
    def get_expiration(self, tenant_name: str) -> AnalyticsResult:
        """Get lease expiration date for a specific tenant."""
        lease = self.get_lease_by_tenant(tenant_name)
        if lease:
            exp = lease.get("lease_end")
            if exp:
                return AnalyticsResult(
                    success=True,
                    answer=f"The lease for {lease.get('tenant_name')} expires on **{exp}**.",
                    data={"tenant": lease.get("tenant_name"), "expiration_date": exp},
                    query_type="expiration"
                )
        return AnalyticsResult(success=False, answer=f"Could not find expiration date for '{tenant_name}'.")
    
    def get_generic_field(self, tenant_name: str, field: str) -> AnalyticsResult:
        """Get any specific field from the lease record."""
        lease = self.get_lease_by_tenant(tenant_name)
        if lease:
            value = lease.get(field)
            if value is not None:
                # Format dates and money if possible
                display_value = str(value)
                if isinstance(value, float) and "sqft" in field:
                    display_value = f"{value:,.0f} sqft"
                elif isinstance(value, float): # assume money for other floats
                    display_value = f"${value:,.2f}"
                
                return AnalyticsResult(
                    success=True,
                    answer=f"The {field.replace('_', ' ')} for {lease.get('tenant_name')} is **{display_value}**.",
                    data={"tenant": lease.get("tenant_name"), field: value},
                    query_type="field_lookup"
                )
        return AnalyticsResult(success=False, answer=f"Could not find {field} for '{tenant_name}'.")

    def get_rent_schedule(self, tenant_name: str) -> AnalyticsResult:
        """Get rent schedule for a specific tenant."""
        lease = self.get_lease_by_tenant(tenant_name)
        if lease:
            schedule = get_rent_schedule(lease["id"], self.db_path)
            if schedule:
                lines = [f"**Rent Schedule for {lease.get('tenant_name')}:**"]
                for step in schedule:
                    lines.append(f"- Years {int(step['start_year'])}-{int(step['end_year'])}: ${step['rate_psf']:.2f}/sqft (${step.get('monthly_rent', 0):,.2f}/month)")
                return AnalyticsResult(
                    success=True,
                    answer="\n".join(lines),
                    data={"tenant": lease.get("tenant_name"), "rent_schedule": schedule},
                    query_type="rent"
                )
        return AnalyticsResult(success=False, answer=f"Could not find rent schedule for '{tenant_name}'.")
    
    # --- Aggregate Calculations ---
    
    def get_total_deposit(self) -> AnalyticsResult:
        """Calculate total security deposits across all leases."""
        leases = self.get_all_leases()
        total = 0.0
        count = 0
        for lease in leases:
            deposit = lease.get("deposit_amount", 0) or 0
            if deposit:
                total += deposit
                count += 1
        
        return AnalyticsResult(
            success=True,
            answer=f"The total security deposits across all {count} leases is **${total:,.2f}**.",
            data={"total": total, "lease_count": count},
            query_type="aggregate"
        )
    
    def get_average_rent_psf(self) -> AnalyticsResult:
        """Calculate average rent per square foot (Year 1)."""
        leases = self.get_all_leases()
        rents = []
        for lease in leases:
            schedule = get_rent_schedule(lease["id"], self.db_path)
            if schedule:
                rents.append({"tenant": lease.get("tenant_name"), "rate": schedule[0].get("rate_psf", 0)})
        
        if rents:
            avg = sum(r["rate"] for r in rents) / len(rents)
            return AnalyticsResult(
                success=True,
                answer=f"The average Year 1 rent across {len(rents)} leases is **${avg:.2f}/sqft**.",
                data={"average": avg, "leases": rents},
                query_type="aggregate"
            )
        return AnalyticsResult(success=False, answer="No rent data available.")
    
    def count_leases(self) -> int:
        """Count total number of leases."""
        return len(self.get_all_leases())
    
    def get_portfolio_summary(self) -> AnalyticsResult:
        """Get a summary of the entire portfolio."""
        leases = self.get_all_leases()
        if not leases:
            return AnalyticsResult(success=False, answer="No leases in portfolio.")
        
        total_deposit = sum(l.get("deposit_amount", 0) or 0 for l in leases)
        tenants = [l.get("trade_name") or l.get("tenant_name") for l in leases]
        
        lines = [
            f"**Portfolio Summary ({len(leases)} leases):**",
            f"- Tenants: {', '.join(str(t) for t in tenants)}",
            f"- Total Deposits: ${total_deposit:,.2f}",
        ]
        
        return AnalyticsResult(
            success=True,
            answer="\n".join(lines),
            data={"lease_count": len(leases), "tenants": tenants, "total_deposit": total_deposit},
            query_type="summary"
        )


# --- Test Block ---
if __name__ == "__main__":
    handler = AnalyticsHandler()
    
    print("\n--- Direct Lookups (No LLM) ---")
    
    # Test deposit lookup
    result = handler.get_deposit_amount("Church")
    print(f"\n{result.answer}")
    
    result = handler.get_deposit_amount("Sran")
    print(f"\n{result.answer}")
    
    # Test term lookup
    result = handler.get_term("Church")
    print(f"\n{result.answer}")
    
    # Test expiration
    result = handler.get_expiration("Sran")
    print(f"\n{result.answer}")
    
    # Test rent schedule
    result = handler.get_rent_schedule("Church")
    print(f"\n{result.answer}")
    
    # Test aggregates
    print("\n--- Aggregates ---")
    result = handler.get_total_deposit()
    print(f"\n{result.answer}")
    
    result = handler.get_average_rent_psf()
    print(f"\n{result.answer}")
    
    result = handler.get_portfolio_summary()
    print(f"\n{result.answer}")
