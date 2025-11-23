import os
from pymongo import MongoClient
from dotenv import load_dotenv

# Carica la password dal file .env che sta nella cartella functions
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'functions', '.env')
load_dotenv(dotenv_path)

mongo_uri = os.getenv('MONGO_URI')

if not mongo_uri:
    print("❌ ERRORE: Non trovo il file .env o la stringa MONGO_URI")
    exit(1)

try:
    # Connessione al DB
    client = MongoClient(mongo_uri)
    db = client.get_database()
    teams_collection = db['teams']
    print(f"🔌 Connesso al database: {db.name}")

    # Dati di prova basati sulle tue specifiche v3.0
    teams_data = [
        {
            "name": "Juventus",
            "league": "Serie A",
            "country": "Italia",
            "logoUrl": "https://upload.wikimedia.org/wikipedia/commons/b/bc/Juventus_FC_2017_icon_%28black%29.svg",
            # Lucifero
            "form": { "last6": ["W", "W", "D", "L", "W", "L"], "score": 68.25 },
            # Coefficienti
            "stats": {
                "goalsScoredHome": 1.8, "goalsConcededHome": 0.6,
                "goalsScoredAway": 1.2, "goalsConcededAway": 0.9,
                "matchesPlayed": 12
            },
            # Valore Rosa
            "marketValue": 450.00,
            # Classifica
            "standings": { "position": 3, "points": 24 }
        },
        {
            "name": "Genoa",
            "league": "Serie A",
            "country": "Italia",
            "logoUrl": "https://upload.wikimedia.org/wikipedia/en/4/4e/Genoa_cfc.png",
            "form": { "last6": ["L", "L", "D", "L", "W", "L"], "score": 25.50 },
            "stats": {
                "goalsScoredHome": 0.9, "goalsConcededHome": 1.5,
                "goalsScoredAway": 0.5, "goalsConcededAway": 2.0,
                "matchesPlayed": 12
            },
            "marketValue": 95.00,
            "standings": { "position": 17, "points": 10 }
        }
    ]

    print("⏳ Inserimento dati v3.0 nel database...")
    for team in teams_data:
        teams_collection.update_one(
            {"name": team["name"]}, 
            {"$set": team}, 
            upsert=True
        )
        print(f"   -> {team['name']} salvata.")

    print("✅ Fatto! Database aggiornato con la nuova struttura.")

except Exception as e:
    print(f"❌ Errore: {e}")
finally:
    client.close()
