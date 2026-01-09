"""
Document Parser Module

Handles LlamaParse/PDF-to-Markdown conversion for legal documents.
This module is responsible for:
- Loading PDF files from the raw_pdfs directory
- Converting PDFs to structured Markdown format
- Preserving document structure (headers, sections, tables)
- Handling various PDF formats and layouts
"""

import os
from typing import List, Optional
from dotenv import load_dotenv
from llama_parse import LlamaParse
from docx2pdf import convert

class DocumentParser:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("LLAMA_CLOUD_API_KEY")
        if not self.api_key:
            raise ValueError("LLAMA_CLOUD_API_KEY not found in environment variables")
            
        self.parser = LlamaParse(
            api_key=self.api_key,
            result_type="markdown",
            verbose=True,
            ignore_errors=False,
        )

    def parse_file(self, file_path: str, output_path: Optional[str] = None) -> List[object]:
        """
        Parses a file (PDF or DOCX) to Markdown.
        
        Args:
            file_path: Path to the input file (PDF or DOCX).
            output_path: Optional path to save the parsed markdown output.
            
        Returns:
            List of document objects from LlamaParse.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # Convert DOCX to PDF first (LlamaParse works better with PDFs)
        if file_path.lower().endswith('.docx'):
            # Convert to temp folder to avoid triggering file watcher again
            temp_dir = os.path.join("data", "temp")
            os.makedirs(temp_dir, exist_ok=True)
            pdf_name = os.path.basename(file_path).replace('.docx', '.pdf')
            pdf_path = os.path.join(temp_dir, pdf_name)
            
            if not os.path.exists(pdf_path):
                print(f"Converting DOCX to PDF...")
                convert(file_path, pdf_path)
                print(f"Conversion successful!")
            
            file_path = pdf_path

        # Parse the document
        print(f"Parsing document: {os.path.basename(file_path)}")
        documents = self.parser.load_data(file_path)

        if output_path:
            # Ensure directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            print(f"Writing parsed content to {output_path}")
            with open(output_path, "w", encoding="utf-8") as f:
                for doc in documents:
                    if hasattr(doc, 'text') and doc.text:
                        f.write(doc.text)
                        f.write("\n\n")
                        
        return documents

if __name__ == "__main__":
    parser = DocumentParser()
    # Using the same test file as before
    input_file = "data/raw_pdfs/Lease Draft #4 (final) - Church's Chicken, 11939 240 Street, MR - Jul 13, 2020.docx"
    output_file = os.path.join("data", "test_outputs", "output.md")
    
    try:
        parser.parse_file(input_file, output_file)
        print("Parsing complete!")
    except Exception as e:
        print(f"Error: {e}")