"""
CALCOLO PROFIT/LOSS — Step 28 Pipeline Notturna
================================================
Per ogni daily_prediction con risultato disponibile ma senza profit_loss:
1. Verifica esito (vinto/perso) con check_pronostico
2. Calcola profit_loss: vinto = stake × (quota - 1), perso = -stake
3. Aggiorna il documento MongoDB
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


# ==================== UTILITÀ (copiate da generate_track_record_report.py) ====================

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
    if tipo == 'SEGNO':
        return parsed['sign'] == p
    if tipo == 'DOPPIA_CHANCE':
        if p == '1X': return parsed['sign'] in ('1', 'X')
        if p == 'X2': return parsed['sign'] in ('X', '2')
        if p == '12': return parsed['sign'] in ('1', '2')
        return None
    if tipo == 'GOL':
        m = re.match(r'(Over|Under)\s+([\d.]+)', p, re.IGNORECASE)
        if m:
            return parsed['total'] > float(m.group(2)) if m.group(1).lower() == 'over' else parsed['total'] < float(m.group(2))
        if p.lower() == 'goal': return parsed['btts']
        if p.lower() == 'nogoal': return not parsed['btts']
        mg = re.match(r'MG\s+(\d+)-(\d+)', p, re.IGNORECASE)
        if mg:
            return int(mg.group(1)) <= parsed['total'] <= int(mg.group(2))
    if tipo == 'RISULTATO_ESATTO':
        real_str = f"{parsed['home']}:{parsed['away']}"
        return p.replace('-', ':') == real_str
    return None


# ==================== CARICA RISULTATI REALI ====================

print(f"\n{'='*60}")
print(f"STEP 28: CALCOLO PROFIT/LOSS")
print(f"{'='*60}")
print(f"Avvio: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")

today = datetime.now().strftime('%Y-%m-%d')

# Risultati da h2h_by_round
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
        # Fallback ±1 giorno: h2h_by_round può avere timezone diverso (es. match
        # argentino 21:00 CET 1/3 salvato come 04:00 UTC 2/3 in date_obj).
        # setdefault = non sovrascrive se esiste già il match esatto per quel giorno.
        for delta in [-1, 1]:
            alt = (d + timedelta(days=delta)).strftime('%Y-%m-%d')
            alt_key = f"{doc['home']}|||{doc['away']}|||{alt}"
            results_map.setdefault(alt_key, doc['score'])

# Risultati coppe (supporta sia real_score che result.home_score/away_score)
for coll_name in ['matches_champions_league', 'matches_europa_league']:
    if coll_name in db.list_collection_names():
        for doc in db[coll_name].find(
            {"$or": [{"real_score": {"$ne": None}}, {"result": {"$exists": True}}]},
            {"home_team": 1, "away_team": 1, "match_date": 1, "real_score": 1, "result": 1, "status": 1}
        ):
            # Prova real_score, altrimenti costruisci da result
            rs = doc.get('real_score')
            if not rs and doc.get('result'):
                r = doc['result']
                if r.get('home_score') is not None and r.get('away_score') is not None:
                    rs = f"{r['home_score']}:{r['away_score']}"
            if not rs:
                continue
            # Accetta solo partite finite
            status = (doc.get('status') or '').lower()
            if status not in ('finished', 'ft'):
                continue
            md = doc.get('match_date', '')
            if md:
                try:
                    dt = md.split(' ')[0].split('-')
                    date_str = md.split(' ')[0] if len(dt[0]) == 4 else f"{dt[2]}-{dt[1]}-{dt[0]}"
                except:
                    continue
                key = f"{doc['home_team']}|||{doc['away_team']}|||{date_str}"
                results_map[key] = rs

print(f"  {len(results_map)} risultati caricati.\n")


# ==================== TROVA PREDICTIONS SENZA PROFIT_LOSS ====================

# Processa tutte le collection di pronostici (A, C, Unified)
PREDICTION_COLLECTIONS = [
    'daily_predictions',
    'daily_predictions_engine_c',
    'daily_predictions_unified',
]

# Cerca documenti con date passate dove almeno un pronostico:
# - non ha profit_loss (pending), oppure
# - ha esito='void' (rinvio che potrebbe essere stato recuperato), oppure
# - ha profit_loss ma manca hit (fix retroattivo)
query = {
    'date': {'$lte': today},
    'pronostici': {'$elemMatch': {'$or': [
        {'profit_loss': {'$exists': False}},
        {'profit_loss': None},
        {'esito': 'void'},
        {'hit': None, 'profit_loss': {'$ne': None}},
    ]}},
}

global_stats = {}

for coll_name in PREDICTION_COLLECTIONS:
    coll = db[coll_name]
    docs = list(coll.find(query))

    stats = {
        'documenti': len(docs),
        'pronostici': 0,
        'aggiornati': 0,
        'vinti': 0,
        'persi': 0,
        'pending': 0,
        'annullati': 0,
        'recuperati': 0,
        'errori': 0,
    }

    print(f"\n--- {coll_name}: {len(docs)} documenti da processare ---")

    for doc in docs:
        date = doc.get('date', '')
        home = doc.get('home', '')
        away = doc.get('away', '')
        key = f"{home}|||{away}|||{date}"
        real_score = results_map.get(key)
        parsed = parse_score(real_score) if real_score else None

        updates = {}
        for i, prono in enumerate(doc.get('pronostici', [])):
            stats['pronostici'] += 1

            # Skip se già calcolato, MA ricalcola se:
            # - esito='void' e ora il risultato esiste
            # - hit manca (fix retroattivo)
            was_void = False
            if prono.get('profit_loss') is not None:
                if prono.get('hit') is None and parsed is not None:
                    pass  # Ricalcola per scrivere hit
                elif prono.get('esito') == 'void' and parsed is not None:
                    was_void = True
                else:
                    continue

            pronostico = prono.get('pronostico', '')
            tipo = prono.get('tipo', '')
            stake = prono.get('stake') or 0
            quota = prono.get('quota')

            esito = check_pronostico(pronostico, tipo, parsed)

            if esito is True and quota:
                pl = round(stake * (quota - 1), 2)
                stats['vinti'] += 1
                if was_void:
                    stats['recuperati'] += 1
                    print(f"  ✅ RECUPERATO (void→hit): {home} vs {away} ({date}) — {real_score}")
            elif esito is False:
                pl = -stake
                stats['persi'] += 1
                if was_void:
                    stats['recuperati'] += 1
                    print(f"  ✅ RECUPERATO (void→miss): {home} vs {away} ({date}) — {real_score}")
            elif parsed is None:
                # Nessun risultato trovato — controlla se è un rinvio (>7 giorni)
                try:
                    days_old = (datetime.now() - datetime.strptime(date, '%Y-%m-%d')).days
                except ValueError:
                    days_old = 0
                if days_old >= 7:
                    pl = 0
                    esito = 'void'
                    stats['annullati'] += 1
                    print(f"  ⛔ VOID: {home} vs {away} ({date}) — {days_old}gg senza risultato → rinvio/annullato")
                else:
                    pl = None
                    stats['pending'] += 1
            else:
                pl = None
                stats['pending'] += 1

            updates[f'pronostici.{i}.esito'] = esito
            updates[f'pronostici.{i}.profit_loss'] = pl
            if esito is True or esito is False:
                updates[f'pronostici.{i}.hit'] = esito
            stats['aggiornati'] += 1

        if updates:
            try:
                coll.update_one({'_id': doc['_id']}, {'$set': updates})
            except Exception as e:
                print(f"  ❌ Errore update {home} vs {away} ({date}): {e}")
                stats['errori'] += 1

    global_stats[coll_name] = stats


# ==================== RIEPILOGO ====================

print(f"\n{'='*60}")
print(f"RIEPILOGO PROFIT/LOSS")
print(f"{'='*60}")
for coll_name, stats in global_stats.items():
    print(f"\n  📊 {coll_name}:")
    print(f"    Documenti processati:  {stats['documenti']}")
    print(f"    Pronostici totali:     {stats['pronostici']}")
    print(f"    Aggiornati ora:        {stats['aggiornati']}")
    print(f"      Vinti:     {stats['vinti']}")
    print(f"      Persi:     {stats['persi']}")
    print(f"      Pending:   {stats['pending']} (risultato non disponibile)")
    print(f"      Annullati: {stats['annullati']} (rinvio >7gg)")
    print(f"      Recuperati:{stats['recuperati']} (void→risultato)")
    print(f"      Errori:    {stats['errori']}")
print(f"\nFine: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

# ==================== P/L MENSILE PRE-CALCOLATO ====================
# Aggiorna monthly_stats con il P/L progressivo del mese corrente
try:
    now = datetime.now()
    month_start = now.strftime('%Y-%m-01')
    month_end = now.strftime('%Y-%m-%d')
    month_label = now.strftime('%Y-%m')

    # Query tutti i pronostici unified del mese con esito
    month_docs = list(db.daily_predictions_unified.find(
        {'date': {'$gte': month_start, '$lte': month_end}},
        {'pronostici': 1}
    ))

    # Calcola P/L per sezione (stessa logica del frontend: filtro per quota)
    sezioni = {
        'tutti': {'pl': 0.0, 'bets': 0, 'wins': 0, 'staked': 0.0},
        'pronostici': {'pl': 0.0, 'bets': 0, 'wins': 0, 'staked': 0.0},
        'elite': {'pl': 0.0, 'bets': 0, 'wins': 0, 'staked': 0.0},
        'alto_rendimento': {'pl': 0.0, 'bets': 0, 'wins': 0, 'staked': 0.0},
    }

    for doc in month_docs:
        for p in doc.get('pronostici', []):
            esito = p.get('esito')
            if esito is None or esito == 'void':
                continue
            quota = p.get('quota', 0) or 0
            stake = p.get('stake', 1) or 1
            if quota <= 1:
                continue
            pronostico = p.get('pronostico', '')
            tipo = p.get('tipo', '')
            if pronostico == 'NO BET':
                continue

            profit = (quota - 1) * stake if esito is True else -stake

            # Soglia quota: DC < 2.00 = pronostici, DC >= 2.00 = alto rendimento
            # Altri: < 2.51 = pronostici, >= 2.51 = alto rendimento
            # RISULTATO_ESATTO = sempre alto rendimento
            soglia = 2.00 if tipo == 'DOPPIA_CHANCE' else 2.51
            is_alto = tipo == 'RISULTATO_ESATTO' or quota >= soglia
            is_pronostici = not is_alto and tipo != 'RISULTATO_ESATTO'

            # Tutti (somma senza doppi)
            sezioni['tutti']['bets'] += 1
            sezioni['tutti']['staked'] += stake
            sezioni['tutti']['pl'] += profit
            if esito is True:
                sezioni['tutti']['wins'] += 1

            # Pronostici (quota bassa)
            if is_pronostici:
                sezioni['pronostici']['bets'] += 1
                sezioni['pronostici']['staked'] += stake
                sezioni['pronostici']['pl'] += profit
                if esito is True:
                    sezioni['pronostici']['wins'] += 1

            # Elite (trasversale)
            if p.get('elite', False):
                sezioni['elite']['bets'] += 1
                sezioni['elite']['staked'] += stake
                sezioni['elite']['pl'] += profit
                if esito is True:
                    sezioni['elite']['wins'] += 1

            # Alto rendimento (quota alta + RE)
            if is_alto:
                sezioni['alto_rendimento']['bets'] += 1
                sezioni['alto_rendimento']['staked'] += stake
                sezioni['alto_rendimento']['pl'] += profit
                if esito is True:
                    sezioni['alto_rendimento']['wins'] += 1

    # Salva nel DB
    for sez_key, s in sezioni.items():
        s['pl'] = round(s['pl'], 2)
        s['staked'] = round(s['staked'], 2)
        s['roi'] = round((s['pl'] / s['staked']) * 100, 1) if s['staked'] > 0 else 0
        s['hr'] = round((s['wins'] / s['bets']) * 100, 1) if s['bets'] > 0 else 0

    db.monthly_stats.update_one(
        {'month': month_label},
        {'$set': {
            'month': month_label,
            'sezioni': sezioni,
            'updated_at': now,
        }},
        upsert=True
    )

    for sez_key, s in sezioni.items():
        if s['bets'] > 0:
            pl_color = '🟢' if s['pl'] >= 0 else '🔴'
            print(f"  {pl_color} {sez_key}: {'+' if s['pl'] >= 0 else ''}{s['pl']}u "
                  f"({s['wins']}/{s['bets']} = {s['hr']}% HR, ROI {'+' if s['roi'] >= 0 else ''}{s['roi']}%)")
except Exception as e:
    print(f"\n⚠️ Errore calcolo P/L mensile: {e}")
