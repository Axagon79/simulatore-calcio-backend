"""
Sync one-time: copia le quote SNAI (O/U + GG/NG) da h2h_by_round a daily_predictions_sandbox.
Matcha su home_mongo_id + away_mongo_id.
Da lanciare una volta sola.
"""
import os, sys

current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db

SNAI_FIELDS = ['over_15', 'under_15', 'over_25', 'under_25', 'over_35', 'under_35', 'gg', 'ng']

print("Lettura h2h_by_round...")
updated = 0
skipped = 0
scanned = 0

for doc in db.h2h_by_round.find({}):
    for m in doc.get('matches', []):
        odds = m.get('odds', {})
        if not odds.get('ts_ou_gg'):
            continue

        home_id = m.get('home_mongo_id')
        away_id = m.get('away_mongo_id')
        if not home_id or not away_id:
            continue

        scanned += 1
        snai_fields = {k: v for k, v in odds.items() if k in SNAI_FIELDS and v is not None}
        if not snai_fields:
            continue

        dp_update = {f"odds.{k}": v for k, v in snai_fields.items()}
        dp_update["odds.src_ou_gg"] = "SNAI"
        dp_update["odds.ts_ou_gg"] = odds['ts_ou_gg']

        result = db.daily_predictions_sandbox.update_many(
            {"home_mongo_id": home_id, "away_mongo_id": away_id, "odds.ts_ou_gg": {"$exists": False}},
            {"$set": dp_update}
        )
        updated += result.modified_count
        skipped += result.matched_count - result.modified_count  # già avevano le quote

print(f"Partite con quote SNAI in h2h_by_round: {scanned}")
print(f"✅ Sandbox aggiornati (da h2h): {updated} pronostici")
print(f"⏩ Già con quote (saltati): {skipped}")

# --- PASS 2: fallback da daily_predictions (produzione) ---
print("\nFallback: lettura daily_predictions (produzione)...")
updated2 = 0
scanned2 = 0

for doc in db.daily_predictions.find({"odds.ts_ou_gg": {"$exists": True}}):
    odds = doc.get('odds', {})
    home_id = doc.get('home_mongo_id')
    away_id = doc.get('away_mongo_id')
    if not home_id or not away_id:
        continue

    scanned2 += 1
    snai_fields = {k: v for k, v in odds.items() if k in SNAI_FIELDS and v is not None}
    if not snai_fields:
        continue

    dp_update = {f"odds.{k}": v for k, v in snai_fields.items()}
    dp_update["odds.src_ou_gg"] = odds.get("src_ou_gg", "SNAI")
    dp_update["odds.ts_ou_gg"] = odds["ts_ou_gg"]

    result = db.daily_predictions_sandbox.update_many(
        {"home_mongo_id": home_id, "away_mongo_id": away_id, "odds.ts_ou_gg": {"$exists": False}},
        {"$set": dp_update}
    )
    updated2 += result.modified_count

print(f"Pronostici con quote SNAI in produzione: {scanned2}")
print(f"✅ Sandbox aggiornati (da produzione): {updated2} pronostici")
print(f"\n🏁 TOTALE sandbox aggiornati: {updated + updated2}")
