"""
File Watchdog Module (Queue Mode with Polling)

Monitors an input folder for new documents and queues them for user selection.
Uses polling instead of inotify for network share compatibility (SMB/CIFS).

This module is responsible for:
- Watching the 'input' folder for new files (via polling)
- Queuing detected files for user decision
- Broadcasting events via WebSocket to frontend
- Processing files with the selected mode (full or clause-only)
"""

import os
import sys
import time
import shutil
import asyncio
from pathlib import Path
from typing import Set, List, Dict, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime

# Add project root and src to path for imports
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from dotenv import load_dotenv
# Use PollingObserver for network share compatibility (inotify doesn't work with SMB/CIFS)
from watchdog.observers.polling import PollingObserver
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

# Polling interval in seconds (how often to check for new files)
POLLING_INTERVAL = 5


@dataclass
class PendingFile:
    """Represents a file waiting for user decision."""
    file_path: str
    file_name: str
    detected_at: datetime = field(default_factory=datetime.now)


class IngestionHandler(FileSystemEventHandler):
    """
    File system event handler that queues files for user decision.
    
    Files are NOT auto-processed. Instead, they are added to a pending queue
    and the frontend is notified via a callback. User then selects extraction mode.
    """
    
    # Class-level shared state for pending files (accessible from API)
    _pending_files: Dict[str, PendingFile] = {}
    _new_file_callbacks: List[Callable] = []
    
    def __init__(
        self,
        input_folder: str = WATCHDOG_INPUT_FOLDER,
        processed_folder: str = WATCHDOG_PROCESSED_FOLDER,
        db_path: str = DEFAULT_DB_PATH,
    ):
        super().__init__()
        
        self.input_folder = Path(input_folder).resolve()
        self.processed_folder = Path(processed_folder).resolve()
        self.db_path = db_path
        
        # Create processed folder if it doesn't exist (input may be read-only mount)
        if not self.input_folder.exists():
            self.input_folder.mkdir(parents=True, exist_ok=True)
        self.processed_folder.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        init_db(db_path)
        
        # Initialize pipeline (lazy)
        self._pipeline = None
        
        # Track files that existed on startup (to ignore them)
        self.startup_files: Set[str] = self._get_existing_files()
        
        print(f"✅ Watchdog initialized (Polling Mode)")
        print(f"   📂 Watching: {self.input_folder}")
        print(f"   📁 Processed folder: {self.processed_folder}")
        print(f"   📋 Files on startup (ignored): {len(self.startup_files)}")
    
    def _get_existing_files(self) -> Set[str]:
        """Get set of files that exist on startup."""
        existing = set()
        for f in self.input_folder.iterdir():
            if f.is_file() and f.suffix.lower() in WATCHDOG_SUPPORTED_EXTENSIONS:
                existing.add(f.name)
        return existing
    
    def forget_file(self, file_name: str):
        """Remove a file from the startup_files set to allow re-ingestion."""
        if file_name in self.startup_files:
            self.startup_files.remove(file_name)
            print(f"🧹 Removed {file_name} from startup/ignore list")
    
    @property
    def pipeline(self) -> IngestionPipeline:
        """Lazy initialize the ingestion pipeline."""
        if self._pipeline is None:
            print("🔧 Initializing ingestion pipeline...")
            self._pipeline = IngestionPipeline()
            print("✅ Pipeline ready")
        return self._pipeline
    
    @classmethod
    def register_callback(cls, callback: Callable):
        """Register a callback to be called when new files are detected."""
        cls._new_file_callbacks.append(callback)
    
    @classmethod
    def get_pending_files(cls) -> List[Dict]:
        """Get list of pending files waiting for user decision."""
        return [
            {
                "file_path": pf.file_path,
                "file_name": pf.file_name,
                "detected_at": pf.detected_at.isoformat(),
            }
            for pf in cls._pending_files.values()
        ]
    
    @classmethod
    def remove_pending(cls, file_name: str):
        """Remove a file from the pending queue."""
        if file_name in cls._pending_files:
            del cls._pending_files[file_name]
    
    def on_created(self, event):
        """Handle file creation events - add to queue."""
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        file_name = file_path.name
        
        # Skip unsupported files
        if file_path.suffix.lower() not in WATCHDOG_SUPPORTED_EXTENSIONS:
            return
        
        # Skip temporary Word files
        if file_name.startswith("~$"):
            return
        
        # Skip files that existed on startup
        if file_name in self.startup_files:
            return
        
        # Skip already processed files
        if is_document_processed(file_name, self.db_path):
            print(f"⏭️  Skipping (already processed): {file_name}")
            return
        
        # Wait for file to finish writing
        time.sleep(1)
        
        # Add to pending queue
        pending = PendingFile(
            file_path=str(file_path),
            file_name=file_name,
        )
        IngestionHandler._pending_files[file_name] = pending
        
        print(f"\n📄 New file detected (queued): {file_name}")
        print(f"   Waiting for user to select extraction mode...")
        
        # Notify callbacks (for WebSocket broadcast)
        for callback in IngestionHandler._new_file_callbacks:
            try:
                callback(file_name, str(file_path))
            except Exception as e:
                print(f"   Warning: Callback failed: {e}")
    
    def process_file(self, file_path: str, mode: str = "full") -> Dict:
        """
        Process a file with the specified mode.
        
        Args:
            file_path: Path to the file to process.
            mode: "full" for complete pipeline, "clause_only" for quick extraction.
            
        Returns:
            Dict with processing result.
        """
        file_name = os.path.basename(file_path)
        
        print(f"\n{'='*60}")
        print(f"📄 Processing: {file_name} (mode: {mode})")
        print(f"{'='*60}")
        
        try:
            if mode == "clause_only":
                result = self.pipeline.run_clause_only(file_path)
            else:
                result = self.pipeline.run(file_path)
            
            if result.success:
                print(f"✅ Successfully processed: {file_name}")
                
                # Log success
                log_ingestion(
                    document_name=file_name,
                    status="success",
                    chunks_processed=result.chunks_processed,
                    vectors_uploaded=result.vectors_uploaded,
                    processing_time_seconds=result.processing_time_seconds,
                    extraction_mode=mode,
                    db_path=self.db_path,
                )
                
                # Move to processed folder
                dest = self.processed_folder / file_name
                if Path(file_path).exists():
                    shutil.move(file_path, str(dest))
                    print(f"   📁 Moved to: {dest}")
                
                # Also copy the converted PDF if it exists (for document preview)
                if file_name.lower().endswith('.docx'):
                    pdf_name = file_name[:-5] + '.pdf'  # Replace .docx with .pdf
                    temp_pdf = Path("data/temp") / pdf_name
                    if temp_pdf.exists():
                        dest_pdf = self.processed_folder / pdf_name
                        shutil.copy2(str(temp_pdf), str(dest_pdf))
                        print(f"   📄 Copied PDF for preview: {dest_pdf}")
                
                # Remove from pending
                IngestionHandler.remove_pending(file_name)
                
                return {
                    "success": True,
                    "file_name": file_name,
                    "mode": mode,
                    "chunks_processed": result.chunks_processed,
                    "vectors_uploaded": result.vectors_uploaded,
                    "processing_time": result.processing_time_seconds,
                }
            else:
                print(f"❌ Failed: {result.error_message}")
                log_ingestion(
                    document_name=file_name,
                    status="failed",
                    error_message=result.error_message,
                    extraction_mode=mode,
                    db_path=self.db_path,
                )
                IngestionHandler.remove_pending(file_name)
                
                return {
                    "success": False,
                    "file_name": file_name,
                    "error": result.error_message,
                }
                
        except Exception as e:
            print(f"❌ Error: {e}")
            log_ingestion(
                document_name=file_name,
                status="failed",
                error_message=str(e),
                extraction_mode=mode,
                db_path=self.db_path,
            )
            IngestionHandler.remove_pending(file_name)
            
            return {
                "success": False,
                "file_name": file_name,
                "error": str(e),
            }


# Global handler instance (for API access)
_handler_instance: Optional[IngestionHandler] = None


def get_handler() -> Optional[IngestionHandler]:
    """Get the global handler instance."""
    return _handler_instance


def run_watchdog(
    input_folder: str = WATCHDOG_INPUT_FOLDER,
    processed_folder: str = WATCHDOG_PROCESSED_FOLDER,
    db_path: str = DEFAULT_DB_PATH,
):
    """Start the file watchdog in polling mode (for network share compatibility)."""
    global _handler_instance
    
    print("\n" + "="*60)
    print("🐕 STARTING FILE WATCHDOG (Polling Mode)")
    print("="*60 + "\n")
    
    # Create event handler
    _handler_instance = IngestionHandler(input_folder, processed_folder, db_path)
    
    # Use PollingObserver for network share compatibility (checks every POLLING_INTERVAL seconds)
    observer = PollingObserver(timeout=POLLING_INTERVAL)
    observer.schedule(_handler_instance, str(_handler_instance.input_folder), recursive=False)
    
    # Start watching
    observer.start()
    print(f"\n🔍 Watching for new files (polling every {POLLING_INTERVAL}s)...")
    print(f"   Press Ctrl+C to stop\n")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping File Watcher...")
        observer.stop()
    
    observer.join()
    print("✅ File Watcher stopped")


# --- Entry Point ---
if __name__ == "__main__":
    run_watchdog()
