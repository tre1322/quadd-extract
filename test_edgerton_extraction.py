"""Test extraction on Windom-Edgerton game to validate the fix."""
import asyncio
import json
from pathlib import Path

from src.ir.builder import IRBuilder
from src.processors.executor import ProcessorExecutor
from src.processors.models import Processor
from src.db.database import get_database

async def main():
    # Load the latest processor
    db = await get_database()
    processor_id = "040deef4-e8c1-4d92-9e8b-3c183756ab88"  # windom_basketball_complete

    print("="*80)
    print("TESTING: Extraction with Calculations")
    print("="*80)
    print(f"Processor ID: {processor_id}")
    print()

    processor_data = await db.get_processor(processor_id)
    processor = Processor.from_json(processor_data['processor_json'])

    print(f"Processor has {len(processor.calculations)} calculations:")
    for calc in processor.calculations:
        print(f"  - {calc.field} = {calc.formula}")
    print()

    # Build IR from training document first to validate fix
    pdf_path = Path("data/samples/Windom-Worthington.pdf")
    print(f"Processing: {pdf_path} (training document)")

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    print("Building DocumentIR...")
    builder = IRBuilder(dpi=300)
    document_ir = builder.build(pdf_bytes, pdf_path.name)
    print(f"  {len(document_ir.blocks)} blocks, {document_ir.page_count} pages")
    print()

    # Execute extraction
    print("Executing processor...")
    executor = ProcessorExecutor()

    try:
        result = executor.execute(document_ir, processor)

        print("="*80)
        print("EXTRACTION RESULT")
        print("="*80)
        print(json.dumps(result, indent=2, default=str))
        print()

        # Check for Edgerton stats
        print("="*80)
        print("WORTHINGTON TEAM STATS VALIDATION")
        print("="*80)

        # Find which team is Worthington
        worthington_team = None
        worthington_key = None

        for key in ['team1', 'team2']:
            if key in result:
                team_name = result[key].get('name', '').lower()
                if 'worthington' in team_name or 'wor' in team_name:
                    worthington_team = result[key]
                    worthington_key = key
                    break

        if worthington_team:
            print(f"Found Worthington as: {worthington_key}")
            print(f"Team Name: {worthington_team.get('name', 'MISSING')}")
            print()

            fouls = worthington_team.get('total_fouls', 0)
            rebounds = worthington_team.get('total_rebounds', 0)
            turnovers = worthington_team.get('total_turnovers', 0)

            print("CALCULATED TEAM TOTALS:")
            print(f"  Fouls:     {fouls} (Expected: 11)")
            print(f"  Rebounds:  {rebounds} (Expected: 47)")
            print(f"  Turnovers: {turnovers} (Expected: 23)")
            print()

            # Check player count
            player_count = len(worthington_team.get('players', []))
            print(f"  Players extracted: {player_count}")

            if player_count > 0:
                print(f"\n  Sample players:")
                for i, player in enumerate(worthington_team.get('players', [])[:3]):
                    print(f"    {i+1}. {player}")

            print()

            # Validation
            fouls_correct = abs(fouls - 11) < 1
            rebounds_correct = abs(rebounds - 47) < 1
            turnovers_correct = abs(turnovers - 23) < 1

            print("VALIDATION:")
            print(f"  Fouls correct:     {'PASS' if fouls_correct else 'FAIL'}")
            print(f"  Rebounds correct:  {'PASS' if rebounds_correct else 'FAIL'}")
            print(f"  Turnovers correct: {'PASS' if turnovers_correct else 'FAIL'}")
            print()

            if fouls_correct and rebounds_correct and turnovers_correct:
                print("SUCCESS! All Worthington stats are correct!")
                confidence = 100.0
            elif player_count > 0:
                confidence = 50.0
                print("Players extracted but calculations incorrect")
            else:
                confidence = 0.0
                print("FAILED! No player data extracted")
        else:
            print("Could not find Worthington team in results")
            confidence = 0.0

            # Show what teams we did find
            print("\nTeams found:")
            for key in ['team1', 'team2']:
                if key in result:
                    print(f"  {key}: {result[key].get('name', 'UNNAMED')}")

        print()
        print("="*80)
        print(f"CONFIDENCE SCORE: {confidence}%")
        print("="*80)

    except Exception as e:
        print(f"EXTRACTION FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
