import sys
import os
import pprint

# --- FIX PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
grandparent_dir = os.path.dirname(parent_dir)
sys.path.append(parent_dir)     # Per ai_engine
sys.path.append(grandparent_dir) # Per la root del progetto

try:
    from config import db
except ImportError:
    # Fallback brutale: prova a cercare config nella cartella corrente o sopra
    sys.path.append(os.path.join(grandparent_dir, 'simulatore-calcio-backend'))
    try:
        from config import db
    except ImportError:
        print("❌ IMPOSSIBILE TROVARE config.py. Controlla i percorsi.")
        sys.exit(1)

def check_data_quality():
    print("🕵️‍♂️ CONTROLLO QUALITÀ DATI H2H")
    
    # Cerchiamo Modena vs Sampdoria (o simile)
    # Usiamo una regex per essere sicuri di trovarlo anche se i nomi sono leggermente diversi
    doc = db.raw_h2h_data.find_one({"matches": {"$exists": True, "$not": {"$size": 0}}})
    
    if not doc:
        print("❌ Database vuoto o nessun documento con partite!")
        return

    print(f"Match Trovato: {doc.get('team_a')} vs {doc.get('team_b')}")
    matches = doc.get("matches", [])
    print(f"Totale partite storiche: {len(matches)}")
    
    print("\n--- ANALISI PRIME 5 PARTITE ---")
    for i, m in enumerate(matches[:5]): 
        print(f"\n[Riga {i}]")
        print(f"  Date: {m.get('date')}")
        print(f"  Score: {m.get('score')}")
        print(f"  Winner field: {m.get('winner')}")
        # Vediamo se c'è qualche campo nascosto utile
        print(f"  Dati Grezzi: {m}")

if __name__ == "__main__":
    check_data_quality()
