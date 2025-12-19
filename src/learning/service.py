"""
Learning Service - orchestrates the processor learning workflow.

Coordinates IRBuilder, ProcessorSynthesizer, and Database to learn
processors from examples.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from src.ir.builder import IRBuilder
from src.ir.document_ir import DocumentIR
from src.processors.synthesizer import ProcessorSynthesizer
from src.processors.executor import ProcessorExecutor
from src.processors.models import Processor
from src.db.database import Database

logger = logging.getLogger(__name__)


class LearningService:
    """
    Orchestrates the learning workflow.

    Handles the end-to-end process of learning a processor from an example:
    1. Build DocumentIR from example
    2. Synthesize processor rules
    3. Validate on example
    4. Store in database
    """

    def __init__(
        self,
        db: Database,
        api_key: Optional[str] = None
    ):
        """
        Initialize learning service.

        Args:
            db: Database instance
            api_key: Anthropic API key
        """
        self.db = db
        self.ir_builder = IRBuilder(dpi=300)
        self.synthesizer = ProcessorSynthesizer(api_key=api_key)
        self.executor = ProcessorExecutor()

    async def learn_from_example(
        self,
        document_bytes: bytes,
        filename: str,
        desired_output: str,
        document_type: str,
        name: str
    ) -> dict:
        """
        Learn a processor from an example document.

        Args:
            document_bytes: Raw document content
            filename: Document filename
            desired_output: Expected formatted output
            document_type: Type of document (basketball, hockey, etc.)
            name: Name for the processor

        Returns:
            Dictionary with processor_id, confidence, and test_output
        """
        logger.info(f"Learning processor '{name}' from {filename}")
        start_time = time.time()

        # Step 1: Build DocumentIR
        logger.info("Step 1: Building DocumentIR from example...")
        document_ir = self.ir_builder.build(document_bytes, filename)
        logger.info(f"Built IR with {len(document_ir.blocks)} blocks, {len(document_ir.tables)} tables")

        # Step 2: Synthesize processor
        logger.info("Step 2: Synthesizing extraction rules...")
        processor = await self.synthesizer.synthesize(
            document_ir=document_ir,
            desired_output=desired_output,
            document_type=document_type,
            name=name
        )
        logger.info(f"Synthesized processor with {len(processor.anchors)} anchors, "
                   f"{len(processor.regions)} regions, {len(processor.extraction_ops)} extraction ops")

        # Step 3: Validate by applying to example
        logger.info("Step 3: Validating processor on example...")
        try:
            extracted_data = self.executor.execute(document_ir, processor)
            test_success = True
            test_output = str(extracted_data)  # TODO: Render with template
            logger.info("Validation successful")
        except Exception as e:
            test_success = False
            test_output = f"Error: {e}"
            logger.warning(f"Validation failed: {e}")

        # Step 4: Save to database
        logger.info("Step 4: Saving processor to database...")
        processor_id = await self.db.create_processor(
            processor_id=processor.id,
            name=processor.name,
            document_type=processor.document_type,
            processor_json=processor.to_json()
        )

        # Save example
        example_id = await self.db.save_example(
            processor_id=processor_id,
            filename=filename,
            document_ir_json=document_ir.to_json(),
            desired_output=desired_output
        )

        elapsed_time = time.time() - start_time
        logger.info(f"Learning completed in {elapsed_time:.1f}s")

        return {
            'processor_id': processor_id,
            'example_id': example_id,
            'success': test_success,
            'test_output': test_output,
            'anchors_count': len(processor.anchors),
            'regions_count': len(processor.regions),
            'extraction_ops_count': len(processor.extraction_ops),
            'learning_time_ms': int(elapsed_time * 1000)
        }

    async def extract_with_processor(
        self,
        document_bytes: bytes,
        filename: str,
        processor_id: str
    ) -> dict:
        """
        Extract data using a learned processor.

        Args:
            document_bytes: Raw document content
            filename: Document filename
            processor_id: ID of processor to use

        Returns:
            Dictionary with extracted data and metadata
        """
        logger.info(f"Extracting from {filename} using processor {processor_id}")
        start_time = time.time()

        # Step 1: Load processor from database
        processor_data = await self.db.get_processor(processor_id)
        if not processor_data:
            raise ValueError(f"Processor {processor_id} not found")

        processor = Processor.from_json(processor_data['processor_json'])

        # Step 2: Build DocumentIR
        logger.info("Building DocumentIR...")
        document_ir = self.ir_builder.build(document_bytes, filename)

        # Step 3: Execute processor
        logger.info("Executing processor...")
        try:
            extracted_data = self.executor.execute(document_ir, processor)
            success = True
            error_message = None

            # Update success count
            await self.db.increment_success(processor_id)

        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            extracted_data = {}
            success = False
            error_message = str(e)

            # Update failure count
            await self.db.increment_failure(processor_id)

        # Step 4: Save extraction record
        elapsed_time = time.time() - start_time
        extraction_id = await self.db.save_extraction(
            processor_id=processor_id,
            filename=filename,
            output_text=str(extracted_data),  # TODO: Render with template
            confidence=1.0 if success else 0.0,
            success=success,
            error_message=error_message,
            processing_time_ms=int(elapsed_time * 1000)
        )

        logger.info(f"Extraction completed in {elapsed_time:.1f}s")

        return {
            'extraction_id': extraction_id,
            'success': success,
            'data': extracted_data,
            'error_message': error_message,
            'processing_time_ms': int(elapsed_time * 1000)
        }
