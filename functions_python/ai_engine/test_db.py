import sys
import os

# Aggiungiamo il percorso per trovare config.py se necessario
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("--- TEST CONNESSIONE MONGO ---")
    from config import db
    
    # 1. Vediamo se il database risponde
    db_name = db.name
    print(f"✅ Connesso al Database: {db_name}")

    # 2. Elenchiamo TUTTE le collezioni disponibili per vedere se il nome è giusto
    collezioni = db.list_collection_names()
    print(f"✅ Collezioni trovate nel DB: {collezioni}")

    if "h2h_by_round" in collezioni:
        print("✅ Collezione 'h2h_by_round' TROVATA.")
        
        # 3. Proviamo a estrarre le nazioni con la sintassi corretta
        nations = db["h2h_by_round"].distinct("country")
        print(f"✅ Risultato query nazioni: {nations}")
        
        if not nations:
            print("⚠️ La query ha restituito una lista vuota. Vediamo un documento per capire:")
            esempio = db["h2h_by_round"].find_one()
            print(f"DEBUG DOCUMENTO: {esempio}")
    else:
        print("❌ ERRORE: La collezione 'h2h_by_round' NON ESISTE in questo database.")
        print("Verifica il nome nel file config.py o su Atlas.")

except Exception as e:
    print(f"❌ ERRORE CRITICO: {str(e)}")