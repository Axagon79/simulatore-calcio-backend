import os
import sys
from pprint import pprint

# FIX PERCORSI
current_path = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.dirname(os.path.dirname(current_path))
sys.path.append(root_path)

try:
    from config import db
except ImportError:
    sys.path.append(os.path.join(root_path, 'ai_engine'))
    from config import db

print("🔍 CERCO L'ULTIMA GIORNATA DI SERIE A IN 'h2h_by_round'...")

# Prende tutti i documenti della Serie A
cursor = db.h2h_by_round.find({"league": "Serie A"})
rounds = list(cursor)

if not rounds:
    print("❌ Nessuna giornata trovata per la Serie A!")
else:
    # Ordina in base al nome (es. Giornata 1, Giornata 2...)
    # Metodo grezzo ma efficace per vedere l'ultima inserita
    def get_num(r):
        import re
        try:
            return int(re.search(r'\d+', r.get('round_name', '0')).group())
        except: return 0
    
    rounds.sort(key=get_num)
    
    last_round = rounds[-1]
    print(f"\n🏆 ULTIMA GIORNATA TROVATA: {last_round.get('round_name')}")
    print("-" * 50)
    
    matches = last_round.get('matches', [])
    print(f"Partite totali in questa giornata: {len(matches)}")
    
    print("\nEcco le prime 3 partite (vediamo se c'è il risultato):")
    for m in matches[:3]:
        print(f"🏠 {m.get('home')} - ✈️ {m.get('away')}")
        print(f"   STATUS: {m.get('status')}")
        print(f"   RISULTATO REALE: {m.get('real_score')}  <-- QUESTO È IL CAMPO CHIAVE")
        print("-" * 20)
