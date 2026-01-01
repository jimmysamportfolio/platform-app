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
from dotenv import load_dotenv
from llama_parse import LlamaParse
from docx2pdf import convert

load_dotenv()

llama_cloud_api_key = os.getenv("LLAMA_CLOUD_API_KEY")

# Validate API key
if not llama_cloud_api_key:
    raise ValueError("LLAMA_CLOUD_API_KEY not found in environment variables")

# Initialize parser
parser = LlamaParse(
    api_key=llama_cloud_api_key,
    result_type="markdown",
    verbose=True,
    ignore_errors=False,
)

# Path to the lease draft document
file_path = os.path.join("data", "raw_pdfs", "Lease Draft #4 (final) - Church's Chicken, 11939 240 Street, MR - Jul 13, 2020.docx")

# Check if file exists
if not os.path.exists(file_path):
    raise FileNotFoundError(f"File not found: {file_path}")

# Convert DOCX to PDF first (LlamaParse works better with PDFs)
if file_path.lower().endswith('.docx'):
    pdf_path = file_path.replace('.docx', '.pdf')
    
    if not os.path.exists(pdf_path):
        print(f"Converting DOCX to PDF...")
        convert(file_path, pdf_path)
        print(f"Conversion successful!")
    
    file_path = pdf_path

# Parse the document
print(f"Parsing document: {os.path.basename(file_path)}")
documents = parser.load_data(file_path)

# Write the parsed content to output.md
print(f"Writing parsed content to output.md...")
with open("output.md", "w", encoding="utf-8") as f:
    for doc in documents:
        if hasattr(doc, 'text') and doc.text:
            f.write(doc.text)
            f.write("\n\n")

print("Parsing complete!")
