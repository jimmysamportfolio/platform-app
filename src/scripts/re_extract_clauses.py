"""
Re-extract clause summaries for existing parsed documents.

This script reads the already-parsed markdown files and runs the ClauseExtractor
with the new shorter summary prompt, then updates the database.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingestion.extractor import ClauseExtractor
from utils.db import insert_clauses, get_all_leases, init_db


def re_extract_clauses():
    """Re-extract clauses for all existing leases."""
    # Initialize database (ensures clauses table exists)
    init_db()
    
    # Get all leases
    leases = get_all_leases()
    print(f"Found {len(leases)} leases to process\n")
    
    if not leases:
        print("No leases found in database.")
        return
    
    # Initialize extractor
    extractor = ClauseExtractor()
    
    # Process each lease
    for lease in leases:
        document_name = lease.get("document_name", "")
        tenant_name = lease.get("tenant_name", "Unknown")
        lease_id = lease.get("id")
        
        print(f"Processing: {tenant_name}")
        print(f"  Document: {document_name}")
        
        # Find the parsed markdown file
        parsed_dir = Path("data/parsed")
        
        # Try different matching strategies
        md_file = None
        
        # Direct match with .md extension
        base_name = document_name.rsplit(".", 1)[0] if "." in document_name else document_name
        potential_paths = [
            parsed_dir / f"{base_name}.md",
            parsed_dir / f"{document_name}.md",
        ]
        
        for path in potential_paths:
            if path.exists():
                md_file = path
                break
        
        # If not found, try glob matching
        if not md_file:
            matches = list(parsed_dir.glob(f"*{base_name[:30]}*.md"))
            if matches:
                md_file = matches[0]
        
        if not md_file or not md_file.exists():
            print(f"  ⚠️ Parsed file not found, skipping")
            continue
        
        # Read the markdown content
        try:
            text = md_file.read_text(encoding="utf-8")
            print(f"  Read {len(text)} characters")
        except Exception as e:
            print(f"  ❌ Error reading file: {e}")
            continue
        
        # Extract clauses
        try:
            clauses = extractor.extract_clauses(text)
            print(f"  Extracted {len(clauses)} clauses")
            
            if clauses:
                num_inserted = insert_clauses(lease_id, clauses)
                print(f"  ✅ Saved {num_inserted} clauses to database")
            else:
                print(f"  ⚠️ No clauses extracted")
                
        except Exception as e:
            print(f"  ❌ Extraction error: {e}")
        
        print()
    
    print("Done!")


if __name__ == "__main__":
    re_extract_clauses()
