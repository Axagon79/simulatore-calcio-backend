import sys
import os

# --- MAGIC PATH FIX ---
# Calcola il percorso assoluto della cartella root del progetto
# Partendo da dove si trova questo file (utils), saliamo di 2 livelli
current_file_path = os.path.abspath(__file__)
utils_dir = os.path.dirname(current_file_path)
ai_engine_dir = os.path.dirname(utils_dir)
project_root = os.path.dirname(ai_engine_dir)

# Aggiungi la root al path di sistema
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Ora Python può vedere "ai_engine"
try:
    from ai_engine.config import db
except ImportError:
    print(f"❌ Errore ancora! Python sta cercando in: {sys.path}")
    # Fallback estremo
    sys.path.append(os.getcwd())
    from ai_engine.config import db

def check():
    print("🔎 Controllo rapido Braga...")
    
    doc = db.h2h_by_round.find_one(
        {
            "league": "Liga Portugal", 
            "matches": {
                "$elemMatch": {
                    "$or": [{"home": "SC Braga"}, {"home": "Sporting Braga"}]
                }
            }
        }
    )
    
    if not doc:
        print("❌ Nessun match trovato.")
        return

    for m in doc.get("matches", []):
        if m.get("home") in ["SC Braga", "Sporting Braga"]:
            print(f"Squadra: {m.get('home')}")
            curr_id = m.get('home_tm_id')
            print(f"ID: {curr_id}")
            
            if curr_id == 1075:
                print("✅ ID CORRETTO (1075)")
            elif curr_id == 38322:
                print("❌ ID SBAGLIATO (38322 - Bra)")
            else:
                 print(f"⚠️ ID SCONOSCIUTO: {curr_id}")
            return

if __name__ == "__main__":
    check()
