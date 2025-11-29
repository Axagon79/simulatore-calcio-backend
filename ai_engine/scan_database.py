import pymongo

MONGO_URI = "mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/pup_pals_db?retryWrites=true&w=majority"
client = pymongo.MongoClient(MONGO_URI)
db = client["pup_pals_db"]

print("📊 DATABASE pup_pals_db - TUTTE LE COLLECTIONS")
print("=" * 70)

# Lista tutte le collections
collections = db.list_collection_names()
print(f"\n🗂️  COLLECTIONS TOTALI: {len(collections)}\n")

for coll_name in sorted(collections):
    collection = db[coll_name]
    count = collection.count_documents({})
    
    print(f"\n{'='*70}")
    print(f"📁 {coll_name}")
    print(f"   Record totali: {count}")
    
    if count > 0:
        # Prendi 1 documento esempio
        sample = collection.find_one()
        print(f"\n   📋 CAMPI DISPONIBILI:")
        for key in sorted(sample.keys()):
            value = sample[key]
            tipo = type(value).__name__
            
            # Mostra valore abbreviato
            if isinstance(value, dict):
                sub_keys = list(value.keys())[:3]
                print(f"      {key}: dict → {sub_keys}...")
            elif isinstance(value, list):
                print(f"      {key}: array[{len(value)}]")
            else:
                val_str = str(value)[:50]
                print(f"      {key}: {tipo} = {val_str}")
    
print(f"\n{'='*70}")
print("✅ SCAN COMPLETO!")
