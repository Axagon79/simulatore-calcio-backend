import os
import sys
from datetime import datetime

# --- CONFIGURAZIONE PERCORSI (Uguale al tuo script) ---
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

def reset_all_results():
    """Cancella tutti i risultati (real_score) senza toccare i documenti."""
    print("\n🧹 RESET RISULTATI IN CORSO...")
    
    col = db[COLLECTION_NAME]
    total_matches_reset = 0
    total_docs_modified = 0
    
    # Prendiamo tutti i documenti
    all_docs = col.find({})
    
    for doc in all_docs:
        doc_id = doc.get("_id")
        matches = doc.get("matches", [])
        modified = False
        
        for match in matches:
            # Se la partita ha un risultato, lo resettiamo
            if match.get('real_score') is not None:
                match['real_score'] = None
                match['status'] = "Scheduled"  # Torniamo allo stato "non giocata"
                modified = True
                total_matches_reset += 1
        
        # Aggiorniamo il documento solo se abbiamo modificato qualcosa
        if modified:
            col.update_one(
                {"_id": doc_id},
                {"$set": {"matches": matches, "last_updated": datetime.now()}}
            )
            total_docs_modified += 1
            print(f"   ✅ {doc_id}: resettate le partite")
    
    print(f"\n🏁 COMPLETATO!")
    print(f"   📄 Documenti modificati: {total_docs_modified}")
    print(f"   ⚽ Partite resettate: {total_matches_reset}")

if __name__ == "__main__":
    # Chiediamo conferma prima di procedere (sicurezza)
    risposta = input("\n⚠️  Vuoi RESETTARE tutti i risultati? (scrivi SI per confermare): ")
    
    if risposta.strip().upper() == "SI":
        reset_all_results()
    else:
        print("❌ Operazione annullata.")
