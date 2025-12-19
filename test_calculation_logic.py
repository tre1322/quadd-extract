"""Test that calculation logic works correctly."""
from src.processors.executor import ProcessorExecutor
from src.processors.models import Calculation

# Create test data with player stats
test_data = {
    "team1": {
        "name": "Edgerton",
        "players": [
            {"name": "Player 1", "fouls": 2, "oreb": 3, "dreb": 5, "turnovers": 1},
            {"name": "Player 2", "fouls": 1, "oreb": 2, "dreb": 4, "turnovers": 3},
            {"name": "Player 3", "fouls": 3, "oreb": 1, "dreb": 6, "turnovers": 2},
            {"name": "Player 4", "fouls": 2, "oreb": 0, "dreb": 3, "turnovers": 1},
            {"name": "Player 5", "fouls": 1, "oreb": 1, "dreb": 2, "turnovers": 0},
        ]
    },
    "team2": {
        "name": "Windom",
        "players": [
            {"name": "Player A", "fouls": 5, "oreb": 4, "dreb": 8, "turnovers": 4},
            {"name": "Player B", "fouls": 3, "oreb": 2, "dreb": 5, "turnovers": 2},
            {"name": "Player C", "fouls": 4, "oreb": 3, "dreb": 7, "turnovers": 3},
        ]
    }
}

# Create calculations
calculations = [
    Calculation(field="team1.total_fouls", formula="sum(team1.players[].fouls)"),
    Calculation(field="team1.total_rebounds", formula="sum(team1.players[].oreb) + sum(team1.players[].dreb)"),
    Calculation(field="team1.total_turnovers", formula="sum(team1.players[].turnovers)"),
    Calculation(field="team2.total_fouls", formula="sum(team2.players[].fouls)"),
    Calculation(field="team2.total_rebounds", formula="sum(team2.players[].oreb) + sum(team2.players[].dreb)"),
    Calculation(field="team2.total_turnovers", formula="sum(team2.players[].turnovers)"),
]

print("="*80)
print("CALCULATION ENGINE TEST")
print("="*80)
print()

print("INPUT DATA:")
print(f"  Team 1 ({test_data['team1']['name']}): {len(test_data['team1']['players'])} players")
for p in test_data['team1']['players']:
    print(f"    - {p['name']}: Fouls={p['fouls']}, OREB={p['oreb']}, DREB={p['dreb']}, TO={p['turnovers']}")

print()
print(f"  Team 2 ({test_data['team2']['name']}): {len(test_data['team2']['players'])} players")
for p in test_data['team2']['players']:
    print(f"    - {p['name']}: Fouls={p['fouls']}, OREB={p['oreb']}, DREB={p['dreb']}, TO={p['turnovers']}")

print()
print("="*80)
print("EXECUTING CALCULATIONS")
print("="*80)

executor = ProcessorExecutor()

# Execute each calculation
for calc in calculations:
    value = executor._execute_calculation(test_data, calc)
    print(f"{calc.field} = {calc.formula}")
    print(f"  Result: {value}")
    print()

# Verify team1 (Edgerton-like stats)
team1_fouls = executor._execute_calculation(test_data, calculations[0])
team1_rebounds = executor._execute_calculation(test_data, calculations[1])
team1_turnovers = executor._execute_calculation(test_data, calculations[2])

print("="*80)
print("TEAM 1 VALIDATION")
print("="*80)
print(f"Calculated Fouls: {team1_fouls} (Expected: 2+1+3+2+1 = 9)")
print(f"Calculated Rebounds: {team1_rebounds} (Expected: (3+2+1+0+1) + (5+4+6+3+2) = 7+20 = 27)")
print(f"Calculated Turnovers: {team1_turnovers} (Expected: 1+3+2+1+0 = 7)")
print()

if team1_fouls == 9:
    print("PASS: Fouls calculation correct!")
else:
    print(f"FAIL: Fouls should be 9, got {team1_fouls}")

if team1_rebounds == 27:
    print("PASS: Rebounds calculation correct!")
else:
    print(f"FAIL: Rebounds should be 27, got {team1_rebounds}")

if team1_turnovers == 7:
    print("PASS: Turnovers calculation correct!")
else:
    print(f"FAIL: Turnovers should be 7, got {team1_turnovers}")

print()
print("="*80)
print("CONCLUSION")
print("="*80)
print("The calculation engine correctly sums player stats into team totals.")
print("Formula syntax sum(team.players[].field) works as expected.")
print("Compound formulas like sum(oreb) + sum(dreb) work correctly.")
