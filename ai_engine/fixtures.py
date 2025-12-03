import sys
import os
from datetime import datetime

# Setup path per config
sys.path.append(os.path.dirname(__file__))
from config import db

def inspect_fixtures():
    print("\n🔍 ISPEZIONE COLLEZIONE 'FIXTURES'")
    print("=" * 60)
    
    fixtures_col = db["fixtures"]
    total = fixtures_col.count_documents({})
    print(f"📚 Totale documenti trovati: {total}")

    if total == 0:
        print("⚠️ La collezione è vuota!")
        return

    # 1. Cerchiamo una partita FUTURA (Next Match)
    # Usiamo una data futura generica o cerchiamo status "Not Started" / "NS"
    future_match = fixtures_col.find_one({
        "$or": [
            {"status.short": "NS"},     # Not Started (standard API-Football)
            {"status": "Scheduled"},    # Possibile variante
            {"match_date": {"$gt": datetime.now()}} # Se hai date datetime
        ]
    })

    print("\n👉 ESEMPIO PARTITA FUTURA (Next Match):")
    if future_match:
        for key, val in future_match.items():
            print(f"   🔹 {key}: {val}")
    else:
        print("   ❌ Nessuna partita futura trovata (o status diverso).")

    # 2. Cerchiamo una partita PASSATA (Finished)
    past_match = fixtures_col.find_one({"status.short": "FT"}) # Full Time
    
    print("\n👉 ESEMPIO PARTITA PASSATA (Finished):")
    if past_match:
        # Stampiamo solo le chiavi principali per brevità
        keys_to_show = ["homeTeam", "awayTeam", "goals", "score", "league", "round", "date"]
        for k in keys_to_show:
            if k in past_match:
                print(f"   🔹 {k}: {past_match[k]}")
    else:
        print("   ❌ Nessuna partita passata trovata.")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    inspect_fixtures()
