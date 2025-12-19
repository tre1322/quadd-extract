"""Check what blocks are being sent to the LLM."""
from pathlib import Path
from src.ir.builder import IRBuilder

pdf_path = Path("data/samples/Windom-Worthington.pdf")
with open(pdf_path, "rb") as f:
    pdf_bytes = f.read()

builder = IRBuilder(dpi=300)
document_ir = builder.build(pdf_bytes, pdf_path.name)

print(f"Total blocks: {len(document_ir.blocks)}")
print(f"First 100 blocks sent to LLM:")
print()

for i, block in enumerate(document_ir.blocks[:100]):
    print(f"Block {i}: '{block.text}' at position ({block.bbox.x0:.2f}, {block.bbox.y0:.2f}) page={block.bbox.page} size={block.font_size:.0f}pt type={block.block_type}")

print("\n\nBlocks on page 2 (where player stats are):")
page2_blocks = [b for b in document_ir.blocks if b.bbox.page == 1]  # page 1 = second page (0-indexed)
print(f"Total page 2 blocks: {len(page2_blocks)}")
for i, block in enumerate(page2_blocks[:50]):
    print(f"Block {i}: '{block.text}' at ({block.bbox.x0:.2f}, {block.bbox.y0:.2f})")
