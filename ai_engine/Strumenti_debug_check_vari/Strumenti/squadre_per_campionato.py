import sys
import os
sys.path.insert(0, r"C:\Progetti\simulatore-calcio-backend")
from config import db
from collections import Counter

teams = db.teams

# Conta squadre per campionato
stats = Counter()
for team in teams.find({}, {'league': 1}):
    stats[team['league']] += 1

print("🏆 CAMPIONATI NEL DATABASE")
print("=" * 60)
print(f"{'Campionato':<25} {'Squadre':<6} {'OK?'}")
print("-" * 60)

for campionato, count in sorted(stats.items()):
    print(f"{campionato:<25} {count:<6} {'✅' if 10 <= count <= 38 else '⚠️'}")

print(f"\n📊 TOTALE SQUADRE: {teams.count_documents({})}")
