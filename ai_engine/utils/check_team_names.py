import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

teams = db["teams"]
avail = db["players_availability_tm"]

print("📊 NOMI SQUADRE Serie C - GIRONE A\n")
print("=" * 70)

# Nomi in teams
print("DA teams collection:")
teams_names = teams.find({"league": "Serie C - Girone A"}, {"name": 1})
for t in teams_names:
    print(f"  - {t['name']}")

print("\n" + "=" * 70)

# Nomi in players_availability_tm
print("\nDA players_availability_tm collection:")
avail_names = avail.distinct("team_name", {"league_code": "ITA3A"})
for name in sorted(avail_names):
    print(f"  - {name}")

print("\n" + "=" * 70)
print("\n🔍 TROVA LE DIFFERENZE!")