"""
Document Removal Utility

Utility to remove a document from both the vector store and SQL database.
"""

import os
import sys

# Add project root and src to path for imports
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from dotenv import load_dotenv
from config.settings import VECTOR_NAMESPACE, DEFAULT_DB_PATH

load_dotenv()


def remove_document(
    document_name: str,
    namespace: str = VECTOR_NAMESPACE,
    db_path: str = DEFAULT_DB_PATH,
    delete_vectors: bool = True,
    delete_lease: bool = True,
    delete_logs: bool = True,
) -> dict:
    """
    Remove a document from both the vector store and SQL database.
    
    Args:
        document_name: Name of the document to remove.
        namespace: Pinecone namespace to delete from.
        db_path: Path to SQLite database.
        delete_vectors: Whether to delete vectors from Pinecone.
        delete_lease: Whether to delete lease record from SQLite.
        delete_logs: Whether to delete ingestion logs.
        
    Returns:
        Dictionary with deletion results.
    """
    results = {
        "document_name": document_name,
        "vectors_deleted": 0,
        "lease_deleted": False,
        "logs_deleted": False,
    }
    
    # Delete from vector store
    if delete_vectors:
        from retrieval.vector_store import LeaseVectorStore
        try:
            store = LeaseVectorStore(namespace=namespace)
            results["vectors_deleted"] = store.delete_by_document(document_name)
        except Exception as e:
            print(f"⚠️ Could not delete vectors: {e}")
    
    # Delete from SQL database
    if delete_lease:
        from utils.db import delete_lease as db_delete_lease
        results["lease_deleted"] = db_delete_lease(document_name, db_path)
    
    # Delete ingestion logs
    if delete_logs:
        from utils.db import delete_ingestion_log
        results["logs_deleted"] = delete_ingestion_log(document_name, db_path)
    
    print(f"\n{'='*60}")
    print(f"📋 Removal Summary: {document_name}")
    print(f"{'='*60}")
    print(f"   Vectors deleted: {results['vectors_deleted']}")
    print(f"   Lease deleted: {results['lease_deleted']}")
    print(f"   Logs deleted: {results['logs_deleted']}")
    
    return results


# --- CLI Interface ---
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python remove_document.py <document_name>")
        print("Example: python remove_document.py 'Lease Draft #3.docx'")
        sys.exit(1)
    
    doc_name = sys.argv[1]
    print(f"\n🗑️  Removing document: {doc_name}")
    
    results = remove_document(doc_name)
    
    if results["vectors_deleted"] or results["lease_deleted"] or results["logs_deleted"]:
        print("\n✅ Removal complete!")
    else:
        print("\n⚠️ No records found for this document.")
