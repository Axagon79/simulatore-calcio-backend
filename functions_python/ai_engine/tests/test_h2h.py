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

# Cerca ESATTAMENTE Genoa vs Inter
result = db.h2h_by_round.find_one({
    "matches": {
        "$elemMatch": {
            "home": "Genoa",
            "away": "Inter"
        }
    }
})

if result:
    # Trova il match specifico nell'array
    match = None
    for m in result.get('matches', []):
        if m['home'] == 'Genoa' and m['away'] == 'Inter':
            match = m
            break
    
    if match:
        print(f"🔍 Partita: {match['home']} vs {match['away']}")
        print(f"📅 Data: {match.get('date_obj', 'N/A')}")
        print(f"\n📊 h2h_data:")
        if 'h2h_data' in match:
            h2h = match['h2h_data']
            print(f"   home_score: {h2h.get('home_score', 'MISSING')}")
            print(f"   away_score: {h2h.get('away_score', 'MISSING')}")
            print(f"   h2h_weight: {h2h.get('h2h_weight', 'MISSING')}")
            print(f"   history_summary: {h2h.get('history_summary', 'MISSING')}")
        else:
            print("   ❌ CAMPO h2h_data NON PRESENTE!")
    else:
        print("❌ Match Genoa-Inter non trovato nell'array matches")
else:
    print("❌ Documento con Genoa-Inter non trovato")
    
# test_match_h2h.py (AGGIUNGI ALLA FINE)

import json

print(f"\n📄 DUMP COMPLETO h2h_data:")
if 'h2h_data' in match:
    print(json.dumps(match['h2h_data'], indent=2, default=str))
else:
    print("   ❌ Campo h2h_data non presente!")

print(f"\n🔧 CHIAVI PRESENTI nel match:")
print(f"   {list(match.keys())}")