"""
File Watchdog Module

Monitors an input folder for new documents and triggers ingestion automatically.
This module is responsible for:
- Watching the 'input' folder for new files
- Triggering the ingestion pipeline when files are added
- Avoiding re-processing of existing files on startup
- Moving processed files to a 'processed' folder
- Logging ingestion results to SQLite database
"""

import os
import sys
import time
import shutil
from pathlib import Path
from typing import Set

# Add project root and src to path for imports
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent

from config.settings import (
    WATCHDOG_INPUT_FOLDER,
    WATCHDOG_PROCESSED_FOLDER,
    WATCHDOG_SUPPORTED_EXTENSIONS,
    DEFAULT_DB_PATH,
)
from ingestion.ingest_pipeline import IngestionPipeline, PipelineConfig
from utils.db import init_db, log_ingestion, is_document_processed

load_dotenv()


class IngestionHandler(FileSystemEventHandler):
    """
    File system event handler that triggers ingestion on new files.
    
    Only processes files that are:
    1. Newly created (not pre-existing on startup)
    2. Have supported extensions (.pdf, .docx, .doc, .md)
    3. Not already processed (checked against SQLite database)
    """
    
    def __init__(
        self,
        input_folder: str = WATCHDOG_INPUT_FOLDER,
        processed_folder: str = WATCHDOG_PROCESSED_FOLDER,
        db_path: str = DEFAULT_DB_PATH,
    ):
        """
        Initialize the ingestion handler.
        
        Args:
            input_folder: Folder to watch for new files.
            processed_folder: Folder to move processed files to.
            db_path: Path to SQLite database for logging.
        """
        super().__init__()
        
        self.input_folder = Path(input_folder).resolve()
        self.processed_folder = Path(processed_folder).resolve()
        self.db_path = db_path
        
        # Create folders if they don't exist
        self.input_folder.mkdir(parents=True, exist_ok=True)
        self.processed_folder.mkdir(parents=True, exist_ok=True)
        
        # Initialize database (creates ingestion_logs table if needed)
        init_db(db_path)
        
        # Initialize pipeline (lazy - will be created on first use)
        self._pipeline = None
        
        # Track files that existed on startup (to ignore them)
        self.startup_files: Set[str] = self._get_existing_files()
        
        print(f"✅ Watchdog initialized")
        print(f"   📂 Watching: {self.input_folder}")
        print(f"   📁 Processed folder: {self.processed_folder}")
        print(f"   🗄️  Database: {self.db_path}")
        print(f"   📋 Files on startup (will be ignored): {len(self.startup_files)}")
    
    def _get_existing_files(self) -> Set[str]:
        """Get set of files that exist on startup."""
        existing = set()
        for f in self.input_folder.iterdir():
            if f.is_file() and f.suffix.lower() in WATCHDOG_SUPPORTED_EXTENSIONS:
                existing.add(f.name)
        return existing
    
    @property
    def pipeline(self) -> IngestionPipeline:
        """Lazy initialize the ingestion pipeline."""
        if self._pipeline is None:
            print("🔧 Initializing ingestion pipeline...")
            self._pipeline = IngestionPipeline()
            print("✅ Pipeline ready")
        return self._pipeline
    
    def on_created(self, event):
        """Handle file creation events."""
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        file_name = file_path.name
        
        # Skip unsupported files
        if file_path.suffix.lower() not in WATCHDOG_SUPPORTED_EXTENSIONS:
            return
        
        # Skip temporary Word files (start with ~$)
        if file_name.startswith("~$"):
            return
        
        # Skip files that existed on startup
        if file_name in self.startup_files:
            print(f"⏭️  Skipping (existed on startup): {file_name}")
            return
        
        # Skip already processed files (check database)
        if is_document_processed(file_name, self.db_path):
            print(f"⏭️  Skipping (already in database): {file_name}")
            return
        
        # Wait a moment for file to finish writing
        time.sleep(1)
        
        # Process the file
        self._process_file(file_path)
    
    def _process_file(self, file_path: Path):
        """Run ingestion pipeline on a file."""
        file_name = file_path.name
        
        print(f"\n{'='*60}")
        print(f"📄 New file detected: {file_name}")
        print(f"{'='*60}")
        
        try:
            # Run the ingestion pipeline
            result = self.pipeline.run(str(file_path))
            
            if result.success:
                print(f"✅ Successfully processed: {file_name}")
                print(f"   📊 Chunks: {result.chunks_processed}")
                print(f"   🔢 Vectors: {result.vectors_uploaded}")
                print(f"   ⏱️  Time: {result.processing_time_seconds:.1f}s")
                
                # Log success to database
                log_ingestion(
                    document_name=file_name,
                    status="success",
                    chunks_processed=result.chunks_processed,
                    vectors_uploaded=result.vectors_uploaded,
                    processing_time_seconds=result.processing_time_seconds,
                    db_path=self.db_path,
                )
                
                # Move to processed folder
                dest = self.processed_folder / file_name
                shutil.move(str(file_path), str(dest))
                print(f"   📁 Moved to: {dest}")
            else:
                print(f"❌ Failed to process: {file_name}")
                print(f"   Error: {result.error_message}")
                
                # Log failure to database
                log_ingestion(
                    document_name=file_name,
                    status="failed",
                    error_message=result.error_message,
                    db_path=self.db_path,
                )
                
        except Exception as e:
            print(f"❌ Error processing {file_name}: {e}")
            
            # Log exception to database
            log_ingestion(
                document_name=file_name,
                status="failed",
                error_message=str(e),
                db_path=self.db_path,
            )
        
        print(f"{'='*60}\n")


def run_watchdog(
    input_folder: str = WATCHDOG_INPUT_FOLDER,
    processed_folder: str = WATCHDOG_PROCESSED_FOLDER,
    db_path: str = DEFAULT_DB_PATH,
):
    """
    Start the file watchdog.
    
    Args:
        input_folder: Folder to watch for new files.
        processed_folder: Folder to move processed files to.
        db_path: Path to SQLite database for logging.
    """
    print("\n" + "="*60)
    print("🐕 STARTING FILE WATCHDOG")
    print("="*60 + "\n")
    
    # Create event handler
    handler = IngestionHandler(input_folder, processed_folder, db_path)
    
    # Create and configure observer
    observer = Observer()
    observer.schedule(handler, str(handler.input_folder), recursive=False)
    
    # Start watching
    observer.start()
    print(f"\n🔍 Watching for new files... (Press Ctrl+C to stop)\n")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n⏹️  Stopping watchdog...")
        observer.stop()
    
    observer.join()
    print("✅ Watchdog stopped.")


# --- Entry Point ---
if __name__ == "__main__":
    run_watchdog()
