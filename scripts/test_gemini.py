import os
from dotenv import load_dotenv
from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.ai_extractor import AIExtractor

def main():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY not found in .env")
        return
        
    db = DatabaseManager()
    logger = PipelineLogger(db)
    extractor = AIExtractor(db, logger, api_key)
    
    # We found company_id 1 has pages
    print("Extracting data for company_id 1...")
    results = extractor.extract_for_company(1)
    print("Extraction complete. Results:")
    for r in results:
        print(r)
        
    stats = extractor.get_extraction_stats()
    print("\nStats:", stats)

if __name__ == "__main__":
    main()
