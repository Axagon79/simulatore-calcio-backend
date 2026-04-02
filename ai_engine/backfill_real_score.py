"""
BACKFILL REAL_SCORE — Script one-shot
======================================
Propaga real_score da h2h_by_round a daily_predictions_unified
per tutte le partite storiche. Aggiunge anche hit per ogni pronostico.

Uso: python backfill_real_score.py
"""

import os, sys, re
from datetime import datetime

# --- FIX PERCORSI ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db


def parse_score(score):
    if not score or not isinstance(score, str):
        return None
    parts = re.split(r'[:\-]', score.strip())
    if len(parts) != 2:
        return None
    try:
        home, away = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if home > away:
        sign = '1'
    elif home < away:
        sign = '2'
    else:
        sign = 'X'
    return {'home': home, 'away': away, 'total': home + away, 'sign': sign, 'btts': home > 0 and away > 0}


def check_pronostico(pronostico, tipo, parsed):
    if not parsed or not pronostico:
        return None
    p = pronostico.strip()

    if tipo == 'SEGNO':
        return p == parsed['sign']

    if tipo == 'DOPPIA_CHANCE':
        if p == '1X': return parsed['sign'] in ('1', 'X')
        if p == 'X2': return parsed['sign'] in ('X', '2')
        if p == '12': return parsed['sign'] in ('1', '2')
        return None

    if tipo == 'GOL':
        m = re.match(r'^Over\s+(\d+\.?\d*)$', p, re.IGNORECASE)
        if m:
            return parsed['total'] > float(m.group(1))
        m = re.match(r'^Under\s+(\d+\.?\d*)$', p, re.IGNORECASE)
        if m:
            return parsed['total'] < float(m.group(1))
        if p.lower() == 'goal':
            return parsed['btts']
        if p.lower() == 'nogoal':
            return not parsed['btts']
        m = re.match(r'^MG\s+(\d+)-(\d+)$', p, re.IGNORECASE)
        if m:
            return parsed['total'] >= int(m.group(1)) and parsed['total'] <= int(m.group(2))
        return None

    if tipo == 'X_FACTOR':
        return p == parsed['sign']

    if tipo == 'RISULTATO_ESATTO':
        real = f"{parsed['home']}:{parsed['away']}"
        return p.replace('-', ':') == real

    return None


def main():
    print("=" * 60)
    print("BACKFILL REAL_SCORE — h2h_by_round → daily_predictions_unified")
    print("=" * 60)

    # 1. Costruisci mappa risultati da h2h_by_round
    print("\n Caricamento risultati da h2h_by_round...")
    pipeline = [
        {"$unwind": "$matches"},
        {"$match": {
            "matches.status": "Finished",
            "matches.real_score": {"$ne": None}
        }},
        {"$project": {
            "_id": 0,
            "home": "$matches.home",
            "away": "$matches.away",
            "real_score": "$matches.real_score",
            "date_obj": "$matches.date_obj"
        }}
    ]
    results = list(db.h2h_by_round.aggregate(pipeline))
    print(f"  {len(results)} risultati trovati")

    # Mappa: "home|||away|||date" → real_score
    results_map = {}
    for r in results:
        if r.get('date_obj'):
            date_str = r['date_obj'].strftime('%Y-%m-%d') if isinstance(r['date_obj'], datetime) else str(r['date_obj'])[:10]
            results_map[f"{r['home']}|||{r['away']}|||{date_str}"] = r['real_score']

    print(f"  {len(results_map)} chiavi nella mappa")

    # 2. Aggiorna predictions
    print("\n Aggiornamento daily_predictions_unified...")
    predictions = list(db.daily_predictions_unified.find(
        {},
        {'_id': 1, 'home': 1, 'away': 1, 'date': 1, 'pronostici': 1, 'real_score': 1}
    ))
    print(f"  {len(predictions)} predictions da verificare")

    updated = 0
    skipped = 0
    no_result = 0

    for pred in predictions:
        key = f"{pred.get('home', '')}|||{pred.get('away', '')}|||{pred.get('date', '')}"
        real_score = results_map.get(key)

        if not real_score:
            no_result += 1
            continue

        # Se ha già lo stesso real_score, skip
        if pred.get('real_score') == real_score:
            skipped += 1
            continue

        parsed = parse_score(real_score)
        real_sign = parsed['sign'] if parsed else None

        # Calcola hit per ogni pronostico
        pronostici = pred.get('pronostici', [])
        for p in pronostici:
            if parsed:
                p['hit'] = check_pronostico(p.get('pronostico', ''), p.get('tipo', ''), parsed)
            else:
                p['hit'] = None

        match_hit = any(p.get('hit') is True for p in pronostici)

        db.daily_predictions_unified.update_one(
            {'_id': pred['_id']},
            {'$set': {
                'real_score': real_score,
                'real_sign': real_sign,
                'hit': match_hit,
                'pronostici': pronostici,
                'real_score_updated_at': datetime.utcnow()
            }}
        )
        updated += 1

    print(f"\n Completato!")
    print(f"  {updated} predictions aggiornate con real_score")
    print(f"  {skipped} già aggiornate (skip)")
    print(f"  {no_result} senza risultato in h2h_by_round")


if __name__ == '__main__':
    main()
