"""Debug script to check how blocks are grouped into rows."""
import asyncio
from pathlib import Path
from src.ir.builder import IRBuilder
from src.processors.executor import ProcessorExecutor
from src.processors.models import Processor
from src.db.database import get_database

async def main():
    # Load processor
    db = await get_database()
    processor_id = "f6e1456d-5188-4fb8-8fa3-a88c5ade224d"
    processor_data = await db.get_processor(processor_id)
    processor = Processor.from_json(processor_data['processor_json'])

    # Build IR
    pdf_path = Path("data/samples/Windom-Worthington.pdf")
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    builder = IRBuilder(dpi=300)
    document_ir = builder.build(pdf_bytes, pdf_path.name)

    # Execute to get regions
    executor = ProcessorExecutor()

    # Find anchors
    anchor_positions = executor._find_anchors(document_ir, processor.anchors)
    print(f"Found {len(anchor_positions)} anchors:")
    for name, block in anchor_positions.items():
        print(f"  {name}: '{block.text}' at page={block.bbox.page}, y={block.bbox.y0:.3f}")
    print()

    # Define regions
    regions = executor._define_regions(document_ir, anchor_positions, processor.regions)
    print(f"Found {len(regions)} regions:")
    for name, blocks in regions.items():
        print(f"  {name}: {len(blocks)} blocks")
    print()

    # Check team1_players region
    if 'team1_players' in regions:
        print("=" * 80)
        print("TEAM1_PLAYERS REGION ANALYSIS")
        print("=" * 80)

        blocks = regions['team1_players']
        print(f"Total blocks: {len(blocks)}")
        print()

        # Group by row
        rows = executor._group_blocks_by_row(blocks)
        print(f"Grouped into {len(rows)} rows:")
        print()

        for i, row in enumerate(rows[:15]):  # Show first 15 rows
            print(f"Row {i} ({len(row)} blocks):")
            for block in row:
                print(f"  '{block.text}' at x={block.bbox.x0:.3f}, y={block.bbox.y0:.3f}")
            print()

if __name__ == "__main__":
    asyncio.run(main())
