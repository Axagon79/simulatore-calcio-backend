import pymongo

MONGO_URI = "**********************************************************************"
client = pymongo.MongoClient(MONGO_URI)
db = client["pup_pals_db"]
avail = db["players_availability_tm"]

# Top 5 giocatori Vicenza
vicenza = list(avail.find({"team_name": "LR Vicenza", "league_code": "ITA3A"}).limit(5))

for p in vicenza:
    print(f"\n{p['player_name']} ({p['position_short']}):")
    events = p.get('events', [])[-10:]
    
    stati = {}
    for e in events:
        s = e.get('status')
        stati[s] = stati.get(s, 0) + 1
    
    print(f"  Ultimi 10: {stati}")
