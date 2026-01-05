"""
Ingestion Pipeline Orchestrator

Orchestrates the full document ingestion flow.
This module is responsible for:
- Coordinating parser -> chunker -> enricher -> extractor flow
- Managing batch processing of multiple documents
- Handling errors and retries during ingestion
- Updating the metadata store with extracted insights
- Pushing enriched chunks to the vector store
"""

import os
import sys
import json
import time
import asyncio
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

# Add src to path for direct execution
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from pinecone import Pinecone
from langchain_google_genai import GoogleGenerativeAIEmbeddings

# Import internal modules
from ingestion.parser import DocumentParser
from ingestion.chunker import DocumentChunker, Chunk
from ingestion.enricher import get_enricher, EnrichedChunk
from ingestion.extractor import LeaseExtractor, Lease, ClauseExtractor
from utils.db import init_db, insert_lease, insert_clauses
from config.settings import (
    VECTOR_NAMESPACE,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DELAY_SECONDS,
    ENRICHMENT_BATCH_SIZE,
    ENRICHMENT_DELAY_SECONDS,
    DEFAULT_EMBEDDING_MODEL,
    METADATA_STORE_PATH,
)

load_dotenv()


@dataclass
class PipelineConfig:
    """Configuration for the ingestion pipeline."""
    # Enrichment settings
    enable_enrichment: bool = True
    enrichment_batch_size: int = ENRICHMENT_BATCH_SIZE
    enrichment_delay_seconds: float = ENRICHMENT_DELAY_SECONDS
    
    # Embedding settings
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_batch_size: int = EMBEDDING_BATCH_SIZE
    embedding_delay_seconds: float = EMBEDDING_DELAY_SECONDS
    
    # Pinecone settings
    pinecone_namespace: str = VECTOR_NAMESPACE
    
    # Output settings
    metadata_store_path: str = METADATA_STORE_PATH


@dataclass
class PipelineResult:
    """Result of a pipeline run."""
    document_name: str
    success: bool
    chunks_processed: int
    vectors_uploaded: int
    lease_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    processing_time_seconds: float = 0.0


class IngestionPipeline:
    """
    Complete ingestion pipeline for legal documents.
    
    Flow: Parse -> Chunk -> Enrich (optional) -> Extract Metadata -> Embed -> Index
    """
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        """
        Initialize the ingestion pipeline.
        
        Args:
            config: Pipeline configuration. Uses defaults if not provided.
        """
        self.config = config or PipelineConfig()
        
        # Validate environment variables
        self._validate_env_vars()
        
        # Initialize components
        self.parser = DocumentParser()
        self.chunker = DocumentChunker()
        
        # Get enricher based on ENRICHMENT_MODE in settings.py
        # Options: 'llm' (expensive), 'rule-based' (free), 'none' (skip)
        self.enricher = get_enricher()
        
        self.extractor = LeaseExtractor()
        
        # Initialize embeddings
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model=self.config.embedding_model,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )
        
        # Initialize Pinecone
        self.pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        self.index = self.pc.Index(os.getenv("PINECONE_INDEX_NAME"))
        
        print(f"✅ Pipeline initialized with config:")
        enricher_type = type(self.enricher).__name__ if self.enricher else "None"
        print(f"   Enrichment: {enricher_type}")
        print(f"   Namespace: {self.config.pinecone_namespace}")
    
    def _validate_env_vars(self):
        """Validate required environment variables are set."""
        required = ["GOOGLE_API_KEY", "PINECONE_API_KEY", "PINECONE_INDEX_NAME", "LLAMA_CLOUD_API_KEY"]
        missing = [var for var in required if not os.getenv(var)]
        if missing:
            raise ValueError(f"Missing environment variables: {', '.join(missing)}")
    
    def _load_metadata_store(self) -> Dict:
        """Load existing metadata store or create empty one."""
        path = Path(self.config.metadata_store_path)
        default_store = {"documents": {}, "last_updated": None}
        
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    store = json.load(f)
                # Ensure required keys exist
                if "documents" not in store:
                    store["documents"] = {}
                return store
            except (json.JSONDecodeError, Exception):
                return default_store
        return default_store
    
    def _save_metadata_store(self, store: Dict):
        """Save metadata store to disk."""
        path = Path(self.config.metadata_store_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        store["last_updated"] = datetime.now().isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2, default=str)
        print(f"📁 Metadata saved to {self.config.metadata_store_path}")
    
    def _prepare_vector_metadata(
        self,
        chunk: EnrichedChunk,
        lease: Lease,
        document_name: str,
    ) -> Dict[str, Any]:
        """Prepare metadata to attach to each vector."""
        return {
            # Source reference
            "document": document_name,
            "chunk_index": chunk.chunk_index,
            "source_section": chunk.source_section,
            "source_reference": chunk.source_reference,
            
            # Enrichment data
            "clause_type": chunk.clause_type,
            "semantic_tags": chunk.semantic_tags,
            "contextual_summary": chunk.contextual_summary[:500] if chunk.contextual_summary else "",
            
            # Lease metadata (attached to every vector for filtering)
            "tenant_name": lease.tenant_name,
            "landlord_name": lease.landlord_name,
            "property_address": lease.property_address or "",
            "trade_name": lease.trade_name or "",
            "term_years": lease.term_years,
            
            # For text display in retrieval
            "text": chunk.content[:1000],  # Pinecone metadata limit
        }
    
    def run(
        self,
        file_path: str,
        output_markdown_path: Optional[str] = None,
    ) -> PipelineResult:
        """
        Run the full ingestion pipeline on a single document.
        
        Args:
            file_path: Path to the input document (PDF or DOCX).
            output_markdown_path: Optional path to save parsed markdown.
            
        Returns:
            PipelineResult with processing details.
        """
        start_time = time.time()
        document_name = os.path.basename(file_path)
        
        print(f"\n{'='*60}")
        print(f"🚀 Starting ingestion: {document_name}")
        print(f"{'='*60}")
        
        try:
            # Step 1: Parse document
            print("\n📄 Step 1/6: Parsing document...")
            if not output_markdown_path:
                output_markdown_path = f"data/parsed/{Path(file_path).stem}.md"
            
            documents = self.parser.parse_file(file_path, output_markdown_path)
            
            # Get full text
            full_text = "\n\n".join(doc.text for doc in documents if hasattr(doc, 'text'))
            print(f"   Parsed {len(full_text):,} characters")
            
            # Step 2: Chunk document
            print("\n✂️  Step 2/6: Chunking document...")
            chunks = self.chunker.chunk(full_text)
            print(f"   Created {len(chunks)} chunks")
            
            # Step 3: Extract structured data
            print("\n🔍 Step 3/6: Extracting lease metadata...")
            # Use more text to include Schedules (Gemini 2.5 Flash has 1M token context)
            lease = self.extractor.extract(full_text[:150000])
            print(f"   Tenant: {lease.tenant_name}")
            print(f"   Landlord: {lease.landlord_name}")
            print(f"   Term: {lease.term_years} years")
            
            # Step 4: Enrich chunks (optional)
            if self.config.enable_enrichment:
                print(f"\n🏷️  Step 4/6: Enriching chunks (batch_size={self.config.enrichment_batch_size})...")
                print(f"   ⏱️  Estimated time: {len(chunks) // self.config.enrichment_batch_size * self.config.enrichment_delay_seconds:.0f}s")
                enriched_chunks = self.enricher.enrich_chunks(chunks, source_document=document_name)
            else:
                print("\n🏷️  Step 4/6: Skipping enrichment (disabled)")
                # Create basic EnrichedChunk objects without LLM enrichment
                enriched_chunks = [
                    EnrichedChunk(
                        content=c.content,
                        original_metadata=c.metadata,
                        token_count=c.token_count,
                        chunk_index=i,
                        source_document=document_name,
                        source_section=c.metadata.get("article", "") or c.metadata.get("section", ""),
                    )
                    for i, c in enumerate(chunks)
                ]
            
            # Step 5: Generate embeddings
            print("\n🧠 Step 5/6: Generating embeddings...")
            texts_to_embed = [c.enriched_content for c in enriched_chunks]
            
            # Batch embed with rate limiting and error handling
            all_embeddings = []
            failed_embedding_indices = []
            
            for i in range(0, len(texts_to_embed), self.config.embedding_batch_size):
                batch = texts_to_embed[i:i + self.config.embedding_batch_size]
                batch_indices = list(range(i, min(i + self.config.embedding_batch_size, len(texts_to_embed))))
                
                # Retry logic for embedding API calls
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        batch_embeddings = self.embeddings.embed_documents(batch)
                        all_embeddings.extend(batch_embeddings)
                        print(f"   Embedded {min(i + self.config.embedding_batch_size, len(texts_to_embed))}/{len(texts_to_embed)}")
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            print(f"   Warning: Embedding batch failed (attempt {attempt + 1}/{max_retries}): {e}")
                            time.sleep(2 ** attempt)  # Exponential backoff
                        else:
                            print(f"   ERROR: Embedding batch {i//self.config.embedding_batch_size + 1} failed permanently: {e}")
                            # Add placeholder embeddings to maintain index alignment
                            placeholder = [0.0] * 768  # Standard embedding dimension
                            all_embeddings.extend([placeholder] * len(batch))
                            failed_embedding_indices.extend(batch_indices)
                
                if i + self.config.embedding_batch_size < len(texts_to_embed):
                    time.sleep(self.config.embedding_delay_seconds)
            
            if failed_embedding_indices:
                print(f"\n   WARNING: {len(failed_embedding_indices)} chunks failed embedding and will have placeholder vectors!")
            
            # Step 6: Upload to Pinecone
            print("\n📤 Step 6/6: Uploading to Pinecone...")
            vectors_to_upsert = []
            
            for i, (chunk, embedding) in enumerate(zip(enriched_chunks, all_embeddings)):
                vector_id = f"{Path(file_path).stem}_chunk_{i}"
                metadata = self._prepare_vector_metadata(chunk, lease, document_name)
                
                vectors_to_upsert.append({
                    "id": vector_id,
                    "values": embedding,
                    "metadata": metadata,
                })
            
            # Batch upsert to Pinecone with error handling
            batch_size = 100
            failed_vectors = []
            
            for i in range(0, len(vectors_to_upsert), batch_size):
                batch = vectors_to_upsert[i:i + batch_size]
                batch_ids = [v["id"] for v in batch]
                
                # Retry logic for resilience
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        self.index.upsert(
                            vectors=batch,
                            namespace=self.config.pinecone_namespace,
                        )
                        print(f"   Uploaded {min(i + batch_size, len(vectors_to_upsert))}/{len(vectors_to_upsert)} vectors")
                        break  # Success, exit retry loop
                    except Exception as e:
                        if attempt < max_retries - 1:
                            print(f"   Warning: Batch {i//batch_size + 1} failed (attempt {attempt + 1}/{max_retries}): {e}")
                            time.sleep(2 ** attempt)  # Exponential backoff
                        else:
                            print(f"   ERROR: Batch {i//batch_size + 1} failed permanently after {max_retries} attempts: {e}")
                            failed_vectors.extend(batch_ids)
            
            # Report any failed uploads
            if failed_vectors:
                print(f"\n   WARNING: {len(failed_vectors)} vectors failed to upload!")
                print(f"   Failed IDs: {failed_vectors[:5]}{'...' if len(failed_vectors) > 5 else ''}")
            
            # Save lease metadata to SQLite database
            print("\n💾 Saving metadata to database...")
            lease_id = insert_lease(lease.model_dump(mode="json"), document_name)
            print(f"📁 Lease saved to database (ID: {lease_id})")
            
            # Step 7: Extract clauses for comparison tool
            print("\n📋 Step 7/7: Extracting clause summaries...")
            try:
                clause_extractor = ClauseExtractor()
                clauses = clause_extractor.extract_clauses(full_text)
                if clauses:
                    num_clauses = insert_clauses(lease_id, clauses)
                    print(f"   Extracted {num_clauses} clause summaries")
                else:
                    print("   No clauses extracted")
            except Exception as clause_err:
                print(f"   ⚠️ Clause extraction failed (non-fatal): {clause_err}")
            
            processing_time = time.time() - start_time
            
            print(f"\n{'='*60}")
            print(f"✅ Ingestion complete: {document_name}")
            print(f"   Chunks: {len(chunks)}")
            print(f"   Vectors: {len(vectors_to_upsert)}")
            print(f"   Time: {processing_time:.1f}s")
            print(f"{'='*60}")
            
            return PipelineResult(
                document_name=document_name,
                success=True,
                chunks_processed=len(chunks),
                vectors_uploaded=len(vectors_to_upsert),
                lease_data=lease.model_dump(mode="json"),
                processing_time_seconds=processing_time,
            )
            
        except Exception as e:
            processing_time = time.time() - start_time
            print(f"\n❌ Error: {e}")
            return PipelineResult(
                document_name=document_name,
                success=False,
                chunks_processed=0,
                vectors_uploaded=0,
                error_message=str(e),
                processing_time_seconds=processing_time,
            )
    
    def run_batch(self, file_paths: List[str]) -> List[PipelineResult]:
        """
        Process multiple documents sequentially.
        
        Args:
            file_paths: List of paths to documents.
            
        Returns:
            List of PipelineResult objects.
        """
        results = []
        total = len(file_paths)
        
        for i, file_path in enumerate(file_paths, 1):
            print(f"\n📁 Processing document {i}/{total}")
            result = self.run(file_path)
            results.append(result)
        
        # Summary
        successful = sum(1 for r in results if r.success)
        print(f"\n{'='*60}")
        print(f"📊 Batch Complete: {successful}/{total} successful")
        print(f"{'='*60}")
        
        return results


# --- Test Block ---
if __name__ == "__main__":
    import sys
    sys.path.insert(0, "src")
    
    # Use existing parsed markdown for faster testing
    test_markdown = "data/test_outputs/output.md"
    test_pdf = "data/raw_pdfs/Lease Draft #4 (final) - Church's Chicken, 11939 240 Street, MR - Jul 13, 2020.docx"
    
    # Configure pipeline (disable enrichment for faster testing)
    config = PipelineConfig(
        enable_enrichment=False,  # Set to True for full enrichment
        pinecone_namespace="leases-test",
    )
    
    try:
        pipeline = IngestionPipeline(config)
        
        # Run on test document
        if os.path.exists(test_pdf):
            result = pipeline.run(test_pdf)
            print(f"\nResult: {'SUCCESS' if result.success else 'FAILED'}")
            if result.lease_data:
                print(f"Tenant: {result.lease_data.get('tenant_name')}")
        else:
            print(f"Test file not found: {test_pdf}")
            print("Please provide a valid document path.")
            
    except Exception as e:
        print(f"Pipeline initialization failed: {e}")