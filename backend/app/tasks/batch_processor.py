# app/tasks/batch_processor.py

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, List
import uuid

from ..db import crud
from ..db.database import get_database
from ..models.enums import BatchStatus, DocumentStatus, ResultStatus
from ..models.document import Document
from ..models.batch import Batch, BatchUpdate
from ..services.text_extraction import extract_text_from_bytes
from ..services.blob_storage import download_blob_as_bytes

# Configure logging
logger = logging.getLogger(__name__)

class BatchProcessor:
    def __init__(self):
        self.is_running = False
        self.current_batch: Optional[Batch] = None
        self.current_documents: List[Document] = []

    async def process_batches(self):
        """Main loop for processing batches."""
        self.is_running = True
        try:
            while self.is_running:
                # Get next batch to process
                batch = await self._get_next_batch()
                if not batch:
                    # No batches to process, wait before checking again
                    await asyncio.sleep(10)
                    continue

                self.current_batch = batch
                logger.info(f"Processing batch {batch.id}")

                try:
                    # Update batch status to PROCESSING
                    await crud.update_batch(
                        batch_id=batch.id,
                        batch_in=BatchUpdate(status=BatchStatus.PROCESSING)
                    )

                    # Get all documents in the batch
                    self.current_documents = await crud.get_documents_by_batch_id(batch_id=batch.id)
                    
                    # Sort documents by queue position
                    self.current_documents.sort(key=lambda x: x.queue_position or float('inf'))
                    
                    # Process each document
                    completed = 0
                    failed = 0
                    for doc in self.current_documents:
                        try:
                            success = await self._process_document(doc)
                            if success:
                                completed += 1
                            else:
                                failed += 1
                        except Exception as e:
                            logger.error(f"Error processing document {doc.id} in batch {batch.id}: {e}")
                            failed += 1
                            continue

                    # Update batch status
                    final_status = BatchStatus.COMPLETED if failed == 0 else BatchStatus.PARTIAL
                    await crud.update_batch(
                        batch_id=batch.id,
                        batch_in=BatchUpdate(
                            status=final_status,
                            completed_files=completed,
                            failed_files=failed,
                            error_message=f"Failed to process {failed} files" if failed > 0 else None
                        )
                    )

                except Exception as e:
                    logger.error(f"Error processing batch {batch.id}: {e}")
                    await crud.update_batch(
                        batch_id=batch.id,
                        batch_in=BatchUpdate(
                            status=BatchStatus.ERROR,
                            error_message=str(e)
                        )
                    )
                finally:
                    self.current_batch = None
                    self.current_documents = []

        except Exception as e:
            logger.error(f"Batch processor error: {e}")
            self.is_running = False

    async def _get_next_batch(self) -> Optional[Batch]:
        """Get the next batch to process based on priority and creation time."""
        try:
            # Get database instance
            db = get_database()
            if db is None:
                logger.error("Database connection not available")
                return None

            # Find batches in QUEUED status, ordered by priority and creation time
            pipeline = [
                {"$match": {"status": BatchStatus.QUEUED}},
                {"$sort": {"priority": -1, "created_at": 1}},
                {"$limit": 1}
            ]
            
            logger.info(f"Executing batch query pipeline: {pipeline}")
            
            # Get collection and check indexes
            collection = db.batches
            indexes = await collection.list_indexes().to_list(length=None)
            logger.info(f"Available indexes on batches collection: {indexes}")
            
            async for batch_dict in collection.aggregate(pipeline):
                return Batch(**batch_dict)
            
            return None
        except Exception as e:
            logger.error(f"Error getting next batch: {e}", exc_info=True)
            return None

    async def _process_document(self, document: Document) -> bool:
        """Process a single document in the batch."""
        try:
            # Update document status to PROCESSING
            await crud.update_document_status(
                document_id=document.id,
                status=DocumentStatus.PROCESSING
            )

            # Download file from blob storage
            file_bytes = await download_blob_as_bytes(document.storage_blob_path)
            if not file_bytes:
                raise Exception("Failed to download file from storage")

            # Extract text from document
            text_content = await extract_text_from_bytes(
                file_bytes=file_bytes,
                file_type=document.file_type
            )
            if not text_content:
                raise Exception("Failed to extract text from document")

            # TODO: Call AI assessment service
            # For now, just update status to COMPLETED
            await crud.update_document_status(
                document_id=document.id,
                status=DocumentStatus.COMPLETED
            )

            # Update result status
            await crud.update_result(
                result_id=document.id,
                update_data={"status": ResultStatus.COMPLETED.value}
            )

            return True

        except Exception as e:
            logger.error(f"Error processing document {document.id}: {e}")
            # Update document status to ERROR
            await crud.update_document_status(
                document_id=document.id,
                status=DocumentStatus.ERROR
            )
            # Update result status
            await crud.update_result(
                result_id=document.id,
                update_data={"status": ResultStatus.ERROR.value}
            )
            return False

    def stop(self):
        """Stop the batch processor."""
        self.is_running = False 