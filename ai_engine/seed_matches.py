import os
from datetime import datetime, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv

# Carica variabili ambiente
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'functions', '.env')
load_dotenv(dotenv_path)
mongo_uri = os.getenv('MONGO_URI')

try:
    client = MongoClient(mongo_uri)
    db = client.get_database()
    
    # 1. Trova gli ID delle squadre che abbiamo appena creato
    juve = db.teams.find_one({"name": "Juventus"})
    genoa = db.teams.find_one({"name": "Genoa"})

    if not juve or not genoa:
        print("❌ Errore: Non trovo Juventus o Genoa nel DB. Hai fatto il seed_teams?")
        exit(1)

    print(f"✅ Trovate squadre: {juve['name']} vs {genoa['name']}")

    # 2. Dati della partita
    match_data = {
        "homeTeam": juve["_id"],
        "awayTeam": genoa["_id"],
        "league": "Serie A",
        "round": "Giornata 13",
        "date": datetime.now() + timedelta(days=7), # Tra 7 giorni
        "status": "SCHEDULED",
        "odds": {
            "one": 1.45,   # Juve favorita
            "x": 4.50,
            "two": 7.00,
            "under25": 1.90,
            "over25": 1.80
        }
    }

    # 3. Salva nel DB
    db.matches.insert_one(match_data)
    print("⚽ Partita Juventus-Genoa inserita nel calendario!")

except Exception as e:
    print(f"❌ Errore: {e}")
finally:
    client.close()
