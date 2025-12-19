"""Check what text blocks are actually in the document."""
from pathlib import Path
from src.ir.builder import IRBuilder

pdf_path = Path("data/samples/Windom-Worthington.pdf")
with open(pdf_path, "rb") as f:
    pdf_bytes = f.read()

builder = IRBuilder(dpi=300)
document_ir = builder.build(pdf_bytes, pdf_path.name)

print(f"Total blocks: {len(document_ir.blocks)}")
print(f"Pages: {document_ir.page_count}")
print()

# Show first 50 blocks to see what text is there
print("First 50 blocks:")
for i, block in enumerate(document_ir.blocks[:50]):
    print(f"{i}: '{block.text}' at ({block.bbox.x0:.2f}, {block.bbox.y0:.2f}) page={block.bbox.page}")

print("\n\nSearching for anchor patterns:")
print("'Box Score Report':", len(document_ir.find_text("Box Score Report")))
print("'Box':", len(document_ir.find_text("Box")))
print("'Score':", len(document_ir.find_text("Score")))
print("'Report':", len(document_ir.find_text("Report")))
print("'Period Stats':", len(document_ir.find_text("Period Stats")))
print("'Team Stats':", len(document_ir.find_text("Team Stats")))
print("'WHS':", len(document_ir.find_text("WHS")))
print("'Worthington':", len(document_ir.find_text("Worthington")))
