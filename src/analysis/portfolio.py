"""
Portfolio Analytics Module

Provides deterministic, LLM-free analytics for the Portfolio Dashboard.
This module is responsible for:
- Calculating aggregate statistics across all leases
- Identifying leases expiring soon
- Computing rent metrics by building/property
- Returning structured data for frontend consumption
"""

import os
import sys
from typing import Dict, Any, List, Optional
from datetime import date, datetime, timedelta

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.db import get_connection, DEFAULT_DB_PATH


class PortfolioAnalyzer:
    """
    Portfolio analytics engine for the Legal RAG dashboard.
    
    Provides hard-coded, deterministic statistics without LLM calls.
    All data is fetched directly from the SQLite database.
    """
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        """
        Initialize the portfolio analyzer.
        
        Args:
            db_path: Path to the SQLite database.
        """
        self.db_path = db_path
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """
        Get a comprehensive portfolio summary for the dashboard.
        
        Returns:
            Dictionary containing all portfolio analytics:
            - total_leases: int
            - total_sqft: float
            - total_deposits: float
            - average_rent_psf: float
            - average_term_years: float
            - leases_expiring_soon: list (next 12 months)
            - rent_by_property: list
            - occupancy_summary: dict
        """
        return {
            "generated_at": datetime.now().isoformat(),
            "total_leases": self._get_total_leases(),
            "total_sqft": self._get_total_sqft(),
            "total_deposits": self._get_total_deposits(),
            "average_rent_psf": self._get_average_rent_psf(),
            "average_term_years": self._get_average_term(),
            "leases_expiring_soon": self._get_expiring_leases(months=12),
            "rent_by_property": self._get_rent_by_property(),
            "lease_breakdown": self._get_lease_breakdown(),
        }
    
    def _get_total_leases(self) -> int:
        """Get total number of active leases."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM leases")
            row = cursor.fetchone()
            return row["count"] if row else 0
    
    def _get_total_sqft(self) -> float:
        """Get total rentable square footage."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT SUM(rentable_area_sqft) as total FROM leases")
            row = cursor.fetchone()
            return row["total"] or 0.0
    
    def _get_total_deposits(self) -> float:
        """Get total security deposits held."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT SUM(deposit_amount) as total FROM leases")
            row = cursor.fetchone()
            return row["total"] or 0.0
    
    def _get_average_rent_psf(self) -> float:
        """Get average rent per square foot (Year 1)."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT AVG(rs.rate_psf) as avg_rate
                FROM rent_schedule rs
                WHERE rs.start_year = 1
            """)
            row = cursor.fetchone()
            return round(row["avg_rate"] or 0.0, 2)
    
    def _get_average_term(self) -> float:
        """Get average lease term in years."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT AVG(term_years) as avg_term FROM leases")
            row = cursor.fetchone()
            return round(row["avg_term"] or 0.0, 1)
    
    def _get_expiring_leases(self, months: int = 12) -> List[Dict[str, Any]]:
        """
        Get leases expiring within the specified number of months.
        
        Args:
            months: Number of months to look ahead.
            
        Returns:
            List of leases ordered by expiration date (soonest first).
        """
        cutoff_date = (datetime.now() + timedelta(days=months * 30)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")
        
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    id,
                    tenant_name,
                    trade_name,
                    property_address,
                    lease_end,
                    deposit_amount,
                    rentable_area_sqft
                FROM leases
                WHERE lease_end IS NOT NULL 
                  AND lease_end >= ?
                  AND lease_end <= ?
                ORDER BY lease_end ASC
            """, (today, cutoff_date))
            
            rows = cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "tenant": row["tenant_name"],
                    "trade_name": row["trade_name"],
                    "property": row["property_address"],
                    "expires": row["lease_end"],
                    "days_remaining": self._days_until(row["lease_end"]),
                    "deposit": row["deposit_amount"],
                    "sqft": row["rentable_area_sqft"],
                }
                for row in rows
            ]
    
    def _days_until(self, date_str: str) -> int:
        """Calculate days until a date string."""
        if not date_str:
            return 0
        try:
            target = datetime.strptime(str(date_str), "%Y-%m-%d")
            return (target - datetime.now()).days
        except ValueError:
            return 0
    
    def _get_rent_by_property(self) -> List[Dict[str, Any]]:
        """
        Get average rent metrics grouped by property address.
        
        Returns:
            List of properties with rent statistics.
        """
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    l.property_address,
                    COUNT(*) as lease_count,
                    SUM(l.rentable_area_sqft) as total_sqft,
                    SUM(l.deposit_amount) as total_deposits,
                    AVG(rs.rate_psf) as avg_rent_psf
                FROM leases l
                LEFT JOIN rent_schedule rs ON l.id = rs.lease_id AND rs.start_year = 1
                GROUP BY l.property_address
                ORDER BY total_sqft DESC
            """)
            
            rows = cursor.fetchall()
            return [
                {
                    "address": row["property_address"] or "Unknown",
                    "lease_count": row["lease_count"],
                    "total_sqft": row["total_sqft"] or 0,
                    "total_deposits": row["total_deposits"] or 0,
                    "avg_rent_psf": round(row["avg_rent_psf"] or 0, 2),
                }
                for row in rows
            ]
    
    def _get_lease_breakdown(self) -> List[Dict[str, Any]]:
        """
        Get detailed breakdown of all leases.
        
        Returns:
            List of all leases with key metrics.
        """
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    l.id,
                    l.tenant_name,
                    l.trade_name,
                    l.property_address,
                    l.rentable_area_sqft,
                    l.lease_start,
                    l.lease_end,
                    l.term_years,
                    l.deposit_amount,
                    l.base_rent,
                    rs.rate_psf as year1_rate_psf
                FROM leases l
                LEFT JOIN rent_schedule rs ON l.id = rs.lease_id AND rs.start_year = 1
                ORDER BY l.tenant_name
            """)
            
            rows = cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "tenant": row["tenant_name"],
                    "trade_name": row["trade_name"],
                    "property": row["property_address"],
                    "sqft": row["rentable_area_sqft"],
                    "start_date": row["lease_start"],
                    "end_date": row["lease_end"],
                    "term_years": row["term_years"],
                    "deposit": row["deposit_amount"],
                    "base_rent": row["base_rent"],
                    "rate_psf": row["year1_rate_psf"],
                }
                for row in rows
            ]
    
    def get_expiration_calendar(self, years: int = 5) -> Dict[int, List[Dict]]:
        """
        Get leases grouped by expiration year.
        
        Args:
            years: Number of years to look ahead.
            
        Returns:
            Dictionary with years as keys and lists of expiring leases.
        """
        current_year = datetime.now().year
        result = {year: [] for year in range(current_year, current_year + years + 1)}
        
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    tenant_name,
                    trade_name,
                    lease_end,
                    deposit_amount,
                    rentable_area_sqft
                FROM leases
                WHERE lease_end IS NOT NULL
                ORDER BY lease_end
            """)
            
            for row in cursor.fetchall():
                try:
                    exp_year = int(str(row["lease_end"])[:4])
                    if exp_year in result:
                        result[exp_year].append({
                            "tenant": row["tenant_name"],
                            "trade_name": row["trade_name"],
                            "expires": row["lease_end"],
                            "deposit": row["deposit_amount"],
                            "sqft": row["rentable_area_sqft"],
                        })
                except (ValueError, TypeError):
                    pass
        
        return result


# --- Test Block ---
if __name__ == "__main__":
    import json
    
    analyzer = PortfolioAnalyzer()
    
    print("=" * 60)
    print("📊 PORTFOLIO ANALYTICS DASHBOARD")
    print("=" * 60)
    
    summary = analyzer.get_portfolio_summary()
    
    print(f"\n📈 Portfolio Metrics:")
    print(f"   Total Leases: {summary['total_leases']}")
    print(f"   Total SqFt: {summary['total_sqft']:,.0f}")
    print(f"   Total Deposits: ${summary['total_deposits']:,.2f}")
    print(f"   Avg Rent/SqFt: ${summary['average_rent_psf']:.2f}")
    print(f"   Avg Term: {summary['average_term_years']} years")
    
    print(f"\n🏢 Rent by Property:")
    for prop in summary['rent_by_property']:
        print(f"   {prop['address']}: {prop['lease_count']} leases, {prop['total_sqft']:,.0f} sqft, ${prop['avg_rent_psf']:.2f}/sqft")
    
    print(f"\n📋 Lease Breakdown:")
    for lease in summary['lease_breakdown']:
        print(f"   {lease['tenant']} ({lease['trade_name']}): {lease['sqft']:,.0f} sqft, ${lease['deposit']:,.2f} deposit")
    
    print(f"\n⏰ Expiring in next 12 months:")
    if summary['leases_expiring_soon']:
        for lease in summary['leases_expiring_soon']:
            print(f"   {lease['tenant']}: {lease['expires']} ({lease['days_remaining']} days)")
    else:
        print("   No leases expiring soon")
    
    print(f"\n📅 Expiration Calendar:")
    calendar = analyzer.get_expiration_calendar()
    for year, leases in calendar.items():
        if leases:
            print(f"   {year}: {len(leases)} lease(s) - {', '.join(l['tenant'] for l in leases)}")
    
    print("\n" + "=" * 60)
    print("✅ Portfolio analysis complete!")
    print("=" * 60)
