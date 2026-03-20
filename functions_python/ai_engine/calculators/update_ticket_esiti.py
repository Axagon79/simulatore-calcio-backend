"""
UPDATE TICKET ESITI — Step 36 Pipeline Notturna
=================================================
Aggiorna il campo 'esito' di ogni selezione nelle bollette (collection 'bollette')
confrontando con i risultati reali da h2h_by_round e coppe.
Aggiorna anche 'esito_globale' della bolletta.
"""

import os, sys, re
from datetime import datetime, timedelta

# --- FIX PERCORSI ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db


# ==================== UTILITÀ ====================

def parse_score(real_score):
    if not real_score:
        return None
    parts = re.split(r'[:\-]', str(real_score).strip())
    if len(parts) != 2:
        return None
    try:
        h, a = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    total = h + a
    sign = '1' if h > a else ('X' if h == a else '2')
    btts = h > 0 and a > 0
    return {'home': h, 'away': a, 'total': total, 'sign': sign, 'btts': btts}


def check_pronostico(pronostico, tipo, parsed):
    if not parsed or not pronostico:
        return None
    p = pronostico.strip()
    t = tipo.upper() if tipo else ''
    if t in ('SEGNO', '1X2 ESITO FINALE', '1X2'):
        return parsed['sign'] == p
    if t in ('DOPPIA_CHANCE', 'DOPPIA CHANCE'):
        if p == '1X': return parsed['sign'] in ('1', 'X')
        if p == 'X2': return parsed['sign'] in ('X', '2')
        if p == '12': return parsed['sign'] in ('1', '2')
        return None
    if t in ('GOL', 'GOAL', 'GOAL/NOGOAL', 'U/O'):
        m = re.match(r'(Over|Under)\s+([\d.]+)', p, re.IGNORECASE)
        if m:
            return parsed['total'] > float(m.group(2)) if m.group(1).lower() == 'over' else parsed['total'] < float(m.group(2))
        if p.lower() in ('goal', 'si'): return parsed['btts']
        if p.lower() in ('nogoal', 'no'): return not parsed['btts']
        mg = re.match(r'MG\s+(\d+)-(\d+)', p, re.IGNORECASE)
        if mg:
            return int(mg.group(1)) <= parsed['total'] <= int(mg.group(2))
    if t in ('RISULTATO_ESATTO', 'RISULTATO ESATTO'):
        normalized = p.replace('-', ':')
        return f"{parsed['home']}:{parsed['away']}" == normalized
    return None


# ==================== MAIN ====================

def main():
    print(f"\n{'='*60}")
    print(f"🎫 UPDATE TICKET ESITI — Step 36")
    print(f"{'='*60}")
    print(f"Avvio: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")

    today = datetime.now().strftime('%Y-%m-%d')

    # 1. Carica risultati reali da h2h_by_round
    print("Caricamento risultati da h2h_by_round...")
    results_map = {}
    pipeline = [
        {"$unwind": "$matches"},
        {"$match": {"matches.real_score": {"$ne": None}}},
        {"$project": {
            "home": "$matches.home",
            "away": "$matches.away",
            "date": "$matches.date_obj",
            "score": "$matches.real_score",
        }}
    ]
    for doc in db.h2h_by_round.aggregate(pipeline):
        d = doc.get('date')
        if d:
            date_str = d.strftime('%Y-%m-%d')
            key = f"{doc['home']}|||{doc['away']}|||{date_str}"
            results_map[key] = doc['score']
            # Fallback ±1 giorno
            for delta in [-1, 1]:
                alt = (d + timedelta(days=delta)).strftime('%Y-%m-%d')
                alt_key = f"{doc['home']}|||{doc['away']}|||{alt}"
                results_map.setdefault(alt_key, doc['score'])

    # Fix coppe: aggiorna status/result da live_score per partite finite ma con status=scheduled
    for coll_name in ['matches_champions_league', 'matches_europa_league']:
        if coll_name in db.list_collection_names():
            stale = list(db[coll_name].find({
                'live_status': 'Finished',
                'live_score': {'$ne': None},
                'status': {'$ne': 'finished'}
            }))
            for doc in stale:
                parsed = parse_score(doc['live_score'])
                if parsed:
                    db[coll_name].update_one(
                        {'_id': doc['_id']},
                        {'$set': {
                            'status': 'finished',
                            'result': {'home_score': parsed['home'], 'away_score': parsed['away']},
                            'real_score': doc['live_score']
                        }}
                    )
            if stale:
                print(f"  ⚡ {coll_name}: {len(stale)} partite coppa aggiornate da live_score")

    # Risultati coppe
    for coll_name in ['matches_champions_league', 'matches_europa_league']:
        if coll_name in db.list_collection_names():
            for doc in db[coll_name].find(
                {"$or": [{"real_score": {"$ne": None}}, {"result": {"$exists": True}}, {"live_score": {"$ne": None}}]},
                {"home_team": 1, "away_team": 1, "match_date": 1, "real_score": 1, "result": 1, "status": 1, "live_score": 1, "live_status": 1}
            ):
                rs = doc.get('real_score')
                if not rs and doc.get('result'):
                    r = doc['result']
                    if r.get('home_score') is not None and r.get('away_score') is not None:
                        rs = f"{r['home_score']}:{r['away_score']}"
                # Fallback: usa live_score se live_status è Finished
                if not rs and doc.get('live_score') and (doc.get('live_status') or '').lower() == 'finished':
                    rs = doc['live_score']
                if not rs:
                    continue
                status = (doc.get('status') or '').lower()
                live_status = (doc.get('live_status') or '').lower()
                if status not in ('finished', 'ft') and live_status not in ('finished', 'ft'):
                    continue
                md = doc.get('match_date', '')
                if md:
                    try:
                        raw_date = md.split(' ')[0]
                        # Normalizza: DD-MM-YYYY → YYYY-MM-DD
                        if len(raw_date) == 10 and raw_date[2] == '-':
                            date_str = f"{raw_date[6:]}-{raw_date[3:5]}-{raw_date[0:2]}"
                        else:
                            date_str = raw_date
                    except:
                        continue
                    key = f"{doc['home_team']}|||{doc['away_team']}|||{date_str}"
                    results_map[key] = rs
                    # Fallback ±1 giorno per coppe
                    from datetime import datetime as dt2
                    try:
                        d = dt2.strptime(date_str, '%Y-%m-%d')
                        for delta in [-1, 1]:
                            alt = (d + timedelta(days=delta)).strftime('%Y-%m-%d')
                            results_map.setdefault(f"{doc['home_team']}|||{doc['away_team']}|||{alt}", rs)
                    except:
                        pass

    print(f"  {len(results_map)} risultati caricati.\n")

    # 2. Trova bollette con selezioni senza esito
    bollette = list(db.bollette.find({
        "selezioni.esito": None
    }))

    print(f"📋 Bollette con selezioni pending: {len(bollette)}")

    updated_count = 0
    sel_updated = 0

    for b in bollette:
        selezioni = b.get('selezioni', [])
        modified = False

        for sel in selezioni:
            if sel.get('esito') is not None and sel.get('real_score'):
                continue  # Già aggiornato con score

            home = sel.get('home', '')
            away = sel.get('away', '')
            match_date = sel.get('match_date', '')

            key = f"{home}|||{away}|||{match_date}"
            real_score = results_map.get(key)

            if not real_score:
                continue  # Risultato non ancora disponibile

            parsed = parse_score(real_score)
            if not parsed:
                continue

            hit = check_pronostico(sel.get('pronostico', ''), sel.get('mercato', ''), parsed)
            if hit is not None:
                sel['esito'] = hit
                sel['real_score'] = real_score
                sel['match_finished'] = True
                modified = True
                sel_updated += 1

        if modified:
            # Calcola esito globale
            esiti = [s.get('esito') for s in selezioni]
            if all(e is True for e in esiti):
                esito_globale = 'vinta'
            elif any(e is False for e in esiti):
                esito_globale = 'persa'
            elif any(e is None for e in esiti):
                esito_globale = None  # ancora partite da giocare
            else:
                esito_globale = None

            db.bollette.update_one(
                {"_id": b["_id"]},
                {"$set": {
                    "selezioni": selezioni,
                    "esito_globale": esito_globale,
                }}
            )
            updated_count += 1

    print(f"\n✅ Aggiornate {updated_count} bollette ({sel_updated} selezioni)")
    if updated_count == 0:
        print("   Nessuna bolletta da aggiornare (tutti gli esiti già presenti o risultati non ancora disponibili)")


if __name__ == "__main__":
    main()
