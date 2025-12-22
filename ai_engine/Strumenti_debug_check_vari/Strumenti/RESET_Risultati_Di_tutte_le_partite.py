import os
import sys
from datetime import datetime

# --- CONFIGURAZIONE PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir))
project_root = os.path.dirname(ai_engine_dir)

if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from config import db
    print(f"✅ DB Connesso: {db.name}")
except ImportError:
    print("❌ Errore Import Config")
    sys.exit(1)

# --- CONFIGURAZIONE ---
COLLECTION_NAME = "h2h_by_round"

def run_full_reset():
    print("☢️  ATTENZIONE: AVVIO RESET TOTALE DEI RISULTATI...")
    print("    Tutti i punteggi verranno cancellati e le partite impostate su 'Scheduled'.")
    
    # Conferma utente (opzionale, per sicurezza nello script manuale)
    confirm = input("    Sei sicuro di voler procedere? (scrivi 'SI' per confermare): ")
    if confirm != "SI":
        print("    Operazione annullata.")
        return

    col = db[COLLECTION_NAME]
    docs = col.find({})
    
    docs_modified = 0
    matches_reset = 0
    
    for doc in docs:
        matches = doc.get("matches", [])
        doc_was_modified = False
        
        for m in matches:
            # Resetta se c'è un risultato o se lo stato non è Scheduled
            if m.get('real_score') is not None or m.get('status') == 'Finished':
                m['real_score'] = None
                m['status'] = "Scheduled"
                doc_was_modified = True
                matches_reset += 1
        
        if doc_was_modified:
            col.update_one(
                {"_id": doc["_id"]},
                {"$set": {"matches": matches}}
            )
            docs_modified += 1
            print(f"    🔄 Reset documento: {doc['_id']}")

    print("="*50)
    print("✅ RESET COMPLETATO.")
    print(f"📄 Documenti aggiornati: {docs_modified}")
    print(f"⚽ Partite resettate: {matches_reset}")

if __name__ == "__main__":
    run_full_reset()