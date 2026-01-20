
import sys
import os
# --- CONFIGURAZIONE PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
grandparent_dir = os.path.dirname(parent_dir)
sys.path.insert(0, grandparent_dir) 
sys.path.insert(0, parent_dir)
sys.path.insert(0, current_dir)
from config import db
from calculators.calculate_h2h_v2 import get_h2h_score_v2

# ID reali da db.teams
genoa_id = "69242272d4d47773ce4edbda"
inter_id = "69235915d4d47773ce4e95e8"

print("🧪 Test get_h2h_score_v2()")
print(f"Genoa ID: {genoa_id}")
print(f"Inter ID: {inter_id}")
print("\n" + "="*50)

result = get_h2h_score_v2("Genoa", "Inter", genoa_id, inter_id)

print("\n📊 RISULTATO:")
print(f"home_score: {result.get('home_score', 'MISSING')}")
print(f"away_score: {result.get('away_score', 'MISSING')}")
print(f"avg_goals_home: {result.get('avg_goals_home', 'MISSING')}")
print(f"avg_goals_away: {result.get('avg_goals_away', 'MISSING')}")
print(f"\nhistory_summary: {result.get('history_summary', 'MISSING')}")