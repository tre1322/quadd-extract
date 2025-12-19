"""Quick test of IRBuilder to verify the fix."""
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)

from src.ir.builder import IRBuilder

# Test with the basketball PDF
pdf_path = Path("data/samples/Windom-Worthington.pdf")

print(f"Testing IRBuilder with {pdf_path}")
print(f"PDF exists: {pdf_path.exists()}")

if pdf_path.exists():
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    builder = IRBuilder(dpi=300)
    document_ir = builder.build(pdf_bytes, pdf_path.name)

    print(f"\nSuccess!")
    print(f"Extracted {len(document_ir.blocks)} blocks")
    print(f"Extracted {len(document_ir.tables)} tables")
    print(f"Pages: {document_ir.page_count}")
    print(f"Layout hash: {document_ir.layout_hash}")

    # Show first few blocks
    print(f"\nFirst 10 blocks:")
    for i, block in enumerate(document_ir.blocks[:10]):
        print(f"  {i}: '{block.text}' at ({block.bbox.x0:.2f}, {block.bbox.y0:.2f})")
else:
    print("PDF not found!")
