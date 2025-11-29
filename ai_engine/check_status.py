import pymongo

MONGO_URI = "mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/"
client = pymongo.MongoClient(MONGO_URI)
db = client["pup_pals_db"]
avail = db["players_availability_tm"]

# TUTTI gli status presenti in Serie C
all_status = avail.distinct("events.status", {"league_code": "ITA3A"})

print("📋 TUTTI GLI STATUS NEL DATABASE:\n")
for status in sorted(all_status):
    print(f"  - {status}")
