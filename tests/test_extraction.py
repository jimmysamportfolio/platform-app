import os
import sys
from dotenv import load_dotenv

# Add src to path
# Robustly find the src directory relative to this script
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
src_path = os.path.join(project_root, "src")
if src_path not in sys.path:
    sys.path.append(src_path)

# Ensure user site-packages are in path (fixes ModuleNotFoundError for locally installed packages)
import site
user_site_packages = site.getusersitepackages()
if user_site_packages not in sys.path:
    sys.path.append(user_site_packages)

from ingestion.extractor import LeaseExtractor, Lease

load_dotenv()

def test_extraction():
    # Path to the parsed output
    file_path = os.path.join("data", "test_outputs", "output.md")
    
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found. Please run parser.py first.")
        return

    print(f"Reading from {file_path}...")
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    
    print("\nExtracting data using LLM...")
    try:
        extractor = LeaseExtractor()
        lease_data = extractor.extract(text)
        
        print("\n=== EXTRACTION SUCCESSFUL ===")
        print(f"Tenant: {lease_data.tenant_name}")
        print(f"Premises: {lease_data.premises_description}")
        print(f"Area: {lease_data.rentable_area_sqft} sqft")
        print(f"Term: {lease_data.term_years} years")
        
        avg_rent = lease_data.calculate_average_rent_psf()
        print(f"Average Rent PSF: ${avg_rent}")
        
        print("\nFull Data:")
        print(lease_data.model_dump_json(indent=2))
        
    except Exception as e:
        print(f"\nError during extraction: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_extraction()
