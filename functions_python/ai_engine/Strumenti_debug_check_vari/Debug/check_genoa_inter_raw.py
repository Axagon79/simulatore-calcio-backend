# check_genoa_inter_raw.py
from config import db

# Cerca tutte le varianti possibili
queries = [
    {"team_a": "Genoa", "team_b": "Inter"},
    {"team_a": "Inter", "team_b": "Genoa"},
    {"team_a": {"$regex": "genoa", "$options": "i"}, "team_b": {"$regex": "inter", "$options": "i"}},
    {"team_a": {"$regex": "inter", "$options": "i"}, "team_b": {"$regex": "genoa", "$options": "i"}}
]

for i, q in enumerate(queries):
    doc = db.raw_h2h_data_v2.find_one(q)
    if doc:
        print(f"✅ Query {i+1} trovata: {doc['_id']}")
        print(f"   team_a: {doc.get('team_a')}")
        print(f"   team_b: {doc.get('team_b')}")
        print(f"   team_a_id: {doc.get('team_a_id')}")
        print(f"   team_b_id: {doc.get('team_b_id')}")
        print(f"   Partite: {len(doc.get('matches', []))}")
        break
else:
    print("❌ Nessun documento H2H trovato per Genoa-Inter")
    
    # Cerca cosa esiste per Genoa
    genoa_docs = list(db.raw_h2h_data_v2.find({
        "$or": [
            {"team_a": {"$regex": "genoa", "$options": "i"}},
            {"team_b": {"$regex": "genoa", "$options": "i"}}
        ]
    }).limit(5))
    
    print(f"\n📋 Documenti con 'Genoa' (primi 5):")
    for doc in genoa_docs:
        print(f"   • {doc['_id']}")