"""
validate_daily.py — Job di validazione notturno

Confronta le predizioni giornaliere con i risultati reali delle partite.
Per ogni predizione:
  1. Cerca il risultato reale in h2h_by_round (campo real_score)
  2. Verifica hit/miss per ogni pronostico
  3. Aggiorna il documento daily_predictions con verified=True + risultati
  4. Aggiorna la collection validation_metrics con aggregati giornalieri

Pensato per essere eseguito come cron job / Cloud Scheduler ogni notte.
Uso: python validate_daily.py [YYYY-MM-DD]  (default: ieri)
"""

import sys
import os
import re
from datetime import datetime, timedelta

# Setup path per importare config.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import db


# --- HELPER: Parse real_score "2:1" → dict ---
def parse_score(real_score):
    if not real_score or not isinstance(real_score, str):
        return None
    parts = real_score.split(':')
    if len(parts) != 2:
        return None
    try:
        home = int(parts[0])
        away = int(parts[1])
    except ValueError:
        return None
    if home > away:
        sign = '1'
    elif home < away:
        sign = '2'
    else:
        sign = 'X'
    return {
        'home': home, 'away': away,
        'total': home + away, 'sign': sign,
        'btts': home > 0 and away > 0
    }


# --- HELPER: Verifica un singolo pronostico ---
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
        over_match = re.match(r'^Over\s+(\d+\.?\d*)$', p, re.IGNORECASE)
        if over_match:
            return parsed['total'] > float(over_match.group(1))
        under_match = re.match(r'^Under\s+(\d+\.?\d*)$', p, re.IGNORECASE)
        if under_match:
            return parsed['total'] < float(under_match.group(1))
        if p.lower() == 'goal':
            return parsed['btts']
        if p.lower() == 'nogoal':
            return not parsed['btts']
        return None

    return None


# --- Carica mappa risultati reali da h2h_by_round ---
def load_results_map():
    results_map = {}
    docs = db['h2h_by_round'].find({}, {
        'matches.home': 1, 'matches.away': 1,
        'matches.real_score': 1, 'matches.status': 1,
        'matches.date_obj': 1
    })
    for doc in docs:
        for m in doc.get('matches', []):
            if m.get('status') == 'Finished' and m.get('real_score') and m.get('date_obj'):
                date_str = m['date_obj'].strftime('%Y-%m-%d') if hasattr(m['date_obj'], 'strftime') else str(m['date_obj'])[:10]
                key = f"{m['home']}|||{m['away']}|||{date_str}"
                results_map[key] = m['real_score']
    return results_map


# --- Calcola hit rate ---
def hit_rate(total, hits):
    return round((hits / total) * 100, 1) if total > 0 else None


# --- MAIN: Valida un giorno ---
def validate_date(target_date):
    target_str = target_date.strftime('%Y-%m-%d')
    print(f"\n{'='*60}")
    print(f"  VALIDAZIONE PRONOSTICI: {target_str}")
    print(f"{'='*60}")

    # 1. Carica predizioni del giorno
    predictions = list(db['daily_predictions'].find({'date': target_str}))
    if not predictions:
        print(f"  Nessuna predizione trovata per {target_str}")
        return None

    print(f"  {len(predictions)} predizioni trovate")

    # 2. Carica risultati reali
    results_map = load_results_map()
    print(f"  {len(results_map)} risultati reali in memoria")

    # 3. Verifica ogni predizione
    stats = {
        'date': target_str,
        'total_predictions': len(predictions),
        'verified': 0,
        'pending': 0,
        'globale': {'total': 0, 'hits': 0, 'misses': 0},
        'per_mercato': {},
        'per_campionato': {},
        'per_confidence_band': {'60-70': {'t': 0, 'h': 0}, '70-80': {'t': 0, 'h': 0}, '80-90': {'t': 0, 'h': 0}, '90+': {'t': 0, 'h': 0}},
        'per_stelle_band': {'2.5-3': {'t': 0, 'h': 0}, '3-4': {'t': 0, 'h': 0}, '4-5': {'t': 0, 'h': 0}},
    }

    for pred in predictions:
        key = f"{pred['home']}|||{pred['away']}|||{pred['date']}"
        real_score = results_map.get(key)

        if not real_score:
            stats['pending'] += 1
            continue

        parsed = parse_score(real_score)
        if not parsed:
            stats['pending'] += 1
            continue

        stats['verified'] += 1
        pronostici = pred.get('pronostici', [])
        pronostici_results = []
        pred_has_hit = False

        for p in pronostici:
            hit = check_pronostico(p.get('pronostico'), p.get('tipo'), parsed)
            if hit is None:
                pronostici_results.append({**p, 'hit': None})
                continue

            pronostici_results.append({**p, 'hit': hit})

            # Aggregazione globale
            stats['globale']['total'] += 1
            if hit:
                stats['globale']['hits'] += 1
                pred_has_hit = True
            else:
                stats['globale']['misses'] += 1

            # Per mercato
            tipo = p.get('tipo', 'ALTRO')
            if tipo not in stats['per_mercato']:
                stats['per_mercato'][tipo] = {'total': 0, 'hits': 0, 'misses': 0}
            stats['per_mercato'][tipo]['total'] += 1
            if hit:
                stats['per_mercato'][tipo]['hits'] += 1
            else:
                stats['per_mercato'][tipo]['misses'] += 1

            # Per campionato
            league = pred.get('league', 'N/A')
            if league not in stats['per_campionato']:
                stats['per_campionato'][league] = {'total': 0, 'hits': 0, 'misses': 0}
            stats['per_campionato'][league]['total'] += 1
            if hit:
                stats['per_campionato'][league]['hits'] += 1
            else:
                stats['per_campionato'][league]['misses'] += 1

            # Per confidence band
            conf = p.get('confidence', 0)
            if conf >= 90: band = '90+'
            elif conf >= 80: band = '80-90'
            elif conf >= 70: band = '70-80'
            else: band = '60-70'
            stats['per_confidence_band'][band]['t'] += 1
            if hit:
                stats['per_confidence_band'][band]['h'] += 1

            # Per stelle band
            st = p.get('stars', 0)
            if st >= 4: sband = '4-5'
            elif st >= 3: sband = '3-4'
            else: sband = '2.5-3'
            stats['per_stelle_band'][sband]['t'] += 1
            if hit:
                stats['per_stelle_band'][sband]['h'] += 1

        # 4. Aggiorna documento daily_predictions con risultati verifica
        db['daily_predictions'].update_one(
            {'_id': pred['_id']},
            {'$set': {
                'verified': True,
                'real_score': real_score,
                'real_sign': parsed['sign'],
                'pronostici': pronostici_results,
                'hit': pred_has_hit,
                'verified_at': datetime.utcnow()
            }}
        )

    # 5. Calcola hit_rate per ogni breakdown
    g = stats['globale']
    g['hit_rate'] = hit_rate(g['total'], g['hits'])

    for m in stats['per_mercato'].values():
        m['hit_rate'] = hit_rate(m['total'], m['hits'])
    for c in stats['per_campionato'].values():
        c['hit_rate'] = hit_rate(c['total'], c['hits'])
    for band_data in stats['per_confidence_band'].values():
        band_data['hit_rate'] = hit_rate(band_data['t'], band_data['h'])
    for band_data in stats['per_stelle_band'].values():
        band_data['hit_rate'] = hit_rate(band_data['t'], band_data['h'])

    # 6. Salva snapshot in validation_metrics
    db['validation_metrics'].update_one(
        {'date': target_str},
        {'$set': stats},
        upsert=True
    )

    # 7. Report
    print(f"\n  RISULTATI:")
    print(f"  Verificate: {stats['verified']} | Pending: {stats['pending']}")
    print(f"  Globale: {g['hits']}/{g['total']} = {g['hit_rate']}%")
    print(f"\n  Per mercato:")
    for tipo, data in stats['per_mercato'].items():
        print(f"    {tipo}: {data['hits']}/{data['total']} = {data['hit_rate']}%")
    print(f"\n  Per campionato:")
    for league, data in stats['per_campionato'].items():
        print(f"    {league}: {data['hits']}/{data['total']} = {data['hit_rate']}%")
    print(f"\n  Per confidence:")
    for band, data in stats['per_confidence_band'].items():
        if data['t'] > 0:
            print(f"    {band}: {data['h']}/{data['t']} = {data['hit_rate']}%")
    print(f"\n  Per stelle:")
    for band, data in stats['per_stelle_band'].items():
        if data['t'] > 0:
            print(f"    {band}: {data['h']}/{data['t']} = {data['hit_rate']}%")

    return stats


# --- Entry point ---
if __name__ == '__main__':
    if len(sys.argv) > 1:
        target = datetime.strptime(sys.argv[1], '%Y-%m-%d')
    else:
        target = datetime.utcnow() - timedelta(days=1)

    result = validate_date(target)

    if result:
        print(f"\n  Validazione completata. Snapshot salvato in validation_metrics.")
    else:
        print(f"\n  Nessun dato da validare.")
