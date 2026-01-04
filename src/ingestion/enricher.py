"""
Chunk Enricher Module - "Contextual Retrieval" Logic

Implements the "Sticky Note" generator for chunk enrichment.
This module is responsible for:
- Adding contextual summaries to each chunk
- Generating metadata annotations for improved retrieval
- Creating semantic tags for chunk categorization
- Enhancing chunks with parent document context
"""

import os
import sys
import asyncio
from typing import List, Optional
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Add project root to path for config imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# New google.genai SDK (replaces deprecated google.generativeai)
from google import genai

from config.settings import DEFAULT_LLM_MODEL, CLAUSE_TYPES
from config.prompts import ENRICHMENT_PROMPT

# Load environment variables
load_dotenv()


@dataclass
class EnrichedChunk:
    """Represents an enriched document chunk with contextual metadata and source references."""
    content: str
    original_metadata: dict = field(default_factory=dict)
    token_count: int = 0
    
    # Source reference fields (provenance tracking)
    chunk_index: int = 0                    # Position in the chunk sequence
    source_document: str = ""               # Original document filename
    source_section: str = ""                # Article/section reference from metadata
    char_start: int = 0                     # Character offset start in original document
    char_end: int = 0                       # Character offset end in original document
    page_numbers: List[int] = field(default_factory=list)  # Page numbers if available
    
    # Enrichment fields
    contextual_summary: str = ""
    semantic_tags: List[str] = field(default_factory=list)
    key_entities: List[str] = field(default_factory=list)
    clause_type: str = ""
    
    @property
    def source_reference(self) -> str:
        """Return a formatted source citation for the chunk."""
        parts = []
        if self.source_document:
            parts.append(self.source_document)
        if self.source_section:
            parts.append(f"§{self.source_section}")
        if self.page_numbers:
            pages = ", ".join(str(p) for p in self.page_numbers)
            parts.append(f"p.{pages}")
        parts.append(f"[Chunk {self.chunk_index + 1}]")
        return " • ".join(parts)
    
    @property
    def enriched_content(self) -> str:
        """Return content with contextual prefix for embedding."""
        if self.contextual_summary:
            return f"{self.contextual_summary}\n\n{self.content}"
        return self.content
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization/storage."""
        return {
            "content": self.content,
            "enriched_content": self.enriched_content,
            "token_count": self.token_count,
            "chunk_index": self.chunk_index,
            "source_document": self.source_document,
            "source_section": self.source_section,
            "source_reference": self.source_reference,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "page_numbers": self.page_numbers,
            "contextual_summary": self.contextual_summary,
            "semantic_tags": self.semantic_tags,
            "key_entities": self.key_entities,
            "clause_type": self.clause_type,
            "original_metadata": self.original_metadata,
        }


class ChunkEnricher:
    """
    Contextual chunk enricher using Gemini 2.5 Flash.
    
    Implements the "Contextual Retrieval" pattern where each chunk
    is enriched with a contextual summary that situates it within
    the broader document context, improving retrieval accuracy.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_LLM_MODEL,
        doc_title: str = "Commercial Lease Agreement",
        batch_size: int = 5,
        rate_limit_delay: float = 0.5,
    ):
        """
        Initialize the ChunkEnricher.
        
        Args:
            model_name: Gemini model to use for enrichment.
            doc_title: Title of the document being processed.
            batch_size: Number of chunks to process in parallel.
            rate_limit_delay: Delay between batches to avoid rate limits.
        """
        self.model_name = model_name
        self.doc_title = doc_title
        self.batch_size = batch_size
        self.rate_limit_delay = rate_limit_delay
        
        # Configure Gemini using new google.genai SDK
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")
        
        self.client = genai.Client(api_key=api_key)
    
    def _build_prompt(self, content: str, metadata: dict) -> str:
        """Build the enrichment prompt for a chunk."""
        metadata_str = "\n".join(f"  {k}: {v}" for k, v in metadata.items()) if metadata else "  None"
        
        return ENRICHMENT_PROMPT.format(
            doc_title=self.doc_title,
            chunk_metadata=metadata_str,
            chunk_content=content[:2000],  # Limit content to avoid token overflow
            clause_types=", ".join(CLAUSE_TYPES)
        )
    
    def _parse_response(self, response_text: str) -> dict:
        """Parse the structured response from Gemini."""
        result = {
            "contextual_summary": "",
            "semantic_tags": [],
            "key_entities": [],
            "clause_type": "other"
        }
        
        lines = response_text.strip().split("\n")
        for line in lines:
            line = line.strip()
            
            if line.startswith("CONTEXTUAL_SUMMARY:"):
                result["contextual_summary"] = line.replace("CONTEXTUAL_SUMMARY:", "").strip()
            
            elif line.startswith("SEMANTIC_TAGS:"):
                tags_str = line.replace("SEMANTIC_TAGS:", "").strip()
                # Parse [tag1, tag2] format
                tags_str = tags_str.strip("[]")
                result["semantic_tags"] = [t.strip() for t in tags_str.split(",") if t.strip()]
            
            elif line.startswith("KEY_ENTITIES:"):
                entities_str = line.replace("KEY_ENTITIES:", "").strip()
                entities_str = entities_str.strip("[]")
                result["key_entities"] = [e.strip() for e in entities_str.split(",") if e.strip()]
            
            elif line.startswith("CLAUSE_TYPE:"):
                clause = line.replace("CLAUSE_TYPE:", "").strip().lower()
                if clause in CLAUSE_TYPES:
                    result["clause_type"] = clause
        
        return result
    
    def enrich_chunk(
        self,
        content: str,
        metadata: dict,
        token_count: int,
        chunk_index: int = 0,
        source_document: str = "",
        char_start: int = 0,
        char_end: int = 0,
        page_numbers: Optional[List[int]] = None,
    ) -> EnrichedChunk:
        """
        Enrich a single chunk with contextual metadata and source references.
        
        Args:
            content: The chunk content.
            metadata: Original chunk metadata.
            token_count: Token count of the chunk.
            chunk_index: Position of chunk in the sequence.
            source_document: Original document filename.
            char_start: Character offset start in original document.
            char_end: Character offset end in original document.
            page_numbers: List of page numbers the chunk spans.
            
        Returns:
            EnrichedChunk with contextual enrichments and source references.
        """
        prompt = self._build_prompt(content, metadata)
        
        # Extract section reference from metadata
        source_section = metadata.get("article", "") or metadata.get("section", "")
        
        try:
            # Use new google.genai SDK client API
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            parsed = self._parse_response(response.text)
            
            return EnrichedChunk(
                content=content,
                original_metadata=metadata,
                token_count=token_count,
                # Source reference fields
                chunk_index=chunk_index,
                source_document=source_document,
                source_section=source_section,
                char_start=char_start,
                char_end=char_end,
                page_numbers=page_numbers or [],
                # Enrichment fields
                contextual_summary=parsed["contextual_summary"],
                semantic_tags=parsed["semantic_tags"],
                key_entities=parsed["key_entities"],
                clause_type=parsed["clause_type"],
            )
        except Exception as e:
            print(f"Warning: Enrichment failed for chunk {chunk_index}: {e}")
            # Return unenriched chunk on failure
            return EnrichedChunk(
                content=content,
                original_metadata=metadata,
                token_count=token_count,
                chunk_index=chunk_index,
                source_document=source_document,
                source_section=source_section,
                char_start=char_start,
                char_end=char_end,
                page_numbers=page_numbers or [],
            )
    
    async def _enrich_chunk_async(
        self,
        content: str,
        metadata: dict,
        token_count: int,
        chunk_index: int,
        source_document: str,
    ) -> EnrichedChunk:
        """Async wrapper for chunk enrichment."""
        return await asyncio.to_thread(
            self.enrich_chunk,
            content,
            metadata,
            token_count,
            chunk_index,
            source_document,
        )
    
    async def enrich_chunks_async(
        self,
        chunks: List,
        source_document: str = "",
    ) -> List[EnrichedChunk]:
        """
        Enrich multiple chunks asynchronously with rate limiting.
        
        Args:
            chunks: List of Chunk objects (from DocumentChunker).
            source_document: Original document filename for provenance.
            
        Returns:
            List of EnrichedChunk objects with source references.
        """
        enriched = []
        total = len(chunks)
        
        for i in range(0, total, self.batch_size):
            batch = chunks[i:i + self.batch_size]
            
            # Process batch in parallel with chunk indices
            tasks = [
                self._enrich_chunk_async(
                    c.content,
                    c.metadata,
                    c.token_count,
                    chunk_index=i + j,
                    source_document=source_document,
                )
                for j, c in enumerate(batch)
            ]
            batch_results = await asyncio.gather(*tasks)
            enriched.extend(batch_results)
            
            # Progress update
            print(f"Enriched {min(i + self.batch_size, total)}/{total} chunks")
            
            # Rate limit delay between batches
            if i + self.batch_size < total:
                await asyncio.sleep(self.rate_limit_delay)
        
        return enriched
    
    def enrich_chunks(self, chunks: List, source_document: str = "") -> List[EnrichedChunk]:
        """
        Synchronous wrapper for chunk enrichment.
        
        Args:
            chunks: List of Chunk objects (from DocumentChunker).
            source_document: Original document filename for provenance.
            
        Returns:
            List of EnrichedChunk objects with source references.
        """
        return asyncio.run(self.enrich_chunks_async(chunks, source_document))


class RuleBasedEnricher:
    """
    Free, fast enricher that uses regex patterns instead of LLM.
    
    Extracts clause type and entities from document headers and content
    without making any API calls.
    """
    
    # Mapping of keywords to clause types
    CLAUSE_PATTERNS = {
        "definitions": ["definition", "defined terms", "interpretation"],
        "rent_payment": ["rent", "base rent", "additional rent", "payment", "lease fee"],
        "security_deposit": ["security deposit", "deposit"],
        "maintenance_repairs": ["maintenance", "repair", "hvac", "janitorial", "common area"],
        "insurance": ["insurance", "liability", "indemnity coverage"],
        "default_remedies": ["default", "breach", "remedy", "remedies", "cure"],
        "termination": ["termination", "terminate", "expiration", "early termination"],
        "assignment_subletting": ["assignment", "subletting", "sublet", "transfer"],
        "use_restrictions": ["use", "permitted use", "exclusive use", "restriction"],
        "environmental": ["environmental", "hazardous", "toxic"],
        "indemnification": ["indemnification", "indemnify", "hold harmless"],
        "general_provisions": ["notice", "governing law", "waiver", "miscellaneous", "general"],
        "schedules_exhibits": ["schedule", "exhibit", "appendix", "attachment"],
        "parties_recitals": ["parties", "recital", "whereas", "landlord", "tenant", "lessor", "lessee"],
    }
    
    # Regex patterns for entity extraction
    ENTITY_PATTERNS = {
        "money": r'\$[\d,]+(?:\.\d{2})?',
        "percentage": r'\d+(?:\.\d+)?%',
        "date": r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b',
        "sqft": r'[\d,]+\s*(?:square feet|sq\.?\s*ft\.?|sf)',
    }
    
    def __init__(self, doc_title: str = "Commercial Lease Agreement"):
        """Initialize the rule-based enricher."""
        self.doc_title = doc_title
        print(f"✅ RuleBasedEnricher initialized (no API calls)")
    
    def _detect_clause_type(self, content: str, metadata: dict) -> str:
        """Detect clause type from headers and content."""
        search_text = ""
        if metadata.get("article"):
            search_text += metadata["article"].lower() + " "
        if metadata.get("section"):
            search_text += metadata["section"].lower() + " "
        search_text += content[:200].lower()
        
        for clause_type, keywords in self.CLAUSE_PATTERNS.items():
            for keyword in keywords:
                if keyword in search_text:
                    return clause_type
        return "other"
    
    def _extract_entities(self, content: str) -> List[str]:
        """Extract entities using regex patterns."""
        import re
        entities = []
        for entity_type, pattern in self.ENTITY_PATTERNS.items():
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches[:3]:
                entities.append(f"{entity_type}: {match}")
        return entities[:10]
    
    def _generate_summary(self, content: str, metadata: dict, clause_type: str) -> str:
        """Generate a simple contextual summary from headers."""
        parts = []
        if metadata.get("article"):
            parts.append(metadata["article"])
        if metadata.get("section"):
            parts.append(metadata["section"])
        
        if parts:
            header = " - ".join(parts)
            return f"This section covers {header} ({clause_type.replace('_', ' ')})."
        elif clause_type != "other":
            return f"This section covers {clause_type.replace('_', ' ')} provisions."
        return "This section is part of the lease agreement."
    
    def _generate_tags(self, clause_type: str, entities: List[str]) -> List[str]:
        """Generate semantic tags from clause type and entities."""
        tags = [clause_type]
        for entity in entities:
            if entity.startswith("money:"):
                tags.append("financial_terms")
            elif entity.startswith("date:"):
                tags.append("dates")
            elif entity.startswith("sqft:"):
                tags.append("space_requirements")
        return list(set(tags))[:5]
    
    def enrich_chunk(
        self,
        content: str,
        metadata: dict,
        token_count: int,
        chunk_index: int = 0,
        source_document: str = "",
        char_start: int = 0,
        char_end: int = 0,
        page_numbers: Optional[List[int]] = None,
    ) -> EnrichedChunk:
        """Enrich a single chunk using rule-based extraction (no API calls)."""
        clause_type = self._detect_clause_type(content, metadata)
        entities = self._extract_entities(content)
        summary = self._generate_summary(content, metadata, clause_type)
        tags = self._generate_tags(clause_type, entities)
        source_section = metadata.get("article", "") or metadata.get("section", "")
        
        return EnrichedChunk(
            content=content,
            original_metadata=metadata,
            token_count=token_count,
            chunk_index=chunk_index,
            source_document=source_document,
            source_section=source_section,
            char_start=char_start,
            char_end=char_end,
            page_numbers=page_numbers or [],
            contextual_summary=summary,
            semantic_tags=tags,
            key_entities=entities,
            clause_type=clause_type,
        )
    
    def enrich_chunks(self, chunks: List, source_document: str = "") -> List[EnrichedChunk]:
        """Enrich multiple chunks (instant, no rate limiting needed)."""
        enriched = []
        for i, chunk in enumerate(chunks):
            enriched_chunk = self.enrich_chunk(
                content=chunk.content,
                metadata=chunk.metadata,
                token_count=chunk.token_count,
                chunk_index=i,
                source_document=source_document,
            )
            enriched.append(enriched_chunk)
        return enriched


def get_enricher(mode: str = None, doc_title: str = "Commercial Lease Agreement"):
    """
    Factory function to get the appropriate enricher based on mode.
    
    Args:
        mode: 'llm', 'rule-based', or 'none'. Defaults to ENRICHMENT_MODE from settings.
        doc_title: Document title for context.
        
    Returns:
        ChunkEnricher, RuleBasedEnricher, or None.
    """
    from config.settings import ENRICHMENT_MODE
    
    mode = mode or ENRICHMENT_MODE
    
    if mode == "llm":
        return ChunkEnricher(doc_title=doc_title)
    elif mode == "rule-based":
        return RuleBasedEnricher(doc_title=doc_title)
    elif mode == "none":
        return None
    else:
        print(f"⚠️ Unknown enrichment mode '{mode}', defaulting to rule-based")
        return RuleBasedEnricher(doc_title=doc_title)


# --- Test Block ---
if __name__ == "__main__":
    import sys
    sys.path.insert(0, "src")
    
    from ingestion.chunker import DocumentChunker
    
    # Load test document
    test_file = "data/test_outputs/output.md"
    source_doc = "Platform_Properties_Lease.pdf"  # Original document name
    
    if not os.path.exists(test_file):
        print(f"Error: {test_file} not found. Run parser.py first.")
    else:
        with open(test_file, "r", encoding="utf-8") as f:
            text = f.read()
        
        # Create chunks
        chunker = DocumentChunker()
        chunks = chunker.chunk(text)
        print(f"Created {len(chunks)} chunks")
        
        # Enrich first 3 chunks as a test
        enricher = ChunkEnricher()
        test_chunks = chunks[:3]
        
        print("\n--- Testing Enrichment with Source References ---")
        for i, chunk in enumerate(test_chunks):
            enriched = enricher.enrich_chunk(
                chunk.content,
                chunk.metadata,
                chunk.token_count,
                chunk_index=i,
                source_document=source_doc,
            )
            
            print(f"\n{'='*60}")
            print(f"CHUNK {i+1}")
            print(f"{'='*60}")
            print(f"📍 Source Reference: {enriched.source_reference}")
            print(f"📄 Section: {enriched.source_section or 'N/A'}")
            print(f"\nContent preview: {enriched.content[:200]}...")
            print(f"\n🏷️  Contextual Summary: {enriched.contextual_summary}")
            print(f"🔖 Semantic Tags: {enriched.semantic_tags}")
            print(f"📋 Key Entities: {enriched.key_entities}")
            print(f"📂 Clause Type: {enriched.clause_type}")
            
            # Show the to_dict output for first chunk
            if i == 0:
                print(f"\n--- JSON Serialization Example ---")
                import json
                print(json.dumps(enriched.to_dict(), indent=2, default=str)[:500] + "...")