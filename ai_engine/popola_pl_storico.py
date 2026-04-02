"""
POPOLA PL_STORICO — Script one-shot
====================================
Legge tutti i documenti da daily_predictions_unified,
calcola il P/L giorno-per-giorno per sezione, e scrive in pl_storico.

Uso: python popola_pl_storico.py
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
    """Parse '2:1' -> {home, away, total, sign, btts}"""
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
    """Verifica un pronostico contro il risultato parsed."""
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


def get_results_map(target_date):
    """Recupera risultati reali da h2h_by_round per una data specifica."""
    from datetime import datetime as dt
    try:
        start = dt.strptime(target_date, "%Y-%m-%d")
        end = dt.strptime(target_date + "T23:59:59", "%Y-%m-%dT%H:%M:%S")
        pipeline = [
            {"$unwind": "$matches"},
            {"$match": {
                "matches.status": "Finished",
                "matches.real_score": {"$ne": None},
                "matches.date_obj": {"$gte": start, "$lte": end}
            }},
            {"$project": {
                "_id": 0,
                "home": "$matches.home",
                "away": "$matches.away",
                "real_score": "$matches.real_score"
            }}
        ]
        results = list(db.h2h_by_round.aggregate(pipeline))
        return {f"{r['home']}|||{r['away']}": r['real_score'] for r in results}
    except Exception:
        return {}


def calcola_pl_giorno(docs, results_map=None):
    """Calcola P/L per sezione da una lista di documenti dello stesso giorno."""
    if results_map is None:
        results_map = {}
    sez = {
        'tutti': {'pl': 0, 'bets': 0, 'wins': 0, 'staked': 0},
        'pronostici': {'pl': 0, 'bets': 0, 'wins': 0, 'staked': 0},
        'elite': {'pl': 0, 'bets': 0, 'wins': 0, 'staked': 0},
        'alto_rendimento': {'pl': 0, 'bets': 0, 'wins': 0, 'staked': 0},
    }

    for doc in docs:
        # Priorità score: 1) real_score da h2h_by_round, 2) live_score dal daemon
        home = doc.get('home', '')
        away = doc.get('away', '')
        real_score = results_map.get(f"{home}|||{away}")
        score = real_score or doc.get('live_score')
        match_over = True if real_score else False
        if not match_over:
            if doc.get('live_status') == 'Finished':
                match_over = True
            elif doc.get('date') and doc.get('match_time'):
                try:
                    kickoff = datetime.strptime(f"{doc['date']}T{doc['match_time']}", "%Y-%m-%dT%H:%M")
                    elapsed = (datetime.utcnow() - kickoff).total_seconds() / 60
                    if elapsed > 130:
                        match_over = True
                except Exception:
                    pass

        for p in doc.get('pronostici', []):
            esito = p.get('esito')

            # Se non c'è esito, prova a calcolarlo da score (h2h > live_score)
            if esito is None and score and match_over:
                parsed = parse_score(score)
                if parsed:
                    esito = check_pronostico(p.get('pronostico', ''), p.get('tipo', ''), parsed)

            if esito is None or esito == 'void':
                continue
            quota = p.get('quota') or 0
            stake = p.get('stake') or 1
            if not quota or quota <= 1:
                continue
            if p.get('pronostico') == 'NO BET':
                continue

            profit = (quota - 1) * stake if esito else -stake
            is_hit = esito is True

            soglia = 2.00 if p.get('tipo') == 'DOPPIA_CHANCE' else 2.51
            is_alto_rend = p.get('tipo') == 'RISULTATO_ESATTO' or quota >= soglia
            is_pronostici = not is_alto_rend and p.get('tipo') != 'RISULTATO_ESATTO'

            sez['tutti']['bets'] += 1
            sez['tutti']['staked'] += stake
            sez['tutti']['pl'] += profit
            if is_hit:
                sez['tutti']['wins'] += 1

            if is_pronostici:
                sez['pronostici']['bets'] += 1
                sez['pronostici']['staked'] += stake
                sez['pronostici']['pl'] += profit
                if is_hit:
                    sez['pronostici']['wins'] += 1

            if p.get('elite'):
                sez['elite']['bets'] += 1
                sez['elite']['staked'] += stake
                sez['elite']['pl'] += profit
                if is_hit:
                    sez['elite']['wins'] += 1

            if is_alto_rend:
                sez['alto_rendimento']['bets'] += 1
                sez['alto_rendimento']['staked'] += stake
                sez['alto_rendimento']['pl'] += profit
                if is_hit:
                    sez['alto_rendimento']['wins'] += 1

    # Arrotonda e calcola HR/ROI
    for s in sez.values():
        s['pl'] = round(s['pl'], 2)
        s['staked'] = round(s['staked'], 2)
        s['hr'] = round((s['wins'] / s['bets']) * 100, 1) if s['bets'] > 0 else 0
        s['roi'] = round((s['pl'] / s['staked']) * 100, 1) if s['staked'] > 0 else 0

    return sez


def main():
    print("=" * 60)
    print("POPOLA PL_STORICO — Calcolo storico completo")
    print("=" * 60)

    # Raggruppa tutti i documenti per data
    print("\n Caricamento documenti da daily_predictions_unified...")
    all_docs = list(db.daily_predictions_unified.find(
        {},
        {'date': 1, 'home': 1, 'away': 1, 'pronostici': 1, 'live_score': 1, 'live_status': 1, 'match_time': 1}
    ))
    print(f"  {len(all_docs)} documenti trovati")

    # Raggruppa per data
    by_date = {}
    for doc in all_docs:
        d = doc.get('date')
        if not d:
            continue
        if d not in by_date:
            by_date[d] = []
        by_date[d].append(doc)

    dates = sorted(by_date.keys())
    print(f"  {len(dates)} giornate da {dates[0]} a {dates[-1]}")

    # Calcola e scrivi
    print("\n Calcolo P/L e scrittura in pl_storico...")
    written = 0
    skipped = 0

    for date in dates:
        docs = by_date[date]
        results_map = get_results_map(date)
        sez = calcola_pl_giorno(docs, results_map)

        # Salta giorni senza bet
        if sez['tutti']['bets'] == 0:
            skipped += 1
            continue

        db.pl_storico.update_one(
            {'date': date},
            {
                '$set': {
                    'tutti': sez['tutti'],
                    'pronostici': sez['pronostici'],
                    'elite': sez['elite'],
                    'alto_rendimento': sez['alto_rendimento'],
                    'updated_at': datetime.utcnow(),
                },
                '$setOnInsert': {
                    'date': date,
                    'created_at': datetime.utcnow(),
                }
            },
            upsert=True
        )
        written += 1

    # Crea indice su date
    db.pl_storico.create_index('date', unique=True)

    print(f"\n Completato!")
    print(f"  {written} giorni scritti in pl_storico")
    print(f"  {skipped} giorni senza bet (saltati)")

    # Verifica
    total = db.pl_storico.count_documents({})
    sample = db.pl_storico.find_one(sort=[('date', -1)])
    print(f"\n Totale documenti in pl_storico: {total}")
    if sample:
        print(f"  Ultimo giorno: {sample['date']}")
        print(f"  Tutti: {sample['tutti']['bets']} bet, P/L {sample['tutti']['pl']}u, HR {sample['tutti']['hr']}%")


if __name__ == '__main__':
    main()
