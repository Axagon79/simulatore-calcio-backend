import pymongo

MONGO_URI = "mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/"
client = pymongo.MongoClient(MONGO_URI)
db = client["pup_pals_db"]
teams = db["teams"]

# DEBUG ESATTO Lecco e Vicenza
for team_name in ["Lecco", "Vicenza"]:
    team = teams.find_one({"name": team_name})
    if team:
        strength = team.get("strengthScore09")
        print(f"\n🔍 {team_name}:")
        print(f"  strengthScore09 = {strength}")
        print(f"  stats.strengthScore09 = {team.get('stats', {}).get('strengthScore09')}")
        print(f"  Tipo: {type(strength)}")
    else:
        print(f"\n❌ {team_name} NON TROVATA")
