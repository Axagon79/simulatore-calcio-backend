"""
LISTA TUTTE LE SQUADRE - Vediamo tutti i nomi esatti
"""

import pymongo

MONGO_URI = "mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/"
DB_NAME = "pup_pals_db"

client = pymongo.MongoClient(MONGO_URI)
db = client[DB_NAME]
teams_col = db["teams"]

print("\n📋 TUTTI I NOMI SQUADRE NEL DATABASE:\n")

all_teams = teams_col.find({}, {"name": 1, "league": 1}).sort("league", 1)

current_league = None
for team in all_teams:
    league = team.get("league", "N/A")
    name = team.get("name", "N/A")
    
    if league != current_league:
        print(f"\n--- {league} ---")
        current_league = league
    
    print(f"  {name}")

print("\n")
