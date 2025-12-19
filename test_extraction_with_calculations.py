"""Test extraction with the improved processor that has calculations."""
import asyncio
import json
from pathlib import Path

from src.ir.builder import IRBuilder
from src.processors.executor import ProcessorExecutor
from src.processors.models import Processor
from src.db.database import get_database

async def main():
    # Get the improved processor from database
    db = await get_database()

    # Use the new processor with calculations
    processor_id = "b5beb90e-1a05-4b3c-bfee-a3a4a22a797d"
    print(f"Using processor ID: {processor_id}")
    print()

    # Load full processor
    processor_data = await db.get_processor(processor_id)
    processor = Processor.from_json(processor_data['processor_json'])

    print(f"Processor has {len(processor.calculations)} calculations:")
    for calc in processor.calculations:
        print(f"  - {calc.field} = {calc.formula}")
    print()

    # Build IR from test document
    pdf_path = Path("data/samples/Windom-Worthington.pdf")
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    print("Building DocumentIR...")
    builder = IRBuilder(dpi=300)
    document_ir = builder.build(pdf_bytes, pdf_path.name)
    print(f"  {len(document_ir.blocks)} blocks, {document_ir.page_count} pages")
    print()

    # Execute processor
    print("Executing processor...")
    executor = ProcessorExecutor()
    try:
        result = executor.execute(document_ir, processor)
        print("SUCCESS! Extraction Result:")
        print(json.dumps(result, indent=2, default=str))
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
