import pymongo

MONGO_URI = "mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/pup_pals_db?retryWrites=true&w=majority"
client = pymongo.MongoClient(MONGO_URI)
db = client['pup_pals_db']
teams = db['teams']

# Mappa Nome Tuo DB -> Nome SoccerStats
updates = {
    # Italia
    "Inter": "Internazionale",

    # Spagna
    "Barcellona": "Barcelona",
    "Athletic Club": "Athletic Bilbao", # Spesso chiamato così su siti stats
    "Siviglia": "Sevilla",

    # Germania
    "Bayern": "Bayern Munich",
    "Eintracht": "Eintracht Frankfurt",
    "Lipsia": "RB Leipzig",
    "Stoccarda": "VfB Stuttgart",
    "Werder Brema": "Werder Bremen",
    "Friburgo": "SC Freiburg",
    "Magonza": "Mainz 05",
    "Augusta": "Augsburg",
    "Union Berlino": "Union Berlin",
    "Amburgo": "Hamburger SV",
    "Colonia": "FC Koln", # O FC Köln

    # Francia
    "PSG": "Paris Saint Germain", # O Paris SG, proviamo il lungo
    "Marsiglia": "Marseille",
    "Strasburgo": "Strasbourg",
    "Nizza": "Nice",
    "Tolosa": "Toulouse"
}

print("🔧 Inizio FIX Aliases...")
count = 0

for db_name, soccerstats_name in updates.items():
    # Aggiorniamo il campo aliases.soccerstats
    res = teams.update_one(
        {"name": db_name},
        {"$set": {"aliases.soccerstats": soccerstats_name}}
    )

    if res.matched_count > 0:
        print(f"✅ {db_name} -> Alias impostato a '{soccerstats_name}'")
        count += 1
    else:
        print(f"⚠️ Squadra '{db_name}' non trovata nel DB. Controlla lo spelling.")

print(f"\nFinito. Aggiornati {count} alias.")