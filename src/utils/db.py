"""
Database Utility Module

SQLite database for storing structured lease metadata.
This module is responsible for:
- Creating and managing the leases table
- Inserting/updating lease data from Pydantic extractors
- Safe connection handling with context managers
"""

import sqlite3
from pathlib import Path
from typing import Dict, Any, Optional
from contextlib import contextmanager
from datetime import date

# Default database path
DEFAULT_DB_PATH = "data/leases.db"


@contextmanager
def get_connection(db_path: str = DEFAULT_DB_PATH):
    """
    Context manager for safe database connections.
    
    Args:
        db_path: Path to the SQLite database file.
        
    Yields:
        sqlite3.Connection with Row factory enabled.
    """
    # Ensure data directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Enable dict-like access
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """
    Initialize the database and create tables if they don't exist.
    
    Args:
        db_path: Path to the SQLite database file.
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_name TEXT UNIQUE,
                tenant_name TEXT NOT NULL,
                trade_name TEXT,
                landlord_name TEXT,
                property_address TEXT,
                premises_description TEXT,
                rentable_area_sqft REAL,
                lease_start DATE,
                lease_end DATE,
                term_years REAL,
                possession_date DATE,
                base_rent REAL,
                deposit_amount REAL,
                renewal_option TEXT,
                permitted_use TEXT,
                exclusive_use TEXT,
                radius_restriction TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create rent schedule table for normalized storage
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rent_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lease_id INTEGER NOT NULL,
                start_year REAL,
                end_year REAL,
                rate_psf REAL,
                monthly_rent REAL,
                annual_rent REAL,
                FOREIGN KEY (lease_id) REFERENCES leases (id) ON DELETE CASCADE
            )
        """)
        
        print(f"✅ Database initialized: {db_path}")


def insert_lease(data: Dict[str, Any], document_name: str, db_path: str = DEFAULT_DB_PATH) -> int:
    """
    Insert or update a lease record from Pydantic extractor data.
    
    Args:
        data: Dictionary from Pydantic Lease model (model_dump()).
        document_name: Name of the source document.
        db_path: Path to the SQLite database file.
        
    Returns:
        The ID of the inserted/updated lease.
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Extract first year's rent as base_rent
        base_rent = None
        rent_schedule = data.get("basic_rent_schedule", [])
        if rent_schedule and len(rent_schedule) > 0:
            base_rent = rent_schedule[0].get("annual_rent")
        
        # Check if lease already exists (upsert)
        cursor.execute("SELECT id FROM leases WHERE document_name = ?", (document_name,))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing lease
            lease_id = existing["id"]
            cursor.execute("""
                UPDATE leases SET
                    tenant_name = ?,
                    trade_name = ?,
                    landlord_name = ?,
                    property_address = ?,
                    premises_description = ?,
                    rentable_area_sqft = ?,
                    lease_start = ?,
                    lease_end = ?,
                    term_years = ?,
                    possession_date = ?,
                    base_rent = ?,
                    deposit_amount = ?,
                    renewal_option = ?,
                    permitted_use = ?,
                    exclusive_use = ?,
                    radius_restriction = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                data.get("tenant_name"),
                data.get("trade_name"),
                data.get("landlord_name"),
                data.get("property_address"),
                data.get("premises_description"),
                data.get("rentable_area_sqft"),
                data.get("commencement_date"),
                data.get("expiration_date"),
                data.get("term_years"),
                data.get("possession_date"),
                base_rent,
                data.get("deposit_amount"),
                data.get("renewal_options"),
                data.get("permitted_use"),
                data.get("exclusive_use"),
                data.get("radius_restriction"),
                lease_id,
            ))
            
            # Delete old rent schedule
            cursor.execute("DELETE FROM rent_schedule WHERE lease_id = ?", (lease_id,))
            
        else:
            # Insert new lease
            cursor.execute("""
                INSERT INTO leases (
                    document_name, tenant_name, trade_name, landlord_name,
                    property_address, premises_description, rentable_area_sqft,
                    lease_start, lease_end, term_years, possession_date,
                    base_rent, deposit_amount, renewal_option, permitted_use,
                    exclusive_use, radius_restriction
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                document_name,
                data.get("tenant_name"),
                data.get("trade_name"),
                data.get("landlord_name"),
                data.get("property_address"),
                data.get("premises_description"),
                data.get("rentable_area_sqft"),
                data.get("commencement_date"),
                data.get("expiration_date"),
                data.get("term_years"),
                data.get("possession_date"),
                base_rent,
                data.get("deposit_amount"),
                data.get("renewal_options"),
                data.get("permitted_use"),
                data.get("exclusive_use"),
                data.get("radius_restriction"),
            ))
            lease_id = cursor.lastrowid
        
        # Insert rent schedule
        for step in rent_schedule:
            cursor.execute("""
                INSERT INTO rent_schedule (
                    lease_id, start_year, end_year, rate_psf, monthly_rent, annual_rent
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                lease_id,
                step.get("start_year"),
                step.get("end_year"),
                step.get("rate_psf"),
                step.get("monthly_rent"),
                step.get("annual_rent"),
            ))
        
        return lease_id


def get_all_leases(db_path: str = DEFAULT_DB_PATH) -> list[Dict[str, Any]]:
    """
    Retrieve all leases from the database.
    
    Returns:
        List of lease dictionaries.
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leases ORDER BY tenant_name")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def _normalize_apostrophes(text: str) -> str:
    """Normalize different apostrophe types to standard straight quote."""
    if not text:
        return ""
    return text.replace("\u2019", "'").replace("\u2018", "'").replace("\u0060", "'")


def get_lease_by_tenant(tenant_name: str, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """
    Find a lease by tenant name (partial match).
    
    Args:
        tenant_name: Full or partial tenant name.
        
    Returns:
        Lease dictionary or None.
    """
    # Normalize the search term
    search = _normalize_apostrophes(tenant_name.lower())
    
    # Fetch all leases and filter in Python (handles Unicode apostrophes properly)
    leases = get_all_leases(db_path)
    
    for lease in leases:
        # Check tenant name
        tenant = _normalize_apostrophes((lease.get("tenant_name") or "").lower())
        if search in tenant:
            return lease
        
        # Check trade name
        trade = _normalize_apostrophes((lease.get("trade_name") or "").lower())
        if search in trade:
            return lease
    
    return None


def get_rent_schedule(lease_id: int, db_path: str = DEFAULT_DB_PATH) -> list[Dict[str, Any]]:
    """
    Get rent schedule for a specific lease.
    
    Args:
        lease_id: ID of the lease.
        
    Returns:
        List of rent schedule dictionaries.
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM rent_schedule 
            WHERE lease_id = ? 
            ORDER BY start_year
        """, (lease_id,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


# --- Test Block ---
if __name__ == "__main__":
    import json
    
    # Initialize database
    init_db()
    
    # Test with sample data from metadata_store.json
    metadata_path = Path("data/metadata_store.json")
    if metadata_path.exists():
        with open(metadata_path) as f:
            metadata = json.load(f)
        
        for doc_name, lease_data in metadata.get("documents", {}).items():
            lease_id = insert_lease(lease_data, doc_name)
            print(f"Inserted/Updated: {doc_name} (ID: {lease_id})")
    
    # Query all leases
    print("\n--- All Leases ---")
    leases = get_all_leases()
    for lease in leases:
        print(f"  {lease['tenant_name']} ({lease['trade_name']}) - ${lease['deposit_amount']:,.2f} deposit")
    
    # Query specific tenant
    print("\n--- Query by Tenant ---")
    church = get_lease_by_tenant("Church")
    if church:
        print(f"Found: {church['tenant_name']}")
        schedule = get_rent_schedule(church['id'])
        print(f"Rent Schedule: {len(schedule)} periods")
