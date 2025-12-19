#!/usr/bin/env python3
"""
Test script for Quadd Extract.

Usage:
    # Set your API key
    export ANTHROPIC_API_KEY=your_key_here
    
    # Run tests
    python test_extraction.py path/to/document.pdf
    
    # Or test all sample documents
    python test_extraction.py --all
"""
import asyncio
import json
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.extractors.vision import VisionExtractor
from src.templates.renderer import TemplateRenderer
from src.schemas.common import DocumentType


async def test_extraction(pdf_path: str, template_id: str = None):
    """Test document extraction and rendering."""
    print(f"\n{'='*70}")
    print(f"Testing: {pdf_path}")
    print('='*70)
    
    # Check file exists
    if not os.path.exists(pdf_path):
        print(f"ERROR: File not found: {pdf_path}")
        return None
    
    # Load document
    with open(pdf_path, "rb") as f:
        content = f.read()
    print(f"File size: {len(content):,} bytes")
    
    # Initialize extractor
    extractor = VisionExtractor()
    renderer = TemplateRenderer()
    
    # Step 1: Classify
    print("\n[1/3] Classifying document...")
    doc_type = await extractor.classify_document(content, os.path.basename(pdf_path))
    print(f"      Detected type: {doc_type.value}")
    
    # Step 2: Extract
    print("\n[2/3] Extracting data...")
    result = await extractor.extract(content, os.path.basename(pdf_path), doc_type)
    print(f"      Success: {result.success}")
    print(f"      Confidence: {result.confidence:.0%}")
    print(f"      Tokens used: {result.tokens_used:,}")
    
    if result.warnings:
        print(f"      Warnings: {result.warnings}")
    if result.errors:
        print(f"      Errors: {result.errors}")
        return result
    
    # Show extracted data summary based on type
    print("\n--- Extracted Data Summary ---")
    data = result.data
    
    if doc_type == DocumentType.BASKETBALL and "away_team" in data:
        away = data.get("away_team", {})
        home = data.get("home_team", {})
        
        print(f"\nGame: {away.get('name')} {away.get('final_score')} @ {home.get('name')} {home.get('final_score')}")
        
        if away.get('period_scores'):
            print(f"Periods: {away.get('period_scores')} | {home.get('period_scores')}")
        
        print(f"\n{away.get('name')} Players: {len(away.get('players', []))}")
        for p in away.get('players', [])[:5]:
            print(f"  #{p.get('jersey_number', '?'):>2} {p.get('name', '?'):<18} "
                  f"PTS:{p.get('points', 0):>2} REB:{p.get('total_rebounds', 'N/A')} AST:{p.get('assists', 'N/A')}")
        if len(away.get('players', [])) > 5:
            print(f"  ... and {len(away.get('players', [])) - 5} more")
        
        print(f"\n{home.get('name')} Players: {len(home.get('players', []))}")
        for p in home.get('players', [])[:5]:
            print(f"  #{p.get('jersey_number', '?'):>2} {p.get('name', '?'):<18} "
                  f"PTS:{p.get('points', 0):>2} REB:{p.get('total_rebounds', 'N/A')} AST:{p.get('assists', 'N/A')}")
        if len(home.get('players', [])) > 5:
            print(f"  ... and {len(home.get('players', [])) - 5} more")
    
    elif doc_type == DocumentType.WRESTLING and "matches" in data:
        print(f"\nMeet: {data.get('team_1_name')} {data.get('team_1_score')} vs {data.get('team_2_name')} {data.get('team_2_score')}")
        print(f"Matches: {len(data.get('matches', []))}")
        for m in data.get('matches', [])[:5]:
            print(f"  {m.get('weight_class')}: {m.get('winner_name')} ({m.get('win_type')})")
    
    elif doc_type == DocumentType.GYMNASTICS:
        teams = data.get('teams', [])
        if teams:
            print(f"\nTeam Scores:")
            for t in teams:
                print(f"  {t.get('name')}: {t.get('final_score')}")
    
    else:
        # Generic output
        print(f"\nExtracted keys: {list(data.keys())}")
    
    # Step 3: Render
    print("\n[3/3] Rendering with template...")
    
    if template_id is None:
        template_id = renderer.find_template_for_type(doc_type)
    
    render_result = renderer.render(result, template_id)
    
    if render_result.success:
        print(f"      Template: {render_result.template_id}")
        print("\n" + "="*70)
        print("RENDERED OUTPUT:")
        print("="*70)
        print(render_result.newspaper_text)
        print("="*70)
    else:
        print(f"      Render failed: {render_result.warnings}")
    
    # Save raw data to file
    output_path = pdf_path + ".extracted.json"
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"\nRaw data saved to: {output_path}")
    
    return result


async def main():
    """Main entry point."""
    # Check for API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY environment variable not set")
        print("\nUsage:")
        print("  export ANTHROPIC_API_KEY=your_key_here")
        print("  python test_extraction.py path/to/document.pdf")
        sys.exit(1)
    
    # Get file path from args
    if len(sys.argv) < 2:
        print("Usage: python test_extraction.py <document.pdf> [template_id]")
        print("\nAvailable templates:")
        renderer = TemplateRenderer()
        for t in renderer.list_templates():
            print(f"  - {t['id']}: {t['name']}")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    template_id = sys.argv[2] if len(sys.argv) > 2 else None
    
    await test_extraction(pdf_path, template_id)


if __name__ == "__main__":
    asyncio.run(main())
