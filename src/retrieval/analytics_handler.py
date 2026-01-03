"""
Analytics Handler Module

Handles structured data queries against metadata_store.json
This module is responsible for:
- Loading and querying the metadata store
- Returning structured data directly (NO LLM calls)
- Answering aggregate/calculation questions
- Looking up specific values (deposit amounts, rent, dates)
"""

import os
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass

from dotenv import load_dotenv

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
    Handles analytics queries using structured data from metadata_store.json.
    
    **NO LLM CALLS** - Returns structured data directly for fast, rate-limit-free responses.
    """
    
    DEFAULT_METADATA_PATH = "data/metadata_store.json"
    
    def __init__(self, metadata_path: str = DEFAULT_METADATA_PATH):
        """
        Initialize the analytics handler.
        
        Args:
            metadata_path: Path to metadata_store.json.
        """
        self.metadata_path = Path(metadata_path)
        self.metadata = self._load_metadata()
        
        print(f"✅ AnalyticsHandler initialized ({len(self.get_all_leases())} leases loaded)")
    
    def _load_metadata(self) -> Dict:
        """Load metadata from JSON file."""
        if not self.metadata_path.exists():
            print(f"⚠️ Metadata file not found: {self.metadata_path}")
            return {"documents": {}}
        
        with open(self.metadata_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def reload_metadata(self):
        """Reload metadata from disk."""
        self.metadata = self._load_metadata()
    
    def get_all_leases(self) -> Dict[str, Dict]:
        """Get all lease documents."""
        return self.metadata.get("documents", {})
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for matching (handle different apostrophe types, etc.)."""
        if not text:
            return ""
        # Normalize different apostrophe types to standard straight quote
        # \u2019 = right single quote (curly)
        # \u2018 = left single quote (curly)
        # \u0060 = backtick
        text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u0060", "'")
        return text.lower().strip()
    
    def get_lease_by_tenant(self, tenant_name: str) -> Optional[Dict]:
        """
        Find a lease by tenant name (partial match).
        
        Args:
            tenant_name: Full or partial tenant name or trade name.
            
        Returns:
            Lease data dict or None if not found.
        """
        search_term = self._normalize_text(tenant_name)
        
        for doc_name, lease in self.get_all_leases().items():
            # Check tenant name
            tenant = self._normalize_text(lease.get("tenant_name", ""))
            if search_term in tenant:
                return {"document": doc_name, **lease}
            
            # Check trade name (e.g., "Church's Chicken")
            trade = self._normalize_text(lease.get("trade_name", ""))
            if trade and search_term in trade:
                return {"document": doc_name, **lease}
        
        return None
    
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
            exp = lease.get("expiration_date")
            if exp:
                return AnalyticsResult(
                    success=True,
                    answer=f"The lease for {lease.get('tenant_name')} expires on **{exp}**.",
                    data={"tenant": lease.get("tenant_name"), "expiration_date": exp},
                    query_type="expiration"
                )
        return AnalyticsResult(success=False, answer=f"Could not find expiration date for '{tenant_name}'.")
    
    def get_rent_schedule(self, tenant_name: str) -> AnalyticsResult:
        """Get rent schedule for a specific tenant."""
        lease = self.get_lease_by_tenant(tenant_name)
        if lease:
            schedule = lease.get("basic_rent_schedule", [])
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
        total = 0.0
        count = 0
        for lease in self.get_all_leases().values():
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
        rents = []
        for doc, lease in self.get_all_leases().items():
            schedule = lease.get("basic_rent_schedule", [])
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
        
        total_deposit = sum(l.get("deposit_amount", 0) or 0 for l in leases.values())
        tenants = [l.get("trade_name") or l.get("tenant_name") for l in leases.values()]
        
        lines = [
            f"**Portfolio Summary ({len(leases)} leases):**",
            f"- Tenants: {', '.join(tenants)}",
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
    result = handler.get_deposit_amount("Church's Chicken")
    print(f"\n{result.answer}")
    
    result = handler.get_deposit_amount("H. Sran")
    print(f"\n{result.answer}")
    
    # Test term lookup
    result = handler.get_term("Church")
    print(f"\n{result.answer}")
    
    # Test expiration
    result = handler.get_expiration("Sran")
    print(f"\n{result.answer}")
    
    # Test aggregates
    print("\n--- Aggregates ---")
    result = handler.get_total_deposit()
    print(f"\n{result.answer}")
    
    result = handler.get_average_rent_psf()
    print(f"\n{result.answer}")
    
    result = handler.get_portfolio_summary()
    print(f"\n{result.answer}")
