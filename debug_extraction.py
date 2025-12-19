"""Debug extraction to see what the processor actually extracts."""
import asyncio
import json
from pathlib import Path

from src.ir.builder import IRBuilder
from src.processors.models import Processor
from src.processors.executor import ProcessorExecutor
from src.db.database import get_database

async def main():
    # Load processor from database
    db = await get_database()
    processor_data = await db.get_processor("df02f539-2443-471b-a80c-caa2669c8789")

    if not processor_data:
        print("Processor not found!")
        return

    processor = Processor.from_json(processor_data['processor_json'])

    print(f"Processor: {processor.name}")
    print(f"Anchors: {len(processor.anchors)}")
    print(f"Regions: {len(processor.regions)}")
    print(f"Extraction ops: {len(processor.extraction_ops)}")
    print()

    # Show extraction ops
    print("Extraction Operations:")
    for i, op in enumerate(processor.extraction_ops):
        print(f"  {i+1}. {op.field_path} <- {op.source}")
    print()

    # Build IR from training document
    pdf_path = Path("data/samples/Windom-Worthington.pdf")
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    builder = IRBuilder(dpi=300)
    document_ir = builder.build(pdf_bytes, pdf_path.name)

    print(f"Document IR: {len(document_ir.blocks)} blocks, {len(document_ir.tables)} tables")
    print()

    # Execute processor
    executor = ProcessorExecutor()
    try:
        result = executor.execute(document_ir, processor)
        print("Extraction Result:")
        print(json.dumps(result, indent=2, default=str))
    except Exception as e:
        print(f"Extraction failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
