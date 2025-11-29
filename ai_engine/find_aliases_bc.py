import pymongo

MONGO_URI = "mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/"
client = pymongo.MongoClient(MONGO_URI)
db = client["pup_pals_db"]
teams = db["teams"]
avail = db["players_availability_tm"]

gironi = {
    "ITA3B": "Serie C - Girone B",
    "ITA3C": "Serie C - Girone C"
}

for league_code, league_name in gironi.items():
    print(f"\n{'='*70}")
    print(f"🏆 {league_name}")
    print(f"{'='*70}\n")
    
    # Nomi in teams
    print("DA teams collection:")
    teams_names = list(teams.find({"league": league_name}, {"name": 1}))
    teams_list = sorted([t['name'] for t in teams_names])
    for name in teams_list:
        print(f"  - {name}")
    
    print(f"\nDA players_availability_tm collection:")
    avail_names = sorted(avail.distinct("team_name", {"league_code": league_code}))
    for name in avail_names:
        print(f"  - {name}")
