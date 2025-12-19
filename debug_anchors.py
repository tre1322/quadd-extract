"""Debug which anchors are found."""
import asyncio
import logging
from pathlib import Path

from src.ir.builder import IRBuilder
from src.processors.executor import ProcessorExecutor
from src.processors.models import Processor
from src.db.database import get_database

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

async def main():
    # Get processor
    db = await get_database()
    processor_id = "3aa8bda6-5985-4f09-9b27-a60b4d49d018"
    processor_data = await db.get_processor(processor_id)
    processor = Processor.from_json(processor_data['processor_json'])

    print(f"Processor has {len(processor.anchors)} anchors:")
    for anchor in processor.anchors:
        print(f"  - {anchor.name}: {anchor.patterns} (required={anchor.required})")
    print()

    # Build IR
    pdf_path = Path("data/samples/Windom-Worthington.pdf")
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    builder = IRBuilder(dpi=300)
    document_ir = builder.build(pdf_bytes, pdf_path.name)
    print(f"Document has {len(document_ir.blocks)} blocks")
    print()

    # Try to find anchors
    executor = ProcessorExecutor()
    print("Finding anchors...")
    anchor_positions = executor._find_anchors(document_ir, processor.anchors)

    print(f"\nFound {len(anchor_positions)} anchors:")
    for name, block in anchor_positions.items():
        print(f"  - {name}: '{block.text}' at {block.bbox}")

if __name__ == "__main__":
    asyncio.run(main())
