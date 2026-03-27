"""
backfill_giornata.py
Aggiunge il campo 'giornata' (numero round) ai documenti in daily_predictions_unified
che non lo hanno, cercando in h2h_by_round.

Uso:
    python backfill_giornata.py
"""

import os, sys, re
from datetime import datetime

current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db


def main():
    coll = db['daily_predictions_unified']
    h2h = db['h2h_by_round']

    # Trova tutti i pronostici senza giornata
    missing = list(coll.find(
        {'giornata': {'$exists': False}},
        {'home': 1, 'away': 1, 'league': 1, 'date': 1}
    ))
    print(f"📊 {len(missing)} pronostici senza campo 'giornata'")

    if not missing:
        print("✅ Tutti i pronostici hanno già il campo giornata")
        return

    # Raggruppa per lega per efficienza
    by_league = {}
    for doc in missing:
        league = doc.get('league', '')
        if league not in by_league:
            by_league[league] = []
        by_league[league].append(doc)

    updated = 0
    not_found = 0

    for league, docs in sorted(by_league.items()):
        # Carica tutti i round di questa lega
        rounds = list(h2h.find(
            {'league': league},
            {'round_name': 1, 'matches.home': 1, 'matches.away': 1, 'matches.date_obj': 1}
        ))

        # Costruisci mappa (home, away) → round_number
        match_to_round = {}
        for r in rounds:
            rname = r.get('round_name', '')
            rnum_match = re.search(r'(\d+)', rname)
            rnum = int(rnum_match.group(1)) if rnum_match else None
            if rnum is None:
                continue
            for m in r.get('matches', []):
                match_to_round[(m.get('home', ''), m.get('away', ''))] = rnum

        # Aggiorna i documenti
        league_updated = 0
        for doc in docs:
            key = (doc.get('home', ''), doc.get('away', ''))
            rnum = match_to_round.get(key)
            if rnum:
                coll.update_one(
                    {'_id': doc['_id']},
                    {'$set': {'giornata': rnum}}
                )
                league_updated += 1
            else:
                not_found += 1

        updated += league_updated
        if league_updated:
            print(f"  ✅ {league}: {league_updated}/{len(docs)} aggiornati")
        else:
            print(f"  ⚠️ {league}: 0/{len(docs)} (round non trovati)")

    print(f"\n{'='*50}")
    print(f"🏁 COMPLETATO: {updated} aggiornati, {not_found} non trovati")


if __name__ == '__main__':
    main()
