"""
ANALISI COMPLETA DATABASE
Mostra struttura di tutte le collection e documenti esempio
"""

import pymongo
from pprint import pprint

MONGO_URI = "mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/"
DB_NAME = "pup_pals_db"

client = pymongo.MongoClient(MONGO_URI)
db = client[DB_NAME]


def analyze_collection(collection_name, collection):
    """
    Analizza una singola collection e mostra struttura
    """
    print("\n" + "="*80)
    print(f"📂 COLLECTION: {collection_name}")
    print("="*80)
    
    # 1. Count totale
    total = collection.count_documents({})
    print(f"\n📊 Totale documenti: {total}")
    
    if total == 0:
        print("   ⚠️  Collection vuota!")
        return
    
    # 2. Prendi un documento esempio COMPLETO
    sample_doc = collection.find_one({})
    
    print(f"\n📋 STRUTTURA DOCUMENTO (primo esempio):")
    print("-" * 80)
    
    # Funzione ricorsiva per mostrare struttura annidata
    def print_structure(obj, indent=0):
        prefix = "   " * indent
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == "_id":
                    continue
                if isinstance(value, dict):
                    print(f"{prefix}📁 {key}: (Object)")
                    print_structure(value, indent + 1)
                elif isinstance(value, list):
                    print(f"{prefix}📋 {key}: (Array, len={len(value)})")
                    if len(value) > 0:
                        print(f"{prefix}   Esempio primo elemento:")
                        print_structure(value[0], indent + 2)
                else:
                    value_type = type(value).__name__
                    value_str = str(value)[:50]  # Max 50 caratteri
                    print(f"{prefix}📄 {key}: {value_type} = {value_str}")
        else:
            print(f"{prefix}   {type(obj).__name__} = {str(obj)[:50]}")
    
    print_structure(sample_doc)
    
    # 3. Lista TUTTI i campi unici presenti nella collection
    print(f"\n📑 TUTTI I CAMPI UNICI nella collection:")
    all_keys = set()
    
    # Campiona primi 100 documenti per trovare tutti i campi
    for doc in collection.find({}).limit(100):
        all_keys.update(doc.keys())
    
    all_keys.discard("_id")
    print(f"   {', '.join(sorted(all_keys))}")
    
    # 4. Cerca campo "rating" in varie forme
    print(f"\n🔍 RICERCA CAMPO RATING:")
    
    # Possibili nomi
    rating_variants = [
        "rating",
        "rating_puro",
        "gk_rating",
        "def_rating", 
        "mid_rating",
        "att_rating"
    ]
    
    for variant in rating_variants:
        # Campo diretto
        count_direct = collection.count_documents({variant: {"$exists": True}})
        if count_direct > 0:
            print(f"   ✅ '{variant}' (diretto): {count_direct} documenti")
            
            # Mostra esempio valore
            example = collection.find_one({variant: {"$exists": True}}, {variant: 1})
            if example:
                print(f"      Esempio valore: {example.get(variant)}")
        
        # Campo annidato (es. gk_rating.rating_puro)
        nested_field = f"{variant}.rating_puro"
        count_nested = collection.count_documents({nested_field: {"$exists": True}})
        if count_nested > 0:
            print(f"   ✅ '{nested_field}' (annidato): {count_nested} documenti")
            
            # Mostra esempio valore
            example = collection.find_one({nested_field: {"$exists": True}}, {variant: 1})
            if example:
                print(f"      Esempio valore: {example.get(variant)}")
    
    # 5. Cerca campo "player/player_name" in varie forme
    print(f"\n🔍 RICERCA CAMPO GIOCATORE:")
    player_variants = ["player", "player_name", "player_name_fbref", "name"]
    
    for variant in player_variants:
        count = collection.count_documents({variant: {"$exists": True}})
        if count > 0:
            print(f"   ✅ '{variant}': {count} documenti")
            
            # Mostra esempi
            examples = list(collection.find({variant: {"$exists": True}}, {variant: 1}).limit(3))
            for ex in examples:
                print(f"      - {ex.get(variant)}")
    
    # 6. Cerca campo "squad/team" in varie forme
    print(f"\n🔍 RICERCA CAMPO SQUADRA:")
    team_variants = ["squad", "team", "team_name", "team_name_fbref", "club"]
    
    for variant in team_variants:
        count = collection.count_documents({variant: {"$exists": True}})
        if count > 0:
            print(f"   ✅ '{variant}': {count} documenti")
            
            # Mostra esempi
            examples = list(collection.find({variant: {"$exists": True}}, {variant: 1}).limit(3))
            for ex in examples:
                print(f"      - {ex.get(variant)}")
    
    # 7. Cerca campo "league" in varie forme
    print(f"\n🔍 RICERCA CAMPO LEGA:")
    league_variants = ["league", "league_name", "league_code", "competition"]
    
    for variant in league_variants:
        count = collection.count_documents({variant: {"$exists": True}})
        if count > 0:
            print(f"   ✅ '{variant}': {count} documenti")
            
            # Mostra valori unici
            unique_values = collection.distinct(variant)
            print(f"      Valori: {', '.join(map(str, unique_values[:10]))}")
    
    # 8. Mostra 2 documenti completi come esempio
    print(f"\n📄 ESEMPI DOCUMENTI COMPLETI (2):")
    print("-" * 80)
    
    for i, doc in enumerate(collection.find({}).limit(2), 1):
        print(f"\n--- Documento {i} ---")
        # Rimuovi _id per leggibilità
        doc_copy = {k: v for k, v in doc.items() if k != "_id"}
        pprint(doc_copy, width=80, compact=False)


def analyze_complete_database():
    """
    Analizza tutte le collection del database
    """
    print("\n" + "="*80)
    print("🔍 ANALISI COMPLETA DATABASE")
    print("="*80)
    print(f"\nDatabase: {DB_NAME}")
    print(f"URI: {MONGO_URI[:50]}...")
    
    # Lista tutte le collection
    all_collections = db.list_collection_names()
    print(f"\n📚 Collection trovate ({len(all_collections)}):")
    for coll in all_collections:
        count = db[coll].count_documents({})
        print(f"   - {coll}: {count} documenti")
    
    # Analizza le 4 collection giocatori
    target_collections = {
        "players_stats_fbref_gk": "PORTIERI",
        "players_stats_fbref_def": "DIFENSORI",
        "players_stats_fbref_mid": "CENTROCAMPISTI",
        "players_stats_fbref_att": "ATTACCANTI"
    }
    
    for coll_name, description in target_collections.items():
        if coll_name in all_collections:
            analyze_collection(f"{description} ({coll_name})", db[coll_name])
        else:
            print(f"\n⚠️  Collection '{coll_name}' non trovata!")
    
    # Riepilogo finale
    print("\n" + "="*80)
    print("📊 RIEPILOGO MAPPING CAMPI")
    print("="*80)
    print("\nPer creare il mapping corretto, devi dirmi:")
    print("1. Quale campo contiene il RATING (es. gk_rating.rating_puro)?")
    print("2. Quale campo contiene il NOME GIOCATORE (es. player_name_fbref)?")
    print("3. Quale campo contiene la SQUADRA (es. team_name_fbref)?")
    print("4. Quale campo contiene la LEGA (es. league_code o league_name)?")
    print("5. Quale campo contiene i MINUTI GIOCATI?")
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    analyze_complete_database()
