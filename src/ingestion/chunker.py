"""
Document Chunker Module

Logic for Context-Aware (Header) splitting of legal documents.
This module is responsible for:
- Splitting documents into semantic chunks based on headers/sections
- Maintaining context across chunk boundaries
- Respecting logical document structure (clauses, articles, sections)
- Configurable chunk sizes with overlap
"""

import os
import sys
import re
from typing import List, Optional
from dataclasses import dataclass, field

# Add project root to path for config imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from config.settings import MAX_CHUNK_TOKENS, SECONDARY_CHUNK_SIZE, SECONDARY_CHUNK_OVERLAP, ORPHAN_CHUNK_MIN_TOKENS


@dataclass
class Chunk:
    """Represents a document chunk with content and metadata."""
    content: str
    metadata: dict = field(default_factory=dict)
    token_count: int = 0


class DocumentChunker:
    """
    Context-aware document chunker for legal documents.
    
    Uses MarkdownHeaderTextSplitter for primary header-based splitting,
    then applies RecursiveCharacterTextSplitter for oversized chunks.
    """
    
    # Patterns to clean from text (boilerplate, page markers, etc.)
    BOILERPLATE_PATTERNS = [
        r'^INITIAL\s*$',                          # "INITIAL" alone on a line
        r'^Landlord\s+Tenant\s*$',                # "Landlord  Tenant" footer
        r'^MR\s*[–-]\s*July\s+2020\s*$',          # Date footer
        r'^\d{1,3}\s*$',                          # Standalone page numbers
        r'^#+\s*\d{1,3}\s*$',                     # Headers that are just numbers
        r'^\s*$',                                 # Empty lines (will be normalized)
    ]
    
    # Regex to detect Table of Contents entries (header followed by just a page number)
    TOC_PATTERN = re.compile(
        r'^(#+\s+[\d.]+\s+[^\n]+)\n+(\d{1,3})\s*$',  # Header + page number only
        re.MULTILINE
    )
    
    # Pattern to match the entire Table of Contents section
    # Matches from "# TABLE OF CONTENTS" until the first content section (ARTICLE with substantive text)
    TOC_SECTION_PATTERN = re.compile(
        r'#\s*TABLE\s+OF\s*\n?\s*CONTENTS.*?(?=\n#\s*ARTICLE\s+1\s+INTERPRETATION\n+1\.01)',
        re.DOTALL | re.IGNORECASE
    )
    
    # Headers to split on (in order of hierarchy)
    HEADERS_TO_SPLIT_ON = [
        ("#", "article"),
        ("##", "section"),
    ]
    
    def __init__(
        self,
        max_tokens: int = MAX_CHUNK_TOKENS,
        secondary_chunk_size: int = SECONDARY_CHUNK_SIZE,
        secondary_chunk_overlap: int = SECONDARY_CHUNK_OVERLAP,
    ):
        """
        Initialize the DocumentChunker.
        
        Args:
            max_tokens: Maximum tokens per chunk before secondary splitting.
            secondary_chunk_size: Character size for secondary splitter.
            secondary_chunk_overlap: Overlap for secondary splitter.
        """
        self.max_tokens = max_tokens
        self.secondary_chunk_size = secondary_chunk_size
        self.secondary_chunk_overlap = secondary_chunk_overlap
        
        # Primary splitter: header-based
        self.header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=self.HEADERS_TO_SPLIT_ON,
            strip_headers=False,  # Keep headers in content for context
        )
        
        # Secondary splitter: for oversized chunks
        self.recursive_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.secondary_chunk_size,
            chunk_overlap=self.secondary_chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
    
    def _clean_text(self, text: str) -> str:
        """
        Clean boilerplate and noise from the document text.
        
        Args:
            text: Raw document text.
            
        Returns:
            Cleaned text with boilerplate removed.
        """
        # Step 0a: Remove entire Table of Contents section if present
        text = self.TOC_SECTION_PATTERN.sub('', text)
        
        # Step 0b: Remove any remaining TOC entries (headers followed by just page numbers)
        # This catches patterns like "# 7.02 Light Fixtures...\n22" from TOC
        text = self.TOC_PATTERN.sub('', text)
        
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Check if line matches any boilerplate pattern
            is_boilerplate = False
            for pattern in self.BOILERPLATE_PATTERNS:
                if re.match(pattern, line.strip(), re.IGNORECASE):
                    is_boilerplate = True
                    break
            
            if not is_boilerplate:
                cleaned_lines.append(line)
        
        # Join and normalize whitespace
        cleaned = '\n'.join(cleaned_lines)
        # Remove excessive blank lines (more than 2 consecutive)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        
        return cleaned.strip()
    
    def _count_tokens(self, text: str) -> int:
        """
        Approximate token count (chars / 4 is a reasonable estimate for English).
        
        Args:
            text: Text to count tokens for.
            
        Returns:
            Approximate token count.
        """
        return len(text) // 4
    
    def _is_orphan_chunk(self, text: str, min_words: int = 5) -> bool:
        """
        Check if a chunk is an "orphan" with too little meaningful content.
        
        Args:
            text: Chunk text to check.
            min_words: Minimum words required for a valid chunk.
            
        Returns:
            True if the chunk is an orphan and should be discarded.
        """
        # Remove markdown formatting for word count
        clean = re.sub(r'[#*_\-|]', ' ', text)
        words = clean.split()
        return len(words) < min_words
    
    def chunk(self, text: str) -> List[Chunk]:
        """
        Split document into coherent, semantic chunks.
        
        Args:
            text: Raw document text (markdown format).
            
        Returns:
            List of Chunk objects with content and metadata.
        """
        # Step 1: Clean the text
        cleaned_text = self._clean_text(text)
        
        # Step 2: Split by headers
        header_docs = self.header_splitter.split_text(cleaned_text)
        
        preliminary_chunks = []
        
        for doc in header_docs:
            content = doc.page_content
            metadata = doc.metadata
            token_count = self._count_tokens(content)
            
            # Step 3: Secondary split if chunk is too large
            if token_count > self.max_tokens:
                sub_docs = self.recursive_splitter.split_text(content)
                for i, sub_content in enumerate(sub_docs):
                    # Skip orphan chunks
                    if self._is_orphan_chunk(sub_content):
                        continue
                    
                    sub_metadata = {**metadata, "sub_chunk": i + 1}
                    preliminary_chunks.append(Chunk(
                        content=sub_content.strip(),
                        metadata=sub_metadata,
                        token_count=self._count_tokens(sub_content),
                    ))
            else:
                # Don't skip orphans yet - we'll merge them in post-processing
                preliminary_chunks.append(Chunk(
                    content=content.strip(),
                    metadata=metadata,
                    token_count=token_count,
                ))
        
        # Step 4: Post-process to merge orphan chunks with next chunk (iterative)
        # Keep merging until no more orphans can be resolved
        chunks_to_process = preliminary_chunks
        max_iterations = 10  # Prevent infinite loops
        
        for _ in range(max_iterations):
            merged_chunks = []
            i = 0
            any_merges = False
            
            while i < len(chunks_to_process):
                current_chunk = chunks_to_process[i]
                
                # Check if current chunk is an orphan (header-only, < threshold tokens)
                if current_chunk.token_count < ORPHAN_CHUNK_MIN_TOKENS and i + 1 < len(chunks_to_process):
                    # Merge with next chunk
                    next_chunk = chunks_to_process[i + 1]
                    merged_content = f"{current_chunk.content}\n\n{next_chunk.content}"
                    
                    # Combine metadata (prefer next chunk's metadata, add orphan's if different)
                    merged_metadata = {**current_chunk.metadata, **next_chunk.metadata}
                    
                    merged_chunks.append(Chunk(
                        content=merged_content.strip(),
                        metadata=merged_metadata,
                        token_count=self._count_tokens(merged_content),
                    ))
                    i += 2  # Skip next chunk since we merged it
                    any_merges = True
                else:
                    # Keep chunk as-is if it's not an orphan or it's the last chunk
                    merged_chunks.append(current_chunk)
                    i += 1
            
            chunks_to_process = merged_chunks
            
            # If no merges happened this iteration, we're done
            if not any_merges:
                break
        
        final_chunks = chunks_to_process
        
        return final_chunks


# --- Test Block ---
if __name__ == "__main__":
    import os
    
    # Load test document
    test_file = os.path.join("data", "test_outputs", "output.md")
    
    if not os.path.exists(test_file):
        print(f"Error: {test_file} not found. Run parser.py first.")
    else:
        with open(test_file, "r", encoding="utf-8") as f:
            text = f.read()
        
        print(f"Original document: {len(text)} characters")
        
        chunker = DocumentChunker()
        chunks = chunker.chunk(text)
        
        print(f"\nTotal chunks: {len(chunks)}")
        print(f"Average tokens per chunk: {sum(c.token_count for c in chunks) // len(chunks)}")
        
        print("\n--- Sample Chunks ---")
        for i, chunk in enumerate(chunks[:5]):
            print(f"\n[Chunk {i+1}] Tokens: {chunk.token_count}, Metadata: {chunk.metadata}")
            print(chunk.content[:200] + "..." if len(chunk.content) > 200 else chunk.content)
