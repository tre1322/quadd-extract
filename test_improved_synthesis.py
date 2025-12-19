"""Test improved synthesis with player stats detection."""
import asyncio
import json
from pathlib import Path

from src.ir.builder import IRBuilder
from src.processors.synthesizer import ProcessorSynthesizer
from src.db.database import get_database

async def main():
    # Load desired output
    with open("desired_output.txt", "r") as f:
        desired_output = f.read()

    # Build IR from training document
    pdf_path = Path("data/samples/Windom-Worthington.pdf")
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    print("Building DocumentIR...")
    builder = IRBuilder(dpi=300)
    document_ir = builder.build(pdf_bytes, pdf_path.name)
    print(f"  {len(document_ir.blocks)} blocks, {document_ir.page_count} pages")
    print()

    # Synthesize processor with improved prompt
    print("Synthesizing processor with improved rules...")
    synthesizer = ProcessorSynthesizer()
    processor = await synthesizer.synthesize(
        document_ir=document_ir,
        desired_output=desired_output,
        document_type="basketball",
        name="windom_basketball_v2"
    )

    print(f"Generated processor: {processor.name}")
    print(f"  Anchors: {len(processor.anchors)}")
    for anchor in processor.anchors:
        print(f"    - {anchor.name}: {anchor.patterns}")
    print()

    print(f"  Regions: {len(processor.regions)}")
    for region in processor.regions:
        print(f"    - {region.name}: {region.start_anchor} -> {region.end_anchor}")
    print()

    print(f"  Extraction Ops: {len(processor.extraction_ops)}")
    for op in processor.extraction_ops[:10]:  # Show first 10
        print(f"    - {op.field_path} <- {op.source}")
    if len(processor.extraction_ops) > 10:
        print(f"    ... and {len(processor.extraction_ops) - 10} more")
    print()

    print(f"  Calculations: {len(processor.calculations)}")
    for calc in processor.calculations:
        print(f"    - {calc.field} = {calc.formula}")
    print()

    # Show full JSON
    print("Full Processor JSON:")
    processor_json = processor.to_json()
    print(processor_json)
    print()

    # Save to database
    db = await get_database()
    saved_id = await db.create_processor(
        processor_id=processor.id,
        name=processor.name,
        document_type=processor.document_type,
        processor_json=processor_json
    )
    print(f"Saved processor with ID: {saved_id}")

if __name__ == "__main__":
    asyncio.run(main())
