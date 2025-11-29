"""
ESPLORA pup_pals_db - Trova collection squadre
"""

import pymongo

MONGO_URI = "mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/"
DB_NAME = "pup_pals_db"

client = pymongo.MongoClient(MONGO_URI)
db = client[DB_NAME]

print("\n" + "="*60)
print(f"📊 DATABASE: {DB_NAME}")
print("="*60)

# Lista tutte le collection
collections = db.list_collection_names()
print(f"\n📂 Collection trovate ({len(collections)}):\n")

for i, coll_name in enumerate(collections, 1):
    coll = db[coll_name]
    count = coll.count_documents({})
    print(f"{i}. {coll_name} → {count} documenti")

print("\n" + "="*60)
print("\n🔍 Cerco collection con squadre (Inter, Napoli, ecc.)...")
print("="*60)

for coll_name in collections:
    coll = db[coll_name]
    
    # Cerca documento con "Inter" o "Napoli"
    team_doc = coll.find_one({"name": {"$in": ["Inter", "Napoli", "Milan", "Juventus"]}})
    
    if team_doc:
        print(f"\n✅ TROVATA! Collection: '{coll_name}'")
        print(f"   Documenti totali: {coll.count_documents({})}")
        
        print(f"\n📄 Esempio documento ({team_doc.get('name', 'Sconosciuto')}):")
        print("-" * 60)
        
        # Mostra campi principali
        for key in list(team_doc.keys())[:15]:
            value = team_doc[key]
            if isinstance(value, (str, int, float, bool)):
                print(f"  {key}: {value}")
            else:
                print(f"  {key}: {type(value).__name__}")
        
        print("\n" + "="*60)
        print(f"\n✅ USA QUESTA COLLECTION: '{coll_name}'")
        print("="*60)
        break
else:
    print("\n❌ Non trovata collection con squadre")

print("\n")
