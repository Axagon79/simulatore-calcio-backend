"""
snapshot_nightly.py — Salva snapshot nightly in prediction_versions

Gira DOPO lo step 31 (orchestratore MoE).
Per ogni match del giorno (da h2h_by_round):
- Se presente in daily_predictions_unified → snapshot con pronostici
- Se assente (scartato) → snapshot con pronostici: [] (NO BET)
"""

import sys
import os
import argparse
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import db

h2h_collection = db['h2h_by_round']
unified_collection = db['daily_predictions_unified']
versions_collection = db['prediction_versions']


def normalize_match_key(date_str, home, away):
    """Genera match_key normalizzato: lowercase, spazi → underscore."""
    home_norm = home.strip().lower().replace(' ', '_')
    away_norm = away.strip().lower().replace(' ', '_')
    return f"{date_str}_{home_norm}_{away_norm}"


def get_today_range(target_date=None):
    if target_date:
        today = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    return today, tomorrow


def get_all_matches(target_date=None):
    """Recupera TUTTE le partite del giorno da h2h_by_round."""
    today, tomorrow = get_today_range(target_date)

    pipeline = [
        {"$unwind": "$matches"},
        {"$match": {"matches.date_obj": {"$gte": today, "$lt": tomorrow}}},
        {"$project": {
            "league": 1,
            "match": "$matches"
        }}
    ]

    matches = []
    for doc in h2h_collection.aggregate(pipeline):
        m = doc['match']
        m['_league'] = doc.get('league', 'Unknown')
        matches.append(m)

    return matches


def run_snapshot_nightly(target_date=None):
    today, _ = get_today_range(target_date)
    date_str = today.strftime('%Y-%m-%d')

    print(f"\n📸 Snapshot nightly per {date_str}")

    # 1. Tutte le partite del giorno
    all_matches = get_all_matches(target_date)
    print(f"   Partite totali da h2h_by_round: {len(all_matches)}")

    if not all_matches:
        print("   Nessuna partita trovata. Skip.")
        return 0

    # 2. Pronostici unified del giorno
    unified_docs = list(unified_collection.find({'date': date_str}))
    unified_index = {}
    for doc in unified_docs:
        key = normalize_match_key(date_str, doc['home'], doc['away'])
        unified_index[key] = doc

    print(f"   Pronostici unified: {len(unified_docs)}")

    # 3. Elimina eventuali snapshot nightly precedenti per questa data
    versions_collection.delete_many({'date': date_str, 'version': 'nightly'})

    # 4. Crea snapshot per ogni match
    snapshots = []
    no_bet_count = 0

    for match in all_matches:
        home = match.get('home', '')
        away = match.get('away', '')
        if not home or not away:
            continue

        match_key = normalize_match_key(date_str, home, away)
        unified_doc = unified_index.get(match_key)

        # Recupera mongo_id da unified_doc o dal match h2h
        home_mongo_id = (unified_doc or {}).get('home_mongo_id') or match.get('home_mongo_id', '')
        away_mongo_id = (unified_doc or {}).get('away_mongo_id') or match.get('away_mongo_id', '')

        snapshot = {
            'match_key': match_key,
            'date': date_str,
            'home': home,
            'away': away,
            'league': match.get('_league', ''),
            'match_time': match.get('match_time', ''),
            'home_mongo_id': home_mongo_id,
            'away_mongo_id': away_mongo_id,
            'version': 'nightly',
            'created_at': datetime.now(timezone.utc),
            'pronostici': [],
            'changes': [],
        }

        if unified_doc:
            snapshot['pronostici'] = unified_doc.get('pronostici', [])
            snapshot['odds'] = unified_doc.get('odds', {})
        else:
            snapshot['odds'] = match.get('odds', {})
            no_bet_count += 1

        snapshots.append(snapshot)

    if snapshots:
        versions_collection.insert_many(snapshots)

    print(f"   ✅ Snapshot salvati: {len(snapshots)} ({no_bet_count} NO BET)")
    return len(snapshots)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Snapshot Nightly — prediction_versions')
    parser.add_argument('date', nargs='?', help='Data YYYY-MM-DD (default: oggi)')
    args = parser.parse_args()

    target = None
    if args.date:
        target = datetime.strptime(args.date, '%Y-%m-%d').replace(tzinfo=timezone.utc)

    run_snapshot_nightly(target)
