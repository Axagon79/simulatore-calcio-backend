"""Verifica che tutte le squadre in tutte le classifiche abbiano il transfermarkt_id."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import db

docs = list(db.classifiche.find({}, {"league": 1, "table": 1, "table_home": 1, "table_away": 1}))

missing = []
total_teams = 0
total_ok = 0

for doc in docs:
    league = doc.get("league", "?")
    for label in ["table", "table_home", "table_away"]:
        for row in doc.get(label, []):
            team = row.get("team", "?")
            tm_id = row.get("transfermarkt_id")
            total_teams += 1
            if tm_id is None:
                missing.append((league, label, team))
            else:
                total_ok += 1

print(f"Campionati: {len(docs)}")
print(f"Totale voci: {total_teams} ({total_ok} con tm_id, {len(missing)} senza)")
print()

if missing:
    print(f"{'='*70}")
    print(f"SQUADRE SENZA TRANSFERMARKT_ID: {len(missing)}")
    print(f"{'='*70}")
    current_league = None
    for league, label, team in sorted(missing):
        if league != current_league:
            print(f"\n  {league}:")
            current_league = league
        print(f"    [{label}] {team}")
else:
    print("Tutte le squadre hanno il transfermarkt_id!")
