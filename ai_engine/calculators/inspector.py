import os
import sys
import json
from datetime import datetime

# --- CONFIGURAZIONE ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR)) 
sys.path.append(PROJECT_ROOT)
sys.path.append(CURRENT_DIR)

# Funzione per stampare JSON formattato (gestisce le date)
def json_serial(obj):
    if isinstance(obj, (datetime)):
        return obj.isoformat()
    raise TypeError (f"Type {type(obj)} not serializable")

try:
    from config import db
    print("✅ Connessione DB OK.\n")
except ImportError as e:
    print(f"❌ Errore importazione: {e}")
    sys.exit(1)

def inspect_collections():
    print(f"{'='*60}")
    print(f"🕵️‍♂️ ISPEZIONE STRUTTURA DATI")
    print(f"{'='*60}")

    # --- 1. ISPEZIONE H2H_BY_ROUND ---
    print("\n📂 COLLEZIONE: h2h_by_round (Campione di 1 documento)")
    doc_round = db["h2h_by_round"].find_one()

    if doc_round:
        print(f"   _id Round: {doc_round.get('_id')}")
        matches = doc_round.get("matches", [])
        print(f"   Numero match nel round: {len(matches)}")
        
        if len(matches) > 0:
            sample_match = matches[0]
            print(f"\n   🔎 STRUTTURA DEL PRIMO MATCH (Chiavi e Tipi):")
            for key, value in sample_match.items():
                # Stampiamo il tipo del valore per capire se è Stringa o Numero (FONDAMENTALE!)
                value_type = type(value).__name__
                preview = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                print(f"      - {key:<20} ({value_type}): {preview}")
        else:
            print("   ⚠️ L'array 'matches' è vuoto!")
    else:
        print("   ❌ Collezione vuota!")

    print("-" * 60)

    # --- 2. ISPEZIONE TEAMS ---
    print("\n📂 COLLEZIONE: teams (Campione di 1 documento)")
    doc_team = db["teams"].find_one()

    if doc_team:
        print(f"   🔎 STRUTTURA TEAM (Chiavi e Tipi):")
        keys_to_show = ["name", "id", "transfermarkt_id", "tm_id", "aliases"]
        
        for key in doc_team.keys():
            # Mostriamo tutto, ma evidenziamo quelli critici
            val = doc_team.get(key)
            val_type = type(val).__name__
            mark = "⭐" if key in keys_to_show else "  "
            print(f"    {mark} {key:<20} ({val_type}): {val}")
    else:
        print("   ❌ Collezione vuota!")

if __name__ == "__main__":
    inspect_collections()