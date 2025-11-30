import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

# CONFIGURAZIONE
teams_col = db['teams']

def check_missing():
    print("🔍 ANALISI SQUADRE SENZA PUNTI (HOME/AWAY)...")

    # Cerchiamo documenti che NON hanno il campo ranking.homePoints
    # Oppure dove ranking esiste ma homePoints no
    missing_cursor = teams_col.find({
        "$or": [
            {"ranking.homePoints": {"$exists": False}},
            {"ranking.awayPoints": {"$exists": False}}
        ]
    })

    missing_teams = list(missing_cursor)

    if not missing_teams:
        print("✅ Tutto perfetto! Tutte le squadre hanno i punti.")
        return

    print(f"⚠️ Trovate {len(missing_teams)} squadre incomplete.")
    print("-" * 40)

    by_league = {}

    for t in missing_teams:
        league = t.get('ranking', {}).get('league', 'Sconosciuto')
        name = t.get('name', 'Senza Nome')

        if league not in by_league:
            by_league[league] = []
        by_league[league].append(name)

    for league, names in by_league.items():
        print(f"📂 {league}: {len(names)} squadre mancanti")
        for n in names:
            print(f"   - {n}")
        print("")

if __name__ == "__main__":
    check_missing()