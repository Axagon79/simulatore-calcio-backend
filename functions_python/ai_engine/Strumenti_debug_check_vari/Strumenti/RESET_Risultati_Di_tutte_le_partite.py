import os
import sys

# Aggiungiamo il percorso del progetto per trovare config.py
# Risaliamo di 3 livelli: Strumenti -> Strumenti_debug... -> ai_engine -> Progetto
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.append(BASE_DIR)

try:
    from config import db
    print("✅ Connessione al database caricata correttamente da config.py")
except ImportError:
    print("❌ Errore: Non trovo config.py. Assicurati che i percorsi siano corretti.")
    sys.exit(1)

def svuota_numeretti_affidabilità():
    # Usiamo la collezione corretta
    h2h_collection = db['h2h_by_round']
    
    # Verifichiamo se il database risponde
    try:
        documents = list(h2h_collection.find({}))
    except Exception as e:
        print(f"❌ Errore di connessione: {e}")
        return

    print(f"🧹 Inizio svuotamento numeretti su {len(documents)} giornate...")

    count = 0
    for doc in documents:
        matches_array = doc.get('matches', [])
        modificato = False
        
        for index, match in enumerate(matches_array):
            h2h = match.get('h2h_data', {})
            
            # Se esiste la sezione affidabilità, svuotiamo solo i numeretti
            if h2h and 'affidabilità' in h2h:
                h2h['affidabilità']['affidabilità_casa'] = None
                h2h['affidabilità']['affidabilità_trasferta'] = None
                h2h['affidabilità']['last_update'] = "Resettato"
                
                modificato = True
                count += 1

        # Salviamo la giornata con i campi svuotati
        if modificato:
            h2h_collection.update_one(
                {"_id": doc['_id']},
                {"$set": {"matches": matches_array}}
            )

    print(f"✅ Reset completato! Svuotati {count} match.")

if __name__ == "__main__":
    svuota_numeretti_affidabilità()