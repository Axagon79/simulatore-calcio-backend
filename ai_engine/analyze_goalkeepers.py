"""
ANALISI PORTIERI - Verifica integrità dati
"""

import pymongo

MONGO_URI = "mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/"
DB_NAME = "pup_pals_db"

client = pymongo.MongoClient(MONGO_URI)
db = client[DB_NAME]
gk_col = db["players_stats_fbref_gk"]


def analyze_goalkeepers():
    """
    Analizza i portieri nel database e categorizza per qualità dei dati
    """
    print("\n" + "="*70)
    print("🥅 ANALISI PORTIERI (GK)")
    print("="*70)
    
    # 1. TOTALE DOCUMENTI
    total_docs = gk_col.count_documents({})
    print(f"\n📊 Totale documenti collection: {total_docs}")
    
    # 2. PORTIERI CON RATING (non NULL, non mancante)
    with_rating = list(gk_col.find({
        "rating": {"$exists": True, "$ne": None, "$type": "number"}
    }))
    
    count_with_rating = len(with_rating)
    print(f"\n✅ Portieri CON rating definito: {count_with_rating} ({count_with_rating/total_docs*100:.1f}%)")
    
    # 3. PORTIERI SENZA RATING
    without_rating = gk_col.count_documents({
        "$or": [
            {"rating": {"$exists": False}},
            {"rating": None},
            {"rating": {"$type": "null"}}
        ]
    })
    
    print(f"❌ Portieri SENZA rating (NULL): {without_rating} ({without_rating/total_docs*100:.1f}%)")
    
    # 4. DI QUELLI CON RATING: QUANTI RISPETTANO 4-10
    valid_range = [p for p in with_rating if 4 <= p["rating"] <= 10]
    invalid_range = [p for p in with_rating if p["rating"] < 4 or p["rating"] > 10]
    
    print(f"\n📋 PORTIERI CON RATING (breakdown):")
    print(f"   ✅ Range valido (4.0 - 10.0): {len(valid_range)} ({len(valid_range)/count_with_rating*100:.1f}%)")
    print(f"   ❌ Range NON valido (<4 o >10): {len(invalid_range)} ({len(invalid_range)/count_with_rating*100:.1f}%)")
    
    # 5. DETTAGLI RATING NON VALIDI
    if invalid_range:
        print(f"\n⚠️  PORTIERI CON RATING ANOMALO:")
        for i, gk in enumerate(invalid_range[:20], 1):
            player_name = gk.get("player", "N/A")
            squad = gk.get("squad", "N/A")
            league = gk.get("league", "N/A")
            rating = gk.get("rating", "N/A")
            print(f"   {i:2}. {player_name:30} | {squad:20} | {league:15} | Rating: {rating}")
        
        if len(invalid_range) > 20:
            print(f"   ... e altri {len(invalid_range) - 20} portieri")
    
    # 6. DETTAGLI PORTIERI SENZA RATING (primi 20)
    if without_rating > 0:
        print(f"\n❌ PORTIERI SENZA RATING (primi 20):")
        no_rating_docs = list(gk_col.find({
            "$or": [
                {"rating": {"$exists": False}},
                {"rating": None}
            ]
        }).limit(20))
        
        for i, gk in enumerate(no_rating_docs, 1):
            player_name = gk.get("player", "N/A")
            squad = gk.get("squad", "N/A")
            league = gk.get("league", "N/A")
            print(f"   {i:2}. {player_name:30} | {squad:20} | {league:15}")
    
    # 7. STATISTICHE PER LEGA
    print(f"\n📊 BREAKDOWN PER LEGA:")
    print(f"{'Lega':<20} | {'Totali':>7} | {'Con rating':>10} | {'Validi 4-10':>12} | {'NULL':>6}")
    print("-" * 70)
    
    # Trova tutte le leghe uniche
    all_leagues = gk_col.distinct("league")
    
    for league in sorted(all_leagues):
        if not league or league == "N/A":
            continue
        
        total_league = gk_col.count_documents({"league": league})
        with_rating_league = gk_col.count_documents({
            "league": league,
            "rating": {"$exists": True, "$ne": None, "$type": "number"}
        })
        valid_league = gk_col.count_documents({
            "league": league,
            "rating": {"$gte": 4, "$lte": 10}
        })
        null_league = total_league - with_rating_league
        
        print(f"{league:<20} | {total_league:>7} | {with_rating_league:>10} | {valid_league:>12} | {null_league:>6}")
    
    # 8. RIEPILOGO FINALE
    print("\n" + "="*70)
    print("📋 RIEPILOGO PORTIERI")
    print("="*70)
    print(f"   Totale documenti: {total_docs}")
    print(f"   ✅ Con rating valido (4-10): {len(valid_range)} ({len(valid_range)/total_docs*100:.1f}%)")
    print(f"   ⚠️  Con rating anomalo (<4 o >10): {len(invalid_range)} ({len(invalid_range)/total_docs*100:.1f}%)")
    print(f"   ❌ Senza rating (NULL): {without_rating} ({without_rating/total_docs*100:.1f}%)")
    print("="*70)
    
    # 9. RACCOMANDAZIONI
    print("\n💡 RACCOMANDAZIONI:")
    
    if without_rating > total_docs * 0.5:
        print("   ❌ CRITICO: Più del 50% dei portieri ha rating NULL")
        print("   → Probabilmente lo scraper ha fallito completamente")
        print("   → Consiglio: rieseguire lo scraper GK da zero")
    elif without_rating > total_docs * 0.1:
        print("   ⚠️  ATTENZIONE: Oltre il 10% dei portieri ha rating NULL")
        print("   → Alcuni scraping sono falliti")
        print("   → Consiglio: identificare quali leghe e ri-scrappare quelle")
    else:
        print("   ✅ Situazione accettabile: meno del 10% di NULL")
        print("   → Puoi procedere con pulizia selettiva")
    
    if len(invalid_range) > 0:
        print(f"\n   ⚠️  Trovati {len(invalid_range)} portieri con rating fuori range (4-10)")
        print("   → Controlla manualmente questi casi")
        print("   → Potrebbero essere errori di parsing o dati corrotti")
    
    print("\n")


if __name__ == "__main__":
    analyze_goalkeepers()
