import os
from pymongo import MongoClient, UpdateMany # <-- Usiamo UpdateMany

# --- CONFIGURAZIONE ---
MONGO_URI="mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/football_simulator_db?retryWrites=true&w=majority&appName=pup-pals-cluster"
DB_NAME = "football_simulator_db"

def sync_all_rounds_with_country():
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    
    col_classifiche = db["classifiche"]
    col_h2h = db["h2h_by_round"]

    print("🔍 Mappatura nazioni dalla collezione 'classifiche'...")
    
    # 1. Creiamo la mappa Leghe -> Nazioni
    mapping = {}
    for doc in col_classifiche.find({}, {"league": 1, "country": 1}):
        league = doc.get("league")
        country = doc.get("country")
        if league and country:
            mapping[league] = country

    if not mapping:
        print("❌ Errore: Nessun dato in 'classifiche'.")
        return

    # 2. Aggiornamento MASSIVO di tutti i documenti
    # UpdateMany aggiornerà TUTTI i documenti (tutte le giornate) che hanno quella lega
    print(f"⏳ Inizio aggiornamento di tutte le giornate per {len(mapping)} campionati...")
    
    total_modified = 0
    for league_name, country_name in mapping.items():
        # Questo comando dice: "Trova TUTTI i documenti di questa lega e aggiungi il paese"
        result = col_h2h.update_many(
            {"league": league_name}, 
            {"$set": {"country": country_name}}
        )
        if result.modified_count > 0:
            print(f"✅ {league_name}: aggiornate {result.modified_count} giornate con '{country_name}'")
            total_modified += result.modified_count

    print(f"\n✨ Operazione completata. Totale documenti aggiornati: {total_modified}")
    client.close()

if __name__ == "__main__":
    sync_all_rounds_with_country()